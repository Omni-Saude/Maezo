from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.enums import AgingBucket
from platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker import (
    CalculateAgingBucketWorker,
)


@pytest.mark.asyncio
class TestCalculateAgingBucketWorker:
    """Testes para CalculateAgingBucketWorker."""

    @pytest.mark.parametrize(
        "days_overdue,expected_bucket",
        [
            (15, AgingBucket.DAYS_0_30),
            (30, AgingBucket.DAYS_0_30),
            (31, AgingBucket.DAYS_31_60),
            (45, AgingBucket.DAYS_31_60),
            (60, AgingBucket.DAYS_31_60),
            (61, AgingBucket.DAYS_61_90),
            (75, AgingBucket.DAYS_61_90),
            (90, AgingBucket.DAYS_61_90),
            (91, AgingBucket.DAYS_91_120),
            (105, AgingBucket.DAYS_91_120),
            (120, AgingBucket.DAYS_91_120),
            (121, AgingBucket.DAYS_121_180),
            (150, AgingBucket.DAYS_121_180),
            (180, AgingBucket.DAYS_121_180),
            (181, AgingBucket.DAYS_180_PLUS),
            (365, AgingBucket.DAYS_180_PLUS),
        ],
    )
    async def test_aging_bucket_calculation(self, days_overdue: int, expected_bucket: AgingBucket):
        """Testa cálculo correto de bucket de aging para diferentes períodos."""
        worker = CalculateAgingBucketWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "days_overdue": days_overdue,
        }

        result = await worker.execute(task_vars)

        assert result["aging_bucket"] == expected_bucket.value
        assert result["days_overdue"] == days_overdue
        assert result["collection_case_id"] == "CC-12345"
        assert "bucket_description" in result

    async def test_bucket_description_in_portuguese(self):
        """Testa que descrição do bucket está em português."""
        worker = CalculateAgingBucketWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "days_overdue": 45,
        }

        result = await worker.execute(task_vars)

        assert "dias" in result["bucket_description"]

    async def test_edge_case_zero_days(self):
        """Testa caso limite de zero dias vencidos."""
        worker = CalculateAgingBucketWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "days_overdue": 0,
        }

        result = await worker.execute(task_vars)

        assert result["aging_bucket"] == AgingBucket.DAYS_0_30.value
