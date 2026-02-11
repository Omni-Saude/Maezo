"""
Tests for Patient Authorization Update Worker

Validates:
- Successful authorization updates for all statuses
- Status-specific next steps and instructions
- Input validation (invalid status, missing fields)
- WhatsApp failures
- Output structure and fields
- Appeal instructions for denials
"""

import pytest

from healthcare_platform.revenue_cycle.workers.patient_authorization_update_worker import (
    PatientAuthorizationUpdateWorker,
    RevenueCycleException,
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
def tenant_ctx():
    """Set up tenant context."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker with stub WhatsApp client."""
    return PatientAuthorizationUpdateWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def base_input():
    """Base authorization update input."""
    return {
        "patient_id": "PAT123456",
        "phone_number": "+5511987654321",
        "authorization_id": "AUTH789012",
        "procedure_name": "Ressonância Magnética",
    }


@pytest.mark.asyncio
async def test_success_approved(tenant_ctx, worker, base_input):
    """Test successful authorization approval notification."""
    input_data = base_input.copy()
    input_data["status"] = "approved"

    result = await worker.execute(input_data)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None
    assert "sent_at" in result
    assert result["sent_at"].endswith("Z") or "+" in result["sent_at"]


@pytest.mark.asyncio
async def test_success_approved_with_default_next_steps(tenant_ctx, base_input):
    """Test approved authorization uses default next steps when not provided."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.last_template = None

        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            self.last_template = template
            return super().send_template_message(phone_number, template)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientAuthorizationUpdateWorker(whatsapp_client=capturing_client)

    input_data = base_input.copy()
    input_data["status"] = "approved"

    await worker.execute(input_data)

    assert capturing_client.last_template is not None
    body_params = capturing_client.last_template.body_params
    assert "Procedimento autorizado" in body_params[2]
    assert "Agende pelo portal" in body_params[2]


@pytest.mark.asyncio
async def test_success_denied(tenant_ctx, worker, base_input):
    """Test successful authorization denial notification."""
    input_data = base_input.copy()
    input_data["status"] = "denied"
    input_data["reason"] = "Falta de documentação"

    result = await worker.execute(input_data)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None


@pytest.mark.asyncio
async def test_success_denied_includes_appeal_instructions(tenant_ctx, base_input):
    """Test denied authorization includes appeal instructions in default next steps."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.last_template = None

        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            self.last_template = template
            return super().send_template_message(phone_number, template)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientAuthorizationUpdateWorker(whatsapp_client=capturing_client)

    input_data = base_input.copy()
    input_data["status"] = "denied"

    await worker.execute(input_data)

    assert capturing_client.last_template is not None
    body_params = capturing_client.last_template.body_params
    next_steps = body_params[2]
    assert "recorrer" in next_steps
    assert "0800" in next_steps or "portal" in next_steps


@pytest.mark.asyncio
async def test_success_pending(tenant_ctx, worker, base_input):
    """Test successful authorization pending notification."""
    input_data = base_input.copy()
    input_data["status"] = "pending"

    result = await worker.execute(input_data)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None


@pytest.mark.asyncio
async def test_success_pending_includes_estimated_timeframe(tenant_ctx, base_input):
    """Test pending authorization includes estimated analysis timeframe."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.last_template = None

        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            self.last_template = template
            return super().send_template_message(phone_number, template)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientAuthorizationUpdateWorker(whatsapp_client=capturing_client)

    input_data = base_input.copy()
    input_data["status"] = "pending"

    await worker.execute(input_data)

    assert capturing_client.last_template is not None
    body_params = capturing_client.last_template.body_params
    next_steps = body_params[2]
    assert "Aguarde" in next_steps or "análise" in next_steps
    assert "5 dias úteis" in next_steps


@pytest.mark.asyncio
async def test_custom_next_steps_override_default(tenant_ctx, worker, base_input):
    """Test custom next_steps override default instructions."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.last_template = None

        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            self.last_template = template
            return super().send_template_message(phone_number, template)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientAuthorizationUpdateWorker(whatsapp_client=capturing_client)

    input_data = base_input.copy()
    input_data["status"] = "approved"
    input_data["next_steps"] = "Custom instructions here"

    await worker.execute(input_data)

    assert capturing_client.last_template is not None
    body_params = capturing_client.last_template.body_params
    assert body_params[2] == "Custom instructions here"


@pytest.mark.asyncio
async def test_invalid_status(tenant_ctx, worker, base_input):
    """Test validation error for invalid status value."""
    input_data = base_input.copy()
    input_data["status"] = "invalid_status"

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(input_data)

    assert "Invalid authorization update input" in str(exc_info.value)
    assert exc_info.value.details is not None
    assert "validation_errors" in exc_info.value.details


@pytest.mark.asyncio
async def test_missing_authorization_id(tenant_ctx, worker, base_input):
    """Test validation error when authorization_id is missing."""
    invalid_input = base_input.copy()
    del invalid_input["authorization_id"]
    invalid_input["status"] = "approved"

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid authorization update input" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_procedure_name(tenant_ctx, worker, base_input):
    """Test validation error when procedure_name is missing."""
    invalid_input = base_input.copy()
    del invalid_input["procedure_name"]
    invalid_input["status"] = "approved"

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid authorization update input" in str(exc_info.value)


@pytest.mark.asyncio
async def test_whatsapp_failure(tenant_ctx, base_input):
    """Test handling of WhatsApp send failure."""

    class FailingWhatsAppClient(StubWhatsAppClient):
        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            raise RuntimeError("WhatsApp API connection failed")

    worker = PatientAuthorizationUpdateWorker(whatsapp_client=FailingWhatsAppClient())

    input_data = base_input.copy()
    input_data["status"] = "approved"

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(input_data)

    assert "Failed to send authorization update" in str(exc_info.value)
    assert exc_info.value.details is not None
    assert "error" in exc_info.value.details


@pytest.mark.asyncio
async def test_output_fields(tenant_ctx, worker, base_input):
    """Test all required output fields are present."""
    input_data = base_input.copy()
    input_data["status"] = "pending"

    result = await worker.execute(input_data)

    required_fields = {"notification_sent", "message_id", "sent_at"}
    assert required_fields.issubset(result.keys())


@pytest.mark.asyncio
async def test_status_label_mapping(tenant_ctx, base_input):
    """Test status labels are correctly mapped to Portuguese."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.captured_templates = []

        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            self.captured_templates.append(template)
            return super().send_template_message(phone_number, template)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientAuthorizationUpdateWorker(whatsapp_client=capturing_client)

    status_mappings = [
        ("approved", "Aprovado"),
        ("denied", "Negado"),
        ("pending", "Em Análise"),
    ]

    for status, expected_label in status_mappings:
        input_data = base_input.copy()
        input_data["status"] = status
        await worker.execute(input_data)

    # Check each captured template
    for i, (status, expected_label) in enumerate(status_mappings):
        template = capturing_client.captured_templates[i]
        assert template.body_params[1] == expected_label


@pytest.mark.asyncio
async def test_missing_phone_number(tenant_ctx, worker, base_input):
    """Test validation error when phone_number is missing."""
    invalid_input = base_input.copy()
    del invalid_input["phone_number"]
    invalid_input["status"] = "approved"

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid authorization update input" in str(exc_info.value)


@pytest.mark.asyncio
async def test_topic_constant(worker):
    """Test worker has correct CIB7 topic."""
    assert worker.TOPIC == "financial.auth_update"


@pytest.mark.asyncio
async def test_template_name_and_language(tenant_ctx, base_input):
    """Test WhatsApp template uses correct name and language code."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.last_template = None

        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            self.last_template = template
            return super().send_template_message(phone_number, template)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientAuthorizationUpdateWorker(whatsapp_client=capturing_client)

    input_data = base_input.copy()
    input_data["status"] = "approved"

    await worker.execute(input_data)

    assert capturing_client.last_template.name == "auth_update_v1"
    assert capturing_client.last_template.language_code == "pt_BR"
