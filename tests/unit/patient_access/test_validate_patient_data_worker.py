"""Tests for ValidatePatientDataWorker."""
from __future__ import annotations

from datetime import date
import hashlib
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.validate_patient_data_worker import (
    ValidatePatientDataWorker,
    ValidatePatientDataInput,
    ValidatePatientDataOutput,
    PatientDataValidator,
    PatientAccessException,
)
from healthcare_platform.shared.domain.value_objects import CPF, CNS
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockPatientDataValidator(PatientDataValidator):
    """Mock validator for testing."""

    def __init__(self):
        self.validate_cpf_called = False
        self.validate_cns_called = False
        self.validate_demographic_called = False
        self.should_fail_cpf = False
        self.should_fail_cns = False
        self.should_fail_demographic = False

    async def validate_cpf(self, cpf: str) -> CPF:
        """Mock CPF validation."""
        self.validate_cpf_called = True
        if self.should_fail_cpf:
            raise ValueError("CPF inválido")
        return CPF.from_raw(cpf)

    async def validate_cns(self, cns: str) -> CNS:
        """Mock CNS validation."""
        self.validate_cns_called = True
        if self.should_fail_cns:
            raise ValueError("CNS inválido")
        return CNS.from_raw(cns)

    async def validate_demographic_data(
        self, name: str, birth_date: str, gender: str
    ) -> dict[str, Any]:
        """Mock demographic validation."""
        self.validate_demographic_called = True
        errors = []

        if self.should_fail_demographic:
            errors.append("Nome inválido")

        if len(name) < 3:
            errors.append("Nome deve ter pelo menos 3 caracteres")

        try:
            birth_date_obj = date.fromisoformat(birth_date)
            if birth_date_obj > date.today():
                errors.append("Data de nascimento não pode ser no futuro")
        except ValueError:
            errors.append("Data de nascimento inválida")

        if gender not in ["male", "female", "other", "unknown"]:
            errors.append("Gênero inválido")

        return {"is_valid": len(errors) == 0, "errors": errors}


@pytest.fixture
def mock_validator():
    return MockPatientDataValidator()


@pytest.fixture
def worker(mock_validator):
    return ValidatePatientDataWorker(validator=mock_validator)


@pytest.mark.unit
class TestValidatePatientDataWorker:
    @pytest.mark.asyncio
    async def test_happy_path_all_valid(self, worker, mock_validator, tenant_austa):
        """Test successful validation of all patient data."""
        # Arrange
        task_vars = {
            "cpf": "11144477735",  # Valid CPF
            "cns": "123456789012345",
            "name": "João Silva Santos",
            "birth_date": "1980-01-15",
            "gender": "male",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is True
        assert len(result["validation_errors"]) == 0
        assert result["cpf_hash"] is not None
        assert result["cns_hash"] is not None
        assert mock_validator.validate_cpf_called is True
        assert mock_validator.validate_cns_called is True
        assert mock_validator.validate_demographic_called is True

    @pytest.mark.asyncio
    async def test_cpf_hashing_for_privacy(self, worker, mock_validator, tenant_austa):
        """Test that CPF is hashed for privacy compliance."""
        # Arrange
        cpf = "11144477735"  # Valid CPF
        task_vars = {
            "cpf": cpf,
            "name": "Test Patient",
            "birth_date": "1990-05-20",
            "gender": "female",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        expected_hash = hashlib.sha256(cpf.encode()).hexdigest()
        assert result["cpf_hash"] == expected_hash
        # Original CPF should NOT be in result
        assert cpf not in str(result)

    @pytest.mark.asyncio
    async def test_validation_without_cns(self, worker, mock_validator, tenant_austa):
        """Test validation without optional CNS."""
        # Arrange
        task_vars = {
            "cpf": "11144477735",  # Valid CPF
            "name": "Maria Santos",
            "birth_date": "1985-03-10",
            "gender": "female",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is True
        assert result["cpf_hash"] is not None
        assert result["cns_hash"] is None

    @pytest.mark.asyncio
    async def test_invalid_cpf(self, worker, mock_validator, tenant_austa):
        """Test handling of invalid CPF."""
        # Arrange
        mock_validator.should_fail_cpf = True
        task_vars = {
            "cpf": "invalid",
            "name": "Test Patient",
            "birth_date": "1990-01-01",
            "gender": "male",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert len(result["validation_errors"]) > 0
        assert any("CPF inválido" in error for error in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_invalid_name(self, worker, mock_validator, tenant_austa):
        """Test validation of too short name."""
        # Arrange
        task_vars = {
            "cpf": "12345678901",
            "name": "AB",  # Too short
            "birth_date": "1990-01-01",
            "gender": "male",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert any("3 caracteres" in error for error in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_future_birth_date(self, worker, mock_validator, tenant_austa):
        """Test validation rejects future birth dates."""
        # Arrange
        future_date = date.today().replace(year=date.today().year + 1)
        task_vars = {
            "cpf": "12345678901",
            "name": "Future Baby",
            "birth_date": future_date.isoformat(),
            "gender": "other",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert any("futuro" in error.lower() for error in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_invalid_gender(self, worker, mock_validator, tenant_austa):
        """Test validation of invalid gender value."""
        # Arrange
        task_vars = {
            "cpf": "12345678901",
            "name": "Test Patient",
            "birth_date": "1990-01-01",
            "gender": "invalid_gender",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert any("Gênero inválido" in error for error in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing name raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "cpf": "12345678901",
                    "birth_date": "1990-01-01",
                    "gender": "male",
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "cpf": "12345678901",
                    "name": "Test Patient",
                    "birth_date": "1990-01-01",
                    "gender": "male",
                }
            )

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(
        self, worker, mock_validator, tenant_austa, tenant_hpa
    ):
        """Test that patient data validations are isolated per tenant."""
        # Arrange (using valid CPFs)
        task_vars_austa = {
            "cpf": "11144477735",  # Valid CPF
            "name": "AUSTA Patient",
            "birth_date": "1980-01-01",
            "gender": "male",
        }

        task_vars_hpa = {
            "cpf": "52998224725",  # Different valid CPF
            "name": "HPA Patient",
            "birth_date": "1985-05-15",
            "gender": "female",
        }

        # Act
        result_austa = await worker.execute(task_vars_austa)
        result_hpa = await worker.execute(task_vars_hpa)

        # Assert - Different hashes for different CPFs
        assert result_austa["cpf_hash"] != result_hpa["cpf_hash"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, mock_validator, tenant_austa):
        """Test that validating same data twice produces same result."""
        # Arrange
        task_vars = {
            "cpf": "12345678901",
            "name": "Idempotent Test",
            "birth_date": "1990-01-01",
            "gender": "other",
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both produce same result
        assert result1["is_valid"] == result2["is_valid"]
        assert result1["cpf_hash"] == result2["cpf_hash"]
        assert len(result1["validation_errors"]) == len(result2["validation_errors"])

    @pytest.mark.asyncio
    async def test_all_gender_values(self, worker, mock_validator, tenant_austa):
        """Test all valid gender values."""
        for gender in ["male", "female", "other", "unknown"]:
            task_vars = {
                "cpf": "11144477735",  # Valid CPF
                "name": f"Test {gender}",
                "birth_date": "1990-01-01",
                "gender": gender,
            }

            result = await worker.execute(task_vars)

            assert result["is_valid"] is True

    @pytest.mark.asyncio
    async def test_multiple_validation_errors(self, worker, mock_validator, tenant_austa):
        """Test handling of multiple validation errors."""
        # Arrange - Multiple issues: short name, future birth date, invalid gender
        future_date = date.today().replace(year=date.today().year + 1)
        task_vars = {
            "cpf": "12345678901",
            "name": "AB",
            "birth_date": future_date.isoformat(),
            "gender": "invalid",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["is_valid"] is False
        assert len(result["validation_errors"]) >= 3
