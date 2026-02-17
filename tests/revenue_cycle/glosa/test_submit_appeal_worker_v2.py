"""
from __future__ import annotations

Tests for Submit Appeal Worker V2
"""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.revenue_cycle.glosa.workers import SubmitAppealWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


def test_submit_appeal_success_prosseguir(mock_dmn_service, mock_metrics, basic_task_context):
    """Test successful appeal submission with PROSSEGUIR result."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Recurso enviado com sucesso",
        "risco": "BAIXO",
    }

    mock_tiss_client = MagicMock()
    mock_tiss_client.submit_guide.return_value = {"success": True}

    worker = SubmitAppealWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=mock_tiss_client,
    )

    context = basic_task_context
    context.variables = {
        "appealDocumentId": "APPEAL-001",
        "claimId": "CLAIM-12345",
        "eligibleGlosas": [{"glosaId": "G1", "deniedAmount": 100.00}],
        "payerId": "PAYER-001",
        "providerId": "PROV-001",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["submissionSuccess"] is True
    assert "submissionProtocol" in result.variables
    assert result.variables["payerResponseCode"] == "SUCCESS"
    assert result.variables["risk"] == "BAIXO"
    mock_dmn_service.evaluate.assert_called_once()


def test_submit_appeal_revisar(mock_dmn_service, mock_metrics, basic_task_context):
    """Test appeal submission requiring review."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Verificar protocolo de submissão",
        "risco": "MEDIO",
    }

    worker = SubmitAppealWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,  # Will use mock submission
    )

    context = basic_task_context
    context.variables = {
        "appealDocumentId": "APPEAL-002",
        "claimId": "CLAIM-67890",
        "eligibleGlosas": [{"glosaId": "G2", "deniedAmount": 200.00}],
        "payerId": "PAYER-002",
        "providerId": "PROV-002",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["requiresReview"] is True
    assert result.variables["risk"] == "MEDIO"


def test_submit_appeal_bloquear(mock_dmn_service, mock_metrics, basic_task_context):
    """Test appeal submission blocked by DMN."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Tentativas excedidas - bloquear",
        "risco": "ALTO",
    }

    worker = SubmitAppealWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "appealDocumentId": "APPEAL-003",
        "claimId": "CLAIM-99999",
        "eligibleGlosas": [{"glosaId": "G3", "deniedAmount": 50.00}],
        "payerId": "PAYER-003",
        "providerId": "PROV-003",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_SUBMISSION_BLOCKED"


def test_submit_appeal_missing_fields(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when required fields are missing."""
    # Arrange
    worker = SubmitAppealWorkerV2(
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
    assert result.error_code == "ERR_MISSING_REQUIRED_FIELDS"


def test_submit_appeal_no_glosas(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when no glosas provided."""
    # Arrange
    worker = SubmitAppealWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "appealDocumentId": "APPEAL-004",
        "claimId": "CLAIM-12345",
        "eligibleGlosas": [],
        "payerId": "PAYER-001",
        "providerId": "PROV-001",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_NO_GLOSAS"


def test_submit_appeal_tiss_client_error(mock_dmn_service, mock_metrics, basic_task_context):
    """Test handling of TISS client errors."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Erro de conexão",
        "risco": "MEDIO",
    }

    mock_tiss_client = MagicMock()
    mock_tiss_client.submit_guide.side_effect = Exception("Connection timeout")

    worker = SubmitAppealWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=mock_tiss_client,
    )

    context = basic_task_context
    context.variables = {
        "appealDocumentId": "APPEAL-005",
        "claimId": "CLAIM-12345",
        "eligibleGlosas": [{"glosaId": "G1", "deniedAmount": 100.00}],
        "payerId": "PAYER-001",
        "providerId": "PROV-001",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["payerResponseCode"] == "CONNECTION_ERROR"
    assert result.variables["requiresReview"] is True


def test_submit_appeal_old_dmn_schema(mock_dmn_service, mock_metrics, basic_task_context):
    """Test submission with old 5-output DMN schema."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "observacao": "Submissão aprovada",
        "acaoRecomendada": "Prosseguir",
        "riscoDenial": "BAIXO",
    }

    worker = SubmitAppealWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tiss_client=None,
    )

    context = basic_task_context
    context.variables = {
        "appealDocumentId": "APPEAL-006",
        "claimId": "CLAIM-OLD",
        "eligibleGlosas": [{"glosaId": "G1", "deniedAmount": 100.00}],
        "payerId": "PAYER-001",
        "providerId": "PROV-001",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "action" in result.variables
    assert result.variables["risk"] == "BAIXO"
