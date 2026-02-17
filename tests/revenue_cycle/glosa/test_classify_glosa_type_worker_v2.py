"""Tests for classify_glosa_type_worker_v2."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.glosa.workers import ClassifyGlosaTypeWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

# Import fixtures
pytest_plugins = ["tests.fixtures.workers"]


class TestClassifyGlosaTypeWorkerV2:
    """Test suite for ClassifyGlosaTypeWorkerV2."""

    def _make_context(self, variables=None):
        """Helper to create TaskContext."""
        return TaskContext(
            task_id="task_test_classify",
            process_instance_id="proc_test_classify",
            tenant_id="HOSPITAL_TEST",
            variables=variables or {},
            worker_id="glosa.classify_type",
        )

    def test_prosseguir_normal_classification(self, mock_dmn_service, mock_metrics):
        """Test normal glosa classification - PROSSEGUIR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Classificação concluída",
            "risco": "BAIXO",
            "glosaType": "ADMINISTRATIVE",
            "glosaExtent": "PARTIAL",
        }

        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {
                    "reason_code": "MISSING_AUTH",
                    "denied_amount": 1000.00,
                    "original_amount": 5000.00,
                }
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["classifiedGlosas"]) == 1
        assert result.variables["classifiedGlosas"][0]["glosa_type"] == "administrative"
        assert result.variables["hasAdministrative"] is True

    def test_total_glosa_requires_review(self, mock_dmn_service, mock_metrics):
        """Test TOTAL glosa classification triggers review."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Glosa TOTAL",
            "risco": "ALTO",
            "glosaType": "TOTAL",
            "glosaExtent": "TOTAL",
        }

        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {
                    "reason_code": "NOT_COVERED",
                    "denied_amount": 10000.00,
                    "original_amount": 10000.00,
                }
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True
        assert "TOTAL" in result.variables["reviewAction"]

    def test_empty_glosas_returns_empty_result(self, mock_dmn_service, mock_metrics):
        """Test empty glosa list returns empty result."""
        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["classifiedGlosas"]) == 0
        assert result.variables["hasAdministrative"] is False
        assert result.variables["hasTechnical"] is False

    def test_reason_code_filter(self, mock_dmn_service, mock_metrics):
        """Test filtering by reason code."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "OK",
            "risco": "BAIXO",
            "glosaType": "TECHNICAL",
            "glosaExtent": "PARTIAL",
        }

        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {"reason_code": "WRONG_CODE", "denied_amount": 500, "original_amount": 1000},
                {"reason_code": "MISSING_AUTH", "denied_amount": 300, "original_amount": 800},
            ],
            "reasonCode": "WRONG_CODE",  # Filter for this only
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["classifiedGlosas"]) == 1
        assert result.variables["classifiedGlosas"][0]["reason_code"] == "WRONG_CODE"

    def test_type_distribution_calculation(self, mock_dmn_service, mock_metrics):
        """Test glosa type distribution calculation."""
        call_count = [0]

        def dmn_side_effect(*args, **kwargs):
            call_count[0] += 1
            glosa_type = "ADMINISTRATIVE" if call_count[0] % 2 == 1 else "TECHNICAL"
            return {
                "resultado": "PROSSEGUIR",
                "acao": "OK",
                "risco": "BAIXO",
                "glosaType": glosa_type,
                "glosaExtent": "PARTIAL",
            }

        mock_dmn_service.evaluate.side_effect = dmn_side_effect

        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {"reason_code": "MISSING_AUTH", "denied_amount": 100, "original_amount": 200},
                {"reason_code": "WRONG_CODE", "denied_amount": 150, "original_amount": 300},
                {"reason_code": "DUPLICATE_CHARGE", "denied_amount": 200, "original_amount": 400},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        distribution = result.variables["glosaTypeDistribution"]
        assert distribution.get("administrative", 0) == 2
        assert distribution.get("technical", 0) == 1

    def test_denial_ratio_calculation(self, mock_dmn_service, mock_metrics):
        """Test denial ratio is calculated correctly."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "OK",
            "risco": "BAIXO",
            "glosaType": "PARTIAL",
            "glosaExtent": "PARTIAL",
        }

        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {"reason_code": "TEST", "denied_amount": 2500, "original_amount": 5000},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["classifiedGlosas"][0]["denial_ratio"] == 0.5

    def test_legacy_5_output_schema(self, mock_dmn_service, mock_metrics):
        """Test compatibility with legacy 5-output DMN schema."""
        mock_dmn_service.evaluate.return_value = {
            "observacao": "Classificado",
            "acaoRecomendada": "Continuar",
            "riscoDenial": "MEDIO",
            "glosaType": "TECHNICAL",
            "glosaExtent": "PARTIAL",
        }

        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {"reason_code": "INCOMPATIBLE_PROCEDURE", "denied_amount": 700, "original_amount": 1400},
            ],
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["hasTechnical"] is True

    def test_dmn_error_handling(self, mock_dmn_service_error, mock_metrics):
        """Test error handling when DMN evaluation fails - uses fallback classification."""
        worker = ClassifyGlosaTypeWorkerV2(
            dmn_service=mock_dmn_service_error,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "glosaItems": [
                {"reason_code": "TEST", "denied_amount": 100, "original_amount": 200},
            ],
        })

        result = worker.execute(context)

        # DMN errors are caught and fallback is used - should succeed
        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["classifiedGlosas"]) == 1
        # Fallback classifies based on denial ratio (100/200 = 0.5 < 1.0, so ADMINISTRATIVE)
        assert result.variables["classifiedGlosas"][0]["glosa_type"] == "administrative"
