"""Capture clinical procedures from ERP systems (Tasy/MV Soul).

CIB7 External Task Topic: production.capture_procedure
BPMN Error Codes: EXTERNAL_SERVICE_ERROR, CODING_ERROR
"""
from __future__ import annotations

from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import CodingException, ExternalServiceException
from healthcare_platform.shared.domain.value_objects import FHIRReference
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.mv_soul_client import MvSoulClientProtocol
from healthcare_platform.shared.integrations.tasy_client import TasyClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

# Tenant-to-ERP mapping (ADR-004)
_TASY_TENANTS = {TenantCode.HOSPITAL_A}
_MV_SOUL_TENANTS = {TenantCode.AMH_SP, TenantCode.AMH_RJ, TenantCode.AMH_MG}


class CaptureProcedureWorker:
    """Captures procedures from hospital ERP via CDC/FHIR delegation.

    Routes to Tasy (AUSTA) or MV Soul (AMH units) based on tenant context.
    Per ADR-004: CDC only, no direct ERP queries.
    Per ADR-006: Snapshot queries via FHIR.

    Archetype: FINANCIAL_CALCULATION
    """

    TOPIC = "revenue_cycle.production.capture_procedure"

    def __init__(
        self,
        tasy_client: TasyClientProtocol,
        mv_soul_client: MvSoulClientProtocol,
    ) -> None:
        self._tasy = tasy_client
        self._mv_soul = mv_soul_client
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    def _evaluate_pricing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate pricing DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='pricing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @require_tenant
    @track_task_execution(metric_name="production_capture_procedure")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Capture procedures for an encounter from the tenant's ERP.

        Task Variables (input):
            encounter_reference: str - FHIR reference (e.g. "Encounter/123")

        Returns:
            captured_procedures: list[dict] - Captured procedure data
            erp_system: str - ERP system used (tasy | mv_soul)
            procedure_count: int - Number of procedures captured
        """
        ctx = get_required_tenant()
        encounter_ref_str: str = task_variables.get("encounter_reference", "")

        if not encounter_ref_str:
            raise CodingException(
                _("Invalid input: {field} - {reason}").format(
                    field="encounter_reference", reason="missing"
                ),
                bpmn_error_code="CODING_ERROR",
            )

        # Parse encounter ID from FHIR reference
        encounter_ref = FHIRReference(reference=encounter_ref_str, type="Encounter")
        encounter_id = encounter_ref_str.rsplit("/", 1)[-1]

        self._logger.info(
            "capturing_procedures",
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id,
            tenant_code=str(ctx.tenant_code),
        )

        # Route to appropriate ERP based on tenant
        captured: list[dict[str, Any]] = []
        erp_system: str

        try:
            if ctx.tenant_code in _TASY_TENANTS:
                erp_system = "tasy"
                procedures = await self._tasy.get_procedures(encounter_id)
                for proc in procedures:
                    captured.append({
                        "procedure_id": proc.procedure_id,
                        "encounter_id": proc.encounter_id,
                        "patient_reference": f"Patient/{proc.patient_id}",
                        "code": proc.code,
                        "display": proc.display,
                        "status": proc.status,
                        "performed_date": proc.performed_date.isoformat() if proc.performed_date else None,
                    })
            elif ctx.tenant_code in _MV_SOUL_TENANTS:
                erp_system = "mv_soul"
                billing_items = await self._mv_soul.get_billing_items(encounter_id)
                for item in billing_items:
                    captured.append({
                        "procedure_id": item.item_id,
                        "encounter_id": item.encounter_id,
                        "patient_reference": "",
                        "code": item.item_code,
                        "display": item.item_description,
                        "status": item.status,
                        "performed_date": item.service_date,
                    })
            else:
                raise CodingException(
                    _("Internal error in {worker_name}: {error}").format(
                        worker_name=self.TOPIC,
                        error=f"unknown tenant {ctx.tenant_code}",
                    ),
                    bpmn_error_code="CODING_ERROR",
                )
        except (CodingException, ExternalServiceException):
            raise
        except Exception as exc:
            self._logger.error(
                "capture_failed",
                encounter_id=encounter_id,
                error=str(exc),
                tenant_id=ctx.tenant_id,
            )
            raise ExternalServiceException(
                _("Failed to capture procedures from {erp_system}").format(
                    erp_system=erp_system if 'erp_system' in dir() else "unknown"
                ),
                service_name=erp_system if 'erp_system' in dir() else "unknown",
                operation="get_procedures",
            ) from exc

        if not captured:
            raise CodingException(
                _("No procedures found for encounter {encounter_id}").format(
                    encounter_id=encounter_id
                ),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "procedures_captured",
            procedure_count=len(captured),
            erp_system=erp_system,
            tenant_id=ctx.tenant_id,
        )

        return {
            "captured_procedures": captured,
            "erp_system": erp_system,
            "procedure_count": len(captured),
        }
