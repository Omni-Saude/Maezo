"""Tests for VerifyInsuranceCoverageWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def ans_verifier():
    """Mock ANS verifier protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, ans_verifier):
    from healthcare_platform.patient_access.workers.verify_insurance_coverage_worker import VerifyInsuranceCoverageWorker
    return VerifyInsuranceCoverageWorker(fhir_client=fhir_client, ans_verifier=ans_verifier)


class TestVerifyInsuranceCoverageWorker:
    @pytest.mark.asyncio
    async def test_happy_path_verifies_coverage(self, worker, fhir_client, ans_verifier, tenant_austa, mock_coverage):
        """Test successful insurance coverage verification."""
        fhir_client.read.return_value = mock_coverage
        ans_verifier.verify.return_value = {"active": True, "coverage_valid": True}

        result = await worker.execute({
            "patient_id": "patient-123",
            "coverage_id": "coverage-999"
        })

        assert result["verified"] is True
        assert result["active"] is True
        fhir_client.read.assert_called_once()
        ans_verifier.verify.assert_called_once()

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
    async def test_inactive_coverage_returns_false(self, worker, fhir_client, ans_verifier, tenant_austa, mock_coverage):
        """Test that inactive coverage returns verified=False."""
        inactive_coverage = {**mock_coverage, "status": "cancelled"}
        fhir_client.read.return_value = inactive_coverage
        ans_verifier.verify.return_value = {"active": False, "coverage_valid": False}

        result = await worker.execute({
            "patient_id": "patient-123",
            "coverage_id": "coverage-999"
        })

        assert result["verified"] is False
        assert result["active"] is False
