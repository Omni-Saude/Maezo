"""Tests for ValidateClaimWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.billing.workers.validate_claim_worker import ValidateClaimWorker

from tests.fixtures.workers import *


class TestValidateClaimWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.validate_claim",
        )

    def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Validação aprovada", "risco": "BAIXO",
        }
        worker = ValidateClaimWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "encounter": "ENC123",
            "patient": "PAT001",
            "payer": "PAYER001",
            "procedureList": [
                {"procedure_code": "CODE001", "quantity": 1}
            ],
        }))
        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("validation_passed") is True
        assert result.variables.get("claim_ready_for_submission") is True
        assert result.variables.get("validationResult") is True

    def test_prosseguir_with_errors(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Prosseguir com erros leves", "risco": "BAIXO",
        }
        worker = ValidateClaimWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "encounter": "ENC123",
            "patient": "PAT001",
            "payer": "PAYER001",
            "procedureList": [],
        }))
        assert result.status == TaskStatus.SUCCESS
        # Should have validation errors
        assert len(result.variables.get("validation_errors", [])) > 0

    def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Validação falhou", "risco": "CRITICO",
        }
        worker = ValidateClaimWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "encounter": "ENC123",
            "patient": "PAT001",
            "payer": "PAYER001",
            "procedureList": [{"procedure_code": "CODE001", "quantity": 1}],
        }))
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_VALIDATION_FAILED"

    def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Revisar conta manualmente", "risco": "MEDIO",
        }
        worker = ValidateClaimWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "encounter": "ENC123",
            "patient": "PAT001",
            "payer": "PAYER001",
            "procedureList": [{"procedure_code": "CODE001"}],
        }))
        assert result.status == TaskStatus.SUCCESS
        assert result.variables.get("requiresReview") is True

    def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = ValidateClaimWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "encounter": "ENC123",
            "patient": "PAT001",
            "procedureList": [],
        }))
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_VALIDATION_EXCEPTION"

    def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "observacao": "Validação",
            "acaoRecomendada": "OK",
            "riscoDenial": "BAIXO",
            "alertasConformidade": "",
        }
        worker = ValidateClaimWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = worker.execute(self._make_context({
            "encounter": "ENC123",
            "patient": "PAT001",
            "payer": "PAYER001",
            "procedureList": [{"procedure_code": "CODE001", "quantity": 1}],
        }))
        assert result.status == TaskStatus.SUCCESS
