"""
Unit tests for Surgical Specimen Worker.

Tests specimen tracking, label verification, chain of custody,
and transport instruction generation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from healthcare_platform.clinical_operations.workers.surgical.surgical_specimen_worker import (
    SurgicalSpecimenWorker,
    SurgicalSpecimenInput,
    SurgicalSpecimenOutput,
    SurgicalOperationsException,
    TOPIC,
)
from healthcare_platform.shared.multi_tenant.context import (
    set_current_tenant,
    TenantContext,
    clear_tenant,
)


@pytest.fixture
def tenant_context():
    """Set up tenant context for tests."""
    tenant = TenantContext(
        tenant_id="hospital-001",
        tenant_name="Hospital Test",
        region="us-east-1"
    )
    set_current_tenant(tenant)
    yield tenant
    clear_tenant()


@pytest.fixture
def worker():
    """Create surgical specimen worker instance."""
    return SurgicalSpecimenWorker()


@pytest.fixture
def valid_specimen_data() -> dict[str, Any]:
    """Create valid specimen data for testing."""
    return {
        "surgery_id": "SURG-2024-001",
        "patient_id": "PAT-12345",
        "specimen_id": "SPEC-001",
        "specimen_type": "biopsy",
        "anatomical_site": "Right breast, upper outer quadrant",
        "laterality": "Right",
        "collection_time": datetime.now(timezone.utc),
        "collecting_practitioner_id": "DOC-789",
        "label_verified": True,
        "container_type": "Formalin container",
        "preservation_method": "formalin",
        "pathology_priority": "routine",
        "clinical_history_summary": "Suspicious mass on mammography, BIRADS 4"
    }


@pytest.mark.unit
class TestSurgicalSpecimenWorker:
    """Test suite for SurgicalSpecimenWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test successful specimen tracking with verified label."""
        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert
        assert result["specimen_id"] == "SPEC-001"
        assert result["surgery_id"] == "SURG-2024-001"
        assert result["label_verification_status"] == "verified"
        assert result["chain_of_custody_initiated"] is True
        assert "tracking_id" in result
        assert "tracking_timestamp" in result
        assert "transport_instructions" in result
        assert "estimated_processing_time" in result

    @pytest.mark.asyncio
    async def test_label_not_verified(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test handling of unverified label."""
        # Arrange - set label as not verified
        valid_specimen_data["label_verified"] = False

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert - should show discrepancy status
        assert result["label_verification_status"] == "discrepancy"
        assert result["specimen_id"] == "SPEC-001"

    @pytest.mark.asyncio
    async def test_stat_priority_processing_time(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test that stat priority has faster processing time than routine."""
        # Execute with stat priority
        valid_specimen_data["pathology_priority"] = "stat"
        stat_result = await worker.execute(valid_specimen_data)

        # Execute with routine priority
        valid_specimen_data["pathology_priority"] = "routine"
        valid_specimen_data["specimen_id"] = "SPEC-002"  # Change to avoid conflicts
        routine_result = await worker.execute(valid_specimen_data)

        # Assert - stat should have shorter time than routine
        stat_time = stat_result["estimated_processing_time"]
        routine_time = routine_result["estimated_processing_time"]

        assert "hours" in stat_time.lower()
        assert ("days" in routine_time.lower() or "business days" in routine_time.lower())

    @pytest.mark.asyncio
    async def test_frozen_specimen_transport(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test special transport instructions for frozen specimens."""
        # Arrange
        valid_specimen_data["preservation_method"] = "frozen"
        valid_specimen_data["container_type"] = "Cryovial"

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert - frozen specimens should have urgent transport instructions
        transport = result["transport_instructions"]
        assert "URGENT" in transport or "urgent" in transport.lower()
        assert any(keyword in transport.lower() for keyword in ["nitrogen", "dry ice", "frozen"])

    @pytest.mark.asyncio
    async def test_invalid_specimen_type(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test validation error for invalid specimen type."""
        # Arrange
        valid_specimen_data["specimen_type"] = "invalid_type"

        # Execute & Assert
        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(valid_specimen_data)

        assert "SURGICAL_OPERATIONS_ERROR" in str(exc_info.value)
        assert exc_info.value.bpmn_error_code == "SURGICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_tracking_id_generated(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test that tracking ID is generated and is a valid UUID."""
        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert - tracking_id should be present and valid UUID
        assert "tracking_id" in result
        tracking_id = result["tracking_id"]

        # Verify it's a valid UUID
        try:
            uuid_obj = UUID(tracking_id)
            assert str(uuid_obj) == tracking_id
        except ValueError:
            pytest.fail(f"tracking_id '{tracking_id}' is not a valid UUID")

    @pytest.mark.asyncio
    async def test_formalin_preservation_instructions(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test transport instructions for formalin-preserved specimens."""
        # Arrange
        valid_specimen_data["preservation_method"] = "formalin"
        valid_specimen_data["container_type"] = "Formalin container"

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert - formalin has standard transport
        transport = result["transport_instructions"]
        assert "Standard transport" in transport or "room temperature" in transport
        assert result["label_verification_status"] == "verified"

    @pytest.mark.asyncio
    async def test_fresh_specimen_urgent_handling(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test that fresh specimens have urgent handling instructions."""
        # Arrange
        valid_specimen_data["preservation_method"] = "fresh"
        valid_specimen_data["container_type"] = "Sterile container"

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert
        transport = result["transport_instructions"]
        assert "immediately" in transport.lower() or "urgent" in transport.lower()
        assert "4°C" in transport or "hour" in transport.lower()

    @pytest.mark.asyncio
    async def test_urgent_priority_processing_time(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test processing time for urgent priority specimens."""
        # Arrange
        valid_specimen_data["pathology_priority"] = "urgent"

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert
        processing_time = result["estimated_processing_time"]
        assert "hours" in processing_time.lower() or "24-48" in processing_time

    @pytest.mark.asyncio
    async def test_organ_specimen_longer_processing(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test that organ specimens have longer processing times."""
        # Arrange
        valid_specimen_data["specimen_type"] = "organ"
        valid_specimen_data["pathology_priority"] = "routine"
        valid_specimen_data["anatomical_site"] = "Kidney"

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert - organ should have longer processing time
        processing_time = result["estimated_processing_time"]
        assert "days" in processing_time.lower()

    @pytest.mark.asyncio
    async def test_chain_of_custody_initiated(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test that chain of custody is properly initiated."""
        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert
        assert result["chain_of_custody_initiated"] is True

    @pytest.mark.asyncio
    async def test_tissue_specimen_processing(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test processing of tissue specimens."""
        # Arrange
        valid_specimen_data["specimen_type"] = "tissue"
        valid_specimen_data["anatomical_site"] = "Colon segment"

        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert
        assert result["label_verification_status"] == "verified"
        assert result["specimen_id"] == "SPEC-001"
        assert "estimated_processing_time" in result

    @pytest.mark.asyncio
    async def test_invalid_preservation_method(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test validation error for invalid preservation method."""
        # Arrange
        valid_specimen_data["preservation_method"] = "invalid_method"

        # Execute & Assert
        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(valid_specimen_data)

        assert exc_info.value.bpmn_error_code == "SURGICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_invalid_priority(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test validation error for invalid pathology priority."""
        # Arrange
        valid_specimen_data["pathology_priority"] = "super_urgent"

        # Execute & Assert
        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(valid_specimen_data)

        assert exc_info.value.bpmn_error_code == "SURGICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_tracking_timestamp_present(
        self,
        worker: SurgicalSpecimenWorker,
        tenant_context: TenantContext,
        valid_specimen_data: dict[str, Any]
    ):
        """Test that tracking timestamp is recorded."""
        # Execute
        result = await worker.execute(valid_specimen_data)

        # Assert
        assert "tracking_timestamp" in result
        timestamp = result["tracking_timestamp"]
        assert isinstance(timestamp, (str, datetime))
