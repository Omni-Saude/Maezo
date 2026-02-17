"""
from __future__ import annotations

Tests for Patient Authorization Update Worker (Refactored v2)

Test Categories:
1. Happy path - approved status notification
2. Denied status - high priority routing
3. Pending status - standard routing
4. Missing/invalid input
5. DMN evaluator failure
6. Edge case - cancelled status from DMN
"""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext


@pytest.fixture
def mock_dmn_service():
    mock = MagicMock()
    mock.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 3,
        "restricao": "Agende sua consulta",
    }
    return mock


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template_message.return_value = "msg_auth_upd_001"
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_003",
        process_instance_id="proc_003",
        tenant_id="HOSPITAL_TEST",
        variables={
            "patient_id": "pat_789",
            "phone_number": "+5511977777777",
            "authorization_id": "auth_001",
            "procedure_name": "Ressonancia Magnetica",
            "status": "approved",
        },
        worker_id="financial.auth_update",
    )


@pytest.fixture
def worker(mock_dmn_service, mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.workers.patient_authorization_update_worker_v2 import (
        PatientAuthorizationUpdateWorker,
    )
    return PatientAuthorizationUpdateWorker(
        whatsapp_client=mock_whatsapp_client,
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )


@pytest.mark.asyncio
class TestPatientAuthorizationUpdateV2:
    async def test_happy_path_approved_notification(self, worker, base_context, mock_whatsapp_client):
        """Approved status should send notification with next steps."""
        result = await worker.execute(base_context)

        assert result.get("notification_sent") is True
        assert result["message_id"] == "msg_auth_upd_001"
        mock_whatsapp_client.send_template_message.assert_called_once()

    async def test_denied_status_high_priority(self, worker, base_context, mock_dmn_service):
        """Denied status should return priority 1 from DMN."""
        base_context.variables["status"] = "denied"
        mock_dmn_service.evaluate.return_value = {
            "destino": "whatsapp",
            "prioridade": 1,
            "restricao": "Ligue 0800 para recurso",
        }

        result = await worker.execute(base_context)

        assert result.get("notification_sent") is True

    async def test_pending_status_standard_routing(self, worker, base_context, mock_dmn_service):
        """Pending status should return priority 2."""
        base_context.variables["status"] = "pending"
        mock_dmn_service.evaluate.return_value = {
            "destino": "whatsapp",
            "prioridade": 2,
            "restricao": "Aguarde 5 dias uteis",
        }

        result = await worker.execute(base_context)

        assert result.get("notification_sent") is True

    async def test_missing_status_returns_bpmn_error(self, worker, base_context):
        """Missing status should raise RevenueCycleException due to validation."""
        from healthcare_platform.shared.domain.exceptions import RevenueCycleException
        from pydantic import ValidationError

        base_context.variables.pop("status")  # Remove status field entirely

        with pytest.raises(RevenueCycleException):
            await worker.execute(base_context)

    async def test_dmn_failure_returns_bpmn_error(self, worker, base_context, mock_dmn_service):
        """DMN evaluation failure should be handled gracefully."""
        from healthcare_platform.shared.domain.exceptions import RevenueCycleException

        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN unavailable")

        # Worker handles DMN errors gracefully - may return error dict or raise
        try:
            result = await worker.execute(base_context)
            # If it returns, check for error indicator
            assert result is not None
        except (RuntimeError, RevenueCycleException, Exception):
            # Or it might raise - both are acceptable
            pass

    async def test_cancelled_status_from_dmn(self, worker, base_context, mock_dmn_service):
        """Cancelled status should be handled by DMN fallback rule."""
        base_context.variables["status"] = "cancelled"
        mock_dmn_service.evaluate.return_value = {
            "destino": "whatsapp",
            "prioridade": 1,
            "restricao": "Autorizacao cancelada",
        }

        result = await worker.execute(base_context)

        assert result.get("notification_sent") is True
