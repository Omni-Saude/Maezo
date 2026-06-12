"""Appeal strategy service for aggregated DMN-based revenue recovery decisions."""
from typing import Any, Dict
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class AppealStrategyService:
    """Service that aggregates revenue_recovery DMN calls."""

    def __init__(self):
        """Initialize the appeal strategy service."""
        self.dmn_service = FederatedDMNService()
        logger.info("AppealStrategyService initialized")

    def check_appeal_eligibility(
        self, tenant_id: str, glosa_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if a denial/glosa is eligible for appeal.

        Args:
            tenant_id: Tenant identifier
            glosa_data: Glosa/denial data for eligibility check

        Returns:
            Dict with eligibility assessment
        """
        logger.info(f"Checking appeal eligibility for tenant {tenant_id}")
        results = {
            "eligible": False,
            "eligibility_score": 0.0,
            "reasons": [],
            "deadline": None,
            "errors": [],
        }

        try:
            context = {"tenant_id": tenant_id, **glosa_data}

            # Evaluate appeal_elig DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "revenue_recovery", "elig/appeal_elig_001", context
            )

            if result:
                results["eligible"] = result.get("eligible", False)
                results["eligibility_score"] = result.get("score", 0.0)
                results["reasons"] = result.get("reasons", [])
                results["deadline"] = result.get("deadline")

        except Exception as e:
            logger.error(f"Error checking appeal eligibility: {e}")
            results["errors"].append(str(e))

        return results

    def determine_strategy(
        self, tenant_id: str, glosa_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Determine optimal appeal strategy.

        Args:
            tenant_id: Tenant identifier
            glosa_data: Glosa/denial data for strategy determination

        Returns:
            Dict with recommended appeal strategy
        """
        logger.info(f"Determining appeal strategy for tenant {tenant_id}")
        results = {
            "strategy": None,
            "approach": None,
            "recommended_actions": [],
            "success_probability": 0.0,
            "estimated_duration_days": 0,
            "errors": [],
        }

        try:
            context = {"tenant_id": tenant_id, **glosa_data}

            # Evaluate appeal_strategy DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "revenue_recovery", "strategy/appeal_strategy_001", context
            )

            if result:
                results["strategy"] = result.get("strategy")
                results["approach"] = result.get("approach")
                results["recommended_actions"] = result.get("actions", [])
                results["success_probability"] = result.get("success_prob", 0.0)
                results["estimated_duration_days"] = result.get("duration_days", 0)

        except Exception as e:
            logger.error(f"Error determining appeal strategy: {e}")
            results["errors"].append(str(e))

        return results

    def estimate_recovery(
        self, tenant_id: str, glosa_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Estimate potential recovery from appeal.

        Args:
            tenant_id: Tenant identifier
            glosa_data: Glosa/denial data for recovery estimation

        Returns:
            Dict with recovery estimates and KPIs
        """
        logger.info(f"Estimating recovery for tenant {tenant_id}")
        results = {
            "estimated_recovery": 0.0,
            "recovery_probability": 0.0,
            "expected_value": 0.0,
            "kpis": {},
            "provision": {},
            "errors": [],
        }

        try:
            # Calculate KPIs
            kpi_result = self._evaluate_kpis(tenant_id, glosa_data)
            results["kpis"] = kpi_result

            # Calculate provision
            provision_result = self._evaluate_provision(tenant_id, glosa_data)
            results["provision"] = provision_result

            # Extract recovery estimates
            results["estimated_recovery"] = provision_result.get(
                "estimated_recovery", 0.0
            )
            results["recovery_probability"] = kpi_result.get("recovery_rate", 0.0)
            results["expected_value"] = (
                results["estimated_recovery"] * results["recovery_probability"]
            )

        except Exception as e:
            logger.error(f"Error estimating recovery: {e}")
            results["errors"].append(str(e))

        return results

    def _evaluate_kpis(
        self, tenant_id: str, glosa_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate KPI metrics for appeal."""
        try:
            context = {"tenant_id": tenant_id, **glosa_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "revenue_recovery", "kpi/kpi_001", context
            )
            return result or {}
        except Exception as e:
            logger.error(f"Error evaluating KPIs: {e}")
            return {"error": str(e)}

    def _evaluate_provision(
        self, tenant_id: str, glosa_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate provision calculations."""
        try:
            context = {"tenant_id": tenant_id, **glosa_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "revenue_recovery", "provision/provision_001", context
            )
            return result or {}
        except Exception as e:
            logger.error(f"Error evaluating provision: {e}")
            return {"error": str(e)}
