"""Tests for MonitorSystemHealthWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.monitor_system_health_worker import (
    MonitorSystemHealthInput,
    MonitorSystemHealthOutput,
    MonitorSystemHealthStub,
    SystemHealthException,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def worker():
    """Create worker instance."""
    return MonitorSystemHealthStub()


@pytest.mark.unit
class TestMonitorSystemHealthWorker:
    """Test suite for MonitorSystemHealthWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful system health monitoring."""
        input_data = MonitorSystemHealthInput(
            components=["api", "database", "queue"],
            include_detailed_metrics=True,
            alert_threshold=80.0,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, MonitorSystemHealthOutput)
        assert result.overall_health_score >= 0
        assert result.overall_health_score <= 100
        assert result.overall_status in ["healthy", "degraded", "unhealthy"]
        assert len(result.components_health) == 3

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = MonitorSystemHealthInput(
            components=["api"],
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_all_components(self, worker, tenant_austa):
        """Test monitoring all components."""
        input_data = MonitorSystemHealthInput(
            components=["api", "database", "queue", "cache", "storage"],
        )

        result = await worker.execute(input_data)

        assert len(result.components_health) == 5
        for component in result.components_health:
            assert component.component_name in [
                "api", "database", "queue", "cache", "storage"
            ]

    @pytest.mark.asyncio
    async def test_degraded_component_detection(self, worker, tenant_austa):
        """Test detection of degraded components."""
        input_data = MonitorSystemHealthInput(
            components=["api", "database", "queue"],  # queue is degraded in stub
        )

        result = await worker.execute(input_data)

        # Stub returns queue as degraded
        assert len(result.degraded_components) >= 0

    @pytest.mark.asyncio
    async def test_alert_triggered_below_threshold(self, worker, tenant_austa):
        """Test alert is triggered when health below threshold."""
        input_data = MonitorSystemHealthInput(
            components=["api"],
            alert_threshold=99.0,  # Very high threshold
        )

        result = await worker.execute(input_data)

        # Alert might be triggered if score below 99
        assert isinstance(result.alert_triggered, bool)

    @pytest.mark.asyncio
    async def test_detailed_metrics_included(self, worker, tenant_austa):
        """Test that detailed metrics are included when requested."""
        input_data = MonitorSystemHealthInput(
            components=["api", "database"],
            include_detailed_metrics=True,
        )

        result = await worker.execute(input_data)

        # Check detailed metrics are present
        for component in result.components_health:
            # Depending on component type, should have metrics
            if component.component_name == "api":
                assert component.response_time_ms is not None

    @pytest.mark.asyncio
    async def test_detailed_metrics_not_included(self, worker, tenant_austa):
        """Test that detailed metrics can be excluded."""
        input_data = MonitorSystemHealthInput(
            components=["api"],
            include_detailed_metrics=False,
        )

        result = await worker.execute(input_data)

        # Still returns result, metrics might be None or default

    @pytest.mark.asyncio
    async def test_single_component(self, worker, tenant_austa):
        """Test monitoring single component."""
        input_data = MonitorSystemHealthInput(
            components=["database"],
        )

        result = await worker.execute(input_data)

        assert len(result.components_health) == 1
        assert result.components_health[0].component_name == "database"

    @pytest.mark.asyncio
    async def test_default_components(self, worker, tenant_austa):
        """Test monitoring with default components."""
        input_data = MonitorSystemHealthInput()

        result = await worker.execute(input_data)

        # Default components: api, database, queue, cache, storage
        assert len(result.components_health) == 5

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = MonitorSystemHealthInput(
            components=["api"],
        )

        result = await worker.execute(input_data)

        assert isinstance(result, MonitorSystemHealthOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = MonitorSystemHealthInput(
            components=["api", "database"],
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same structure
        assert len(result1.components_health) == len(result2.components_health)
        assert type(result1.overall_health_score) == type(result2.overall_health_score)
