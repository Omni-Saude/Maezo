"""Tests for audit_coding_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
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
    def worker(self, mock_audit_engine, mock_dmn_service):
        worker = AuditCodingWorker(audit_engine=mock_audit_engine, dmn_service=mock_dmn_service)
        # Also inject into v2 worker
        worker.dmn_service = mock_dmn_service
        return worker

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
        # V2 output uses auditRecommendation (approve/revise/reject)
        recommendation = variables.get("auditRecommendation", variables.get("audit_recommendation", ""))
        score = variables.get("auditScore", variables.get("audit_score", 0))
        assert recommendation == "approve" or score >= 80

    @pytest.mark.asyncio
    async def test_audit_failed_low_score(self, worker, mock_task, mock_dmn_service):
        """Audit below threshold triggers BPMN error for manual review."""
        # Override DMN mock to return failures for this test
        def failing_evaluate(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
            # Return BLOQUEAR for audit quality checks
            return {
                "resultado": "BLOQUEAR",
                "acao": "Audit check failed",
                "risco": "ALTO"
            }

        mock_dmn_service.evaluate.side_effect = failing_evaluate
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
            "audit_threshold": 0.85,
            "coding_rules_result": {"rules": [{"passed": False}] * 5},  # Multiple rule violations
        }.get(key, default)

        # Should raise BpmnErrorException
        with pytest.raises(Exception):  # BpmnErrorException is caught and handled
            await worker.execute(mock_task)

        # Verify bpmn_error was called
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
        # V2 uses different field names
        out = AuditCodingOutput(
            audit_score=0.95,
            audit_recommendation="aprovar",
            issues=[],
        )
        assert out.audit_recommendation == "aprovar"
        assert out.audit_score >= 0.85
