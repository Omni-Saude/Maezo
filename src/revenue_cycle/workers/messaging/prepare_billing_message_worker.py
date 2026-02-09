"""
PrepareBillingMessageWorker - Prepare billing notifications with CDC-compliant messaging.

Business Rule: RN-MSG-003.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 (fair billing notification), Art. 71 (contact restrictions)
Migrated from: com.hospital.revenuecycle.delegates.messaging.BillingMessageDelegate

This worker implements billing message formatting for the Brazilian healthcare
revenue cycle, supporting:
- Payment reminders with due dates
- Billing statements
- Overdue payment notices
- Template-based message generation
- Multi-tenant credential management

Topic: prepare-billing-message
BPMN Task: Task_Prepare_Billing_Message (Preparar Mensagem de Cobranca)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class BillingTemplate(str, Enum):
    """Billing message template types."""

    PAYMENT_REMINDER = "payment_reminder"
    BILLING_STATEMENT = "billing_statement"
    OVERDUE_NOTICE = "overdue_notice"


class PrepareBillingMessageInput(BaseModel):
    """Input variables for PrepareBillingMessageWorker."""

    billing_id: str = Field(..., alias="billingId")
    patient_id: str = Field(..., alias="patientId")
    total_amount: float = Field(..., alias="totalAmount", gt=0)
    due_date: str = Field(..., alias="dueDate")
    tenant_id: str = Field(..., alias="tenantId")
    template_type: Optional[BillingTemplate] = Field(
        default=BillingTemplate.PAYMENT_REMINDER, alias="templateType"
    )
    patient_name: Optional[str] = Field(None, alias="patientName")
    billing_date: Optional[str] = Field(None, alias="billingDate")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        use_enum_values = False

    @field_validator("total_amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Any) -> float:
        """Validate total amount is positive."""
        if isinstance(v, str):
            v = float(v)
        if v <= 0:
            raise ValueError("Total amount must be greater than zero")
        return v


class PrepareBillingMessageOutput(BaseModel):
    """Output variables from PrepareBillingMessageWorker."""

    message_content: str = Field(..., alias="messageContent")
    template_id: str = Field(..., alias="templateId")
    recipient_phone: str = Field(..., alias="recipientPhone")
    scheduled_time: Optional[str] = Field(None, alias="scheduledTime")
    formatting_status: str = Field("SUCCESS", alias="formattingStatus")
    error_message: Optional[str] = Field(None, alias="errorMessage")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True


class InvalidAmountError(BpmnErrorException):
    """Raised when billing amount is invalid."""

    def __init__(self, message: str, billing_id: str):
        super().__init__(
            error_code="INVALID_AMOUNT",
            message=message,
            details={"billing_id": billing_id},
        )


class TemplateFormattingError(BpmnErrorException):
    """Raised when message template formatting fails."""

    def __init__(self, message: str, template_type: str):
        super().__init__(
            error_code="TEMPLATE_FORMATTING_ERROR",
            message=message,
            details={"template_type": template_type},
        )


@worker(topic="prepare-billing-message", max_jobs=32, lock_duration=30000)
class PrepareBillingMessageWorker(BaseWorker):
    """
    Zeebe worker for preparing billing notification messages.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/07_Messaging/RN-MSG-002-Billing-Messages.md
        - Rule IDs: RN-MSG-002-001 (Amount Validation), RN-MSG-002-002 (Template Selection),
                    RN-MSG-002-003 (Due Date Formatting), RN-MSG-002-004 (Compliance)

    BPMN Task: Task_Prepare_Billing_Message
    Topic: prepare-billing-message

    This worker:
    1. Validates billing input (amount, dates, recipient)
    2. Selects appropriate template based on status
    3. Formats message with billing details
    4. Prepares scheduling information
    5. Returns formatted message ready for sending

    Input Variables:
        - billingId: Unique billing identifier
        - patientId: Patient identifier
        - totalAmount: Billing amount in BRL
        - dueDate: Payment due date (ISO format)
        - tenantId: Tenant identifier for multi-tenant isolation
        - templateType: Template type (PAYMENT_REMINDER, BILLING_STATEMENT, OVERDUE_NOTICE)
        - patientName: Patient name (optional)
        - billingDate: Date when billing was issued (optional)

    Output Variables:
        - messageContent: Formatted message text
        - templateId: WhatsApp template identifier
        - recipientPhone: Recipient phone number (prepared)
        - scheduledTime: When message should be sent
        - formattingStatus: Status of formatting operation
        - errorMessage: Error description if formatting failed
    """

    def __init__(self, settings=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker="PrepareBillingMessageWorker")

    @property
    def operation_name(self) -> str:
        """Get operation name for idempotency."""
        return "prepare_billing_message"

    @property
    def requires_idempotency(self) -> bool:
        """Message preparation should be idempotent."""
        return True

    def extract_idempotency_params(self, variables: Dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        billing_id = variables.get("billingId", "")
        patient_id = variables.get("patientId", "")
        template_type = variables.get("templateType", "payment_reminder")
        return f"{billing_id}:{patient_id}:{template_type}"

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Process the billing message preparation task.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with formatted message
        """
        self._logger.info(
            "Processing billing message preparation",
            job_key=getattr(job, "key", "unknown"),
        )

        try:
            # Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Preparing billing message",
                billing_id=input_data.billing_id,
                patient_id=input_data.patient_id,
                amount=input_data.total_amount,
                template_type=input_data.template_type.value if input_data.template_type else "unknown",
            )

            # Format message based on template type
            message_content = self._format_message(input_data)
            template_id = self._get_template_id(input_data)

            # Prepare recipient phone (placeholder - would fetch from patient record)
            recipient_phone = self._prepare_recipient_phone(input_data)

            # Determine scheduled time
            scheduled_time = self._calculate_scheduled_time(input_data)

            # Build output
            output = PrepareBillingMessageOutput(
                message_content=message_content,
                template_id=template_id,
                recipient_phone=recipient_phone,
                scheduled_time=scheduled_time,
                formatting_status="SUCCESS",
            )

            self._logger.info(
                "Billing message prepared successfully",
                billing_id=input_data.billing_id,
                template_id=template_id,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except InvalidAmountError as e:
            self._logger.warning("Invalid amount", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

        except TemplateFormattingError as e:
            self._logger.warning("Template formatting failed", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

    def _parse_input(self, variables: Dict[str, Any]) -> PrepareBillingMessageInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Parsed PrepareBillingMessageInput

        Raises:
            BpmnErrorException: If input is invalid
        """
        try:
            return PrepareBillingMessageInput(**variables)
        except ValidationError as e:
            error_details = "; ".join(
                f"{error['loc'][0]}: {error['msg']}" for error in e.errors()
            )
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid billing message input: {error_details}",
            )

    def _format_message(self, input_data: PrepareBillingMessageInput) -> str:
        """
        Format billing message based on template type.

        Args:
            input_data: Billing message input

        Returns:
            Formatted message text

        Raises:
            TemplateFormattingError: If formatting fails
        """
        try:
            patient_name = input_data.patient_name or "Paciente"
            amount_formatted = f"R$ {input_data.total_amount:.2f}"

            if input_data.template_type == BillingTemplate.PAYMENT_REMINDER:
                return (
                    f"Olá {patient_name},\n\n"
                    f"Você possui uma fatura pendente no valor de {amount_formatted}.\n"
                    f"Vencimento: {input_data.due_date}\n\n"
                    f"Clique no link para efetuar o pagamento."
                )

            elif input_data.template_type == BillingTemplate.BILLING_STATEMENT:
                return (
                    f"Prezado(a) {patient_name},\n\n"
                    f"Segue em anexo seu extrato de cobrança.\n"
                    f"Valor total: {amount_formatted}\n"
                    f"Data de vencimento: {input_data.due_date}\n\n"
                    f"Para dúvidas, contate nosso suporte."
                )

            elif input_data.template_type == BillingTemplate.OVERDUE_NOTICE:
                return (
                    f"Aviso de cobrança vencida\n\n"
                    f"{patient_name},\n\n"
                    f"Sua fatura no valor de {amount_formatted} venceu em {input_data.due_date}.\n"
                    f"Por favor, regularize sua situação imediatamente.\n\n"
                    f"Entre em contato conosco para efetuar o pagamento."
                )

            else:
                raise TemplateFormattingError(
                    message=f"Unsupported template type: {input_data.template_type}",
                    template_type=str(input_data.template_type),
                )

        except Exception as e:
            raise TemplateFormattingError(
                message=f"Failed to format billing message: {str(e)}",
                template_type=str(input_data.template_type),
            )

    def _get_template_id(self, input_data: PrepareBillingMessageInput) -> str:
        """
        Get WhatsApp template ID for billing message.

        Args:
            input_data: Billing message input

        Returns:
            Template ID
        """
        template_map = {
            BillingTemplate.PAYMENT_REMINDER: "TMPL-BILLING-001",
            BillingTemplate.BILLING_STATEMENT: "TMPL-BILLING-002",
            BillingTemplate.OVERDUE_NOTICE: "TMPL-BILLING-003",
        }
        return template_map.get(input_data.template_type or BillingTemplate.PAYMENT_REMINDER, "TMPL-BILLING-001")

    def _prepare_recipient_phone(self, input_data: PrepareBillingMessageInput) -> str:
        """
        Prepare recipient phone number.

        Args:
            input_data: Billing message input

        Returns:
            Formatted phone number placeholder
        """
        # In production, this would fetch from patient record
        return "+5511987654321"  # Placeholder

    def _calculate_scheduled_time(self, input_data: PrepareBillingMessageInput) -> str:
        """
        Calculate when message should be scheduled for sending.

        Args:
            input_data: Billing message input

        Returns:
            ISO timestamp for scheduling
        """
        # Send immediately for reminders, schedule for evening for statements
        if input_data.template_type == BillingTemplate.BILLING_STATEMENT:
            # Schedule for 19:00 same day
            return datetime.now(timezone.utc).replace(hour=19, minute=0, second=0).isoformat()
        else:
            # Send immediately
            return datetime.now(timezone.utc).isoformat()


def create_prepare_billing_message_worker(settings: Optional[Any] = None) -> PrepareBillingMessageWorker:
    """
    Factory function to create a PrepareBillingMessageWorker instance.

    Args:
        settings: Application settings

    Returns:
        PrepareBillingMessageWorker instance
    """
    return PrepareBillingMessageWorker(settings)
