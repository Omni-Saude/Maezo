"""Tests for check_appeal_eligibility_worker_v2."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from healthcare_platform.revenue_cycle.glosa.workers import CheckAppealEligibilityWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

# Import fixtures
pytest_plugins = ["tests.fixtures.workers"]


class TestCheckAppealEligibilityWorkerV2:
    """Test suite for CheckAppealEligibilityWorkerV2."""

    def _make_context(self, variables=None):
        """Helper to create TaskContext."""
        return TaskContext(
            task_id="task_test_eligibility",
            process_instance_id="proc_test_eligibility",
            tenant_id="HOSPITAL_TEST",
            variables=variables or {},
            worker_id="glosa.check_appeal_eligibility",
        )

    def test_prosseguir_eligible_glosas(self, mock_dmn_service, mock_metrics):
        """Test eligible glosas - PROSSEGUIR."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Elegível para recurso",
            "risco": "BAIXO",
        }

        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        # Glosa date 10 days ago (within 30-day deadline)
        glosa_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        context = self._make_context({
            "analyzedGlosas": [
                {
                    "glosa_type": "ADMINISTRATIVE",
                    "reason_code": "MISSING_DOCUMENTATION",
                }
            ],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_123",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["eligibleGlosas"]) == 1
        assert len(result.variables["ineligibleGlosas"]) == 0
        assert result.variables["daysRemaining"] > 0

    def test_bloquear_ineligible_type(self, mock_dmn_service, mock_metrics):
        """Test ineligible glosa type - raises GlosaNotAppealable exception."""
        from healthcare_platform.shared.domain.exceptions import GlosaNotAppealable

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Tipo não elegível para recurso",
            "risco": "ALTO",
        }

        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        glosa_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

        context = self._make_context({
            "analyzedGlosas": [
                {
                    "glosa_type": "TOTAL",
                    "reason_code": "NOT_COVERED",
                }
            ],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_456",
        })

        # Should raise GlosaNotAppealable exception because no eligible glosas
        with pytest.raises(GlosaNotAppealable, match="Nenhuma glosa elegível"):
            worker.execute(context)

    def test_deadline_expired_error(self, mock_dmn_service, mock_metrics):
        """Test deadline expired - raises GlosaAppealDeadlineExpired exception."""
        from healthcare_platform.shared.domain.exceptions import GlosaAppealDeadlineExpired

        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        # Glosa date 40 days ago (past 30-day deadline)
        glosa_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()

        context = self._make_context({
            "analyzedGlosas": [
                {
                    "glosa_type": "ADMINISTRATIVE",
                    "reason_code": "MISSING_DOCUMENTATION",
                }
            ],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_789",
        })

        # Should raise GlosaAppealDeadlineExpired exception
        with pytest.raises(GlosaAppealDeadlineExpired, match="Prazo de recurso expirado"):
            worker.execute(context)

    def test_no_glosas_error(self, mock_dmn_service, mock_metrics):
        """Test error when no glosas provided."""
        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        glosa_date = datetime.now(timezone.utc).isoformat()

        context = self._make_context({
            "analyzedGlosas": [],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_EMPTY",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_NO_GLOSAS"

    def test_missing_date_error(self, mock_dmn_service, mock_metrics):
        """Test error when glosaDate is missing."""
        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        context = self._make_context({
            "analyzedGlosas": [{"glosa_type": "PARTIAL"}],
            "claimId": "CLAIM_NODATE",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_MISSING_DATE"

    def test_mixed_eligibility(self, mock_dmn_service, mock_metrics):
        """Test mixed eligible/ineligible glosas."""
        # DMN returns different results for different glosas
        call_count = [0]

        def dmn_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
            else:
                return {"resultado": "BLOQUEAR", "acao": "Not eligible", "risco": "ALTO"}

        mock_dmn_service.evaluate.side_effect = dmn_side_effect

        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        glosa_date = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()

        context = self._make_context({
            "analyzedGlosas": [
                {"glosa_type": "ADMINISTRATIVE", "reason_code": "MISSING_AUTH"},
                {"glosa_type": "TOTAL", "reason_code": "NOT_COVERED"},
            ],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_MIXED",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["eligibleGlosas"]) == 1
        assert len(result.variables["ineligibleGlosas"]) == 1

    def test_legacy_5_output_schema(self, mock_dmn_service, mock_metrics):
        """Test compatibility with legacy 5-output DMN schema."""
        mock_dmn_service.evaluate.return_value = {
            "observacao": "Elegível",
            "acaoRecomendada": "Continuar com recurso",
            "riscoDenial": "BAIXO",
        }

        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )

        glosa_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

        context = self._make_context({
            "analyzedGlosas": [
                {"glosa_type": "PARTIAL", "reason_code": "WRONG_CODE"},
            ],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_LEGACY",
        })

        result = worker.execute(context)

        # Legacy schema with no "resultado" defaults to PROSSEGUIR (line 108 in worker)
        # So glosa should be eligible
        assert result.status == TaskStatus.SUCCESS
        assert len(result.variables["eligibleGlosas"]) == 1

    def test_dmn_error_handling(self, mock_dmn_service_error, mock_metrics):
        """Test error handling when DMN evaluation fails."""
        worker = CheckAppealEligibilityWorkerV2(
            dmn_service=mock_dmn_service_error,
            metrics=mock_metrics,
        )

        glosa_date = datetime.now(timezone.utc).isoformat()

        context = self._make_context({
            "analyzedGlosas": [{"glosa_type": "PARTIAL"}],
            "glosaDate": glosa_date,
            "claimId": "CLAIM_ERROR",
        })

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_ELIGIBILITY_CHECK_PROCESSING"
