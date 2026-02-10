"""Tests for IntegrateImagingWorker."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.integrate_imaging_worker import (
    IntegrateImagingInput,
    IntegrateImagingOutput,
    execute,
    ImagingIntegrationException,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.mark.unit
class TestIntegrateImagingWorker:
    """Test suite for IntegrateImagingWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, tenant_austa):
        """Test successful imaging integration."""
        input_data = {
            "patient_id": "pat-123",
            "accession_number": "ACC-2024-001",
            "study_instance_uid": "1.2.840.113619.2.1.123",
            "modality": "CT",
            "study_description": "CT Abdomen with contrast",
            "body_part": "Abdomen",
            "series_count": 2,
            "instance_count": 270,
            "study_date": datetime.now().isoformat(),
            "referring_physician": "Dr. Silva",
            "pacs_url": "https://pacs.example.com",
        }

        result = await execute(input_data)

        assert result["patient_id"] == "pat-123"
        assert result["accession_number"] == "ACC-2024-001"
        assert result["modality"] == "CT"
        assert result["study_status"] == "available"
        assert result["total_size_mb"] > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            await execute({
                "patient_id": "pat-123",
                # Missing required fields
            })

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = {
            "patient_id": "pat-123",
            "accession_number": "ACC-001",
            "study_instance_uid": "1.2.840.113619.2.1.123",
            "modality": "CT",
            "study_description": "CT Scan",
            "series_count": 1,
            "instance_count": 100,
            "study_date": datetime.now().isoformat(),
            "pacs_url": "https://pacs.example.com",
        }

        with pytest.raises(InvalidTenant):
            await execute(input_data)

    @pytest.mark.asyncio
    async def test_different_modalities(self, tenant_austa):
        """Test integration with different imaging modalities."""
        modalities = ["CT", "MR", "XR", "US", "NM", "PT", "CR", "DX"]

        for modality in modalities:
            input_data = {
                "patient_id": f"pat-{modality}",
                "accession_number": f"ACC-{modality}-001",
                "study_instance_uid": f"1.2.840.113619.{modality}",
                "modality": modality,
                "study_description": f"{modality} Study",
                "series_count": 2,
                "instance_count": 150,
                "study_date": datetime.now().isoformat(),
                "pacs_url": "https://pacs.example.com",
            }

            result = await execute(input_data)

            assert result["modality"] == modality
            assert result["study_status"] == "available"

    @pytest.mark.asyncio
    async def test_series_info_populated(self, tenant_austa):
        """Test that series information is populated."""
        input_data = {
            "patient_id": "pat-123",
            "accession_number": "ACC-001",
            "study_instance_uid": "1.2.840.113619.2.1.123",
            "modality": "CT",
            "study_description": "CT Scan",
            "series_count": 2,
            "instance_count": 270,
            "study_date": datetime.now().isoformat(),
            "pacs_url": "https://pacs.example.com",
        }

        result = await execute(input_data)

        assert "series_info" in result
        assert isinstance(result["series_info"], list)
        assert len(result["series_info"]) > 0

    @pytest.mark.asyncio
    async def test_fhir_resource_created(self, tenant_austa):
        """Test that FHIR ImagingStudy resource is created."""
        input_data = {
            "patient_id": "pat-123",
            "accession_number": "ACC-001",
            "study_instance_uid": "1.2.840.113619.2.1.123",
            "modality": "MR",
            "study_description": "MRI Brain",
            "series_count": 4,
            "instance_count": 480,
            "study_date": datetime.now().isoformat(),
            "pacs_url": "https://pacs.example.com",
        }

        result = await execute(input_data)

        assert "fhir_imaging_study_id" in result
        assert result["fhir_imaging_study_id"].startswith("ImagingStudy/")

    @pytest.mark.asyncio
    async def test_viewer_url_generated(self, tenant_austa):
        """Test that viewer URL is generated."""
        input_data = {
            "patient_id": "pat-123",
            "accession_number": "ACC-001",
            "study_instance_uid": "1.2.840.113619.2.1.123",
            "modality": "CT",
            "study_description": "CT Scan",
            "series_count": 2,
            "instance_count": 270,
            "study_date": datetime.now().isoformat(),
            "pacs_url": "https://pacs.example.com",
        }

        result = await execute(input_data)

        assert "viewer_url" in result
        assert result["viewer_url"] is not None
        assert "pacs.example.com" in result["viewer_url"]
        assert result["study_instance_uid"] in result["viewer_url"]

    @pytest.mark.asyncio
    async def test_optional_fields(self, tenant_austa):
        """Test integration with optional fields."""
        input_data = {
            "patient_id": "pat-123",
            "accession_number": "ACC-001",
            "study_instance_uid": "1.2.840.113619.2.1.123",
            "modality": "US",
            "study_description": "Ultrasound Abdomen",
            "body_part": "Abdomen",
            "series_count": 1,
            "instance_count": 30,
            "study_date": datetime.now().isoformat(),
            "referring_physician": "Dr. Santos",
            "pacs_url": "https://pacs.example.com",
            "dicom_metadata": {
                "patient_position": "HFS",
                "manufacturer": "GE Healthcare",
            },
        }

        result = await execute(input_data)

        assert result["study_status"] == "available"

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = {
            "patient_id": "pat-999",
            "accession_number": "ACC-999",
            "study_instance_uid": "1.2.840.999",
            "modality": "XR",
            "study_description": "X-Ray Chest",
            "series_count": 1,
            "instance_count": 2,
            "study_date": datetime.now().isoformat(),
            "pacs_url": "https://pacs.example.com",
        }

        result = await execute(input_data)

        assert result["patient_id"] == "pat-999"
        assert result["accession_number"] == "ACC-999"

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test that multiple executions produce consistent results."""
        input_data = {
            "patient_id": "pat-idem",
            "accession_number": "ACC-idem",
            "study_instance_uid": "1.2.840.idem",
            "modality": "CT",
            "study_description": "CT Scan",
            "series_count": 2,
            "instance_count": 270,
            "study_date": datetime.now().isoformat(),
            "pacs_url": "https://pacs.example.com",
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        # Should have same patient_id and accession_number
        assert result1["patient_id"] == result2["patient_id"]
        assert result1["accession_number"] == result2["accession_number"]
