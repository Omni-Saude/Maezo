from __future__ import annotations

from datetime import date

import pytest

from platform.revenue_cycle.collection.workers.predict_collection_date_worker import PredictCollectionDateWorker


@pytest.mark.asyncio
class TestPredictCollectionDateWorker:
    """Tests for PredictCollectionDateWorker."""

    async def test_predict_collection_date_with_ml(self):
        """Test prediction with sufficient historical data for ML."""
        worker = PredictCollectionDateWorker()

        task_variables = {
            "claim_id": "CLAIM-001",
            "payer_id": "PAYER-001",
            "claim_amount": 35000.00,
            "claim_date": date.today().isoformat(),
            "claim_type": "standard",
        }

        result = await worker.execute(task_variables)

        assert result["claim_id"] == "CLAIM-001"
        assert result["payer_id"] == "PAYER-001"
        assert result["predicted_collection_date"] is not None
        assert 30 <= result["predicted_days"] <= 180
        assert 0 <= result["confidence"] <= 1
        assert result["model_type"] == "linear_regression"
        assert result["historical_samples"] >= 3

    async def test_predict_collection_date_insufficient_data(self):
        """Test prediction with insufficient historical data."""
        worker = PredictCollectionDateWorker()

        task_variables = {
            "claim_id": "CLAIM-002",
            "payer_id": "PAYER-002",
            "claim_amount": 50000.00,
            "claim_date": date.today().isoformat(),
            "historical_data": [
                {"days": 45, "amount": 30000.00},
            ],  # Only 1 sample
        }

        result = await worker.execute(task_variables)

        assert result["model_type"] == "average"
        assert result["confidence"] == 0.5

    async def test_predict_collection_date_days_bounded(self):
        """Test that predicted days are bounded to reasonable range."""
        worker = PredictCollectionDateWorker()

        task_variables = {
            "claim_id": "CLAIM-003",
            "payer_id": "PAYER-003",
            "claim_amount": 100000.00,  # Very high amount
            "claim_date": date.today().isoformat(),
        }

        result = await worker.execute(task_variables)

        # Should be bounded between 30-180 days
        assert 30 <= result["predicted_days"] <= 180
