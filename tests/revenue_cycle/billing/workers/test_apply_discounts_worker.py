"""Tests for ApplyDiscountsWorker."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from platform.revenue_cycle.billing.workers.apply_discounts_worker import ApplyDiscountsWorker
from platform.shared.domain.exceptions import BillingException


@pytest.fixture
def worker():
    """Create worker instance."""
    return ApplyDiscountsWorker()


@pytest.fixture
def sample_line_items() -> List[Dict[str, Any]]:
    """Create sample line items."""
    return [
        {
            "sequence": 1,
            "code": "10101012",
            "quantity": 1,
            "total_price": "150.00",
            "description": "Consulta médica"
        },
        {
            "sequence": 2,
            "code": "20101015",
            "quantity": 2,
            "total_price": "160.00",
            "description": "Exame de sangue"
        },
        {
            "sequence": 3,
            "code": "30502012",
            "quantity": 1,
            "total_price": "5000.00",
            "description": "Cirurgia cardíaca"
        }
    ]


@pytest.fixture
def basic_discount_rules() -> List[Dict[str, Any]]:
    """Create basic discount rules."""
    return [
        {
            "type": "contractual",
            "percentage": "10",
            "conditions": {}
        }
    ]


@pytest.fixture
def mock_job():
    """Create mock job."""
    job = MagicMock()
    job.variables = {}
    return job


class TestApplyDiscountsWorker:
    """Tests for ApplyDiscountsWorker."""

    @pytest.mark.asyncio
    async def test_operation_name(self, worker):
        """Test operation name is set."""
        assert worker.operation_name == "Aplicar descontos contratuais"

    @pytest.mark.asyncio
    async def test_process_task_success(self, worker, mock_job, sample_line_items, basic_discount_rules):
        """Test successful discount application."""
        variables = {
            "line_items": sample_line_items,
            "discount_rules": basic_discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        assert result.success is True
        assert "discounted_items" in result.variables
        assert "total_discount" in result.variables
        assert "final_amount" in result.variables

        discounted = result.variables["discounted_items"]
        assert len(discounted) == 3

    @pytest.mark.asyncio
    async def test_basic_discount(self, worker, mock_job):
        """Test basic percentage discount."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            }
        ]

        discount_rules = [
            {
                "type": "contractual",
                "percentage": "10",
                "conditions": {}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["discounted_items"][0]
        assert Decimal(item["original_price"]) == Decimal("100.00")
        assert Decimal(item["discount_amount"]) == Decimal("10.00")
        assert Decimal(item["final_price"]) == Decimal("90.00")

    @pytest.mark.asyncio
    async def test_volume_discount(self, worker, mock_job):
        """Test volume-based discount."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "quantity": 25,
                "total_price": "1000.00"
            }
        ]

        discount_rules = [
            {
                "type": "volume",
                "percentage": "10",
                "conditions": {"min_quantity": 20}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["discounted_items"][0]
        # Volume discount with 25 quantity gets 15% bonus (10 * 1.15)
        expected_discount = Decimal("1000.00") * Decimal("0.115")
        assert Decimal(item["discount_amount"]) == expected_discount

    @pytest.mark.asyncio
    async def test_volume_discount_tiers(self, worker, mock_job):
        """Test volume discount tiers."""
        test_cases = [
            (10, "10"),  # Below 20, no bonus
            (25, "11.5"),  # 20-49, 15% bonus
            (60, "13"),  # 50-99, 30% bonus
            (150, "15"),  # 100+, 50% bonus
        ]

        for quantity, expected_pct in test_cases:
            line_items = [
                {
                    "sequence": 1,
                    "code": "10101012",
                    "quantity": quantity,
                    "total_price": "100.00"
                }
            ]

            discount_rules = [
                {
                    "type": "volume",
                    "percentage": "10",
                    "conditions": {}
                }
            ]

            variables = {
                "line_items": line_items,
                "discount_rules": discount_rules
            }

            result = await worker.process_task(mock_job, variables)

            item = result.variables["discounted_items"][0]
            expected_discount = Decimal("100.00") * (Decimal(expected_pct) / Decimal("100"))
            assert Decimal(item["discount_amount"]) == expected_discount

    @pytest.mark.asyncio
    async def test_procedure_code_condition(self, worker, mock_job):
        """Test discount with procedure code condition."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            },
            {
                "sequence": 2,
                "code": "20101015",
                "total_price": "100.00"
            }
        ]

        discount_rules = [
            {
                "type": "promotional",
                "percentage": "20",
                "conditions": {"procedure_code": "10101012"}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["discounted_items"]

        # First item should have discount
        assert Decimal(items[0]["discount_amount"]) == Decimal("20.00")
        # Second item should not
        assert Decimal(items[1]["discount_amount"]) == Decimal("0")

    @pytest.mark.asyncio
    async def test_wildcard_procedure_code(self, worker, mock_job):
        """Test discount with wildcard procedure code."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            },
            {
                "sequence": 2,
                "code": "10101013",
                "total_price": "100.00"
            },
            {
                "sequence": 3,
                "code": "20101015",
                "total_price": "100.00"
            }
        ]

        discount_rules = [
            {
                "type": "promotional",
                "percentage": "15",
                "conditions": {"procedure_code": "101*"}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["discounted_items"]

        # First two should have discount (codes start with 101)
        assert Decimal(items[0]["discount_amount"]) == Decimal("15.00")
        assert Decimal(items[1]["discount_amount"]) == Decimal("15.00")
        # Third should not
        assert Decimal(items[2]["discount_amount"]) == Decimal("0")

    @pytest.mark.asyncio
    async def test_minimum_quantity_condition(self, worker, mock_job):
        """Test discount with minimum quantity condition."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "quantity": 5,
                "total_price": "500.00"
            },
            {
                "sequence": 2,
                "code": "20101015",
                "quantity": 15,
                "total_price": "1500.00"
            }
        ]

        discount_rules = [
            {
                "type": "volume",
                "percentage": "10",
                "conditions": {"min_quantity": 10}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["discounted_items"]

        # First item has quantity < 10, no discount
        assert Decimal(items[0]["discount_amount"]) == Decimal("0")
        # Second item has quantity >= 10, gets discount
        assert Decimal(items[1]["discount_amount"]) > Decimal("0")

    @pytest.mark.asyncio
    async def test_multiple_discounts(self, worker, mock_job):
        """Test multiple discount rules on same item."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            }
        ]

        discount_rules = [
            {
                "type": "contractual",
                "percentage": "10",
                "conditions": {}
            },
            {
                "type": "promotional",
                "percentage": "5",
                "conditions": {}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["discounted_items"][0]
        # Total discount: 10 + 5 = 15
        assert Decimal(item["discount_amount"]) == Decimal("15.00")
        assert Decimal(item["final_price"]) == Decimal("85.00")

    @pytest.mark.asyncio
    async def test_discount_exceeds_price(self, worker, mock_job):
        """Test that discount cannot result in negative price."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            }
        ]

        discount_rules = [
            {
                "type": "promotional",
                "percentage": "150",  # More than 100%
                "conditions": {}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        # Should raise error for invalid percentage
        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_DISCOUNT_PERCENTAGE"

    @pytest.mark.asyncio
    async def test_no_discount_rules(self, worker, mock_job, sample_line_items):
        """Test with no discount rules."""
        variables = {
            "line_items": sample_line_items,
            "discount_rules": []
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["discounted_items"]

        # All items should have zero discount
        for item in items:
            assert Decimal(item["discount_amount"]) == Decimal("0")
            assert Decimal(item["original_price"]) == Decimal(item["final_price"])

    @pytest.mark.asyncio
    async def test_total_calculations(self, worker, mock_job):
        """Test total discount and final amount calculations."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            },
            {
                "sequence": 2,
                "code": "20101015",
                "total_price": "200.00"
            }
        ]

        discount_rules = [
            {
                "type": "contractual",
                "percentage": "10",
                "conditions": {}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        # Total: 100 + 200 = 300
        # Discount: 10 + 20 = 30
        # Final: 300 - 30 = 270
        assert Decimal(result.variables["original_amount"]) == Decimal("300.00")
        assert Decimal(result.variables["total_discount"]) == Decimal("30.00")
        assert Decimal(result.variables["final_amount"]) == Decimal("270.00")
        assert Decimal(result.variables["discount_percentage"]) == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_missing_line_items(self, worker, mock_job):
        """Test error when line items are missing."""
        variables = {}

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_LINE_ITEMS"

    @pytest.mark.asyncio
    async def test_invalid_line_items_format(self, worker, mock_job):
        """Test error when line items is not a list."""
        variables = {
            "line_items": "not-a-list"
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_DISCOUNT_RULES_FORMAT"

    @pytest.mark.asyncio
    async def test_missing_item_total(self, worker, mock_job):
        """Test error when item total price is missing."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012"
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": []
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_ITEM_TOTAL"

    @pytest.mark.asyncio
    async def test_invalid_item_total(self, worker, mock_job):
        """Test error with invalid item total."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "invalid"
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": []
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_ITEM_TOTAL"

    @pytest.mark.asyncio
    async def test_applied_discounts_details(self, worker, mock_job):
        """Test that applied discounts are detailed in output."""
        line_items = [
            {
                "sequence": 1,
                "code": "10101012",
                "total_price": "100.00"
            }
        ]

        discount_rules = [
            {
                "type": "contractual",
                "percentage": "10",
                "conditions": {}
            },
            {
                "type": "promotional",
                "percentage": "5",
                "conditions": {}
            }
        ]

        variables = {
            "line_items": line_items,
            "discount_rules": discount_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["discounted_items"][0]
        applied = item["applied_discounts"]

        assert len(applied) == 2
        assert applied[0]["type"] == "contractual"
        assert Decimal(applied[0]["percentage"]) == Decimal("10")
        assert Decimal(applied[0]["amount"]) == Decimal("10.00")
        assert applied[1]["type"] == "promotional"
        assert Decimal(applied[1]["percentage"]) == Decimal("5")
        assert Decimal(applied[1]["amount"]) == Decimal("5.00")
