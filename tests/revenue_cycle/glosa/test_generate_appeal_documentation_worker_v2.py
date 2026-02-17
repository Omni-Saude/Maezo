"""
from __future__ import annotations

Tests for Generate Appeal Documentation Worker V2
"""
import pytest
from healthcare_platform.revenue_cycle.glosa.workers import GenerateAppealDocumentationWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


def test_generate_documentation_success_prosseguir(mock_dmn_service, mock_metrics, basic_task_context):
    """Test successful documentation generation with PROSSEGUIR result."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Gerar documentação completa",
        "risco": "BAIXO",
    }

    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [
            {
                "reasonCode": "MISSING_SIGNATURE",
                "type": "ADMINISTRATIVE",
                "deniedAmount": 100.50,
            }
        ],
        "claimId": "CLAIM-12345",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "appealDocumentId" in result.variables
    assert "appealLetter" in result.variables
    assert result.variables["documentationComplete"] is True
    assert result.variables["risk"] == "BAIXO"
    mock_dmn_service.evaluate.assert_called_once()


def test_generate_documentation_revisar(mock_dmn_service, mock_metrics, basic_task_context):
    """Test documentation generation requiring review."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Documentação incompleta - revisar",
        "risco": "MEDIO",
    }

    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [
            {
                "reasonCode": "INVALID_CODE",
                "type": "TECHNICAL",
                "deniedAmount": 250.00,
            }
        ],
        "claimId": "CLAIM-67890",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["requiresReview"] is True
    assert result.variables["documentationComplete"] is False
    assert result.variables["risk"] == "MEDIO"


def test_generate_documentation_bloquear(mock_dmn_service, mock_metrics, basic_task_context):
    """Test documentation generation blocked by DMN."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Razão inválida - bloquear",
        "risco": "ALTO",
    }

    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [
            {
                "reasonCode": "UNKNOWN",
                "type": "PARTIAL",
                "deniedAmount": 50.00,
            }
        ],
        "claimId": "CLAIM-99999",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_DOCUMENTATION_BLOCKED"
    assert "risk" in result.variables
    assert result.variables["risk"] == "ALTO"


def test_generate_documentation_no_glosas(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when no eligible glosas provided."""
    # Arrange
    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [],
        "claimId": "CLAIM-12345",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_NO_GLOSAS"


def test_generate_documentation_multiple_glosas(mock_dmn_service, mock_metrics, basic_task_context):
    """Test documentation generation with multiple glosas."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Documentação gerada",
        "risco": "BAIXO",
    }

    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [
            {"reasonCode": "MISSING_SIGNATURE", "type": "ADMINISTRATIVE", "deniedAmount": 100.00},
            {"reasonCode": "INVALID_CODE", "type": "TECHNICAL", "deniedAmount": 200.00},
        ],
        "claimId": "CLAIM-MULTI",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "appealLetter" in result.variables
    assert "requiredDocuments" in result.variables
    assert "evidenceChecklist" in result.variables


def test_generate_documentation_old_dmn_schema(mock_dmn_service, mock_metrics, basic_task_context):
    """Test documentation generation with old 5-output DMN schema."""
    # Arrange - Old schema with observacao + acaoRecomendada
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "observacao": "Documentação aprovada",
        "acaoRecomendada": "Prosseguir com submissão",
        "riscoDenial": "BAIXO",
    }

    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [
            {"reasonCode": "MISSING_CLINICAL_JUSTIFICATION", "type": "TECHNICAL", "deniedAmount": 150.00}
        ],
        "claimId": "CLAIM-OLD-SCHEMA",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "action" in result.variables
    assert "Documentação aprovada Prosseguir com submissão" in result.variables["action"]
    assert result.variables["risk"] == "BAIXO"


def test_generate_documentation_exception_handling(mock_dmn_service_error, mock_metrics, basic_task_context):
    """Test error handling when DMN evaluation fails."""
    # Arrange
    worker = GenerateAppealDocumentationWorkerV2(
        dmn_service=mock_dmn_service_error,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "eligibleGlosas": [
            {"reasonCode": "MISSING_SIGNATURE", "type": "ADMINISTRATIVE", "deniedAmount": 100.00}
        ],
        "claimId": "CLAIM-ERROR",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_DOCUMENTATION_GENERATION"
