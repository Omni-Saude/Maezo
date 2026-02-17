"""Tests for HandleAcknowledgmentWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext
from healthcare_platform.revenue_cycle.billing.workers.handle_acknowledgment_worker_v2 import HandleAcknowledgmentWorker
from tests.fixtures.workers import *

@pytest.mark.asyncio
class TestHandleAcknowledgmentWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(task_id="task_123", process_instance_id="proc_456", tenant_id="HOSPITAL_TEST", variables=variables or {}, worker_id="billing.handle_acknowledgment")
    
    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "Processar ACK", "risco": "BAIXO"}
        worker = HandleAcknowledgmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"protocol_number": "PROT001", "claim_id": "CLM001", "acknowledgment_type": "ACK", "response_code": "200"}))
        assert result.success is True
    
    async def test_prosseguir_with_output(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        worker = HandleAcknowledgmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"protocol_number": "PROT001", "claim_id": "CLM001", "acknowledgment_type": "ACK", "response_code": "200"}))
        assert result.variables.get("acknowledged")
        assert result.variables.get("billing_status")
    
    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "BLOQUEAR", "acao": "Erro", "risco": "CRITICO"}
        worker = HandleAcknowledgmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"protocol_number": "PROT001", "claim_id": "CLM001", "acknowledgment_type": "NACK", "response_code": "400"}))
        assert result.success is False
    
    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "REVISAR", "acao": "Revisar", "risco": "MEDIO"}
        worker = HandleAcknowledgmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"protocol_number": "PROT001", "claim_id": "CLM001", "acknowledgment_type": "ACK", "response_code": "200"}))
        assert result.variables.get("requiresReview") is True
    
    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = HandleAcknowledgmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"protocol_number": "PROT001", "claim_id": "CLM001", "acknowledgment_type": "ACK", "response_code": "200"}))
        assert result.success is False
    
    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "observacao": "O", "acaoRecomendada": "A", "riscoDenial": "BAIXO", "alertasConformidade": ""}
        worker = HandleAcknowledgmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"protocol_number": "PROT001", "claim_id": "CLM001", "acknowledgment_type": "ACK", "response_code": "200"}))
        assert result.success is True
