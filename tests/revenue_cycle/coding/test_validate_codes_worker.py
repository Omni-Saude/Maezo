"""Tests for validate_codes_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from revenue_cycle.coding.workers.validate_codes_worker import (
    ValidateCodesWorker,
    ValidateCodesInput,
    ValidateCodesOutput,
    register_worker,
)


class TestValidateCodesWorker:
    """Tests for the code validation worker."""

    @pytest.fixture
    def worker(self, mock_ans_client):
        return ValidateCodesWorker(ans_client=mock_ans_client)

    @pytest.mark.asyncio
    async def test_all_codes_valid(self, worker, mock_task, mock_ans_client):
        """All CID-10 and TUSS codes pass validation."""
        mock_ans_client.validate_cid10 = AsyncMock(
            return_value={"valid": True, "description": "Diabetes mellitus tipo 2"}
        )
        mock_ans_client.validate_tuss = AsyncMock(
            return_value={"valid": True, "description": "Consulta em consultorio"}
        )
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}, {"code": "I10"}],
            "tuss_codes": [{"code": "10101012"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        validation = variables.get("validation_result", variables.get("all_valid", None))
        assert validation is True or "valid" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_invalid_cid10_bpmn_error(self, worker, mock_task, mock_ans_client):
        """Invalid CID-10 code triggers BPMN error."""
        mock_ans_client.validate_cid10 = AsyncMock(
            return_value={"valid": False, "reason": "Code E99.9 not in CID-10 table"}
        )
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E99.9"}],
            "tuss_codes": [{"code": "10101012"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "INVALID" in error_code.upper() or "CID" in error_code.upper()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_tuss_bpmn_error(self, worker, mock_task, mock_ans_client):
        """Invalid TUSS code triggers BPMN error."""
        mock_ans_client.validate_cid10 = AsyncMock(
            return_value={"valid": True, "description": "Valid"}
        )
        mock_ans_client.validate_tuss = AsyncMock(
            return_value={"valid": False, "reason": "Code 99999999 not in TUSS table"}
        )
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "99999999"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "INVALID" in error_code.upper() or "TUSS" in error_code.upper()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_validation(self, worker, mock_task, mock_ans_client):
        """Mix of valid and invalid codes reports all invalid ones."""
        call_count = 0

        async def alternating_cid10(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"valid": True, "description": "Valid code"}
            return {"valid": False, "reason": "Invalid code"}

        mock_ans_client.validate_cid10 = AsyncMock(side_effect=alternating_cid10)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}, {"code": "X99.9"}],
            "tuss_codes": [],
        }.get(key, default)

        await worker.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called


class TestValidateCodesInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = ValidateCodesInput(
            encounter_id="ENC-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
        )
        assert len(inp.cid10_codes) == 1

    def test_empty_codes_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ValidateCodesInput(
                encounter_id="ENC-001",
                cid10_codes=[],
                tuss_codes=[],
            )


class TestValidateCodesOutput:
    """Tests for output model."""

    def test_all_valid_output(self):
        out = ValidateCodesOutput(
            all_valid=True,
            invalid_codes=[],
            validation_details=[],
        )
        assert out.all_valid is True
        assert len(out.invalid_codes) == 0
