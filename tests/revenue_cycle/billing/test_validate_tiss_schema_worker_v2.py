"""Tests for ValidateTISSSchemaWorker v2"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.revenue_cycle.billing.workers.validate_tiss_schema_worker import ValidateTISSSchemaWorker

from tests.fixtures.workers import *


@pytest.mark.asyncio
class TestValidateTISSSchemaWorkerV2:
    def _make_context(self, variables=None):
        return TaskContext(
            task_id="task_123", process_instance_id="proc_456",
            tenant_id="HOSPITAL_TEST", variables=variables or {},
            worker_id="billing.validate_tiss_schema",
        )

    async def test_prosseguir_happy_path(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Esquema válido", "risco": "BAIXO",
        }
        worker = ValidateTISSSchemaWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "tiss_xml": "<xml>valid tiss xml content here</xml>",
            "guide_type": "sp_sadt",
            "guide_number": "GUIDE123"
        }))
        assert result.success is True
        assert result.variables.get("schema_valid") is True

    async def test_prosseguir_with_errors(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR", "acao": "Continuar com avisos", "risco": "BAIXO",
        }
        mock_tiss = MagicMock()

        worker = ValidateTISSSchemaWorker(
            tiss_client=mock_tiss,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics
        )
        result = await worker.execute(self._make_context({
            "tiss_xml": "<xml>short</xml>",  # Too short - will generate error
            "guide_type": "sp_sadt",
            "guide_number": "GUIDE456"
        }))
        assert result.success is True
        # Should have validation errors
        assert len(result.variables.get("schema_errors", [])) > 0

    async def test_bloquear_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR", "acao": "Esquema inválido", "risco": "CRITICO",
        }
        worker = ValidateTISSSchemaWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "tiss_xml": "invalid xml",
            "guide_type": "sp_sadt"
        }))
        assert result.success is False
        assert result.error_code == "ERR_SCHEMA_INVALID"

    async def test_revisar_returns_review(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR", "acao": "Revisar esquema manualmente", "risco": "MEDIO",
        }
        worker = ValidateTISSSchemaWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "tiss_xml": "<xml>test xml</xml>",
            "guide_type": "consultation",
            "guide_number": "GUIDE789"
        }))
        assert result.success is True
        assert result.variables.get("requiresReview") is True

    async def test_dmn_error_returns_bpmn_error(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failed")
        worker = ValidateTISSSchemaWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "tiss_xml": "<xml>test</xml>",
            "guide_type": "sp_sadt"
        }))
        assert result.success is False
        assert result.error_code == "ERR_SCHEMA_VALIDATION_EXCEPTION"

    async def test_legacy_5_output_compat(self, mock_dmn_service, mock_metrics):
        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "observacao": "Esquema",
            "acaoRecomendada": "validado",
            "riscoDenial": "BAIXO",
            "alertasConformidade": "",
        }
        worker = ValidateTISSSchemaWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        result = await worker.execute(self._make_context({
            "tiss_xml": "<xml>valid tiss xml content here</xml>",
            "guide_type": "sp_sadt",
            "guide_number": "GUIDE999"
        }))
        assert result.success is True
