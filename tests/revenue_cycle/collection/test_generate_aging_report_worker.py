from __future__ import annotations

from datetime import date

import pytest

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.revenue_cycle.collection.workers.generate_aging_report_worker import GenerateAgingReportWorker


@pytest.mark.asyncio
class TestGenerateAgingReportWorker:
    """Tests for GenerateAgingReportWorker."""

    async def test_generate_aging_report_success(self):
        """Test successful aging report generation."""
        worker = GenerateAgingReportWorker()

        task_variables = {
            "as_of_date": date.today().isoformat(),
            "include_closed": False,
        }

        result = await worker.execute(task_variables)

        assert result["report_date"] == date.today().isoformat()
        assert result["total_ar"] > 0
        assert result["total_claims"] > 0
        assert "aging_buckets" in result

        # Verify all aging buckets are present
        buckets = result["aging_buckets"]
        assert "current" in buckets
        assert "30_days" in buckets
        assert "60_days" in buckets
        assert "90_days" in buckets
        assert "120_days" in buckets
        assert "180_days" in buckets
        assert "over_180_days" in buckets

        # Verify each bucket has required fields
        for bucket_data in buckets.values():
            assert "amount" in bucket_data
            assert "count" in bucket_data
            assert "percentage" in bucket_data

    async def test_generate_aging_report_default_date(self):
        """Test report generation with default date."""
        worker = GenerateAgingReportWorker()

        task_variables = {}

        result = await worker.execute(task_variables)

        assert result["report_date"] == date.today().isoformat()
        assert result["include_closed"] is False

    async def test_generate_aging_report_percentages_sum_to_100(self):
        """Test that bucket percentages approximately sum to 100%."""
        worker = GenerateAgingReportWorker()

        task_variables = {}

        result = await worker.execute(task_variables)

        total_percentage = sum(
            bucket["percentage"] for bucket in result["aging_buckets"].values()
        )

        # Allow small floating point variance
        assert 99.0 <= total_percentage <= 101.0
