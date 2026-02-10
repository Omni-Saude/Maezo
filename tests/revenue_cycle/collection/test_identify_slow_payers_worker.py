from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.identify_slow_payers_worker import IdentifySlowPayersWorker


@pytest.mark.asyncio
class TestIdentifySlowPayersWorker:
    """Tests for IdentifySlowPayersWorker."""

    async def test_identify_slow_payers_success(self):
        """Test successful identification of slow payers."""
        worker = IdentifySlowPayersWorker()

        task_variables = {
            "lookback_days": 90,
            "min_payments": 5,
            "threshold_days": 60,
        }

        result = await worker.execute(task_variables)

        assert "slow_payers" in result
        assert result["analyzed_payers"] > 0
        assert result["total_payments"] > 0
        assert result["lookback_days"] == 90
        assert result["threshold_days"] == 60

        # Verify slow payers are sorted by slowest first
        if len(result["slow_payers"]) > 1:
            for i in range(len(result["slow_payers"]) - 1):
                assert (
                    result["slow_payers"][i]["avg_days_to_payment"]
                    >= result["slow_payers"][i + 1]["avg_days_to_payment"]
                )

    async def test_identify_slow_payers_filters_by_threshold(self):
        """Test that only payers above threshold are included."""
        worker = IdentifySlowPayersWorker()

        task_variables = {
            "threshold_days": 100,  # High threshold
            "min_payments": 5,
        }

        result = await worker.execute(task_variables)

        # With mocked data, no payers should exceed 100 days
        for payer in result["slow_payers"]:
            assert payer["avg_days_to_payment"] >= 100

    async def test_identify_slow_payers_structure(self):
        """Test structure of slow payer data."""
        worker = IdentifySlowPayersWorker()

        task_variables = {}

        result = await worker.execute(task_variables)

        if result["slow_payers"]:
            payer = result["slow_payers"][0]
            assert "payer_id" in payer
            assert "payer_name" in payer
            assert "avg_days_to_payment" in payer
            assert "payment_count" in payer
            assert "total_amount" in payer
            assert "variance" in payer
