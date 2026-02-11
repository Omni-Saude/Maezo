"""Unit tests for TasyClaimAdapter.

Tests Tasy CONTA_MEDICA to FHIR Claim R4 conversions with Brazilian coding systems.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.claim_adapter import (
    TasyClaimAdapter,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client fixture."""
    return MagicMock()


@pytest.fixture
def claim_adapter(fhir_client):
    """TasyClaimAdapter fixture."""
    return TasyClaimAdapter(fhir_client=fhir_client, tenant_id="test-hospital")


@pytest.fixture
def minimal_tasy_data():
    """Minimal valid Tasy billing data."""
    return {
        "NR_CONTA": "CONTA-12345",
        "DT_CONTA": "2024-02-10",
        "NR_PACIENTE": "PAC-789",
        "NR_ATENDIMENTO": "ATD-456",
    }


@pytest.fixture
def complete_tasy_data():
    """Complete Tasy billing data with all fields."""
    return {
        "NR_CONTA": "CONTA-12345",
        "DT_CONTA": "2024-02-10",
        "NR_PACIENTE": "PAC-789",
        "NR_ATENDIMENTO": "ATD-456",
        "IE_SITUACAO": "A",
        "TP_CONTA": "P",
        "IE_PRIORIDADE": "N",
        "CD_CONVENIO": "CONV-123",
        "VL_TOTAL": 2500.00,
        "items": [
            {
                "CD_ITEM_CONTA": "ITEM-001",
                "CD_PROCEDIMENTO": "40101010",
                "TP_PROCEDIMENTO": "TUSS",
                "DS_PROCEDIMENTO": "Consulta médica",
                "QT_ITEM": 1,
                "VL_UNITARIO": 500.00,
                "VL_TOTAL": 500.00,
                "DT_SERVICO": "2024-02-10",
            },
            {
                "CD_ITEM_CONTA": "ITEM-002",
                "CD_PROCEDIMENTO": "20104030",
                "TP_PROCEDIMENTO": "CBHPM",
                "DS_PROCEDIMENTO": "Raio-X de tórax",
                "QT_ITEM": 1,
                "VL_UNITARIO": 2000.00,
                "VL_TOTAL": 2000.00,
                "DT_SERVICO": "2024-02-10",
            },
        ],
    }


@pytest.mark.asyncio
async def test_adapt_minimal_input(claim_adapter, minimal_tasy_data):
    """Test adapt with only required fields."""
    fhir_claim = await claim_adapter.adapt(minimal_tasy_data)

    # Verify resource type
    assert fhir_claim["resourceType"] == "Claim"

    # Verify identifier
    assert len(fhir_claim["identifier"]) == 1
    assert fhir_claim["identifier"][0]["system"] == "http://tasy.com/fhir/identifier/conta-medica"
    assert fhir_claim["identifier"][0]["value"] == "CONTA-12345"

    # Verify status (default should be active)
    assert fhir_claim["status"] == "active"

    # Verify type
    assert "type" in fhir_claim
    assert fhir_claim["type"]["coding"][0]["system"] == "http://terminology.hl7.org/CodeSystem/claim-type"

    # Verify use
    assert fhir_claim["use"] == "claim"

    # Verify patient reference
    assert fhir_claim["patient"]["reference"] == "Patient/PAC-789"

    # Verify created date
    assert fhir_claim["created"] == "2024-02-10"

    # Verify provider
    assert "provider" in fhir_claim
    assert fhir_claim["provider"]["type"] == "Organization"

    # Verify meta tags
    assert fhir_claim["meta"]["tag"][0]["code"] == "test-hospital"


@pytest.mark.asyncio
async def test_adapt_complete_input(claim_adapter, complete_tasy_data):
    """Test adapt with all fields including items, insurance, total."""
    fhir_claim = await claim_adapter.adapt(complete_tasy_data)

    # Verify basic structure
    assert fhir_claim["resourceType"] == "Claim"
    assert fhir_claim["identifier"][0]["value"] == "CONTA-12345"

    # Verify status mapping
    assert fhir_claim["status"] == "active"

    # Verify type mapping
    assert fhir_claim["type"]["coding"][0]["code"] == "professional"

    # Verify priority
    assert "priority" in fhir_claim
    assert fhir_claim["priority"]["coding"][0]["system"] == "http://terminology.hl7.org/CodeSystem/processpriority"
    assert fhir_claim["priority"]["coding"][0]["code"] == "normal"

    # Verify insurance
    assert "insurance" in fhir_claim
    assert len(fhir_claim["insurance"]) == 1
    assert fhir_claim["insurance"][0]["sequence"] == 1
    assert fhir_claim["insurance"][0]["focal"] is True
    assert fhir_claim["insurance"][0]["coverage"]["identifier"]["value"] == "CONV-123"

    # Verify items
    assert "item" in fhir_claim
    assert len(fhir_claim["item"]) == 2

    # Verify first item
    item1 = fhir_claim["item"][0]
    assert item1["sequence"] == 1
    assert item1["productOrService"]["coding"][0]["code"] == "40101010"
    assert item1["quantity"]["value"] == 1
    assert item1["unitPrice"]["value"] == 500.00
    assert item1["unitPrice"]["currency"] == "BRL"
    assert item1["net"]["value"] == 500.00
    assert item1["servicedDate"] == "2024-02-10"

    # Verify second item
    item2 = fhir_claim["item"][1]
    assert item2["sequence"] == 2
    assert item2["productOrService"]["coding"][0]["code"] == "20104030"

    # Verify total
    assert "total" in fhir_claim
    assert fhir_claim["total"]["value"] == 2500.00
    assert fhir_claim["total"]["currency"] == "BRL"


@pytest.mark.asyncio
async def test_adapt_with_brazilian_codes(claim_adapter, complete_tasy_data):
    """Test that Brazilian coding systems (TUSS/CBHPM/CID-10) are properly mapped."""
    fhir_claim = await claim_adapter.adapt(complete_tasy_data)

    # Verify TUSS coding system
    item1 = fhir_claim["item"][0]
    assert item1["productOrService"]["coding"][0]["system"] == "http://www.ans.gov.br/tuss"
    assert item1["productOrService"]["coding"][0]["code"] == "40101010"
    assert item1["productOrService"]["coding"][0]["display"] == "Consulta médica"

    # Verify CBHPM coding system
    item2 = fhir_claim["item"][1]
    assert item2["productOrService"]["coding"][0]["system"] == "http://www.cbhpm.com.br"
    assert item2["productOrService"]["coding"][0]["code"] == "20104030"
    assert item2["productOrService"]["coding"][0]["display"] == "Raio-X de tórax"


@pytest.mark.asyncio
async def test_adapt_with_cid10_code(claim_adapter, minimal_tasy_data):
    """Test CID-10 coding system support."""
    tasy_data = {
        **minimal_tasy_data,
        "items": [
            {
                "CD_PROCEDIMENTO": "J18.9",
                "TP_PROCEDIMENTO": "CID10",
                "DS_PROCEDIMENTO": "Pneumonia não especificada",
                "QT_ITEM": 1,
                "VL_UNITARIO": 1000.00,
                "VL_TOTAL": 1000.00,
            }
        ],
    }

    fhir_claim = await claim_adapter.adapt(tasy_data)

    # Verify CID-10 coding system
    item = fhir_claim["item"][0]
    assert item["productOrService"]["coding"][0]["system"] == "http://hl7.org/fhir/sid/icd-10"
    assert item["productOrService"]["coding"][0]["code"] == "J18.9"
    assert item["productOrService"]["coding"][0]["display"] == "Pneumonia não especificada"


@pytest.mark.asyncio
async def test_reverse_adapt(claim_adapter, complete_tasy_data):
    """Test reverse adaptation from FHIR Claim back to Tasy format."""
    # First adapt to FHIR
    fhir_claim = await claim_adapter.adapt(complete_tasy_data)

    # Then reverse adapt
    tasy_data = await claim_adapter.reverse_adapt(fhir_claim)

    # Verify core fields
    assert tasy_data["NR_CONTA"] == "CONTA-12345"
    assert tasy_data["DT_CONTA"] == "2024-02-10"
    assert tasy_data["NR_PACIENTE"] == "PAC-789"
    assert tasy_data["IE_SITUACAO"] == "A"
    assert tasy_data["TP_CONTA"] == "P"
    assert tasy_data["VL_TOTAL"] == 2500.00

    # Verify items
    assert "items" in tasy_data
    assert len(tasy_data["items"]) == 2

    # Verify first item
    item1 = tasy_data["items"][0]
    assert item1["CD_PROCEDIMENTO"] == "40101010"
    assert item1["TP_PROCEDIMENTO"] == "TUSS"
    assert item1["DS_PROCEDIMENTO"] == "Consulta médica"
    assert item1["QT_ITEM"] == 1
    assert item1["VL_UNITARIO"] == 500.00
    assert item1["VL_TOTAL"] == 500.00
    assert item1["DT_SERVICO"] == "2024-02-10"

    # Verify second item
    item2 = tasy_data["items"][1]
    assert item2["CD_PROCEDIMENTO"] == "20104030"
    assert item2["TP_PROCEDIMENTO"] == "CBHPM"


@pytest.mark.asyncio
async def test_invalid_input_raises(claim_adapter):
    """Test that missing required fields raise ValueError."""
    invalid_data = {
        "NR_CONTA": "CONTA-12345",
        # Missing DT_CONTA, NR_PACIENTE, NR_ATENDIMENTO
    }

    with pytest.raises(ValueError) as exc_info:
        await claim_adapter.adapt(invalid_data)

    assert "Missing required fields" in str(exc_info.value)


@pytest.mark.asyncio
async def test_status_mapping(claim_adapter, minimal_tasy_data):
    """Test various status code mappings."""
    test_cases = [
        ("A", "active"),
        ("C", "cancelled"),
        ("E", "entered-in-error"),
        ("F", "active"),
        ("P", "active"),
        ("G", "active"),
        (None, "active"),  # Default
    ]

    for tasy_status, expected_fhir_status in test_cases:
        tasy_data = {**minimal_tasy_data}
        if tasy_status is not None:
            tasy_data["IE_SITUACAO"] = tasy_status

        fhir_claim = await claim_adapter.adapt(tasy_data)
        assert fhir_claim["status"] == expected_fhir_status


@pytest.mark.asyncio
async def test_type_mapping(claim_adapter, minimal_tasy_data):
    """Test various claim type mappings."""
    test_cases = [
        ("I", "institutional"),
        ("P", "professional"),
        ("F", "pharmacy"),
        (None, "professional"),  # Default
    ]

    for tasy_type, expected_claim_type in test_cases:
        tasy_data = {**minimal_tasy_data}
        if tasy_type is not None:
            tasy_data["TP_CONTA"] = tasy_type

        fhir_claim = await claim_adapter.adapt(tasy_data)
        assert fhir_claim["type"]["coding"][0]["code"] == expected_claim_type


@pytest.mark.asyncio
async def test_priority_mapping(claim_adapter, minimal_tasy_data):
    """Test priority code mappings."""
    test_cases = [
        ("N", "normal"),
        ("S", "stat"),
        ("U", "stat"),
    ]

    for tasy_priority, expected_fhir_priority in test_cases:
        tasy_data = {**minimal_tasy_data, "IE_PRIORIDADE": tasy_priority}

        fhir_claim = await claim_adapter.adapt(tasy_data)
        assert fhir_claim["priority"]["coding"][0]["code"] == expected_fhir_priority
