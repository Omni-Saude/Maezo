"""Pricing service for aggregated DMN-based pricing decisions."""
from typing import Any, Dict, List
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class PricingService:
    """Service that aggregates pricing DMN calls."""

    def __init__(self):
        """Initialize the pricing service."""
        self.dmn_service = FederatedDMNService()
        logger.info("PricingService initialized")

    def get_contract_price(
        self, tenant_id: str, procedure_code: str, contract_id: str
    ) -> Dict[str, Any]:
        """
        Get contract-specific price for a procedure.

        Args:
            tenant_id: Tenant identifier
            procedure_code: Procedure code to price
            contract_id: Contract identifier

        Returns:
            Dict with contract pricing information
        """
        logger.info(
            f"Getting contract price for tenant {tenant_id}: {procedure_code} in contract {contract_id}"
        )
        results = {
            "procedure_code": procedure_code,
            "contract_id": contract_id,
            "price": None,
            "currency": "BRL",
            "modifiers": [],
            "valid_from": None,
            "valid_to": None,
            "errors": [],
        }

        try:
            context = {
                "tenant_id": tenant_id,
                "procedure_code": procedure_code,
                "contract_id": contract_id,
            }

            # Evaluate contract DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "pricing", "contract/contract_001", context
            )

            if result:
                results["price"] = result.get("price")
                results["currency"] = result.get("currency", "BRL")
                results["modifiers"] = result.get("modifiers", [])
                results["valid_from"] = result.get("valid_from")
                results["valid_to"] = result.get("valid_to")

        except Exception as e:
            logger.error(f"Error getting contract price: {e}")
            results["errors"].append(str(e))

        return results

    def check_package_pricing(
        self, tenant_id: str, procedures: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Check if procedures qualify for package pricing.

        Args:
            tenant_id: Tenant identifier
            procedures: List of procedures to check

        Returns:
            Dict with package pricing analysis
        """
        logger.info(f"Checking package pricing for tenant {tenant_id}")
        results = {
            "has_package": False,
            "package_id": None,
            "package_price": None,
            "individual_total": 0.0,
            "savings": 0.0,
            "savings_percent": 0.0,
            "errors": [],
        }

        try:
            context = {
                "tenant_id": tenant_id,
                "procedures": procedures,
                "procedure_codes": [p.get("code") for p in procedures],
            }

            # Evaluate package DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "pricing", "package/package_001", context
            )

            if result:
                results["has_package"] = result.get("has_package", False)
                results["package_id"] = result.get("package_id")
                results["package_price"] = result.get("package_price")
                results["individual_total"] = result.get("individual_total", 0.0)

                if results["has_package"] and results["package_price"]:
                    results["savings"] = (
                        results["individual_total"] - results["package_price"]
                    )
                    if results["individual_total"] > 0:
                        results["savings_percent"] = (
                            results["savings"] / results["individual_total"]
                        ) * 100

        except Exception as e:
            logger.error(f"Error checking package pricing: {e}")
            results["errors"].append(str(e))

        return results

    def detect_outlier_pricing(
        self, tenant_id: str, procedure: str, amount: float
    ) -> Dict[str, Any]:
        """
        Detect if pricing is an outlier compared to norms.

        Args:
            tenant_id: Tenant identifier
            procedure: Procedure code
            amount: Billed amount to check

        Returns:
            Dict with outlier analysis
        """
        logger.info(
            f"Detecting outlier pricing for tenant {tenant_id}: {procedure} at {amount}"
        )
        results = {
            "is_outlier": False,
            "outlier_score": 0.0,
            "expected_range": {},
            "variance": 0.0,
            "variance_percent": 0.0,
            "severity": "NORMAL",
            "errors": [],
        }

        try:
            context = {
                "tenant_id": tenant_id,
                "procedure_code": procedure,
                "amount": amount,
            }

            # Evaluate outlier DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "pricing", "outlier/outlier_001", context
            )

            if result:
                results["is_outlier"] = result.get("is_outlier", False)
                results["outlier_score"] = result.get("score", 0.0)
                results["expected_range"] = result.get("expected_range", {})
                results["variance"] = result.get("variance", 0.0)
                results["variance_percent"] = result.get("variance_percent", 0.0)

                # Determine severity
                if results["outlier_score"] >= 0.8:
                    results["severity"] = "CRITICAL"
                elif results["outlier_score"] >= 0.6:
                    results["severity"] = "HIGH"
                elif results["outlier_score"] >= 0.4:
                    results["severity"] = "MODERATE"

        except Exception as e:
            logger.error(f"Error detecting outlier pricing: {e}")
            results["errors"].append(str(e))

        return results
