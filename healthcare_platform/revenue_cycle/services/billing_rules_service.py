"""Billing rules service for aggregated DMN-based billing decisions."""
from typing import Any, Dict, List
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class BillingRulesService:
    """Service that aggregates multiple billing DMN calls."""

    def __init__(self):
        """Initialize the billing rules service."""
        self.dmn_service = FederatedDMNService()
        logger.info("BillingRulesService initialized")

    def validate_claim_rules(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate claim against quantity, modifier, and upcode rules.

        Args:
            tenant_id: Tenant identifier
            claim_data: Claim data containing procedures and quantities

        Returns:
            Dict with validation results including quantity checks, modifier validation, and upcode detection
        """
        logger.info(f"Validating claim rules for tenant {tenant_id}")
        results = {
            "valid": True,
            "quantity_validation": {},
            "modifier_validation": {},
            "upcode_detection": {},
            "errors": [],
        }

        try:
            # Evaluate bill_quantity DMN tables
            quantity_result = self._evaluate_quantity_rules(tenant_id, claim_data)
            results["quantity_validation"] = quantity_result

            # Evaluate bill_modifier DMN tables
            modifier_result = self._evaluate_modifier_rules(tenant_id, claim_data)
            results["modifier_validation"] = modifier_result

            # Evaluate bill_upcode DMN tables
            upcode_result = self._evaluate_upcode_rules(tenant_id, claim_data)
            results["upcode_detection"] = upcode_result

            # Determine overall validity
            results["valid"] = (
                quantity_result.get("valid", True)
                and modifier_result.get("valid", True)
                and not upcode_result.get("detected", False)
            )

        except Exception as e:
            logger.error(f"Error validating claim rules: {e}")
            results["valid"] = False
            results["errors"].append(str(e))

        return results

    def check_bundle_rules(
        self, tenant_id: str, procedures: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Check bundle rules for multiple procedures.

        Args:
            tenant_id: Tenant identifier
            procedures: List of procedures to check for bundling

        Returns:
            Dict with bundle analysis results
        """
        logger.info(f"Checking bundle rules for tenant {tenant_id}")
        results = {
            "bundled": False,
            "bundle_code": None,
            "bundle_price": None,
            "savings": 0.0,
            "errors": [],
        }

        try:
            # Evaluate bill_bundle DMN tables
            for table_name in self._get_bundle_table_names():
                context = {
                    "tenant_id": tenant_id,
                    "procedures": procedures,
                    "procedure_codes": [p.get("code") for p in procedures],
                }
                result = self.dmn_service.evaluate_table(
                    tenant_id, "billing", f"bundle/{table_name}", context
                )
                if result and result.get("bundled"):
                    results.update(result)
                    break

        except Exception as e:
            logger.error(f"Error checking bundle rules: {e}")
            results["errors"].append(str(e))

        return results

    def validate_material_rules(
        self, tenant_id: str, materials: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate material and OPME rules.

        Args:
            tenant_id: Tenant identifier
            materials: List of materials to validate

        Returns:
            Dict with material validation results
        """
        logger.info(f"Validating material rules for tenant {tenant_id}")
        results = {
            "valid": True,
            "material_validation": {},
            "opme_validation": {},
            "errors": [],
        }

        try:
            # Evaluate bill_material DMN tables
            material_result = self._evaluate_material_rules(tenant_id, materials)
            results["material_validation"] = material_result

            # Evaluate bill_opme DMN tables
            opme_result = self._evaluate_opme_rules(tenant_id, materials)
            results["opme_validation"] = opme_result

            results["valid"] = material_result.get("valid", True) and opme_result.get(
                "valid", True
            )

        except Exception as e:
            logger.error(f"Error validating material rules: {e}")
            results["valid"] = False
            results["errors"].append(str(e))

        return results

    def calculate_taxa(
        self, tenant_id: str, billing_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate taxa (fees/taxes) based on billing data.

        Args:
            tenant_id: Tenant identifier
            billing_data: Billing data containing amounts and categories

        Returns:
            Dict with calculated taxa
        """
        logger.info(f"Calculating taxa for tenant {tenant_id}")
        results = {"total_taxa": 0.0, "taxa_breakdown": [], "errors": []}

        try:
            # Evaluate bill_taxa DMN tables
            for table_name in self._get_taxa_table_names():
                context = {"tenant_id": tenant_id, **billing_data}
                result = self.dmn_service.evaluate_table(
                    tenant_id, "billing", f"taxa/{table_name}", context
                )
                if result and result.get("taxa_amount"):
                    results["taxa_breakdown"].append(result)
                    results["total_taxa"] += result.get("taxa_amount", 0.0)

        except Exception as e:
            logger.error(f"Error calculating taxa: {e}")
            results["errors"].append(str(e))

        return results

    def _evaluate_quantity_rules(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate quantity validation rules."""
        try:
            context = {"tenant_id": tenant_id, **claim_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "billing", "quantity/bill_quantity_001", context
            )
            return result or {"valid": True}
        except Exception as e:
            logger.error(f"Error evaluating quantity rules: {e}")
            return {"valid": False, "error": str(e)}

    def _evaluate_modifier_rules(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate modifier validation rules."""
        try:
            context = {"tenant_id": tenant_id, **claim_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "billing", "modifier/bill_modifier_001", context
            )
            return result or {"valid": True}
        except Exception as e:
            logger.error(f"Error evaluating modifier rules: {e}")
            return {"valid": False, "error": str(e)}

    def _evaluate_upcode_rules(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate upcode detection rules."""
        try:
            context = {"tenant_id": tenant_id, **claim_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "billing", "upcode/bill_upcode_001", context
            )
            return result or {"detected": False}
        except Exception as e:
            logger.error(f"Error evaluating upcode rules: {e}")
            return {"detected": False, "error": str(e)}

    def _evaluate_material_rules(
        self, tenant_id: str, materials: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Evaluate material validation rules."""
        try:
            context = {"tenant_id": tenant_id, "materials": materials}
            result = self.dmn_service.evaluate_table(
                tenant_id, "billing", "material/bill_material_001", context
            )
            return result or {"valid": True}
        except Exception as e:
            logger.error(f"Error evaluating material rules: {e}")
            return {"valid": False, "error": str(e)}

    def _evaluate_opme_rules(
        self, tenant_id: str, materials: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Evaluate OPME validation rules."""
        try:
            context = {"tenant_id": tenant_id, "materials": materials}
            result = self.dmn_service.evaluate_table(
                tenant_id, "billing", "opme/bill_opme_001", context
            )
            return result or {"valid": True}
        except Exception as e:
            logger.error(f"Error evaluating OPME rules: {e}")
            return {"valid": False, "error": str(e)}

    def _get_bundle_table_names(self) -> List[str]:
        """Get list of bundle DMN table names."""
        return ["bill_bundle_001"]

    def _get_taxa_table_names(self) -> List[str]:
        """Get list of taxa DMN table names."""
        return ["bill_taxa_001"]
