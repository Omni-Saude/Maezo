"""Tests for SurgicalSiteMarkingWorker."""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from healthcare_platform.clinical_operations.workers.surgical.surgical_site_marking_worker import (
    SurgicalOperationsException,
    SurgicalSiteMarkingInput,
    SurgicalSiteMarkingOutput,
    SurgicalSiteMarkingWorker,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    """Create tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance with mocked adapter."""
    return SurgicalSiteMarkingWorker(tasy_adapter=AsyncMock())


@pytest.mark.unit
class TestSurgicalSiteMarkingWorker:
    """Test suite for SurgicalSiteMarkingWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(self, worker, tenant_ctx):
        """Test successful surgical site marking verification."""
        task_variables = {
            "surgery_id": "SRG-001",
            "patient_id": "PAT-001",
            "procedure_code": "40701010",
            "procedure_description": "Left knee arthroscopy",
            "surgical_site": "Left knee",
            "laterality": "left",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": "photo://marking-001.jpg",
            "marking_confirmed": True,
            "patient_confirmed": True,
            "who_checklist_phase": "sign_in",
        }

        result = await worker.execute(task_variables)

        assert result["site_verified"] is True
        assert result["laterality_verified"] is True
        assert result["photo_confirmed"] is True
        assert result["patient_identity_confirmed"] is True
        assert result["who_phase_completed"] == "sign_in"
        assert result["surgery_id"] == "SRG-001"
        assert len(result["discrepancies"]) == 0
        assert "verification_id" in result
        assert "verification_timestamp" in result

    @pytest.mark.asyncio
    async def test_laterality_requires_photo(self, worker, tenant_ctx):
        """Test that lateral procedures require photo documentation."""
        task_variables = {
            "surgery_id": "SRG-002",
            "patient_id": "PAT-002",
            "procedure_code": "40701010",
            "procedure_description": "Left knee arthroscopy",
            "surgical_site": "Left knee",
            "laterality": "left",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": None,
            "marking_confirmed": True,
            "patient_confirmed": True,
        }

        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(task_variables)

        assert "SURGICAL_OPERATIONS_ERROR" in str(exc_info.value.bpmn_error_code)
        assert "Photo documentation required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_not_applicable_laterality_no_photo_needed(
        self, worker, tenant_ctx
    ):
        """Test that non-lateral procedures don't require photo."""
        task_variables = {
            "surgery_id": "SRG-003",
            "patient_id": "PAT-003",
            "procedure_code": "31101011",
            "procedure_description": "Appendectomy",
            "surgical_site": "Abdomen",
            "laterality": "not_applicable",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": None,
            "marking_confirmed": True,
            "patient_confirmed": True,
        }

        result = await worker.execute(task_variables)

        assert result["site_verified"] is True
        assert result["laterality_verified"] is True
        assert result["photo_confirmed"] is False
        assert len(result["discrepancies"]) == 0

    @pytest.mark.asyncio
    async def test_marking_not_confirmed_adds_discrepancy(self, worker, tenant_ctx):
        """Test that unconfirmed marking creates discrepancy."""
        task_variables = {
            "surgery_id": "SRG-004",
            "patient_id": "PAT-004",
            "procedure_code": "40701010",
            "procedure_description": "Left knee arthroscopy",
            "surgical_site": "Left knee",
            "laterality": "left",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": "photo://marking-002.jpg",
            "marking_confirmed": False,
            "patient_confirmed": True,
        }

        result = await worker.execute(task_variables)

        assert result["site_verified"] is False
        assert len(result["discrepancies"]) == 1
        assert "not confirmed surgical site marking" in result["discrepancies"][0]

    @pytest.mark.asyncio
    async def test_patient_not_confirmed_adds_discrepancy(self, worker, tenant_ctx):
        """Test that unconfirmed patient creates discrepancy."""
        task_variables = {
            "surgery_id": "SRG-005",
            "patient_id": "PAT-005",
            "procedure_code": "40701010",
            "procedure_description": "Left knee arthroscopy",
            "surgical_site": "Left knee",
            "laterality": "left",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": "photo://marking-003.jpg",
            "marking_confirmed": True,
            "patient_confirmed": False,
        }

        result = await worker.execute(task_variables)

        assert result["site_verified"] is False
        assert result["patient_identity_confirmed"] is False
        assert len(result["discrepancies"]) == 1
        assert "not confirmed surgical site and procedure" in result["discrepancies"][0]

    @pytest.mark.asyncio
    async def test_invalid_laterality_raises(self, worker, tenant_ctx):
        """Test that invalid laterality value raises exception."""
        task_variables = {
            "surgery_id": "SRG-006",
            "patient_id": "PAT-006",
            "procedure_code": "40701010",
            "procedure_description": "Knee arthroscopy",
            "surgical_site": "Knee",
            "laterality": "invalid",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": "photo://marking-004.jpg",
            "marking_confirmed": True,
            "patient_confirmed": True,
        }

        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(task_variables)

        assert "Validation error" in str(exc_info.value)
        assert "Laterality must be one of" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verification_id_is_uuid(self, worker, tenant_ctx):
        """Test that verification ID is a valid UUID."""
        task_variables = {
            "surgery_id": "SRG-007",
            "patient_id": "PAT-007",
            "procedure_code": "31101011",
            "procedure_description": "Appendectomy",
            "surgical_site": "Abdomen",
            "laterality": "not_applicable",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": None,
            "marking_confirmed": True,
            "patient_confirmed": True,
        }

        result = await worker.execute(task_variables)

        verification_id = result["verification_id"]
        # Should not raise ValueError
        uuid.UUID(verification_id)

    @pytest.mark.asyncio
    async def test_who_phase_defaults_to_sign_in(self, worker, tenant_ctx):
        """Test that WHO checklist phase defaults to sign_in."""
        task_variables = {
            "surgery_id": "SRG-008",
            "patient_id": "PAT-008",
            "procedure_code": "31101011",
            "procedure_description": "Appendectomy",
            "surgical_site": "Abdomen",
            "laterality": "not_applicable",
            "marking_practitioner_id": "DOC-001",
            "photo_reference": None,
            "marking_confirmed": True,
            "patient_confirmed": True,
            # who_checklist_phase not provided
        }

        result = await worker.execute(task_variables)

        assert result["who_phase_completed"] == "sign_in"
