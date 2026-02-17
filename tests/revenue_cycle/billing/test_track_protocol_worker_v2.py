"""Tests for TrackProtocolWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.revenue_cycle.billing.workers.track_protocol_worker_v2 import TrackProtocolWorker

from tests.fixtures.workers import *


@pytest.mark.asyncio
class TestTrackProtocolWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.track_protocol",
        )

    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Registrar protocolo", "risco": "BAIXO",
        }
        worker = TrackProtocolWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "protocol_number": "PROT123",
            "payer_id": "PAYER001", "submission_timestamp": "2026-02-14T10:00:00Z"
        }))
        assert result.success is True
        assert result.variables.get("protocol_tracked") is True
        assert "TRACK-" in result.variables.get("tracking_id", "")

    async def test_prosseguir_stores_in_db(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Registrar", "risco": "BAIXO",
        }
        worker = TrackProtocolWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "protocol_number": "PROT456",
            "payer_id": "PAYER001"
        }))
        assert result.success is True
        # Verify protocol stored
        assert "PROT456" in worker._protocol_db
        assert worker._protocol_db["PROT456"]["claim_id"] == "CLM123"

    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Protocolo duplicado", "risco": "CRITICO",
        }
        worker = TrackProtocolWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "protocol_number": "PROT789",
            "payer_id": "PAYER001"
        }))
        assert result.success is False
        assert result.error_code == "ERR_TRACKING_BLOCKED"

    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Verificar protocolo antes de rastrear", "risco": "MEDIO",
        }
        worker = TrackProtocolWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "protocol_number": "PROT999",
            "payer_id": "PAYER001"
        }))
        assert result.success is True
        assert result.variables.get("requiresReview") is True

    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = TrackProtocolWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "protocol_number": "PROT000",
            "payer_id": "PAYER001"
        }))
        assert result.success is False
        assert result.error_code == "ERR_TRACKING_FAILURE"

    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "observacao": "Protocolo",
            "acaoRecomendada": "válido",
            "riscoDenial": "BAIXO",
            "alertasConformidade": "",
        }
        worker = TrackProtocolWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "claim_id": "CLM123", "protocol_number": "PROT111",
            "payer_id": "PAYER001"
        }))
        assert result.success is True
