from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.doctor_readmission_risk_worker import (
    ClinicalOperationsException,
    DoctorReadmissionRiskInput,
    DoctorReadmissionRiskOutput,
    DoctorReadmissionRiskWorker,
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
    return DoctorReadmissionRiskWorker()


@pytest.fixture
def valid_task_variables():
    return {
        "doctor_id": "Practitioner/dr-silva-123",
        "phone_number": "+5511987654321",
        "patient_id": "Patient/patient-789",
        "patient_name": "João da Silva",
        "risk_score": 85.5,
        "risk_factors": [
            "História de readmissões recentes",
            "Múltiplas comorbidades",
            "Falta de suporte familiar",
        ],
        "recommended_actions": [
            "Agendar consulta de acompanhamento em 72h",
            "Revisar adesão medicamentosa",
            "Avaliar suporte domiciliar",
        ],
        "discharge_date": "2025-02-08T14:30:00Z",
    }


class TestDoctorReadmissionRiskWorker:
    def test_topic_constant(self):
        assert TOPIC == "continuity.readmission_risk"
        assert DoctorReadmissionRiskWorker.TOPIC == "continuity.readmission_risk"

    @pytest.mark.asyncio
    async def test_execute_success(self, tenant_ctx, worker, valid_task_variables):
        output = await worker.execute(valid_task_variables)

        assert isinstance(output, DoctorReadmissionRiskOutput)
        assert output.notification_sent is True
        assert output.message_id is not None
        assert output.sent_at is not None
        assert output.alert_id is not None

        parsed_sent_at = datetime.fromisoformat(output.sent_at)
        assert parsed_sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_execute_with_high_risk_score(self, tenant_ctx, worker, valid_task_variables):
        valid_task_variables["risk_score"] = 95.0

        output = await worker.execute(valid_task_variables)

        assert output.notification_sent is True
        assert output.message_id is not None
        assert output.alert_id is not None

    @pytest.mark.asyncio
    async def test_execute_with_single_risk_factor(self, tenant_ctx, worker, valid_task_variables):
        valid_task_variables["risk_factors"] = ["Múltiplas comorbidades"]
        valid_task_variables["recommended_actions"] = ["Agendar consulta de acompanhamento"]

        output = await worker.execute(valid_task_variables)

        assert output.notification_sent is True
        assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_execute_alert_id_is_unique(self, tenant_ctx, worker, valid_task_variables):
        output1 = await worker.execute(valid_task_variables)
        output2 = await worker.execute(valid_task_variables)

        assert output1.alert_id != output2.alert_id

    @pytest.mark.asyncio
    async def test_execute_missing_required_fields(self, tenant_ctx, worker):
        invalid_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
            "patient_id": "Patient/patient-789",
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

        worker = DoctorReadmissionRiskWorker(whatsapp_client=mock_client)

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "Failed to send readmission risk alert" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_output_to_variables(self, tenant_ctx, worker, valid_task_variables):
        output = await worker.execute(valid_task_variables)
        variables = output.to_variables()

        assert isinstance(variables, dict)
        assert variables["notification_sent"] is True
        assert "message_id" in variables
        assert "sent_at" in variables
        assert "alert_id" in variables

    def test_input_validation_success(self, valid_task_variables):
        input_data = DoctorReadmissionRiskInput(**valid_task_variables)

        assert input_data.doctor_id == "Practitioner/dr-silva-123"
        assert input_data.phone_number == "+5511987654321"
        assert input_data.patient_id == "Patient/patient-789"
        assert input_data.patient_name == "João da Silva"
        assert input_data.risk_score == 85.5
        assert len(input_data.risk_factors) == 3
        assert len(input_data.recommended_actions) == 3
        assert input_data.discharge_date == "2025-02-08T14:30:00Z"

    def test_input_validation_missing_required_fields(self):
        invalid_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
            "patient_id": "Patient/patient-789",
        }

        with pytest.raises(ValidationError):
            DoctorReadmissionRiskInput(**invalid_vars)

    def test_input_validation_invalid_risk_score_type(self):
        invalid_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
            "patient_id": "Patient/patient-789",
            "patient_name": "João da Silva",
            "risk_score": "high",
            "risk_factors": ["Factor 1"],
            "recommended_actions": ["Action 1"],
            "discharge_date": "2025-02-08T14:30:00Z",
        }

        with pytest.raises(ValidationError):
            DoctorReadmissionRiskInput(**invalid_vars)

    def test_input_validation_empty_lists(self):
        minimal_vars = {
            "doctor_id": "Practitioner/dr-silva-123",
            "phone_number": "+5511987654321",
            "patient_id": "Patient/patient-789",
            "patient_name": "João da Silva",
            "risk_score": 75.0,
            "risk_factors": [],
            "recommended_actions": [],
            "discharge_date": "2025-02-08T14:30:00Z",
        }

        input_data = DoctorReadmissionRiskInput(**minimal_vars)
        assert len(input_data.risk_factors) == 0
        assert len(input_data.recommended_actions) == 0
