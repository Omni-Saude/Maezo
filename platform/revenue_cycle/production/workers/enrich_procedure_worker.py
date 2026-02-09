"""Enrich procedures with CID-10 diagnosis, performer, and body site data.

CIB7 External Task Topic: production.enrich_procedure
BPMN Error Codes: MISSING_DIAGNOSIS, CODING_ERROR
"""
from __future__ import annotations

from typing import Any

from platform.shared.domain.exceptions import CodingException, MissingDiagnosisCode
from platform.shared.domain.value_objects import CodedValue, FHIRReference
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


class EnrichProcedureWorker:
    """Enriches captured procedures with clinical context.

    Adds:
    - CID-10 diagnosis codes from encounter
    - Performer references (practitioner)
    - Body site information
    - Specialty classification
    """

    TOPIC = "production.enrich_procedure"

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self._fhir = fhir_client
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="production_enrich_procedure")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Enrich procedures with clinical data from FHIR.

        Task Variables (input):
            captured_procedures: list[dict] - Procedures from capture step
            encounter_reference: str - FHIR reference (e.g. "Encounter/123")

        Returns:
            enriched_procedures: list[dict] - Procedures with added clinical data
            diagnosis_codes: list[str] - CID-10 codes from encounter
            enrichment_warnings: list[str] - Non-fatal warnings
        """
        ctx = get_required_tenant()
        procedures: list[dict[str, Any]] = task_variables.get("captured_procedures", [])
        encounter_ref_str: str = task_variables.get("encounter_reference", "")

        if not procedures:
            raise CodingException(
                _("Invalid input: {field} - {reason}").format(
                    field="captured_procedures", reason="empty"
                ),
                bpmn_error_code="CODING_ERROR",
            )

        encounter_id = encounter_ref_str.rsplit("/", 1)[-1] if encounter_ref_str else ""

        self._logger.info(
            "enriching_procedures",
            procedure_count=len(procedures),
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id,
        )

        # Fetch encounter for diagnosis and performer info
        encounter_data: dict[str, Any] = {}
        diagnosis_codes: list[str] = []
        performers: list[str] = []
        warnings: list[str] = []

        if encounter_id:
            try:
                encounter_data = await self._fhir.get_encounter(encounter_id)
                # Extract diagnosis codes (CID-10)
                for reason in encounter_data.get("reasonCode", []):
                    for coding in reason.get("coding", []):
                        if "icd" in coding.get("system", "").lower() or "cid" in coding.get("system", "").lower():
                            diagnosis_codes.append(coding.get("code", ""))

                # Extract performer references
                for participant in encounter_data.get("participant", []):
                    individual = participant.get("individual", {})
                    ref = individual.get("reference", "")
                    if ref:
                        performers.append(ref)

            except Exception as exc:
                self._logger.warning(
                    "encounter_fetch_partial",
                    encounter_id=encounter_id,
                    error=str(exc),
                    tenant_id=ctx.tenant_id,
                )
                warnings.append(f"Could not fetch encounter data: {encounter_id}")

        # Validate at least one diagnosis code
        if not diagnosis_codes:
            self._logger.error(
                "missing_diagnosis",
                encounter_id=encounter_id,
                tenant_id=ctx.tenant_id,
            )
            raise MissingDiagnosisCode(
                _("Missing diagnosis code (CID-10) for procedure {code}").format(
                    code=procedures[0].get("code", "unknown")
                ),
                details={"encounter_id": encounter_id},
            )

        # Enrich each procedure
        enriched: list[dict[str, Any]] = []
        for proc in procedures:
            enriched_proc = {**proc}
            enriched_proc["diagnosis_codes"] = diagnosis_codes
            enriched_proc["performer_references"] = performers
            enriched_proc["encounter_reference"] = encounter_ref_str

            # Try to fetch body site from FHIR Procedure resource
            proc_id = proc.get("procedure_id", "")
            if proc_id:
                try:
                    fhir_proc = await self._fhir.read("Procedure", proc_id)
                    body_site = fhir_proc.get("bodySite", [])
                    if body_site:
                        coding = body_site[0].get("coding", [{}])[0]
                        enriched_proc["body_site"] = {
                            "system": coding.get("system", ""),
                            "code": coding.get("code", ""),
                            "display": coding.get("display", ""),
                        }
                except Exception:
                    warnings.append(f"Could not fetch body site for {proc_id}")

            if not enriched_proc.get("body_site"):
                enriched_proc["body_site"] = None

            enriched.append(enriched_proc)

        if not performers:
            warnings.append(
                _("Performer not found for procedure {code}").format(
                    code=procedures[0].get("code", "unknown")
                )
            )

        self._logger.info(
            "procedures_enriched",
            enriched_count=len(enriched),
            diagnosis_count=len(diagnosis_codes),
            performer_count=len(performers),
            warning_count=len(warnings),
            tenant_id=ctx.tenant_id,
        )

        return {
            "enriched_procedures": enriched,
            "diagnosis_codes": diagnosis_codes,
            "enrichment_warnings": warnings,
        }
