"""
Unit tests for PatientFollowupReminderWorker.

Tests follow-up appointment reminder notifications via WhatsApp.
"""

from __future__ import annotations

import pytest

from healthcare_platform.clinical_operations.workers.patient_followup_reminder_worker import (
    ClinicalOperationsException,
    PatientFollowupReminderInput,
    PatientFollowupReminderWorker,
)
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    """Set up tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance with stub WhatsApp client."""
    return PatientFollowupReminderWorker(whatsapp_client=StubWhatsAppClient())


@pytest.mark.asyncio
async def test_execute_success(worker, tenant_ctx):
    """Test successful follow-up reminder delivery."""
    input_data = PatientFollowupReminderInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        doctor_name="Dr. Silva",
        specialty="Cardiologia",
        recommended_timeframe="7 dias",
        available_slots=[
            {"date": "2026-02-17", "time": "09:00"},
            {"date": "2026-02-17", "time": "14:00"},
            {"date": "2026-02-18", "time": "10:00"},
        ],
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True
    assert output.message_id is not None
    assert output.sent_at is not None
    assert output.reminder_id is not None
    assert output.action_taken is None


@pytest.mark.asyncio
async def test_execute_validates_required_fields(worker, tenant_ctx):
    """Test that required fields are validated."""
    with pytest.raises(Exception):  # Pydantic validation error
        PatientFollowupReminderInput(
            patient_id="patient-12345",
            phone_number="+5511987654321",
            # Missing doctor_name, specialty, recommended_timeframe, available_slots
        )


@pytest.mark.asyncio
async def test_execute_generates_unique_reminder_id(worker, tenant_ctx):
    """Test that each reminder gets a unique ID."""
    input_data = PatientFollowupReminderInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        doctor_name="Dr. Silva",
        specialty="Cardiologia",
        recommended_timeframe="7 dias",
        available_slots=[{"date": "2026-02-17", "time": "09:00"}],
    )

    output1 = await worker.execute(input_data)
    output2 = await worker.execute(input_data)

    assert output1.reminder_id != output2.reminder_id


@pytest.mark.asyncio
async def test_to_variables(worker, tenant_ctx):
    """Test output conversion to workflow variables."""
    input_data = PatientFollowupReminderInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        doctor_name="Dr. Silva",
        specialty="Cardiologia",
        recommended_timeframe="7 dias",
        available_slots=[{"date": "2026-02-17", "time": "09:00"}],
    )

    output = await worker.execute(input_data)
    variables = output.to_variables()

    assert isinstance(variables, dict)
    assert variables["notification_sent"] is True
    assert "reminder_id" in variables
    assert "sent_at" in variables
    assert "message_id" in variables


@pytest.mark.asyncio
async def test_execute_multiple_available_slots(worker, tenant_ctx):
    """Test reminder with multiple available appointment slots."""
    input_data = PatientFollowupReminderInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        doctor_name="Dr. Silva",
        specialty="Ortopedia",
        recommended_timeframe="14 dias",
        available_slots=[
            {"date": "2026-02-20", "time": "08:00"},
            {"date": "2026-02-20", "time": "09:00"},
            {"date": "2026-02-20", "time": "10:00"},
            {"date": "2026-02-21", "time": "08:00"},
            {"date": "2026-02-21", "time": "14:00"},
        ],
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True
    assert output.reminder_id is not None


@pytest.mark.asyncio
async def test_topic_constant():
    """Test that TOPIC constant is defined."""
    from healthcare_platform.clinical_operations.workers import (
        patient_followup_reminder_worker,
    )

    assert hasattr(patient_followup_reminder_worker, "TOPIC")
    assert (
        patient_followup_reminder_worker.TOPIC
        == "continuity.followup_reminder"
    )
    assert (
        PatientFollowupReminderWorker.TOPIC
        == "continuity.followup_reminder"
    )
