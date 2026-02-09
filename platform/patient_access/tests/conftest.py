"""Shared test fixtures for patient_access module."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


@pytest.fixture
def tenant_austa():
    """Fixture for AUSTA tenant context."""
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def tenant_hpa():
    """Fixture for HPA tenant context."""
    ctx = TenantContext.from_tenant_code(TenantCode.HPA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def ans_client():
    """Mock ANS verification client."""
    return AsyncMock()


@pytest.fixture
def tasy_client():
    """Mock TASY integration client."""
    return AsyncMock()


@pytest.fixture
def mv_soul_client():
    """Mock MV Soul integration client."""
    return AsyncMock()


@pytest.fixture
def whatsapp_client():
    """Mock WhatsApp notification client."""
    return AsyncMock()


@pytest.fixture
def mock_patient():
    """Mock patient resource."""
    return {
        "resourceType": "Patient",
        "id": "patient-123",
        "identifier": [
            {
                "system": "http://austa.com.br/mrn",
                "value": "MRN123456"
            },
            {
                "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/cpf",
                "value": "12345678901"
            }
        ],
        "name": [
            {
                "use": "official",
                "family": "Silva",
                "given": ["João", "Carlos"]
            }
        ],
        "gender": "male",
        "birthDate": "1980-05-15",
        "telecom": [
            {
                "system": "phone",
                "value": "+5511987654321",
                "use": "mobile"
            },
            {
                "system": "email",
                "value": "joao.silva@example.com"
            }
        ],
        "address": [
            {
                "use": "home",
                "line": ["Rua Exemplo, 123"],
                "city": "São Paulo",
                "state": "SP",
                "postalCode": "01234-567",
                "country": "BR"
            }
        ]
    }


@pytest.fixture
def mock_encounter():
    """Mock encounter resource."""
    return {
        "resourceType": "Encounter",
        "id": "encounter-456",
        "status": "planned",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory"
        },
        "subject": {
            "reference": "Patient/patient-123"
        },
        "period": {
            "start": "2024-01-15T10:00:00Z"
        }
    }


@pytest.fixture
def mock_appointment():
    """Mock appointment resource."""
    return {
        "resourceType": "Appointment",
        "id": "appointment-789",
        "status": "booked",
        "serviceType": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/service-type",
                        "code": "124",
                        "display": "General Practice"
                    }
                ]
            }
        ],
        "start": "2024-01-15T10:00:00Z",
        "end": "2024-01-15T10:30:00Z",
        "minutesDuration": 30,
        "participant": [
            {
                "actor": {
                    "reference": "Patient/patient-123"
                },
                "status": "accepted"
            },
            {
                "actor": {
                    "reference": "Practitioner/practitioner-001"
                },
                "status": "accepted"
            }
        ]
    }


@pytest.fixture
def mock_coverage():
    """Mock coverage resource."""
    return {
        "resourceType": "Coverage",
        "id": "coverage-999",
        "status": "active",
        "subscriber": {
            "reference": "Patient/patient-123"
        },
        "beneficiary": {
            "reference": "Patient/patient-123"
        },
        "payor": [
            {
                "reference": "Organization/payor-001",
                "display": "Health Insurance Co"
            }
        ],
        "class": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                            "code": "plan"
                        }
                    ]
                },
                "value": "PLAN-001",
                "name": "Gold Plan"
            }
        ]
    }
