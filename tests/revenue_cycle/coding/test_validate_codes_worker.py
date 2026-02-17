"""Tests for validate_codes_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
    ValidateCodesWorker,
    register_worker,
)
from healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2 import (
    ValidateCodesInput,
    ValidateCodesOutput,
)


class TestValidateCodesWorker:
    """Tests for the code validation worker."""

    @pytest.fixture
    def worker(self, mock_ans_client, mock_dmn_service):
        return ValidateCodesWorker(ans_client=mock_ans_client, dmn_service=mock_dmn_service)

    @pytest.mark.asyncio
    async def test_all_codes_valid(self, worker, mock_ans_client):
        """All CID-10 and TUSS codes pass validation."""
        mock_ans_client.validate_cid10 = AsyncMock(
            return_value={"valid": True, "description": "Diabetes mellitus tipo 2"}
        )
        mock_ans_client.validate_tuss = AsyncMock(
            return_value={"valid": True, "description": "Consulta em consultorio"}
        )
        task_variables = {
            "suggested_cid10_codes": [{"code": "E11.9"}, {"code": "I10"}],
            "suggested_tuss_codes": [{"code": "10101012"}],
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "all_valid" in result
        assert "validated_cid10" in result
        assert "validated_tuss" in result
        assert "validation_errors" in result
        assert result["all_valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_cid10_bpmn_error(self, worker, mock_ans_client, mock_dmn_service):
        """Invalid CID-10 code triggers BPMN error."""
        # Mock DMN to return errors for invalid codes
        def dmn_error_side_effect(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
            if "cid10_format" in str(table_name):
                return {
                    "validated_cid10": [],
                    "errors": [{"code": "E99.9", "reason": "Invalid format"}]
                }
            return {"errors": []}

        mock_dmn_service.evaluate.side_effect = dmn_error_side_effect
        mock_ans_client.validate_cid10 = AsyncMock(
            return_value={"valid": False, "reason": "Code E99.9 not in CID-10 table"}
        )
        task_variables = {
            "suggested_cid10_codes": [{"code": "E99.9"}],
            "suggested_tuss_codes": [{"code": "10101012"}],
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        from healthcare_platform.shared.domain.exceptions import BpmnErrorException
        with pytest.raises(BpmnErrorException) as exc_info:
            await worker.execute(task_variables)

        assert "INVALID_CID10_CODE" in str(exc_info.value.error_code)

    @pytest.mark.asyncio
    async def test_invalid_tuss_bpmn_error(self, worker, mock_ans_client, mock_dmn_service):
        """Invalid TUSS code triggers BPMN error."""
        # Mock DMN to return errors for invalid TUSS codes
        def dmn_error_side_effect(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
            if "cid10_format" in str(table_name):
                suggested = inputs.get("suggested_cid10_codes", []) if inputs else []
                return {"validated_cid10": suggested, "errors": []}
            elif "tuss_format" in str(table_name):
                return {
                    "format_valid_tuss": [],
                    "errors": [{"code": "99999999", "reason": "Invalid format"}]
                }
            elif "tuss_coverage" in str(table_name):
                return {
                    "validated_tuss": [],
                    "errors": [{"code": "99999999", "reason": "Not covered"}]
                }
            return {"errors": []}

        mock_dmn_service.evaluate.side_effect = dmn_error_side_effect
        mock_ans_client.validate_cid10 = AsyncMock(
            return_value={"valid": True, "description": "Valid"}
        )
        mock_ans_client.validate_tuss = AsyncMock(
            return_value={"valid": False, "reason": "Code 99999999 not in TUSS table"}
        )
        task_variables = {
            "suggested_cid10_codes": [{"code": "E11.9"}],
            "suggested_tuss_codes": [{"code": "99999999"}],
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        from healthcare_platform.shared.domain.exceptions import BpmnErrorException
        with pytest.raises(BpmnErrorException) as exc_info:
            await worker.execute(task_variables)

        assert "INVALID_TUSS_CODE" in str(exc_info.value.error_code)

    @pytest.mark.asyncio
    async def test_partial_validation(self, worker, mock_ans_client, mock_dmn_service):
        """Mix of valid and invalid codes reports all invalid ones."""
        # Mock DMN to return partial validation - with at least one TUSS code to avoid exception
        def dmn_partial_side_effect(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
            if "cid10_format" in str(table_name):
                return {
                    "validated_cid10": [{"code": "E11.9"}],
                    "errors": [{"code": "X99.9", "reason": "Invalid code"}]
                }
            elif "tuss_format" in str(table_name):
                # Return at least one valid TUSS code to avoid BPMN exception
                return {"format_valid_tuss": [{"code": "10101012"}], "errors": []}
            elif "tuss_coverage" in str(table_name):
                return {"validated_tuss": [{"code": "10101012"}], "errors": []}
            return {"errors": []}

        mock_dmn_service.evaluate.side_effect = dmn_partial_side_effect
        call_count = 0

        async def alternating_cid10(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"valid": True, "description": "Valid code"}
            return {"valid": False, "reason": "Invalid code"}

        mock_ans_client.validate_cid10 = AsyncMock(side_effect=alternating_cid10)
        task_variables = {
            "suggested_cid10_codes": [{"code": "E11.9"}, {"code": "X99.9"}],
            "suggested_tuss_codes": [{"code": "10101012"}],
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        # Should complete with errors but not raise exception if some codes are valid
        assert "validation_errors" in result
        assert len(result["validation_errors"]) > 0
        assert result["all_valid"] is False


class TestValidateCodesInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = ValidateCodesInput(
            suggested_cid10_codes=[{"code": "E11.9"}],
            suggested_tuss_codes=[{"code": "10101012"}],
            encounter_id="ENC-001",
            tenant_id="hospital-alpha",
        )
        assert len(inp.suggested_cid10_codes) == 1

    def test_empty_codes_allowed(self):
        # V2 model allows empty lists - validation happens in the worker
        inp = ValidateCodesInput(
            suggested_cid10_codes=[],
            suggested_tuss_codes=[],
            encounter_id="ENC-001",
            tenant_id="hospital-alpha",
        )
        assert len(inp.suggested_cid10_codes) == 0


class TestValidateCodesOutput:
    """Tests for output model."""

    def test_all_valid_output(self):
        out = ValidateCodesOutput(
            all_valid=True,
            validated_cid10=[],
            validated_tuss=[],
            validation_errors=[],
        )
        assert out.all_valid is True
        assert len(out.validation_errors) == 0
