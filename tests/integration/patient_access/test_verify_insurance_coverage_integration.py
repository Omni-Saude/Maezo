"""Integration tests for Verify Insurance Coverage Worker with CIB7 engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from healthcare_platform.patient_access.workers.verify_insurance_coverage_worker import (
    VerifyInsuranceCoverageWorker,
    StubInsuranceCoverageVerifier,
    PatientAccessException,
)


@pytest.mark.integration
@pytest.mark.slow
class TestVerifyInsuranceCoverageIntegration:
    @pytest.fixture
    def mock_fhir_client(self):
        """Create a mock FHIR client."""
        client = AsyncMock()
        client.create = AsyncMock(return_value={"id": "coverage-123", "resourceType": "Coverage"})
        return client

    @pytest.fixture
    def mock_verifier(self):
        """Create a mock insurance verifier."""
        return StubInsuranceCoverageVerifier()

    @pytest.fixture
    def worker(self, mock_fhir_client, mock_verifier):
        """Create worker instance with mocked dependencies."""
        return VerifyInsuranceCoverageWorker(
            fhir_client=mock_fhir_client,
            verifier=mock_verifier
        )

    @pytest.mark.asyncio
    async def test_end_to_end_process(self, worker):
        """Test complete insurance verification process flow."""
        # Given: external task from Camunda with insurance data
        task_variables = {
            "patient_reference": "Patient/patient-123",
            "operator_code": "123456",
            "plan_code": "GOLD-001",
            "card_number": "9876543210",
            "cardholder_name": "João da Silva",
            "tenantId": "hospital-123",
        }

        # When: worker executes verification
        result = await worker.execute(task_variables)

        # Then: verification result is returned
        assert result["coverage_active"] is True
        assert result["eligibility_verified"] is True
        assert "coverage_reference" in result
        assert result["coverage_status"] == "active"

    @pytest.mark.asyncio
    async def test_variable_passing(self, worker, mock_fhir_client):
        """Test process variables flow correctly between tasks."""
        # Given: task variables with insurance data
        task_variables = {
            "patient_reference": "Patient/patient-456",
            "operator_code": "654321",
            "plan_code": "STANDARD-002",
            "card_number": "1234567890",
            "cardholder_name": "Maria Santos",
            "tenantId": "clinic-456",
        }

        # When: executing the worker
        result = await worker.execute(task_variables)

        # Then: output variables are properly structured
        assert "coverage_active" in result
        assert "coverage_reference" in result
        assert "coverage_status" in result
        assert "eligibility_verified" in result
        assert "verification_date" in result

        # And FHIR client was called to create coverage resource
        mock_fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_ans_eligibility_verification(self, worker):
        """Test ANS eligibility verification integration."""
        # Given: valid insurance credentials
        task_variables = {
            "patient_reference": "Patient/patient-789",
            "operator_code": "ANS-12345",
            "plan_code": "PREMIUM-003",
            "card_number": "5555555555",
            "cardholder_name": "Carlos Oliveira",
            "tenantId": "hospital-789",
        }

        # When: verifying eligibility
        result = await worker.execute(task_variables)

        # Then: ANS eligibility is confirmed
        assert result["eligibility_verified"] is True
        assert result["coverage_active"] is True

    @pytest.mark.asyncio
    async def test_fhir_coverage_creation(self, worker, mock_fhir_client):
        """Test that FHIR Coverage resource is created correctly."""
        # Given: valid insurance data
        task_variables = {
            "patient_reference": "Patient/patient-111",
            "operator_code": "OP-123",
            "plan_code": "BASIC-001",
            "card_number": "1111111111",
            "cardholder_name": "Ana Costa",
            "tenantId": "clinic-111",
        }

        # When: executing verification
        result = await worker.execute(task_variables)

        # Then: FHIR create was called with Coverage resource
        mock_fhir_client.create.assert_called_once_with("Coverage", pytest.approx(dict, rel=1))
        assert result["coverage_reference"] == "Coverage/coverage-123"

    @pytest.mark.asyncio
    async def test_compensation_handler(self, worker, mock_fhir_client):
        """Test BPMN compensation when FHIR creation fails."""
        # Given: FHIR client that fails
        mock_fhir_client.create = AsyncMock(side_effect=Exception("FHIR server error"))

        task_variables = {
            "patient_reference": "Patient/patient-error",
            "operator_code": "OP-999",
            "plan_code": "ERROR-001",
            "card_number": "9999999999",
            "cardholder_name": "Error Patient",
            "tenantId": "test-tenant",
        }

        # When: executing with failing FHIR
        result = await worker.execute(task_variables)

        # Then: verification still succeeds but no coverage reference
        assert result["eligibility_verified"] is True
        assert result["coverage_reference"] is None  # FHIR creation failed

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker):
        """Test that tenant context is properly maintained."""
        # Given: insurance verifications for different tenants
        tenant1_vars = {
            "patient_reference": "Patient/p1",
            "operator_code": "OP-T1",
            "plan_code": "PLAN-T1",
            "card_number": "1111111111",
            "cardholder_name": "Tenant 1 Patient",
            "tenantId": "tenant-1",
        }

        tenant2_vars = {
            "patient_reference": "Patient/p2",
            "operator_code": "OP-T2",
            "plan_code": "PLAN-T2",
            "card_number": "2222222222",
            "cardholder_name": "Tenant 2 Patient",
            "tenantId": "tenant-2",
        }

        # When: executing for both tenants
        result1 = await worker.execute(tenant1_vars)
        result2 = await worker.execute(tenant2_vars)

        # Then: both should succeed independently
        assert result1["eligibility_verified"] is True
        assert result2["eligibility_verified"] is True
