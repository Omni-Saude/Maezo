"""
from __future__ import annotations

Tests for IdentifyGlosaWorker

Tests glosa identification from claim responses including denial extraction,
reason mapping, and amount calculation.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from healthcare_platform.revenue_cycle.glosa.workers import IdentifyGlosaWorker
from healthcare_platform.shared.domain.entities import ClaimResponse
from healthcare_platform.shared.domain.enums import GlosaReasonCode
from healthcare_platform.shared.domain.exceptions import GlosaException


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker instance for testing with mocked DMN service."""
    return IdentifyGlosaWorker(dmn_service=mock_dmn_service)


@pytest.fixture
def mock_job():
    """Create mock Zeebe job."""
    job = Mock()
    job.key = "test-job-123"
    return job


@pytest.fixture
def sample_claim_response():
    """Create sample claim response with glosas."""
    return {
        "id": "claim-response-001",
        "claimReference": "claim-001",
        "status": "active",
        "total": {"value": 5000.00, "currency": "BRL"},
        "items": [
            {
                "sequence": 1,
                "productOrService": {"code": "40101010"},
                "unitPrice": 1000.00,
                "quantity": 1,
                "adjudication": [
                    {
                        "category": "denied",
                        "reason": "Autorização ausente",
                        "amount": 1000.00,
                    }
                ],
            },
            {
                "sequence": 2,
                "productOrService": {"code": "40101020"},
                "unitPrice": 2000.00,
                "quantity": 2,
                "adjudication": [
                    {
                        "category": "denied",
                        "reason": "Quantidade excede limite autorizado",
                        "amount": 2000.00,
                    }
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_identify_glosas_from_claim_response(
    worker, mock_job, sample_claim_response
):
    """Test successful identification of glosas from claim response."""
    variables = {
        "claimResponse": sample_claim_response,
        "claimId": "claim-001",
    }

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert "glosaItems" in result.variables
    assert "totalDeniedAmount" in result.variables
    assert "glosaCount" in result.variables
    assert "hasGlosas" in result.variables

    glosa_items = result.variables["glosaItems"]
    assert len(glosa_items) == 2
    assert result.variables["glosaCount"] == 2
    assert result.variables["hasGlosas"] is True
    assert result.variables["totalDeniedAmount"] == 3000.00

    # Check first glosa
    glosa1 = glosa_items[0]
    assert glosa1["item_sequence"] == 1
    assert glosa1["procedure_code"] == "40101010"
    assert glosa1["reason_code"] == GlosaReasonCode.MISSING_AUTH.value
    assert glosa1["denied_amount"] == 1000.00
    assert glosa1["original_amount"] == 1000.00

    # Check second glosa
    glosa2 = glosa_items[1]
    assert glosa2["item_sequence"] == 2
    assert glosa2["reason_code"] == GlosaReasonCode.EXCEEDS_QUANTITY.value
    assert glosa2["denied_amount"] == 2000.00
    assert glosa2["original_amount"] == 4000.00


@pytest.mark.asyncio
async def test_no_glosas_found(worker, mock_job):
    """Test handling of claim response with no denials."""
    claim_response = {
        "id": "claim-response-002",
        "claimReference": "claim-002",
        "status": "active",
        "total": {"value": 1000.00, "currency": "BRL"},
        "items": [
            {
                "sequence": 1,
                "productOrService": {"code": "40101010"},
                "unitPrice": 1000.00,
                "quantity": 1,
                "adjudication": [
                    {
                        "category": "approved",
                        "amount": 1000.00,
                    }
                ],
            }
        ],
    }

    variables = {
        "claimResponse": claim_response,
        "claimId": "claim-002",
    }

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["glosaCount"] == 0
    assert result.variables["hasGlosas"] is False
    assert result.variables["totalDeniedAmount"] == 0.0
    assert len(result.variables["glosaItems"]) == 0


@pytest.mark.asyncio
async def test_multiple_glosas_same_item(worker, mock_job):
    """Test handling of multiple denials on the same item."""
    claim_response = {
        "id": "claim-response-003",
        "claimReference": "claim-003",
        "status": "active",
        "items": [
            {
                "sequence": 1,
                "productOrService": {"code": "40101010"},
                "unitPrice": 1000.00,
                "quantity": 1,
                "adjudication": [
                    {
                        "category": "denied",
                        "reason": "Autorização ausente",
                        "amount": 500.00,
                    },
                    {
                        "category": "denied",
                        "reason": "Documentação obrigatória ausente",
                        "amount": 500.00,
                    },
                ],
            }
        ],
    }

    variables = {
        "claimResponse": claim_response,
        "claimId": "claim-003",
    }

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["glosaCount"] == 2
    assert result.variables["totalDeniedAmount"] == 1000.00

    glosa_items = result.variables["glosaItems"]
    assert len(glosa_items) == 2
    assert glosa_items[0]["reason_code"] == GlosaReasonCode.MISSING_AUTH.value
    assert glosa_items[1]["reason_code"] == GlosaReasonCode.MISSING_DOCUMENTATION.value


@pytest.mark.asyncio
async def test_missing_claim_response_raises_error(worker, mock_job):
    """Test that missing claim response raises appropriate error."""
    variables = {
        "claimId": "claim-004",
    }

    result = await worker.process_task(mock_job, variables)

    assert result.success is False
    assert "não encontrada" in result.error_message.lower()


@pytest.mark.asyncio
async def test_reason_code_mapping(worker, mock_job):
    """Test correct mapping of various reason texts to reason codes."""
    test_cases = [
        ("Autorização expirada", GlosaReasonCode.EXPIRED_AUTH),
        ("Cobrança duplicada", GlosaReasonCode.DUPLICATE_CHARGE),
        ("Procedimento não coberto pelo plano", GlosaReasonCode.NOT_COVERED),
        ("Código de procedimento incorreto", GlosaReasonCode.WRONG_CODE),
        ("Procedimento incompatível com diagnóstico", GlosaReasonCode.INCOMPATIBLE_PROCEDURE),
        ("Divergência no valor cobrado", GlosaReasonCode.PRICE_DIVERGENCE),
        ("Erro desconhecido", GlosaReasonCode.TISS_VALIDATION),
    ]

    for reason_text, expected_code in test_cases:
        claim_response = {
            "id": "claim-response-test",
            "claimReference": "claim-test",
            "status": "active",
            "items": [
                {
                    "sequence": 1,
                    "productOrService": {"code": "40101010"},
                    "unitPrice": 100.00,
                    "quantity": 1,
                    "adjudication": [
                        {
                            "category": "denied",
                            "reason": reason_text,
                            "amount": 100.00,
                        }
                    ],
                }
            ],
        }

        variables = {
            "claimResponse": claim_response,
            "claimId": "claim-test",
        }

        result = await worker.process_task(mock_job, variables)

        assert result.success is True
        glosa_items = result.variables["glosaItems"]
        assert len(glosa_items) == 1
        assert glosa_items[0]["reason_code"] == expected_code.value


@pytest.mark.asyncio
async def test_claim_response_entity_input(worker, mock_job):
    """Test handling of ClaimResponse entity as input."""
    claim_response = ClaimResponse(
        id="claim-response-004",
        claim_reference="claim-004",
        status="active",
        items=[
            {
                "sequence": 1,
                "productOrService": {"code": "40101010"},
                "unitPrice": 1000.00,
                "quantity": 1,
                "adjudication": [
                    {
                        "category": "denied",
                        "reason": "Autorização ausente",
                        "amount": 1000.00,
                    }
                ],
            }
        ],
        total={"value": 1000.00, "currency": "BRL"},
    )

    variables = {
        "claimResponse": claim_response,
        "claimId": "claim-004",
    }

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["glosaCount"] == 1
    assert result.variables["hasGlosas"] is True
