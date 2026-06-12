"""Tests for NotifySubmissionStatusWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.revenue_cycle.billing.workers.notify_submission_status_worker_v2 import NotifySubmissionStatusWorker

from tests.fixtures.workers import *


@pytest.mark.asyncio
class TestNotifySubmissionStatusWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.notify_submission_status",
        )

    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Enviar notificações", "risco": "BAIXO",
        }
        worker = NotifySubmissionStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "submission_status": "submitted",
            "payer_name": "Unimed", "total_amount": 1500.00,
            "notification_phones": []
        }))
        assert result.success is True
        assert result.variables.get("notifications_sent") == 0

    async def test_prosseguir_with_notifications(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Enviar notificações", "risco": "BAIXO",
        }
        mock_whatsapp = MagicMock()
        mock_whatsapp.send_template_message.return_value = "msg_001"

        worker = NotifySubmissionStatusWorker(
            whatsapp_client=mock_whatsapp,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics
        )
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "submission_status": "submitted",
            "payer_name": "Unimed", "total_amount": 1500.00,
            "notification_phones": ["+5511999999999"]
        }))
        assert result.success is True
        assert result.variables.get("notifications_sent") == 1
        assert len(result.variables.get("notification_ids", [])) == 1

    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Não enviar notificações", "risco": "CRITICO",
        }
        worker = NotifySubmissionStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "submission_status": "failed",
        }))
        assert result.success is False
        assert result.error_code == "ERR_NOTIFICATION_BLOCKED"

    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Verificar destinatários", "risco": "MEDIO",
        }
        worker = NotifySubmissionStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "submission_status": "acknowledged",
        }))
        assert result.success is True
        assert result.variables.get("requiresReview") is True

    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = NotifySubmissionStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "submission_status": "submitted",
        }))
        assert result.success is False
        assert result.error_code == "ERR_NOTIFICATION_FAILURE"

    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "observacao": "Enviar",
            "acaoRecomendada": "notificações",
            "riscoDenial": "BAIXO",
            "alertasConformidade": "",
        }
        worker = NotifySubmissionStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "submission_status": "submitted",
        }))
        assert result.success is True
