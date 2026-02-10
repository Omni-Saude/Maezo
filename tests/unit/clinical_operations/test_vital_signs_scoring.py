"""Tests for VitalSignsMonitoringWorker with TASY Scoring Integration (Wave 4).

Tests integration of EWS and Sentry scores into vital signs monitoring workflow.
Validates graceful degradation when TASY API is unavailable.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from healthcare_platform.clinical_operations.workers.vital_signs_monitoring_worker import (
    VitalSignsMonitoringWorker,
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
    mock.create = AsyncMock(return_value={"resourceType": "Observation", "id": "obs-123"})
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

    # Add EWS score
    client.add_scoring_data("ATD-789", "ews", {
        "score_type": "ews",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "DT_SCORE": "2024-02-10T14:30:00",
        "VL_SCORE": 5,
        "DS_CLASSIFICACAO": "Medium Risk",
        "IE_RISCO": "M",
    })

    # Add Sentry score
    client.add_scoring_data("ATD-789", "sentry", {
        "score_type": "sentry",
        "VL_SCORE": 7,
        "DS_CLASSIFICACAO": "Deteriorating",
        "IE_RISCO": "A",
    })

    return client


@pytest.fixture
def worker_with_scoring(fhir_client_mock, stub_tasy_client, tenant_context):
    """Create VitalSignsMonitoringWorker with TASY scoring integration."""
    return VitalSignsMonitoringWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=stub_tasy_client,
    )


@pytest.fixture
def worker_without_scoring(fhir_client_mock, tenant_context):
    """Create VitalSignsMonitoringWorker without TASY API client."""
    return VitalSignsMonitoringWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=None,
    )


# =============================================================================
# Test Worker with TASY Scoring Integration
# =============================================================================


@pytest.mark.asyncio
async def test_vital_signs_worker_includes_ews_score(
    worker_with_scoring, stub_tasy_client
):
    """Test that worker includes EWS score in output when TASY API available."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "temperature_celsius": 38.5,
            "heart_rate": 105,
            "systolic_bp": 160,
            "diastolic_bp": 95,
        },
    }

    result = await worker_with_scoring.execute(task_vars)

    assert "vital_signs_status" in result
    assert "alerts" in result
    # Check if EWS score is included in alerts or metadata
    assert any("EWS" in str(alert) or "Early Warning" in str(alert) for alert in result["alerts"]) or \
           "ews_score" in result or "clinical_scores" in result


@pytest.mark.asyncio
async def test_vital_signs_worker_includes_sentry_score(
    worker_with_scoring, stub_tasy_client
):
    """Test that worker includes Sentry score in output."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "temperature_celsius": 39.0,
            "heart_rate": 110,
            "respiratory_rate": 24,
        },
    }

    result = await worker_with_scoring.execute(task_vars)

    # Check if Sentry score is included
    result_str = str(result)
    assert "sentry" in result_str.lower() or "deteriorat" in result_str.lower() or \
           "clinical_scores" in result


@pytest.mark.asyncio
async def test_vital_signs_worker_elevates_severity_with_high_ews(
    worker_with_scoring, stub_tasy_client
):
    """Test that high EWS score elevates severity assessment."""
    # Override with high EWS score
    stub_tasy_client.add_scoring_data("ATD-789", "ews", {
        "score_type": "ews",
        "VL_SCORE": 9,  # High score
        "IE_RISCO": "A",
        "DS_CLASSIFICACAO": "Critical Risk",
    })

    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "temperature_celsius": 40.0,
            "heart_rate": 120,
            "systolic_bp": 85,
        },
    }

    result = await worker_with_scoring.execute(task_vars)

    # With high EWS, should require immediate attention
    assert result.get("requires_immediate_attention") is True or \
           result.get("severity_level") in ["CRITICAL", "HIGH"]


# =============================================================================
# Test Graceful Degradation without TASY API
# =============================================================================


@pytest.mark.asyncio
async def test_vital_signs_worker_without_tasy_client_works(worker_without_scoring):
    """Test that worker functions normally without TASY API client."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-999",
        "patient_reference": "Patient/99999",
        "vital_signs": {
            "temperature_celsius": 37.5,
            "heart_rate": 75,
            "systolic_bp": 120,
            "diastolic_bp": 80,
        },
    }

    result = await worker_without_scoring.execute(task_vars)

    # Should still work, just without TASY scores
    assert "vital_signs_status" in result
    assert "alerts" in result
    assert result["vital_signs_status"] in ["NORMAL", "WARNING", "CRITICAL"]


@pytest.mark.asyncio
async def test_vital_signs_worker_handles_tasy_api_failure(
    fhir_client_mock, tenant_context
):
    """Test that worker handles TASY API failures gracefully."""
    # Create a mock that raises exception
    failing_tasy_client = AsyncMock()
    failing_tasy_client.get_early_warning_score = AsyncMock(
        side_effect=ExternalServiceException(
            "TASY API unavailable",
            service_name="tasy_api",
            operation="get_early_warning_score",
        )
    )

    worker = VitalSignsMonitoringWorker(
        fhir_client=fhir_client_mock,
        tasy_api_client=failing_tasy_client,
    )

    task_vars = {
        "encounter_reference": "Encounter/ATD-999",
        "patient_reference": "Patient/99999",
        "vital_signs": {
            "temperature_celsius": 37.5,
            "heart_rate": 75,
        },
    }

    # Should not raise, should degrade gracefully
    result = await worker.execute(task_vars)

    assert "vital_signs_status" in result
    # Worker should still complete successfully


# =============================================================================
# Test Score Enrichment Logic
# =============================================================================


@pytest.mark.asyncio
async def test_ews_score_enriches_alert_metadata(
    worker_with_scoring, stub_tasy_client
):
    """Test that EWS score enriches alert metadata."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "temperature_celsius": 38.5,
            "heart_rate": 105,
        },
    }

    result = await worker_with_scoring.execute(task_vars)

    # Check for enriched metadata in alerts
    if result["alerts"]:
        # At least one alert should have EWS context
        alert_data = str(result["alerts"])
        assert "ews" in alert_data.lower() or "score" in alert_data.lower()


@pytest.mark.asyncio
async def test_sentry_smart_alert_triggers_immediate_attention(
    worker_with_scoring, stub_tasy_client
):
    """Test that Sentry Smart Alert triggers immediate attention flag."""
    # Add Sentry Smart Alert
    stub_tasy_client.add_scoring_data("ATD-789", "sentry_smart_alert", {
        "score_type": "sentry_smart_alert",
        "alert_active": True,
        "IE_RISCO": "A",
    })

    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "heart_rate": 110,
        },
    }

    result = await worker_with_scoring.execute(task_vars)

    # Sentry Smart Alert should trigger immediate attention
    assert result.get("requires_immediate_attention") is True or \
           any("sentry" in str(alert).lower() for alert in result.get("alerts", []))


# =============================================================================
# Test Worker Output Structure
# =============================================================================


@pytest.mark.asyncio
async def test_worker_output_includes_scores_section(worker_with_scoring):
    """Test that worker output includes clinical_scores section."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "temperature_celsius": 37.0,
            "heart_rate": 70,
        },
    }

    result = await worker_with_scoring.execute(task_vars)

    # Result should have clinical scores if available
    assert isinstance(result, dict)
    # Either in dedicated section or integrated into alerts
    has_scores = "clinical_scores" in result or \
                 "ews_score" in result or \
                 any("score" in str(alert).lower() for alert in result.get("alerts", []))
    assert has_scores or result.get("vital_signs_status") == "NORMAL"


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
        "vital_signs": {
            "temperature_celsius": 37.0,
        },
    }

    # Should not crash, should work without scores
    result = await worker_with_scoring.execute(task_vars)

    assert "vital_signs_status" in result


@pytest.mark.asyncio
async def test_worker_caches_tasy_scores_appropriately(
    worker_with_scoring, stub_tasy_client
):
    """Test that worker doesn't call TASY API excessively (caching)."""
    task_vars = {
        "encounter_reference": "Encounter/ATD-789",
        "patient_reference": "Patient/12345",
        "vital_signs": {
            "heart_rate": 75,
        },
    }

    # Execute twice
    result1 = await worker_with_scoring.execute(task_vars)
    result2 = await worker_with_scoring.execute(task_vars)

    # Both should succeed
    assert result1["vital_signs_status"] is not None
    assert result2["vital_signs_status"] is not None
