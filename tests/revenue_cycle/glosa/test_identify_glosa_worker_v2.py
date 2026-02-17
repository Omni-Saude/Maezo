"""
from __future__ import annotations

Tests for Identify Glosa Worker V2
"""
import pytest
from healthcare_platform.revenue_cycle.glosa.workers import IdentifyGlosaWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


def test_identify_glosas_success_prosseguir(mock_dmn_service, mock_metrics, basic_task_context):
    """Test successful glosa identification with PROSSEGUIR result."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Glosas identificadas corretamente",
        "risco": "BAIXO",
    }

    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimResponse": {
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "PROC-001"},
                    "adjudication": [
                        {
                            "category": "denied",
                            "amount": 150.00,
                            "reason": "Falta de autorização",
                        }
                    ],
                }
            ]
        },
        "claimId": "CLAIM-12345",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["hasGlosas"] is True
    assert result.variables["glosaCount"] == 1
    assert result.variables["totalDeniedAmount"] == 150.00
    assert result.variables["risk"] == "BAIXO"
    mock_dmn_service.evaluate.assert_called_once()


def test_identify_glosas_revisar(mock_dmn_service, mock_metrics, basic_task_context):
    """Test glosa identification requiring review."""
    # Arrange
    # Mock needs to be configured to return REVISAR for this specific call
    def side_effect_revisar(tenant_id, category, table_name, inputs):
        return {
            "resultado": "REVISAR",
            "acao": "Verificar categoria de adjudicação",
            "risco": "MEDIO",
        }

    mock_dmn_service.evaluate.side_effect = side_effect_revisar

    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimResponse": {
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "PROC-002"},
                    "adjudication": [
                        {
                            "category": "rejected",
                            "amount": 200.00,
                            "reason": "Código incorreto",
                        }
                    ],
                }
            ]
        },
        "claimId": "CLAIM-67890",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["requiresReview"] is True
    assert result.variables["risk"] == "MEDIO"


def test_identify_glosas_bloquear(mock_dmn_service, mock_metrics, basic_task_context):
    """Test glosa identification blocked by DMN."""
    # Arrange
    def side_effect_bloquear(tenant_id, category, table_name, inputs):
        return {
            "resultado": "BLOQUEAR",
            "acao": "Resposta inválida - bloquear",
            "risco": "ALTO",
        }

    mock_dmn_service.evaluate.side_effect = side_effect_bloquear

    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimResponse": {
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "PROC-003"},
                    "adjudication": [
                        {
                            "category": "denied",
                            "amount": 50.00,
                            "reason": "Motivo inválido",
                        }
                    ],
                }
            ]
        },
        "claimId": "CLAIM-99999",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_GLOSA_IDENTIFICATION_BLOCKED"


def test_identify_glosas_missing_response(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when claim response is missing."""
    # Arrange
    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-12345",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_MISSING_CLAIM_RESPONSE"


def test_identify_glosas_multiple_items(mock_dmn_service, mock_metrics, basic_task_context):
    """Test identification with multiple denied items."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Múltiplas glosas identificadas",
        "risco": "BAIXO",
    }

    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimResponse": {
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "PROC-001"},
                    "adjudication": [
                        {"category": "denied", "amount": 100.00, "reason": "Duplicado"}
                    ],
                },
                {
                    "sequence": 2,
                    "productOrService": {"code": "PROC-002"},
                    "adjudication": [
                        {"category": "rejected", "amount": 200.00, "reason": "Não coberto"}
                    ],
                },
            ]
        },
        "claimId": "CLAIM-MULTI",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["glosaCount"] == 2
    assert result.variables["totalDeniedAmount"] == 300.00


def test_identify_glosas_reason_code_mapping(mock_dmn_service, mock_metrics, basic_task_context):
    """Test reason code mapping from payer text."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Glosa identificada",
        "risco": "BAIXO",
    }

    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimResponse": {
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "PROC-001"},
                    "adjudication": [
                        {"category": "denied", "amount": 100.00, "reason": "Falta de autorização"}
                    ],
                }
            ]
        },
        "claimId": "CLAIM-MAPPING",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    glosa_items = result.variables["glosaItems"]
    assert len(glosa_items) == 1
    assert glosa_items[0]["reason_code"] == "MISSING_AUTH"


def test_identify_glosas_old_dmn_schema(mock_dmn_service, mock_metrics, basic_task_context):
    """Test identification with old 5-output DMN schema."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "observacao": "Glosa válida",
        "acaoRecomendada": "Processar recurso",
        "riscoDenial": "BAIXO",
    }

    worker = IdentifyGlosaWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimResponse": {
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "PROC-001"},
                    "adjudication": [
                        {"category": "denied", "amount": 100.00, "reason": "Teste"}
                    ],
                }
            ]
        },
        "claimId": "CLAIM-OLD",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "action" in result.variables
    assert result.variables["risk"] == "BAIXO"
