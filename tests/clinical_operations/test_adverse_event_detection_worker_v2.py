"""
from __future__ import annotations

Tests for Adverse Event Detection Worker (Refactored v2)

Purpose: Validate refactored worker using pytest fixtures (no Stubs)

Test Categories:
1. Happy path - successful event processing
2. DMN evaluation - severity routing
3. Error handling - BPMN error responses
4. FHIR resource creation

ADR Compliance:
- ADR-003: Pytest fixtures instead of Stub classes
- ADR-007: DMN federation mocking
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService with default responses."""
    mock = MagicMock()
    mock.evaluate.return_value = {
        "nivelAlerta": "ALTO",
        "acaoRequerida": "Notificar equipe médica",
        "justificativa": "Evento moderado requer acompanhamento",
        "eventClassification": "preventable",
        "rcaRequired": False,
        "regulatoryReporting": False,
    }
    return mock


@pytest.fixture
def mock_fhir_client():
    """Mock FHIR client for resource operations."""
    mock = MagicMock()
    mock.create_resource.return_value = {"id": "AdverseEvent-12345"}
    return mock


@pytest.fixture
def mock_metrics():
    """Mock WorkerMetrics."""
    return MagicMock()


@pytest.fixture
def mock_tenant_resolver():
    """Mock TenantResolver."""
    mock = MagicMock()
    mock.resolve.return_value = "HOSPITAL_TEST"
    return mock


@pytest.fixture
def mock_lgpd_hasher():
    """Mock LGPDHasher."""
    mock = MagicMock()
    mock.hash.side_effect = lambda value, field: f"hashed_{value}"
    return mock


@pytest.fixture
def base_task_context():
    """Base task context for testing."""
    return TaskContext(
        task_id="task_ae_001",
        process_instance_id="proc_ae_456",
        tenant_id="HOSPITAL_TEST",
        variables={
            "encounterId": "Encounter/enc-12345",
            "patientId": "Patient/pat-67890",
            "eventType": "medication_error",
            "eventDescription": "Wrong dosage administered",
            "severity": "moderate",
            "occurrenceDatetime": datetime.utcnow().isoformat(),
            "patientOutcome": "temporary_harm",
        },
        worker_id="clinical.adverse_events",
        retries=3,
    )


@pytest.fixture
def worker_with_mocks(mock_dmn_service, mock_fhir_client, mock_metrics, mock_tenant_resolver, mock_lgpd_hasher):
    """Create worker with all dependencies mocked."""
    from healthcare_platform.clinical_operations.workers.adverse_event_detection_worker_v2 import (
        AdverseEventDetectionWorker,
    )
    
    return AdverseEventDetectionWorker(
        fhir_client=mock_fhir_client,
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
        tenant_resolver=mock_tenant_resolver,
        lgpd_hasher=mock_lgpd_hasher,
    )


# ============================================================================
# HAPPY PATH TESTS
# ============================================================================

class TestAdverseEventDetectionWorkerHappyPath:
    """Tests for successful event processing."""

    def test_execute_returns_success_with_dmn_outputs(
        self, worker_with_mocks, base_task_context, mock_dmn_service
    ):
        """Worker should return success with DMN evaluation outputs."""
        result = worker_with_mocks.execute(base_task_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["nivelAlerta"] == "ALTO"
        assert result.variables["acaoRequerida"] == "Notificar equipe médica"
        assert "adverseEventReference" in result.variables
        assert "eventId" in result.variables

    def test_execute_calls_dmn_service_with_correct_inputs(
        self, worker_with_mocks, base_task_context, mock_dmn_service
    ):
        """Worker should call DMN service with event type, severity, and outcome."""
        worker_with_mocks.execute(base_task_context)

        mock_dmn_service.evaluate.assert_called_once()
        call_args = mock_dmn_service.evaluate.call_args
        
        assert call_args.kwargs["tenant_id"] == "HOSPITAL_TEST"
        assert call_args.kwargs["category"] == "clinical_safety"
        assert call_args.kwargs["table_name"] == "adverse_event_severity_assessment"
        assert call_args.kwargs["inputs"]["eventType"] == "medication_error"
        assert call_args.kwargs["inputs"]["severity"] == "moderate"

    def test_execute_generates_event_id(
        self, worker_with_mocks, base_task_context
    ):
        """Worker should generate unique event ID."""
        result = worker_with_mocks.execute(base_task_context)

        assert result.variables["eventId"].startswith("AE-")
        assert len(result.variables["eventId"]) > 10


# ============================================================================
# DMN SEVERITY ROUTING TESTS
# ============================================================================

class TestDMNSeverityRouting:
    """Tests for DMN-based severity assessment."""

    def test_critical_severity_returns_critico(
        self, worker_with_mocks, base_task_context, mock_dmn_service
    ):
        """Critical events should return CRITICO level."""
        mock_dmn_service.evaluate.return_value = {
            "nivelAlerta": "CRITICO",
            "acaoRequerida": "Escalonamento imediato",
            "justificativa": "Óbito - notificação ANVISA",
            "eventClassification": "preventable",
            "rcaRequired": True,
            "regulatoryReporting": True,
        }
        base_task_context.variables["severity"] = "fatal"
        base_task_context.variables["patientOutcome"] = "death"

        result = worker_with_mocks.execute(base_task_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["nivelAlerta"] == "CRITICO"
        assert result.variables["regulatoryReporting"] is True
        assert result.variables["rcaRequired"] is True

    def test_mild_severity_returns_baixo(
        self, worker_with_mocks, base_task_context, mock_dmn_service
    ):
        """Mild events should return BAIXO level."""
        mock_dmn_service.evaluate.return_value = {
            "nivelAlerta": "BAIXO",
            "acaoRequerida": "Registrar evento",
            "justificativa": "Evento sem dano significativo",
            "eventClassification": "non_preventable",
            "rcaRequired": False,
            "regulatoryReporting": False,
        }
        base_task_context.variables["severity"] = "mild"
        base_task_context.variables["patientOutcome"] = "no_harm"

        result = worker_with_mocks.execute(base_task_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["nivelAlerta"] == "BAIXO"
        assert result.variables["regulatoryReporting"] is False


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Tests for error scenarios and BPMN error responses."""

    def test_dmn_evaluation_failure_returns_bpmn_error(
        self, worker_with_mocks, base_task_context, mock_dmn_service
    ):
        """DMN evaluation failure should return BPMN error."""
        mock_dmn_service.evaluate.side_effect = ValueError("No matching DMN rules found")

        result = worker_with_mocks.execute(base_task_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_ADVERSE_EVENT_PROCESSING"
        assert "No matching DMN rules" in result.error_message

    def test_missing_event_type_uses_default(
        self, worker_with_mocks, base_task_context, mock_dmn_service
    ):
        """Missing event type should default to 'other'."""
        del base_task_context.variables["eventType"]

        worker_with_mocks.execute(base_task_context)

        call_args = mock_dmn_service.evaluate.call_args
        assert call_args.kwargs["inputs"]["eventType"] == "other"


# ============================================================================
# EVENT TYPE TESTS
# ============================================================================

class TestEventTypes:
    """Tests for different adverse event types."""

    @pytest.mark.parametrize("event_type,expected_classification", [
        ("medication_error", "preventable"),
        ("fall", "preventable"),
        ("infection", "non_preventable"),
        ("surgical_complication", "unavoidable"),
        ("equipment_failure", "non_preventable"),
    ])
    def test_event_type_classification(
        self,
        worker_with_mocks,
        base_task_context,
        mock_dmn_service,
        event_type,
        expected_classification,
    ):
        """Different event types should be classified correctly by DMN."""
        mock_dmn_service.evaluate.return_value = {
            "nivelAlerta": "MEDIO",
            "acaoRequerida": "Acompanhar",
            "justificativa": "Evento padrão",
            "eventClassification": expected_classification,
            "rcaRequired": False,
            "regulatoryReporting": False,
        }
        base_task_context.variables["eventType"] = event_type

        result = worker_with_mocks.execute(base_task_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["eventClassification"] == expected_classification
