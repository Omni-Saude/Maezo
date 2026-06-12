"""Payment reporting service for platform services."""
from typing import Any, Dict

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability import get_logger

logger = get_logger(__name__)


class PaymentReportingService:
    """Service for payment reporting and dashboard generation."""

    def __init__(self) -> None:
        """Initialize the payment reporting service."""
        self.dmn_service = FederatedDMNService()

    def generate_report(
        self,
        tenant_id: str,
        report_type: str,
        period: str,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Generate payment report.

        Args:
            tenant_id: Tenant identifier
            report_type: Type of report to generate
            period: Time period for report
            correlation_id: Correlation ID for tracing

        Returns:
            Dict containing report data
        """
        try:
            logger.info(
                "Generating payment report",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "report_type": report_type,
                    "period": period,
                },
            )

            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category="platform_services",
                table_name="analytics/payment_report",
                inputs={
                    "report_type": report_type,
                    "period": period,
                    "correlation_id": correlation_id,
                },
            )

            logger.info(
                "Report generated successfully",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "report_sections": len(result.get("sections", [])),
                },
            )

            return result

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "Report generation failed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                },
            )
            return {
                "report_type": report_type,
                "sections": [],
                "generated": False,
                "error": str(e),
            }

    def compile_dashboard(
        self,
        tenant_id: str,
        dashboard_config: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Compile executive dashboard.

        Args:
            tenant_id: Tenant identifier
            dashboard_config: Dashboard configuration
            correlation_id: Correlation ID for tracing

        Returns:
            Dict containing dashboard data
        """
        try:
            logger.info(
                "Compiling executive dashboard",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                },
            )

            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category="platform_services",
                table_name="analytics/executive_dashboard",
                inputs={
                    "dashboard_config": dashboard_config,
                    "correlation_id": correlation_id,
                },
            )

            logger.info(
                "Dashboard compiled successfully",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "widgets_count": len(result.get("widgets", [])),
                },
            )

            return result

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "Dashboard compilation failed",
                extra={
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                },
            )
            return {
                "widgets": [],
                "compiled": False,
                "error": str(e),
            }
