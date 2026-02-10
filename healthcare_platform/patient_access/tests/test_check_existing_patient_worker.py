"""Tests for CheckExistingPatientWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.check_existing_patient_worker import CheckExistingPatientWorker
    return CheckExistingPatientWorker(fhir_client=fhir_client)


class TestCheckExistingPatientWorker:
    @pytest.mark.asyncio
    async def test_happy_path_finds_existing_patient(self, worker, fhir_client, tenant_austa, mock_patient):
        """Test successful check for existing patient."""
        fhir_client.search.return_value = {"entry": [{"resource": mock_patient}]}

        result = await worker.execute({
            "cpf": "12345678901"
        })

        assert result["exists"] is True
        assert result["patient_id"] == "patient-123"
        fhir_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing cpf raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"cpf": "12345678901"})

    @pytest.mark.asyncio
    async def test_patient_not_found_returns_false(self, worker, fhir_client, tenant_austa):
        """Test that non-existing patient returns exists=False."""
        fhir_client.search.return_value = {"entry": []}

        result = await worker.execute({
            "cpf": "98765432100"
        })

        assert result["exists"] is False
        assert result["patient_id"] is None
