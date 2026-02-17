"""Unit tests for TasyObservationAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.observation_adapter import (
    TasyObservationAdapter,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client fixture."""
    return MagicMock()


@pytest.fixture
def adapter(fhir_client):
    """TasyObservationAdapter fixture."""
    return TasyObservationAdapter(
        fhir_client=fhir_client,
        tenant_id="test-hospital",
    )


@pytest.mark.asyncio
async def test_adapt_minimal_input(adapter):
    """Test adaptation with minimal required fields (heart rate vital sign)."""
    tasy_data = {
        "NR_OBSERVACAO": "OBS-123",
        "DT_REGISTRO": "2024-02-10T14:30:00",
        "NR_PACIENTE": "PAT-456",
        "TP_RESULTADO": "HR",
    }

    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "Observation"
    assert result["status"] == "final"
    assert result["identifier"][0]["value"] == "OBS-123"
    assert result["subject"]["reference"] == "Patient/PAT-456"
    assert result["effectiveDateTime"] == "2024-02-10T14:30:00"
    assert result["code"]["coding"][0]["system"] == "http://loinc.org"
    assert result["code"]["coding"][0]["code"] == "8867-4"  # Heart rate LOINC
    assert result["code"]["coding"][0]["display"] == "Heart rate"
    assert result["category"][0]["coding"][0]["code"] == "laboratory"  # Default category


@pytest.mark.asyncio
async def test_adapt_complete_input(adapter):
    """Test adaptation with all fields including interpretation and reference range."""
    tasy_data = {
        "NR_OBSERVACAO": "OBS-789",
        "DT_REGISTRO": "2024-02-10T08:15:00",
        "NR_PACIENTE": "PAT-123",
        "NR_ATENDIMENTO": "ENC-456",
        "TP_CATEGORIA": "laboratory",
        "TP_RESULTADO": "GLUCOSE",
        "VL_RESULTADO": 95.0,
        "DS_UNIDADE": "mg/dL",
        "IE_STATUS": "F",
        "IE_INTERPRETACAO": "N",
        "VL_REF_MIN": 70.0,
        "VL_REF_MAX": 100.0,
        "CD_PROFISSIONAL": "LAB-456",
        "NM_PROFISSIONAL": "Dr. João Silva",
    }

    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "Observation"
    assert result["status"] == "final"
    assert result["identifier"][0]["value"] == "OBS-789"
    assert result["subject"]["reference"] == "Patient/PAT-123"
    assert result["encounter"]["reference"] == "Encounter/ENC-456"
    assert result["effectiveDateTime"] == "2024-02-10T08:15:00"

    # Check LOINC code for glucose
    assert result["code"]["coding"][0]["system"] == "http://loinc.org"
    assert result["code"]["coding"][0]["code"] == "2345-7"
    assert "Glucose" in result["code"]["coding"][0]["display"]

    # Check category
    assert result["category"][0]["coding"][0]["code"] == "laboratory"

    # Check value
    assert result["valueQuantity"]["value"] == 95.0
    assert result["valueQuantity"]["unit"] == "mg/dL"
    assert result["valueQuantity"]["system"] == "http://unitsofmeasure.org"

    # Check interpretation
    assert result["interpretation"][0]["coding"][0]["code"] == "N"
    assert result["interpretation"][0]["coding"][0]["display"] == "Normal"

    # Check reference range
    assert result["referenceRange"][0]["low"]["value"] == 70.0
    assert result["referenceRange"][0]["high"]["value"] == 100.0

    # Check performer
    assert result["performer"][0]["type"] == "Practitioner"
    assert result["performer"][0]["display"] == "Dr. João Silva"
    assert result["performer"][0]["identifier"]["value"] == "LAB-456"

    # Check tenant tag
    assert result["meta"]["tag"][0]["code"] == "test-hospital"


@pytest.mark.asyncio
async def test_adapt_with_brazilian_codes(adapter):
    """Test adaptation verifies LOINC codes for vital signs and lab results."""
    # Test vital signs LOINC codes
    vital_tests = [
        ("HR", "8867-4"),  # Heart rate
        ("BP_SYS", "8480-6"),  # Systolic BP
        ("BP_DIA", "8462-4"),  # Diastolic BP
        ("TEMP", "8310-5"),  # Temperature
        ("SPO2", "2708-6"),  # Oxygen saturation
        ("RR", "9279-1"),  # Respiratory rate
        ("PAIN", "72514-3"),  # Pain severity
    ]

    for tp_resultado, expected_loinc in vital_tests:
        tasy_data = {
            "NR_OBSERVACAO": f"OBS-{tp_resultado}",
            "DT_REGISTRO": "2024-02-10T14:30:00",
            "NR_PACIENTE": "PAT-456",
            "TP_RESULTADO": tp_resultado,
        }
        result = await adapter.adapt(tasy_data)
        assert result["code"]["coding"][0]["code"] == expected_loinc, f"Failed for {tp_resultado}"

    # Test lab results LOINC codes
    lab_tests = [
        ("GLUCOSE", "2345-7"),
        ("CREATININE", "2160-0"),
        ("HEMOGLOBIN", "718-7"),
        ("PLATELETS", "777-3"),
        ("WBC", "6690-2"),
        ("POTASSIUM", "2823-3"),
        ("SODIUM", "2951-2"),
    ]

    for tp_resultado, expected_loinc in lab_tests:
        tasy_data = {
            "NR_OBSERVACAO": f"OBS-{tp_resultado}",
            "DT_REGISTRO": "2024-02-10T08:00:00",
            "NR_PACIENTE": "PAT-789",
            "TP_RESULTADO": tp_resultado,
        }
        result = await adapter.adapt(tasy_data)
        assert result["code"]["coding"][0]["code"] == expected_loinc, f"Failed for {tp_resultado}"


@pytest.mark.asyncio
async def test_critical_value_flagging(adapter):
    """Test that critical values are properly flagged in meta.tag."""
    tasy_data = {
        "NR_OBSERVACAO": "OBS-CRITICAL-123",
        "DT_REGISTRO": "2024-02-10T08:15:00",
        "NR_PACIENTE": "PAT-999",
        "TP_CATEGORIA": "laboratory",
        "TP_RESULTADO": "POTASSIUM",
        "VL_RESULTADO": 7.5,  # Critical high potassium
        "DS_UNIDADE": "mmol/L",
        "IE_STATUS": "F",
        "IE_INTERPRETACAO": "C",  # Critical
    }

    result = await adapter.adapt(tasy_data)

    # Check interpretation is critical
    assert result["interpretation"][0]["coding"][0]["code"] == "HH"  # Critical high

    # Check critical flag in meta.tag
    tags = result["meta"]["tag"]
    critical_tag = next((tag for tag in tags if tag.get("code") == "critical"), None)
    assert critical_tag is not None
    assert critical_tag["system"] == "http://tasy.com/fhir/critical-value"
    assert critical_tag["display"] == "Critical Value"


@pytest.mark.asyncio
async def test_blood_pressure_panel(adapter):
    """Test blood pressure panel observation with systolic and diastolic components."""
    tasy_data = {
        "NR_OBSERVACAO": "OBS-BP-123",
        "DT_REGISTRO": "2024-02-10T14:30:00",
        "NR_PACIENTE": "PAT-456",
        "TP_CATEGORIA": "vital-signs",
        "TP_SINAL": "BP",  # Blood pressure panel
        "VL_SISTOLICA": 120,
        "VL_DIASTOLICA": 80,
        "IE_STATUS": "F",
        "CD_PROFISSIONAL": "ENF-123",
        "NM_PROFISSIONAL": "Enf. Maria Santos",
    }

    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "Observation"
    assert result["code"]["coding"][0]["code"] == "85354-9"  # Blood pressure panel LOINC
    assert result["category"][0]["coding"][0]["code"] == "vital-signs"

    # Check components
    assert "component" in result
    assert len(result["component"]) == 2

    # Check systolic component
    systolic = result["component"][0]
    assert systolic["code"]["coding"][0]["code"] == "8480-6"
    assert systolic["valueQuantity"]["value"] == 120
    assert systolic["valueQuantity"]["unit"] == "mm[Hg]"

    # Check diastolic component
    diastolic = result["component"][1]
    assert diastolic["code"]["coding"][0]["code"] == "8462-4"
    assert diastolic["valueQuantity"]["value"] == 80
    assert diastolic["valueQuantity"]["unit"] == "mm[Hg]"


@pytest.mark.asyncio
async def test_invalid_input_raises(adapter):
    """Test that missing required fields raise ValueError."""
    # Missing NR_OBSERVACAO
    tasy_data_missing_id = {
        "DT_REGISTRO": "2024-02-10T14:30:00",
        "NR_PACIENTE": "PAT-456",
    }

    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt(tasy_data_missing_id)

    # Missing DT_REGISTRO
    tasy_data_missing_date = {
        "NR_OBSERVACAO": "OBS-123",
        "NR_PACIENTE": "PAT-456",
    }

    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt(tasy_data_missing_date)

    # Missing NR_PACIENTE
    tasy_data_missing_patient = {
        "NR_OBSERVACAO": "OBS-123",
        "DT_REGISTRO": "2024-02-10T14:30:00",
    }

    with pytest.raises(ValueError, match="Missing required fields"):
        await adapter.adapt(tasy_data_missing_patient)
