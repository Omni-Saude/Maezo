"""Tests for TrackProcessPerformanceWorker."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.track_process_performance_worker import (
    TrackProcessPerformanceInput,
    TrackProcessPerformanceOutput,
    TrackProcessPerformanceStub,
    ProcessPerformanceException,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def worker():
    """Create worker instance."""
    return TrackProcessPerformanceStub()


@pytest.mark.unit
class TestTrackProcessPerformanceWorker:
    """Test suite for TrackProcessPerformanceWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful process performance tracking."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
            include_active_instances=False,
            calculate_bottlenecks=True,
            sla_threshold_hours=24.0,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, TrackProcessPerformanceOutput)
        assert result.process_definition_key == "revenue_cycle"
        assert result.total_instances >= 0
        assert result.avg_cycle_time_seconds >= 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            TrackProcessPerformanceInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_different_process_keys(self, worker, tenant_austa):
        """Test tracking different process types."""
        process_keys = ["revenue_cycle", "clinical_admission", "claims_processing"]

        for process_key in process_keys:
            input_data = TrackProcessPerformanceInput(
                process_definition_key=process_key,
                date_start=datetime.now() - timedelta(days=7),
                date_end=datetime.now(),
            )

            result = await worker.execute(input_data)

            assert result.process_definition_key == process_key

    @pytest.mark.asyncio
    async def test_include_active_instances(self, worker, tenant_austa):
        """Test including active (non-completed) instances."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
            include_active_instances=True,
        )

        result = await worker.execute(input_data)

        # Should include active instances
        assert result.total_instances >= result.completed_instances

    @pytest.mark.asyncio
    async def test_exclude_active_instances(self, worker, tenant_austa):
        """Test excluding active instances."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
            include_active_instances=False,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, TrackProcessPerformanceOutput)

    @pytest.mark.asyncio
    async def test_bottleneck_detection(self, worker, tenant_austa):
        """Test bottleneck detection."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
            calculate_bottlenecks=True,
        )

        result = await worker.execute(input_data)

        # Should have bottlenecks list
        assert isinstance(result.bottlenecks, list)

    @pytest.mark.asyncio
    async def test_skip_bottleneck_detection(self, worker, tenant_austa):
        """Test skipping bottleneck detection."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
            calculate_bottlenecks=False,
        )

        result = await worker.execute(input_data)

        # Should have empty bottlenecks list
        assert result.bottlenecks == []

    @pytest.mark.asyncio
    async def test_sla_compliance_calculated(self, worker, tenant_austa):
        """Test SLA compliance calculation."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
            sla_threshold_hours=24.0,
        )

        result = await worker.execute(input_data)

        # Should have SLA compliance rate
        assert result.sla_compliance_rate >= 0.0
        assert result.sla_compliance_rate <= 100.0

    @pytest.mark.asyncio
    async def test_different_sla_thresholds(self, worker, tenant_austa):
        """Test different SLA thresholds."""
        for threshold in [12.0, 24.0, 48.0]:
            input_data = TrackProcessPerformanceInput(
                process_definition_key="revenue_cycle",
                date_start=datetime.now() - timedelta(days=7),
                date_end=datetime.now(),
                sla_threshold_hours=threshold,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, TrackProcessPerformanceOutput)

    @pytest.mark.asyncio
    async def test_throughput_calculated(self, worker, tenant_austa):
        """Test throughput calculation."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
        )

        result = await worker.execute(input_data)

        # Should have throughput per hour
        assert result.throughput_per_hour >= 0.0

    @pytest.mark.asyncio
    async def test_activities_performance_tracked(self, worker, tenant_austa):
        """Test that individual activities performance is tracked."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
        )

        result = await worker.execute(input_data)

        # Should have activities performance data
        assert isinstance(result.activities_performance, list)

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
        )

        result = await worker.execute(input_data)

        assert isinstance(result, TrackProcessPerformanceOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = TrackProcessPerformanceInput(
            process_definition_key="revenue_cycle",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same process key and structure
        assert result1.process_definition_key == result2.process_definition_key
        assert type(result1.activities_performance) == type(result2.activities_performance)
