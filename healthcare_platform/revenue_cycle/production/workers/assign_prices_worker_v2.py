"""Assign prices to procedures (Thin Delegation).

TOPIC: production.assign_prices

Delegates pricing logic to PricingAssignmentService.
Worker handles: input validation, delegation, error mapping.
"""

from __future__ import annotations
from typing import Optional
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.revenue_cycle.production.services.pricing_assignment_service import PricingAssignmentService


class AssignPricesWorker(BaseExternalTaskWorker):
    """Assigns prices to procedures. Thin worker - delegates to PricingAssignmentService."""

    TOPIC = "production.assign_prices"

    def __init__(self, fhir_client: Optional[FHIRClientProtocol] = None,
                 tasy_api_client: Optional[TasyApiClientProtocol] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fhir_client = fhir_client
        self.tasy_api_client = tasy_api_client
        self.service = PricingAssignmentService(fhir_client=fhir_client, tasy_api_client=tasy_api_client)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            procedures = variables.get("quantified_procedures", [])
            contract_id = variables.get("contract_id", "")
            price_table_id = variables.get("price_table_id", "tuss_default")

            if not procedures:
                return TaskResult.bpmn_error(error_code="BILLING_ERROR", error_message="No procedures to price")

            self.logger.info(f"Assigning prices: {len(procedures)} procedures",
                extra={"tenant_id": context.tenant_id, "contract_id": contract_id})

            result = self.service.assign_prices(procedures, contract_id, price_table_id)
            missing = result.pop("missing_codes", [])

            if missing:
                return TaskResult.bpmn_error(error_code="CONTRACT_RULE_VIOLATION",
                    error_message=f"Price not found for: {', '.join(missing)}",
                    variables={"missing_codes": missing})

            return TaskResult.success(result)
        except Exception as e:
            self.logger.error(f"Price assignment failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="BILLING_ERROR", error_message=str(e))
