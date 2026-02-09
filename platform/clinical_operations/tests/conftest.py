"""Shared test fixtures for Clinical Operations."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


@pytest.fixture
def tenant_austa():
    """AUSTA tenant fixture."""
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def tenant_hpa():
    """HPA tenant fixture."""
    ctx = TenantContext.from_tenant_code(TenantCode.HPA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def mock_patient():
    """Mock patient resource."""
    return {
        "resourceType": "Patient",
        "id": "patient-123",
        "identifier": [{"system": "urn:hospital:patient", "value": "P123456"}],
        "name": [{"family": "Silva", "given": ["João"]}],
        "gender": "male",
        "birthDate": "1980-01-01",
    }


@pytest.fixture
def mock_encounter():
    """Mock encounter resource."""
    return {
        "resourceType": "Encounter",
        "id": "encounter-456",
        "status": "in-progress",
        "class": {"code": "IMP", "display": "inpatient encounter"},
        "subject": {"reference": "Patient/patient-123"},
        "period": {"start": "2025-01-15T08:00:00Z"},
    }


@pytest.fixture
def mock_observation():
    """Mock observation resource."""
    return {
        "resourceType": "Observation",
        "id": "obs-789",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure"}]},
        "subject": {"reference": "Patient/patient-123"},
        "valueQuantity": {"value": 120, "unit": "mmHg"},
    }
