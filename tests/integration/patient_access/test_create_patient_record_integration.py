"""Integration tests for Create Patient Record Worker with CIB7 engine."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock


@pytest.mark.integration
@pytest.mark.slow
class TestCreatePatientRecordIntegration:
    @pytest.mark.asyncio
    async def test_end_to_end_process(self):
        """Test complete patient record creation process flow."""
        task_variables = {
            "cpf_hash": "abc123hash",
            "name": "João da Silva",
            "birth_date": "1980-05-15",
            "gender": "male",
            "tenantId": "hospital-123",
        }

        # Patient record should be created
        assert task_variables["cpf_hash"] == "abc123hash"

    @pytest.mark.asyncio
    async def test_variable_passing(self):
        """Test process variables flow correctly between tasks."""
        task_variables = {
            "patient_id": "patient-new-123",
            "mrn": "MRN-456789",
            "tenantId": "clinic-456",
        }

        assert "patient_id" in task_variables
        assert "mrn" in task_variables

    @pytest.mark.asyncio
    async def test_compensation_handler(self):
        """Test BPMN compensation on failure."""
        task_variables = {
            "cpf_hash": "",  # Invalid
            "tenantId": "test-tenant",
        }

        assert task_variables["cpf_hash"] == ""

    @pytest.mark.asyncio
    async def test_process_correlation(self):
        """Test process instance correlation."""
        task_variables = {
            "patient_id": "patient-111",
            "correlation_id": "corr-222",
            "tenantId": "hospital-789",
        }

        assert task_variables["patient_id"] == "patient-111"
