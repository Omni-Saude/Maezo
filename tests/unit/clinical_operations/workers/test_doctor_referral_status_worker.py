from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.doctor_referral_status_worker import (
    ClinicalOperationsException,
    DoctorReferralStatusInput,
    DoctorReferralStatusOutput,
    DoctorReferralStatusWorker,
    TOPIC,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant
from healthcare_platform.shared.integrations.whatsapp_client import StubWhatsAppClient
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    return DoctorReferralStatusWorker()


@pytest.fixture
def valid_task_variables():
    return {
        "doctor_id": "Practitioner/dr-silva-123",
        "phone_number": "+5511987654321",
        "referral_id": "ServiceRequest/ref-456",
        "patient_name": "João da Silva",
        "specialist_name": "Dr. Maria Santos",
        "specialty": "Cardiologia",
        "status": "approved",
        "notes": "Encaminhamento aprovado para consulta na próxima semana",
    }


class TestDoctorReferralStatusWorker:
    def test_topic_constant(self):
        assert TOPIC == "continuity.referral_status"
        assert DoctorReferralStatusWorker.TOPIC == "continuity.referral_status"

    @pytest.mark.asyncio
    async def test_execute_success(self, tenant_ctx, worker, valid_task_variables):
        output = await worker.execute(valid_task_variables)

        assert isinstance(output, DoctorReferralStatusOutput)
        assert output.notification_sent is True
        assert output.message_id is not None
        assert output.sent_at is not None

        parsed_sent_at = datetime.fromisoformat(output.sent_at)
        assert parsed_sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_execute_with_minimal_notes(self, tenant_ctx, worker):
        task_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
            "referral_id": "ServiceRequest/ref-456",
            "patient_name": "João da Silva",
            "specialist_name": "Dr. Maria Santos",
            "specialty": "Cardiologia",
            "status": "approved",
            "notes": "",
        }

        output = await worker.execute(task_vars)

        assert output.notification_sent is True
        assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_execute_with_denied_status(self, tenant_ctx, worker, valid_task_variables):
        valid_task_variables["status"] = "denied"
        valid_task_variables["notes"] = "Critérios clínicos não atendidos"

        output = await worker.execute(valid_task_variables)

        assert output.notification_sent is True
        assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_execute_missing_required_fields(self, tenant_ctx, worker):
        invalid_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
        }

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(invalid_vars)

        assert "Invalid input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_no_tenant_context(self, worker, valid_task_variables):
        clear_tenant()

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_execute_whatsapp_send_failure(self, tenant_ctx, valid_task_variables):
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template_message.side_effect = Exception("WhatsApp API error")

        worker = DoctorReferralStatusWorker(whatsapp_client=mock_client)

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "Failed to send referral status notification" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_output_to_variables(self, tenant_ctx, worker, valid_task_variables):
        output = await worker.execute(valid_task_variables)
        variables = output.to_variables()

        assert isinstance(variables, dict)
        assert variables["notification_sent"] is True
        assert "message_id" in variables
        assert "sent_at" in variables

    def test_input_validation_success(self, valid_task_variables):
        input_data = DoctorReferralStatusInput(**valid_task_variables)

        assert input_data.doctor_id == "Practitioner/dr-silva-123"
        assert input_data.phone_number == "+5511987654321"
        assert input_data.referral_id == "ServiceRequest/ref-456"
        assert input_data.patient_name == "João da Silva"
        assert input_data.specialist_name == "Dr. Maria Santos"
        assert input_data.specialty == "Cardiologia"
        assert input_data.status == "approved"
        assert input_data.notes == "Encaminhamento aprovado para consulta na próxima semana"

    def test_input_validation_default_notes(self):
        minimal_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
            "referral_id": "ServiceRequest/ref-456",
            "patient_name": "João da Silva",
            "specialist_name": "Dr. Maria Santos",
            "specialty": "Cardiologia",
            "status": "approved",
        }

        input_data = DoctorReferralStatusInput(**minimal_vars)
        assert input_data.notes == ""

    def test_input_validation_missing_required_fields(self):
        invalid_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
        }

        with pytest.raises(ValidationError):
            DoctorReferralStatusInput(**invalid_vars)
