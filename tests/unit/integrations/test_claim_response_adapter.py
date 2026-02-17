"""Tests for TasyClaimResponseAdapter."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.claim_response_adapter import (
    TasyClaimResponseAdapter,
)


@pytest.fixture
def mock_fhir_client():
    """Create mock FHIR client."""
    return MagicMock()


@pytest.fixture
def adapter(mock_fhir_client):
    """Create adapter instance."""
    return TasyClaimResponseAdapter(
        fhir_client=mock_fhir_client,
        tenant_id="test-hospital",
    )


@pytest.mark.asyncio
async def test_adapt_minimal_input(adapter):
    """Test conversion with minimal required fields only."""
    tasy_data = {
        "NR_GLOSA": "12345",
        "CD_CONTA": "CONTA-789",
        "VL_GLOSADO": 1500.00,
        "CD_MOTIVO_GLOSA": "302",
    }

    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "ClaimResponse"
    assert result["id"] == "12345"
    assert result["status"] == "active"
    assert result["use"] == "claim"
    assert result["outcome"] == "queued"  # Default when ST_GLOSA not provided

    # Check request reference
    assert result["request"]["reference"] == "Claim/CONTA-789"

    # Check items with adjudication
    assert len(result["item"]) == 1
    assert result["item"][0]["itemSequence"] == 1

    # Check adjudication with ANS code
    adjudication = result["item"][0]["adjudication"][0]
    assert adjudication["amount"]["value"] == 1500.00
    assert adjudication["amount"]["currency"] == "BRL"

    # Check ANS code in reason
    reason_coding = adjudication["reason"]["coding"][0]
    assert reason_coding["system"] == "http://www.ans.gov.br/glosa-codes"
    assert reason_coding["code"] == "302"

    # Check total
    assert len(result["total"]) >= 1
    assert result["total"][0]["category"]["coding"][0]["code"] == "denied"
    assert result["total"][0]["amount"]["value"] == 1500.00


@pytest.mark.asyncio
async def test_adapt_complete_input(adapter):
    """Test conversion with all fields including payment and process notes."""
    tasy_data = {
        "NR_GLOSA": "12345",
        "CD_CONTA": "CONTA-789",
        "VL_GLOSADO": 1500.00,
        "CD_MOTIVO_GLOSA": "201",
        "DS_MOTIVO": "Falta de indicação clínica",
        "DT_GLOSA": "2024-01-15 10:30:00",
        "ST_GLOSA": "N",  # Negada (Denied) -> outcome: error
        "CD_CONVENIO": "CONV-123",
        "CD_PACIENTE": "PAC-456",
        "DT_PAGAMENTO": "2024-02-01",
        "VL_PAGO": 3500.00,
        "VL_APRESENTADO": 5000.00,
        "DS_OBSERVACAO": "Documentação médica insuficiente",
        "ITENS": [
            {
                "VL_GLOSADO": 800.00,
                "CD_MOTIVO_GLOSA": "201",
                "DS_MOTIVO": "Procedimento sem indicação",
            },
            {
                "VL_GLOSADO": 700.00,
                "CD_MOTIVO_GLOSA": "203",
                "DS_MOTIVO": "Material não coberto",
            },
        ],
    }

    result = await adapter.adapt(tasy_data)

    # Check basic fields
    assert result["resourceType"] == "ClaimResponse"
    assert result["id"] == "12345"
    assert result["outcome"] == "error"  # ST_GLOSA: N -> error
    assert result["disposition"] == "Falta de indicação clínica"
    assert result["created"] == "2024-01-15T10:30:00"

    # Check patient and insurer references
    assert result["patient"]["reference"] == "Patient/PAC-456"
    assert result["insurer"]["reference"] == "Organization/CONV-123"
    assert result["insurer"]["display"] == "Convênio CONV-123"

    # Check itemized adjudications
    assert len(result["item"]) == 2

    item1 = result["item"][0]
    assert item1["itemSequence"] == 1
    assert item1["adjudication"][0]["amount"]["value"] == 800.00
    assert item1["adjudication"][0]["reason"]["coding"][0]["code"] == "201"

    item2 = result["item"][1]
    assert item2["itemSequence"] == 2
    assert item2["adjudication"][0]["amount"]["value"] == 700.00
    assert item2["adjudication"][0]["reason"]["coding"][0]["code"] == "203"

    # Check totals (denied, submitted, eligible)
    assert len(result["total"]) == 3
    denied_total = next(t for t in result["total"] if t["category"]["coding"][0]["code"] == "denied")
    assert denied_total["amount"]["value"] == 1500.00

    submitted_total = next(t for t in result["total"] if t["category"]["coding"][0]["code"] == "submitted")
    assert submitted_total["amount"]["value"] == 5000.00

    eligible_total = next(t for t in result["total"] if t["category"]["coding"][0]["code"] == "eligible")
    assert eligible_total["amount"]["value"] == 3500.00

    # Check payment information
    assert result["payment"]["date"] == "2024-02-01"
    assert result["payment"]["amount"]["value"] == 3500.00
    assert result["payment"]["amount"]["currency"] == "BRL"

    # Check process notes
    assert len(result["processNote"]) == 1
    assert result["processNote"][0]["text"] == "Documentação médica insuficiente"


@pytest.mark.asyncio
async def test_adapt_with_brazilian_codes(adapter):
    """Test that ANS glosa codes are properly mapped to FHIR adjudication categories."""
    test_cases = [
        ("101", "benefit"),      # Administrative denial
        ("201", "eligible"),     # Clinical denial
        ("301", "submitted"),    # Technical denial
        ("401", "copay"),        # Financial denial (copay)
        ("402", "deductible"),   # Financial denial (deductible)
        ("999", "denied"),       # Unknown code -> default to denied
    ]

    for ans_code, expected_category in test_cases:
        tasy_data = {
            "NR_GLOSA": f"glosa-{ans_code}",
            "CD_CONTA": "CONTA-100",
            "VL_GLOSADO": 1000.00,
            "CD_MOTIVO_GLOSA": ans_code,
        }

        result = await adapter.adapt(tasy_data)

        # Check that ANS code is in the reason
        adjudication = result["item"][0]["adjudication"][0]
        reason_coding = adjudication["reason"]["coding"][0]
        assert reason_coding["system"] == "http://www.ans.gov.br/glosa-codes"
        assert reason_coding["code"] == ans_code

        # Check that category is mapped correctly
        category_code = adjudication["category"]["coding"][0]["code"]
        assert category_code == expected_category, f"ANS code {ans_code} should map to {expected_category}"


@pytest.mark.asyncio
async def test_reverse_adapt(adapter):
    """Test converting FHIR ClaimResponse back to TASY format."""
    fhir_claim_response = {
        "resourceType": "ClaimResponse",
        "id": "glosa-12345",
        "identifier": [
            {
                "system": "https://tasy.test-hospital/glosa",
                "value": "12345",
            }
        ],
        "status": "active",
        "outcome": "partial",
        "request": {
            "reference": "Claim/CONTA-789"
        },
        "created": "2024-01-15T10:30:00",
        "disposition": "Parcialmente aprovado",
        "item": [
            {
                "itemSequence": 1,
                "adjudication": [
                    {
                        "category": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/adjudication",
                                    "code": "denied",
                                }
                            ]
                        },
                        "reason": {
                            "coding": [
                                {
                                    "system": "http://www.ans.gov.br/glosa-codes",
                                    "code": "201",
                                }
                            ]
                        },
                        "amount": {
                            "value": 1500.00,
                            "currency": "BRL",
                        },
                    }
                ],
            }
        ],
        "total": [
            {
                "category": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/adjudication",
                            "code": "denied",
                        }
                    ]
                },
                "amount": {
                    "value": 1500.00,
                    "currency": "BRL",
                },
            }
        ],
        "payment": {
            "date": "2024-02-01",
            "amount": {
                "value": 3500.00,
                "currency": "BRL",
            },
        },
        "processNote": [
            {
                "text": "Revisão de auditoria concluída"
            }
        ],
    }

    result = await adapter.reverse_adapt(fhir_claim_response)

    assert result["NR_GLOSA"] == "12345"
    assert result["CD_CONTA"] == "CONTA-789"
    assert result["VL_GLOSADO"] == 1500.00
    assert result["CD_MOTIVO_GLOSA"] == "201"
    assert result["DS_MOTIVO"] == "Parcialmente aprovado"
    assert result["ST_GLOSA"] == "R"  # partial -> R (Recurso)
    assert result["DT_GLOSA"] == "2024-01-15T10:30:00"
    assert result["DT_PAGAMENTO"] == "2024-02-01"
    assert result["VL_PAGO"] == 3500.00
    assert result["DS_OBSERVACAO"] == "Revisão de auditoria concluída"


@pytest.mark.asyncio
async def test_invalid_input_raises(adapter):
    """Test that missing required fields raise ValueError."""
    # Missing NR_GLOSA
    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt({
            "CD_CONTA": "CONTA-789",
            "VL_GLOSADO": 1500.00,
            "CD_MOTIVO_GLOSA": "302",
        })

    # Missing CD_CONTA
    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt({
            "NR_GLOSA": "12345",
            "VL_GLOSADO": 1500.00,
            "CD_MOTIVO_GLOSA": "302",
        })

    # Missing VL_GLOSADO
    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt({
            "NR_GLOSA": "12345",
            "CD_CONTA": "CONTA-789",
            "CD_MOTIVO_GLOSA": "302",
        })

    # Missing CD_MOTIVO_GLOSA
    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt({
            "NR_GLOSA": "12345",
            "CD_CONTA": "CONTA-789",
            "VL_GLOSADO": 1500.00,
        })


@pytest.mark.asyncio
async def test_status_mapping(adapter):
    """Test TASY status codes map correctly to FHIR outcomes."""
    status_tests = [
        ("A", "complete"),
        ("N", "error"),
        ("R", "partial"),
        ("P", "queued"),
        ("I", "queued"),
        ("X", "queued"),  # Unknown status -> default to queued
    ]

    for tasy_status, expected_outcome in status_tests:
        tasy_data = {
            "NR_GLOSA": "12345",
            "CD_CONTA": "CONTA-789",
            "VL_GLOSADO": 1000.00,
            "CD_MOTIVO_GLOSA": "201",
            "ST_GLOSA": tasy_status,
        }

        result = await adapter.adapt(tasy_data)
        assert result["outcome"] == expected_outcome, f"Status {tasy_status} should map to {expected_outcome}"


@pytest.mark.asyncio
async def test_date_parsing(adapter):
    """Test various TASY date formats are parsed correctly."""
    date_tests = [
        ("2024-01-15 10:30:00", "2024-01-15T10:30:00"),
        ("2024-01-15", "2024-01-15T00:00:00"),
        ("15/01/2024", "2024-01-15T00:00:00"),
    ]

    for tasy_date, expected_iso in date_tests:
        tasy_data = {
            "NR_GLOSA": "12345",
            "CD_CONTA": "CONTA-789",
            "VL_GLOSADO": 1000.00,
            "CD_MOTIVO_GLOSA": "201",
            "DT_GLOSA": tasy_date,
        }

        result = await adapter.adapt(tasy_data)
        assert result["created"] == expected_iso, f"Date {tasy_date} should parse to {expected_iso}"


@pytest.mark.asyncio
async def test_reverse_adapt_invalid_resource_type(adapter):
    """Test reverse_adapt raises error for non-ClaimResponse resources."""
    invalid_resource = {
        "resourceType": "Claim",
        "id": "claim-123",
    }

    with pytest.raises(ValueError, match="Resource must be of type ClaimResponse"):
        await adapter.reverse_adapt(invalid_resource)
