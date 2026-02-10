"""Integration tests for Validate Patient Data Worker with CIB7 engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from healthcare_platform.patient_access.workers.validate_patient_data_worker import (
    ValidatePatientDataWorker,
    StubPatientDataValidator,
    PatientAccessException,
)
from healthcare_platform.shared.domain.value_objects import CPF, CNS


@pytest.mark.integration
@pytest.mark.slow
class TestValidatePatientDataIntegration:
    @pytest.fixture
    def mock_validator(self):
        """Create a mock validator for testing."""
        validator = StubPatientDataValidator()
        return validator

    @pytest.fixture
    def worker(self, mock_validator):
        """Create worker instance with mocked validator."""
        return ValidatePatientDataWorker(validator=mock_validator)

    @pytest.mark.asyncio
    async def test_end_to_end_process(self, worker):
        """Test complete validation process flow with mocked engine."""
        # Given: external task from Camunda with patient data
        task_variables = {
            "cpf": "12345678901",
            "cns": "123456789012345",
            "name": "João da Silva",
            "birth_date": "1980-05-15",
            "gender": "male",
            "tenantId": "hospital-123",
        }

        # When: worker executes validation
        result = await worker.execute(task_variables)

        # Then: validation result is returned with hashed PII
        assert result["is_valid"] is True
        assert "cpf_hash" in result
        assert result["cpf_hash"] != ""  # Hash is generated
        assert "cns_hash" in result
        assert len(result["validation_errors"]) == 0

    @pytest.mark.asyncio
    async def test_variable_passing(self, worker):
        """Test process variables flow correctly between tasks."""
        # Given: task variables with valid patient data
        task_variables = {
            "cpf": "98765432109",
            "cns": None,  # Optional CNS
            "name": "Maria Santos",
            "birth_date": "1990-03-20",
            "gender": "female",
            "tenantId": "clinic-456",
        }

        # When: executing the worker
        result = await worker.execute(task_variables)

        # Then: output variables are properly structured for next BPMN task
        assert "is_valid" in result
        assert "cpf_hash" in result
        assert "cns_hash" in result  # Should be None but present
        assert "validation_errors" in result
        assert isinstance(result["validation_errors"], list)

    @pytest.mark.asyncio
    async def test_invalid_cpf_handling(self, worker):
        """Test that invalid CPF is properly detected and reported."""
        # Given: task variables with invalid CPF
        task_variables = {
            "cpf": "00000000000",  # Invalid CPF
            "name": "Test Patient",
            "birth_date": "1985-01-01",
            "gender": "male",
            "tenantId": "test-tenant",
        }

        # When: executing validation
        result = await worker.execute(task_variables)

        # Then: validation should fail with error message
        assert result["is_valid"] is False
        assert len(result["validation_errors"]) > 0

    @pytest.mark.asyncio
    async def test_invalid_birth_date(self, worker):
        """Test that future birth dates are rejected."""
        # Given: birth date in the future
        future_date = "2030-01-01"
        task_variables = {
            "cpf": "12345678901",
            "name": "Future Baby",
            "birth_date": future_date,
            "gender": "unknown",
            "tenantId": "test-tenant",
        }

        # When: executing validation
        result = await worker.execute(task_variables)

        # Then: validation should fail
        assert result["is_valid"] is False
        assert any("futuro" in err.lower() or "future" in err.lower()
                   for err in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_invalid_gender(self, worker):
        """Test that invalid gender values are rejected."""
        # Given: invalid gender
        task_variables = {
            "cpf": "12345678901",
            "name": "Test Patient",
            "birth_date": "1985-01-01",
            "gender": "invalid_gender",
            "tenantId": "test-tenant",
        }

        # When: executing validation
        result = await worker.execute(task_variables)

        # Then: validation should fail with gender error
        assert result["is_valid"] is False
        assert any("gênero" in err.lower() or "gender" in err.lower()
                   for err in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker):
        """Test that tenant context is properly maintained."""
        # Given: tasks from different tenants
        tenant1_vars = {
            "cpf": "12345678901",
            "name": "Patient 1",
            "birth_date": "1980-01-01",
            "gender": "male",
            "tenantId": "tenant-1",
        }

        tenant2_vars = {
            "cpf": "98765432109",
            "name": "Patient 2",
            "birth_date": "1990-01-01",
            "gender": "female",
            "tenantId": "tenant-2",
        }

        # When: executing for both tenants
        result1 = await worker.execute(tenant1_vars)
        result2 = await worker.execute(tenant2_vars)

        # Then: both should succeed independently
        assert result1["is_valid"] is True
        assert result2["is_valid"] is True
        # And hashes should be different
        assert result1["cpf_hash"] != result2["cpf_hash"]

    @pytest.mark.asyncio
    async def test_compensation_handler(self, worker):
        """Test BPMN compensation on validation failure."""
        # Given: completely invalid data
        task_variables = {
            "cpf": "",  # Empty CPF
            "name": "AB",  # Too short name
            "birth_date": "invalid-date",  # Invalid format
            "gender": "invalid",
            "tenantId": "test-tenant",
        }

        # When: executing validation
        result = await worker.execute(task_variables)

        # Then: multiple validation errors should be present
        assert result["is_valid"] is False
        assert len(result["validation_errors"]) >= 3  # CPF, name, birth date, gender

    @pytest.mark.asyncio
    async def test_pii_hashing(self, worker):
        """Test that PII is properly hashed and not stored in plain text."""
        # Given: valid patient data
        task_variables = {
            "cpf": "12345678901",
            "cns": "123456789012345",
            "name": "Test Patient",
            "birth_date": "1985-01-01",
            "gender": "male",
            "tenantId": "test-tenant",
        }

        # When: executing validation
        result = await worker.execute(task_variables)

        # Then: hashes should be present and different from original
        assert result["cpf_hash"] != task_variables["cpf"]
        assert result["cns_hash"] != task_variables["cns"]
        assert len(result["cpf_hash"]) == 64  # SHA-256 produces 64 hex chars
        assert len(result["cns_hash"]) == 64
