"""Tests for CheckAuthorizationRequirementsWorker."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker():
    from healthcare_platform.patient_access.workers.check_authorization_requirements_worker import (
        CheckAuthorizationRequirementsWorker,
        StubAuthorizationRequirementChecker,
    )

    return CheckAuthorizationRequirementsWorker(checker=StubAuthorizationRequirementChecker())


@pytest.mark.unit
class TestCheckAuthorizationRequirementsWorker:
    @pytest.mark.asyncio
    async def test_happy_path_no_authorization_required(self, worker, tenant_austa):
        """Test procedure that doesn't require authorization."""
        # Arrange
        task_vars = {
            "procedure_code": "10101010",  # Simple procedure
            "service_type": "consulta",
            "operator_code": "123456",
            "plan_code": "PLAN-001",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["requires_authorization"] is False
        assert result["authorization_type"] == "none"
        assert len(result["authorization_criteria"]) == 0

    @pytest.mark.asyncio
    async def test_happy_path_authorization_required(self, worker, tenant_austa):
        """Test high-complexity procedure requiring authorization."""
        # Arrange
        task_vars = {
            "procedure_code": "40101010",  # Cardiac surgery (high complexity)
            "service_type": "cirurgia",
            "operator_code": "123456",
            "plan_code": "PLAN-001",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["requires_authorization"] is True
        assert result["authorization_type"] == "prior"
        assert len(result["authorization_criteria"]) > 0
        assert result["estimated_approval_time"] is not None

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"procedure_code": "40101010"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "procedure_code": "40101010",
                    "service_type": "cirurgia",
                    "operator_code": "123456",
                    "plan_code": "PLAN-001",
                }
            )

    @pytest.mark.asyncio
    async def test_authorization_criteria_provided(self, worker, tenant_austa):
        """Test that authorization criteria are returned for complex procedures."""
        result = await worker.execute(
            {
                "procedure_code": "40101010",  # Requires authorization
                "service_type": "cirurgia",
                "operator_code": "123456",
                "plan_code": "PLAN-001",
            }
        )

        # Should have criteria
        assert len(result["authorization_criteria"]) >= 3
        criteria_text = " ".join(result["authorization_criteria"])
        assert "Laudo médico" in criteria_text or "laudo" in criteria_text.lower()

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "procedure_code": "40101010",
                "service_type": "cirurgia",
                "operator_code": "123456",
                "plan_code": "PLAN-AUSTA",
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "procedure_code": "40101010",
                "service_type": "cirurgia",
                "operator_code": "123456",
                "plan_code": "PLAN-HPA",
            }
        )

        # Authorization rules should be consistent
        assert result_austa["requires_authorization"] == result_hpa["requires_authorization"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        task_vars = {
            "procedure_code": "40101010",
            "service_type": "cirurgia",
            "operator_code": "123456",
            "plan_code": "PLAN-001",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be identical
        assert result1["requires_authorization"] == result2["requires_authorization"]
        assert result1["authorization_type"] == result2["authorization_type"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.check_authorization_requirements_worker import (
            PatientAccessException,
        )

        # Mock failure
        worker.checker.check_ans_rules = AsyncMock(side_effect=Exception("ANS service down"))

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "procedure_code": "40101010",
                    "service_type": "cirurgia",
                    "operator_code": "123456",
                    "plan_code": "PLAN-001",
                }
            )

    @pytest.mark.asyncio
    async def test_operator_specific_rules(self, worker, tenant_austa):
        """Test operator-specific authorization rules."""
        # Mock operator requiring authorization
        worker.checker.check_operator_rules = AsyncMock(
            return_value={
                "operator_requires_auth": True,
                "operator_rule": "Operator requires pre-auth for all procedures",
                "estimated_approval_time": "48h",
            }
        )

        result = await worker.execute(
            {
                "procedure_code": "10101010",  # Normally doesn't require auth
                "service_type": "consulta",
                "operator_code": "strict-operator",
                "plan_code": "PLAN-001",
            }
        )

        # Should require auth due to operator rules
        assert result["requires_authorization"] is True

    @pytest.mark.asyncio
    async def test_multiple_high_complexity_procedures(self, worker, tenant_austa):
        """Test multiple high-complexity procedures."""
        procedures = ["40101010", "40201010", "40301010"]  # All high-complexity

        for proc_code in procedures:
            result = await worker.execute(
                {
                    "procedure_code": proc_code,
                    "service_type": "cirurgia",
                    "operator_code": "123456",
                    "plan_code": "PLAN-001",
                }
            )

            assert result["requires_authorization"] is True
            assert result["authorization_type"] == "prior"
