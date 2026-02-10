"""Tests for TasyScoringAdapter (Wave 4 - GAP-01).

Tests the scoring adapter that converts TASY clinical scores to FHIR RiskAssessment R4.
Covers all 9 score types: EWS, Sepsis, Acuity, Death Risk, Readmission Risk,
Sentry, Sentry Smart Alert, Ventilation Management, and Sepsis Alert.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from healthcare_platform.shared.integrations.tasy_adapters.scoring_adapter import (
    TasyScoringAdapter,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant


@pytest.fixture
def fhir_client_mock():
    """Mock FHIR client for testing."""
    mock = AsyncMock()
    mock.create = AsyncMock()
    mock.search = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def tenant_context():
    """Set up tenant context for tests."""
    tenant = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(tenant)
    return tenant


@pytest.fixture
def scoring_adapter(fhir_client_mock, tenant_context):
    """Create TasyScoringAdapter instance for testing."""
    return TasyScoringAdapter(
        fhir_client=fhir_client_mock,
        tenant_id=tenant_context.tenant_id,
    )


# =============================================================================
# Test EWS (Early Warning Score)
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_ews_valid_data(scoring_adapter):
    """Test EWS adaptation with valid TASY data."""
    tasy_data = {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 5,
        "DS_CLASSIFICACAO": "Medium Risk",
        "IE_RISCO": "M",
        "observations": [
            {
                "CD_OBS": "HR",
                "DS_OBS": "Heart Rate",
                "VL_OBS": "105",
                "UN_MEDIDA": "bpm",
            }
        ],
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["status"] == "final"
    assert result["subject"]["reference"] == "Patient/12345"
    assert result["encounter"]["reference"] == "Encounter/ATD-789"
    assert result["occurrenceDateTime"] == "2024-02-10T14:30:00"
    assert "code" in result
    assert result["code"]["text"] == "Early Warning Score"
    assert len(result["prediction"]) > 0
    assert len(result["basis"]) == 1


@pytest.mark.asyncio
async def test_adapt_ews_missing_required_fields_raises(scoring_adapter):
    """Test EWS adaptation raises ValueError when missing required fields."""
    tasy_data = {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        # Missing DT_SCORE
    }

    with pytest.raises(ValueError, match="required"):
        await scoring_adapter.adapt(tasy_data)


# =============================================================================
# Test Sepsis Score
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_sepsis_valid_data(scoring_adapter):
    """Test Sepsis score adaptation with valid TASY data."""
    tasy_data = {
        "score_type": "sepsis",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 3,
        "DS_CLASSIFICACAO": "High Risk",
        "IE_RISCO": "A",
        "observations": [
            {"CD_OBS": "QSOFA", "DS_OBS": "Quick SOFA", "VL_OBS": "3"}
        ],
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Sepsis Score"
    assert result["prediction"][0]["outcome"]["text"] == "High Risk"


# =============================================================================
# Test Automated Acuity
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_acuity_valid_data(scoring_adapter):
    """Test Automated Acuity adaptation with valid TASY data."""
    tasy_data = {
        "score_type": "acuity",
        "NR_PACIENTE": "12345",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 3,
        "DS_CLASSIFICACAO": "Level 3 - Urgent",
        "IE_RISCO": "M",
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Automated Acuity"
    assert len(result["prediction"]) > 0


# =============================================================================
# Test Risk of Death
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_risk_of_death_valid_data(scoring_adapter):
    """Test Risk of Death adaptation with valid TASY data."""
    tasy_data = {
        "score_type": "risk_of_death",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 25,  # APACHE II score
        "DS_CLASSIFICACAO": "High Risk of Mortality",
        "IE_RISCO": "A",
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Risk of Death"
    assert "probabilityDecimal" in result["prediction"][0]
    assert 0 <= result["prediction"][0]["probabilityDecimal"] <= 1


# =============================================================================
# Test Risk of Readmission
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_risk_of_readmission_valid_data(scoring_adapter):
    """Test Risk of Readmission adaptation with valid TASY data."""
    tasy_data = {
        "score_type": "risk_of_readmission",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 65,  # 65% probability
        "DS_CLASSIFICACAO": "High Risk of Readmission",
        "IE_RISCO": "A",
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Risk of Readmission"
    assert "probabilityDecimal" in result["prediction"][0]


# =============================================================================
# Test Sentry Deterioration Score
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_sentry_valid_data(scoring_adapter):
    """Test Sentry deterioration score adaptation."""
    tasy_data = {
        "score_type": "sentry",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 8,
        "DS_CLASSIFICACAO": "Deteriorating",
        "IE_RISCO": "A",
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Sentry Deterioration Score"


# =============================================================================
# Test Sentry Smart Alert
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_sentry_smart_alert_valid_data(scoring_adapter):
    """Test Sentry Smart Alert adaptation."""
    tasy_data = {
        "score_type": "sentry_smart_alert",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "IE_RISCO": "A",
        "observations": [
            {"CD_OBS": "ALERT", "DS_OBS": "Patient Deterioration Alert"}
        ],
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Sentry Smart Alert"
    assert result["prediction"][0]["outcome"]["text"] == "Patient Deterioration"


# =============================================================================
# Test Ventilation Management
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_vent_management_valid_data(scoring_adapter):
    """Test Ventilation Management score adaptation."""
    tasy_data = {
        "score_type": "vent_management",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 7,
        "DS_CLASSIFICACAO": "Good Compliance",
        "IE_RISCO": "B",
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Ventilation Management"


# =============================================================================
# Test Sepsis Alert
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_sepsis_alert_valid_data(scoring_adapter):
    """Test Sepsis Alert adaptation."""
    tasy_data = {
        "score_type": "sepsis_alert",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "observations": [
            {"CD_OBS": "ALERT", "DS_OBS": "Sepsis Criteria Met"}
        ],
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == "Sepsis Alert"
    assert result["prediction"][0]["qualitativeRisk"]["coding"][0]["code"] == "high"


# =============================================================================
# Test Routing by Score Type
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "score_type,expected_text",
    [
        ("ews", "Early Warning Score"),
        ("sepsis", "Sepsis Score"),
        ("acuity", "Automated Acuity"),
        ("risk_of_death", "Risk of Death"),
        ("risk_of_readmission", "Risk of Readmission"),
        ("sentry", "Sentry Deterioration Score"),
        ("sentry_smart_alert", "Sentry Smart Alert"),
        ("vent_management", "Ventilation Management"),
        ("sepsis_alert", "Sepsis Alert"),
    ],
)
async def test_adapt_routes_by_score_type(
    scoring_adapter, score_type, expected_text
):
    """Test that adapt() routes to correct method based on score_type."""
    tasy_data = {
        "score_type": score_type,
        "NR_PACIENTE": "12345",
        "DT_SCORE": "2024-02-10T14:30:00",
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["code"]["text"] == expected_text


@pytest.mark.asyncio
async def test_adapt_unknown_score_type_raises(scoring_adapter):
    """Test that unknown score_type raises ValueError."""
    tasy_data = {
        "score_type": "unknown_score",
        "NR_PACIENTE": "12345",
        "DT_SCORE": "2024-02-10T14:30:00",
    }

    with pytest.raises(ValueError, match="Unknown score_type"):
        await scoring_adapter.adapt(tasy_data)


# =============================================================================
# Test Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_adapt_without_encounter_reference(scoring_adapter):
    """Test adaptation without encounter reference (encounter field optional)."""
    tasy_data = {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        # No NR_ATENDIMENTO
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 3,
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert "encounter" not in result


@pytest.mark.asyncio
async def test_adapt_without_observations(scoring_adapter):
    """Test adaptation without observations array (optional)."""
    tasy_data = {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        "DT_SCORE": "2024-02-10T14:30:00",
        # No observations
    }

    result = await scoring_adapter.adapt(tasy_data)

    assert result["resourceType"] == "RiskAssessment"
    assert "basis" not in result


@pytest.mark.asyncio
async def test_risk_mapping(scoring_adapter):
    """Test IE_RISCO mapping to FHIR risk codes."""
    test_cases = [
        ("B", "low"),
        ("M", "moderate"),
        ("A", "high"),
    ]

    for ie_risco, expected_risk in test_cases:
        tasy_data = {
            "score_type": "ews",
            "NR_PACIENTE": "12345",
            "DT_SCORE": "2024-02-10T14:30:00",
            "IE_RISCO": ie_risco,
        }

        result = await scoring_adapter.adapt(tasy_data)

        risk_code = result["prediction"][0]["qualitativeRisk"]["coding"][0]["code"]
        assert risk_code == expected_risk


@pytest.mark.asyncio
async def test_adapt_handles_missing_optional_fields(scoring_adapter):
    """Test that adapter handles missing optional fields gracefully."""
    minimal_data = {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        "DT_SCORE": "2024-02-10T14:30:00",
        # Missing: VL_SCORE, DS_CLASSIFICACAO, IE_RISCO, observations
    }

    result = await scoring_adapter.adapt(minimal_data)

    assert result["resourceType"] == "RiskAssessment"
    assert result["subject"]["reference"] == "Patient/12345"
