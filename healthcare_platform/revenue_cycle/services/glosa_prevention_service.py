"""Glosa prevention service for aggregated DMN-based denial prevention."""
from typing import Any, Dict
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class GlosaPreventionService:
    """Service that aggregates glosa_prevention DMN calls."""

    def __init__(self):
        """Initialize the glosa prevention service."""
        self.dmn_service = FederatedDMNService()
        logger.info("GlosaPreventionService initialized")

    def assess_denial_risk(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Assess denial risk using prediction and prevention rules.

        Args:
            tenant_id: Tenant identifier
            claim_data: Claim data for risk assessment

        Returns:
            Dict with risk assessment results
        """
        logger.info(f"Assessing denial risk for tenant {tenant_id}")
        results = {
            "risk_score": 0.0,
            "risk_level": "LOW",
            "prediction": {},
            "prevention_actions": [],
            "errors": [],
        }

        try:
            # Evaluate deny_predict DMN tables
            prediction_result = self._evaluate_prediction_rules(tenant_id, claim_data)
            results["prediction"] = prediction_result
            results["risk_score"] = prediction_result.get("risk_score", 0.0)

            # Determine risk level
            if results["risk_score"] >= 0.7:
                results["risk_level"] = "HIGH"
            elif results["risk_score"] >= 0.4:
                results["risk_level"] = "MEDIUM"

            # Evaluate deny_prevent DMN tables for actions
            prevention_result = self._evaluate_prevention_rules(tenant_id, claim_data)
            results["prevention_actions"] = prevention_result.get("actions", [])

        except Exception as e:
            logger.error(f"Error assessing denial risk: {e}")
            results["errors"].append(str(e))

        return results

    def check_medical_necessity(
        self, tenant_id: str, procedure: str, diagnosis: str
    ) -> Dict[str, Any]:
        """
        Check medical necessity for procedure and diagnosis combination.

        Args:
            tenant_id: Tenant identifier
            procedure: Procedure code
            diagnosis: Diagnosis code

        Returns:
            Dict with medical necessity check results
        """
        logger.info(
            f"Checking medical necessity for tenant {tenant_id}: {procedure} with {diagnosis}"
        )
        results = {
            "medically_necessary": False,
            "justification": None,
            "alternative_codes": [],
            "errors": [],
        }

        try:
            context = {
                "tenant_id": tenant_id,
                "procedure_code": procedure,
                "diagnosis_code": diagnosis,
            }

            # Evaluate deny_medical DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "glosa_prevention", "medical/deny_medical_001", context
            )

            if result:
                results["medically_necessary"] = result.get("necessary", False)
                results["justification"] = result.get("justification")
                results["alternative_codes"] = result.get("alternatives", [])

        except Exception as e:
            logger.error(f"Error checking medical necessity: {e}")
            results["errors"].append(str(e))

        return results

    def check_duplicate_risk(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check for duplicate claim risk.

        Args:
            tenant_id: Tenant identifier
            claim_data: Claim data to check for duplicates

        Returns:
            Dict with duplicate risk assessment
        """
        logger.info(f"Checking duplicate risk for tenant {tenant_id}")
        results = {
            "is_duplicate": False,
            "duplicate_probability": 0.0,
            "matching_claims": [],
            "errors": [],
        }

        try:
            context = {"tenant_id": tenant_id, **claim_data}

            # Evaluate deny_duplicate DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "glosa_prevention", "duplicate/deny_duplicate_001", context
            )

            if result:
                results["is_duplicate"] = result.get("is_duplicate", False)
                results["duplicate_probability"] = result.get("probability", 0.0)
                results["matching_claims"] = result.get("matches", [])

        except Exception as e:
            logger.error(f"Error checking duplicate risk: {e}")
            results["errors"].append(str(e))

        return results

    def get_payer_rules(self, tenant_id: str, payer_id: str) -> Dict[str, Any]:
        """
        Get payer-specific rules for claim submission.

        Args:
            tenant_id: Tenant identifier
            payer_id: Payer identifier

        Returns:
            Dict with payer-specific rules
        """
        logger.info(f"Getting payer rules for tenant {tenant_id}, payer {payer_id}")
        results = {
            "payer_id": payer_id,
            "rules": {},
            "requirements": [],
            "deadline_days": 30,
            "errors": [],
        }

        try:
            context = {"tenant_id": tenant_id, "payer_id": payer_id}

            # Evaluate deny_payer DMN tables
            result = self.dmn_service.evaluate_table(
                tenant_id, "glosa_prevention", "payer/deny_payer_001", context
            )

            if result:
                results["rules"] = result.get("rules", {})
                results["requirements"] = result.get("requirements", [])
                results["deadline_days"] = result.get("deadline_days", 30)

        except Exception as e:
            logger.error(f"Error getting payer rules: {e}")
            results["errors"].append(str(e))

        return results

    def _evaluate_prediction_rules(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate denial prediction rules."""
        try:
            context = {"tenant_id": tenant_id, **claim_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "glosa_prevention", "predict/deny_predict_001", context
            )
            return result or {"risk_score": 0.0}
        except Exception as e:
            logger.error(f"Error evaluating prediction rules: {e}")
            return {"risk_score": 0.0, "error": str(e)}

    def _evaluate_prevention_rules(
        self, tenant_id: str, claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate denial prevention rules."""
        try:
            context = {"tenant_id": tenant_id, **claim_data}
            result = self.dmn_service.evaluate_table(
                tenant_id, "glosa_prevention", "prevent/deny_prevent_001", context
            )
            return result or {"actions": []}
        except Exception as e:
            logger.error(f"Error evaluating prevention rules: {e}")
            return {"actions": [], "error": str(e)}
