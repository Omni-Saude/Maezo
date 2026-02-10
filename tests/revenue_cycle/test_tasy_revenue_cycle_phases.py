"""Tests for Revenue Cycle TASY integration phases (RC-GAP-1 through RC-GAP-10)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.integrations.tasy_api_client import StubTasyApiClient


class TestPricingMethods:
    """RC-GAP-1: Material Pricing."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_get_material_price(self, stub):
        result = await stub.get_material_price("MAT-001")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_brasindice_medicines(self, stub):
        result = await stub.get_brasindice_medicines()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_simpro_materials(self, stub):
        result = await stub.get_simpro_materials()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_resolve_price(self, stub):
        result = await stub.resolve_price("MAT-001", ["brasindice", "simpro"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_procedure_price(self, stub):
        result = await stub.get_procedure_price("40101010")
        assert isinstance(result, dict)


class TestAuthorizationMethods:
    """RC-GAP-2: Insurance Authorization."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_submit_authorization(self, stub):
        result = await stub.submit_authorization({"procedure_code": "40101010", "patient_id": "P1"})
        assert "authorization_id" in result

    @pytest.mark.asyncio
    async def test_get_authorization_status(self, stub):
        auth = await stub.submit_authorization({"procedure_code": "X"})
        result = await stub.get_authorization_status(auth["authorization_id"])
        assert "status" in result

    @pytest.mark.asyncio
    async def test_cancel_authorization(self, stub):
        auth = await stub.submit_authorization({"procedure_code": "X"})
        result = await stub.cancel_authorization(auth["authorization_id"], "no longer needed")
        assert result["status"] == "cancelled"


class TestGlosaMethods:
    """RC-GAP-3: Glosa/Denial."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_post_glosa(self, stub):
        result = await stub.post_glosa({"claim_id": "C1", "amount": 500.00, "reason": "DUPLICIDADE"})
        assert "glosa_id" in result

    @pytest.mark.asyncio
    async def test_get_glosa(self, stub):
        g = await stub.post_glosa({"claim_id": "C1", "amount": 500.00})
        result = await stub.get_glosa("C1")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_submit_glosa_appeal(self, stub):
        g = await stub.post_glosa({"claim_id": "C1", "amount": 500.00})
        result = await stub.submit_glosa_appeal(g["glosa_id"], {"justification": "Procedimento correto"})
        assert "appeal_id" in result

    @pytest.mark.asyncio
    async def test_get_glosa_statistics(self, stub):
        result = await stub.get_glosa_statistics("2024-01-01", "2024-01-31")
        assert isinstance(result, dict)


class TestTISSMethods:
    """RC-GAP-4: TISS Data."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_get_tiss_header(self, stub):
        result = await stub.get_tiss_header("CONTA-123")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_validate_tiss(self, stub):
        result = await stub.validate_tiss("CONTA-123")
        assert isinstance(result, dict)


class TestContractMethods:
    """RC-GAP-5: Contract Rules."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_get_contract_rules(self, stub):
        result = await stub.get_contract_rules("CONTRACT-001")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_validate_contract(self, stub):
        result = await stub.validate_contract("CONTRACT-001", {"procedure": "40101010"})
        assert isinstance(result, dict)


class TestProcedureMethods:
    """RC-GAP-6: Procedure Master."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_search_tuss_procedures(self, stub):
        result = await stub.search_tuss_procedures(search="consulta")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_tuss_procedure_details(self, stub):
        result = await stub.get_tuss_procedure_details("40101010")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_compatible_procedures(self, stub):
        result = await stub.get_compatible_procedures("40101010")
        assert isinstance(result, list)


class TestMVSoulMethods:
    """RC-GAP-7: MV Soul."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_export_to_mvsoul(self, stub):
        result = await stub.export_to_mvsoul({"entity_type": "payment", "data": {}})
        assert "export_id" in result


class TestPIXExtendedMethods:
    """RC-GAP-8: PIX Callbacks."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_post_pix_refund(self, stub):
        result = await stub.post_pix_refund("PIX-001", {"amount": 100.00})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_pix_settlement(self, stub):
        result = await stub.get_pix_settlement("2024-01-01", "2024-01-31")
        assert isinstance(result, dict)


class TestReconciliationMethods:
    """RC-GAP-9: Extended Reconciliation."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_get_reconciliation_summary(self, stub):
        result = await stub.get_reconciliation_summary("daily", "2024-01-01", "2024-01-01")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_reconciliation_discrepancies(self, stub):
        result = await stub.get_reconciliation_discrepancies("2024-01-01", "2024-01-31")
        assert isinstance(result, list)


class TestFinancialReportingMethods:
    """RC-GAP-10: Financial Reporting."""

    @pytest.fixture
    def stub(self):
        return StubTasyApiClient()

    @pytest.mark.asyncio
    async def test_get_aging_report(self, stub):
        result = await stub.get_aging_report()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_dso_metric(self, stub):
        result = await stub.get_dso_metric("2024-01-01", "2024-01-31")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_revenue_leakage(self, stub):
        result = await stub.get_revenue_leakage("2024-01-01", "2024-01-31")
        assert isinstance(result, dict)


class TestCDCPollerExtended:
    """Verify new CDC tables."""

    def test_glosa_table_in_defaults(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        names = [c.table_name for c in DEFAULT_TABLE_CONFIGS]
        assert "GLOSA" in names

    def test_contrato_table_in_defaults(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        names = [c.table_name for c in DEFAULT_TABLE_CONFIGS]
        assert "CONTRATO" in names

    def test_procedimento_table_in_defaults(self):
        from healthcare_platform.shared.integrations.cdc_fallback_poller import DEFAULT_TABLE_CONFIGS
        names = [c.table_name for c in DEFAULT_TABLE_CONFIGS]
        assert "PROCEDIMENTO" in names
