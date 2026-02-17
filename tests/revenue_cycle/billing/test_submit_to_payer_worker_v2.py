"""Tests for SubmitToPayerWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.billing.workers.submit_to_payer_worker_v2 import SubmitToPayerWorker

from tests.fixtures.workers import *


class TestSubmitToPayerWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.submit_to_payer",
        )

    @pytest.mark.asyncio
    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Submeter à operadora", "risco": "BAIXO",
        }
        mock_tiss = MagicMock()
        mock_tiss.submit_guide = AsyncMock(return_value=MagicMock(
            success=True,
            protocol_number="PROT123",
            submission_timestamp=None,
            payer_response_code="OK",
            payer_response_message="Sucesso"
        ))

        worker = SubmitToPayerWorker(
            tiss_client=mock_tiss,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics
        )
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("submission_success") is True
        assert result.variables.get("protocol_number") == "PROT123"

    @pytest.mark.asyncio
    async def test_prosseguir_submission_failed(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Submeter", "risco": "BAIXO",
        }
        mock_tiss = MagicMock()
        mock_tiss.submit_guide = AsyncMock(return_value=MagicMock(
            success=False,
            payer_response_message="Erro de validação",
            payer_response_code="ERR001"
        ))

        worker = SubmitToPayerWorker(
            tiss_client=mock_tiss,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics
        )
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_SUBMISSION_FAILED"

    @pytest.mark.asyncio
    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Submissão bloqueada", "risco": "CRITICO",
        }
        worker = SubmitToPayerWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_SUBMISSION_BLOCKED"

    @pytest.mark.asyncio
    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Verificar dados antes de submeter", "risco": "MEDIO",
        }
        worker = SubmitToPayerWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True

    @pytest.mark.asyncio
    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = SubmitToPayerWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_SUBMISSION_FAILURE"

    @pytest.mark.asyncio
    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "observacao": "Validado",
            "acaoRecomendada": "submeter",
            "riscoDenial": "BAIXO",
            "alertasConformidade": "",
        }
        worker = SubmitToPayerWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "tiss_xml": "<xml>test</xml>",
            "payer_id": "PAYER001"
        }))
        assert result.status == TaskStatus.SUCCESS
