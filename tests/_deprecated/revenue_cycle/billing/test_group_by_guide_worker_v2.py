"""Tests for GroupByGuideWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.billing.workers.group_by_guide_worker_v2 import GroupByGuideWorker
from tests.fixtures.workers import *

class TestGroupByGuideWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(task_id="task_123", process_instance_id="proc_456", tenant_id="HOSPITAL_TEST", variables=variables or {}, worker_id="billing.group_by_guide")
    
    def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "Agrupar", "risco": "BAIXO"}
        worker = GroupByGuideWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "procedures": [{"type": "SP_SADT", "code": "P1"}]}))
        assert result.status == TaskStatus.SUCCESS
    
    def test_prosseguir_with_output(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        worker = GroupByGuideWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "procedures": [{"type": "SP_SADT", "code": "P1"}]}))
        assert result.variables.get("grouped_guides")
        assert result.variables.get("guide_count")
    
    def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "BLOQUEAR", "acao": "Erro", "risco": "CRITICO"}
        worker = GroupByGuideWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "procedures": []}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "REVISAR", "acao": "Revisar", "risco": "MEDIO"}
        worker = GroupByGuideWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "procedures": []}))
        assert result.variables.get("requiresReview") is True
    
    def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = GroupByGuideWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "procedures": []}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "observacao": "O", "acaoRecomendada": "A", "riscoDenial": "BAIXO", "alertasConformidade": ""}
        worker = GroupByGuideWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "procedures": [{"type": "SP_SADT", "code": "P1"}]}))
        assert result.status == TaskStatus.SUCCESS
