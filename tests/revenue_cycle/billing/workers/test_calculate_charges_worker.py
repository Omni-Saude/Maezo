"""Tests for CalculateChargesWorker."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from platform.revenue_cycle.billing.workers.calculate_charges_worker import CalculateChargesWorker
from platform.shared.domain.exceptions import BillingException


@pytest.fixture
def worker():
    """Create worker instance."""
    return CalculateChargesWorker()


@pytest.fixture
def sample_procedures() -> List[Dict[str, Any]]:
    """Create sample procedures."""
    return [
        {
            "code": "10101012",
            "quantity": 1,
            "unit_price": "150.00",
            "description": "Consulta médica"
        },
        {
            "code": "20101015",
            "quantity": 2,
            "unit_price": "80.00",
            "description": "Exame de sangue"
        },
        {
            "code": "30502012",
            "quantity": 1,
            "unit_price": "5000.00",
            "description": "Cirurgia cardíaca"
        }
    ]


@pytest.fixture
def sample_modifiers() -> List[Dict[str, Any]]:
    """Create sample modifiers."""
    return [
        {
            "code": "MOD-50",
            "type": "percentage",
            "value": "10",
            "applies_to": None  # Applies to all
        },
        {
            "code": "MOD-SURG",
            "type": "percentage",
            "value": "20",
            "applies_to": "30502012"  # Only surgery
        }
    ]


@pytest.fixture
def mock_job():
    """Create mock job."""
    job = MagicMock()
    job.variables = {}
    return job


class TestCalculateChargesWorker:
    """Tests for CalculateChargesWorker."""

    @pytest.mark.asyncio
    async def test_operation_name(self, worker):
        """Test operation name is set."""
        assert worker.operation_name == "Calcular valores de cobrança"

    @pytest.mark.asyncio
    async def test_process_task_success(self, worker, mock_job, sample_procedures):
        """Test successful charge calculation."""
        variables = {
            "procedures": sample_procedures
        }

        result = await worker.process_task(mock_job, variables)

        assert result.success is True
        assert "line_items" in result.variables
        assert "total_amount" in result.variables
        assert "modifier_adjustments" in result.variables

        line_items = result.variables["line_items"]
        assert len(line_items) == 3

        # Check totals
        total = Decimal(result.variables["total_amount"])
        expected_total = Decimal("150.00") + Decimal("160.00") + Decimal("5000.00")
        assert total == expected_total

    @pytest.mark.asyncio
    async def test_basic_calculation(self, worker, mock_job):
        """Test basic price calculation."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 3,
                "unit_price": "100.00"
            }
        ]

        variables = {
            "procedures": procedures
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["line_items"][0]
        assert item["sequence"] == 1
        assert item["code"] == "10101012"
        assert item["quantity"] == 3
        assert Decimal(item["unit_price"]) == Decimal("100.00")
        assert Decimal(item["base_amount"]) == Decimal("300.00")
        assert Decimal(item["total_price"]) == Decimal("300.00")

    @pytest.mark.asyncio
    async def test_with_percentage_modifier(self, worker, mock_job):
        """Test calculation with percentage modifier."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-10",
                "type": "percentage",
                "value": "10",
                "applies_to": None
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["line_items"][0]
        assert Decimal(item["base_amount"]) == Decimal("100.00")
        assert Decimal(item["adjustments"]) == Decimal("10.00")
        assert Decimal(item["total_price"]) == Decimal("110.00")

    @pytest.mark.asyncio
    async def test_with_fixed_modifier(self, worker, mock_job):
        """Test calculation with fixed modifier."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-FIXED",
                "type": "fixed",
                "value": "25.00",
                "applies_to": None
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["line_items"][0]
        assert Decimal(item["adjustments"]) == Decimal("25.00")
        assert Decimal(item["total_price"]) == Decimal("125.00")

    @pytest.mark.asyncio
    async def test_selective_modifier_application(self, worker, mock_job):
        """Test that modifiers apply only to specified procedures."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            },
            {
                "code": "20101015",
                "quantity": 1,
                "unit_price": "50.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-SPEC",
                "type": "percentage",
                "value": "20",
                "applies_to": "10101012"
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["line_items"]

        # First procedure should have modifier
        assert Decimal(items[0]["adjustments"]) == Decimal("20.00")
        assert Decimal(items[0]["total_price"]) == Decimal("120.00")

        # Second procedure should not have modifier
        assert Decimal(items[1]["adjustments"]) == Decimal("0")
        assert Decimal(items[1]["total_price"]) == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_wildcard_modifier(self, worker, mock_job):
        """Test modifier with wildcard pattern."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            },
            {
                "code": "10101013",
                "quantity": 1,
                "unit_price": "100.00"
            },
            {
                "code": "20101015",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-CONSULT",
                "type": "percentage",
                "value": "10",
                "applies_to": "101*"  # Matches codes starting with 101
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["line_items"]

        # First two should have modifier
        assert Decimal(items[0]["adjustments"]) == Decimal("10.00")
        assert Decimal(items[1]["adjustments"]) == Decimal("10.00")
        # Third should not
        assert Decimal(items[2]["adjustments"]) == Decimal("0")

    @pytest.mark.asyncio
    async def test_multiple_modifiers(self, worker, mock_job):
        """Test multiple modifiers on same procedure."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-1",
                "type": "percentage",
                "value": "10",
                "applies_to": None
            },
            {
                "code": "MOD-2",
                "type": "fixed",
                "value": "15.00",
                "applies_to": None
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["line_items"][0]
        # 10% of 100 = 10 + fixed 15 = 25 total adjustment
        assert Decimal(item["adjustments"]) == Decimal("25.00")
        assert Decimal(item["total_price"]) == Decimal("125.00")

    @pytest.mark.asyncio
    async def test_negative_adjustment_to_zero(self, worker, mock_job):
        """Test that negative adjustments result in zero price."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-NEG",
                "type": "percentage",
                "value": "-150",  # More than 100% reduction
                "applies_to": None
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["line_items"][0]
        # Should be capped at zero
        assert Decimal(item["total_price"]) == Decimal("0")

    @pytest.mark.asyncio
    async def test_missing_procedures(self, worker, mock_job):
        """Test error when procedures are missing."""
        variables = {}

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_PROCEDURES"

    @pytest.mark.asyncio
    async def test_missing_procedure_code(self, worker, mock_job):
        """Test error when procedure code is missing."""
        procedures = [
            {
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        variables = {
            "procedures": procedures
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_PROCEDURE_CODE"

    @pytest.mark.asyncio
    async def test_invalid_quantity(self, worker, mock_job):
        """Test error with invalid quantity."""
        procedures = [
            {
                "code": "10101012",
                "quantity": "invalid",
                "unit_price": "100.00"
            }
        ]

        variables = {
            "procedures": procedures
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_QUANTITY"

    @pytest.mark.asyncio
    async def test_missing_unit_price(self, worker, mock_job):
        """Test error when unit price is missing."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1
            }
        ]

        variables = {
            "procedures": procedures
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_UNIT_PRICE"

    @pytest.mark.asyncio
    async def test_invalid_unit_price(self, worker, mock_job):
        """Test error with invalid unit price."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "invalid"
            }
        ]

        variables = {
            "procedures": procedures
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_UNIT_PRICE"

    @pytest.mark.asyncio
    async def test_standard_modifier_defaults(self, worker, mock_job):
        """Test that standard modifiers use default values."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        modifiers = [
            {
                "code": "MOD-MULTI",
                "type": "multiple_procedure",
                "applies_to": None
                # No value specified - should use default -50%
            }
        ]

        variables = {
            "procedures": procedures,
            "modifiers": modifiers
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["line_items"][0]
        # Default multiple_procedure is -50%
        assert Decimal(item["adjustments"]) == Decimal("-50.00")
        assert Decimal(item["total_price"]) == Decimal("50.00")
