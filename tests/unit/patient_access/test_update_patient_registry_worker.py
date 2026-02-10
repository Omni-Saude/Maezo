"""Tests for UpdatePatientRegistryWorker."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.update_patient_registry_worker import (
    UpdatePatientRegistryWorker,
    PatientRegistryUpdateInput,
    PatientRegistryUpdateOutput,
    PatientRegistryUpdaterProtocol,
    SystemSyncResult,
    PatientAccessException,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockPatientRegistryUpdater(PatientRegistryUpdaterProtocol):
    """Mock updater for testing."""

    def __init__(self):
        self.sync_called = 0
        self.should_fail_tasy = False
        self.should_fail_mv_soul = False
        self.synced_systems = []

    async def sync_to_system(
        self, system_name: str, patient_id: str, mrn: str, patient_data: dict[str, Any]
    ) -> SystemSyncResult:
        """Mock system sync."""
        self.sync_called += 1
        self.synced_systems.append(system_name)

        if system_name == "tasy" and self.should_fail_tasy:
            return SystemSyncResult(
                system_name="tasy",
                success=False,
                error_message="Tasy connection timeout",
            )

        if system_name == "mv_soul" and self.should_fail_mv_soul:
            return SystemSyncResult(
                system_name="mv_soul",
                success=False,
                error_message="MV Soul authentication failed",
            )

        return SystemSyncResult(
            system_name=system_name,
            success=True,
            error_message=None,
        )


@pytest.fixture
def mock_updater():
    return MockPatientRegistryUpdater()


@pytest.fixture
def worker(mock_updater):
    return UpdatePatientRegistryWorker(updater=mock_updater)


@pytest.mark.unit
class TestUpdatePatientRegistryWorker:
    @pytest.mark.asyncio
    async def test_happy_path_all_systems_synced(
        self, worker, mock_updater, tenant_austa
    ):
        """Test successful sync to all systems."""
        # Arrange
        task_vars = {
            "patient_id": "patient_123",
            "mrn": "MRN-12345",
            "patient_data": {
                "name": "João Silva",
                "birth_date": "1980-01-15",
                "gender": "male",
            },
            "target_systems": ["tasy", "mv_soul"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_id"] == "patient_123"
        assert result["mrn"] == "MRN-12345"
        assert result["all_systems_synced"] is True
        assert len(result["sync_results"]) == 2
        assert len(result["failed_systems"]) == 0
        assert mock_updater.sync_called == 2

    @pytest.mark.asyncio
    async def test_partial_sync_success(self, worker, mock_updater, tenant_austa):
        """Test partial sync where one system fails."""
        # Arrange
        mock_updater.should_fail_mv_soul = True
        task_vars = {
            "patient_id": "patient_456",
            "mrn": "MRN-67890",
            "patient_data": {"name": "Maria Santos"},
            "target_systems": ["tasy", "mv_soul"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["all_systems_synced"] is False
        assert len(result["sync_results"]) == 2
        assert "mv_soul" in result["failed_systems"]
        assert "tasy" not in result["failed_systems"]

    @pytest.mark.asyncio
    async def test_single_system_sync(self, worker, mock_updater, tenant_austa):
        """Test syncing to only one system."""
        # Arrange
        task_vars = {
            "patient_id": "patient_single",
            "mrn": "MRN-SINGLE",
            "patient_data": {"name": "Test Patient"},
            "target_systems": ["tasy"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["all_systems_synced"] is True
        assert len(result["sync_results"]) == 1
        assert result["sync_results"][0]["system_name"] == "tasy"

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_data raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "mrn": "MRN-123",
                    "target_systems": ["tasy"],
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "mrn": "MRN-123",
                    "patient_data": {"name": "Test"},
                    "target_systems": ["tasy"],
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
            "patient_id": "patient_all_fail",
            "mrn": "MRN-FAIL",
            "patient_data": {"name": "Fail Test"},
            "target_systems": ["tasy", "mv_soul"],
        }

        # Act & Assert
        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(task_vars)

        assert "Falha ao sincronizar com todos os sistemas" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(
        self, worker, mock_updater, tenant_austa, tenant_hpa
    ):
        """Test that registry updates are isolated per tenant."""
        # Arrange
        task_vars_austa = {
            "patient_id": "patient_austa",
            "mrn": "MRN-AUSTA",
            "patient_data": {"name": "AUSTA Patient"},
            "target_systems": ["tasy"],
        }

        task_vars_hpa = {
            "patient_id": "patient_hpa",
            "mrn": "MRN-HPA",
            "patient_data": {"name": "HPA Patient"},
            "target_systems": ["mv_soul"],
        }

        # Act
        result_austa = await worker.execute(task_vars_austa)
        result_hpa = await worker.execute(task_vars_hpa)

        # Assert - Different patients, different systems
        assert result_austa["patient_id"] != result_hpa["patient_id"]
        assert result_austa["mrn"] != result_hpa["mrn"]
        assert mock_updater.sync_called == 2

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, mock_updater, tenant_austa):
        """Test that updating registry twice is safe."""
        # Arrange
        task_vars = {
            "patient_id": "patient_idem",
            "mrn": "MRN-IDEM",
            "patient_data": {"name": "Idempotent Test"},
            "target_systems": ["tasy"],
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both succeed with same data
        assert result1["all_systems_synced"] is True
        assert result2["all_systems_synced"] is True
        assert result1["patient_id"] == result2["patient_id"]

    @pytest.mark.asyncio
    async def test_sync_result_details(self, worker, mock_updater, tenant_austa):
        """Test that sync results contain proper details."""
        # Arrange
        task_vars = {
            "patient_id": "patient_details",
            "mrn": "MRN-DETAILS",
            "patient_data": {"name": "Details Test"},
            "target_systems": ["tasy", "mv_soul"],
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert len(result["sync_results"]) == 2
        for sync_result in result["sync_results"]:
            assert "system_name" in sync_result
            assert "success" in sync_result
            assert "sync_timestamp" in sync_result
            assert sync_result["system_name"] in ["tasy", "mv_soul"]

    @pytest.mark.asyncio
    async def test_update_timestamp(self, worker, mock_updater, tenant_austa):
        """Test that update_timestamp is properly set."""
        # Arrange
        task_vars = {
            "patient_id": "patient_ts",
            "mrn": "MRN-TS",
            "patient_data": {"name": "Timestamp Test"},
            "target_systems": ["tasy"],
        }

        # Act
        before = datetime.utcnow()
        result = await worker.execute(task_vars)
        after = datetime.utcnow()

        # Assert - Timestamp is between before and after
        update_time = datetime.fromisoformat(
            result["update_timestamp"].replace("Z", "+00:00").replace("+00:00", "")
        )
        assert before <= update_time <= after
