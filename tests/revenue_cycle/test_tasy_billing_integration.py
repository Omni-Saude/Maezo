"""Tests for TASY billing integration (GAP-03 fix)."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.shared.integrations.tasy_api_client import (
    StubTasyApiClient,
)


class TestTasyApiClientBillingMethods:
    """Test new billing methods on TasyApiClient."""

    @pytest.fixture
    def stub_client(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_post_billing_sync(self, stub_client):
        """post_billing_sync returns transaction response."""
        result = await stub_client.post_billing_sync(
            account_id="CONTA-123",
            billing_data={"entity_type": "payment", "operation": "insert", "data": {}},
        )
        assert "transaction_id" in result
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_payments_empty(self, stub_client):
        """get_payments returns empty list when no payments."""
        result = await stub_client.get_payments(
            date_from="2024-01-01", date_to="2024-01-31"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_payments_with_data(self, stub_client):
        """get_payments returns added payments."""
        stub_client.add_payment("PAY-1", {
            "NR_PAGAMENTO": "PAY-1",
            "VL_PAGAMENTO": 1000.00,
            "DT_PAGAMENTO": "2024-01-15",
            "IE_CONCILIADO": "S",
        })
        result = await stub_client.get_payments(
            date_from="2024-01-01", date_to="2024-01-31"
        )
        assert len(result) == 1
        assert result[0]["VL_PAGAMENTO"] == 1000.00

    @pytest.mark.asyncio
    async def test_get_receivables(self, stub_client):
        """get_receivables returns receivable records."""
        result = await stub_client.get_receivables(
            date_from="2024-01-01", date_to="2024-01-31"
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_post_pix_payment(self, stub_client):
        """post_pix_payment returns PIX response."""
        result = await stub_client.post_pix_payment(
            payment_data={"VL_PAGAMENTO": 500.00, "CD_CHAVE_PIX": "email@test.com"}
        )
        assert "pix_id" in result
        assert "e2e_id" in result

    @pytest.mark.asyncio
    async def test_get_pix_status(self, stub_client):
        """get_pix_status returns status for PIX payment."""
        # First create a PIX payment
        pix = await stub_client.post_pix_payment(
            payment_data={"VL_PAGAMENTO": 500.00}
        )
        result = await stub_client.get_pix_status(pix_id=pix["pix_id"])
        assert "status" in result


class TestExportToERPWorkerIntegration:
    """Test export_to_erp_worker with real TasyApiClient."""

    @pytest.mark.asyncio
    async def test_sync_to_tasy_uses_api_client(self):
        """_sync_to_tasy calls post_billing_sync on TasyApiClient."""
        mock_client = AsyncMock()
        mock_client.post_billing_sync.return_value = {
            "transaction_id": "TASY-REAL-123",
            "status": "success",
            "synced_at": "2024-01-15T10:00:00Z",
        }

        from healthcare_platform.revenue_cycle.collection.workers.export_to_erp_worker import ExportToERPWorker
        worker = ExportToERPWorker(tasy_api_client=mock_client)

        result = await worker.service._sync_to_tasy(
            entity_type="payment",
            entity_data={"account_id": "CONTA-123", "amount": 1000},
            operation="insert",
        )

        mock_client.post_billing_sync.assert_called_once()
        assert result["transaction_id"] == "TASY-REAL-123"

    @pytest.mark.asyncio
    async def test_sync_to_tasy_without_client_raises(self):
        """_sync_to_tasy raises ERPSyncError without api client."""
        from healthcare_platform.revenue_cycle.collection.workers.export_to_erp_worker import ExportToERPWorker
        from healthcare_platform.revenue_cycle.collection.exceptions import ERPSyncError

        worker = ExportToERPWorker(tasy_api_client=None)

        with pytest.raises(ERPSyncError):
            await worker.service._sync_to_tasy("payment", {"account_id": "X"}, "insert")


class TestReconcileDailyWorkerIntegration:
    """Test reconcile_daily_worker with real TasyApiClient."""

    @pytest.mark.asyncio
    async def test_uses_tasy_payments(self):
        """execute fetches payments from TasyApiClient."""
        mock_client = AsyncMock()
        mock_client.get_payments.return_value = [
            {"NR_PAGAMENTO": "P1", "VL_PAGAMENTO": 1000.00, "IE_CONCILIADO": "S"},
            {"NR_PAGAMENTO": "P2", "VL_PAGAMENTO": 500.00, "IE_CONCILIADO": "N"},
        ]
        mock_client.get_receivables.return_value = [
            {"NR_TITULO": "T1", "VL_TITULO": 1500.00},
        ]

        from healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker import ReconcileDailyWorker
        worker = ReconcileDailyWorker(tasy_api_client=mock_client)

        result = await worker.execute({
            "reconciliation_date": "2024-01-15",
        })

        assert result["payment_count"] == 2
        assert result["matched_count"] == 1
        assert result["unmatched_count"] == 1
        assert result["total_received"] == 1500.0
        mock_client.get_payments.assert_called_once()


class TestCDCFallbackPollerTables:
    """Test CDC poller includes PAGAMENTO and AUTORIZACAO tables."""

    def test_default_configs_include_pagamento(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        table_names = [c.table_name for c in DEFAULT_TABLE_CONFIGS]
        assert "PAGAMENTO" in table_names

    def test_default_configs_include_autorizacao(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        table_names = [c.table_name for c in DEFAULT_TABLE_CONFIGS]
        assert "AUTORIZACAO" in table_names

    def test_pagamento_is_high_priority(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        pagamento = next(c for c in DEFAULT_TABLE_CONFIGS if c.table_name == "PAGAMENTO")
        assert pagamento.priority == "HIGH"

    def test_autorizacao_is_high_priority(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        autorizacao = next(c for c in DEFAULT_TABLE_CONFIGS if c.table_name == "AUTORIZACAO")
        assert autorizacao.priority == "HIGH"

    def test_pagamento_interval_is_120(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        pagamento = next(c for c in DEFAULT_TABLE_CONFIGS if c.table_name == "PAGAMENTO")
        assert pagamento.interval_seconds == 120

    def test_autorizacao_interval_is_180(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        autorizacao = next(c for c in DEFAULT_TABLE_CONFIGS if c.table_name == "AUTORIZACAO")
        assert autorizacao.interval_seconds == 180

    def test_pagamento_kafka_topic(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        pagamento = next(c for c in DEFAULT_TABLE_CONFIGS if c.table_name == "PAGAMENTO")
        assert pagamento.kafka_topic == "tasy.AUSTA.PAGAMENTO"

    def test_autorizacao_kafka_topic(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        autorizacao = next(c for c in DEFAULT_TABLE_CONFIGS if c.table_name == "AUTORIZACAO")
        assert autorizacao.kafka_topic == "tasy.AUSTA.AUTORIZACAO"
