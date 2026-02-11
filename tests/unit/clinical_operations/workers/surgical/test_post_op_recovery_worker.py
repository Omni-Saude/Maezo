"""Tests for PostOpRecoveryWorker."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from healthcare_platform.clinical_operations.workers.surgical.post_op_recovery_worker import (
    PostOpRecoveryInput,
    PostOpRecoveryOutput,
    PostOpRecoveryWorker,
    SurgicalOperationsException,
)
from healthcare_platform.shared.multi_tenant.context import TenantContext, clear_tenant, set_current_tenant


@pytest.mark.unit
class TestPostOpRecoveryWorker:
    """Tests for PostOpRecoveryWorker."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        """Create test tenant context."""
        return TenantContext(
            tenant_id="test-tenant-001",
            tenant_name="Test Hospital",
            features={"surgical_management": True},
            settings={},
        )

    @pytest.fixture
    def mock_tasy_adapter(self) -> AsyncMock:
        """Create mock TASY adapter."""
        adapter = AsyncMock()
        adapter.record_post_op_assessment = AsyncMock(return_value=None)
        return adapter

    @pytest.fixture
    def worker(self, mock_tasy_adapter: AsyncMock) -> PostOpRecoveryWorker:
        """Create worker instance with mocked adapter."""
        return PostOpRecoveryWorker(tasy_adapter=mock_tasy_adapter)

    @pytest.fixture(autouse=True)
    def setup_tenant(self, tenant_context: TenantContext) -> None:
        """Set up tenant context for each test."""
        set_current_tenant(tenant_context)
        yield
        clear_tenant()

    @pytest.mark.asyncio
    async def test_execute_stable_recovery(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test stable recovery with optimal scores."""
        # Arrange
        variables = {
            "surgery_id": "SURG-001",
            "patient_id": "PAT-12345",
            "pacu_bed_id": "PACU-BED-01",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 2,
            "aldrete_respiration": 2,
            "aldrete_circulation": 2,
            "aldrete_consciousness": 2,
            "aldrete_oxygen_saturation": 2,
            "pain_score": 2,
            "temperature": 36.8,
            "complications": [],
            "who_checklist_phase": "sign_out",
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["aldrete_total_score"] == 10
        assert result["recovery_status"] == "stable"
        assert result["discharge_ready"] is True
        assert result["who_sign_out_completed"] is True
        assert "Patient meets discharge criteria from PACU" in result["recommendations"]
        mock_tasy_adapter.record_post_op_assessment.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitoring_status(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test monitoring status with intermediate scores."""
        # Arrange
        variables = {
            "surgery_id": "SURG-002",
            "patient_id": "PAT-12346",
            "pacu_bed_id": "PACU-BED-02",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 2,
            "aldrete_respiration": 2,
            "aldrete_circulation": 1,
            "aldrete_consciousness": 2,
            "aldrete_oxygen_saturation": 1,
            "pain_score": 3,
            "temperature": 36.5,
            "complications": [],
            "who_checklist_phase": "sign_out",
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["aldrete_total_score"] == 8
        assert result["recovery_status"] == "monitoring"
        assert result["discharge_ready"] is False
        assert any("Continue close observation" in rec for rec in result["recommendations"])
        assert any("Reassess in 30 minutes" in rec for rec in result["recommendations"])

    @pytest.mark.asyncio
    async def test_critical_status(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test critical status with low scores."""
        # Arrange
        variables = {
            "surgery_id": "SURG-003",
            "patient_id": "PAT-12347",
            "pacu_bed_id": "PACU-BED-03",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 1,
            "aldrete_respiration": 1,
            "aldrete_circulation": 1,
            "aldrete_consciousness": 1,
            "aldrete_oxygen_saturation": 1,
            "pain_score": 8,
            "temperature": 35.5,
            "complications": ["respiratory distress"],
            "who_checklist_phase": "sign_out",
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["aldrete_total_score"] == 5
        assert result["recovery_status"] == "critical"
        assert result["discharge_ready"] is False
        assert any("Immediate clinical review required" in rec for rec in result["recommendations"])
        assert any("Consider ICU transfer" in rec for rec in result["recommendations"])
        assert any("respiratory" in rec.lower() for rec in result["recommendations"])

    @pytest.mark.asyncio
    async def test_complications_prevent_discharge(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test that complications prevent discharge even with good scores."""
        # Arrange
        variables = {
            "surgery_id": "SURG-004",
            "patient_id": "PAT-12348",
            "pacu_bed_id": "PACU-BED-04",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 2,
            "aldrete_respiration": 2,
            "aldrete_circulation": 2,
            "aldrete_consciousness": 2,
            "aldrete_oxygen_saturation": 2,
            "pain_score": 2,
            "temperature": 36.8,
            "complications": ["nausea"],
            "who_checklist_phase": "sign_out",
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["aldrete_total_score"] == 10
        assert result["recovery_status"] == "stable"
        assert result["discharge_ready"] is False
        assert any("Active complications" in rec for rec in result["recommendations"])
        assert any("antiemetic" in rec.lower() for rec in result["recommendations"])

    @pytest.mark.asyncio
    async def test_high_pain_prevents_discharge(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test that high pain prevents discharge."""
        # Arrange
        variables = {
            "surgery_id": "SURG-005",
            "patient_id": "PAT-12349",
            "pacu_bed_id": "PACU-BED-05",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 2,
            "aldrete_respiration": 2,
            "aldrete_circulation": 2,
            "aldrete_consciousness": 2,
            "aldrete_oxygen_saturation": 2,
            "pain_score": 7,
            "temperature": 36.8,
            "complications": [],
            "who_checklist_phase": "sign_out",
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["aldrete_total_score"] == 10
        assert result["recovery_status"] == "stable"
        assert result["discharge_ready"] is False
        assert any("Pain score 7/10" in rec for rec in result["recommendations"])
        assert any("additional analgesia" in rec.lower() for rec in result["recommendations"])

    @pytest.mark.asyncio
    async def test_invalid_aldrete_score_raises(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test that invalid Aldrete score raises validation error."""
        # Arrange
        variables = {
            "surgery_id": "SURG-006",
            "patient_id": "PAT-12350",
            "pacu_bed_id": "PACU-BED-06",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 3,  # Invalid: must be 0-2
            "aldrete_respiration": 2,
            "aldrete_circulation": 2,
            "aldrete_consciousness": 2,
            "aldrete_oxygen_saturation": 2,
            "pain_score": 2,
            "temperature": 36.8,
            "complications": [],
            "who_checklist_phase": "sign_out",
        }

        # Act & Assert
        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(variables)

        assert "Invalid post-operative recovery data" in str(exc_info.value)
        assert exc_info.value.bpmn_error_code == "SURGICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_who_sign_out_phase(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test WHO Sign Out phase defaults and completion."""
        # Arrange
        variables = {
            "surgery_id": "SURG-007",
            "patient_id": "PAT-12351",
            "pacu_bed_id": "PACU-BED-07",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 2,
            "aldrete_respiration": 2,
            "aldrete_circulation": 2,
            "aldrete_consciousness": 2,
            "aldrete_oxygen_saturation": 2,
            "pain_score": 2,
            "temperature": 36.8,
            "complications": [],
            # who_checklist_phase defaults to "sign_out"
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["who_sign_out_completed"] is True

    @pytest.mark.asyncio
    async def test_recommendations_generated(
        self,
        worker: PostOpRecoveryWorker,
        mock_tasy_adapter: AsyncMock,
    ) -> None:
        """Test that recommendations are generated based on assessment."""
        # Arrange
        variables = {
            "surgery_id": "SURG-008",
            "patient_id": "PAT-12352",
            "pacu_bed_id": "PACU-BED-08",
            "admission_time": datetime.now(timezone.utc),
            "aldrete_activity": 0,
            "aldrete_respiration": 1,
            "aldrete_circulation": 1,
            "aldrete_consciousness": 1,
            "aldrete_oxygen_saturation": 0,
            "pain_score": 9,
            "temperature": 35.0,
            "complications": ["bleeding", "nausea"],
            "who_checklist_phase": "sign_out",
        }

        # Act
        result = await worker.execute(variables)

        # Assert
        assert result["recovery_status"] == "critical"
        recommendations = result["recommendations"]
        assert len(recommendations) > 0

        # Check for critical status recommendations
        assert any("Immediate clinical review" in rec for rec in recommendations)

        # Check for hypothermia
        assert any("Hypothermia" in rec for rec in recommendations)
        assert any("warming measures" in rec for rec in recommendations)

        # Check for high pain
        assert any("Pain score 9/10" in rec for rec in recommendations)

        # Check for complications
        assert any("Active complications" in rec for rec in recommendations)
        assert any("surgical site" in rec.lower() for rec in recommendations)
        assert any("antiemetic" in rec.lower() for rec in recommendations)
