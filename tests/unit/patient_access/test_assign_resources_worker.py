"""Tests for AssignResourcesWorker."""
from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.assign_resources_worker import (
        AssignResourcesWorker,
        StubResourceAssigner,
    )

    return AssignResourcesWorker(fhir_client=fhir_client, resource_assigner=StubResourceAssigner())


@pytest.mark.unit
class TestAssignResourcesWorker:
    @pytest.mark.asyncio
    async def test_happy_path_assign_resources(self, worker, fhir_client, tenant_austa):
        """Test successful resource assignment."""
        # Arrange
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        task_vars = {
            "appointment_reference": "Appointment/123",
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat(),
            "service_type": "consulta",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["all_resources_assigned"] is True
        assert len(result["assigned_resources"]) > 0
        assert len(result["missing_resources"]) == 0
        assert len(result["conflicts"]) == 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"appointment_reference": "Appointment/123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "appointment_reference": "Appointment/123",
                    "start_datetime": start_time.isoformat(),
                    "end_datetime": end_time.isoformat(),
                    "service_type": "consulta",
                }
            )

    @pytest.mark.asyncio
    async def test_surgery_resource_allocation(self, worker, tenant_austa):
        """Test resource allocation for surgical procedures."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=3)

        result = await worker.execute(
            {
                "appointment_reference": "Appointment/456",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "cirurgia",
            }
        )

        # Surgery requires more resources
        assert len(result["assigned_resources"]) >= 3
        resource_types = [r["resource_type"] for r in result["assigned_resources"]]
        assert "Location" in resource_types  # Operating room
        assert "Device" in resource_types  # Surgical equipment

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "appointment_reference": "Appointment/austa-123",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
            }
        )

        # Switch to HOSPITAL_B
        hospital_b_ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_B)
        set_current_tenant(hospital_b_ctx)

        # Execute with HOSPITAL_B
        result_hospital_b = await worker.execute(
            {
                "appointment_reference": "Appointment/hpa-123",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
            }
        )

        # Resources should be assigned independently
        assert result_austa["assigned_resources"] != result_hospital_b["assigned_resources"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        task_vars = {
            "appointment_reference": "Appointment/123",
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat(),
            "service_type": "consulta",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be consistent
        assert result1["all_resources_assigned"] == result2["all_resources_assigned"]
        assert len(result1["assigned_resources"]) == len(result2["assigned_resources"])

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.assign_resources_worker import PatientAccessException

        # Mock failure
        worker.resource_assigner.assign_resources = AsyncMock(
            side_effect=Exception("Resource allocation service unavailable")
        )

        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "appointment_reference": "Appointment/123",
                    "start_datetime": start_time.isoformat(),
                    "end_datetime": end_time.isoformat(),
                    "service_type": "consulta",
                }
            )

    @pytest.mark.asyncio
    async def test_resource_requirements_provided(self, worker, tenant_austa):
        """Test resource assignment with explicit requirements."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        result = await worker.execute(
            {
                "appointment_reference": "Appointment/789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "exame_simples",
                "resource_requirements": [
                    {"resource_type": "room", "resource_code": "exam_room", "quantity": 1},
                    {"resource_type": "equipment", "resource_code": "ecg_machine", "quantity": 1},
                ],
            }
        )

        assert result["all_resources_assigned"] is True
        assert len(result["assigned_resources"]) == 2

    @pytest.mark.asyncio
    async def test_location_preference(self, worker, tenant_austa):
        """Test resource assignment with location preference."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        result = await worker.execute(
            {
                "appointment_reference": "Appointment/999",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
                "location_id": "Location/building-a",
            }
        )

        # Should assign resources successfully
        assert result["all_resources_assigned"] is True

    @pytest.mark.asyncio
    async def test_partial_resource_allocation(self, worker, tenant_austa):
        """Test partial resource allocation when some resources unavailable."""
        from healthcare_platform.patient_access.workers.assign_resources_worker import AssignedResource

        # Mock partial allocation
        worker.resource_assigner.assign_resources = AsyncMock(
            return_value=(
                [
                    AssignedResource(
                        resource_reference="Location/room-1",
                        resource_type="Location",
                        resource_code="exam_room",
                        slot_reference="Slot/slot-1",
                        status="busy",
                    )
                ],
                ["equipment:ecg_machine"],  # Missing
                [],  # No conflicts
            )
        )

        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)

        result = await worker.execute(
            {
                "appointment_reference": "Appointment/456",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "exame_simples",
            }
        )

        assert result["all_resources_assigned"] is False
        assert len(result["missing_resources"]) == 1
        assert "equipment:ecg_machine" in result["missing_resources"]
