from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.revenue_cycle.collection.workers.generate_aging_report_worker import GenerateAgingReportWorker


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_aging_report_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_aging_report_worker.FederatedDMNService")
class TestGenerateAgingReportWorker:
    """Tests for GenerateAgingReportWorker."""

    async def test_generate_aging_report_success(self, mock_dmn_service_cls, mock_tenant):
        """Test successful aging report generation."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {}
        mock_dmn_service_cls.return_value = mock_dmn

        worker = GenerateAgingReportWorker()
        job = MagicMock()
        job.variables = {
            "as_of_date": date.today().isoformat(),
            "include_closed": False,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["report_date"] == date.today().isoformat()
        assert result.variables["total_ar"] > 0
        assert result.variables["total_claims"] > 0
        assert "aging_buckets" in result.variables

        # Verify all aging buckets are present
        buckets = result.variables["aging_buckets"]
        assert AgingBucket.CURRENT.value in buckets
        assert AgingBucket.DAYS_30.value in buckets
        assert AgingBucket.DAYS_60.value in buckets
        assert AgingBucket.DAYS_90.value in buckets
        assert AgingBucket.DAYS_120.value in buckets
        assert AgingBucket.DAYS_180.value in buckets
        assert AgingBucket.OVER_180.value in buckets

        # Verify each bucket has required fields
        for bucket_data in buckets.values():
            assert "amount" in bucket_data
            assert "count" in bucket_data
            assert "percentage" in bucket_data

    async def test_generate_aging_report_default_date(self, mock_dmn_service_cls, mock_tenant):
        """Test report generation with default date."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {}
        mock_dmn_service_cls.return_value = mock_dmn

        worker = GenerateAgingReportWorker()
        job = MagicMock()
        job.variables = {}

        result = await worker.execute(job)

        assert result.success
        assert result.variables["report_date"] == date.today().isoformat()
        assert result.variables["include_closed"] is False

    async def test_generate_aging_report_percentages_sum_to_100(self, mock_dmn_service_cls, mock_tenant):
        """Test that bucket percentages approximately sum to 100%."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {}
        mock_dmn_service_cls.return_value = mock_dmn

        worker = GenerateAgingReportWorker()
        job = MagicMock()
        job.variables = {}

        result = await worker.execute(job)

        assert result.success
        total_percentage = sum(
            bucket["percentage"] for bucket in result.variables["aging_buckets"].values()
        )

        # Allow small floating point variance
        assert 99.0 <= total_percentage <= 101.0
