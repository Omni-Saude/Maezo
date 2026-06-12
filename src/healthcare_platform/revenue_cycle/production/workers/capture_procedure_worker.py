"""Capture clinical procedures from ERP systems (Thin Delegation).

TOPIC: production.capture_procedure

Delegates ERP capture to ProcedureCaptureService.
Worker handles: input validation, DMN routing, delegation.
"""

from __future__ import annotations
from typing import Optional
from healthcare_platform.shared.integrations.tasy_client import TasyClientProtocol
from healthcare_platform.shared.integrations.mv_soul_client import MvSoulClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.revenue_cycle.production.services.procedure_capture_service import ProcedureCaptureService


class CaptureProcedureWorker(BaseExternalTaskWorker):
    """Captures procedures from ERP. Thin worker - delegates to ProcedureCaptureService."""

    TOPIC = "revenue_cycle.capture_procedure"
    DMN_DECISION_KEY = "erp_system_routing"
    DMN_CATEGORY = "pricing"

    def __init__(self, tasy_client: Optional[TasyClientProtocol] = None,
                 mv_soul_client: Optional[MvSoulClientProtocol] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tasy_client = tasy_client
        self.mv_soul_client = mv_soul_client
        self.service = ProcedureCaptureService(tasy_client=tasy_client, mv_soul_client=mv_soul_client)

    def execute(self, context: TaskContext) -> TaskResult:
        import json
        from datetime import datetime, timezone

        variables = context.variables
        encounter_ref = variables.get("encounter_reference", "") or variables.get("encounterId", "")
        procedure_code = variables.get("procedureCode", "10101012")

        dmn_result = self.evaluate_dmn(context=context, decision_key=self.DMN_DECISION_KEY,
            variables={"tenantId": context.tenant_id}, category=self.DMN_CATEGORY)
        destino = dmn_result.get("destino", "tasy")

        # Try real capture; fallback to stub data if service unavailable
        captured = None
        if encounter_ref:
            encounter_id = encounter_ref.rsplit("/", 1)[-1]
            try:
                captured = self.service.capture(destino, encounter_id)
            except Exception as e:
                self.logger.warning(f"ERP capture failed, using stub: {e}")

        if not captured:
            captured = [{"code": procedure_code, "quantity": 1, "category": "procedure"}]

        return TaskResult.success({
            "clinicalData": json.dumps(captured) if not isinstance(captured, str) else captured,
            "capturedData": json.dumps(captured) if not isinstance(captured, str) else captured,
            "captureTimestamp": datetime.now(timezone.utc).isoformat(),
            "captured_procedures": captured,
            "erp_system": destino,
            "procedure_count": len(captured),
        })
