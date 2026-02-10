"""Tests for TASY API Client Scoring Protocol (Wave 4 - GAP-01).

Tests that StubTasyApiClient properly implements all 9 scoring methods
and provides valid mock data for integration testing.
"""
from __future__ import annotations

import pytest
from datetime import datetime

from healthcare_platform.shared.integrations.tasy_api_client import (
    StubTasyApiClient,
)


@pytest.fixture
def stub_client():
    """Create StubTasyApiClient instance for testing."""
    return StubTasyApiClient()


@pytest.fixture
def stub_client_with_data(stub_client):
    """Create StubTasyApiClient with pre-populated scoring data."""
    # Add encounter for testing
    stub_client.add_encounter(
        "ATD-789",
        {
            "encounter_id": "ATD-789",
            "patient_id": "12345",
            "status": "in-progress",
        },
    )

    # Add scoring data
    stub_client.add_scoring_data("ATD-789", "ews", {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 5,
        "DS_CLASSIFICACAO": "Medium Risk",
        "IE_RISCO": "M",
    })

    stub_client.add_scoring_data("ATD-789", "sepsis", {
        "score_type": "sepsis",
        "VL_SCORE": 3,
        "DS_CLASSIFICACAO": "High Risk",
        "IE_RISCO": "A",
    })

    return stub_client


# =============================================================================
# Test Early Warning Score (EWS)
# =============================================================================


@pytest.mark.asyncio
async def test_get_early_warning_score_returns_valid_data(stub_client_with_data):
    """Test get_early_warning_score returns valid EWS data."""
    result = await stub_client_with_data.get_early_warning_score("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "ews"
    assert "VL_SCORE" in result
    assert "DS_CLASSIFICACAO" in result
    assert "IE_RISCO" in result
    assert result["NR_ATENDIMENTO"] == "ATD-789"


@pytest.mark.asyncio
async def test_get_early_warning_score_not_found_raises(stub_client):
    """Test get_early_warning_score raises for non-existent encounter."""
    from healthcare_platform.shared.domain.exceptions import ExternalServiceException

    with pytest.raises(ExternalServiceException) as exc_info:
        await stub_client.get_early_warning_score("NONEXISTENT")

    assert exc_info.value.status_code == 404


# =============================================================================
# Test Sepsis Score
# =============================================================================


@pytest.mark.asyncio
async def test_get_sepsis_score_returns_valid_data(stub_client_with_data):
    """Test get_sepsis_score returns valid sepsis score data."""
    result = await stub_client_with_data.get_sepsis_score("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "sepsis"
    assert "VL_SCORE" in result
    assert isinstance(result["VL_SCORE"], (int, float))


@pytest.mark.asyncio
async def test_get_sepsis_score_not_found_raises(stub_client):
    """Test get_sepsis_score raises for non-existent encounter."""
    from healthcare_platform.shared.domain.exceptions import ExternalServiceException

    with pytest.raises(ExternalServiceException) as exc_info:
        await stub_client.get_sepsis_score("NONEXISTENT")

    assert exc_info.value.status_code == 404


# =============================================================================
# Test Sentry Score
# =============================================================================


@pytest.mark.asyncio
async def test_get_sentry_score_returns_valid_data(stub_client_with_data):
    """Test get_sentry_score returns valid Sentry score data."""
    result = await stub_client_with_data.get_sentry_score("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "sentry"


# =============================================================================
# Test Sentry Smart Alert
# =============================================================================


@pytest.mark.asyncio
async def test_get_sentry_smart_alert_returns_valid_data(stub_client_with_data):
    """Test get_sentry_smart_alert returns valid alert data."""
    result = await stub_client_with_data.get_sentry_smart_alert("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "sentry_smart_alert"
    assert "alert_active" in result
    assert isinstance(result["alert_active"], bool)


# =============================================================================
# Test Risk of Death Score
# =============================================================================


@pytest.mark.asyncio
async def test_get_risk_of_death_score_returns_valid_data(stub_client_with_data):
    """Test get_risk_of_death_score returns valid data."""
    result = await stub_client_with_data.get_risk_of_death_score("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "risk_of_death"
    assert "VL_SCORE" in result


# =============================================================================
# Test Risk of Readmission Score
# =============================================================================


@pytest.mark.asyncio
async def test_get_risk_of_readmission_score_returns_valid_data(stub_client_with_data):
    """Test get_risk_of_readmission_score returns valid data."""
    result = await stub_client_with_data.get_risk_of_readmission_score("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "risk_of_readmission"


# =============================================================================
# Test Automated Acuity
# =============================================================================


@pytest.mark.asyncio
async def test_get_automated_acuity_returns_valid_data(stub_client_with_data):
    """Test get_automated_acuity returns valid acuity data."""
    result = await stub_client_with_data.get_automated_acuity("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "acuity"


# =============================================================================
# Test Ventilator Management Score
# =============================================================================


@pytest.mark.asyncio
async def test_get_vent_management_score_returns_valid_data(stub_client_with_data):
    """Test get_vent_management_score returns valid data."""
    result = await stub_client_with_data.get_vent_management_score("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "vent_management"


# =============================================================================
# Test Sepsis Alert
# =============================================================================


@pytest.mark.asyncio
async def test_get_sepsis_alert_returns_valid_data(stub_client_with_data):
    """Test get_sepsis_alert returns valid alert data."""
    result = await stub_client_with_data.get_sepsis_alert("ATD-789")

    assert "score_type" in result
    assert result["score_type"] == "sepsis_alert"
    assert "alert_active" in result


# =============================================================================
# Test All Scoring Methods Protocol Compliance
# =============================================================================


@pytest.mark.asyncio
async def test_all_scoring_methods_exist(stub_client):
    """Test that StubTasyApiClient implements all 9 scoring methods."""
    required_methods = [
        "get_early_warning_score",
        "get_sepsis_score",
        "get_sentry_score",
        "get_sentry_smart_alert",
        "get_risk_of_death_score",
        "get_risk_of_readmission_score",
        "get_automated_acuity",
        "get_vent_management_score",
        "get_sepsis_alert",
    ]

    for method_name in required_methods:
        assert hasattr(stub_client, method_name), f"Missing method: {method_name}"
        method = getattr(stub_client, method_name)
        assert callable(method), f"Method not callable: {method_name}"


# =============================================================================
# Test Helper Method: add_scoring_data
# =============================================================================


@pytest.mark.asyncio
async def test_add_scoring_data_helper(stub_client):
    """Test add_scoring_data helper method for populating stub data."""
    stub_client.add_scoring_data("ATD-123", "ews", {
        "score_type": "ews",
        "VL_SCORE": 7,
        "IE_RISCO": "A",
    })

    result = await stub_client.get_early_warning_score("ATD-123")

    assert result["VL_SCORE"] == 7
    assert result["IE_RISCO"] == "A"


@pytest.mark.asyncio
async def test_add_scoring_data_multiple_score_types(stub_client):
    """Test adding multiple score types for same encounter."""
    encounter_id = "ATD-456"

    stub_client.add_scoring_data(encounter_id, "ews", {"VL_SCORE": 5})
    stub_client.add_scoring_data(encounter_id, "sepsis", {"VL_SCORE": 3})

    ews_result = await stub_client.get_early_warning_score(encounter_id)
    sepsis_result = await stub_client.get_sepsis_score(encounter_id)

    assert ews_result["VL_SCORE"] == 5
    assert sepsis_result["VL_SCORE"] == 3


# =============================================================================
# Test Response Structure
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,score_type",
    [
        ("get_early_warning_score", "ews"),
        ("get_sepsis_score", "sepsis"),
        ("get_sentry_score", "sentry"),
        ("get_risk_of_death_score", "risk_of_death"),
        ("get_risk_of_readmission_score", "risk_of_readmission"),
        ("get_automated_acuity", "acuity"),
        ("get_vent_management_score", "vent_management"),
    ],
)
async def test_scoring_response_structure(stub_client, method_name, score_type):
    """Test that all scoring methods return expected structure."""
    encounter_id = "ATD-TEST"
    stub_client.add_scoring_data(encounter_id, score_type, {
        "score_type": score_type,
        "VL_SCORE": 5,
    })

    method = getattr(stub_client, method_name)
    result = await method(encounter_id)

    assert isinstance(result, dict)
    assert result["score_type"] == score_type


# =============================================================================
# Test Default Mock Data
# =============================================================================


@pytest.mark.asyncio
async def test_stub_returns_default_data_when_no_custom_data(stub_client):
    """Test that stub returns sensible defaults when no custom data added."""
    # Even without adding data, stub should return defaults for existing encounter
    stub_client.add_encounter("ATD-DEFAULT", {"encounter_id": "ATD-DEFAULT"})

    result = await stub_client.get_early_warning_score("ATD-DEFAULT")

    assert "score_type" in result
    assert result["score_type"] == "ews"
    assert "VL_SCORE" in result
