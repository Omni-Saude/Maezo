from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker import (
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
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker.FederatedDMNService')
    async def test_aging_bucket_calculation(self, MockDMNService, mock_tenant, days_overdue: int, expected_bucket: AgingBucket):
        """Testa cálculo correto de bucket de aging para diferentes períodos."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'agingBucket': expected_bucket.value,
            'bucketDescription': f'{expected_bucket.value} dias'
        }

        worker = CalculateAgingBucketWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "days_overdue": days_overdue,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["aging_bucket"] == expected_bucket.value
        assert result.variables["days_overdue"] == days_overdue
        assert result.variables["collection_case_id"] == "CC-12345"
        assert "bucket_description" in result.variables

    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker.FederatedDMNService')
    async def test_bucket_description_in_portuguese(self, MockDMNService, mock_tenant):
        """Testa que descrição do bucket está em português."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'agingBucket': 'DAYS_31_60',
            'bucketDescription': '31-60 dias'
        }

        worker = CalculateAgingBucketWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "days_overdue": 45,
        }

        result = await worker.execute(job)

        assert result.success
        assert "dias" in result.variables["bucket_description"]

    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker.FederatedDMNService')
    async def test_edge_case_zero_days(self, MockDMNService, mock_tenant):
        """Testa caso limite de zero dias vencidos."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'agingBucket': AgingBucket.DAYS_0_30.value,
            'bucketDescription': '0-30 dias'
        }

        worker = CalculateAgingBucketWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "days_overdue": 0,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["aging_bucket"] == AgingBucket.DAYS_0_30.value
