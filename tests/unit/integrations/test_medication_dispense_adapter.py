"""Unit tests for TasyMedicationDispenseAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.medication_dispense_adapter import (
    TasyMedicationDispenseAdapter,
)


@pytest.fixture
def fhir_client():
    return MagicMock()


@pytest.fixture
def adapter(fhir_client):
    return TasyMedicationDispenseAdapter(fhir_client=fhir_client, tenant_id="test-hospital")


@pytest.mark.asyncio
async def test_adapt_minimal(adapter):
    tasy_data = {
        "NR_DISPENSACAO": "DISP-001",
        "NR_PACIENTE": "123456",
        "CD_ANVISA": "1234567890123",
    }
    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "MedicationDispense"
    assert result["status"] == "preparation"
    assert result["identifier"][0]["value"] == "DISP-001"
    assert result["subject"]["reference"] == "Patient/123456"
    assert any(
        c["system"] == "http://www.anvisa.gov.br/medicamentos" and c["code"] == "1234567890123"
        for c in result["medicationCodeableConcept"]["coding"]
    )


@pytest.mark.asyncio
async def test_adapt_complete_with_brazilian_codes(adapter):
    tasy_data = {
        "NR_DISPENSACAO": "DISP-002",
        "NR_PRESCRICAO": "PRESC-123",
        "NR_PACIENTE": "789012",
        "NR_ATENDIMENTO": "ATD-456",
        "NR_CRF": "CRF/SP 12345",
        "NM_FARMACEUTICO": "Dr. Ana Souza",
        "CD_ANVISA": "1234567890123",
        "CD_DCB": "00220",
        "CD_FORMULARIO": "MED-AMO-500",
        "NM_MEDICAMENTO": "Amoxicilina 500mg",
        "QT_DISPENSADA": 21,
        "DS_UNIDADE": "comprimido",
        "NR_DIAS_FORNECIMENTO": 7,
        "DT_PREPARACAO": "2024-02-10T14:00:00",
        "DT_ENTREGA": "2024-02-10T14:30:00",
        "IE_SITUACAO": "C",
        "DS_POSOLOGIA": "1 comprimido a cada 8 horas",
    }
    result = await adapter.adapt(tasy_data)

    assert result["status"] == "completed"
    assert result["context"]["reference"] == "Encounter/ATD-456"
    assert result["authorizingPrescription"][0]["reference"] == "MedicationRequest/PRESC-123"
    assert result["quantity"]["value"] == 21
    assert result["daysSupply"]["value"] == 7
    assert result["whenPrepared"] == "2024-02-10T14:00:00"
    assert result["whenHandedOver"] == "2024-02-10T14:30:00"

    # CRF pharmacist
    performer_actor = result["performer"][0]["actor"]
    assert performer_actor["identifier"]["system"] == "http://www.cff.org.br/pharmacist"
    assert performer_actor["identifier"]["value"] == "CRF/SP 12345"

    # Brazilian codes
    codings = result["medicationCodeableConcept"]["coding"]
    assert any(c["system"] == "http://www.anvisa.gov.br/medicamentos" for c in codings)
    assert any(c["system"] == "http://www.anvisa.gov.br/dcb" and c["code"] == "00220" for c in codings)


@pytest.mark.asyncio
async def test_reverse_adapt(adapter):
    fhir_resource = {
        "resourceType": "MedicationDispense",
        "identifier": [{"system": "http://tasy.com/fhir/identifier/dispensacao", "value": "DISP-999"}],
        "status": "completed",
        "medicationCodeableConcept": {
            "coding": [
                {"system": "http://www.anvisa.gov.br/medicamentos", "code": "1111111111111", "display": "Ibuprofeno 600mg"},
                {"system": "http://www.anvisa.gov.br/dcb", "code": "00550"},
            ]
        },
        "subject": {"reference": "Patient/888999"},
        "context": {"reference": "Encounter/ATD-777"},
        "authorizingPrescription": [{"reference": "MedicationRequest/PRESC-555"}],
        "quantity": {"value": 20, "unit": "comprimido"},
        "daysSupply": {"value": 5},
        "whenPrepared": "2024-02-11T09:00:00",
        "whenHandedOver": "2024-02-11T09:15:00",
        "substitution": {"wasSubstituted": True, "reason": [{"text": "Genérico disponível"}]},
    }
    result = await adapter.reverse_adapt(fhir_resource)

    assert result["NR_DISPENSACAO"] == "DISP-999"
    assert result["NR_PACIENTE"] == "888999"
    assert result["NR_ATENDIMENTO"] == "ATD-777"
    assert result["NR_PRESCRICAO"] == "PRESC-555"
    assert result["CD_ANVISA"] == "1111111111111"
    assert result["CD_DCB"] == "00550"
    assert result["QT_DISPENSADA"] == 20
    assert result["NR_DIAS_FORNECIMENTO"] == 5
    assert result["IE_SUBSTITUICAO"] is True
    assert result["DS_MOTIVO_SUBSTITUICAO"] == "Genérico disponível"


@pytest.mark.asyncio
async def test_substitution_handling(adapter):
    tasy_data = {
        "NR_DISPENSACAO": "DISP-SUB",
        "NR_PACIENTE": "123456",
        "CD_ANVISA": "1234567890123",
        "IE_SUBSTITUICAO": True,
        "CD_ANVISA_ORIGINAL": "9876543210987",
        "DS_MOTIVO_SUBSTITUICAO": "Genérico conforme Lei 9.787/1999",
    }
    result = await adapter.adapt(tasy_data)

    assert result["substitution"]["wasSubstituted"] is True
    assert result["substitution"]["reason"][0]["text"] == "Genérico conforme Lei 9.787/1999"
    assert "responsibleParty" in result["substitution"]

    # No substitution
    tasy_data_no_sub = {
        "NR_DISPENSACAO": "DISP-NOSUB",
        "NR_PACIENTE": "123456",
        "CD_ANVISA": "1234567890123",
        "IE_SUBSTITUICAO": False,
    }
    result2 = await adapter.adapt(tasy_data_no_sub)
    assert result2["substitution"]["wasSubstituted"] is False
