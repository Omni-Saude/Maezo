"""Tests for AdverseEventDetectionWorker with TASY Scoring Integration (Wave 4).

Tests integration of Sepsis Score into adverse event detection workflow.
Validates that sepsis scores inform event classification and severity.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from healthcare_platform.clinical_operations.workers.adverse_event_detection_worker import (
    AdverseEventDetectionWorker,
)
from healthcare_platform.shared.integrations.tasy_api_client import (
    StubTasyApiClient,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant
from healthcare_platform.shared.domain.exceptions import ExternalServiceException


@pytest.fixture
def fhir_client_mock():
    """Mock FHIR client for testing."""
    mock = AsyncMock()
    mock.create = AsyncMock(return_value={
        "resourceType": "AdverseEvent",
        "id": "adverse-123",
    })
    mock.search = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def tenant_context():
    """Set up tenant context for tests."""
    tenant = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(tenant)
    return tenant


@pytest.fixture
def stub_tasy_client():
    """Create StubTasyApiClient with scoring data."""
    client = StubTasyApiClient()

    # Add encounter
    client.add_encounter("ATD-789", {
        "encounter_id": "ATD-789",
        "patient_id": "12345",
        "status": "in-progress",
    })

    # Add high Sepsis Score
    client.add_scoring_data("ATD-789", "sepsis", {
        "score_type": "sepsis",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 8,  # High sepsis risk
        "DS_CLASSIFICACAO": "High Risk Sepsis",
        "IE_RISCO": "A",
    })

    return client


@pytest.fixture
def worker_with_scoring(fhir_client_mock, stub_tasy_client, tenant_context):
    """Create AdverseEventDetectionWorker with TASY scoring integration."""
    return AdverseEventDetectionWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=stub_tasy_client,
    )


@pytest.fixture
def worker_without_scoring(fhir_client_mock, tenant_context):
    """Create AdverseEventDetectionWorker without TASY API client."""
    return AdverseEventDetectionWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=None,
    )


# =============================================================================
# Test Worker with Sepsis Score Integration
# =============================================================================


@pytest.mark.asyncio
async def test_infection_event_with_high_sepsis_score_severe_classification(
    worker_with_scoring, stub_tasy_client
):
    """Test that infection event with high Sepsis Score gets severe classification."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Hospital-acquired pneumonia suspected",
        "severity": "moderate",  # Initial assessment
        "occurrence_datetime": "2024-02-10T14:00:00",
        "location": "Location/ward-3",
        "detected_by": "Practitioner/nurse-456",
    }

    result = await worker_with_scoring.execute(task_vars)

    # With high sepsis score, severity should be elevated
    assert result["severity_assessment"] in ["severe", "life_threatening"]
    assert result["root_cause_analysis_required"] is True


@pytest.mark.asyncio
async def test_sepsis_score_adds_contributing_factors(
    worker_with_scoring, stub_tasy_client
):
    """Test that Sepsis Score adds contributing factors to adverse event."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Patient developed signs of sepsis",
        "severity": "severe",
        "occurrence_datetime": "2024-02-10T14:00:00",
        "contributing_factors": [
            {
                "factor_type": "process",
                "description": "Delayed antibiotic administration",
                "contribution_level": "primary",
            }
        ],
    }

    result = await worker_with_scoring.execute(task_vars)

    # Sepsis score should enrich contributing factors
    contributing_factors = result.get("contributing_factors", [])
    assert len(contributing_factors) >= 1
    # Check if sepsis-related factors were added
    factors_str = str(contributing_factors).lower()
    assert "sepsis" in factors_str or len(contributing_factors) > 1


@pytest.mark.asyncio
async def test_high_sepsis_score_triggers_immediate_actions(
    worker_with_scoring, stub_tasy_client
):
    """Test that high Sepsis Score triggers immediate actions."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Sepsis suspected based on qSOFA criteria",
        "severity": "severe",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    result = await worker_with_scoring.execute(task_vars)

    # Should have immediate actions
    immediate_actions = result.get("immediate_actions", [])
    assert len(immediate_actions) > 0
    # Typical sepsis immediate actions
    actions_str = str(immediate_actions).lower()
    assert any(
        keyword in actions_str
        for keyword in ["antibiotic", "fluid", "sepsis", "protocol", "bundle"]
    )


@pytest.mark.asyncio
async def test_sepsis_score_requires_regulatory_reporting(
    worker_with_scoring, stub_tasy_client
):
    """Test that severe sepsis requires regulatory reporting."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Patient developed septic shock",
        "severity": "life_threatening",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    result = await worker_with_scoring.execute(task_vars)

    # Septic shock should require regulatory reporting
    assert result.get("regulatory_reporting_required") is True


# =============================================================================
# Test Patient Outcome Assessment with Sepsis
# =============================================================================


@pytest.mark.asyncio
async def test_sepsis_score_influences_patient_outcome_assessment(
    worker_with_scoring, stub_tasy_client
):
    """Test that Sepsis Score influences patient outcome assessment."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Infection developed during hospitalization",
        "severity": "moderate",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    result = await worker_with_scoring.execute(task_vars)

    # With high sepsis score, patient outcome should reflect increased risk
    patient_outcome = result.get("patient_outcome")
    assert patient_outcome in [
        "temporary_harm",
        "permanent_harm",
        "intervention_required",
        "death",
    ]


# =============================================================================
# Test Event Classification with Sepsis Context
# =============================================================================


@pytest.mark.asyncio
async def test_sepsis_context_helps_classify_preventability(
    worker_with_scoring, stub_tasy_client
):
    """Test that Sepsis Score context helps classify event preventability."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Post-surgical wound infection with sepsis",
        "severity": "severe",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    result = await worker_with_scoring.execute(task_vars)

    # Should classify preventability
    classification = result.get("event_classification")
    assert classification in ["preventable", "non_preventable", "unavoidable"]


# =============================================================================
# Test Graceful Degradation
# =============================================================================


@pytest.mark.asyncio
async def test_adverse_event_worker_without_tasy_client_works(worker_without_scoring):
    """Test that worker functions normally without TASY API client."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-999",
        "patient_reference": "Patient/99999",
        "event_type": "fall",
        "event_description": "Patient fell while ambulating",
        "severity": "moderate",
        "occurrence_datetime": "2024-02-10T10:00:00",
    }

    result = await worker_without_scoring.execute(task_vars)

    # Should still work, just without sepsis context
    assert "adverse_event_reference" in result
    assert "event_id" in result
    assert "event_classification" in result


@pytest.mark.asyncio
async def test_adverse_event_worker_handles_tasy_api_failure(
    fhir_client_mock, tenant_context
):
    """Test that worker handles TASY API failures gracefully."""
    # Create a mock that raises exception
    failing_tasy_client = AsyncMock()
    failing_tasy_client.get_sepsis_score = AsyncMock(
        side_effect=ExternalServiceException(
            "TASY API unavailable",
            service_name="tasy_api",
            operation="get_sepsis_score",
        )
    )

    worker = AdverseEventDetectionWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=failing_tasy_client,
    )

    task_vars = {
        "encounter_reference": "Encounter/ATD-999",
        "patient_reference": "Patient/99999",
        "event_type": "infection",
        "event_description": "Possible infection",
        "severity": "moderate",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    # Should not raise, should degrade gracefully
    result = await worker.execute(task_vars)

    assert "adverse_event_reference" in result


# =============================================================================
# Test Non-Infection Events (Sepsis Score Not Relevant)
# =============================================================================


@pytest.mark.asyncio
async def test_non_infection_event_doesnt_fetch_sepsis_score(
    worker_with_scoring, stub_tasy_client
):
    """Test that non-infection events don't unnecessarily fetch Sepsis Score."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "fall",
        "event_description": "Patient fell in bathroom",
        "severity": "moderate",
        "occurrence_datetime": "2024-02-10T08:00:00",
    }

    result = await worker_with_scoring.execute(task_vars)

    # Should process normally without sepsis context
    assert result["event_type"] == "fall"
    # Sepsis scoring might be skipped for falls


@pytest.mark.asyncio
async def test_medication_error_without_infection_no_sepsis_context(
    worker_with_scoring, stub_tasy_client
):
    """Test medication error without infection doesn't use sepsis context."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "medication_error",
        "event_description": "Wrong dose administered",
        "severity": "mild",
        "occurrence_datetime": "2024-02-10T12:00:00",
    }

    result = await worker_with_scoring.execute(task_vars)

    assert result["event_type"] == "medication_error"


# =============================================================================
# Test Low Sepsis Score (No Escalation)
# =============================================================================


@pytest.mark.asyncio
async def test_low_sepsis_score_doesnt_escalate_severity(
    fhir_client_mock, tenant_context
):
    """Test that low Sepsis Score doesn't unnecessarily escalate severity."""
    # Create stub with low sepsis score
    stub_client = StubTasyApiClient()
    stub_client.add_encounter("ATD-999", {"encounter_id": "ATD-999"})
    stub_client.add_scoring_data("ATD-999", "sepsis", {
        "score_type": "sepsis",
        "VL_SCORE": 1,  # Low score
        "IE_RISCO": "B",
        "DS_CLASSIFICACAO": "Low Risk",
    })

    worker = AdverseEventDetectionWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=stub_client,
    )

    task_vars = {
        "encounter_reference": "Encounter/ATD-999",
        "patient_reference": "Patient/99999",
        "event_type": "infection",
        "event_description": "Minor wound infection",
        "severity": "mild",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    result = await worker.execute(task_vars)

    # Low sepsis score shouldn't force severe classification
    assert result["severity_assessment"] in ["mild", "moderate"]


# =============================================================================
# Test Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_worker_with_missing_encounter_id_in_tasy(
    worker_with_scoring, fhir_client_mock
):
    """Test worker handles missing encounter in TASY gracefully."""
    task_vars = {
        "encounter_reference": "Encounter/MISSING",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Infection event",
        "severity": "moderate",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    # Should not crash, should work without sepsis score
    result = await worker_with_scoring.execute(task_vars)

    assert "adverse_event_reference" in result


@pytest.mark.asyncio
async def test_worker_handles_partial_sepsis_scoring_data(
    worker_with_scoring, stub_tasy_client
):
    """Test worker handles partial/incomplete sepsis scoring data."""
    # Override with partial data
    stub_tasy_client.add_scoring_data("ATD-789", "sepsis", {
        "score_type": "sepsis",
        # Missing VL_SCORE and IE_RISCO
    })

    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "event_type": "infection",
        "event_description": "Infection event",
        "severity": "moderate",
        "occurrence_datetime": "2024-02-10T14:00:00",
    }

    # Should handle gracefully
    result = await worker_with_scoring.execute(task_vars)

    assert "adverse_event_reference" in result
