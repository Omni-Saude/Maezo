from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from platform.revenue_cycle.collection.exceptions import ERPSyncError
from platform.revenue_cycle.collection.workers.export_to_erp_worker import ExportToERPWorker


@pytest.mark.asyncio
class TestExportToERPWorker:
    """Tests for ExportToERPWorker."""

    async def test_export_to_tasy_success(self):
        """Test successful export to Tasy ERP."""
        worker = ExportToERPWorker()

        task_variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "tasy",
            "entity_type": "payment",
            "entity_data": {"amount": 50000.00, "date": "2024-01-15"},
            "operation": "insert",
        }

        result = await worker.execute(task_variables)

        assert result["success"] is True
        assert result["erp_system"] == "tasy"
        assert result["operation"] == "insert"
        assert result["export_id"] is not None
        assert "erp_response" in result
        assert "exported_at" in result

    async def test_export_to_mv_soul_success(self):
        """Test successful export to MV Soul ERP."""
        worker = ExportToERPWorker()

        task_variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "mv_soul",
            "entity_type": "reconciliation",
            "entity_data": {"total": 1000000.00, "status": "closed"},
            "operation": "update",
        }

        result = await worker.execute(task_variables)

        assert result["success"] is True
        assert result["erp_system"] == "mv_soul"
        assert result["entity_type"] == "reconciliation"

    async def test_export_unsupported_erp_system(self):
        """Test export with unsupported ERP system."""
        worker = ExportToERPWorker()

        task_variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "unsupported_system",
            "entity_type": "payment",
            "entity_data": {},
            "operation": "insert",
        }

        with pytest.raises(ERPSyncError):
            await worker.execute(task_variables)

    @patch("platform.revenue_cycle.collection.workers.export_to_erp_worker.ExportToERPWorker._sync_to_tasy")
    async def test_export_sync_failure(self, mock_sync):
        """Test export with sync failure."""
        mock_sync.side_effect = Exception("Connection timeout")

        worker = ExportToERPWorker()

        task_variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "tasy",
            "entity_type": "payment",
            "entity_data": {},
            "operation": "insert",
        }

        with pytest.raises(ERPSyncError):
            await worker.execute(task_variables)
