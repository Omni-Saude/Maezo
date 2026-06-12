"""Tests for escalate_to_supervisor_worker_v2."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.glosa.workers import EscalateToSupervisorWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

# Import fixtures
pytest_plugins = ["tests.fixtures.workers"]


class TestEscalateToSupervisorWorkerV2:
    """Test suite for EscalateToSupervisorWorkerV2."""

    def _make_context(self, variables=None):
        """Helper to create TaskContext."""
        return TaskContext(
            task_id="task_test_escalate",
            process_instance_id="proc_test_escalate",
            tenant_id="HOSPITAL_TEST",
            variables=variables or {},
            worker_id="glosa.escalate_to_supervisor",
        )

    def test_prosseguir_normal_escalation(self, mock_dmn_service, mock_metrics):
        """Test normal escalation - PROSSEGUIR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Escalar para revisão",
            "risco": "MEDIO",
            "priority": "MEDIUM",
            "assignedTeam": "Coordenação de Glosas",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [
                {"glosa_type": "ADMINISTRATIVE"},
                {"glosa_type": "TECHNICAL"},
            ],
            "totalImpactBRL": "7500.00",
            "claimId": "CLAIM_123",
            "escalationReason": "Múltiplas glosas administrativas",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert "escalationId" in result.variables
        assert result.variables["priority"] == "MEDIUM"
        assert result.variables["assignedTeam"] == "Coordenação de Glosas"
        assert result.variables.get("requiresHumanDecision") is True

    def test_bloquear_critical_escalation(self, mock_dmn_service, mock_metrics):
        """Test critical escalation - BLOQUEAR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "CRÍTICO: Escalar imediatamente para diretoria",
            "risco": "CRITICO",
            "priority": "CRITICAL",
            "assignedTeam": "Diretoria Médica e Financeira",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [
                {"glosa_type": "TOTAL", "glosa_extent": "TOTAL"},
            ],
            "totalImpactBRL": "75000.00",
            "claimId": "CLAIM_456",
            "escalationReason": "Glosa TOTAL de alto valor",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CRITICAL_ESCALATION"
        assert "CRÍTICO" in result.error_message
        assert result.variables.get("requiresImmediateAction") is True

    def test_revisar_needs_review_before_escalation(self, mock_dmn_service, mock_metrics):
        """Test REVISAR - needs additional review."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR",
            "acao": "Revisar análise antes de escalar",
            "risco": "MEDIO",
            "priority": "MEDIUM",
            "assignedTeam": "Supervisão de Auditoria",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [
                {"glosa_type": "TECHNICAL"},
            ],
            "totalImpactBRL": "12000.00",
            "claimId": "CLAIM_789",
            "escalationReason": "Padrão técnico detectado",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True
        assert "reviewAction" in result.variables

    def test_priority_determination_fallback(self, mock_dmn_service, mock_metrics):
        """Test priority determination when DMN doesn't provide it."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Escalar",
            "risco": "MEDIO",
            # No priority/assignedTeam - should use fallback
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [{"glosa_type": "PARTIAL"}],
            "totalImpactBRL": "60000.00",  # > 50k = CRITICAL
            "claimId": "CLAIM_ABC",
            "escalationReason": "Alto impacto",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["priority"] == "CRITICAL"
        assert "Diretoria" in result.variables["assignedTeam"]

    def test_total_glosa_team_assignment(self, mock_dmn_service, mock_metrics):
        """Test team assignment for TOTAL glosa."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Escalar",
            "risco": "ALTO",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [
                {"glosa_type": "TOTAL", "glosa_extent": "TOTAL"},
            ],
            "totalImpactBRL": "15000.00",
            "claimId": "CLAIM_TOTAL",
            "escalationReason": "Conta totalmente glosada",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert "Diretoria" in result.variables["assignedTeam"]
        assert result.variables["escalationPackage"]["hasTotalGlosa"] is True

    def test_escalation_package_structure(self, mock_dmn_service, mock_metrics):
        """Test escalation package contains all required fields."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Escalar para análise",
            "risco": "MEDIO",
            "priority": "HIGH",
            "assignedTeam": "Supervisão de Auditoria",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [{"glosa_type": "ADMINISTRATIVE"}],
            "totalImpactBRL": "8000.00",
            "claimId": "CLAIM_PKG",
            "escalationReason": "Teste estrutura",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        package = result.variables["escalationPackage"]
        assert "escalationId" in package
        assert "claimId" in package
        assert "escalationDate" in package
        assert "priority" in package
        assert "assignedTeam" in package
        assert "totalImpact" in package
        assert "glosaCount" in package

    def test_legacy_5_output_schema(self, mock_dmn_service, mock_metrics):
        """Test compatibility with legacy 5-output DMN schema."""
        mock_dmn_service.evaluate.return_value = {
            "observacao": "Escalar",
            "acaoRecomendada": "Revisão manual",
            "riscoDenial": "ALTO",
            "priority": "HIGH",
            "assignedTeam": "Supervisão",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [{"glosa_type": "TECHNICAL"}],
            "totalImpactBRL": "11000.00",
            "claimId": "CLAIM_LEGACY",
            "escalationReason": "Teste legacy",
        })

        result = worker.execute(context)

        # Legacy schema defaults to REVISAR
        assert result.status == TaskStatus.SUCCESS

    def test_dmn_error_handling(self, mock_dmn_service_error, mock_metrics):
        """Test error handling when DMN evaluation fails."""
        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service_error,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [{"glosa_type": "PARTIAL"}],
            "totalImpactBRL": "5000.00",
            "claimId": "CLAIM_ERROR",
            "escalationReason": "Teste erro",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_ESCALATION_PROCESSING"

    def test_multiple_glosas_count_threshold(self, mock_dmn_service, mock_metrics):
        """Test escalation with high glosa count (>10)."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Múltiplas glosas",
            "risco": "MEDIO",
        }

        worker = EscalateToSupervisorWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        # Create 12 glosas
        glosas = [{"glosa_type": "PARTIAL"} for _ in range(12)]

        context = self._make_context({
            "analyzedGlosas": glosas,
            "totalImpactBRL": "4500.00",  # Below MEDIUM threshold
            "claimId": "CLAIM_COUNT",
            "escalationReason": "Múltiplas glosas",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        # Should be MEDIUM due to count > 10
        assert result.variables["priority"] == "MEDIUM"
