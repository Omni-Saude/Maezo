"""Reconciliation service for platform services."""
from typing import Any, Dict, List

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability import get_logger

logger = get_logger(__name__)


class ReconciliationService:
    """Service for data reconciliation and archival operations."""

    def __init__(self) -> None:
        """Initialize the reconciliation service."""
        self.dmn_service = FederatedDMNService()

    def reconcile_sources(
        self,
        tenant_id: str,
        sources: List[str],
        period: str,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Reconcile data from multiple sources.

        Args:
            tenant_id: Tenant identifier
            sources: List of data sources to reconcile
            period: Time period for reconciliation
            correlation_id: Correlation ID for tracing

        Returns:
            Dict containing reconciliation results
        """
        try:
            logger.info(
                "Reconciling data sources",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "sources": sources,
                    "period": period,
                },
            )

            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category="platform_services",
                table_name="analytics/data_reconciliation",
                inputs={
                    "sources": sources,
                    "period": period,
                    "correlation_id": correlation_id,
                },
            )

            logger.info(
                "Data reconciliation completed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "discrepancies_found": result.get("discrepancies_count", 0),
                },
            )

            return result

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "Data reconciliation failed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                },
            )
            return {
                "reconciled": False,
                "discrepancies_count": 0,
                "discrepancies": [],
                "error": str(e),
            }

    def validate_archive(
        self,
        tenant_id: str,
        archive_params: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Validate archive parameters before archival.

        Args:
            tenant_id: Tenant identifier
            archive_params: Archive parameters to validate
            correlation_id: Correlation ID for tracing

        Returns:
            Dict containing validation results
        """
        try:
            logger.info(
                "Validating archive parameters",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                },
            )

            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category="platform_services",
                table_name="analytics/archive_validation",
                inputs={
                    "archive_params": archive_params,
                    "correlation_id": correlation_id,
                },
            )

            logger.info(
                "Archive validation completed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "is_valid": result.get("is_valid", False),
                },
            )

            return result

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "Archive validation failed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                },
            )
            return {
                "is_valid": False,
                "validation_errors": [str(e)],
                "can_proceed": False,
            }
