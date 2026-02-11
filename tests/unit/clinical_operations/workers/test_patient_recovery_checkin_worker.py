"""
Unit tests for PatientRecoveryCheckinWorker.

Tests patient recovery check-in notifications via WhatsApp.
"""

from __future__ import annotations

import pytest

from healthcare_platform.clinical_operations.workers.patient_recovery_checkin_worker import (
    ClinicalOperationsException,
    PatientRecoveryCheckinInput,
    PatientRecoveryCheckinWorker,
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
    return PatientRecoveryCheckinWorker(whatsapp_client=StubWhatsAppClient())


@pytest.mark.asyncio
async def test_execute_success(worker, tenant_ctx):
    """Test successful recovery check-in delivery."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-09T10:00:00Z",
        days_since_discharge=1,
        condition_name="Pneumonia",
        checkin_number=1,
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True
    assert output.message_id is not None
    assert output.sent_at is not None
    assert output.checkin_id is not None
    assert output.response_received is False
    assert output.reported_status is None


@pytest.mark.asyncio
async def test_execute_validates_required_fields(worker, tenant_ctx):
    """Test that required fields are validated."""
    with pytest.raises(Exception):  # Pydantic validation error
        PatientRecoveryCheckinInput(
            patient_id="patient-12345",
            phone_number="+5511987654321",
            # Missing discharge_date, days_since_discharge, condition_name, checkin_number
        )


@pytest.mark.asyncio
async def test_execute_generates_unique_checkin_id(worker, tenant_ctx):
    """Test that each check-in gets a unique ID."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-09T10:00:00Z",
        days_since_discharge=1,
        condition_name="Pneumonia",
        checkin_number=1,
    )

    output1 = await worker.execute(input_data)
    output2 = await worker.execute(input_data)

    assert output1.checkin_id != output2.checkin_id


@pytest.mark.asyncio
async def test_to_variables(worker, tenant_ctx):
    """Test output conversion to workflow variables."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-09T10:00:00Z",
        days_since_discharge=3,
        condition_name="Cirurgia Cardíaca",
        checkin_number=2,
    )

    output = await worker.execute(input_data)
    variables = output.to_variables()

    assert isinstance(variables, dict)
    assert variables["notification_sent"] is True
    assert "checkin_id" in variables
    assert "sent_at" in variables
    assert "message_id" in variables
    assert variables["response_received"] is False
    assert variables["reported_status"] is None


@pytest.mark.asyncio
async def test_execute_day_1_checkin(worker, tenant_ctx):
    """Test Day 1 post-discharge check-in."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-09T10:00:00Z",
        days_since_discharge=1,
        condition_name="Apendicectomia",
        checkin_number=1,
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True
    assert output.checkin_id is not None


@pytest.mark.asyncio
async def test_execute_day_3_checkin(worker, tenant_ctx):
    """Test Day 3 post-discharge check-in."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-07T10:00:00Z",
        days_since_discharge=3,
        condition_name="Fratura de Fêmur",
        checkin_number=2,
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True


@pytest.mark.asyncio
async def test_execute_day_7_checkin(worker, tenant_ctx):
    """Test Day 7 post-discharge check-in."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-03T10:00:00Z",
        days_since_discharge=7,
        condition_name="Infarto Agudo do Miocárdio",
        checkin_number=3,
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True


@pytest.mark.asyncio
async def test_execute_day_14_checkin(worker, tenant_ctx):
    """Test Day 14 post-discharge check-in."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-01-27T10:00:00Z",
        days_since_discharge=14,
        condition_name="AVC Isquêmico",
        checkin_number=4,
    )

    output = await worker.execute(input_data)

    assert output.notification_sent is True


@pytest.mark.asyncio
async def test_topic_constant():
    """Test that TOPIC constant is defined."""
    from healthcare_platform.clinical_operations.workers import (
        patient_recovery_checkin_worker,
    )

    assert hasattr(patient_recovery_checkin_worker, "TOPIC")
    assert (
        patient_recovery_checkin_worker.TOPIC == "continuity.recovery_checkin"
    )
    assert (
        PatientRecoveryCheckinWorker.TOPIC == "continuity.recovery_checkin"
    )


@pytest.mark.asyncio
async def test_response_received_defaults_to_false(worker, tenant_ctx):
    """Test that response_received defaults to False."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-09T10:00:00Z",
        days_since_discharge=1,
        condition_name="Pneumonia",
        checkin_number=1,
    )

    output = await worker.execute(input_data)

    assert output.response_received is False


@pytest.mark.asyncio
async def test_reported_status_defaults_to_none(worker, tenant_ctx):
    """Test that reported_status defaults to None."""
    input_data = PatientRecoveryCheckinInput(
        patient_id="patient-12345",
        phone_number="+5511987654321",
        discharge_date="2026-02-09T10:00:00Z",
        days_since_discharge=1,
        condition_name="Pneumonia",
        checkin_number=1,
    )

    output = await worker.execute(input_data)

    assert output.reported_status is None
