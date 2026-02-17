"""Tests for RetryFailedSubmissionWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.revenue_cycle.billing.workers.retry_failed_submission_worker_v2 import RetryFailedSubmissionWorker

from tests.fixtures.workers import *


@pytest.mark.asyncio
class TestRetryFailedSubmissionWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.retry_failed_submission",
        )

    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Retentar submissão", "risco": "BAIXO",
        }
        mock_tiss = MagicMock()
        mock_tiss.submit_guide = AsyncMock(return_value=MagicMock(success=True, protocol_number="PROT123"))

        worker = RetryFailedSubmissionWorker(
            tiss_client=mock_tiss,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics
        )
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001", "attempt_number": 1, "max_attempts": 5
        }))
        assert result.success is True
        assert result.variables.get("retry_success") is True
        assert result.variables.get("protocol_number") == "PROT123"

    async def test_prosseguir_retry_failed(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Retentar", "risco": "BAIXO",
        }
        mock_tiss = MagicMock()
        mock_tiss.submit_guide = AsyncMock(return_value=MagicMock(
            success=False, payer_response_message="Erro temporário"
        ))

        worker = RetryFailedSubmissionWorker(
            tiss_client=mock_tiss,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics
        )
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001", "attempt_number": 2, "max_attempts": 5
        }))
        assert result.success is True
        assert result.variables.get("retry_success") is False
        assert result.variables.get("next_attempt_number") == 3

    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Max tentativas atingidas", "risco": "CRITICO",
        }
        worker = RetryFailedSubmissionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001", "attempt_number": 5, "max_attempts": 5
        }))
        assert result.success is False
        assert result.error_code == "ERR_MAX_RETRY_REACHED"

    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Verificar erro antes de retentar", "risco": "MEDIO",
        }
        worker = RetryFailedSubmissionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001", "attempt_number": 3, "max_attempts": 5
        }))
        assert result.success is True
        assert result.variables.get("requiresReview") is True

    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = RetryFailedSubmissionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.success is False
        assert result.error_code == "ERR_RETRY_FAILURE"

    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "observacao": "Prosseguir",
            "acaoRecomendada": "com retry",
            "riscoDenial": "BAIXO",
            "alertasConformidade": "",
        }
        worker = RetryFailedSubmissionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001", "attempt_number": 1
        }))
        assert result.success is True
