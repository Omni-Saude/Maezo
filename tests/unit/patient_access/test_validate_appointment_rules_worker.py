"""Tests for ValidateAppointmentRulesWorker."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.validate_appointment_rules_worker import (
    ValidateAppointmentRulesWorker,
    AppointmentRulesInput,
    AppointmentRulesOutput,
    AppointmentRulesValidator,
    RuleViolation,
    PatientAccessException,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockAppointmentRulesValidator(AppointmentRulesValidator):
    """Mock validator for testing."""

    def __init__(self):
        self.validate_called = False
        self.should_fail = False
        self.force_violations = []

    async def validate_rules(
        self,
        patient_id: str,
        practitioner_id: str,
        specialty_code: str,
        proposed_datetime: datetime,
        service_type: str,
        duration_minutes: int,
        tenant_id: str | None = None,
    ) -> tuple[bool, list[RuleViolation], list[RuleViolation]]:
        """Mock rule validation."""
        self.validate_called = True

        if self.should_fail:
            raise Exception("Rule engine unavailable")

        violations = list(self.force_violations)
        warnings = []

        # Check business hours
        if proposed_datetime.hour < 8 or proposed_datetime.hour >= 18:
            violations.append(
                RuleViolation(
                    rule_code="BUSINESS_HOURS",
                    rule_name="Horário comercial",
                    violation_message="Agendamento fora do horário comercial (8:00-18:00)",
                    severity="ERROR",
                )
            )

        # Check weekend
        if proposed_datetime.weekday() >= 5:
            warnings.append(
                RuleViolation(
                    rule_code="WEEKEND_APPOINTMENT",
                    rule_name="Agendamento em fim de semana",
                    violation_message="Agendamento proposto para fim de semana",
                    severity="WARNING",
                )
            )

        is_valid = len(violations) == 0
        return is_valid, violations, warnings


@pytest.fixture
def mock_validator():
    return MockAppointmentRulesValidator()


@pytest.fixture
def worker(mock_validator, fhir_client):
    return ValidateAppointmentRulesWorker(
        fhir_client=fhir_client,
        rules_validator=mock_validator
    )


@pytest.mark.unit
class TestValidateAppointmentRulesWorker:
    @pytest.mark.asyncio
    async def test_happy_path_valid_appointment(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test successful validation of valid appointment."""
        # Arrange - Weekday during business hours
        proposed_time = datetime(2026, 2, 16, 10, 0)  # Monday 10:00
        task_vars = {
            "patient_id": "patient_123",
            "practitioner_id": "prac_456",
            "specialty_code": "cardiologia",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is True
        assert len(result["violations"]) == 0
        assert len(result["warnings"]) == 0
        assert "sucesso" in result["message"].lower()
        assert mock_validator.validate_called is True

    @pytest.mark.asyncio
    async def test_outside_business_hours(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test validation fails for appointment outside business hours."""
        # Arrange - 7:00 AM (before 8:00)
        proposed_time = datetime(2026, 2, 16, 7, 0)
        task_vars = {
            "patient_id": "patient_early",
            "practitioner_id": "prac_early",
            "specialty_code": "ortopedia",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert len(result["violations"]) > 0
        assert any("horário comercial" in v["violation_message"].lower()
                   for v in result["violations"])

    @pytest.mark.asyncio
    async def test_weekend_warning(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test validation produces warning for weekend appointment."""
        # Arrange - Saturday 10:00
        proposed_time = datetime(2026, 2, 14, 10, 0)  # Saturday
        task_vars = {
            "patient_id": "patient_weekend",
            "practitioner_id": "prac_weekend",
            "specialty_code": "pediatria",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert len(result["warnings"]) > 0
        assert any("fim de semana" in w["violation_message"].lower()
                   for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "practitioner_id": "prac_456",
                    "specialty_code": "cardiologia",
                    "proposed_datetime": datetime.now().isoformat(),
                    "service_type": "consultation",
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "practitioner_id": "prac_456",
                    "specialty_code": "cardiologia",
                    "proposed_datetime": datetime.now().isoformat(),
                    "service_type": "consultation",
                    "duration_minutes": 30,
                }
            )

    @pytest.mark.asyncio
    async def test_rule_engine_failure(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test handling of rule engine failure."""
        # Arrange
        mock_validator.should_fail = True
        task_vars = {
            "patient_id": "patient_fail",
            "practitioner_id": "prac_fail",
            "specialty_code": "test",
            "proposed_datetime": datetime.now().isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act & Assert
        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(task_vars)

        assert "Falha na validação de regras" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(
        self, worker, mock_validator, fhir_client, tenant_austa, tenant_hpa
    ):
        """Test that rule validations are isolated per tenant."""
        # Arrange
        proposed_time = datetime(2026, 2, 16, 10, 0)
        task_vars_austa = {
            "patient_id": "patient_austa",
            "practitioner_id": "prac_austa",
            "specialty_code": "cardiologia",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        task_vars_hpa = {
            "patient_id": "patient_hpa",
            "practitioner_id": "prac_hpa",
            "specialty_code": "ortopedia",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        result_austa = await worker.execute(task_vars_austa)
        result_hpa = await worker.execute(task_vars_hpa)

        # Assert - Both validations succeed independently
        assert result_austa["is_valid"] is True
        assert result_hpa["is_valid"] is True

    @pytest.mark.asyncio
    async def test_idempotency(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test that validating rules twice produces same result."""
        # Arrange
        proposed_time = datetime(2026, 2, 16, 10, 0)
        task_vars = {
            "patient_id": "patient_idem",
            "practitioner_id": "prac_idem",
            "specialty_code": "ginecologia",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both produce same result
        assert result1["is_valid"] == result2["is_valid"]
        assert len(result1["violations"]) == len(result2["violations"])

    @pytest.mark.asyncio
    async def test_multiple_violations(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test handling of multiple rule violations."""
        # Arrange - Weekend AND outside business hours
        proposed_time = datetime(2026, 2, 14, 19, 0)  # Saturday 19:00
        task_vars = {
            "patient_id": "patient_multi",
            "practitioner_id": "prac_multi",
            "specialty_code": "test",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert len(result["violations"]) > 0
        assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_validation_timestamp(
        self, worker, mock_validator, fhir_client, tenant_austa
    ):
        """Test that validation_timestamp is properly set."""
        # Arrange
        proposed_time = datetime(2026, 2, 16, 10, 0)
        task_vars = {
            "patient_id": "patient_ts",
            "practitioner_id": "prac_ts",
            "specialty_code": "test",
            "proposed_datetime": proposed_time.isoformat(),
            "service_type": "consultation",
            "duration_minutes": 30,
        }

        # Act
        before = datetime.utcnow()
        result = await worker.execute(task_vars)
        after = datetime.utcnow()

        # Assert - Timestamp is between before and after
        validation_time = datetime.fromisoformat(
            result["validation_timestamp"].replace("Z", "+00:00").replace("+00:00", "")
        )
        assert before <= validation_time <= after
