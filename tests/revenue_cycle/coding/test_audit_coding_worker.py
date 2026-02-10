"""Tests for audit_coding_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker import (
    AuditCodingWorker,
    AuditCodingInput,
    AuditCodingOutput,
    register_worker,
)


class TestAuditCodingWorker:
    """Tests for the coding audit worker."""

    @pytest.fixture
    def mock_audit_engine(self):
        engine = MagicMock()
        engine.audit_encounter_coding = AsyncMock(return_value={
            "score": 0.95,
            "status": "approved",
            "findings": [],
            "reviewer": "AUTO-AUDIT",
        })
        return engine

    @pytest.fixture
    def worker(self, mock_audit_engine):
        return AuditCodingWorker(audit_engine=mock_audit_engine)

    @pytest.mark.asyncio
    async def test_audit_approved(self, worker, mock_task):
        """Audit passes with score above threshold and task completes."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
            "coding_rules_result": {"all_passed": True},
            "audit_threshold": 0.85,
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        status = variables.get("audit_status", variables.get("status", ""))
        assert status == "approved" or "approved" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_audit_failed_low_score(self, worker, mock_task):
        """Audit below threshold triggers BPMN error for manual review."""
        mock_audit_engine = MagicMock()
        mock_audit_engine.audit_encounter_coding = AsyncMock(return_value={
            "score": 0.55,
            "status": "failed",
            "findings": [
                {"type": "MISSING_DX", "message": "Primary diagnosis not supported by notes"},
            ],
            "reviewer": "AUTO-AUDIT",
        })
        worker_fail = AuditCodingWorker(audit_engine=mock_audit_engine)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
            "audit_threshold": 0.85,
        }.get(key, default)

        await worker_fail.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "AUDIT" in error_code.upper() or "FAILED" in error_code.upper()

    @pytest.mark.asyncio
    async def test_audit_revision_required(self, worker, mock_task):
        """Audit with borderline score triggers revision workflow."""
        mock_audit_engine = MagicMock()
        mock_audit_engine.audit_encounter_coding = AsyncMock(return_value={
            "score": 0.80,
            "status": "revision_required",
            "findings": [
                {"type": "INSUFFICIENT_JUSTIFICATION", "message": "Additional documentation needed"},
            ],
            "reviewer": "AUTO-AUDIT",
        })
        worker_rev = AuditCodingWorker(audit_engine=mock_audit_engine)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
            "audit_threshold": 0.85,
        }.get(key, default)

        await worker_rev.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        if mock_task.complete.called:
            call_args = mock_task.complete.call_args
            variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
            assert "revision" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_audit_with_findings(self, worker, mock_task):
        """Audit findings are included in output even when approved."""
        mock_audit_engine = MagicMock()
        mock_audit_engine.audit_encounter_coding = AsyncMock(return_value={
            "score": 0.90,
            "status": "approved",
            "findings": [
                {"type": "INFO", "message": "Consider adding secondary diagnosis for completeness"},
            ],
            "reviewer": "AUTO-AUDIT",
        })
        worker_findings = AuditCodingWorker(audit_engine=mock_audit_engine)
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
            "audit_threshold": 0.85,
        }.get(key, default)

        await worker_findings.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        findings = variables.get("audit_findings", variables.get("findings", []))
        assert len(findings) >= 1 or "finding" in str(variables).lower()


class TestAuditCodingInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = AuditCodingInput(
            encounter_id="ENC-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
        )
        assert inp.encounter_id == "ENC-001"


class TestAuditCodingOutput:
    """Tests for output model."""

    def test_approved_output(self):
        out = AuditCodingOutput(
            score=0.95,
            status="approved",
            findings=[],
        )
        assert out.status == "approved"
        assert out.score >= 0.85
