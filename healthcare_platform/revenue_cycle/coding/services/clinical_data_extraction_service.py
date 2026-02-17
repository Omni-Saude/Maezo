"""Clinical data extraction service - extracted from ExtractClinicalDataWorkerV2.

Handles FHIR resource fetching: encounters, diagnoses, procedures, notes, medications.
"""
from __future__ import annotations
import re
from typing import Any

from healthcare_platform.shared.domain.exceptions import BpmnErrorException, ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.multi_tenant.context import get_required_tenant

logger = get_logger(__name__)


class ClinicalDataExtractionService:
    """Orchestrates clinical data extraction from FHIR resources."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self._fhir = fhir_client

    async def extract(self, encounter_id: str, tenant_id: str) -> dict[str, Any]:
        """Extract all clinical data for an encounter.

        Returns dict with encounter, diagnoses, procedures, notes, medications.
        """
        encounter = await self.fetch_encounter(encounter_id, tenant_id)
        diagnoses = await self.fetch_diagnoses(encounter_id, tenant_id)
        procedures = await self.fetch_procedures(encounter_id, tenant_id)
        notes = await self.fetch_clinical_notes(encounter_id, tenant_id)
        medications = await self.fetch_medications(encounter_id, tenant_id)
        return {
            "encounter": encounter,
            "extracted_diagnoses": diagnoses,
            "extracted_procedures": procedures,
            "clinical_notes": notes,
            "medications": medications,
        }

    async def fetch_encounter(self, enc_id: str, tenant_id: str) -> dict[str, Any]:
        """Fetch FHIR Encounter resource."""
        try:
            return await self._fhir.get_encounter(enc_id)
        except ExternalServiceException as exc:
            if exc.status_code == 404:
                logger.error("encounter_not_found", encounter_id=enc_id, tenant_id=tenant_id)
                raise BpmnErrorException(
                    error_code="ENCOUNTER_NOT_FOUND",
                    message=_("Atendimento nao encontrado: {id}").format(id=enc_id),
                    details={"encounter_id": enc_id},
                ) from exc
            raise ExternalServiceException(
                _("Erro ao consultar FHIR: {error}").format(error=str(exc)),
                service_name="fhir",
                operation="get_encounter",
                retryable=True,
            ) from exc

    async def fetch_diagnoses(self, enc_id: str, tenant_id: str) -> list[dict[str, Any]]:
        """Fetch diagnoses (Condition resources) for encounter."""
        try:
            conds = await self._fhir.search("Condition", {"encounter": enc_id})
        except ExternalServiceException:
            logger.warning("diagnoses_fetch_failed", encounter_id=enc_id)
            return []
        diags: list[dict[str, Any]] = []
        for cond in conds:
            for coding in cond.get("code", {}).get("coding", []):
                sys = coding.get("system", "")
                if "icd" in sys.lower() or "cid" in sys.lower():
                    diags.append({
                        "code": coding.get("code", ""),
                        "display": coding.get("display", ""),
                        "system": sys,
                        "clinical_status": (
                            cond.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "")
                        ),
                    })
        return diags

    async def fetch_procedures(self, enc_id: str, tenant_id: str) -> list[dict[str, Any]]:
        """Fetch Procedure resources for encounter."""
        try:
            procs = await self._fhir.search("Procedure", {"encounter": enc_id})
        except ExternalServiceException:
            logger.warning("procedures_fetch_failed", encounter_id=enc_id)
            return []
        return [
            {
                "code": c.get("code", ""),
                "display": c.get("display", ""),
                "system": c.get("system", ""),
                "status": p.get("status", ""),
            }
            for p in procs
            for c in p.get("code", {}).get("coding", [])
        ]

    async def fetch_clinical_notes(self, enc_id: str, tenant_id: str) -> str:
        """Fetch clinical notes (DocumentReference) for encounter."""
        try:
            docs = await self._fhir.search("DocumentReference", {"encounter": enc_id})
        except ExternalServiceException:
            logger.warning("clinical_notes_fetch_failed", encounter_id=enc_id)
            return ""
        parts = [
            att.get("data", "")
            for doc in docs
            for cont in doc.get("content", [])
            if (att := cont.get("attachment", {})).get("contentType") == "text/plain"
            and att.get("data")
        ]
        return "\n".join(parts)

    async def fetch_medications(self, enc_id: str, tenant_id: str) -> list[dict[str, Any]]:
        """Fetch MedicationRequest resources for encounter."""
        try:
            meds = await self._fhir.search("MedicationRequest", {"encounter": enc_id})
        except ExternalServiceException:
            logger.warning("medications_fetch_failed", encounter_id=enc_id)
            return []
        return [
            {
                "code": c.get("code", ""),
                "display": c.get("display", ""),
                "system": c.get("system", ""),
                "status": m.get("status", ""),
            }
            for m in meds
            for c in m.get("medicationCodeableConcept", {}).get("coding", [])
        ]

    def extract_variables_from_mock_task(self, mock_task: Any) -> dict[str, Any]:
        """Extract variables from v1 mock_task object."""
        def get_val(key, alt_key=None):
            val = mock_task.get_variable(key)
            if val is None and alt_key:
                val = mock_task.get_variable(alt_key)
            return val

        variables: dict[str, Any] = {}
        if (val := get_val('encounter_id', 'encounterId')) is not None:
            variables['encounterId'] = val
        if (val := get_val('tenant_id', 'tenantId')) is not None:
            variables['tenantId'] = val
        if (val := get_val('patient_id', 'patientId')) is not None:
            variables['patientId'] = val
        for key_pair in [('cid10_codes', 'validatedCid10'), ('tuss_codes', 'validatedTuss'),
                         ('suggested_cid10_codes', 'suggestedCid10Codes'),
                         ('suggested_tuss_codes', 'suggestedTussCodes')]:
            if (val := get_val(key_pair[0], key_pair[1])) is not None:
                variables[key_pair[1]] = val
        for field in ['clinicalNotes', 'proceduresText', 'codedBy', 'patientAge',
                      'comorbidities', 'encounterClass', 'auditStatus', 'fraudRiskLevel']:
            snake = re.sub(r'([a-z])([A-Z])', r'_', field).lower()
            if (val := get_val(snake, field)) is not None:
                variables[field] = val
        if (coding_result := get_val('coding_rules_result', 'codingRulesResult')) is not None:
            if isinstance(coding_result, dict):
                variables['rulesApplied'] = coding_result.get('rules', [])
            variables['codingRulesResult'] = coding_result
        return variables

    async def extract_with_dmn(self, enc_id: str, tenant_id: str, dmn_service: Any) -> dict[str, Any]:
        """Extract clinical data and evaluate DMN tables."""
        data = await self.extract(enc_id, tenant_id)
        enc = data["encounter"]
        diag = data["extracted_diagnoses"]
        proc = data["extracted_procedures"]

        # DMN evaluation for encounter class mapping
        fhir_cls = enc.get("class", {})
        code = fhir_cls.get("code", "") if isinstance(fhir_cls, dict) else ""
        cls_res = self._evaluate_dmn(dmn_service, "data_extraction/encounter_class_mapping",
                                      {"fhir_class_code": code}, tenant_id)
        enc_cls = cls_res.get("encounter_class", "ambulatorio")

        # DMN evaluation for primary diagnosis
        pri_res = self._evaluate_dmn(dmn_service, "data_extraction/primary_diagnosis_priority",
            {"encounter_diagnoses": enc.get("diagnosis", []), "extracted_diagnoses": diag}, tenant_id)
        pri_diag = pri_res.get("primary_code", "") or (diag[0].get("code", "") if diag else "")

        return {
            "extracted_diagnoses": diag,
            "extracted_procedures": proc,
            "clinical_notes": data["clinical_notes"],
            "encounter_class": enc_cls,
            "primary_diagnosis": pri_diag,
            "medications": data["medications"]
        }

    def _evaluate_dmn(self, dmn_service: Any, table_name: str, inputs: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        try:
            return dmn_service.evaluate(tenant_id=tenant_id, category='coding_audit',
                                       table_name=table_name, inputs=inputs)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task_compat(self, execute_fn: Any, variables: dict[str, Any]) -> Any:
        """V1 backward-compatible test result wrapper."""
        from dataclasses import dataclass, field
        from typing import Dict, Optional
        from healthcare_platform.shared.domain.exceptions import BpmnErrorException

        @dataclass
        class _Result:
            success: bool
            variables: Dict[str, Any] = field(default_factory=dict)
            error_code: Optional[str] = None
            error_message: Optional[str] = None

        try:
            result = await execute_fn(variables)
            return _Result(success=True, variables=result)
        except BpmnErrorException as e:
            return _Result(success=False, error_code=e.error_code, error_message=str(e), variables=e.details or {})
        except Exception as e:
            error_code = getattr(e, 'bpmn_error_code', getattr(e, 'error_code', None))
            return _Result(success=False, error_code=error_code, error_message=str(e))
