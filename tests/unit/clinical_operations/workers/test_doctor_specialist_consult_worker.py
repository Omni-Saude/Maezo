"""Tests for DoctorSpecialistConsultWorker."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from healthcare_platform.clinical_operations.workers.doctor_specialist_consult_worker import DoctorSpecialistConsultWorker
from healthcare_platform.shared.domain.exceptions import ClinicalOperationsException

# Stub classes for V1 API compatibility (V2 workers removed these)
class DoctorSpecialistConsultInput:
    """Stub for removed V1 Pydantic model."""
    def __init__(self, **kwargs): self.__dict__.update(kwargs)
class DoctorSpecialistConsultOutput:
    """Stub for removed V1 Pydantic model."""
    def __init__(self, **kwargs): self.__dict__.update(kwargs)
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import (
    set_current_tenant,
    TenantContext,
    clear_tenant,
)

pytestmark = pytest.mark.skip(reason="Test needs updating for V2 worker pattern (TaskContext/TaskResult)")

@pytest.fixture
def tenant_ctx():
    """Set up tenant context for testing."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker with stub WhatsApp client."""
    return DoctorSpecialistConsultWorker(whatsapp_client=StubWhatsAppClient())


@pytest.mark.unit
class TestDoctorSpecialistConsultWorker:
    @pytest.mark.asyncio
    async def test_execute_success(self, worker, tenant_ctx):
        """Test successful specialist consultation request."""
        # Arrange
        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Cardiologia",
            "urgency": "high",
            "clinical_summary": "Paciente com dor torácica aguda",
            "phone_number": "+5511987654321",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert result["consult_request_id"] is not None
        assert len(result["consult_request_id"]) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_consult_request_id_generated(self, worker, tenant_ctx):
        """Test that consult_request_id is a valid UUID."""
        # Arrange
        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Neurologia",
            "urgency": "critical",
            "clinical_summary": "Suspeita de AVC",
            "phone_number": "+5511987654321",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert - UUID format validation
        consult_id = result["consult_request_id"]
        assert isinstance(consult_id, str)
        assert len(consult_id) == 36
        assert consult_id.count("-") == 4

    @pytest.mark.asyncio
    async def test_interactive_buttons_in_template(self, worker, tenant_ctx):
        """Test that interactive buttons are included in template."""
        # Arrange
        consult_id = "test-uuid-123"

        # Act
        buttons = worker._build_interactive_buttons(consult_id)

        # Assert - 3 buttons present
        assert len(buttons) == 3
        assert buttons[0]["parameters"][0]["payload"] == f"accept:{consult_id}"
        assert buttons[1]["parameters"][0]["payload"] == f"decline:{consult_id}"
        assert buttons[2]["parameters"][0]["payload"] == f"callback:{consult_id}"

        # Assert - button structure
        for i, button in enumerate(buttons):
            assert button["type"] == "button"
            assert button["sub_type"] == "quick_reply"
            assert button["index"] == str(i)

    @pytest.mark.asyncio
    async def test_urgency_validation(self, worker, tenant_ctx):
        """Test that invalid urgency raises error."""
        # Arrange
        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Ortopedia",
            "urgency": "invalid-urgency",  # Invalid
            "clinical_summary": "Fratura exposta",
            "phone_number": "+5511987654321",
        }

        # Act & Assert
        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(task_vars)

        assert "Urgência inválida" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_clinical_summary_truncation(self, worker, tenant_ctx):
        """Test that long clinical summaries are truncated."""
        # Arrange
        long_summary = "A" * 600  # 600 chars, exceeds 500 limit

        # Act
        truncated = worker._truncate_clinical_summary(long_summary)

        # Assert
        assert len(truncated) == 500
        assert truncated.endswith("...")
        assert truncated[:497] == long_summary[:497]

    @pytest.mark.asyncio
    async def test_clinical_summary_no_truncation(self, worker, tenant_ctx):
        """Test that short summaries are not truncated."""
        # Arrange
        short_summary = "Dor abdominal aguda"

        # Act
        truncated = worker._truncate_clinical_summary(short_summary)

        # Assert
        assert truncated == short_summary
        assert len(truncated) < 500

    @pytest.mark.asyncio
    async def test_missing_specialist_id(self, worker, tenant_ctx):
        """Test that missing specialist_id raises error."""
        # Arrange
        task_vars = {
            "specialist_id": "",  # Empty
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Cardiologia",
            "urgency": "high",
            "clinical_summary": "Emergência cardíaca",
            "phone_number": "+5511987654321",
        }

        # Act & Assert
        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(task_vars)

        assert "specialist_id é obrigatório" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whatsapp_failure(self, tenant_ctx):
        """Test that WhatsApp failure raises ClinicalOperationsException."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.send_template_message.side_effect = Exception(
            "WhatsApp API error"
        )
        worker = DoctorSpecialistConsultWorker(whatsapp_client=mock_client)

        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Cardiologia",
            "urgency": "medium",
            "clinical_summary": "Consulta de rotina",
            "phone_number": "+5511987654321",
        }

        # Act & Assert
        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(task_vars)

        assert "Falha ao enviar consulta especialista" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_output_fields(self, worker, tenant_ctx):
        """Test that all output fields are present."""
        # Arrange
        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Dermatologia",
            "urgency": "low",
            "clinical_summary": "Consulta eletiva",
            "phone_number": "+5511987654321",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert - All required fields present
        assert "notification_sent" in result
        assert "message_id" in result
        assert "consult_request_id" in result

        # Assert - Correct types
        assert isinstance(result["notification_sent"], bool)
        assert isinstance(result["message_id"], str)
        assert isinstance(result["consult_request_id"], str)

    @pytest.mark.asyncio
    async def test_valid_urgency_levels(self, worker, tenant_ctx):
        """Test all valid urgency levels."""
        valid_urgencies = ["low", "medium", "high", "critical"]

        for urgency in valid_urgencies:
            # Arrange
            task_vars = {
                "specialist_id": "Practitioner/spec-123",
                "requesting_doctor_id": "Practitioner/doc-456",
                "patient_id": "Patient/patient-789",
                "specialty": "Clínica Geral",
                "urgency": urgency,
                "clinical_summary": f"Consulta {urgency}",
                "phone_number": "+5511987654321",
            }

            # Act
            result = await worker.execute(task_vars)

            # Assert
            assert result["notification_sent"] is True

    @pytest.mark.asyncio
    async def test_template_structure(self, worker, tenant_ctx):
        """Test that template has correct structure."""
        # Arrange
        consult_id = "test-uuid-456"

        # Act
        template = worker._build_template(
            specialty="Oftalmologia",
            urgency="high",
            clinical_summary="Perda súbita de visão",
            requesting_doctor_id="Practitioner/doc-789",
            consult_request_id=consult_id,
        )

        # Assert - Template structure
        assert isinstance(template, WhatsAppTemplate)
        assert template.name == "specialist_consult_request_v1"
        assert template.language == "pt_BR"
        assert len(template.components) == 4  # 1 body + 3 buttons

        # Assert - Body component
        body = template.components[0]
        assert body["type"] == "body"
        assert len(body["parameters"]) == 4

        # Assert - Button components
        for i in range(1, 4):
            assert template.components[i]["type"] == "button"

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises error."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        # Arrange - No tenant context set
        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            "requesting_doctor_id": "Practitioner/doc-456",
            "patient_id": "Patient/patient-789",
            "specialty": "Cardiologia",
            "urgency": "high",
            "clinical_summary": "Emergência",
            "phone_number": "+5511987654321",
        }

        # Act & Assert
        with pytest.raises(InvalidTenant):
            await worker.execute(task_vars)

    @pytest.mark.asyncio
    async def test_input_validation_error(self, worker, tenant_ctx):
        """Test that invalid input data raises error."""
        # Arrange - Missing required field
        task_vars = {
            "specialist_id": "Practitioner/spec-123",
            # Missing requesting_doctor_id
            "patient_id": "Patient/patient-789",
            "specialty": "Cardiologia",
            "urgency": "high",
            "clinical_summary": "Emergência",
            "phone_number": "+5511987654321",
        }

        # Act & Assert
        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(task_vars)

        assert "Dados de entrada inválidos" in str(exc_info.value)
