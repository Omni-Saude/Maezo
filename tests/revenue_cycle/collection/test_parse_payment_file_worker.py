"""Tests for ParsePaymentFileWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.parse_payment_file_worker import (
    ParsePaymentFileWorker,
)
from platform.revenue_cycle.collection.exceptions import CNABParsingError


@pytest.mark.asyncio
async def test_parse_payment_file_cnab240_success():
    """Test successful CNAB 240 file parsing."""
    worker = ParsePaymentFileWorker()

    # Minimal valid CNAB 240 header (240 chars)
    header = "001" + "0" * 4 + "0" + " " * 233  # Bank code + record type 0
    detail_t = "001" + "0" * 4 + "3" + " " * 6 + "T" + " " * 226  # Detail segment T
    detail_u = "001" + "0" * 4 + "3" + " " * 6 + "U" + " " * 226  # Detail segment U
    trailer = "001" + "0" * 4 + "9" + " " * 233  # Trailer

    cnab_content = "\n".join([header, detail_t, detail_u, trailer])

    task_vars = {"file_content": cnab_content}

    result = await worker.execute(task_vars)

    assert "payment_records" in result
    assert "header" in result
    assert result["header"]["cnab_format"] == "cnab_240"
    assert "total_records" in result


@pytest.mark.asyncio
async def test_parse_payment_file_empty_content():
    """Test parsing empty file fails."""
    worker = ParsePaymentFileWorker()

    task_vars = {"file_content": ""}

    with pytest.raises(CNABParsingError, match="vazio"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_parse_payment_file_invalid_format():
    """Test parsing invalid CNAB format fails."""
    worker = ParsePaymentFileWorker()

    # Too short to be valid CNAB
    cnab_content = "001234567890"

    task_vars = {"file_content": cnab_content}

    with pytest.raises(CNABParsingError, match="não reconhecido"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_parse_payment_file_missing_file_content():
    """Test parsing with missing file_content fails."""
    worker = ParsePaymentFileWorker()

    task_vars = {}

    with pytest.raises(CNABParsingError, match="vazio"):
        await worker.execute(task_vars)
