"""Tests for CheckAvailabilityWorker."""
from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.check_availability_worker import (
        CheckAvailabilityWorker,
        StubAvailabilityChecker,
    )

    return CheckAvailabilityWorker(
        fhir_client=fhir_client, availability_checker=StubAvailabilityChecker()
    )


@pytest.mark.unit
class TestCheckAvailabilityWorker:
    @pytest.mark.asyncio
    async def test_happy_path_check_availability(self, worker, fhir_client, tenant_austa):
        """Test successful availability check."""
        # Arrange
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        task_vars = {
            "practitioner_id": "Practitioner/123",
            "service_type": "consulta",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["search_completed"] is True
        assert result["total_slots_found"] > 0
        assert len(result["available_slots"]) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"practitioner_id": "Practitioner/123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "practitioner_id": "Practitioner/123",
                    "service_type": "consulta",
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
            )

    @pytest.mark.asyncio
    async def test_slot_details(self, worker, tenant_austa):
        """Test that slots contain required details."""
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=1)

        result = await worker.execute(
            {
                "practitioner_id": "Practitioner/123",
                "service_type": "consulta",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        # Check slot structure
        for slot in result["available_slots"]:
            assert "slot_id" in slot
            assert "start_time" in slot
            assert "end_time" in slot
            assert "practitioner_id" in slot
            assert "service_type" in slot

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "practitioner_id": "Practitioner/austa-123",
                "service_type": "consulta",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        # Switch to HOSPITAL_B
        hospital_b_ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_B)
        set_current_tenant(hospital_b_ctx)

        # Execute with HOSPITAL_B
        result_hospital_b = await worker.execute(
            {
                "practitioner_id": "Practitioner/hpa-123",
                "service_type": "consulta",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        # Slots should be tenant-specific
        assert result_austa["available_slots"] != result_hospital_b["available_slots"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        task_vars = {
            "practitioner_id": "Practitioner/123",
            "service_type": "consulta",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be consistent
        assert result1["total_slots_found"] == result2["total_slots_found"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.check_availability_worker import PatientAccessException

        # Mock failure
        worker.availability_checker.check_availability = AsyncMock(
            side_effect=Exception("Schedule service unavailable")
        )

        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "practitioner_id": "Practitioner/123",
                    "service_type": "consulta",
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
            )

    @pytest.mark.asyncio
    async def test_location_filter(self, worker, tenant_austa):
        """Test availability check with location filter."""
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        result = await worker.execute(
            {
                "practitioner_id": "Practitioner/123",
                "service_type": "consulta",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "location_id": "Location/building-a",
            }
        )

        # Should still find slots
        assert result["search_completed"] is True
        assert result["total_slots_found"] > 0

    @pytest.mark.asyncio
    async def test_required_duration(self, worker, tenant_austa):
        """Test availability check with required duration."""
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        result = await worker.execute(
            {
                "practitioner_id": "Practitioner/123",
                "service_type": "consulta",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "required_duration_minutes": 60,  # Longer appointment
            }
        )

        # Should find slots with appropriate duration
        assert result["search_completed"] is True
        for slot in result["available_slots"]:
            # Parse datetimes and check duration
            slot_start = datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
            slot_end = datetime.fromisoformat(slot["end_time"].replace("Z", "+00:00"))
            duration = (slot_end - slot_start).total_seconds() / 60
            assert duration >= 60

    @pytest.mark.asyncio
    async def test_no_slots_available(self, worker, tenant_austa):
        """Test when no slots are available."""
        # Mock empty results
        worker.availability_checker.check_availability = AsyncMock(return_value=[])

        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=7)

        result = await worker.execute(
            {
                "practitioner_id": "Practitioner/123",
                "service_type": "consulta",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        assert result["search_completed"] is True
        assert result["total_slots_found"] == 0
        assert len(result["available_slots"]) == 0
