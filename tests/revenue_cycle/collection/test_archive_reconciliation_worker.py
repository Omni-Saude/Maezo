from __future__ import annotations

from datetime import date, timedelta

import pytest

from platform.revenue_cycle.collection.workers.archive_reconciliation_worker import ArchiveReconciliationWorker


@pytest.mark.asyncio
class TestArchiveReconciliationWorker:
    """Tests for ArchiveReconciliationWorker."""

    async def test_archive_reconciliation_success(self):
        """Test successful archiving of reconciliations."""
        worker = ArchiveReconciliationWorker()

        task_variables = {
            "retention_days": 365,
            "dry_run": False,
            "batch_size": 100,
        }

        result = await worker.execute(task_variables)

        assert result["archived_count"] > 0
        assert result["eligible_count"] > 0
        assert result["retention_days"] == 365
        assert result["dry_run"] is False
        assert len(result["archived_ids"]) > 0

    async def test_archive_reconciliation_dry_run(self):
        """Test dry run mode (list without archiving)."""
        worker = ArchiveReconciliationWorker()

        task_variables = {
            "retention_days": 365,
            "dry_run": True,
        }

        result = await worker.execute(task_variables)

        assert result["archived_count"] == 0  # No actual archiving in dry run
        assert result["eligible_count"] > 0
        assert result["dry_run"] is True
        assert len(result["archived_ids"]) > 0  # But IDs are listed

    async def test_archive_reconciliation_cutoff_date(self):
        """Test that cutoff date is calculated correctly."""
        worker = ArchiveReconciliationWorker()

        retention_days = 180
        expected_cutoff = date.today() - timedelta(days=retention_days)

        task_variables = {
            "retention_days": retention_days,
        }

        result = await worker.execute(task_variables)

        assert result["cutoff_date"] == expected_cutoff.isoformat()

    async def test_archive_reconciliation_custom_batch_size(self):
        """Test archiving with custom batch size."""
        worker = ArchiveReconciliationWorker()

        task_variables = {
            "retention_days": 365,
            "dry_run": False,
            "batch_size": 5,
        }

        result = await worker.execute(task_variables)

        # Should still process all eligible records regardless of batch size
        assert result["archived_count"] == result["eligible_count"]
