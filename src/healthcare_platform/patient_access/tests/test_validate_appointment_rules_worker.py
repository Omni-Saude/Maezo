"""Tests for ValidateAppointmentRulesWorker."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def rules_validator():
    """Mock rules validator protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, rules_validator):
    from healthcare_platform.patient_access.workers.validate_appointment_rules_worker import ValidateAppointmentRulesWorker
    return ValidateAppointmentRulesWorker(fhir_client=fhir_client, rules_validator=rules_validator)


class TestValidateAppointmentRulesWorker:
    @pytest.mark.asyncio
    async def test_happy_path_validates_rules(self, worker, fhir_client, rules_validator, tenant_hospital_a):
        """Test successful appointment rules validation."""
        rules_validator.validate.return_value = {
            "valid": True,
            "violations": []
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "service_type": "consultation",
            "start_time": "2024-01-15T10:00:00Z"
        })

        assert result["valid"] is True
        assert result["violations"] == []
        rules_validator.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_hospital_a):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_rule_violations_returns_list(self, worker, fhir_client, rules_validator, tenant_hospital_a):
        """Test that rule violations are returned."""
        rules_validator.validate.return_value = {
            "valid": False,
            "violations": ["Minimum notice period not met", "Outside operating hours"]
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "service_type": "consultation",
            "start_time": "2024-01-15T06:00:00Z"
        })

        assert result["valid"] is False
        assert len(result["violations"]) == 2
