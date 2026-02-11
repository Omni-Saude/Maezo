"""
Unit tests for Patient Meal Preference Worker.

Tests meal preference collection via WhatsApp interactive list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.patient_meal_preference_worker import (
    VALID_MEAL_TYPES,
    ClinicalOperationsException,
    PatientMealPreferenceInput,
    PatientMealPreferenceOutput,
    PatientMealPreferenceWorker,
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
    """Set up tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance with stub WhatsApp client."""
    return PatientMealPreferenceWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    """Valid task variables for meal preference collection."""
    return {
        "patient_id": "Patient/12345",
        "phone_number": "+5511999887766",
        "meal_type": "lunch",
        "options": [
            {
                "id": "meal-001",
                "title": "Frango grelhado",
                "description": "Com arroz integral e legumes",
            },
            {
                "id": "meal-002",
                "title": "Peixe assado",
                "description": "Com purê de batata e salada",
            },
            {
                "id": "meal-003",
                "title": "Lasanha vegetariana",
                "description": "Com molho branco e queijo",
            },
        ],
        "dietary_restrictions": ["sem lactose", "pouco sal"],
    }


@pytest.mark.unit
class TestPatientMealPreferenceWorker:
    """Test suite for PatientMealPreferenceWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test successful meal preference collection."""
        result = await worker.execute(valid_task_variables)

        # Verify output structure
        output = PatientMealPreferenceOutput.model_validate(result)
        assert output.notification_sent is True
        assert output.message_id is not None
        assert output.message_id.startswith("stub-msg-")
        assert output.sent_at is not None
        assert output.selection_received is False
        assert output.selected_option is None
        assert output.meal_request_id is not None

        # Verify timestamp is valid ISO 8601
        datetime.fromisoformat(output.sent_at)

    @pytest.mark.asyncio
    async def test_output_has_all_fields(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that output model has all expected fields with correct types."""
        result = await worker.execute(valid_task_variables)

        # Verify all fields present
        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result
        assert "selection_received" in result
        assert "selected_option" in result
        assert "meal_request_id" in result

        # Verify types
        assert isinstance(result["notification_sent"], bool)
        assert isinstance(result["message_id"], str) or result["message_id"] is None
        assert isinstance(result["sent_at"], str)
        assert isinstance(result["selection_received"], bool)
        assert result["selected_option"] is None
        assert isinstance(result["meal_request_id"], str)

    @pytest.mark.asyncio
    async def test_invalid_meal_type(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that invalid meal_type raises ClinicalOperationsException."""
        valid_task_variables["meal_type"] = "snack"

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "Tipo de refeição inválido" in str(exc_info.value)
        assert exc_info.value.code == "CLINICAL_OPERATIONS_ERROR"
        assert "snack" in str(exc_info.value.details)

    @pytest.mark.asyncio
    async def test_valid_meal_types(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test all valid meal types (breakfast, lunch, dinner)."""
        for meal_type in VALID_MEAL_TYPES:
            valid_task_variables["meal_type"] = meal_type
            result = await worker.execute(valid_task_variables)

            output = PatientMealPreferenceOutput.model_validate(result)
            assert output.notification_sent is True
            assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_list_sections_format(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that list sections are formatted correctly for WhatsApp."""
        # Capture template during execution
        captured_template = None

        def mock_send(phone_number: str, template: Any) -> str:
            nonlocal captured_template
            captured_template = template
            return "stub-msg-12345"

        worker._whatsapp_client.send_template_message = mock_send

        await worker.execute(valid_task_variables)

        # Verify template structure
        assert captured_template is not None
        assert captured_template.name == "meal_choice_v1"
        assert captured_template.language == "pt_BR"
        assert len(captured_template.components) == 2

        # Verify body component
        body_component = captured_template.components[0]
        assert body_component["type"] == "body"
        params = body_component["parameters"]
        assert params[0]["text"] == "lunch"
        assert params[1]["text"] == "sem lactose, pouco sal"

        # Verify interactive component
        interactive_component = captured_template.components[1]
        assert interactive_component["type"] == "interactive"
        assert interactive_component["sub_type"] == "list"

        # Verify list sections
        action = interactive_component["parameters"][0]["action"]
        assert action["button"] == "Ver opções"
        sections = action["sections"]
        assert len(sections) == 1
        assert sections[0]["title"] == "Lunch"
        assert len(sections[0]["rows"]) == 3

        # Verify row format
        first_row = sections[0]["rows"][0]
        assert first_row["id"] == "meal-001"
        assert first_row["title"] == "Frango grelhado"
        assert first_row["description"] == "Com arroz integral e legumes"

    @pytest.mark.asyncio
    async def test_no_dietary_restrictions(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test meal preference with no dietary restrictions."""
        valid_task_variables["dietary_restrictions"] = []

        captured_template = None

        def mock_send(phone_number: str, template: Any) -> str:
            nonlocal captured_template
            captured_template = template
            return "stub-msg-12345"

        worker._whatsapp_client.send_template_message = mock_send

        result = await worker.execute(valid_task_variables)

        # Verify dietary info shows "Nenhuma"
        body_params = captured_template.components[0]["parameters"]
        assert body_params[1]["text"] == "Nenhuma"

        output = PatientMealPreferenceOutput.model_validate(result)
        assert output.notification_sent is True

    @pytest.mark.asyncio
    async def test_whatsapp_failure(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that WhatsApp client failure raises ClinicalOperationsException."""
        # Mock WhatsApp client to raise exception
        mock_client = AsyncMock()
        mock_client.send_template_message.side_effect = Exception("WhatsApp API error")
        worker._whatsapp_client = mock_client

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "Falha ao enviar" in str(exc_info.value)
        assert exc_info.value.code == "CLINICAL_OPERATIONS_ERROR"
        assert exc_info.value.bpmn_error_code == "CLINICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_missing_patient_id(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that missing patient_id raises ClinicalOperationsException."""
        del valid_task_variables["patient_id"]

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "inválidos" in str(exc_info.value).lower()
        assert exc_info.value.code == "CLINICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_missing_options(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that missing options raises ClinicalOperationsException."""
        del valid_task_variables["options"]

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "inválidos" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_no_tenant_context(
        self, worker: PatientMealPreferenceWorker, valid_task_variables
    ):
        """Test that missing tenant context raises InvalidTenant."""
        # Ensure no tenant is set
        clear_tenant()

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_meal_request_id_uniqueness(
        self, worker: PatientMealPreferenceWorker, tenant_ctx, valid_task_variables
    ):
        """Test that each request generates unique meal_request_id."""
        result1 = await worker.execute(valid_task_variables)
        result2 = await worker.execute(valid_task_variables)

        output1 = PatientMealPreferenceOutput.model_validate(result1)
        output2 = PatientMealPreferenceOutput.model_validate(result2)

        assert output1.meal_request_id != output2.meal_request_id

    def test_build_list_sections(self, worker: PatientMealPreferenceWorker):
        """Test _build_list_sections helper method."""
        options = [
            {"id": "m1", "title": "Option 1", "description": "Desc 1"},
            {"id": "m2", "title": "Option 2", "description": "Desc 2"},
        ]

        sections = worker._build_list_sections("breakfast", options)

        assert len(sections) == 1
        assert sections[0]["title"] == "Breakfast"
        assert len(sections[0]["rows"]) == 2
        assert sections[0]["rows"][0]["id"] == "m1"
        assert sections[0]["rows"][0]["title"] == "Option 1"
        assert sections[0]["rows"][0]["description"] == "Desc 1"

    def test_input_validation_direct(self):
        """Test input model validation directly."""
        # Valid input
        valid_input = PatientMealPreferenceInput(
            patient_id="Patient/123",
            phone_number="+5511999887766",
            meal_type="dinner",
            options=[{"id": "m1", "title": "Option 1"}],
            dietary_restrictions=["vegetarian"],
        )
        assert valid_input.meal_type == "dinner"

        # Missing required field
        with pytest.raises(ValidationError):
            PatientMealPreferenceInput(
                patient_id="Patient/123",
                phone_number="+5511999887766",
                meal_type="lunch",
            )

    def test_output_to_variables(self):
        """Test output model to_variables method."""
        output = PatientMealPreferenceOutput(
            notification_sent=True,
            message_id="msg-123",
            sent_at="2024-01-15T10:30:00Z",
            selection_received=False,
            selected_option=None,
            meal_request_id="req-456",
        )

        variables = output.to_variables()

        assert variables["notification_sent"] is True
        assert variables["message_id"] == "msg-123"
        assert variables["sent_at"] == "2024-01-15T10:30:00Z"
        assert variables["selection_received"] is False
        assert variables["selected_option"] is None
        assert variables["meal_request_id"] == "req-456"
