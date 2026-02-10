"""Root conftest with shared fixtures for all tests."""

from unittest.mock import AsyncMock
import pytest
from datetime import datetime
from typing import AsyncGenerator

from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant
from healthcare_platform.shared.domain.enums import TenantCode


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "dmn: mark test as a DMN decision table test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "asyncio: mark test as async")


@pytest.fixture(autouse=True)
def test_isolation():
    """Fixture que garante isolamento entre testes."""
    # Setup
    clear_tenant()
    yield
    # Teardown
    clear_tenant()


# ============================================================================
# Tenant Fixtures
# ============================================================================

@pytest.fixture
def tenant_austa() -> TenantContext:
    """Fixture para tenant AUSTA com contexto configurado."""
    tenant = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(tenant)
    yield tenant
    clear_tenant()


@pytest.fixture
def tenant_hpa() -> TenantContext:
    """Fixture para tenant AMH_SP com contexto configurado."""
    tenant = TenantContext.from_tenant_code(TenantCode.AMH_SP)
    set_current_tenant(tenant)
    yield tenant
    clear_tenant()


@pytest.fixture
def current_tenant(tenant_austa) -> TenantContext:
    """Fixture para tenant atual (default: AUSTA)."""
    return tenant_austa


# ============================================================================
# Mock Client Fixtures
# ============================================================================

@pytest.fixture
def fhir_client() -> AsyncMock:
    """Mock FHIR client."""
    mock = AsyncMock()
    mock.create = AsyncMock()
    mock.read = AsyncMock()
    mock.search = AsyncMock()
    mock.update = AsyncMock()
    mock.delete = AsyncMock()
    mock.validate_resource = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def ans_client() -> AsyncMock:
    """Mock ANS client."""
    mock = AsyncMock()
    mock.validate_beneficiary = AsyncMock()
    mock.get_procedure_coverage = AsyncMock()
    mock.submit_billing = AsyncMock()
    return mock


@pytest.fixture
def tasy_client() -> AsyncMock:
    """Mock TASY client."""
    mock = AsyncMock()
    mock.get_patient = AsyncMock()
    mock.create_appointment = AsyncMock()
    mock.get_schedule = AsyncMock()
    return mock


@pytest.fixture
def mv_soul_client() -> AsyncMock:
    """Mock MV Soul client."""
    mock = AsyncMock()
    mock.get_patient = AsyncMock()
    mock.sync_patient = AsyncMock()
    mock.get_medical_record = AsyncMock()
    return mock


@pytest.fixture
def whatsapp_client() -> AsyncMock:
    """Mock WhatsApp client."""
    mock = AsyncMock()
    mock.send_message = AsyncMock()
    mock.send_template = AsyncMock()
    mock.get_message_status = AsyncMock()
    return mock


@pytest.fixture
def database_client() -> AsyncMock:
    """Mock database client."""
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.fetch_one = AsyncMock()
    mock.fetch_all = AsyncMock()
    mock.begin_transaction = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    return mock


@pytest.fixture
def camunda_client() -> AsyncMock:
    """Mock Camunda client."""
    mock = AsyncMock()
    mock.fetch_and_lock = AsyncMock()
    mock.complete = AsyncMock()
    mock.handle_failure = AsyncMock()
    mock.handle_bpmn_error = AsyncMock()
    mock.start_process = AsyncMock()
    mock.get_process_instance = AsyncMock()
    return mock


@pytest.fixture
def erp_client() -> AsyncMock:
    """Mock ERP client."""
    mock = AsyncMock()
    mock.create_invoice = AsyncMock()
    mock.get_contract_rules = AsyncMock()
    mock.calculate_billing = AsyncMock()
    mock.submit_glosa = AsyncMock()
    return mock


@pytest.fixture
def kafka_client() -> AsyncMock:
    """Mock Kafka client."""
    mock = AsyncMock()
    mock.produce = AsyncMock()
    mock.consume = AsyncMock()
    mock.subscribe = AsyncMock()
    return mock


# ============================================================================
# Mock FHIR Resource Fixtures
# ============================================================================

@pytest.fixture
def mock_patient() -> dict:
    """Mock FHIR Patient resource."""
    return {
        "resourceType": "Patient",
        "id": "patient-123",
        "identifier": [
            {
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                "value": "12345678901",
            },
            {
                "system": "http://austa.com.br/fhir/identifier/mrn",
                "value": "MRN-123456",
            },
        ],
        "name": [
            {
                "use": "official",
                "family": "Silva",
                "given": ["João", "Pedro"],
            }
        ],
        "gender": "male",
        "birthDate": "1980-05-15",
        "telecom": [
            {
                "system": "phone",
                "value": "+5511987654321",
                "use": "mobile",
            }
        ],
        "address": [
            {
                "use": "home",
                "line": ["Rua das Flores, 123"],
                "city": "São Paulo",
                "state": "SP",
                "postalCode": "01234-567",
                "country": "BR",
            }
        ],
    }


@pytest.fixture
def mock_appointment() -> dict:
    """Mock FHIR Appointment resource."""
    return {
        "resourceType": "Appointment",
        "id": "appointment-456",
        "status": "booked",
        "serviceType": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/service-type",
                        "code": "124",
                        "display": "General Practice",
                    }
                ]
            }
        ],
        "appointmentType": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                    "code": "ROUTINE",
                    "display": "Routine appointment",
                }
            ]
        },
        "start": "2024-03-15T10:00:00Z",
        "end": "2024-03-15T10:30:00Z",
        "participant": [
            {
                "actor": {"reference": "Patient/patient-123"},
                "status": "accepted",
            },
            {
                "actor": {"reference": "Practitioner/practitioner-789"},
                "status": "accepted",
            },
        ],
    }


@pytest.fixture
def mock_practitioner() -> dict:
    """Mock FHIR Practitioner resource."""
    return {
        "resourceType": "Practitioner",
        "id": "practitioner-789",
        "identifier": [
            {
                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                "value": "98765432100",
            },
            {
                "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/cnes",
                "value": "1234567",
            },
        ],
        "name": [
            {
                "use": "official",
                "family": "Santos",
                "given": ["Maria", "Clara"],
                "prefix": ["Dr."],
            }
        ],
        "qualification": [
            {
                "code": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0360",
                            "code": "MD",
                            "display": "Medical Doctor",
                        }
                    ]
                }
            }
        ],
    }


@pytest.fixture
def mock_location() -> dict:
    """Mock FHIR Location resource."""
    return {
        "resourceType": "Location",
        "id": "location-001",
        "name": "Consultório A - Cardiologia",
        "type": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                        "code": "CARD",
                        "display": "Ambulatory Health Care Facilities; Clinic/Center; Rehabilitation: Cardiac Facilities",
                    }
                ]
            }
        ],
        "address": {
            "line": ["Av. Paulista, 1000 - Sala 501"],
            "city": "São Paulo",
            "state": "SP",
            "postalCode": "01310-100",
            "country": "BR",
        },
    }


@pytest.fixture
def mock_slot() -> dict:
    """Mock FHIR Slot resource."""
    return {
        "resourceType": "Slot",
        "id": "slot-001",
        "schedule": {"reference": "Schedule/schedule-001"},
        "status": "free",
        "start": "2024-03-15T10:00:00Z",
        "end": "2024-03-15T10:30:00Z",
    }


@pytest.fixture
def mock_encounter() -> dict:
    """Mock FHIR Encounter resource."""
    return {
        "resourceType": "Encounter",
        "id": "encounter-001",
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
        "subject": {"reference": "Patient/patient-123"},
        "participant": [
            {
                "individual": {"reference": "Practitioner/practitioner-789"}
            }
        ],
        "period": {
            "start": "2024-03-15T10:00:00Z",
            "end": "2024-03-15T10:30:00Z",
        },
    }
