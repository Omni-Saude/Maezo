from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker import ArchiveReconciliationWorker


@pytest.mark.asyncio
class TestArchiveReconciliationWorker:
    """Tests for ArchiveReconciliationWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.FederatedDMNService')
    async def test_archive_reconciliation_success(self, MockDMNService, mock_tenant):
        """Test successful archiving of reconciliations."""
        mock_dmn = MockDMNService.return_value
        cutoff = date.today() - timedelta(days=365)
        mock_dmn.evaluate.return_value = {
            'archivedCount': 5,
            'eligibleCount': 5,
            'cutoffDate': cutoff.isoformat(),
            'archivedIds': ['rec-1', 'rec-2', 'rec-3', 'rec-4', 'rec-5'],
            'archivedAt': '2024-01-01T00:00:00Z'
        }

        worker = ArchiveReconciliationWorker()
        job = MagicMock()
        job.variables = {
            "retention_days": 365,
            "dry_run": False,
            "batch_size": 100,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["archived_count"] > 0
        assert result.variables["eligible_count"] > 0
        assert result.variables["retention_days"] == 365
        assert result.variables["dry_run"] is False
        assert len(result.variables["archived_ids"]) > 0

    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.FederatedDMNService')
    async def test_archive_reconciliation_dry_run(self, MockDMNService, mock_tenant):
        """Test dry run mode (list without archiving)."""
        mock_dmn = MockDMNService.return_value
        cutoff = date.today() - timedelta(days=365)
        mock_dmn.evaluate.return_value = {
            'archivedCount': 3,
            'eligibleCount': 3,
            'cutoffDate': cutoff.isoformat(),
            'archivedIds': ['rec-1', 'rec-2', 'rec-3'],
            'archivedAt': ''
        }

        worker = ArchiveReconciliationWorker()
        job = MagicMock()
        job.variables = {
            "retention_days": 365,
            "dry_run": True,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["archived_count"] == 0  # No actual archiving in dry run
        assert result.variables["eligible_count"] > 0
        assert result.variables["dry_run"] is True
        assert len(result.variables["archived_ids"]) > 0  # But IDs are listed

    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.FederatedDMNService')
    async def test_archive_reconciliation_cutoff_date(self, MockDMNService, mock_tenant):
        """Test that cutoff date is calculated correctly."""
        retention_days = 180
        expected_cutoff = date.today() - timedelta(days=retention_days)

        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'archivedCount': 2,
            'eligibleCount': 2,
            'cutoffDate': expected_cutoff.isoformat(),
            'archivedIds': ['rec-1', 'rec-2'],
            'archivedAt': '2024-01-01T00:00:00Z'
        }

        worker = ArchiveReconciliationWorker()
        job = MagicMock()
        job.variables = {
            "retention_days": retention_days,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["cutoff_date"] == expected_cutoff.isoformat()

    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.archive_reconciliation_worker.FederatedDMNService')
    async def test_archive_reconciliation_custom_batch_size(self, MockDMNService, mock_tenant):
        """Test archiving with custom batch size."""
        mock_dmn = MockDMNService.return_value
        cutoff = date.today() - timedelta(days=365)
        mock_dmn.evaluate.return_value = {
            'archivedCount': 3,
            'eligibleCount': 3,
            'cutoffDate': cutoff.isoformat(),
            'archivedIds': ['rec-1', 'rec-2', 'rec-3'],
            'archivedAt': '2024-01-01T00:00:00Z'
        }

        worker = ArchiveReconciliationWorker()
        job = MagicMock()
        job.variables = {
            "retention_days": 365,
            "dry_run": False,
            "batch_size": 5,
        }

        result = await worker.execute(job)

        assert result.success
        # Should still process all eligible records regardless of batch size
        assert result.variables["archived_count"] == result.variables["eligible_count"]
