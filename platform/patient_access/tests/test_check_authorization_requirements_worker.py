"""Tests for CheckAuthorizationRequirementsWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException


@pytest.fixture
def auth_checker():
    """Mock authorization checker protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, auth_checker):
    from platform.patient_access.workers.check_authorization_requirements_worker import CheckAuthorizationRequirementsWorker
    return CheckAuthorizationRequirementsWorker(fhir_client=fhir_client, auth_checker=auth_checker)


class TestCheckAuthorizationRequirementsWorker:
    @pytest.mark.asyncio
    async def test_happy_path_checks_authorization(self, worker, fhir_client, auth_checker, tenant_austa):
        """Test successful authorization requirements check."""
        auth_checker.check_requirements.return_value = {
            "required": True,
            "authorization_type": "prior_auth",
            "estimated_days": 5
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "service_code": "SERVICE-001"
        })

        assert result["required"] is True
        assert result["authorization_type"] == "prior_auth"
        auth_checker.check_requirements.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_no_authorization_required(self, worker, fhir_client, auth_checker, tenant_austa):
        """Test that no authorization required returns required=False."""
        auth_checker.check_requirements.return_value = {
            "required": False,
            "authorization_type": None
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "service_code": "SERVICE-002"
        })

        assert result["required"] is False
        assert result["authorization_type"] is None
