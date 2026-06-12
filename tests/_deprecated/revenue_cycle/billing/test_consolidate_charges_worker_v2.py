"""Tests for ConsolidateChargesWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.billing.workers.consolidate_charges_worker_v2 import ConsolidateChargesWorker
from tests.fixtures.workers import *

class TestConsolidateChargesWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(task_id="task_123", process_instance_id="proc_456", tenant_id="HOSPITAL_TEST", variables=variables or {}, worker_id="billing.consolidate_charges")
    
    def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "Consolidar", "risco": "BAIXO"}
        worker = ConsolidateChargesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "patient_id": "PAT001", "line_items": [{"total_price": "100"}]}))
        assert result.status == TaskStatus.SUCCESS
    
    def test_prosseguir_with_output(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        worker = ConsolidateChargesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "patient_id": "PAT001", "line_items": [{"total_price": "100"}]}))
        assert result.variables.get("claim_id")
        assert result.variables.get("claim_total")
    
    def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "BLOQUEAR", "acao": "Erro", "risco": "CRITICO"}
        worker = ConsolidateChargesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "patient_id": "PAT001", "line_items": []}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "REVISAR", "acao": "Revisar", "risco": "MEDIO"}
        worker = ConsolidateChargesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "patient_id": "PAT001", "line_items": []}))
        assert result.variables.get("requiresReview") is True
    
    def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = ConsolidateChargesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "patient_id": "PAT001", "line_items": []}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR", "observacao": "O", "acaoRecomendada": "A", "riscoDenial": "BAIXO", "alertasConformidade": ""}
        worker = ConsolidateChargesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"encounter_id": "ENC001", "patient_id": "PAT001", "line_items": [{"total_price": "100"}]}))
        assert result.status == TaskStatus.SUCCESS
