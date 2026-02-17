"""Handle payer acknowledgment worker."""
from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.enums import BillingStatus
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-handle-acknowledgment")
class HandleAcknowledgmentWorker(BaseWorker):
    """Worker to process ACK/NACK responses from payer.

    Archetype: FINANCIAL_CALCULATION
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        """Get human-readable operation name."""
        return _("Processar confirmação da operadora")

    def _evaluate_billing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate billing DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='billing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Process acknowledgment from payer.

        Input variables:
            - protocol_number: Protocol number of submission
            - claim_id: Claim identifier
            - acknowledgment_type: "ACK" or "NACK"
            - response_code: Response code from payer
            - response_message: Response message from payer
            - errors: Optional list of error descriptions

        Output variables:
            - acknowledged: Boolean indicating if acknowledged successfully
            - billing_status: New billing status
            - requires_resubmission: Boolean indicating if resubmission needed
            - rejection_reasons: List of rejection reasons (if NACK)

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with acknowledgment processing outcome
        """
        protocol_number = variables.get("protocol_number")
        claim_id = variables.get("claim_id")
        acknowledgment_type = variables.get("acknowledgment_type", "").upper()
        response_code = variables.get("response_code")
        response_message = variables.get("response_message", "")
        errors = variables.get("errors", [])

        # Validate required inputs
        if not protocol_number:
            return WorkerResult.bpmn_error(
                error_code="MISSING_PROTOCOL_NUMBER",
                error_message=_("Número de protocolo não fornecido")
            )

        if not claim_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_CLAIM_ID",
                error_message=_("Identificador da fatura não fornecido")
            )

        if acknowledgment_type not in ("ACK", "NACK"):
            return WorkerResult.bpmn_error(
                error_code="INVALID_ACKNOWLEDGMENT_TYPE",
                error_message=_("Tipo de confirmação inválido: {type}").format(type=acknowledgment_type)
            )

        self._logger.info(
            "Processing payer acknowledgment",
            claim_id=claim_id,
            protocol_number=protocol_number,
            acknowledgment_type=acknowledgment_type,
            response_code=response_code
        )

        # Process ACK
        if acknowledgment_type == "ACK":
            output = self._handle_ack(claim_id, protocol_number, response_code, response_message)
            self._logger.info(
                "Acknowledgment processed: ACK",
                claim_id=claim_id,
                protocol_number=protocol_number,
                billing_status=output["billing_status"]
            )
            return WorkerResult.ok(output)

        # Process NACK
        output = self._handle_nack(
            claim_id, protocol_number, response_code, response_message, errors
        )
        self._logger.warning(
            "Acknowledgment processed: NACK",
            claim_id=claim_id,
            protocol_number=protocol_number,
            requires_resubmission=output["requires_resubmission"],
            rejection_count=len(output["rejection_reasons"])
        )
        return WorkerResult.ok(output)

    def _handle_ack(
        self,
        claim_id: str,
        protocol_number: str,
        response_code: str,
        response_message: str
    ) -> dict[str, Any]:
        """
        Handle positive acknowledgment (ACK).

        Args:
            claim_id: Claim identifier
            protocol_number: Protocol number
            response_code: Response code
            response_message: Response message

        Returns:
            Output variables dictionary
        """
        return {
            "acknowledged": True,
            "billing_status": BillingStatus.ACKNOWLEDGED.value,
            "requires_resubmission": False,
            "rejection_reasons": []
        }

    def _handle_nack(
        self,
        claim_id: str,
        protocol_number: str,
        response_code: str,
        response_message: str,
        errors: list[str]
    ) -> dict[str, Any]:
        """
        Handle negative acknowledgment (NACK).

        Args:
            claim_id: Claim identifier
            protocol_number: Protocol number
            response_code: Response code
            response_message: Response message
            errors: List of error descriptions

        Returns:
            Output variables dictionary
        """
        # Collect rejection reasons
        rejection_reasons = []
        if response_message:
            rejection_reasons.append(response_message)
        if errors:
            rejection_reasons.extend(errors)

        # Determine if retryable based on response code
        # Common retryable codes: timeout, temporary unavailability, etc.
        retryable_codes = ["TIMEOUT", "SERVICE_UNAVAILABLE", "RATE_LIMIT"]
        requires_resubmission = response_code in retryable_codes

        # Determine billing status
        # If retryable, keep as SUBMITTED for retry
        # If permanent rejection, mark as DENIED
        if requires_resubmission:
            billing_status = BillingStatus.SUBMITTED.value
            self._logger.info(
                "NACK is retryable",
                claim_id=claim_id,
                response_code=response_code
            )
        else:
            billing_status = BillingStatus.DENIED.value
            self._logger.warning(
                "NACK is permanent rejection",
                claim_id=claim_id,
                response_code=response_code,
                rejection_reasons=rejection_reasons
            )

        return {
            "acknowledged": False,
            "billing_status": billing_status,
            "requires_resubmission": requires_resubmission,
            "rejection_reasons": rejection_reasons
        }
