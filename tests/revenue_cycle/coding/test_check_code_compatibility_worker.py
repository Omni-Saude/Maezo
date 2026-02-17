"""Tests for check_code_compatibility_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
    CheckCodeCompatibilityWorker,
    register_worker,
)
from healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker_v2 import (
    CheckCodeCompatibilityOutputV2 as CheckCodeCompatibilityOutput,
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
        # V2 worker creates its own DMN service, we'll need to patch it
        return CheckCodeCompatibilityWorker(
            compatibility_engine=mock_compatibility_engine,
            ans_client=mock_ans_client,
        )

    @pytest.mark.asyncio
    async def test_compatible_codes(self, worker):
        """All codes are compatible and task completes normally."""
        task_variables = {
            "validatedCid10": [{"code": "E11.9"}, {"code": "I10"}],
            "validatedTuss": [{"code": "10101012"}],
            "encounterId": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "compatible" in result
        assert "incompatibilities" in result
        assert "warnings" in result
        assert result["compatible"] is True

    @pytest.mark.asyncio
    async def test_incompatible_codes_bpmn_error(
        self, worker, mock_compatibility_engine
    ):
        """Incompatible diagnosis-procedure pair triggers BPMN error."""
        # Mock DMN to return incompatibility
        def dmn_incompatible_side_effect(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
            if "incompatible_matrix" in str(table_name):
                return {
                    "resultado": "BLOQUEAR",
                    "acao": "Incompatível",
                    "cid10": "Z00.0",
                    "tuss": "30911017"
                }
            return {"resultado": "PROSSEGUIR"}

        worker.dmn_service.evaluate = MagicMock(side_effect=dmn_incompatible_side_effect)
        mock_compatibility_engine.check_dx_proc_compatibility = AsyncMock(return_value={
            "compatible": False,
            "warnings": [],
            "incompatible_pairs": [
                {"diagnosis": "Z00.0", "procedure": "30911017", "reason": "Procedure not indicated for diagnosis"},
            ],
        })
        task_variables = {
            "validatedCid10": [{"code": "Z00.0"}],
            "validatedTuss": [{"code": "30911017"}],
            "encounterId": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        from healthcare_platform.shared.domain.exceptions import IncompatibleCodes
        with pytest.raises(IncompatibleCodes):
            await worker.execute(task_variables)

    @pytest.mark.asyncio
    async def test_warnings_generated(self, worker, mock_compatibility_engine):
        """Compatible codes with warnings complete but include warning data."""
        # Mock DMN to return warnings
        def dmn_warning_side_effect(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
            if "warning_pairs" in str(table_name):
                return {
                    "resultado": "REVISAR",
                    "acao": "Review required - rare combination",
                    "Decisao": "Revisar"
                }
            return {"resultado": "PROSSEGUIR"}

        worker.dmn_service.evaluate = MagicMock(side_effect=dmn_warning_side_effect)
        mock_compatibility_engine.check_dx_proc_compatibility = AsyncMock(return_value={
            "compatible": True,
            "warnings": [
                "Procedure 10101012 rarely used with E11.9 - verify clinical justification",
            ],
            "incompatible_pairs": [],
        })
        task_variables = {
            "validatedCid10": [{"code": "E11.9"}],
            "validatedTuss": [{"code": "10101012"}],
            "encounterId": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "warnings" in result
        assert len(result["warnings"]) >= 1
        assert result["compatible"] is True

    @pytest.mark.asyncio
    async def test_empty_code_lists(self, worker):
        """Empty code lists trigger BPMN error or complete with no-op."""
        task_variables = {
            "validatedCid10": [],
            "validatedTuss": [],
            "encounterId": "ENC-001",
            "tenant_id": "hospital-alpha",
        }

        from healthcare_platform.shared.domain.exceptions import CodingException
        with pytest.raises(CodingException):
            await worker.execute(task_variables)


class TestCheckCodeCompatibilityInput:
    """Tests for input model - removed as V2 worker doesn't export Input model."""

    def test_valid_input(self):
        # V2 worker doesn't export an Input model, it uses dict directly
        # This test is for backward compatibility only
        pass


class TestCheckCodeCompatibilityOutput:
    """Tests for output model."""

    def test_compatible_output(self):
        out = CheckCodeCompatibilityOutput(
            compatible=True,
            warnings=[],
            incompatible_pairs=[],
        )
        assert out.compatible is True
