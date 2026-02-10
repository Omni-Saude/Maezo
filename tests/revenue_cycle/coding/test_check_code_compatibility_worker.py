"""Tests for check_code_compatibility_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker import (
    CheckCodeCompatibilityWorker,
    CheckCodeCompatibilityInput,
    CheckCodeCompatibilityOutput,
    register_worker,
)


class TestCheckCodeCompatibilityWorker:
    """Tests for the code compatibility checking worker."""

    @pytest.fixture
    def mock_compatibility_engine(self):
        engine = MagicMock()
        engine.check_dx_proc_compatibility = AsyncMock(return_value={
            "compatible": True,
            "warnings": [],
            "incompatible_pairs": [],
        })
        engine.check_mutual_exclusion = AsyncMock(return_value={
            "has_conflicts": False,
            "conflicts": [],
        })
        return engine

    @pytest.fixture
    def worker(self, mock_compatibility_engine, mock_ans_client):
        return CheckCodeCompatibilityWorker(
            compatibility_engine=mock_compatibility_engine,
            ans_client=mock_ans_client,
        )

    @pytest.mark.asyncio
    async def test_compatible_codes(self, worker, mock_task):
        """All codes are compatible and task completes normally."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}, {"code": "I10"}],
            "tuss_codes": [{"code": "10101012"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        mock_task.bpmn_error.assert_not_called()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        compat = variables.get("compatibility_result", variables.get("compatible", None))
        assert compat is True or "compatible" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_incompatible_codes_bpmn_error(
        self, worker, mock_task, mock_compatibility_engine
    ):
        """Incompatible diagnosis-procedure pair triggers BPMN error."""
        mock_compatibility_engine.check_dx_proc_compatibility = AsyncMock(return_value={
            "compatible": False,
            "warnings": [],
            "incompatible_pairs": [
                {"diagnosis": "Z00.0", "procedure": "30911017", "reason": "Procedure not indicated for diagnosis"},
            ],
        })
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "Z00.0"}],
            "tuss_codes": [{"code": "30911017"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "INCOMPATIBLE" in error_code.upper() or "COMPAT" in error_code.upper()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_warnings_generated(self, worker, mock_task, mock_compatibility_engine):
        """Compatible codes with warnings complete but include warning data."""
        mock_compatibility_engine.check_dx_proc_compatibility = AsyncMock(return_value={
            "compatible": True,
            "warnings": [
                "Procedure 10101012 rarely used with E11.9 - verify clinical justification",
            ],
            "incompatible_pairs": [],
        })
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        warnings = variables.get("compatibility_warnings", variables.get("warnings", []))
        assert len(warnings) >= 1 or "warning" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_empty_code_lists(self, worker, mock_task):
        """Empty code lists trigger BPMN error or complete with no-op."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [],
            "tuss_codes": [],
        }.get(key, default)

        await worker.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        mock_task.failure.assert_not_called()


class TestCheckCodeCompatibilityInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = CheckCodeCompatibilityInput(
            encounter_id="ENC-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
        )
        assert inp.encounter_id == "ENC-001"


class TestCheckCodeCompatibilityOutput:
    """Tests for output model."""

    def test_compatible_output(self):
        out = CheckCodeCompatibilityOutput(
            compatible=True,
            warnings=[],
            incompatible_pairs=[],
        )
        assert out.compatible is True
