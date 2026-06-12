"""
from __future__ import annotations

Tests for Update Payment Worker V2
"""
import pytest

pytest_plugins = ["tests.fixtures.workers"]
from healthcare_platform.revenue_cycle.glosa.workers import UpdatePaymentWorkerV2
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


def test_update_payment_success_prosseguir(mock_dmn_service, mock_metrics, basic_task_context):
    """Test successful payment update with PROSSEGUIR result."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Pagamento atualizado com sucesso",
        "risco": "BAIXO",
    }

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-12345",
        "appealStatus": "APPROVED",
        "originalAmount": "1000.00",
        "deniedAmount": "200.00",
        "recoveredAmount": "190.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "adjustedPaymentBRL" in result.variables
    assert result.variables["paymentAdjustmentType"] == "FULL_RECOVERY"
    assert result.variables["newBillingStatus"] == "PAYMENT_EXPECTED"
    assert result.variables["risk"] == "BAIXO"
    mock_dmn_service.evaluate.assert_called_once()


def test_update_payment_revisar(mock_dmn_service, mock_metrics, basic_task_context):
    """Test payment update requiring review."""
    # Arrange
    def dmn_revisar(tenant_id, category, table_name, inputs):
        return {
            "resultado": "REVISAR",
            "acao": "Verificar taxa de recuperação",
            "risco": "MEDIO",
        }

    mock_dmn_service.evaluate.side_effect = dmn_revisar

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-67890",
        "appealStatus": "PARTIALLY_APPROVED",
        "originalAmount": "1000.00",
        "deniedAmount": "300.00",
        "recoveredAmount": "100.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["requiresReview"] is True
    assert result.variables["paymentAdjustmentType"] == "PARTIAL_RECOVERY"
    assert result.variables["risk"] == "MEDIO"


def test_update_payment_bloquear(mock_dmn_service, mock_metrics, basic_task_context):
    """Test payment update blocked by DMN."""
    # Arrange
    def dmn_bloquear(tenant_id, category, table_name, inputs):
        return {
            "resultado": "BLOQUEAR",
            "acao": "Valor inválido - bloquear",
            "risco": "ALTO",
        }

    mock_dmn_service.evaluate.side_effect = dmn_bloquear

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-99999",
        "appealStatus": "DENIED",
        "originalAmount": "1000.00",
        "deniedAmount": "500.00",
        "recoveredAmount": "0.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_PAYMENT_UPDATE_BLOCKED"


def test_update_payment_missing_claim_id(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when claim ID is missing."""
    # Arrange
    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "originalAmount": "1000.00",
        "deniedAmount": "200.00",
        "recoveredAmount": "100.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_MISSING_CLAIM_ID"


def test_update_payment_invalid_amount(mock_dmn_service, mock_metrics, basic_task_context):
    """Test error when original amount is invalid."""
    # Arrange
    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-12345",
        "originalAmount": "0.00",
        "deniedAmount": "200.00",
        "recoveredAmount": "100.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_INVALID_AMOUNT"


def test_update_payment_full_recovery(mock_dmn_service, mock_metrics, basic_task_context):
    """Test full recovery scenario."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Recuperação total",
        "risco": "BAIXO",
    }

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-FULL",
        "originalAmount": "1000.00",
        "deniedAmount": "200.00",
        "recoveredAmount": "200.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["paymentAdjustmentType"] == "FULL_RECOVERY"
    assert result.variables["newBillingStatus"] == "PAYMENT_EXPECTED"
    assert result.variables["recoveryRate"] == 1.0


def test_update_payment_write_off(mock_dmn_service, mock_metrics, basic_task_context):
    """Test write-off scenario."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Baixa contábil",
        "risco": "MEDIO",
    }

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-WRITEOFF",
        "originalAmount": "1000.00",
        "deniedAmount": "500.00",
        "recoveredAmount": "0.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["paymentAdjustmentType"] == "WRITE_OFF"
    assert result.variables["newBillingStatus"] == "WRITTEN_OFF"
    assert float(result.variables["writeOffAmount"]) == 500.00


def test_update_payment_old_dmn_schema(mock_dmn_service, mock_metrics, basic_task_context):
    """Test payment update with old 5-output DMN schema."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "observacao": "Pagamento aprovado",
        "acaoRecomendada": "Processar",
        "riscoDenial": "BAIXO",
    }

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-OLD",
        "originalAmount": "1000.00",
        "deniedAmount": "200.00",
        "recoveredAmount": "150.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert "action" in result.variables
    assert result.variables["risk"] == "BAIXO"


def test_update_payment_partial_recovery(mock_dmn_service, mock_metrics, basic_task_context):
    """Test partial recovery scenario."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Recuperação parcial",
        "risco": "BAIXO",
    }

    worker = UpdatePaymentWorkerV2(
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )

    context = basic_task_context
    context.variables = {
        "claimId": "CLAIM-PARTIAL",
        "originalAmount": "1000.00",
        "deniedAmount": "300.00",
        "recoveredAmount": "150.00",
    }

    # Act
    result = worker.execute(context)

    # Assert
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["paymentAdjustmentType"] == "PARTIAL_RECOVERY"
    assert result.variables["newBillingStatus"] == "PARTIAL_PAYMENT_EXPECTED"
    assert result.variables["recoveryRate"] == 0.5
