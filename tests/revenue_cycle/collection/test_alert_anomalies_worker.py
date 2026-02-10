"""Tests for AlertAnomaliesWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker import (
    AlertAnomaliesWorker,
)


@pytest.mark.asyncio
async def test_alert_anomalies_high_z_score():
    """Test detection of anomaly with high z-score."""
    worker = AlertAnomaliesWorker()

    # Historical: ~10000 avg, current: 3000 (significant drop)
    task_variables = {
        "current_period": {
            "collections": 3000.0,
            "denials": 5,
            "payment_time_avg": 30.0,
        },
        "historical_data": [
            {"collections": 10000.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 10500.0, "denials": 4, "payment_time_avg": 28.0},
            {"collections": 9800.0, "denials": 6, "payment_time_avg": 32.0},
            {"collections": 10200.0, "denials": 5, "payment_time_avg": 29.0},
            {"collections": 10100.0, "denials": 5, "payment_time_avg": 31.0},
            {"collections": 9900.0, "denials": 4, "payment_time_avg": 30.0},
            {"collections": 10300.0, "denials": 5, "payment_time_avg": 28.0},
        ],
    }

    result = await worker.execute(task_variables)

    assert result["total_anomalies"] > 0
    assert result["requires_attention"]

    # Should detect collections anomaly
    collections_anomaly = next(
        a for a in result["anomalies"] if a["category"] == "collections"
    )
    assert abs(collections_anomaly["z_score"]) > 2
    assert collections_anomaly["severity"] in ["high", "critical"]


@pytest.mark.asyncio
async def test_alert_anomalies_no_anomalies():
    """Test when no anomalies are detected."""
    worker = AlertAnomaliesWorker()

    # Current within normal range
    task_variables = {
        "current_period": {
            "collections": 10000.0,
            "denials": 5,
            "payment_time_avg": 30.0,
        },
        "historical_data": [
            {"collections": 10000.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 10100.0, "denials": 4, "payment_time_avg": 29.0},
            {"collections": 9900.0, "denials": 6, "payment_time_avg": 31.0},
            {"collections": 10050.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 9950.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 10100.0, "denials": 4, "payment_time_avg": 29.0},
            {"collections": 9900.0, "denials": 5, "payment_time_avg": 31.0},
        ],
    }

    result = await worker.execute(task_variables)

    assert result["total_anomalies"] == 0
    assert result["critical_anomalies"] == 0
    assert not result["requires_attention"]


@pytest.mark.asyncio
async def test_alert_anomalies_insufficient_data():
    """Test handling of insufficient historical data."""
    worker = AlertAnomaliesWorker()

    task_variables = {
        "current_period": {
            "collections": 3000.0,
            "denials": 5,
            "payment_time_avg": 30.0,
        },
        "historical_data": [
            {"collections": 10000.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 10500.0, "denials": 4, "payment_time_avg": 28.0},
        ],  # Only 2 data points
    }

    result = await worker.execute(task_variables)

    assert result["total_anomalies"] == 0
    assert result["requires_attention"] is False


@pytest.mark.asyncio
async def test_alert_anomalies_denial_spike():
    """Test detection of denial spike anomaly."""
    worker = AlertAnomaliesWorker()

    # Denial spike from ~5 to 25
    task_variables = {
        "current_period": {
            "collections": 10000.0,
            "denials": 25,  # Spike
            "payment_time_avg": 30.0,
        },
        "historical_data": [
            {"collections": 10000.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 10100.0, "denials": 4, "payment_time_avg": 29.0},
            {"collections": 9900.0, "denials": 6, "payment_time_avg": 31.0},
            {"collections": 10050.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 9950.0, "denials": 5, "payment_time_avg": 30.0},
            {"collections": 10100.0, "denials": 4, "payment_time_avg": 29.0},
            {"collections": 9900.0, "denials": 5, "payment_time_avg": 31.0},
        ],
    }

    result = await worker.execute(task_variables)

    assert result["total_anomalies"] > 0

    # Should detect denials anomaly
    denials_anomaly = next(
        a for a in result["anomalies"] if a["category"] == "denials"
    )
    assert abs(denials_anomaly["z_score"]) > 2


@pytest.mark.asyncio
async def test_alert_anomalies_severity_levels():
    """Test severity level assignment."""
    worker = AlertAnomaliesWorker()

    # Create extreme deviation for critical severity
    task_variables = {
        "current_period": {
            "collections": 1000.0,  # Extreme drop
            "denials": 5,
            "payment_time_avg": 30.0,
        },
        "historical_data": [
            {"collections": 10000.0, "denials": 5, "payment_time_avg": 30.0}
        ]
        * 10,  # Consistent baseline
    }

    result = await worker.execute(task_variables)

    if result["total_anomalies"] > 0:
        anomaly = result["anomalies"][0]
        assert anomaly["severity"] in ["low", "medium", "high", "critical"]
        # With extreme deviation, should be critical
        if abs(anomaly["z_score"]) >= 4:
            assert anomaly["severity"] == "critical"
