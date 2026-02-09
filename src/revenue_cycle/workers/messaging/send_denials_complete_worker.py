"""
SendDenialsCompleteWorker - Notify stakeholders of denial resolution completion and outcomes.

Business Rule: RN-MSG-006.md
Regulatory Compliance: LGPD (Privacy), CDC Lei 8.078/90 (Consumer notification of outcomes)
Migrated from: com.hospital.revenuecycle.delegates.messaging.DenialCompleteDelegate

This worker notifies stakeholders when denial resolution process is complete, supporting:
- WhatsApp Business API messages
- Recovery/loss outcome notifications
- Delivery status tracking
- Multi-tenant credential management

Topic: send-denials-complete
BPMN Task: Task_Send_Denials_Complete (Enviar Notificacao de Glosa Resolvida)
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


class ResolutionType(str, Enum):
    """Types of denial resolution."""

    RECOVERED = "RECOVERED"
    LOST = "LOST"
    PARTIAL = "PARTIAL"


class SendDenialsCompleteInput(BaseModel):
    """Input variables for SendDenialsCompleteWorker."""

    denial_id: str = Field(..., alias="denialId")
    resolution: ResolutionType = Field(..., alias="resolution")
    amount: float = Field(default=0.0, alias="amount", ge=0)
    tenant_id: str = Field(..., alias="tenantId")
    claim_id: Optional[str] = Field(None, alias="claimId")
    patient_id: Optional[str] = Field(None, alias="patientId")
    patient_phone: Optional[str] = Field(None, alias="patientPhone")
    patient_name: Optional[str] = Field(None, alias="patientName")
    resolution_date: Optional[str] = Field(None, alias="resolutionDate")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        use_enum_values = False

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Any) -> float:
        """Validate amount."""
        if v is None:
            return 0.0
        if isinstance(v, str):
            v = float(v)
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return v


class SendDenialsCompleteOutput(BaseModel):
    """Output variables from SendDenialsCompleteWorker."""

    notification_sent: bool = Field(..., alias="notificationSent")
    delivery_status: str = Field(..., alias="deliveryStatus")
    message_id: Optional[str] = Field(None, alias="messageId")
    sent_at: Optional[str] = Field(None, alias="sentAt")
    error_message: Optional[str] = Field(None, alias="errorMessage")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True


class DenialNotificationError(BpmnErrorException):
    """Raised when denial notification sending fails."""

    def __init__(self, message: str, denial_id: str):
        super().__init__(
            error_code="DENIAL_NOTIFICATION_ERROR",
            message=message,
            details={"denial_id": denial_id},
        )


@worker(topic="send-denials-complete", max_jobs=32, lock_duration=30000)
class SendDenialsCompleteWorker(BaseWorker):
    """
    Zeebe worker for sending denial resolution completion notifications.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/07_Messaging/RN-MSG-005-Denial-Complete.md
        - Rule IDs: RN-MSG-005-001 (Resolution Validation), RN-MSG-005-002 (Outcome Notification),
                    RN-MSG-005-003 (Amount Reporting)

    BPMN Task: Task_Send_Denials_Complete
    Topic: send-denials-complete

    This worker:
    1. Validates denial resolution input
    2. Prepares notification message based on resolution type
    3. Sends notification via WhatsApp API
    4. Includes recovery amount if applicable
    5. Tracks delivery status

    Input Variables:
        - denialId: Unique denial identifier
        - resolution: Resolution type (RECOVERED, LOST, PARTIAL)
        - amount: Recovered or lost amount
        - tenantId: Tenant identifier
        - claimId: Associated claim identifier (optional)
        - patientId: Patient identifier (optional)
        - patientPhone: Patient phone number (optional)
        - patientName: Patient name (optional)
        - resolutionDate: Date when resolution was finalized (optional)

    Output Variables:
        - notificationSent: Whether notification was sent successfully
        - deliveryStatus: Current delivery status
        - messageId: Unique message identifier
        - sentAt: ISO timestamp of send attempt
        - errorMessage: Error description if sending failed

    BPMN Error Codes:
        - DENIAL_NOTIFICATION_ERROR: WhatsApp API failure
        - INVALID_INPUT: Required input missing or invalid
    """

    def __init__(self, settings=None, whatsapp_client=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            whatsapp_client: Optional WhatsApp client (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker="SendDenialsCompleteWorker")
        self._whatsapp_client = whatsapp_client

    @property
    def operation_name(self) -> str:
        """Get operation name for idempotency."""
        return "send_denials_complete"

    @property
    def requires_idempotency(self) -> bool:
        """Notification sending should be idempotent."""
        return True

    def extract_idempotency_params(self, variables: Dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        denial_id = variables.get("denialId", "")
        resolution = variables.get("resolution", "")
        return f"{denial_id}:{resolution}"

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Process the denial completion notification task.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with notification delivery status
        """
        self._logger.info(
            "Processing denial completion notification",
            job_key=getattr(job, "key", "unknown"),
        )

        try:
            # Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Sending denial completion notification",
                denial_id=input_data.denial_id,
                resolution=input_data.resolution.value,
                amount=input_data.amount,
            )

            # Check if patient phone available
            if not input_data.patient_phone:
                self._logger.warning(
                    "Patient phone not available, skipping notification",
                    denial_id=input_data.denial_id,
                )
                return WorkerResult.ok({
                    "notificationSent": False,
                    "deliveryStatus": "SKIPPED",
                    "errorMessage": "Patient phone number not available",
                })

            # Generate message ID
            message_id = f"msg_{uuid.uuid4().hex[:12]}"

            # Format notification message
            message_content = self._format_message(input_data)

            # Send via WhatsApp (placeholder implementation)
            delivery_status = await self._send_whatsapp_notification(
                message_id=message_id,
                phone=input_data.patient_phone,
                content=message_content,
            )

            # Build output
            output = SendDenialsCompleteOutput(
                notification_sent=delivery_status == "SENT",
                delivery_status=delivery_status,
                message_id=message_id,
                sent_at=datetime.now(timezone.utc).isoformat(),
            )

            self._logger.info(
                "Denial completion notification sent",
                denial_id=input_data.denial_id,
                message_id=message_id,
                status=delivery_status,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except DenialNotificationError as e:
            self._logger.warning("Notification sending failed", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

    def _parse_input(self, variables: Dict[str, Any]) -> SendDenialsCompleteInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Parsed SendDenialsCompleteInput

        Raises:
            BpmnErrorException: If input is invalid
        """
        try:
            return SendDenialsCompleteInput(**variables)
        except ValidationError as e:
            error_details = "; ".join(
                f"{error['loc'][0]}: {error['msg']}" for error in e.errors()
            )
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid denial complete input: {error_details}",
            )

    def _format_message(self, input_data: SendDenialsCompleteInput) -> str:
        """
        Format denial resolution notification message.

        Args:
            input_data: Denial completion input

        Returns:
            Formatted message text
        """
        patient_name = input_data.patient_name or "Paciente"

        if input_data.resolution == ResolutionType.RECOVERED:
            amount_formatted = f"R$ {input_data.amount:.2f}"
            return (
                f"Boa notícia! Sua negação foi recuperada\n\n"
                f"{patient_name},\n\n"
                f"O recurso contra a negação da sua cobrança foi aprovado.\n\n"
                f"Valor recuperado: {amount_formatted}\n\n"
                f"Este valor será creditado em sua conta nos próximos dias úteis."
            )

        elif input_data.resolution == ResolutionType.PARTIAL:
            amount_formatted = f"R$ {input_data.amount:.2f}"
            return (
                f"Resultado Parcial - Recurso de Negação\n\n"
                f"{patient_name},\n\n"
                f"O resultado do seu recurso foi parcialmente aprovado.\n\n"
                f"Valor aprovado: {amount_formatted}\n\n"
                f"Consulte seu portal para mais detalhes sobre a decisão."
            )

        else:  # LOST
            return (
                f"Resultado do Recurso - Negação Mantida\n\n"
                f"{patient_name},\n\n"
                f"Infelizmente, seu recurso contra a negação foi indeferido.\n\n"
                f"A decisão foi mantida. Se desejar, você pode entrar em contato "
                f"com nosso departamento para explorar outras opções."
            )

    async def _send_whatsapp_notification(
        self,
        message_id: str,
        phone: str,
        content: str,
    ) -> str:
        """
        Send notification via WhatsApp.

        Args:
            message_id: Message identifier
            phone: Recipient phone number
            content: Message content

        Returns:
            Delivery status

        Raises:
            DenialNotificationError: If sending fails
        """
        try:
            # Placeholder: actual WhatsApp API integration
            # This would:
            # 1. Retrieve WhatsApp credentials from Vault
            # 2. Call WhatsApp Business API
            # 3. Return delivery status

            self._logger.info(
                "WhatsApp message queued",
                message_id=message_id,
                phone=self._mask_phone(phone),
            )

            # Simulate successful send
            return "SENT"

        except Exception as e:
            self._logger.error(
                "WhatsApp send failed",
                message_id=message_id,
                error=str(e),
            )
            raise DenialNotificationError(
                message=f"Failed to send WhatsApp notification: {str(e)}",
                denial_id="unknown",
            )

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """
        Mask phone number for logging.

        Args:
            phone: Phone number

        Returns:
            Masked phone number
        """
        if not phone or len(phone) < 5:
            return "***"
        # Keep first 3 and last 2 characters
        return f"{phone[:3]}***{phone[-2:]}"


def create_send_denials_complete_worker(settings: Optional[Any] = None) -> SendDenialsCompleteWorker:
    """
    Factory function to create a SendDenialsCompleteWorker instance.

    Args:
        settings: Application settings

    Returns:
        SendDenialsCompleteWorker instance
    """
    return SendDenialsCompleteWorker(settings)
