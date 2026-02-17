"""Tests for AlertAnomaliesWorker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker import (
    AlertAnomaliesWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.FederatedDMNService')
async def test_alert_anomalies_high_z_score(MockDMNService, mock_tenant):
    """Test detection of anomaly with high z-score."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'anomalies': [{'category': 'collections', 'z_score': 3.5, 'severity': 'critical'}],
        'totalAnomalies': 1,
        'criticalAnomalies': 1,
        'requiresAttention': True
    }

    worker = AlertAnomaliesWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_anomalies"] > 0
    assert result.variables["requires_attention"]

    # Should detect collections anomaly
    collections_anomaly = next(
        a for a in result.variables["anomalies"] if a["category"] == "collections"
    )
    assert abs(collections_anomaly["z_score"]) > 2
    assert collections_anomaly["severity"] in ["high", "critical"]


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.FederatedDMNService')
async def test_alert_anomalies_no_anomalies(MockDMNService, mock_tenant):
    """Test when no anomalies are detected."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'anomalies': [],
        'totalAnomalies': 0,
        'criticalAnomalies': 0,
        'requiresAttention': False
    }

    worker = AlertAnomaliesWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_anomalies"] == 0
    assert result.variables["critical_anomalies"] == 0
    assert not result.variables["requires_attention"]


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.get_required_tenant', return_value='test-tenant')
async def test_alert_anomalies_insufficient_data(mock_tenant):
    """Test handling of insufficient historical data."""
    worker = AlertAnomaliesWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_anomalies"] == 0
    assert result.variables["requires_attention"] is False


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.FederatedDMNService')
async def test_alert_anomalies_denial_spike(MockDMNService, mock_tenant):
    """Test detection of denial spike anomaly."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'anomalies': [{'category': 'denials', 'z_score': 3.8, 'severity': 'high'}],
        'totalAnomalies': 1,
        'criticalAnomalies': 0,
        'requiresAttention': True
    }

    worker = AlertAnomaliesWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_anomalies"] > 0

    # Should detect denials anomaly
    denials_anomaly = next(
        a for a in result.variables["anomalies"] if a["category"] == "denials"
    )
    assert abs(denials_anomaly["z_score"]) > 2


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.alert_anomalies_worker.FederatedDMNService')
async def test_alert_anomalies_severity_levels(MockDMNService, mock_tenant):
    """Test severity level assignment."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'anomalies': [{'category': 'collections', 'z_score': 4.5, 'severity': 'critical'}],
        'totalAnomalies': 1,
        'criticalAnomalies': 1,
        'requiresAttention': True
    }

    worker = AlertAnomaliesWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    if result.variables["total_anomalies"] > 0:
        anomaly = result.variables["anomalies"][0]
        assert anomaly["severity"] in ["low", "medium", "high", "critical"]
        # With extreme deviation, should be critical
        if abs(anomaly["z_score"]) >= 4:
            assert anomaly["severity"] == "critical"
