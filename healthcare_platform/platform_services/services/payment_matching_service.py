"""Payment matching service for platform services."""
from typing import Any, Dict

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability import get_logger

logger = get_logger(__name__)


class PaymentMatchingService:
    """Service for payment matching operations."""

    def __init__(self) -> None:
        """Initialize the payment matching service."""
        self.dmn_service = FederatedDMNService()

    def match_payment(
        self,
        tenant_id: str,
        payment_data: Dict[str, Any],
        match_strategy: str,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Match payment using specified strategy.

        Args:
            tenant_id: Tenant identifier
            payment_data: Payment data to match
            match_strategy: Matching strategy (invoice|patient|protocol)
            correlation_id: Correlation ID for tracing

        Returns:
            Dict containing match results
        """
        try:
            logger.info(
                "Matching payment",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "match_strategy": match_strategy,
                },
            )

            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category="platform_services",
                table_name=f"analytics/payment_match_{match_strategy}",
                inputs={
                    "payment_data": payment_data,
                    "strategy": match_strategy,
                    "correlation_id": correlation_id,
                },
            )

            logger.info(
                "Payment matched successfully",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "matched": result.get("matched", False),
                },
            )

            return result

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "Payment matching failed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                },
            )
            return {
                "matched": False,
                "confidence": 0.0,
                "match_type": None,
                "error": str(e),
            }

    def validate_match(
        self,
        tenant_id: str,
        match_result: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Validate payment match result.

        Args:
            tenant_id: Tenant identifier
            match_result: Match result to validate
            correlation_id: Correlation ID for tracing

        Returns:
            Dict containing validation results
        """
        try:
            logger.info(
                "Validating payment match",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                },
            )

            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category="platform_services",
                table_name="analytics/payment_match_validation",
                inputs={
                    "match_result": match_result,
                    "correlation_id": correlation_id,
                },
            )

            logger.info(
                "Match validation completed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "is_valid": result.get("is_valid", False),
                },
            )

            return result

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "Match validation failed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                },
            )
            return {
                "is_valid": False,
                "validation_errors": [str(e)],
                "requires_manual_review": True,
            }
