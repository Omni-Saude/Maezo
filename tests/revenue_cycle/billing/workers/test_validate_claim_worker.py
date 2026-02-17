"""Tests for ValidateClaimWorker."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.billing.workers.validate_claim_worker_v2 import ValidateClaimWorker
from healthcare_platform.shared.workers.base import TaskStatus

from unittest.mock import Mock


@pytest.fixture
def mock_dmn_service():
    """Create mock DMN service."""
    dmn_service = Mock()
    # Default DMN response: PROSSEGUIR (allow processing)
    dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Processar com sucesso",
        "risco": "BAIXO"
    }
    return dmn_service


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker instance."""
    return ValidateClaimWorker(dmn_service=mock_dmn_service)


@pytest.fixture
def valid_claim_data():
    """Create valid claim data."""
    return {
        "patient_id": str(uuid4()),
        "payer_id": str(uuid4()),
        "tiss_guide_type": "sp_sadt",
        "items": [
            {
                "sequence": 1,
                "procedure_code": {"code": "10101012", "system": "http://www.ans.gov.br/tuss"},
                "quantity": 1,
                "unit_price": 150.00,
                "total_price": 150.00,
            },
            {
                "sequence": 2,
                "procedure_code": {"code": "20104030", "system": "http://www.ans.gov.br/tuss"},
                "quantity": 2,
                "unit_price": 50.00,
                "total_price": 100.00,
            },
        ],
        "total": {"amount": 250.00, "currency": "BRL"},
    }


@pytest.fixture
def valid_variables(valid_claim_data):
    """Create valid process variables."""
    return {
        "claim_id": str(uuid4()),
        "claim": valid_claim_data,
    }


class TestValidateClaimWorker:
    """Test suite for ValidateClaimWorker."""

    @pytest.mark.asyncio
    async def test_successful_validation(self, worker, valid_variables):
        """Test successful claim validation."""
        job = SimpleNamespace(variables=valid_variables)

        result = await worker.process_task(job, valid_variables)

        assert result.success is True
        assert result.variables["validation_passed"] is True
        assert result.variables["claim_ready_for_submission"] is True
        assert len(result.variables["validation_errors"]) == 0

    @pytest.mark.asyncio
    async def test_missing_claim_id(self, worker, valid_variables):
        """Test error when claim_id is missing."""
        variables = valid_variables.copy()
        del variables["claim_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_missing_claim_data(self, worker):
        """Test error when claim data is missing."""
        variables = {"claim_id": str(uuid4())}

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "CLAIM_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_missing_required_field(self, worker, valid_variables):
        """Test validation fails when required field is missing."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        del claim["patient_id"]
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert len(result.variables["validation_errors"]) > 0
        assert any("patient_id" in err for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_empty_items(self, worker, valid_variables):
        """Test validation fails when items list is empty."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["items"] = []
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("item" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_invalid_tiss_guide_type(self, worker, valid_variables):
        """Test validation fails for invalid TISS guide type."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["tiss_guide_type"] = "invalid_type"
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("guia tiss" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_item_missing_sequence(self, worker, valid_variables):
        """Test validation fails when item is missing sequence."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        items = claim["items"].copy()
        del items[0]["sequence"]
        claim["items"] = items
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("sequence" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_item_missing_procedure_code(self, worker, valid_variables):
        """Test validation fails when item is missing procedure code."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        items = claim["items"].copy()
        del items[0]["procedure_code"]
        claim["items"] = items
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("procedimento" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_invalid_quantity(self, worker, valid_variables):
        """Test validation fails for invalid quantity."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        items = claim["items"].copy()
        items[0]["quantity"] = 0  # Invalid
        claim["items"] = items
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("quantidade" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_price_inconsistency(self, worker, valid_variables):
        """Test validation fails when item price is inconsistent."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        items = claim["items"].copy()
        items[0]["unit_price"] = 100.00
        items[0]["quantity"] = 2
        items[0]["total_price"] = 150.00  # Should be 200.00
        claim["items"] = items
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("inconsistente" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_total_mismatch(self, worker, valid_variables):
        """Test validation fails when total doesn't match sum of items."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["total"] = {"amount": 999.99, "currency": "BRL"}  # Incorrect total
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("soma" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_duplicate_items(self, worker, valid_variables):
        """Test validation detects duplicate items."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        # Add duplicate item
        items = claim["items"].copy()
        items.append(items[0].copy())  # Duplicate first item
        items[-1]["sequence"] = 3
        claim["items"] = items
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("duplicado" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_missing_authorization_for_admission(self, worker, valid_variables):
        """Test validation fails when authorization is missing for admission."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["tiss_guide_type"] = "admission"
        # Items don't have authorization_reference
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert any("autorização" in err.lower() for err in result.variables["validation_errors"])

    @pytest.mark.asyncio
    async def test_authorization_present_for_admission(self, worker, valid_variables):
        """Test validation passes when authorization is present for admission."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["tiss_guide_type"] = "admission"
        items = claim["items"].copy()
        for item in items:
            item["authorization_reference"] = "AUTH-12345"
        claim["items"] = items
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is True

    @pytest.mark.asyncio
    async def test_items_not_list(self, worker, valid_variables):
        """Test validation fails when items is not a list."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["items"] = "not a list"
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False

    @pytest.mark.asyncio
    async def test_multiple_validation_errors(self, worker, valid_variables):
        """Test that multiple validation errors are collected."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        del claim["patient_id"]  # Error 1
        del claim["payer_id"]  # Error 2
        claim["items"] = []  # Error 3
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["validation_passed"] is False
        assert len(result.variables["validation_errors"]) >= 3

    @pytest.mark.asyncio
    async def test_decimal_rounding_tolerance(self, worker, valid_variables):
        """Test validation allows small rounding differences."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        # Total is 250.00, but due to rounding might be 250.01
        claim["total"] = {"amount": 250.01, "currency": "BRL"}
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        # Should pass with 0.01 tolerance
        assert result.success is True
        assert result.variables["validation_passed"] is True
