"""Tests for CheckPreAuthorizationWorker."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def pre_auth_checker():
    """Mock pre-authorization checker protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, pre_auth_checker):
    from healthcare_platform.patient_access.workers.check_pre_authorization_worker import CheckPreAuthorizationWorker
    return CheckPreAuthorizationWorker(fhir_client=fhir_client, pre_auth_checker=pre_auth_checker)


class TestCheckPreAuthorizationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_checks_authorization(self, worker, fhir_client, pre_auth_checker, tenant_hospital_a):
        """Test successful pre-authorization check."""
        pre_auth_checker.check.return_value = {
            "authorized": True,
            "authorization_number": "AUTH-123456",
            "valid_until": "2024-12-31"
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "service_code": "SERVICE-001",
            "coverage_id": "coverage-999"
        })

        assert result["authorized"] is True
        assert result["authorization_number"] == "AUTH-123456"
        pre_auth_checker.check.assert_called_once()

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
    async def test_authorization_denied_returns_false(self, worker, fhir_client, pre_auth_checker, tenant_hospital_a):
        """Test that denied authorization returns authorized=False."""
        pre_auth_checker.check.return_value = {
            "authorized": False,
            "denial_reason": "Service not covered under plan"
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "service_code": "SERVICE-001",
            "coverage_id": "coverage-999"
        })

        assert result["authorized"] is False
        assert "denial_reason" in result
