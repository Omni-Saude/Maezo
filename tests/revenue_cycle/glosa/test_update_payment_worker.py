"""
Tests for Update Payment Worker.

Tests payment recalculation after glosa appeal outcomes.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock

from platform.revenue_cycle.glosa.workers.update_payment_worker import UpdatePaymentWorker


@pytest.fixture
def update_payment_worker():
    """Create UpdatePaymentWorker instance."""
    return UpdatePaymentWorker()


@pytest.fixture
def base_input_variables():
    """Create base input variables for payment update."""
    return {
        "claimId": "CLAIM-123456",
        "appealStatus": "APPROVED",
        "originalAmount": "1000.00",
        "deniedAmount": "250.00",
        "recoveredAmount": "0.00",
        "glosaItems": [
            {"glosaId": "GLOSA-001", "deniedAmount": "150.00"},
            {"glosaId": "GLOSA-002", "deniedAmount": "100.00"},
        ],
    }


@pytest.mark.asyncio
async def test_full_recovery(update_payment_worker, base_input_variables):
    """Test full recovery scenario (>95% recovered)."""
    # Arrange - recover 240 of 250 denied (96%)
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "240.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("990.00")  # 1000 - 250 + 240
    assert result.variables["paymentAdjustmentType"] == "FULL_RECOVERY"
    assert result.variables["newBillingStatus"] == "PAYMENT_EXPECTED"
    assert Decimal(result.variables["writeOffAmount"]) == Decimal("10.00")
    assert "Recuperação Total" in result.variables["financialSummary"]


@pytest.mark.asyncio
async def test_partial_recovery(update_payment_worker, base_input_variables):
    """Test partial recovery scenario (10-95% recovered)."""
    # Arrange - recover 100 of 250 denied (40%)
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "100.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("850.00")  # 1000 - 250 + 100
    assert result.variables["paymentAdjustmentType"] == "PARTIAL_RECOVERY"
    assert result.variables["newBillingStatus"] == "PARTIAL_PAYMENT_EXPECTED"
    assert Decimal(result.variables["writeOffAmount"]) == Decimal("150.00")
    assert "Recuperação Parcial" in result.variables["financialSummary"]


@pytest.mark.asyncio
async def test_no_recovery_write_off(update_payment_worker, base_input_variables):
    """Test no recovery scenario (write-off)."""
    # Arrange - no recovery
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "0.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("750.00")  # 1000 - 250
    assert result.variables["paymentAdjustmentType"] == "WRITE_OFF"
    assert result.variables["newBillingStatus"] == "WRITTEN_OFF"
    assert Decimal(result.variables["writeOffAmount"]) == Decimal("250.00")
    assert "Baixa Contábil" in result.variables["financialSummary"]


@pytest.mark.asyncio
async def test_minimal_recovery(update_payment_worker, base_input_variables):
    """Test minimal recovery scenario (<10% recovered)."""
    # Arrange - recover 20 of 250 denied (8%)
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "20.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("770.00")  # 1000 - 250 + 20
    assert result.variables["paymentAdjustmentType"] == "MINIMAL_RECOVERY"
    assert result.variables["newBillingStatus"] == "PARTIAL_PAYMENT_EXPECTED"
    assert Decimal(result.variables["writeOffAmount"]) == Decimal("230.00")


@pytest.mark.asyncio
async def test_payment_calculation_accuracy(update_payment_worker):
    """Test payment calculation with various decimal amounts."""
    # Arrange - precise decimal amounts
    input_vars = {
        "claimId": "CLAIM-999",
        "appealStatus": "PARTIALLY_APPROVED",
        "originalAmount": "1234.56",
        "deniedAmount": "345.67",
        "recoveredAmount": "123.45",
        "glosaItems": [],
    }

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    # 1234.56 - 345.67 + 123.45 = 1012.34
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("1012.34")


@pytest.mark.asyncio
async def test_negative_adjusted_payment_becomes_zero(update_payment_worker):
    """Test that negative adjusted payment is set to zero."""
    # Arrange - edge case where recovery exceeds reasonable bounds
    input_vars = {
        "claimId": "CLAIM-888",
        "appealStatus": "DENIED",
        "originalAmount": "100.00",
        "deniedAmount": "150.00",  # Denied more than original (edge case)
        "recoveredAmount": "0.00",
        "glosaItems": [],
    }

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("0.00")
    assert result.variables["newBillingStatus"] == "WRITTEN_OFF"


@pytest.mark.asyncio
async def test_missing_claim_id(update_payment_worker, base_input_variables):
    """Test validation error when claim ID is missing."""
    # Arrange
    invalid_vars = base_input_variables.copy()
    del invalid_vars["claimId"]

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is False
    assert "conta" in result.error_message.lower()


@pytest.mark.asyncio
async def test_zero_original_amount(update_payment_worker, base_input_variables):
    """Test validation error when original amount is zero."""
    # Arrange
    invalid_vars = base_input_variables.copy()
    invalid_vars["originalAmount"] = "0.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is False
    assert "maior que zero" in result.error_message.lower()


@pytest.mark.asyncio
async def test_no_denial_no_adjustment(update_payment_worker):
    """Test scenario with no denials (no adjustment needed)."""
    # Arrange - no denied amount
    input_vars = {
        "claimId": "CLAIM-777",
        "appealStatus": "N/A",
        "originalAmount": "1000.00",
        "deniedAmount": "0.00",
        "recoveredAmount": "0.00",
        "glosaItems": [],
    }

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert Decimal(result.variables["adjustedPaymentBRL"]) == Decimal("1000.00")
    assert result.variables["paymentAdjustmentType"] == "NO_ADJUSTMENT"
    assert Decimal(result.variables["writeOffAmount"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_financial_summary_content(update_payment_worker, base_input_variables):
    """Test financial summary contains all expected information."""
    # Arrange
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "150.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    summary = result.variables["financialSummary"]
    assert "Valor Original: R$ 1000.00" in summary
    assert "Valor Glosado: R$ 250.00" in summary
    assert "Valor Recuperado: R$ 150.00" in summary
    assert "Pagamento Ajustado: R$ 900.00" in summary
    assert "Valor Baixado: R$ 100.00" in summary
    assert "Tipo de Ajuste:" in summary


@pytest.mark.asyncio
async def test_exact_threshold_boundary_full_recovery(update_payment_worker, base_input_variables):
    """Test exact 95% threshold boundary for full recovery."""
    # Arrange - exactly 95% recovered (237.5 of 250)
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "237.50"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert result.variables["paymentAdjustmentType"] == "FULL_RECOVERY"


@pytest.mark.asyncio
async def test_exact_threshold_boundary_partial_recovery(update_payment_worker, base_input_variables):
    """Test exact 10% threshold boundary for write-off."""
    # Arrange - exactly 10% recovered (25 of 250)
    input_vars = base_input_variables.copy()
    input_vars["recoveredAmount"] = "25.00"

    mock_job = Mock()

    # Act
    result = await update_payment_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert result.variables["paymentAdjustmentType"] == "PARTIAL_RECOVERY"
