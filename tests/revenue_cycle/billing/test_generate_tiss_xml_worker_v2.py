"""Tests for GenerateTISSXMLWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext
from healthcare_platform.revenue_cycle.billing.workers.generate_tiss_xml_worker import GenerateTISSXMLWorker
from tests.fixtures.workers import *

@pytest.mark.asyncio
class TestGenerateTISSXMLWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(task_id="task_123", process_instance_id="proc_456", tenant_id="HOSPITAL_TEST", variables=variables or {}, worker_id="billing.generate_tiss_xml")
    
    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "Gerar XML", "risco": "BAIXO"}
        worker = GenerateTISSXMLWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"charges": {}, "payer": "PAY001", "guide_type": "consultation"}))
        assert result.success is True

    async def test_prosseguir_with_output(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        worker = GenerateTISSXMLWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"charges": {}, "payer": "PAY001", "guide_type": "consultation"}))
        assert result.variables.get("tissXml") is not None or result.variables.get("tiss_xml") is not None

    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "BLOQUEAR", "acao": "Erro", "risco": "CRITICO"}
        worker = GenerateTISSXMLWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"charges": {}, "payer": "PAY001", "guide_type": "consultation"}))
        assert result.success is False

    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "REVISAR", "acao": "Revisar", "risco": "MEDIO"}
        worker = GenerateTISSXMLWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"charges": {}, "payer": "PAY001", "guide_type": "consultation"}))
        assert result.variables.get("requiresReview") is True

    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = GenerateTISSXMLWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"charges": {}, "payer": "PAY001", "guide_type": "consultation"}))
        assert result.success is False

    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "observacao": "O", "acaoRecomendada": "A", "riscoDenial": "BAIXO", "alertasConformidade": ""}
        worker = GenerateTISSXMLWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({"charges": {}, "payer": "PAY001", "guide_type": "consultation"}))
        assert result.success is True
