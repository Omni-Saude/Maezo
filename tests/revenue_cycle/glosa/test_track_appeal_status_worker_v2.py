"""
from __future__ import annotations

Tests for Track Appeal Status Worker V2
"""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.revenue_cycle.glosa.workers import TrackAppealStatusWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


def test_track_status_success_prosseguir(mock_dmn_service, mock_metrics, basic_task_context):
    """Test successful status tracking with PROSSEGUIR result."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Status rastreado com sucesso",
        "risco": "BAIXO",
    }

    mock_tiss_client = MagicMock()
    mock_tiss_client.check_submission_status.return_value = {
        "statusCode": "APPROVED"
    }

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=mock_tiss_client,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-12345",
        "claimId": "CLAIM-12345",
        "submissionTimestamp": "2026-02-01T10:00:00Z",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["appealStatus"] == "APPROVED"
    assert result.variables["followUpRequired"] is False
    assert "statusMessage" in result.variables
    assert result.variables["risk"] == "BAIXO"
    mock_dmn_service.evaluate.assert_called_once()


def test_track_status_revisar(mock_dmn_service, mock_metrics, basic_task_context):
    """Test status tracking requiring review."""
    # Arrange
    def dmn_revisar(tenant_id, category, table_name, inputs):
        return {
            "resultado": "REVISAR",
            "acao": "Prazo excedido - revisar",
            "risco": "MEDIO",
        }

    mock_dmn_service.evaluate.side_effect = dmn_revisar

    mock_tiss_client = MagicMock()
    mock_tiss_client.check_submission_status.return_value = {
        "statusCode": "PENDING_INFO"
    }

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=mock_tiss_client,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-67890",
        "claimId": "CLAIM-67890",
        "submissionTimestamp": "2026-01-15T10:00:00Z",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["requiresReview"] is True
    assert result.variables["followUpRequired"] is True
    assert result.variables["risk"] == "MEDIO"


def test_track_status_bloquear(mock_dmn_service, mock_metrics, basic_task_context):
    """Test status tracking blocked by DMN."""
    # Arrange
    def dmn_bloquear(tenant_id, category, table_name, inputs):
        return {
            "resultado": "BLOQUEAR",
            "acao": "Status inválido - bloquear",
            "risco": "ALTO",
        }

    mock_dmn_service.evaluate.side_effect = dmn_bloquear

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-99999",
        "claimId": "CLAIM-99999",
        "submissionTimestamp": "2026-02-10T10:00:00Z",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_TRACKING_BLOCKED"


def test_track_status_missing_protocol(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when protocol is missing."""
    # Arrange
    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-12345",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_MISSING_PROTOCOL"


def test_track_status_elapsed_days_calculation(mock_dmn_service, mock_metrics, basic_task_context):
    """Test elapsed days calculation."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Status em análise",
        "risco": "BAIXO",
    }

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-12345",
        "claimId": "CLAIM-12345",
        "submissionTimestamp": "2026-01-01T10:00:00Z",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["elapsedDays"] >= 0


def test_track_status_payer_code_mapping(mock_dmn_service, mock_metrics, basic_task_context):
    """Test mapping of payer status codes."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Status mapeado",
        "risco": "BAIXO",
    }

    mock_tiss_client = MagicMock()
    mock_tiss_client.check_submission_status.return_value = {
        "statusCode": "PARTIALLY_APPROVED"
    }

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=mock_tiss_client,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-12345",
        "claimId": "CLAIM-12345",
        "submissionTimestamp": "2026-02-10T10:00:00Z",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["appealStatus"] == "PARTIALLY_APPROVED"
    assert "statusMessage" in result.variables


def test_track_status_old_dmn_schema(mock_dmn_service, mock_metrics, basic_task_context):
    """Test status tracking with old 5-output DMN schema."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "observacao": "Status válido",
        "acaoRecomendada": "Continuar monitoramento",
        "riscoDenial": "BAIXO",
    }

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-OLD",
        "claimId": "CLAIM-OLD",
        "submissionTimestamp": "2026-02-10T10:00:00Z",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "action" in result.variables
    assert result.variables["risk"] == "BAIXO"


def test_track_status_follow_up_threshold(mock_dmn_service, mock_metrics, basic_task_context):
    """Test follow-up required after threshold days."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Follow-up necessário",
        "risco": "MEDIO",
    }

    worker = TrackAppealStatusWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "submissionProtocol": "PROT-12345",
        "claimId": "CLAIM-12345",
        "submissionTimestamp": "2026-01-01T10:00:00Z",  # More than 15 days ago
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["followUpRequired"] is True
