"""Tests for UpdateBiDatawarehouseWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker import (
    UpdateBiDatawarehouseWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker.FederatedDMNService')
async def test_update_bi_datawarehouse_success(mock_dmn_class, mock_tenant):
    """Test successful BI data warehouse export."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'exportFormat': 'dimensional'
    }

    worker = UpdateBiDatawarehouseWorker()

    job = MagicMock()
    job.variables = {
        "date": "2024-01-31T00:00:00Z",
        "facility_id": "facility-1",
        "metrics_by_payer": [
            {
                "payer_id": "payer-1",
                "amount_billed": 100000.0,
                "amount_collected": 85000.0,
                "amount_denied": 5000.0,
                "claim_count": 100,
                "payment_count": 80,
                "denial_count": 5,
                "avg_days_to_payment": 30.5,
            },
            {
                "payer_id": "payer-2",
                "amount_billed": 50000.0,
                "amount_collected": 45000.0,
                "amount_denied": 2000.0,
                "claim_count": 50,
                "payment_count": 45,
                "denial_count": 2,
                "avg_days_to_payment": 25.0,
            },
        ],
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_records"] == 2
    assert result.variables["export_format"] == "dimensional"
    assert result.variables["status"] == "success"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker.FederatedDMNService')
async def test_update_bi_datawarehouse_export_timestamp(mock_dmn_class, mock_tenant):
    """Test that export timestamp is included."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'exportFormat': 'dimensional'
    }

    worker = UpdateBiDatawarehouseWorker()

    job = MagicMock()
    job.variables = {
        "date": "2024-01-31T00:00:00Z",
        "facility_id": "facility-1",
        "metrics_by_payer": [
            {
                "payer_id": "payer-1",
                "amount_billed": 10000.0,
                "amount_collected": 9000.0,
                "amount_denied": 0.0,
                "claim_count": 10,
                "payment_count": 9,
                "denial_count": 0,
                "avg_days_to_payment": 20.0,
            }
        ],
    }

    result = await worker.execute(job)

    assert result.success
    assert "export_timestamp" in result.variables
    assert "T" in result.variables["export_timestamp"]
