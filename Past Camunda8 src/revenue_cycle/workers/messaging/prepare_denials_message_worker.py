"""
PrepareDenialsMessageWorker - Prepare denial notifications with appeal deadline reminders.

Business Rule: RN-MSG-004.md
Regulatory Compliance: CDC Lei 8.078/90 (Consumer notification rights), Benchmark: Denial Management Compliance
Migrated from: com.hospital.revenuecycle.delegates.messaging.DenialMessageDelegate

This worker implements denial message formatting for the Brazilian healthcare
revenue cycle, supporting:
- Denial notification messages
- Appeal deadline reminders
- Denial reason explanations
- Template-based message generation
- Urgency level indicators

Topic: prepare-denials-message
BPMN Task: Task_Prepare_Denials_Message (Preparar Mensagem de Negacao)
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


class DenialTemplate(str, Enum):
    """Denial message template types."""

    DENIAL_NOTIFICATION = "denial_notification"
    APPEAL_DEADLINE_REMINDER = "appeal_deadline_reminder"


class UrgencyLevel(str, Enum):
    """Urgency level for denial messages."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PrepareDenialsMessageInput(BaseModel):
    """Input variables for PrepareDenialsMessageWorker."""

    denial_id: str = Field(..., alias="denialId")
    claim_id: str = Field(..., alias="claimId")
    denial_reason: str = Field(..., alias="denialReason")
    appeal_deadline: str = Field(..., alias="appealDeadline")
    tenant_id: str = Field(..., alias="tenantId")
    patient_id: Optional[str] = Field(None, alias="patientId")
    patient_name: Optional[str] = Field(None, alias="patientName")
    denial_amount: Optional[float] = Field(None, alias="denialAmount")
    template_type: Optional[DenialTemplate] = Field(
        default=DenialTemplate.DENIAL_NOTIFICATION, alias="templateType"
    )

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        use_enum_values = False

    @field_validator("denial_amount", mode="before")
    @classmethod
    def validate_denial_amount(cls, v: Any) -> Optional[float]:
        """Validate denial amount if provided."""
        if v is None:
            return None
        if isinstance(v, str):
            v = float(v)
        if v < 0:
            raise ValueError("Denial amount cannot be negative")
        return v


class PrepareDenialsMessageOutput(BaseModel):
    """Output variables from PrepareDenialsMessageWorker."""

    message_content: str = Field(..., alias="messageContent")
    template_id: str = Field(..., alias="templateId")
    urgency_level: UrgencyLevel = Field(..., alias="urgencyLevel")
    appeal_days_remaining: int = Field(..., alias="appealDaysRemaining")
    formatting_status: str = Field("SUCCESS", alias="formattingStatus")
    error_message: Optional[str] = Field(None, alias="errorMessage")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True


class InvalidDenialError(BpmnErrorException):
    """Raised when denial data is invalid."""

    def __init__(self, message: str, denial_id: str):
        super().__init__(
            error_code="INVALID_DENIAL",
            message=message,
            details={"denial_id": denial_id},
        )


class DeadlineCalculationError(BpmnErrorException):
    """Raised when deadline calculation fails."""

    def __init__(self, message: str, appeal_deadline: str):
        super().__init__(
            error_code="DEADLINE_CALCULATION_ERROR",
            message=message,
            details={"appeal_deadline": appeal_deadline},
        )


@worker(topic="prepare-denials-message", max_jobs=32, lock_duration=30000)
class PrepareDenialsMessageWorker(BaseWorker):
    """
    Zeebe worker for preparing denial notification messages.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/07_Messaging/RN-MSG-003-Denial-Messages.md
        - Rule IDs: RN-MSG-003-001 (Denial Validation), RN-MSG-003-002 (Template Selection),
                    RN-MSG-003-003 (Deadline Calculation), RN-MSG-003-004 (Urgency)

    BPMN Task: Task_Prepare_Denials_Message
    Topic: prepare-denials-message

    This worker:
    1. Validates denial input (claim, reasons)
    2. Calculates days remaining until appeal deadline
    3. Determines urgency level based on deadline
    4. Formats message with denial details
    5. Returns formatted message with urgency indicators

    Input Variables:
        - denialId: Unique denial identifier
        - claimId: Associated claim identifier
        - denialReason: Reason for denial
        - appealDeadline: Deadline for appeal (ISO format)
        - tenantId: Tenant identifier for multi-tenant isolation
        - patientId: Patient identifier (optional)
        - patientName: Patient name (optional)
        - denialAmount: Amount of denied claim (optional)
        - templateType: Template type (DENIAL_NOTIFICATION, APPEAL_DEADLINE_REMINDER)

    Output Variables:
        - messageContent: Formatted message text
        - templateId: WhatsApp template identifier
        - urgencyLevel: Urgency level (LOW, MEDIUM, HIGH, CRITICAL)
        - appealDaysRemaining: Number of days until deadline
        - formattingStatus: Status of formatting operation
        - errorMessage: Error description if formatting failed

    BPMN Error Codes:
        - INVALID_DENIAL: Invalid denial data
        - DEADLINE_CALCULATION_ERROR: Deadline calculation failed
        - INVALID_INPUT: Required input missing or invalid
    """

    def __init__(self, settings=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker="PrepareDenialsMessageWorker")

    @property
    def operation_name(self) -> str:
        """Get operation name for idempotency."""
        return "prepare_denials_message"

    @property
    def requires_idempotency(self) -> bool:
        """Message preparation should be idempotent."""
        return True

    def extract_idempotency_params(self, variables: Dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        denial_id = variables.get("denialId", "")
        claim_id = variables.get("claimId", "")
        return f"{denial_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Process the denial message preparation task.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with formatted message
        """
        self._logger.info(
            "Processing denial message preparation",
            job_key=getattr(job, "key", "unknown"),
        )

        try:
            # Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Preparing denial message",
                denial_id=input_data.denial_id,
                claim_id=input_data.claim_id,
                reason=input_data.denial_reason,
            )

            # Calculate days remaining until deadline
            appeal_days_remaining = self._calculate_days_remaining(input_data.appeal_deadline)

            # Determine urgency level
            urgency_level = self._determine_urgency_level(appeal_days_remaining)

            # Format message based on template type
            message_content = self._format_message(input_data, appeal_days_remaining)
            template_id = self._get_template_id(input_data)

            # Build output
            output = PrepareDenialsMessageOutput(
                message_content=message_content,
                template_id=template_id,
                urgency_level=urgency_level,
                appeal_days_remaining=appeal_days_remaining,
                formatting_status="SUCCESS",
            )

            self._logger.info(
                "Denial message prepared successfully",
                denial_id=input_data.denial_id,
                urgency_level=urgency_level.value,
                days_remaining=appeal_days_remaining,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except InvalidDenialError as e:
            self._logger.warning("Invalid denial data", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

        except DeadlineCalculationError as e:
            self._logger.warning("Deadline calculation failed", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

    def _parse_input(self, variables: Dict[str, Any]) -> PrepareDenialsMessageInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Parsed PrepareDenialsMessageInput

        Raises:
            BpmnErrorException: If input is invalid
        """
        try:
            return PrepareDenialsMessageInput(**variables)
        except ValidationError as e:
            error_details = "; ".join(
                f"{error['loc'][0]}: {error['msg']}" for error in e.errors()
            )
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid denial message input: {error_details}",
            )

    def _calculate_days_remaining(self, appeal_deadline: str) -> int:
        """
        Calculate days remaining until appeal deadline.

        Args:
            appeal_deadline: Deadline date (ISO format)

        Returns:
            Number of days remaining

        Raises:
            DeadlineCalculationError: If calculation fails
        """
        try:
            deadline_dt = datetime.fromisoformat(appeal_deadline.replace("Z", "+00:00"))
            days_remaining = (deadline_dt.date() - datetime.now(timezone.utc).date()).days
            return max(0, days_remaining)
        except Exception as e:
            raise DeadlineCalculationError(
                message=f"Failed to calculate deadline: {str(e)}",
                appeal_deadline=appeal_deadline,
            )

    def _determine_urgency_level(self, days_remaining: int) -> UrgencyLevel:
        """
        Determine urgency level based on days remaining.

        Args:
            days_remaining: Number of days until deadline

        Returns:
            Urgency level
        """
        if days_remaining <= 0:
            return UrgencyLevel.CRITICAL
        elif days_remaining <= 5:
            return UrgencyLevel.HIGH
        elif days_remaining <= 15:
            return UrgencyLevel.MEDIUM
        else:
            return UrgencyLevel.LOW

    def _format_message(
        self,
        input_data: PrepareDenialsMessageInput,
        appeal_days_remaining: int,
    ) -> str:
        """
        Format denial message based on template type.

        Args:
            input_data: Denial message input
            appeal_days_remaining: Days remaining for appeal

        Returns:
            Formatted message text
        """
        patient_name = input_data.patient_name or "Paciente"

        if input_data.template_type == DenialTemplate.DENIAL_NOTIFICATION:
            return (
                f"Notificação de Negação de Cobrança\n\n"
                f"Prezado(a) {patient_name},\n\n"
                f"Informamos que sua solicitação (Claim ID: {input_data.claim_id}) "
                f"foi negada.\n\n"
                f"Motivo da negação: {input_data.denial_reason}\n\n"
                f"Você tem direito a recorrer dessa decisão até {input_data.appeal_deadline}.\n\n"
                f"Para interpor um recurso, entre em contato com nosso departamento de cobrança."
            )

        elif input_data.template_type == DenialTemplate.APPEAL_DEADLINE_REMINDER:
            return (
                f"AVISO IMPORTANTE - Prazo para Recurso\n\n"
                f"{patient_name},\n\n"
                f"Faltam apenas {appeal_days_remaining} dias para o prazo final "
                f"para recorrer da negação do seu clamo.\n\n"
                f"Data limite: {input_data.appeal_deadline}\n\n"
                f"Não deixe passar esta oportunidade! "
                f"Clique para enviar seu recurso agora mesmo."
            )

        else:
            return (
                f"Mensagem sobre negação de cobrança\n\n"
                f"{patient_name}, sua solicitação foi negada.\n"
                f"Motivo: {input_data.denial_reason}\n"
                f"Prazo para recurso: {input_data.appeal_deadline}"
            )

    def _get_template_id(self, input_data: PrepareDenialsMessageInput) -> str:
        """
        Get WhatsApp template ID for denial message.

        Args:
            input_data: Denial message input

        Returns:
            Template ID
        """
        if input_data.template_type == DenialTemplate.APPEAL_DEADLINE_REMINDER:
            return "TMPL-DENIAL-002"
        return "TMPL-DENIAL-001"


def create_prepare_denials_message_worker(settings: Optional[Any] = None) -> PrepareDenialsMessageWorker:
    """
    Factory function to create a PrepareDenialsMessageWorker instance.

    Args:
        settings: Application settings

    Returns:
        PrepareDenialsMessageWorker instance
    """
    return PrepareDenialsMessageWorker(settings)
