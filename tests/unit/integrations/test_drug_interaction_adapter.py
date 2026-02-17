"""Unit tests for TasyDrugInteractionAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.drug_interaction_adapter import (
    TasyDrugInteractionAdapter,
)


@pytest.fixture
def fhir_client():
    return MagicMock()


@pytest.fixture
def adapter(fhir_client):
    return TasyDrugInteractionAdapter(fhir_client=fhir_client, tenant_id="test-hospital")


@pytest.mark.asyncio
async def test_adapt_minimal(adapter):
    tasy_data = {
        "NR_INTERACAO": "INT-001",
        "NR_PACIENTE": "123456",
        "IE_TIPO": "DD",
    }
    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "DetectedIssue"
    assert result["status"] == "preliminary"
    assert result["identifier"][0]["value"] == "INT-001"
    assert result["patient"]["reference"] == "Patient/123456"
    assert any(
        c["code"] == "drug-drug" for c in result["code"]["coding"]
    )


@pytest.mark.asyncio
async def test_adapt_complete_with_brazilian_codes(adapter):
    tasy_data = {
        "NR_INTERACAO": "INT-002",
        "NR_PACIENTE": "789012",
        "IE_TIPO": "DD",
        "IE_GRAVIDADE": "A",
        "IE_SITUACAO": "F",
        "CD_MEDICAMENTO_1": "1234567890123",
        "NM_MEDICAMENTO_1": "Warfarina 5mg",
        "NR_PRESCRICAO_1": "PRESC-100",
        "CD_MEDICAMENTO_2": "9876543210987",
        "NM_MEDICAMENTO_2": "Amoxicilina 500mg",
        "NR_PRESCRICAO_2": "PRESC-101",
        "DS_INTERACAO": "Amoxicilina pode aumentar o efeito anticoagulante da Warfarina",
        "DS_MITIGACAO": "Monitorar INR a cada 48h durante uso concomitante",
        "DT_DETECCAO": "2024-02-10T10:30:00",
        "CD_ALERGIA": "ALER-999",
    }
    result = await adapter.adapt(tasy_data)

    assert result["status"] == "final"
    assert result["severity"] == "high"
    assert result["identifiedDateTime"] == "2024-02-10T10:30:00"
    assert result["detail"] == "Amoxicilina pode aumentar o efeito anticoagulante da Warfarina"

    # Implicated medications
    assert len(result["implicated"]) == 2
    assert result["implicated"][0]["reference"] == "MedicationRequest/PRESC-100"
    assert result["implicated"][0]["display"] == "Warfarina 5mg"
    assert result["implicated"][1]["reference"] == "MedicationRequest/PRESC-101"
    assert result["implicated"][1]["display"] == "Amoxicilina 500mg"

    # Mitigation
    assert len(result["mitigation"]) == 1
    assert result["mitigation"][0]["action"]["text"] == "Monitorar INR a cada 48h durante uso concomitante"

    # Allergy cross-reference extension
    assert len(result["extension"]) == 1
    assert result["extension"][0]["url"] == "http://tasy.com/fhir/StructureDefinition/allergy-reference"
    assert result["extension"][0]["valueReference"]["reference"] == "AllergyIntolerance/ALER-999"


@pytest.mark.asyncio
async def test_reverse_adapt(adapter):
    fhir_resource = {
        "resourceType": "DetectedIssue",
        "identifier": [{"system": "http://tasy.com/fhir/identifier/interaction", "value": "INT-999"}],
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "drug-drug",
                    "display": "Drug-drug interaction",
                }
            ]
        },
        "severity": "moderate",
        "patient": {"reference": "Patient/888999"},
        "identifiedDateTime": "2024-02-11T09:00:00",
        "detail": "Interação moderada detectada",
        "implicated": [
            {"reference": "MedicationRequest/PRESC-200", "display": "Medicamento A"},
            {"reference": "MedicationRequest/PRESC-201", "display": "Medicamento B"},
        ],
        "mitigation": [
            {
                "action": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                            "code": "13",
                            "display": "Stopped Concurrent Therapy",
                        }
                    ],
                    "text": "Suspender um dos medicamentos",
                }
            }
        ],
        "extension": [
            {
                "url": "http://tasy.com/fhir/StructureDefinition/allergy-reference",
                "valueReference": {"reference": "AllergyIntolerance/ALER-555"},
            }
        ],
    }
    result = await adapter.reverse_adapt(fhir_resource)

    assert result["NR_INTERACAO"] == "INT-999"
    assert result["IE_SITUACAO"] == "F"
    assert result["IE_TIPO"] == "DD"
    assert result["IE_GRAVIDADE"] == "M"
    assert result["NR_PACIENTE"] == "888999"
    assert result["DT_DETECCAO"] == "2024-02-11T09:00:00"
    assert result["DS_INTERACAO"] == "Interação moderada detectada"
    assert result["NR_PRESCRICAO_1"] == "PRESC-200"
    assert result["NM_MEDICAMENTO_1"] == "Medicamento A"
    assert result["NR_PRESCRICAO_2"] == "PRESC-201"
    assert result["NM_MEDICAMENTO_2"] == "Medicamento B"
    assert result["DS_MITIGACAO"] == "Suspender um dos medicamentos"
    assert result["CD_ALERGIA"] == "ALER-555"


@pytest.mark.asyncio
async def test_severity_mapping(adapter):
    """Test all severity levels and interaction types."""
    # Test severity mapping
    severity_test_cases = [
        ("A", "high"),
        ("M", "moderate"),
        ("B", "low"),
        (None, "moderate"),  # Default
    ]

    for tasy_severity, expected_fhir_severity in severity_test_cases:
        tasy_data = {
            "NR_INTERACAO": f"INT-SEV-{tasy_severity or 'NULL'}",
            "NR_PACIENTE": "123456",
            "IE_TIPO": "DD",
        }

        if tasy_severity is not None:
            tasy_data["IE_GRAVIDADE"] = tasy_severity

        result = await adapter.adapt(tasy_data)

        if tasy_severity is not None:
            assert result["severity"] == expected_fhir_severity
        else:
            assert "severity" not in result

    # Test interaction type mapping
    interaction_type_test_cases = [
        ("DD", "drug-drug", "Drug-drug interaction"),
        ("DA", "drug-allergy", "Drug-allergy interaction"),
        ("DF", "drug-food", "Drug-food interaction"),
        ("DT", "duplicate-therapy", "Duplicate therapy"),
    ]

    for tasy_type, expected_code, expected_display in interaction_type_test_cases:
        tasy_data = {
            "NR_INTERACAO": f"INT-TYPE-{tasy_type}",
            "NR_PACIENTE": "123456",
            "IE_TIPO": tasy_type,
        }

        result = await adapter.adapt(tasy_data)

        assert any(
            c["system"] == "http://terminology.hl7.org/CodeSystem/v3-ActCode"
            and c["code"] == expected_code
            and c["display"] == expected_display
            for c in result["code"]["coding"]
        )
