"""Tests for UpdateBiDatawarehouseWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker import (
    UpdateBiDatawarehouseWorker,
)


@pytest.mark.asyncio
async def test_update_bi_datawarehouse_success():
    """Test successful BI data warehouse export."""
    worker = UpdateBiDatawarehouseWorker()

    task_variables = {
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

    result = await worker.execute(task_variables)

    assert result["total_records"] == 2
    assert len(result["fact_records"]) == 2

    # Check dimension date
    dim_date = result["dim_date"]
    assert dim_date["date_key"] == "20240131"
    assert dim_date["year"] == 2024
    assert dim_date["month"] == 1
    assert dim_date["day"] == 31

    # Check fact records
    fact1 = result["fact_records"][0]
    assert fact1["payer_key"] == "payer-1"
    assert fact1["facility_key"] == "facility-1"
    assert fact1["amount_billed"] == 100000.0
    assert fact1["amount_collected"] == 85000.0
    assert fact1["amount_outstanding"] == 10000.0  # billed - collected - denied
    assert fact1["collection_rate"] == 85.0


@pytest.mark.asyncio
async def test_update_bi_datawarehouse_date_dimensions():
    """Test date dimension calculation."""
    worker = UpdateBiDatawarehouseWorker()

    task_variables = {
        "date": "2024-03-15T00:00:00Z",
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

    result = await worker.execute(task_variables)

    dim_date = result["dim_date"]
    assert dim_date["year"] == 2024
    assert dim_date["quarter"] == 1  # Q1
    assert dim_date["month"] == 3
    assert dim_date["day"] == 15
    assert dim_date["day_of_week"] == 5  # Friday


@pytest.mark.asyncio
async def test_update_bi_datawarehouse_zero_collection():
    """Test handling of zero collection rate."""
    worker = UpdateBiDatawarehouseWorker()

    task_variables = {
        "date": "2024-01-31T00:00:00Z",
        "facility_id": "facility-1",
        "metrics_by_payer": [
            {
                "payer_id": "payer-1",
                "amount_billed": 0.0,  # Zero billed
                "amount_collected": 0.0,
                "amount_denied": 0.0,
                "claim_count": 0,
                "payment_count": 0,
                "denial_count": 0,
                "avg_days_to_payment": 0.0,
            }
        ],
    }

    result = await worker.execute(task_variables)

    fact = result["fact_records"][0]
    assert fact["collection_rate"] == 0.0
    assert fact["amount_outstanding"] == 0.0


@pytest.mark.asyncio
async def test_update_bi_datawarehouse_export_timestamp():
    """Test that export timestamp is included."""
    worker = UpdateBiDatawarehouseWorker()

    task_variables = {
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

    result = await worker.execute(task_variables)

    assert "export_timestamp" in result
    assert result["export_timestamp"].endswith("Z") or "T" in result["export_timestamp"]
