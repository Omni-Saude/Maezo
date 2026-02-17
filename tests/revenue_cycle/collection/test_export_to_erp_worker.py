from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import ERPSyncError
from healthcare_platform.revenue_cycle.collection.workers.export_to_erp_worker import ExportToERPWorker


def _make_worker_with_mock_client():
    """Create worker with a mock TasyApiClient."""
    mock_client = MagicMock()
    mock_client.post_billing_sync = AsyncMock(return_value={
        "transaction_id": "TXN-001",
        "status": "success",
    })
    mock_client.export_to_mvsoul = AsyncMock(return_value={
        "transaction_id": "TXN-002",
        "status": "success",
    })
    worker = ExportToERPWorker(tasy_api_client=mock_client)
    return worker


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.export_to_erp_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.export_to_erp_worker.FederatedDMNService")
class TestExportToERPWorker:
    """Tests for ExportToERPWorker."""

    async def test_export_to_tasy_success(self, mock_dmn_service_cls, mock_tenant):
        """Test successful export to Tasy ERP."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldExport": True,
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = _make_worker_with_mock_client()
        job = MagicMock()
        job.variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "tasy",
            "entity_type": "payment",
            "entity_data": {"amount": 50000.00, "date": "2024-01-15", "account_id": "ACC-001"},
            "operation": "insert",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["success"] is True
        assert result.variables["erp_system"] == "tasy"
        assert result.variables["operation"] == "insert"
        assert result.variables["export_id"] is not None
        assert "erp_response" in result.variables
        assert "exported_at" in result.variables

    async def test_export_to_mv_soul_success(self, mock_dmn_service_cls, mock_tenant):
        """Test successful export to MV Soul ERP."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldExport": True,
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = _make_worker_with_mock_client()
        job = MagicMock()
        job.variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "mv_soul",
            "entity_type": "reconciliation",
            "entity_data": {"total": 1000000.00, "status": "closed"},
            "operation": "update",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["success"] is True
        assert result.variables["erp_system"] == "mv_soul"
        assert result.variables["entity_type"] == "reconciliation"

    async def test_export_unsupported_erp_system(self, mock_dmn_service_cls, mock_tenant):
        """Test export with unsupported ERP system."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldExport": True,
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = _make_worker_with_mock_client()
        job = MagicMock()
        job.variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "unsupported_system",
            "entity_type": "payment",
            "entity_data": {},
            "operation": "insert",
        }

        result = await worker.execute(job)

        assert result.success is False
        assert result.error_code == "ERP_SYNC_ERROR"

    async def test_export_sync_failure(self, mock_dmn_service_cls, mock_tenant):
        """Test export with sync failure."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldExport": True,
        }
        mock_dmn_service_cls.return_value = mock_dmn

        mock_client = MagicMock()
        mock_client.post_billing_sync = AsyncMock(side_effect=Exception("Connection timeout"))
        worker = ExportToERPWorker(tasy_api_client=mock_client)
        job = MagicMock()
        job.variables = {
            "reconciliation_id": str(uuid4()),
            "erp_system": "tasy",
            "entity_type": "payment",
            "entity_data": {"account_id": "ACC-001"},
            "operation": "insert",
        }

        result = await worker.execute(job)

        assert result.success is False
        assert result.error_code == "ERP_SYNC_ERROR"
