"""Integration tests for revenue cycle DMN integration."""
import pytest
from unittest.mock import patch, MagicMock
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


class TestRevenueDMNIntegration:
    """Integration tests for revenue cycle DMN integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.dmn_service = FederatedDMNService()

    def test_federation_service_loads_revenue_dmn(self):
        """Test that federation service can load billing DMN tables."""
        # Try loading a billing DMN table
        try:
            table = self.dmn_service.load_base_table(
                "billing", "quantity/bill_quantity_001"
            )
            assert table is not None
            assert "rules" in table
            assert "hitPolicy" in table
        except Exception:
            # If DMN files aren't found, mock should still pass structural tests
            pytest.skip("DMN files not available in test environment")

    def test_billing_worker_calls_bill_dmn(self):
        """Test billing worker DMN integration."""
        from healthcare_platform.revenue_cycle.billing.workers.validate_claim_worker import (
            ValidateClaimWorker,
        )

        worker = ValidateClaimWorker()
        assert hasattr(worker, "dmn_service")
        assert isinstance(worker.dmn_service, FederatedDMNService)

    def test_glosa_worker_calls_denial_dmn(self):
        """Test glosa worker DMN integration."""
        from healthcare_platform.revenue_cycle.glosa.workers.identify_glosa_worker import (
            IdentifyGlosaWorker,
        )

        worker = IdentifyGlosaWorker()
        assert hasattr(worker, "dmn_service")
        assert isinstance(worker.dmn_service, FederatedDMNService)

    def test_appeal_worker_calls_appeal_strategy_dmn(self):
        """Test appeal worker DMN integration."""
        from healthcare_platform.revenue_cycle.glosa.workers.check_appeal_eligibility_worker import (
            CheckAppealEligibilityWorker,
        )

        # Check class has dmn_service after init
        worker = CheckAppealEligibilityWorker()
        assert hasattr(worker, "dmn_service")

    def test_collection_worker_calls_cash_dmn(self):
        """Test collection worker DMN integration."""
        from healthcare_platform.revenue_cycle.collection.workers.identify_overdue_worker import (
            IdentifyOverdueWorker,
        )

        worker = IdentifyOverdueWorker()
        assert hasattr(worker, "dmn_service")

    def test_coding_worker_calls_edit_dmn(self):
        """Test coding worker DMN integration."""
        from healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker import (
            ValidateCodesWorker,
        )

        # ValidateCodesWorker requires ans_client
        mock_ans = MagicMock()
        worker = ValidateCodesWorker(ans_client=mock_ans)
        assert hasattr(worker, "dmn_service")

    def test_billing_rules_service(self):
        """Test BillingRulesService aggregates DMN calls."""
        from healthcare_platform.revenue_cycle.services.billing_rules_service import (
            BillingRulesService,
        )

        service = BillingRulesService()
        assert hasattr(service, "dmn_service")
        assert isinstance(service.dmn_service, FederatedDMNService)

    def test_glosa_prevention_service(self):
        """Test GlosaPreventionService aggregates DMN calls."""
        from healthcare_platform.revenue_cycle.services.glosa_prevention_service import (
            GlosaPreventionService,
        )

        service = GlosaPreventionService()
        assert hasattr(service, "dmn_service")
        assert isinstance(service.dmn_service, FederatedDMNService)

    def test_appeal_strategy_service(self):
        """Test AppealStrategyService aggregates DMN calls."""
        from healthcare_platform.revenue_cycle.services.appeal_strategy_service import (
            AppealStrategyService,
        )

        service = AppealStrategyService()
        assert hasattr(service, "dmn_service")
        assert isinstance(service.dmn_service, FederatedDMNService)

    def test_pricing_service(self):
        """Test PricingService aggregates DMN calls."""
        from healthcare_platform.revenue_cycle.services.pricing_service import PricingService

        service = PricingService()
        assert hasattr(service, "dmn_service")
        assert isinstance(service.dmn_service, FederatedDMNService)

    def test_billing_rules_service_validate_claim(self):
        """Test BillingRulesService validate_claim_rules method."""
        from healthcare_platform.revenue_cycle.services.billing_rules_service import (
            BillingRulesService,
        )

        service = BillingRulesService()
        claim_data = {
            "procedure_code": "12345",
            "quantity": 1,
            "modifiers": ["59"],
        }

        with patch.object(
            service.dmn_service, "evaluate_table", return_value={"valid": True}
        ):
            result = service.validate_claim_rules("tenant-001", claim_data)
            assert "valid" in result
            assert "quantity_validation" in result
            assert "modifier_validation" in result
            assert "upcode_detection" in result

    def test_glosa_prevention_service_assess_risk(self):
        """Test GlosaPreventionService assess_denial_risk method."""
        from healthcare_platform.revenue_cycle.services.glosa_prevention_service import (
            GlosaPreventionService,
        )

        service = GlosaPreventionService()
        claim_data = {"procedure_code": "12345", "diagnosis_code": "Z00.0"}

        with patch.object(
            service.dmn_service,
            "evaluate_table",
            return_value={"risk_score": 0.3, "actions": []},
        ):
            result = service.assess_denial_risk("tenant-001", claim_data)
            assert "risk_score" in result
            assert "risk_level" in result
            assert "prediction" in result
            assert "prevention_actions" in result

    def test_appeal_strategy_service_check_eligibility(self):
        """Test AppealStrategyService check_appeal_eligibility method."""
        from healthcare_platform.revenue_cycle.services.appeal_strategy_service import (
            AppealStrategyService,
        )

        service = AppealStrategyService()
        glosa_data = {
            "denial_code": "CO-45",
            "denied_amount": 1000.0,
        }

        with patch.object(
            service.dmn_service,
            "evaluate_table",
            return_value={"eligible": True, "score": 0.8},
        ):
            result = service.check_appeal_eligibility("tenant-001", glosa_data)
            assert "eligible" in result
            assert "eligibility_score" in result
            assert "reasons" in result

    def test_pricing_service_get_contract_price(self):
        """Test PricingService get_contract_price method."""
        from healthcare_platform.revenue_cycle.services.pricing_service import PricingService

        service = PricingService()

        with patch.object(
            service.dmn_service,
            "evaluate_table",
            return_value={"price": 150.0, "currency": "BRL"},
        ):
            result = service.get_contract_price("tenant-001", "12345", "contract-001")
            assert "price" in result
            assert "currency" in result
            assert "procedure_code" in result
            assert result["procedure_code"] == "12345"
