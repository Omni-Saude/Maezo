"""Tests for ConsolidateChargesWorker."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.billing.workers.consolidate_charges_worker import ConsolidateChargesWorker
from healthcare_platform.shared.domain.enums import BillingStatus


@pytest.fixture
def worker():
    """Create worker instance."""
    return ConsolidateChargesWorker()


@pytest.fixture
def valid_line_items():
    """Create valid line items."""
    return [
        {
            "code": "10101012",
            "code_system": "http://www.ans.gov.br/tuss",
            "display": "Consulta médica",
            "quantity": 1,
            "unit_price": 150.00,
            "service_date": "2024-02-09",
        },
        {
            "code": "20104030",
            "display": "Hemograma completo",
            "quantity": 1,
            "unit_price": 25.50,
        },
        {
            "code": "40101010",
            "display": "Raio-X",
            "quantity": 2,
            "unit_price": 80.00,
        },
    ]


@pytest.fixture
def valid_variables(valid_line_items):
    """Create valid process variables."""
    return {
        "encounter_id": str(uuid4()),
        "patient_id": str(uuid4()),
        "payer_id": str(uuid4()),
        "provider_id": str(uuid4()),
        "line_items": valid_line_items,
        "tiss_guide_type": "sp_sadt",
        "tenant_id": "AUSTA",
    }


class TestConsolidateChargesWorker:
    """Test suite for ConsolidateChargesWorker."""

    @pytest.mark.asyncio
    async def test_successful_consolidation(self, worker, valid_variables):
        """Test successful charge consolidation."""
        job = SimpleNamespace(variables=valid_variables)

        result = await worker.process_task(job, valid_variables)

        assert result.success is True
        assert "claim_id" in result.variables
        assert result.variables["item_count"] == 3
        # 150 + 25.50 + 2*80 = 335.50
        assert result.variables["claim_total"] == 335.50
        assert result.variables["billing_status"] == BillingStatus.VALIDATED.value

    @pytest.mark.asyncio
    async def test_missing_encounter_id(self, worker, valid_variables):
        """Test error when encounter_id is missing."""
        variables = valid_variables.copy()
        del variables["encounter_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"
        assert "atendimento" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_missing_patient_id(self, worker, valid_variables):
        """Test error when patient_id is missing."""
        variables = valid_variables.copy()
        del variables["patient_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"
        assert "paciente" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_missing_tenant_id(self, worker, valid_variables):
        """Test error when tenant_id is missing."""
        variables = valid_variables.copy()
        del variables["tenant_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_empty_line_items(self, worker, valid_variables):
        """Test error when line_items is empty."""
        variables = valid_variables.copy()
        variables["line_items"] = []

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"
        assert "item" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_line_items_not_list(self, worker, valid_variables):
        """Test error when line_items is not a list."""
        variables = valid_variables.copy()
        variables["line_items"] = "not a list"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_invalid_tenant_code(self, worker, valid_variables):
        """Test error when tenant code is invalid."""
        variables = valid_variables.copy()
        variables["tenant_id"] = "INVALID_TENANT"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"
        assert "tenant" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_item_missing_code(self, worker, valid_variables):
        """Test error when item is missing procedure code."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {
                "code": "",  # Empty code
                "quantity": 1,
                "unit_price": 100.00,
            }
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"
        assert "procedimento" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_invalid_quantity(self, worker, valid_variables):
        """Test error when item has invalid quantity."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {
                "code": "10101012",
                "quantity": 0,  # Invalid quantity
                "unit_price": 100.00,
            }
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_total_calculation_with_multiple_items(self, worker, valid_variables):
        """Test correct total calculation with multiple quantities."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {"code": "10101012", "quantity": 2, "unit_price": 100.00},
            {"code": "20104030", "quantity": 3, "unit_price": 50.00},
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        # 2*100 + 3*50 = 350
        assert result.variables["claim_total"] == 350.00

    @pytest.mark.asyncio
    async def test_zero_total_rejected(self, worker, valid_variables):
        """Test that zero total is rejected."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {"code": "10101012", "quantity": 1, "unit_price": 0.00},
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"
        assert "zero" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_optional_payer_id(self, worker, valid_variables):
        """Test that payer_id is optional (can be empty)."""
        variables = valid_variables.copy()
        variables["payer_id"] = ""

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        # Should succeed, payer can be set later
        assert result.success is True

    @pytest.mark.asyncio
    async def test_invalid_tiss_guide_type_ignored(self, worker, valid_variables):
        """Test that invalid TISS guide type is logged but doesn't fail."""
        variables = valid_variables.copy()
        variables["tiss_guide_type"] = "invalid_type"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        # Should succeed, guide type is optional
        assert result.success is True

    @pytest.mark.asyncio
    async def test_service_date_parsing(self, worker, valid_variables):
        """Test service date is correctly parsed."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": 100.00,
                "service_date": "2024-02-09",
            }
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_authorization_reference(self, worker, valid_variables):
        """Test authorization reference is preserved."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": 100.00,
                "authorization_reference": "AUTH-12345",
            }
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_modifier_codes(self, worker, valid_variables):
        """Test modifier codes are correctly handled."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": 100.00,
                "modifiers": [
                    {"system": "http://www.ans.gov.br/tuss", "code": "22"},
                    "26",  # String format
                ],
            }
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_decimal_precision(self, worker, valid_variables):
        """Test decimal precision is maintained."""
        variables = valid_variables.copy()
        variables["line_items"] = [
            {"code": "10101012", "quantity": 3, "unit_price": 33.33},
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        # 3 * 33.33 = 99.99
        assert abs(result.variables["claim_total"] - 99.99) < 0.01
