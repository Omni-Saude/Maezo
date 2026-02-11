"""Tests for ClinicalDocumentationWorker."""
from __future__ import annotations

from datetime import datetime
import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


@pytest.fixture
def tenant_hospital_a():
    """Set up AUSTA tenant context."""
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    """Mock FHIR client fixture."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """ClinicalDocumentationWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_documentation import ClinicalDocumentationWorker
    return ClinicalDocumentationWorker(fhir_client=fhir_client)


class TestClinicalDocumentationWorker:
    """Test cases for ClinicalDocumentationWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_progress_note(self, worker, fhir_client, tenant_hospital_a):
        """Test successful progress note creation."""
        fhir_client.create.return_value = {
            "resourceType": "DocumentReference",
            "id": "doc-123",
            "status": "current",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "document_type": "progress-note",
            "content": "Patient shows improvement in respiratory function.",
            "author_id": "practitioner-001",
        })

        assert result["status"] == "completed"
        assert result["document_id"] == "doc-123"
        assert result["patient_id"] == "patient-456"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_content_raises(self, worker, tenant_hospital_a):
        """Test that missing content raises DomainException."""
        with pytest.raises(DomainException, match="content is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "document_type": "progress-note",
            })

    @pytest.mark.asyncio
    async def test_missing_document_type_raises(self, worker, tenant_hospital_a):
        """Test that missing document_type raises DomainException."""
        with pytest.raises(DomainException, match="document_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "content": "Some content",
            })

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "document_type": "progress-note",
                "content": "Content",
            })
