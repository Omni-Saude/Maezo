"""Tests for calculate_glosa_impact_worker_v2."""
from __future__ import annotations

import pytest
from decimal import Decimal

from healthcare_platform.revenue_cycle.glosa.workers import CalculateGlosaImpactWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

# Import fixtures
pytest_plugins = ["tests.fixtures.workers"]


class TestCalculateGlosaImpactWorkerV2:
    """Test suite for CalculateGlosaImpactWorkerV2."""

    def _make_context(self, variables=None):
        """Helper to create TaskContext."""
        return TaskContext(
            task_id="task_test_impact",
            process_instance_id="proc_test_impact",
            tenant_id="HOSPITAL_TEST",
            variables=variables or {},
            worker_id="glosa.calculate_impact",
        )

    def test_prosseguir_normal_impact(self, mock_dmn_service, mock_metrics):
        """Test normal impact calculation - PROSSEGUIR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Impacto dentro do esperado",
            "risco": "BAIXO",
            "recoveryRate": 0.7,
        }

        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {
                    "glosa_type": "administrative",
                    "denied_amount": 1000.00,
                    "original_amount": 5000.00,
                },
                {
                    "glosa_type": "technical",
                    "denied_amount": 500.00,
                    "original_amount": 2000.00,
                }
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["totalImpactBRL"] == 1500.00
        assert result.variables["denialPercentage"] > 0
        # Recovery: 1000 * 0.80 (admin) + 500 * 0.60 (tech) = 800 + 300 = 1100
        assert result.variables["recoveryPotentialBRL"] == 1100.00

    def test_bloquear_high_impact(self, mock_dmn_service, mock_metrics):
        """Test high impact - BLOQUEAR (escalate)."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Impacto crítico - escalar imediatamente",
            "risco": "ALTO",
            "recoveryRate": 0.3,
        }

        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {
                    "glosa_type": "total",
                    "denied_amount": 50000.00,
                    "original_amount": 50000.00,
                }
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_HIGH_IMPACT"
        assert "crítico" in result.error_message.lower()

    def test_revisar_medium_impact(self, mock_dmn_service, mock_metrics):
        """Test medium impact - REVISAR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR",
            "acao": "Revisar estratégia de recuperação",
            "risco": "MEDIO",
            "recoveryRate": 0.5,
        }

        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {
                    "glosa_type": "partial",
                    "denied_amount": 10000.00,
                    "original_amount": 20000.00,
                }
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True
        assert "reviewAction" in result.variables

    def test_no_glosas_error(self, mock_dmn_service, mock_metrics):
        """Test error when no glosas provided."""
        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_NO_GLOSAS"

    def test_impact_by_type_aggregation(self, mock_dmn_service, mock_metrics):
        """Test aggregation by glosa type."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "OK",
            "risco": "BAIXO",
            "recoveryRate": 0.6,
        }

        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {"glosa_type": "administrative", "denied_amount": 1000, "original_amount": 2000},
                {"glosa_type": "administrative", "denied_amount": 500, "original_amount": 1000},
                {"glosa_type": "technical", "denied_amount": 2000, "original_amount": 4000},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        impact_by_type = result.variables["impactByType"]
        assert impact_by_type["administrative"] == 1500.00
        assert impact_by_type["technical"] == 2000.00

    def test_legacy_5_output_schema(self, mock_dmn_service, mock_metrics):
        """Test compatibility with legacy 5-output DMN schema."""
        mock_dmn_service.evaluate.return_value = {
            "observacao": "Impacto moderado",
            "acaoRecomendada": "Continuar",
            "riscoDenial": "MEDIO",
            "recoveryRate": 0.55,
        }

        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {"glosa_type": "partial", "denied_amount": 3000, "original_amount": 6000},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        # recoveryRate from DMN is ignored, worker calculates it: 3000 * 0.50 (partial rate) = 1500
        # average_recovery_rate = 1500 / 3000 = 0.50
        assert result.variables["recoveryRate"] == 0.50

    def test_dmn_error_handling(self, mock_dmn_service_error, mock_metrics):
        """Test error handling when DMN evaluation fails."""
        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service_error,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {"glosa_type": "partial", "denied_amount": 100, "original_amount": 200},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_IMPACT_CALCULATION_PROCESSING"

    def test_zero_original_amount_handling(self, mock_dmn_service, mock_metrics):
        """Test handling of zero original amount (edge case)."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "OK",
            "risco": "BAIXO",
            "recoveryRate": 0.5,
        }

        worker = CalculateGlosaImpactWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "classifiedGlosas": [
                {"glosa_type": "partial", "denied_amount": 100, "original_amount": 0},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["denialPercentage"] == 0.0
