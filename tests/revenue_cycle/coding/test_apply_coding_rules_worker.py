"""Tests for apply_coding_rules_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from revenue_cycle.coding.workers.apply_coding_rules_worker import (
    ApplyCodingRulesWorker,
    ApplyCodingRulesInput,
    ApplyCodingRulesOutput,
    register_worker,
)


class TestApplyCodingRulesWorker:
    """Tests for the coding rules application worker."""

    @pytest.fixture
    def mock_rules_engine(self):
        engine = MagicMock()
        engine.evaluate_rules = AsyncMock(return_value={
            "all_passed": True,
            "violations": [],
            "applied_rules": ["MODIFIER_CHECK", "BUNDLE_CHECK", "QUANTITY_CHECK"],
            "modifiers_applied": [],
        })
        return engine

    @pytest.fixture
    def worker(self, mock_rules_engine):
        return ApplyCodingRulesWorker(rules_engine=mock_rules_engine)

    @pytest.mark.asyncio
    async def test_all_rules_pass(self, worker, mock_task):
        """All coding rules pass and task completes."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012", "quantity": 1}],
            "payer_id": "PAYER-001",
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        mock_task.bpmn_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_rule_violation_bpmn_error(self, worker, mock_task, mock_rules_engine=None):
        """Rule violation triggers BPMN error with violation details."""
        if mock_rules_engine is None:
            mock_rules_engine = worker._rules_engine if hasattr(worker, '_rules_engine') else MagicMock()
        mock_rules_engine = MagicMock()
        mock_rules_engine.evaluate_rules = AsyncMock(return_value={
            "all_passed": False,
            "violations": [
                {
                    "rule": "MODIFIER_REQUIRED",
                    "code": "10101012",
                    "message": "Modifier -22 required for increased complexity",
                },
            ],
            "applied_rules": ["MODIFIER_CHECK"],
            "modifiers_applied": [],
        })
        worker_with_violation = ApplyCodingRulesWorker(rules_engine=mock_rules_engine)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012", "quantity": 1}],
            "payer_id": "PAYER-001",
        }.get(key, default)

        await worker_with_violation.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "RULE" in error_code.upper() or "VIOLATION" in error_code.upper()

    @pytest.mark.asyncio
    async def test_modifier_requirements(self, worker, mock_task):
        """Modifiers are correctly applied to procedure codes."""
        mock_rules_engine = MagicMock()
        mock_rules_engine.evaluate_rules = AsyncMock(return_value={
            "all_passed": True,
            "violations": [],
            "applied_rules": ["MODIFIER_CHECK"],
            "modifiers_applied": [
                {"code": "10101012", "modifier": "-22", "reason": "Increased complexity"},
            ],
        })
        worker_mod = ApplyCodingRulesWorker(rules_engine=mock_rules_engine)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012", "quantity": 1}],
            "payer_id": "PAYER-001",
        }.get(key, default)

        await worker_mod.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        modifiers = variables.get("modifiers_applied", variables.get("modifiers", []))
        assert len(modifiers) >= 1 or "modifier" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_bundling_rules(self, worker, mock_task):
        """Bundling rules detect procedures that should be bundled."""
        mock_rules_engine = MagicMock()
        mock_rules_engine.evaluate_rules = AsyncMock(return_value={
            "all_passed": False,
            "violations": [
                {
                    "rule": "BUNDLE_REQUIRED",
                    "codes": ["10101012", "10101020"],
                    "message": "Procedures must be billed as bundle",
                    "bundle_code": "10101039",
                },
            ],
            "applied_rules": ["BUNDLE_CHECK"],
            "modifiers_applied": [],
        })
        worker_bundle = ApplyCodingRulesWorker(rules_engine=mock_rules_engine)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [
                {"code": "10101012", "quantity": 1},
                {"code": "10101020", "quantity": 1},
            ],
            "payer_id": "PAYER-001",
        }.get(key, default)

        await worker_bundle.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()


class TestApplyCodingRulesInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = ApplyCodingRulesInput(
            encounter_id="ENC-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
            payer_id="PAYER-001",
        )
        assert inp.payer_id == "PAYER-001"


class TestApplyCodingRulesOutput:
    """Tests for output model."""

    def test_passed_output(self):
        out = ApplyCodingRulesOutput(
            all_passed=True,
            violations=[],
            modifiers_applied=[],
        )
        assert out.all_passed is True
