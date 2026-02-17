"""Unit tests for TasyMedicationRequestAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.medication_request_adapter import (
    TasyMedicationRequestAdapter,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return MagicMock()


@pytest.fixture
def adapter(fhir_client):
    """Create adapter instance."""
    return TasyMedicationRequestAdapter(
        fhir_client=fhir_client,
        tenant_id="test-hospital",
    )


@pytest.mark.asyncio
async def test_adapt_minimal_input(adapter):
    """Test adaptation with only required fields."""
    tasy_data = {
        "NR_PRESCRICAO": "PRESC-001",
        "DT_PRESCRICAO": "2024-02-10T10:30:00",
        "NR_PACIENTE": "123456",
        "CD_ANVISA": "1234567890123",
    }

    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "MedicationRequest"
    assert result["status"] == "active"
    assert result["intent"] == "order"
    assert result["identifier"][0]["value"] == "PRESC-001"
    assert result["subject"]["reference"] == "Patient/123456"
    assert result["authoredOn"] == "2024-02-10T10:30:00"

    # Verify ANVISA code in medication
    assert any(
        coding["system"] == "http://www.anvisa.gov.br/medicamentos"
        and coding["code"] == "1234567890123"
        for coding in result["medicationCodeableConcept"]["coding"]
    )


@pytest.mark.asyncio
async def test_adapt_complete_input(adapter):
    """Test adaptation with all fields including dosage and dispense."""
    tasy_data = {
        "NR_PRESCRICAO": "PRESC-002",
        "DT_PRESCRICAO": "2024-02-10T14:00:00",
        "NR_PACIENTE": "789012",
        "NR_ATENDIMENTO": "ATD-456",
        "NR_CRM": "CRM/SP 123456",
        "NM_MEDICO": "Dr. Carlos Silva",
        "CD_ANVISA": "1234567890123",
        "CD_ATC": "J01CA04",
        "CD_FORMULARIO": "MED-AMO-500",
        "NM_MEDICAMENTO": "Amoxicilina 500mg",
        "DS_POSOLOGIA": "1 comprimido a cada 8 horas por 7 dias",
        "VL_DOSE": 500,
        "DS_DOSE_UNIDADE": "mg",
        "NR_FREQUENCIA": 3,
        "NR_PERIODO": 8,
        "DS_PERIODO_UNIDADE": "h",
        "VIA_ADMINISTRACAO": "VO",
        "QT_PRESCRITA": 21,
        "NR_DIAS_TRATAMENTO": 7,
        "IE_SITUACAO": "A",
        "IE_INTENCAO": "order",
    }

    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "MedicationRequest"
    assert result["status"] == "active"
    assert result["intent"] == "order"
    assert result["encounter"]["reference"] == "Encounter/ATD-456"

    # Verify requester with CRM
    assert result["requester"]["identifier"]["system"] == "http://www.crm.org.br/practitioner"
    assert result["requester"]["identifier"]["value"] == "CRM/SP 123456"
    assert result["requester"]["display"] == "Dr. Carlos Silva"

    # Verify medication codes (ANVISA, ATC, formulary)
    codings = result["medicationCodeableConcept"]["coding"]
    assert len(codings) == 3
    assert any(c["system"] == "http://www.anvisa.gov.br/medicamentos" for c in codings)
    assert any(c["system"] == "http://www.whocc.no/atc" and c["code"] == "J01CA04" for c in codings)
    assert any(c["system"] == "http://tasy.com/fhir/identifier/formulary" for c in codings)

    # Verify dosage instruction
    dosage = result["dosageInstruction"][0]
    assert dosage["text"] == "1 comprimido a cada 8 horas por 7 dias"
    assert dosage["timing"]["repeat"]["frequency"] == 3
    assert dosage["timing"]["repeat"]["period"] == 8
    assert dosage["timing"]["repeat"]["periodUnit"] == "h"
    assert dosage["route"]["coding"][0]["code"] == "26643006"  # Oral route SNOMED
    assert dosage["doseAndRate"][0]["doseQuantity"]["value"] == 500
    assert dosage["doseAndRate"][0]["doseQuantity"]["unit"] == "mg"

    # Verify dispense request
    assert result["dispenseRequest"]["quantity"]["value"] == 21
    assert result["dispenseRequest"]["expectedSupplyDuration"]["value"] == 7
    assert result["dispenseRequest"]["expectedSupplyDuration"]["unit"] == "dias"


@pytest.mark.asyncio
async def test_adapt_with_brazilian_codes(adapter):
    """Test that Brazilian pharmaceutical codes are properly mapped."""
    tasy_data = {
        "NR_PRESCRICAO": "PRESC-003",
        "DT_PRESCRICAO": "2024-02-10T16:00:00",
        "NR_PACIENTE": "345678",
        "CD_ANVISA": "9876543210987",
        "CD_ATC": "N02BE01",
        "NM_MEDICAMENTO": "Paracetamol 750mg",
        "NR_CRM": "CRM/RJ 654321",
    }

    result = await adapter.adapt(tasy_data)

    # Verify ANVISA system
    anvisa_coding = next(
        (c for c in result["medicationCodeableConcept"]["coding"]
         if c["system"] == "http://www.anvisa.gov.br/medicamentos"),
        None
    )
    assert anvisa_coding is not None
    assert anvisa_coding["code"] == "9876543210987"

    # Verify ATC system
    atc_coding = next(
        (c for c in result["medicationCodeableConcept"]["coding"]
         if c["system"] == "http://www.whocc.no/atc"),
        None
    )
    assert atc_coding is not None
    assert atc_coding["code"] == "N02BE01"

    # Verify CRM system
    assert result["requester"]["identifier"]["system"] == "http://www.crm.org.br/practitioner"
    assert result["requester"]["identifier"]["value"] == "CRM/RJ 654321"


@pytest.mark.asyncio
async def test_reverse_adapt(adapter):
    """Test reverse adaptation from FHIR to Tasy format."""
    fhir_resource = {
        "resourceType": "MedicationRequest",
        "identifier": [{
            "system": "http://tasy.com/fhir/identifier/prescricao",
            "value": "PRESC-999"
        }],
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://www.anvisa.gov.br/medicamentos",
                    "code": "1111111111111",
                    "display": "Ibuprofeno 600mg"
                },
                {
                    "system": "http://www.whocc.no/atc",
                    "code": "M01AE01"
                },
                {
                    "system": "http://tasy.com/fhir/identifier/formulary",
                    "code": "MED-IBU-600"
                }
            ]
        },
        "subject": {"reference": "Patient/888999"},
        "encounter": {"reference": "Encounter/ATD-777"},
        "authoredOn": "2024-02-11T09:00:00",
        "requester": {
            "identifier": {
                "system": "http://www.crm.org.br/practitioner",
                "value": "CRM/MG 111222"
            },
            "display": "Dra. Maria Santos"
        },
        "dosageInstruction": [{
            "text": "1 comprimido a cada 6 horas",
            "timing": {
                "repeat": {
                    "frequency": 4,
                    "period": 6,
                    "periodUnit": "h"
                }
            },
            "route": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "26643006",
                    "display": "Oral route"
                }]
            },
            "doseAndRate": [{
                "doseQuantity": {
                    "value": 600,
                    "unit": "mg"
                }
            }]
        }],
        "dispenseRequest": {
            "quantity": {"value": 20},
            "expectedSupplyDuration": {"value": 5}
        }
    }

    result = await adapter.reverse_adapt(fhir_resource)

    assert result["NR_PRESCRICAO"] == "PRESC-999"
    assert result["DT_PRESCRICAO"] == "2024-02-11T09:00:00"
    assert result["NR_PACIENTE"] == "888999"
    assert result["NR_ATENDIMENTO"] == "ATD-777"
    assert result["CD_ANVISA"] == "1111111111111"
    assert result["CD_ATC"] == "M01AE01"
    assert result["CD_FORMULARIO"] == "MED-IBU-600"
    assert result["NM_MEDICAMENTO"] == "Ibuprofeno 600mg"
    assert result["IE_SITUACAO"] == "A"
    assert result["IE_INTENCAO"] == "order"
    assert result["NR_CRM"] == "CRM/MG 111222"
    assert result["NM_MEDICO"] == "Dra. Maria Santos"
    assert result["DS_POSOLOGIA"] == "1 comprimido a cada 6 horas"
    assert result["NR_FREQUENCIA"] == 4
    assert result["NR_PERIODO"] == 6
    assert result["DS_PERIODO_UNIDADE"] == "h"
    assert result["VIA_ADMINISTRACAO"] == "VO"
    assert result["VL_DOSE"] == 600
    assert result["DS_DOSE_UNIDADE"] == "mg"
    assert result["QT_PRESCRITA"] == 20
    assert result["NR_DIAS_TRATAMENTO"] == 5


@pytest.mark.asyncio
async def test_invalid_input_raises(adapter):
    """Test that missing required fields raise ValueError."""
    tasy_data = {
        "NR_PRESCRICAO": "PRESC-004",
        # Missing required fields: DT_PRESCRICAO, NR_PACIENTE, CD_ANVISA
    }

    with pytest.raises(ValueError) as exc_info:
        await adapter.adapt(tasy_data)

    assert "Missing required fields" in str(exc_info.value)


@pytest.mark.asyncio
async def test_status_mapping(adapter):
    """Test status mapping from Tasy to FHIR."""
    test_cases = [
        ("A", "active"),
        ("S", "on-hold"),
        ("C", "cancelled"),
        ("F", "completed"),
        (None, "active"),  # Default
    ]

    for tasy_status, expected_fhir_status in test_cases:
        tasy_data = {
            "NR_PRESCRICAO": f"PRESC-{tasy_status or 'NULL'}",
            "DT_PRESCRICAO": "2024-02-10T10:00:00",
            "NR_PACIENTE": "123456",
            "CD_ANVISA": "1234567890123",
        }

        if tasy_status is not None:
            tasy_data["IE_SITUACAO"] = tasy_status

        result = await adapter.adapt(tasy_data)
        assert result["status"] == expected_fhir_status


@pytest.mark.asyncio
async def test_route_mapping(adapter):
    """Test route of administration mapping."""
    test_routes = [
        ("VO", "26643006", "Oral route"),
        ("IV", "47625008", "Intravenous route"),
        ("IM", "78421000", "Intramuscular route"),
        ("SC", "34206005", "Subcutaneous route"),
    ]

    for tasy_route, snomed_code, snomed_display in test_routes:
        tasy_data = {
            "NR_PRESCRICAO": f"PRESC-{tasy_route}",
            "DT_PRESCRICAO": "2024-02-10T10:00:00",
            "NR_PACIENTE": "123456",
            "CD_ANVISA": "1234567890123",
            "DS_POSOLOGIA": "Test dosage",
            "VIA_ADMINISTRACAO": tasy_route,
        }

        result = await adapter.adapt(tasy_data)
        dosage = result["dosageInstruction"][0]

        assert dosage["route"]["coding"][0]["system"] == "http://snomed.info/sct"
        assert dosage["route"]["coding"][0]["code"] == snomed_code
        assert dosage["route"]["coding"][0]["display"] == snomed_display
