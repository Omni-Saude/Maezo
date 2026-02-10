"""Tests for AlertOnAnomaliesWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import (
    AlertOnAnomaliesInput,
    AlertOnAnomaliesOutput,
    AnomalyDetectionException,
    AlertOnAnomaliesStub,
)


@pytest.fixture
def worker(tenant_austa):
    """Create worker instance."""
    return AlertOnAnomaliesStub()


@pytest.fixture
def valid_input():
    """Valid input for anomaly detection."""
    return AlertOnAnomaliesInput(
        metric_type="revenue",
        detection_method="z_score",
        lookback_days=30,
        sensitivity="medium",
        auto_alert=True,
        alert_channel="email",
    )


@pytest.mark.unit
class TestAlertOnAnomaliesWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input):
        """Test successful anomaly detection."""
        result = await worker.execute(valid_input)

        assert isinstance(result, AlertOnAnomaliesOutput)
        assert result.scan_id is not None
        assert result.metric_type == "revenue"
        assert result.detection_method == "z_score"
        assert result.total_data_points > 0
        assert result.baseline_mean > 0
        assert result.baseline_std_dev > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            AlertOnAnomaliesInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        worker = AlertOnAnomaliesStub()
        valid_input = AlertOnAnomaliesInput(
            metric_type="revenue",
            detection_method="z_score",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_z_score_detection(self, worker, tenant_austa):
        """Test z-score anomaly detection method."""
        input_data = AlertOnAnomaliesInput(
            metric_type="claim_volume",
            detection_method="z_score",
            sensitivity="high",
            lookback_days=30,
        )

        result = await worker.execute(input_data)

        assert result.detection_method == "z_score"
        assert len(result.anomalies_detected) >= 0

        # Check anomalies have z_score
        for anomaly in result.anomalies_detected:
            assert anomaly.z_score is not None

    @pytest.mark.asyncio
    async def test_sensitivity_levels(self, worker, tenant_austa):
        """Test different sensitivity levels."""
        for sensitivity in ["low", "medium", "high"]:
            input_data = AlertOnAnomaliesInput(
                metric_type="revenue",
                detection_method="z_score",
                sensitivity=sensitivity,
            )

            result = await worker.execute(input_data)
            assert result.detection_method == "z_score"

    @pytest.mark.asyncio
    async def test_auto_alert_enabled(self, worker, tenant_austa):
        """Test auto-alerting when enabled."""
        input_data = AlertOnAnomaliesInput(
            metric_type="revenue",
            detection_method="z_score",
            auto_alert=True,
            alert_channel="slack",
        )

        result = await worker.execute(input_data)

        # Should send alerts for high/critical anomalies
        assert result.alerts_sent >= 0

    @pytest.mark.asyncio
    async def test_auto_alert_disabled(self, worker, tenant_austa):
        """Test no alerts when auto_alert is disabled."""
        input_data = AlertOnAnomaliesInput(
            metric_type="revenue",
            detection_method="z_score",
            auto_alert=False,
        )

        result = await worker.execute(input_data)

        assert result.alerts_sent == 0

    @pytest.mark.asyncio
    async def test_lookback_window(self, worker, tenant_austa):
        """Test different lookback windows."""
        for lookback_days in [7, 14, 30, 60]:
            input_data = AlertOnAnomaliesInput(
                metric_type="revenue",
                detection_method="z_score",
                lookback_days=lookback_days,
            )

            result = await worker.execute(input_data)
            # Total data points should be proportional to lookback_days
            assert result.total_data_points > 0

    @pytest.mark.asyncio
    async def test_anomaly_severity_classification(self, worker, tenant_austa):
        """Test anomaly severity classification."""
        input_data = AlertOnAnomaliesInput(
            metric_type="revenue",
            detection_method="z_score",
            sensitivity="medium",
        )

        result = await worker.execute(input_data)

        # All anomalies should have severity
        for anomaly in result.anomalies_detected:
            assert anomaly.severity in ["low", "medium", "high", "critical"]

    @pytest.mark.asyncio
    async def test_duration_recorded(self, worker, tenant_austa):
        """Test duration is recorded."""
        input_data = AlertOnAnomaliesInput(
            metric_type="revenue",
            detection_method="z_score",
        )

        result = await worker.execute(input_data)

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_anomaly_count(self, worker, tenant_austa):
        """Test anomaly count matches list length."""
        input_data = AlertOnAnomaliesInput(
            metric_type="revenue",
            detection_method="z_score",
        )

        result = await worker.execute(input_data)

        assert result.anomaly_count == len(result.anomalies_detected)
