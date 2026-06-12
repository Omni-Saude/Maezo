"""Tests for DoctorProcedureAuthStatusWorker v2 (ARCHETYPE: OPERATIONAL_ROUTING).

Contrato DMN validado:
  Input:  total_pending (number), oldest_days (number)   ← snake_case (worker → DMN)
  Output: destino (string), prioridade (number), restricao (string)

Variáveis BPMN de entrada (camelCase — convenção BPMN/CIB Seven):
  doctorId, phoneNumber, pendingAuthorizations (list)

Variáveis BPMN de saída (camelCase):
  notificationSent, messageId, sentAt, totalPending, destino, prioridade, restricao
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


@pytest.fixture
def mock_dmn_service():
    mock = MagicMock()
    mock.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 3,
        "restricao": "Standard notification",
    }
    return mock


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template.return_value = "msg_auth_001"
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_001",
        process_instance_id="proc_001",
        tenant_id="HOSPITAL_TEST",
        variables={
            "doctorId": "doc_123",
            "phoneNumber": "+5511999999999",
            "pendingAuthorizations": [
                {"patient_name": "Joao", "procedure": "RMN", "days_pending": 5, "payer": "Unimed"},
                {"patient_name": "Maria", "procedure": "TC", "days_pending": 10, "payer": "Amil"},
            ],
        },
        worker_id="financial.auth_pending",
    )


@pytest.fixture
def worker(mock_dmn_service, mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.billing.workers.doctor_procedure_auth_status_worker_v2 import (
        DoctorProcedureAuthStatusWorker,
    )
    return DoctorProcedureAuthStatusWorker(
        whatsapp_client=mock_whatsapp_client,
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )


# ── Contrato de variáveis DMN ────────────────────────────────────────────────

class TestDmnContrato:
    def test_dmn_recebe_total_pending_snake_case(self, worker, base_context, mock_dmn_service):
        """DMN deve receber 'total_pending' (snake_case), nunca 'totalPending'."""
        worker.execute(base_context)

        inputs = mock_dmn_service.evaluate.call_args.kwargs.get(
            "inputs", mock_dmn_service.evaluate.call_args[1].get("inputs", {})
        )
        assert "total_pending" in inputs, "DMN deve receber 'total_pending'"
        assert "totalPending" not in inputs, "DMN não deve receber 'totalPending' (camelCase)"
        assert inputs["total_pending"] == 2

    def test_dmn_recebe_oldest_days_snake_case(self, worker, base_context, mock_dmn_service):
        """DMN deve receber 'oldest_days' (snake_case), nunca 'oldestDays'."""
        worker.execute(base_context)

        inputs = mock_dmn_service.evaluate.call_args.kwargs.get(
            "inputs", mock_dmn_service.evaluate.call_args[1].get("inputs", {})
        )
        assert "oldest_days" in inputs, "DMN deve receber 'oldest_days'"
        assert "oldestDays" not in inputs, "DMN não deve receber 'oldestDays' (camelCase)"
        assert inputs["oldest_days"] == 10  # max(5, 10)

    def test_dmn_nao_recebe_variaveis_irrelevantes(self, worker, base_context, mock_dmn_service):
        """DMN não deve receber doctorId, phoneNumber nem lista raw de autorizações."""
        worker.execute(base_context)

        inputs = mock_dmn_service.evaluate.call_args.kwargs.get(
            "inputs", mock_dmn_service.evaluate.call_args[1].get("inputs", {})
        )
        assert "doctorId" not in inputs
        assert "phoneNumber" not in inputs
        assert "pendingAuthorizations" not in inputs

    def test_dmn_chamado_exatamente_uma_vez(self, worker, base_context, mock_dmn_service):
        """Deve haver exatamente 1 chamada DMN por execução."""
        worker.execute(base_context)
        assert mock_dmn_service.evaluate.call_count == 1

    def test_oldest_days_calculado_corretamente(self, worker, mock_dmn_service, mock_metrics):
        """oldest_days deve ser o máximo de days_pending na lista."""
        from healthcare_platform.revenue_cycle.billing.workers.doctor_procedure_auth_status_worker_v2 import (
            DoctorProcedureAuthStatusWorker,
        )
        w = DoctorProcedureAuthStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        ctx = TaskContext(
            task_id="t", process_instance_id="p", tenant_id="HOSPITAL_TEST",
            variables={
                "doctorId": "doc_x",
                "phoneNumber": "+55",
                "pendingAuthorizations": [
                    {"days_pending": 2},
                    {"days_pending": 15},
                    {"days_pending": 7},
                ],
            },
            worker_id="financial.auth_pending",
        )
        w.execute(ctx)

        inputs = mock_dmn_service.evaluate.call_args.kwargs.get(
            "inputs", mock_dmn_service.evaluate.call_args[1].get("inputs", {})
        )
        assert inputs["oldest_days"] == 15

    def test_total_pending_calculado_corretamente(self, worker, mock_dmn_service, mock_metrics):
        """total_pending deve refletir len(pendingAuthorizations)."""
        from healthcare_platform.revenue_cycle.billing.workers.doctor_procedure_auth_status_worker_v2 import (
            DoctorProcedureAuthStatusWorker,
        )
        w = DoctorProcedureAuthStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        ctx = TaskContext(
            task_id="t", process_instance_id="p", tenant_id="HOSPITAL_TEST",
            variables={
                "doctorId": "doc_x",
                "phoneNumber": "+55",
                "pendingAuthorizations": [
                    {"days_pending": 1},
                    {"days_pending": 3},
                    {"days_pending": 5},
                    {"days_pending": 8},
                ],
            },
            worker_id="financial.auth_pending",
        )
        w.execute(ctx)

        inputs = mock_dmn_service.evaluate.call_args.kwargs.get(
            "inputs", mock_dmn_service.evaluate.call_args[1].get("inputs", {})
        )
        assert inputs["total_pending"] == 4


# ── Happy paths ──────────────────────────────────────────────────────────────

class TestDoctorProcedureAuthStatusV2:
    def test_happy_path_sends_notification(self, worker, base_context, mock_whatsapp_client):
        """Happy path: DMN routes to whatsapp, notification sent."""
        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notificationSent"] is True
        assert result.variables["messageId"] == "msg_auth_001"
        assert result.variables["totalPending"] == 2
        mock_whatsapp_client.send_template.assert_called_once()

    def test_skip_routing_no_pending(self, worker, base_context, mock_dmn_service):
        """DMN returns skip when no pending authorizations."""
        base_context.variables["pendingAuthorizations"] = []
        mock_dmn_service.evaluate.return_value = {
            "destino": "skip",
            "prioridade": 5,
            "restricao": "No pending authorizations",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notificationSent"] is False
        assert result.variables["destino"] == "skip"

    def test_urgent_routing_overdue(self, worker, base_context, mock_dmn_service):
        """DMN returns urgent priority for overdue authorizations."""
        base_context.variables["pendingAuthorizations"][1]["days_pending"] = 15
        mock_dmn_service.evaluate.return_value = {
            "destino": "whatsapp",
            "prioridade": 1,
            "restricao": "Urgent: overdue authorizations",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["prioridade"] == 1
        assert result.variables["restricao"] == "Urgent: overdue authorizations"

    def test_missing_doctor_id_returns_bpmn_error(self, worker, base_context):
        """Missing doctorId should return BPMN error."""
        base_context.variables["doctorId"] = ""

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INVALID_INPUT"

    def test_missing_phone_number_returns_bpmn_error(self, worker, base_context):
        """Missing phoneNumber should return BPMN error."""
        base_context.variables["phoneNumber"] = ""

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INVALID_INPUT"

    def test_dmn_failure_returns_bpmn_error(self, worker, base_context, mock_dmn_service):
        """DMN evaluation failure should return BPMN error."""
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN evaluation failed")

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_AUTH_STATUS_NOTIFICATION"
        assert "DMN evaluation failed" in result.error_message

    def test_sem_whatsapp_client_nao_quebra(self, mock_dmn_service, mock_metrics):
        """Worker sem whatsapp_client não deve quebrar — message_id será None."""
        from healthcare_platform.revenue_cycle.billing.workers.doctor_procedure_auth_status_worker_v2 import (
            DoctorProcedureAuthStatusWorker,
        )
        worker = DoctorProcedureAuthStatusWorker(
            whatsapp_client=None,
            dmn_service=mock_dmn_service,
            metrics=mock_metrics,
        )
        ctx = TaskContext(
            task_id="t", process_instance_id="p", tenant_id="HOSPITAL_TEST",
            variables={
                "doctorId": "doc_x",
                "phoneNumber": "+55",
                "pendingAuthorizations": [{"days_pending": 3}],
            },
            worker_id="financial.auth_pending",
        )
        result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["messageId"] is None

    def test_output_contem_campos_esperados(self, worker, base_context):
        """Resultado de sucesso deve conter todos os campos obrigatórios."""
        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        for campo in ("notificationSent", "messageId", "sentAt", "totalPending",
                      "destino", "prioridade", "restricao"):
            assert campo in result.variables, f"Campo ausente no resultado: {campo}"

    def test_summary_shows_top_3_sorted_by_days(self, worker, base_context, mock_whatsapp_client):
        """Summary should include top 3 authorizations sorted by days_pending desc."""
        base_context.variables["pendingAuthorizations"] = [
            {"patient_name": "A", "procedure": "P1", "days_pending": 1, "payer": "X"},
            {"patient_name": "B", "procedure": "P2", "days_pending": 20, "payer": "Y"},
            {"patient_name": "C", "procedure": "P3", "days_pending": 10, "payer": "Z"},
            {"patient_name": "D", "procedure": "P4", "days_pending": 5, "payer": "W"},
        ]

        worker.execute(base_context)

        call_args = mock_whatsapp_client.send_template.call_args
        body_params = call_args.kwargs["body_params"]
        # Top 3 sorted by days_pending DESC: B=20, C=10, D=5
        assert "B" in body_params[2]
        assert "C" in body_params[2]
        assert "D" in body_params[2]
        assert "A" not in body_params[2]  # A tem 1 dia, não entra no top 3
