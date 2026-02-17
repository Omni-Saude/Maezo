"""Tests for ParsePaymentFileWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker import (
    ParsePaymentFileWorker,
)
from healthcare_platform.revenue_cycle.collection.exceptions import CNABParsingError


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.FederatedDMNService')
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.parse_cnab')
async def test_parse_payment_file_cnab240_success(mock_parse_cnab, mock_dmn_service, mock_tenant):
    """Test successful CNAB 240 file parsing."""
    from datetime import date
    from decimal import Decimal
    from healthcare_platform.revenue_cycle.collection.lib.cnab_parser import CNABFileResult, CNABPaymentRecord, CNABFileHeader

    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'payment_type': 'full', 'valid': True}
    mock_dmn_service.return_value = mock_dmn

    # Mock CNAB parser result
    from healthcare_platform.revenue_cycle.collection.enums import CNABFormat

    mock_parse_cnab.return_value = CNABFileResult(
        header=CNABFileHeader(
            bank_code='001',
            bank_name='Banco do Brasil',
            company_name='Test Company',
            company_cnpj='12345678000199',
            file_date=date(2024, 1, 15),
            file_sequence=1,
            cnab_format=CNABFormat.CNAB_240
        ),
        payments=[
            CNABPaymentRecord(
                nosso_numero='123456',
                seu_numero='789',
                payment_date=date(2024, 1, 15),
                credit_date=date(2024, 1, 15),
                gross_amount=Decimal('1000.00'),
                discount_amount=Decimal('0.00'),
                interest_amount=Decimal('0.00'),
                penalty_amount=Decimal('0.00'),
                net_amount=Decimal('1000.00'),
                occurrence_code='06',
                occurrence_description='Liquidação',
                payer_name='Test Payer',
                payer_document='12345678000199',
                bank_code='001',
                agency='1234',
                account='567890',
                line_number=1,
            )
        ],
        total_records=1,
        total_amount=Decimal('1000.00'),
    )

    worker = ParsePaymentFileWorker()
    worker.dmn_service = mock_dmn

    # Minimal valid CNAB 240 content
    header = "001" + "0" * 4 + "0" + " " * 233
    detail_t = "001" + "0" * 4 + "3" + " " * 6 + "T" + " " * 226
    detail_u = "001" + "0" * 4 + "3" + " " * 6 + "U" + " " * 226
    trailer = "001" + "0" * 4 + "9" + " " * 233
    cnab_content = "\n".join([header, detail_t, detail_u, trailer])

    job = MagicMock()
    job.variables = {"file_content": cnab_content}

    result = await worker.execute(job)

    assert result.success is True
    assert "payment_records" in result.variables
    assert result.variables["total_records"] == 1
    assert len(result.variables["payment_records"]) == 1


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.FederatedDMNService')
async def test_parse_payment_file_empty_content(mock_dmn_service, mock_tenant):
    """Test parsing empty file fails."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn_service.return_value = mock_dmn

    worker = ParsePaymentFileWorker()
    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {"file_content": ""}

    result = await worker.execute(job)

    # Worker catches CNABParsingError and returns BPMN error
    assert result.success is False
    assert result.error_code is not None
    assert "vazio" in result.error_message


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.FederatedDMNService')
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.parse_cnab')
async def test_parse_payment_file_invalid_format(mock_parse_cnab, mock_dmn_service, mock_tenant):
    """Test parsing invalid CNAB format fails."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn_service.return_value = mock_dmn

    # Mock parser raising error
    mock_parse_cnab.side_effect = CNABParsingError("Formato CNAB não reconhecido")

    worker = ParsePaymentFileWorker()
    worker.dmn_service = mock_dmn

    # Too short to be valid CNAB
    cnab_content = "001234567890"

    job = MagicMock()
    job.variables = {"file_content": cnab_content}

    result = await worker.execute(job)

    # Worker catches CNABParsingError and returns BPMN error
    assert result.success is False
    assert result.error_code is not None
    assert "não reconhecido" in result.error_message or "Formato" in result.error_message


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.parse_payment_file_worker.FederatedDMNService')
async def test_parse_payment_file_missing_file_content(mock_dmn_service, mock_tenant):
    """Test parsing with missing file_content fails."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn_service.return_value = mock_dmn

    worker = ParsePaymentFileWorker()
    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {}

    result = await worker.execute(job)

    # Worker catches CNABParsingError and returns BPMN error
    assert result.success is False
    assert result.error_code is not None
    assert "vazio" in result.error_message
