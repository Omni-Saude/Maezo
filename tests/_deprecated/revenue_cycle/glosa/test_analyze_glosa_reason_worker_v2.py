"""Tests for analyze_glosa_reason_worker_v2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from healthcare_platform.revenue_cycle.glosa.workers import AnalyzeGlosaReasonWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

# Import fixtures
pytest_plugins = ["tests.fixtures.workers"]


class TestAnalyzeGlosaReasonWorkerV2:
    """Test suite for AnalyzeGlosaReasonWorkerV2."""

    def _make_context(self, variables=None):
        """Helper to create TaskContext."""
        return TaskContext(
            task_id="task_test_analyze",
            process_instance_id="proc_test_analyze",
            tenant_id="HOSPITAL_TEST",
            variables=variables or {},
            worker_id="glosa.analyze_reason",
        )

    def test_prosseguir_normal_analysis(self, mock_dmn_service, mock_metrics):
        """Test normal glosa reason analysis - PROSSEGUIR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Análise concluída",
            "risco": "BAIXO",
            "reasonCode": "MISSING_DOCUMENTATION",
            "reasonDescription": "Documentação ausente",
        }

        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {
                    "glosa_type": "ADMINISTRATIVE",
                    "description": "Falta documentação",
                    "denied_amount": 1000.00,
                }
            ],
            "claimId": "CLAIM_123",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["analyzedGlosas"]) == 1
        assert result.variables["analyzedGlosas"][0]["reason_code"] == "MISSING_DOCUMENTATION"
        assert "reasonDistribution" in result.variables
        assert "rootCausePatterns" in result.variables

    def test_critico_with_patterns(self, mock_dmn_service, mock_metrics):
        """Test critical risk with patterns - BPMN_ERROR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Padrão detectado",
            "risco": "CRITICO",
            "reasonCode": "MISSING_AUTH",
            "reasonDescription": "Autorização ausente",
        }

        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        # Create 5 glosas with same reason to trigger pattern
        glosas = [
            {
                "glosa_type": "ADMINISTRATIVE",
                "description": f"Falta autorização {i}",
                "denied_amount": 500.00,
            }
            for i in range(5)
        ]

        context = self._make_context({
            "classifiedGlosas": glosas,
            "claimId": "CLAIM_456",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CRITICAL_PATTERN"
        assert "Padrão crítico" in result.error_message

    def test_alto_risco_requires_review(self, mock_dmn_service, mock_metrics):
        """Test high risk with patterns - requires review."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR",
            "acao": "Revisar padrão",
            "risco": "ALTO",
            "reasonCode": "DUPLICATE_CHARGE",
            "reasonDescription": "Cobrança duplicada",
        }

        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        # Create 4 glosas to trigger pattern
        glosas = [
            {
                "glosa_type": "ADMINISTRATIVE",
                "description": f"Duplicado {i}",
                "denied_amount": 300.00,
            }
            for i in range(4)
        ]

        context = self._make_context({
            "classifiedGlosas": glosas,
            "claimId": "CLAIM_789",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True
        assert len(result.variables["rootCausePatterns"]) > 0

    def test_no_glosas_error(self, mock_dmn_service, mock_metrics):
        """Test error when no glosas provided."""
        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [],
            "claimId": "CLAIM_EMPTY",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_NO_GLOSAS"

    def test_legacy_5_output_schema(self, mock_dmn_service, mock_metrics):
        """Test compatibility with legacy 5-output DMN schema."""
        mock_dmn_service.evaluate.return_value = {
            "observacao": "Análise ok",
            "acaoRecomendada": "Continuar processo",
            "riscoDenial": "MEDIO",
            "reasonCode": "WRONG_CODE",
            "reasonDescription": "Código incorreto",
        }

        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {
                    "glosa_type": "TECHNICAL",
                    "description": "Código errado",
                    "denied_amount": 750.00,
                }
            ],
            "claimId": "CLAIM_LEGACY",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert "maxRisco" in result.variables

    def test_dmn_error_handling(self, mock_dmn_service_error, mock_metrics):
        """Test error handling when DMN evaluation fails."""
        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service_error,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {
                    "glosa_type": "ADMINISTRATIVE",
                    "description": "Test",
                    "denied_amount": 100.00,
                }
            ],
            "claimId": "CLAIM_ERROR",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_REASON_ANALYSIS_PROCESSING"

    def test_pattern_identification_threshold(self, mock_dmn_service, mock_metrics):
        """Test pattern identification with threshold (3+ occurrences)."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "OK",
            "risco": "MEDIO",
            "reasonCode": "EXCEEDS_QUANTITY",
            "reasonDescription": "Quantidade excedida",
        }

        worker = AnalyzeGlosaReasonWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        # Exactly 3 glosas - should trigger pattern
        glosas = [
            {
                "glosa_type": "TECHNICAL",
                "description": f"Quantidade {i}",
                "denied_amount": 200.00,
            }
            for i in range(3)
        ]

        context = self._make_context({
            "classifiedGlosas": glosas,
            "claimId": "CLAIM_THRESHOLD",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        patterns = result.variables["rootCausePatterns"]
        assert len(patterns) >= 1
        assert patterns[0]["occurrences"] == 3
