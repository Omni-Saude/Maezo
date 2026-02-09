"""Tests for ApplyContractRulesWorker."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from platform.revenue_cycle.billing.workers.apply_contract_rules_worker import ApplyContractRulesWorker
from platform.shared.domain.exceptions import ContractRuleViolation
from platform.shared.domain.value_objects import Money


@pytest.fixture
def worker():
    """Create worker instance."""
    return ApplyContractRulesWorker()


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
def basic_contract_rules() -> Dict[str, Any]:
    """Create basic contract rules."""
    return {
        "copay_pct": "20",
        "deductible": "100.00",
        "coverage_limit": None,
        "procedure_limits": {}
    }


@pytest.fixture
def mock_job():
    """Create mock job."""
    job = MagicMock()
    job.variables = {}
    return job


class TestApplyContractRulesWorker:
    """Tests for ApplyContractRulesWorker."""

    @pytest.mark.asyncio
    async def test_operation_name(self, worker):
        """Test operation name is set."""
        assert worker.operation_name == "Aplicar regras contratuais"

    @pytest.mark.asyncio
    async def test_process_task_success(self, worker, mock_job, sample_procedures, basic_contract_rules):
        """Test successful contract rules application."""
        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": sample_procedures,
            "contract_rules": basic_contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        assert result.success is True
        assert "adjusted_items" in result.variables
        assert "total_patient_responsibility" in result.variables
        assert "total_payer_responsibility" in result.variables
        assert "applied_rules" in result.variables

        adjusted_items = result.variables["adjusted_items"]
        assert len(adjusted_items) == 3

        # Verify calculations
        total_patient = Decimal(result.variables["total_patient_responsibility"])
        total_payer = Decimal(result.variables["total_payer_responsibility"])
        total_charges = Decimal(result.variables["total_charges"])

        assert total_patient + total_payer == total_charges

    @pytest.mark.asyncio
    async def test_copay_calculation(self, worker, mock_job):
        """Test co-payment calculation."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        contract_rules = {
            "copay_pct": "20",
            "deductible": "0",
            "coverage_limit": None,
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["adjusted_items"][0]
        assert Decimal(item["copay_amount"]) == Decimal("20.00")
        assert Decimal(item["patient_responsibility"]) == Decimal("20.00")
        assert Decimal(item["payer_responsibility"]) == Decimal("80.00")

    @pytest.mark.asyncio
    async def test_deductible_application(self, worker, mock_job):
        """Test deductible application."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "150.00"
            },
            {
                "code": "20101015",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        contract_rules = {
            "copay_pct": "0",
            "deductible": "120.00",
            "coverage_limit": None,
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        items = result.variables["adjusted_items"]

        # First procedure should have 120 deductible applied
        assert Decimal(items[0]["deductible_applied"]) == Decimal("120.00")
        assert Decimal(items[0]["patient_responsibility"]) == Decimal("120.00")
        assert Decimal(items[0]["payer_responsibility"]) == Decimal("30.00")

        # Second procedure should have 0 deductible (already exhausted)
        assert Decimal(items[1]["deductible_applied"]) == Decimal("0")
        assert Decimal(items[1]["payer_responsibility"]) == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_coverage_limit(self, worker, mock_job):
        """Test coverage limit enforcement."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "5000.00"
            }
        ]

        contract_rules = {
            "copay_pct": "0",
            "deductible": "0",
            "coverage_limit": "3000.00",
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        total_payer = Decimal(result.variables["total_payer_responsibility"])
        total_patient = Decimal(result.variables["total_patient_responsibility"])

        # Payer should only pay up to coverage limit
        assert total_payer == Decimal("3000.00")
        # Patient pays the excess
        assert total_patient == Decimal("2000.00")

    @pytest.mark.asyncio
    async def test_procedure_limits(self, worker, mock_job):
        """Test procedure-specific limits."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "500.00"
            }
        ]

        contract_rules = {
            "copay_pct": "0",
            "deductible": "0",
            "coverage_limit": None,
            "procedure_limits": {
                "10101012": "300.00"
            }
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["adjusted_items"][0]
        # Line total should be capped at procedure limit
        assert Decimal(item["line_total"]) == Decimal("300.00")

    @pytest.mark.asyncio
    async def test_combined_rules(self, worker, mock_job):
        """Test combined copay and deductible."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "1000.00"
            }
        ]

        contract_rules = {
            "copay_pct": "20",
            "deductible": "100.00",
            "coverage_limit": None,
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["adjusted_items"][0]

        copay = Decimal(item["copay_amount"])
        deductible = Decimal(item["deductible_applied"])
        patient = Decimal(item["patient_responsibility"])
        payer = Decimal(item["payer_responsibility"])

        # Copay: 20% of 1000 = 200
        assert copay == Decimal("200.00")
        # Deductible: 100
        assert deductible == Decimal("100.00")
        # Patient: copay + deductible = 300
        assert patient == Decimal("300.00")
        # Payer: 1000 - 300 = 700
        assert payer == Decimal("700.00")

    @pytest.mark.asyncio
    async def test_missing_claim_id(self, worker, mock_job, sample_procedures, basic_contract_rules):
        """Test error when claim_id is missing."""
        variables = {
            "payer_id": "payer-456",
            "procedures": sample_procedures,
            "contract_rules": basic_contract_rules
        }

        with pytest.raises(ContractRuleViolation) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_CLAIM_ID"

    @pytest.mark.asyncio
    async def test_missing_payer_id(self, worker, mock_job, sample_procedures, basic_contract_rules):
        """Test error when payer_id is missing."""
        variables = {
            "claim_id": "claim-123",
            "procedures": sample_procedures,
            "contract_rules": basic_contract_rules
        }

        with pytest.raises(ContractRuleViolation) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_PAYER_ID"

    @pytest.mark.asyncio
    async def test_invalid_copay_percentage(self, worker, mock_job, sample_procedures):
        """Test error with invalid copay percentage."""
        contract_rules = {
            "copay_pct": "150",  # Invalid: > 100
            "deductible": "0",
            "coverage_limit": None,
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": sample_procedures,
            "contract_rules": contract_rules
        }

        with pytest.raises(ContractRuleViolation) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_COPAY_PERCENTAGE"

    @pytest.mark.asyncio
    async def test_negative_deductible(self, worker, mock_job, sample_procedures):
        """Test error with negative deductible."""
        contract_rules = {
            "copay_pct": "20",
            "deductible": "-100.00",  # Invalid: negative
            "coverage_limit": None,
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": sample_procedures,
            "contract_rules": contract_rules
        }

        with pytest.raises(ContractRuleViolation) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_DEDUCTIBLE"

    @pytest.mark.asyncio
    async def test_invalid_unit_price(self, worker, mock_job, basic_contract_rules):
        """Test error with invalid unit price."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "invalid"
            }
        ]

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": basic_contract_rules
        }

        with pytest.raises(ContractRuleViolation) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_UNIT_PRICE"

    @pytest.mark.asyncio
    async def test_zero_copay_and_deductible(self, worker, mock_job):
        """Test with zero copay and deductible."""
        procedures = [
            {
                "code": "10101012",
                "quantity": 1,
                "unit_price": "100.00"
            }
        ]

        contract_rules = {
            "copay_pct": "0",
            "deductible": "0",
            "coverage_limit": None,
            "procedure_limits": {}
        }

        variables = {
            "claim_id": "claim-123",
            "payer_id": "payer-456",
            "procedures": procedures,
            "contract_rules": contract_rules
        }

        result = await worker.process_task(mock_job, variables)

        item = result.variables["adjusted_items"][0]
        assert Decimal(item["patient_responsibility"]) == Decimal("0")
        assert Decimal(item["payer_responsibility"]) == Decimal("100.00")
