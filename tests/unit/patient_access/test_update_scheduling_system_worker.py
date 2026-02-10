"""Tests for UpdateSchedulingSystemWorker."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.update_scheduling_system_worker import (
    UpdateSchedulingSystemWorker,
    UpdateSchedulingSystemInput,
    UpdateSchedulingSystemOutput,
    SchedulingSystemUpdaterProtocol,
    SystemSyncStatus,
    PatientAccessException,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockSchedulingSystemUpdater(SchedulingSystemUpdaterProtocol):
    """Mock updater for testing."""

    def __init__(self):
        self.sync_tasy_called = False
        self.sync_mv_soul_called = False
        self.should_fail_tasy = False
        self.should_fail_mv_soul = False

    async def sync_to_tasy(self, appointment_data: dict[str, Any]) -> SystemSyncStatus:
        """Mock Tasy sync."""
        self.sync_tasy_called = True
        if self.should_fail_tasy:
            return SystemSyncStatus(
                system_name="tasy",
                sync_successful=False,
                synced_at=datetime.now(timezone.utc).isoformat(),
                external_id=None,
                error_message="Tasy connection failed",
                retry_count=1,
            )

        return SystemSyncStatus(
            system_name="tasy",
            sync_successful=True,
            synced_at=datetime.now(timezone.utc).isoformat(),
            external_id=f"tasy_{appointment_data['appointment_id']}",
            error_message=None,
            retry_count=0,
        )

    async def sync_to_mv_soul(self, appointment_data: dict[str, Any]) -> SystemSyncStatus:
        """Mock MV Soul sync."""
        self.sync_mv_soul_called = True
        if self.should_fail_mv_soul:
            return SystemSyncStatus(
                system_name="mv_soul",
                sync_successful=False,
                synced_at=datetime.now(timezone.utc).isoformat(),
                external_id=None,
                error_message="MV Soul authentication failed",
                retry_count=1,
            )

        return SystemSyncStatus(
            system_name="mv_soul",
            sync_successful=True,
            synced_at=datetime.now(timezone.utc).isoformat(),
            external_id=f"mv_soul_{appointment_data['appointment_id']}",
            error_message=None,
            retry_count=0,
        )


@pytest.fixture
def mock_updater():
    return MockSchedulingSystemUpdater()


@pytest.fixture
def worker(mock_updater):
    return UpdateSchedulingSystemWorker(system_updater=mock_updater)


@pytest.mark.unit
class TestUpdateSchedulingSystemWorker:
    @pytest.mark.asyncio
    async def test_happy_path_all_systems_synced(
        self, worker, mock_updater, tenant_austa
    ):
        """Test successful sync to all systems."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_123",
            "patient_id": "patient_456",
            "practitioner_id": "prac_789",
            "appointment_datetime": "2026-02-15T09:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_001",
            "specialty_code": "cardiology",
            "status": "booked",
            "systems_to_update": ["tasy", "mv_soul"],
            "insurance_plan_id": "plan_123",
            "procedure_codes": ["TUSS-001", "TUSS-002"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["sync_completed"] is True
        assert result["systems_synced"] == 2
        assert result["systems_failed"] == 0
        assert result["partial_success"] is True
        assert len(result["sync_statuses"]) == 2
        assert mock_updater.sync_tasy_called is True
        assert mock_updater.sync_mv_soul_called is True

    @pytest.mark.asyncio
    async def test_partial_sync_success(self, worker, mock_updater, tenant_austa):
        """Test partial sync where one system fails."""
        # Arrange
        mock_updater.should_fail_mv_soul = True
        task_vars = {
            "appointment_id": "appt_partial",
            "patient_id": "patient_partial",
            "practitioner_id": "prac_partial",
            "appointment_datetime": "2026-02-16T10:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_002",
            "specialty_code": "orthopedics",
            "status": "booked",
            "systems_to_update": ["tasy", "mv_soul"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["sync_completed"] is False
        assert result["systems_synced"] == 1
        assert result["systems_failed"] == 1
        assert result["partial_success"] is True

    @pytest.mark.asyncio
    async def test_single_system_sync(self, worker, mock_updater, tenant_austa):
        """Test syncing to only one system."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_single",
            "patient_id": "patient_single",
            "practitioner_id": "prac_single",
            "appointment_datetime": "2026-02-17T11:00:00Z",
            "appointment_type": "followup",
            "location_id": "location_003",
            "specialty_code": "general",
            "status": "booked",
            "systems_to_update": ["tasy"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["sync_completed"] is True
        assert result["systems_synced"] == 1
        assert mock_updater.sync_tasy_called is True
        assert mock_updater.sync_mv_soul_called is False

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing practitioner_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "appointment_id": "appt_123",
                    "patient_id": "patient_456",
                    "appointment_datetime": "2026-02-15T09:00:00Z",
                    "appointment_type": "consultation",
                    "location_id": "location_001",
                    "specialty_code": "cardiology",
                    "status": "booked",
                    "systems_to_update": ["tasy"],
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "appointment_id": "appt_123",
                    "patient_id": "patient_456",
                    "practitioner_id": "prac_789",
                    "appointment_datetime": "2026-02-15T09:00:00Z",
                    "appointment_type": "consultation",
                    "location_id": "location_001",
                    "specialty_code": "cardiology",
                    "status": "booked",
                    "systems_to_update": ["tasy"],
                }
            )

    @pytest.mark.asyncio
    async def test_all_systems_fail_raises_exception(
        self, worker, mock_updater, tenant_austa
    ):
        """Test that all systems failing raises PatientAccessException."""
        # Arrange
        mock_updater.should_fail_tasy = True
        mock_updater.should_fail_mv_soul = True
        task_vars = {
            "appointment_id": "appt_all_fail",
            "patient_id": "patient_fail",
            "practitioner_id": "prac_fail",
            "appointment_datetime": "2026-02-18T12:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_fail",
            "specialty_code": "test",
            "status": "booked",
            "systems_to_update": ["tasy", "mv_soul"],
        }

        # Act & Assert
        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(task_vars)

        assert "Falha ao sincronizar com todos os sistemas" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(
        self, worker, mock_updater, tenant_austa, tenant_hpa
    ):
        """Test that scheduling updates are isolated per tenant."""
        # Arrange
        task_vars_austa = {
            "appointment_id": "appt_austa",
            "patient_id": "patient_austa",
            "practitioner_id": "prac_austa",
            "appointment_datetime": "2026-02-19T09:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_austa",
            "specialty_code": "cardiology",
            "status": "booked",
            "systems_to_update": ["tasy"],
        }

        task_vars_hpa = {
            "appointment_id": "appt_hpa",
            "patient_id": "patient_hpa",
            "practitioner_id": "prac_hpa",
            "appointment_datetime": "2026-02-19T10:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_hpa",
            "specialty_code": "orthopedics",
            "status": "booked",
            "systems_to_update": ["mv_soul"],
        }

        # Act
        result_austa = await worker.execute(task_vars_austa)
        result_hpa = await worker.execute(task_vars_hpa)

        # Assert - Different appointments
        assert result_austa["sync_completed"] is True
        assert result_hpa["sync_completed"] is True

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, mock_updater, tenant_austa):
        """Test that updating scheduling system twice is safe."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_idem",
            "patient_id": "patient_idem",
            "practitioner_id": "prac_idem",
            "appointment_datetime": "2026-02-20T11:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_idem",
            "specialty_code": "general",
            "status": "booked",
            "systems_to_update": ["tasy"],
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both succeed
        assert result1["sync_completed"] is True
        assert result2["sync_completed"] is True

    @pytest.mark.asyncio
    async def test_sync_status_details(self, worker, mock_updater, tenant_austa):
        """Test that sync statuses contain proper details."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_details",
            "patient_id": "patient_details",
            "practitioner_id": "prac_details",
            "appointment_datetime": "2026-02-21T12:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_details",
            "specialty_code": "test",
            "status": "booked",
            "systems_to_update": ["tasy", "mv_soul"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert len(result["sync_statuses"]) == 2
        for status in result["sync_statuses"]:
            assert "system_name" in status
            assert "sync_successful" in status
            assert "synced_at" in status
            assert "external_id" in status
            assert "retry_count" in status
            if status["sync_successful"]:
                assert status["external_id"] is not None

    @pytest.mark.asyncio
    async def test_cancelled_appointment_sync(self, worker, mock_updater, tenant_austa):
        """Test syncing a cancelled appointment."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_cancelled",
            "patient_id": "patient_cancelled",
            "practitioner_id": "prac_cancelled",
            "appointment_datetime": "2026-02-22T13:00:00Z",
            "appointment_type": "consultation",
            "location_id": "location_cancelled",
            "specialty_code": "test",
            "status": "cancelled",
            "systems_to_update": ["tasy"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["sync_completed"] is True
