"""Tests for ApplyContractRulesWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.billing.workers.apply_contract_rules_worker_v2 import ApplyContractRulesWorker
from tests.fixtures.workers import *

class TestApplyContractRulesWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.apply_contract_rules",
        )
    
    def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Aplicar regras contratuais", "risco": "BAIXO",
        }
        worker = ApplyContractRulesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "claim_id": "CLM001", "payer_id": "PAY001",
            "procedures": [{"code": "PROC1", "unit_price": "100", "quantity": 1}],
            "contract_rules": {"copay_pct": "10", "deductible": "50"},
        }))
        assert result.status == TaskStatus.SUCCESS
        assert "adjusted_items" in result.variables
    
    def test_prosseguir_with_output(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Autorizar", "risco": "BAIXO",
        }
        worker = ApplyContractRulesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "claim_id": "CLM001", "payer_id": "PAY001",
            "procedures": [{"code": "PROC1", "unit_price": "100", "quantity": 1}],
            "contract_rules": {"copay_pct": "10", "deductible": "50"},
        }))
        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("total_patient_responsibility")
        assert result.variables.get("total_payer_responsibility")
    
    def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Regras contratuais inválidas", "risco": "CRITICO",
        }
        worker = ApplyContractRulesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "claim_id": "CLM001", "payer_id": "PAY001",
            "procedures": [], "contract_rules": {},
        }))
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CONTRACT_VIOLATION"
    
    def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Revisar regras", "risco": "MEDIO",
        }
        worker = ApplyContractRulesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "claim_id": "CLM001", "payer_id": "PAY001",
            "procedures": [], "contract_rules": {},
        }))
        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True
    
    def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = ApplyContractRulesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({"claim_id": "CLM001", "payer_id": "PAY001", "procedures": [], "contract_rules": {}}))
        assert result.status == TaskStatus.BPMN_ERROR
    
    def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "observacao": "Obs", "acaoRecomendada": "Action",
            "riscoDenial": "BAIXO", "alertasConformidade": "",
        }
        worker = ApplyContractRulesWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "claim_id": "CLM001", "payer_id": "PAY001",
            "procedures": [{"code": "PROC1", "unit_price": "100", "quantity": 1}],
            "contract_rules": {"copay_pct": "10", "deductible": "50"},
        }))
        assert result.status == TaskStatus.SUCCESS
