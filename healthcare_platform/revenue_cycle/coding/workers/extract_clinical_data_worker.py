"""Extract clinical data from FHIR encounter for coding.

CIB7 External Task Topic: coding.extract_clinical_data
BPMN Error Codes: ENCOUNTER_NOT_FOUND, FHIR_SERVICE_ERROR
"""
from __future__ import annotations

from typing import Any

from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
    ExternalServiceException,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from dataclasses import dataclass


@dataclass
class ExtractClinicalDataInput:
    """Input model for extract clinical data worker."""
    encounter_id: str
    tenant_id: str

    def __post_init__(self):
        if not self.encounter_id:
            raise ValueError("encounter_id is required")
        if not self.tenant_id:
            raise ValueError("tenant_id is required")


@dataclass
class ExtractClinicalDataOutput:
    """Output model for extract clinical data worker."""
    encounter_id: str
    patient_id: str
    diagnoses: list[dict]
    procedures: list[dict]
    clinical_notes: str
    encounter_class: str = "ambulatorio"
    primary_diagnosis: str = ""
    medications: list[dict] = None

    def __post_init__(self):
        if self.medications is None:
            self.medications = []


class ExtractClinicalDataWorker:
    """Extracts clinical data from a FHIR Encounter for coding workflow.

    Fetches the encounter resource and related Condition, Procedure,
    DocumentReference, and MedicationRequest resources to build
    a complete clinical picture for CID-10 and TUSS coding.

    Archetype: FINANCIAL_CALCULATION
    """

    TOPIC = "revenue_cycle.coding.extract_clinical_data"

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self._fhir = fhir_client
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    # ── Public API ────────────────────────────────────────────────────

    @require_tenant
    @track_task_execution(metric_name="coding_extract_clinical_data")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Extract clinical data from FHIR encounter.

        Task Variables (input):
            encounter_id: str - FHIR Encounter logical ID
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            extracted_diagnoses: list[dict] - CID-10 diagnoses found
            extracted_procedures: list[dict] - Procedures performed
            clinical_notes: str - Combined clinical notes text
            encounter_class: str - Encounter class (ambulatorio, internacao, urgencia)
            primary_diagnosis: str - Primary CID-10 code
        """
        ctx = get_required_tenant()
        encounter_id: str = task_variables.get("encounter_id", "")

        if not encounter_id:
            raise CodingException(
                _("Entrada inválida: {field} é obrigatório").format(
                    field="encounter_id"
                ),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "extracting_clinical_data",
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id,
        )

        # ── Fetch encounter ──────────────────────────────────────────

        encounter = await self._fetch_encounter(encounter_id, ctx.tenant_id)

        # ── Extract encounter class ──────────────────────────────────

        encounter_class = self._extract_encounter_class(encounter)

        # ── Fetch related resources in parallel ──────────────────────

        diagnoses = await self._fetch_diagnoses(encounter_id, ctx.tenant_id)
        procedures = await self._fetch_procedures(encounter_id, ctx.tenant_id)
        clinical_notes = await self._fetch_clinical_notes(encounter_id, ctx.tenant_id)
        medications = await self._fetch_medications(encounter_id, ctx.tenant_id)

        # ── Determine primary diagnosis ──────────────────────────────

        primary_diagnosis = self._determine_primary_diagnosis(diagnoses, encounter)

        self._logger.info(
            "clinical_data_extracted",
            encounter_id=encounter_id,
            diagnoses_count=len(diagnoses),
            procedures_count=len(procedures),
            notes_length=len(clinical_notes),
            encounter_class=encounter_class,
            primary_diagnosis=primary_diagnosis,
            tenant_id=ctx.tenant_id,
        )

        return {
            "extracted_diagnoses": diagnoses,
            "extracted_procedures": procedures,
            "clinical_notes": clinical_notes,
            "encounter_class": encounter_class,
            "primary_diagnosis": primary_diagnosis,
            "medications": medications,
        }

    

    def _evaluate_coding_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate coding_audit DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='coding_audit',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}


    # ── Private helpers ───────────────────────────────────────────────

    async def _fetch_encounter(
        self, encounter_id: str, tenant_id: str
    ) -> dict[str, Any]:
        """Fetch encounter from FHIR, raising BPMN error if not found."""
        try:
            encounter = await self._fhir.get_encounter(encounter_id)
        except ExternalServiceException as exc:
            if exc.status_code == 404:
                self._logger.error(
                    "encounter_not_found",
                    encounter_id=encounter_id,
                    tenant_id=tenant_id,
                )
                raise BpmnErrorException(
                    error_code="ENCOUNTER_NOT_FOUND",
                    message=_("Atendimento não encontrado: {id}").format(
                        id=encounter_id
                    ),
                    details={"encounter_id": encounter_id},
                ) from exc
            self._logger.error(
                "fhir_service_error",
                encounter_id=encounter_id,
                error=str(exc),
                tenant_id=tenant_id,
            )
            raise ExternalServiceException(
                _("Erro ao consultar serviço FHIR: {error}").format(error=str(exc)),
                service_name="fhir",
                operation="get_encounter",
                retryable=True,
            ) from exc

        return encounter

    def _extract_encounter_class(self, encounter: dict[str, Any]) -> str:
        """Map FHIR encounter class to Brazilian healthcare classification."""
        fhir_class = encounter.get("class", {})
        code = fhir_class.get("code", "") if isinstance(fhir_class, dict) else ""

        class_mapping: dict[str, str] = {
            "AMB": "ambulatorio",
            "IMP": "internacao",
            "EMER": "urgencia",
            "SS": "ambulatorio",
            "HH": "domiciliar",
            "OBSENC": "internacao",
        }
        return class_mapping.get(code, "ambulatorio")

    async def _fetch_diagnoses(
        self, encounter_id: str, tenant_id: str
    ) -> list[dict[str, Any]]:
        """Fetch Condition resources linked to the encounter."""
        try:
            conditions = await self._fhir.search(
                "Condition", {"encounter": encounter_id}
            )
        except ExternalServiceException:
            self._logger.warning(
                "diagnoses_fetch_failed",
                encounter_id=encounter_id,
                tenant_id=tenant_id,
            )
            return []

        diagnoses: list[dict[str, Any]] = []
        for condition in conditions:
            coding_list = (
                condition.get("code", {}).get("coding", [])
                if isinstance(condition.get("code"), dict)
                else []
            )
            for coding in coding_list:
                system = coding.get("system", "")
                if "icd" in system.lower() or "cid" in system.lower():
                    diagnoses.append(
                        {
                            "code": coding.get("code", ""),
                            "display": coding.get("display", ""),
                            "system": system,
                            "clinical_status": (
                                condition.get("clinicalStatus", {})
                                .get("coding", [{}])[0]
                                .get("code", "")
                                if isinstance(
                                    condition.get("clinicalStatus"), dict
                                )
                                else ""
                            ),
                        }
                    )
        return diagnoses

    async def _fetch_procedures(
        self, encounter_id: str, tenant_id: str
    ) -> list[dict[str, Any]]:
        """Fetch Procedure resources linked to the encounter."""
        try:
            procedures = await self._fhir.search(
                "Procedure", {"encounter": encounter_id}
            )
        except ExternalServiceException:
            self._logger.warning(
                "procedures_fetch_failed",
                encounter_id=encounter_id,
                tenant_id=tenant_id,
            )
            return []

        result: list[dict[str, Any]] = []
        for proc in procedures:
            coding_list = (
                proc.get("code", {}).get("coding", [])
                if isinstance(proc.get("code"), dict)
                else []
            )
            for coding in coding_list:
                result.append(
                    {
                        "code": coding.get("code", ""),
                        "display": coding.get("display", ""),
                        "system": coding.get("system", ""),
                        "status": proc.get("status", ""),
                        "performed_period": proc.get("performedPeriod", {}),
                    }
                )
        return result

    async def _fetch_clinical_notes(
        self, encounter_id: str, tenant_id: str
    ) -> str:
        """Fetch DocumentReference resources and combine note text."""
        try:
            docs = await self._fhir.search(
                "DocumentReference", {"encounter": encounter_id}
            )
        except ExternalServiceException:
            self._logger.warning(
                "clinical_notes_fetch_failed",
                encounter_id=encounter_id,
                tenant_id=tenant_id,
            )
            return ""

        notes_parts: list[str] = []
        for doc in docs:
            for content in doc.get("content", []):
                attachment = content.get("attachment", {})
                if attachment.get("contentType", "") == "text/plain":
                    data = attachment.get("data", "")
                    if data:
                        notes_parts.append(data)
                    title = attachment.get("title", "")
                    if title:
                        notes_parts.append(title)

        return "\n".join(notes_parts)

    async def _fetch_medications(
        self, encounter_id: str, tenant_id: str
    ) -> list[dict[str, Any]]:
        """Fetch MedicationRequest resources linked to the encounter."""
        try:
            med_requests = await self._fhir.search(
                "MedicationRequest", {"encounter": encounter_id}
            )
        except ExternalServiceException:
            self._logger.warning(
                "medications_fetch_failed",
                encounter_id=encounter_id,
                tenant_id=tenant_id,
            )
            return []

        medications: list[dict[str, Any]] = []
        for med in med_requests:
            medication_ref = med.get("medicationCodeableConcept", {})
            coding_list = medication_ref.get("coding", []) if isinstance(
                medication_ref, dict
            ) else []
            for coding in coding_list:
                medications.append(
                    {
                        "code": coding.get("code", ""),
                        "display": coding.get("display", ""),
                        "system": coding.get("system", ""),
                        "status": med.get("status", ""),
                    }
                )
        return medications

    def _determine_primary_diagnosis(
        self,
        diagnoses: list[dict[str, Any]],
        encounter: dict[str, Any],
    ) -> str:
        """Determine primary diagnosis code from encounter or conditions.

        Priority:
        1. Encounter.diagnosis with rank=1 or use=AD (admitting diagnosis)
        2. First condition with clinicalStatus=active
        3. First diagnosis in list
        """
        # Check encounter-level diagnosis ranking
        encounter_diagnoses = encounter.get("diagnosis", [])
        for diag in encounter_diagnoses:
            rank = diag.get("rank")
            use_coding = diag.get("use", {}).get("coding", [{}])
            use_code = use_coding[0].get("code", "") if use_coding else ""

            if rank == 1 or use_code == "AD":
                condition_ref = diag.get("condition", {}).get("reference", "")
                # Try to match with extracted diagnoses
                for extracted in diagnoses:
                    if extracted.get("code"):
                        return extracted["code"]

        # Fallback: first active diagnosis
        for diag in diagnoses:
            if diag.get("clinical_status") == "active" and diag.get("code"):
                return diag["code"]

        # Fallback: first available
        if diagnoses and diagnoses[0].get("code"):
            return diagnoses[0]["code"]

        return ""


def register_worker():
    """Register the extract clinical data worker with the task manager."""
    return ExtractClinicalDataWorker.TOPIC
