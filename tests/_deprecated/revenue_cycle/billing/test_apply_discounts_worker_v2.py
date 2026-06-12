"""Tests for ApplyDiscountsWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.billing.workers.apply_discounts_worker_v2 import ApplyDiscountsWorker
from tests.fixtures.workers import *

class TestApplyDiscountsWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(task_id="task_123", process_instance_id="proc_456", tenant_id="HOSPITAL_TEST", variables=variables or {}, worker_id="billing.apply_discounts")
    
    def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "Aplicar descontos", "risco": "BAIXO"}
        worker = ApplyDiscountsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"line_items": [{"total_price": "100"}], "discount_rules": [{"percentage": "10"}]}))
        assert result.status == TaskStatus.SUCCESS
    
    def test_prosseguir_with_output(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        worker = ApplyDiscountsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"line_items": [{"total_price": "100"}], "discount_rules": [{"percentage": "10"}]}))
        assert result.variables.get("total_discount")
        assert result.variables.get("final_amount")
    
    def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "BLOQUEAR", "acao": "Desconto inválido", "risco": "CRITICO"}
        worker = ApplyDiscountsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"line_items": [], "discount_rules": []}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "REVISAR", "acao": "Revisar", "risco": "MEDIO"}
        worker = ApplyDiscountsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"line_items": [], "discount_rules": []}))
        assert result.variables.get("requiresReview") is True
    
    def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = ApplyDiscountsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"line_items": [], "discount_rules": []}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "observacao": "Obs", "acaoRecomendada": "Act", "riscoDenial": "BAIXO", "alertasConformidade": ""}
        worker = ApplyDiscountsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"line_items": [{"total_price": "100"}], "discount_rules": [{"percentage": "10"}]}))
        assert result.status == TaskStatus.SUCCESS
