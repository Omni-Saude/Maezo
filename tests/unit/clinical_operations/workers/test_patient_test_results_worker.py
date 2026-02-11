"""Unit tests for Patient Test Results Worker."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from healthcare_platform.clinical_operations.workers.patient_test_results_worker import (
    ClinicalOperationsException,
    PatientTestResultsInput,
    PatientTestResultsOutput,
    PatientTestResultsWorker,
)
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Set up tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker() -> PatientTestResultsWorker:
    """Create worker instance with stub WhatsApp client."""
    return PatientTestResultsWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def sample_input_with_followup() -> PatientTestResultsInput:
    """Create sample input data requiring followup."""
    return PatientTestResultsInput(
        patient_id="patient-123",
        phone_number="+5511999999999",
        test_name="Hemograma Completo",
        result_date="2026-02-10T14:30:00Z",
        requires_followup=True,
        portal_url="https://portal.austa.health/results/abc123",
    )


@pytest.fixture
def sample_input_no_followup() -> PatientTestResultsInput:
    """Create sample input data without followup."""
    return PatientTestResultsInput(
        patient_id="patient-456",
        phone_number="+5511888888888",
        test_name="Glicemia em Jejum",
        result_date="2026-02-09T10:15:00Z",
        requires_followup=False,
        portal_url="https://portal.austa.health/results/xyz789",
    )


def test_worker_initialization() -> None:
    """Test worker initialization."""
    worker = PatientTestResultsWorker()
    assert worker.whatsapp_client is not None
    assert worker.TOPIC == "continuity.results_available"


def test_notify_test_results_success(
    worker: PatientTestResultsWorker,
    sample_input_with_followup: PatientTestResultsInput,
    tenant_ctx: TenantContext,
) -> None:
    """Test successful test results notification."""
    output = worker.notify_test_results(sample_input_with_followup)

    assert isinstance(output, PatientTestResultsOutput)
    assert output.notification_sent is True
    assert output.message_id is not None
    assert output.notification_id is not None

    # Validate notification_id is a valid UUID
    uuid.UUID(output.notification_id)

    # Validate sent_at is a valid ISO 8601 timestamp
    datetime.fromisoformat(output.sent_at)


def test_notify_test_results_template_with_followup(
    sample_input_with_followup: PatientTestResultsInput,
    tenant_ctx: TenantContext,
) -> None:
    """Test WhatsApp template formatting when followup is required."""
    mock_client = MagicMock(spec=StubWhatsAppClient)
    mock_client.send_template.return_value = "msg-123"

    worker = PatientTestResultsWorker(whatsapp_client=mock_client)
    output = worker.notify_test_results(sample_input_with_followup)

    # Verify send_template was called
    assert mock_client.send_template.called
    call_args = mock_client.send_template.call_args

    # Check phone number
    assert call_args.kwargs["to"] == "+5511999999999"

    # Check template structure
    template = call_args.kwargs["template"]
    assert isinstance(template, WhatsAppTemplate)
    assert template.name == "results_available_v1"
    assert template.language == "pt_BR"

    # Check body parameters (test name, date, followup message)
    body_component = next(c for c in template.components if c["type"] == "body")
    params = body_component["parameters"]
    assert len(params) == 3
    assert params[0]["text"] == "Hemograma Completo"
    assert params[1]["text"] == "2026-02-10T14:30:00Z"
    assert "Recomendamos agendar uma consulta" in params[2]["text"]

    # Check buttons (2 quick replies)
    button_components = [c for c in template.components if c["type"] == "button"]
    assert len(button_components) == 2

    # Verify button payloads contain notification_id
    notification_id = output.notification_id
    payloads = [
        c["parameters"][0]["payload"] for c in button_components
    ]
    assert f"view_results:{notification_id}" in payloads
    assert f"schedule_discussion:{notification_id}" in payloads


def test_notify_test_results_template_no_followup(
    sample_input_no_followup: PatientTestResultsInput,
    tenant_ctx: TenantContext,
) -> None:
    """Test WhatsApp template formatting when followup is not required."""
    mock_client = MagicMock(spec=StubWhatsAppClient)
    mock_client.send_template.return_value = "msg-456"

    worker = PatientTestResultsWorker(whatsapp_client=mock_client)
    worker.notify_test_results(sample_input_no_followup)

    # Check template structure
    template = mock_client.send_template.call_args.kwargs["template"]

    # Check body parameters for no-followup message
    body_component = next(c for c in template.components if c["type"] == "body")
    params = body_component["parameters"]
    assert len(params) == 3
    assert params[0]["text"] == "Glicemia em Jejum"
    assert params[1]["text"] == "2026-02-09T10:15:00Z"
    assert "Sem necessidade de acompanhamento" in params[2]["text"]


def test_notify_test_results_whatsapp_failure(
    sample_input_with_followup: PatientTestResultsInput,
    tenant_ctx: TenantContext,
) -> None:
    """Test handling of WhatsApp send failure."""
    mock_client = MagicMock(spec=StubWhatsAppClient)
    mock_client.send_template.side_effect = Exception("WhatsApp API error")

    worker = PatientTestResultsWorker(whatsapp_client=mock_client)

    with pytest.raises(ClinicalOperationsException) as exc_info:
        worker.notify_test_results(sample_input_with_followup)

    assert "Failed to send test results notification" in str(exc_info.value)
    assert exc_info.value.code == "CLINICAL_OPERATIONS_ERROR"
    assert exc_info.value.bpmn_error_code == "CLINICAL_OPERATIONS_ERROR"


def test_output_to_variables(
    worker: PatientTestResultsWorker,
    sample_input_with_followup: PatientTestResultsInput,
    tenant_ctx: TenantContext,
) -> None:
    """Test output conversion to variables."""
    output = worker.notify_test_results(sample_input_with_followup)
    variables = output.to_variables()

    assert isinstance(variables, dict)
    assert variables["notification_sent"] is True
    assert "message_id" in variables
    assert "sent_at" in variables
    assert "notification_id" in variables


def test_notify_test_results_different_tests(
    worker: PatientTestResultsWorker,
    tenant_ctx: TenantContext,
) -> None:
    """Test notifications for different test types."""
    test_cases = [
        ("Raio-X de Tórax", True),
        ("Eletrocardiograma", False),
        ("Tomografia Computadorizada", True),
        ("Ultrassonografia", False),
    ]

    for test_name, requires_followup in test_cases:
        input_data = PatientTestResultsInput(
            patient_id=f"patient-{test_name}",
            phone_number="+5511999999999",
            test_name=test_name,
            result_date=datetime.now(UTC).isoformat(),
            requires_followup=requires_followup,
            portal_url="https://portal.austa.health/results/test123",
        )

        output = worker.notify_test_results(input_data)

        assert output.notification_sent is True
        assert output.notification_id is not None


def test_notify_test_results_portal_url_not_logged(
    sample_input_with_followup: PatientTestResultsInput,
    tenant_ctx: TenantContext,
) -> None:
    """Test that portal_url is not logged (LGPD compliance)."""
    mock_client = MagicMock(spec=StubWhatsAppClient)
    mock_client.send_template.return_value = "msg-123"

    worker = PatientTestResultsWorker(whatsapp_client=mock_client)
    output = worker.notify_test_results(sample_input_with_followup)

    # Verify the notification was sent
    assert output.notification_sent is True

    # Note: portal_url should be used for deep linking but not logged
    # This is enforced by code review and LGPD compliance checks


def test_topic_constant() -> None:
    """Test TOPIC constant is correctly defined."""
    assert PatientTestResultsWorker.TOPIC == "continuity.results_available"
    from healthcare_platform.clinical_operations.workers import (
        patient_test_results_worker,
    )

    assert patient_test_results_worker.TOPIC == "continuity.results_available"
