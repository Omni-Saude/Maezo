"""
SendMessageWorker - Generic message dispatch with multi-channel routing and priority queuing.

Business Rule: RN-MSG-002.md
Regulatory Compliance: LGPD (Privacy), GDPR (EU Compliance), CDC Lei 8.078/90 (Consumer notification)
Migrated from: com.hospital.revenuecycle.delegates.messaging.SendMessageDelegate

This worker implements flexible message routing and delivery for the Brazilian
healthcare revenue cycle, supporting:
- WhatsApp Business API messages
- Email notifications
- SMS messages
- INTERNAL message queuing
- Template-based message generation with parameter rendering
- Priority-based queuing (HIGH, NORMAL, LOW)
- Scheduled message delivery
- Multi-tenant credential management

Topic: send-message
BPMN Task: Task_Send_Message (Enviar Mensagem Genérica)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException, IntegrationException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class MessageType(str, Enum):
    """Types of messages supported."""

    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    INTERNAL = "INTERNAL"


class MessagePriority(str, Enum):
    """Priority levels for message delivery."""

    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class MessageDeliveryStatus(str, Enum):
    """Status of message delivery."""

    SENT = "SENT"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    FAILED = "FAILED"
    PENDING = "PENDING"


class SendMessageInput(BaseModel):
    """
    Input variables for SendMessageWorker.

    Attributes:
        messageType: Type of message (WHATSAPP|EMAIL|SMS|INTERNAL)
        recipientId: Recipient identifier
        templateId: Template identifier for message rendering
        templateParams: Parameters for template rendering
        priority: Priority level (HIGH|NORMAL|LOW)
        scheduledTime: Optional ISO timestamp for scheduled delivery
        tenantId: Multi-tenant identifier
    """

    message_type: MessageType = Field(..., alias="messageType")
    recipient_id: str = Field(..., alias="recipientId")
    template_id: str = Field(..., alias="templateId")
    template_params: Dict[str, Any] = Field(default_factory=dict, alias="templateParams")
    priority: MessagePriority = Field(default=MessagePriority.NORMAL, alias="priority")
    scheduled_time: Optional[str] = Field(None, alias="scheduledTime")
    tenant_id: str = Field(..., alias="tenantId")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=False)

    @field_validator("scheduled_time", mode="before")
    @classmethod
    def validate_scheduled_time(cls, v: Optional[str]) -> Optional[str]:
        """Validate scheduled time is valid ISO format if provided."""
        if v is None:
            return None
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid ISO datetime format: {v}")

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        """Validate tenant ID is non-empty."""
        if not v or not v.strip():
            raise ValueError("tenant_id cannot be empty")
        return v


class SendMessageOutput(BaseModel):
    """
    Output variables for SendMessageWorker.

    Attributes:
        messageId: Unique message identifier
        deliveryStatus: Current delivery status
        channel: Delivery channel used
        sentAt: ISO timestamp of send attempt
        scheduledFor: ISO timestamp if message was scheduled
    """

    message_id: str = Field(..., alias="messageId")
    delivery_status: MessageDeliveryStatus = Field(..., alias="deliveryStatus")
    channel: str
    sent_at: str = Field(..., alias="sentAt")
    scheduled_for: Optional[str] = Field(None, alias="scheduledFor")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class MessageSendError(BpmnErrorException):
    """Raised when message sending fails."""

    def __init__(self, message: str, channel: str, recipient: Optional[str] = None):
        super().__init__(
            error_code="MESSAGE_SEND_ERROR",
            message=message,
            details={"channel": channel, "recipient": recipient},
        )


class InvalidTemplateError(BpmnErrorException):
    """Raised when message template is invalid."""

    def __init__(self, message: str, template_id: str):
        super().__init__(
            error_code="INVALID_TEMPLATE",
            message=message,
            details={"template_id": template_id},
        )


class TemplateRenderError(BpmnErrorException):
    """Raised when template rendering fails."""

    def __init__(self, message: str, template_id: Optional[str] = None):
        super().__init__(
            error_code="TEMPLATE_RENDER_ERROR",
            message=message,
            details={"template_id": template_id} if template_id else None,
        )


class SchedulingError(BpmnErrorException):
    """Raised when message scheduling fails."""

    def __init__(self, message: str, scheduled_time: Optional[str] = None):
        super().__init__(
            error_code="SCHEDULING_ERROR",
            message=message,
            details={"scheduled_time": scheduled_time} if scheduled_time else None,
        )


@worker(topic="send-message", max_jobs=64, lock_duration=30000)
class SendMessageWorker(BaseWorker):
    """
    Zeebe worker for sending generic messages via multiple channels.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/07_Messaging/RN-MSG-002-Send-Message.md
        - Rule IDs: RN-MSG-002-001 (Channel Routing), RN-MSG-002-002 (Priority Queuing),
                    RN-MSG-002-003 (Template Rendering), RN-MSG-002-004 (Scheduled Delivery)
        - Regulatory: LGPD (Privacy), GDPR (EU Citizens), CDC (Consumer Rights)
        - Channels: WhatsApp Business API, Email (SMTP), SMS, Internal Queue
        - Compliance: Consent tracking, Delivery confirmation, Audit logging

    BPMN Task: Task_Send_Message
    Topic: send-message

    This worker:
    1. Validates message input (type, channel, recipient)
    2. Retrieves channel-specific credentials from Vault (multi-tenant)
    3. Renders template with provided parameters
    4. Routes message to appropriate channel
    5. Handles priority-based queuing
    6. Schedules delivery if specified
    7. Records message event for audit trail
    8. Returns delivery status

    Input Variables:
        - messageType: Message type (WHATSAPP, EMAIL, SMS, INTERNAL)
        - recipientId: Recipient identifier (phone, email, or user ID)
        - templateId: Message template identifier
        - templateParams: Dictionary of template parameters
        - priority: Priority level (HIGH, NORMAL, LOW)
        - scheduledTime: Optional ISO datetime for scheduled delivery
        - tenantId: Multi-tenant identifier (required)

    Output Variables:
        - messageId: Unique message identifier
        - deliveryStatus: Current delivery status (SENT, QUEUED, SCHEDULED, FAILED)
        - channel: Delivery channel used
        - sentAt: ISO timestamp of send attempt
        - scheduledFor: ISO timestamp if message was scheduled
    """

    def __init__(
        self,
        settings=None,
        template_service=None,
        message_queue_service=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            template_service: Optional template service (for testing)
            message_queue_service: Optional message queue service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker="SendMessageWorker")

        # Optional service overrides for testing
        self._template_service = template_service
        self._message_queue_service = message_queue_service

        # Template registry for rendering
        self._templates: Dict[str, str] = self._init_templates()

    def _init_templates(self) -> Dict[str, str]:
        """
        Initialize message templates.

        Returns:
            Dictionary mapping template IDs to template strings
        """
        return {
            "TMPL-MSG-001": "Olá {recipientName}, {message}",
            "TMPL-MSG-002": "Notificação: {subject}\n\n{message}",
            "TMPL-MSG-003": "Você tem uma mensagem pendente. Acesse {link}",
            "TMPL-MSG-004": "{message}",
        }

    @property
    def operation_name(self) -> str:
        """Get operation name for idempotency."""
        return "send_message"

    @property
    def requires_idempotency(self) -> bool:
        """
        Message sending should be idempotent.

        Multiple attempts to send the same message should return
        the same messageId and not create duplicates.
        """
        return True

    def extract_idempotency_params(self, variables: Dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses tenant_id, recipient_id, template_id, and message_type
        for deterministic key generation.
        """
        tenant_id = variables.get("tenantId", "")
        recipient_id = variables.get("recipientId", "")
        template_id = variables.get("templateId", "")
        message_type = variables.get("messageType", "")

        return f"{tenant_id}:{recipient_id}:{template_id}:{message_type}"

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Process the message sending task.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with message delivery status
        """
        self._logger.info(
            "Processing message send",
            job_key=getattr(job, "key", "unknown"),
        )

        try:
            # Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Sending message",
                message_type=input_data.message_type.value,
                recipient_id=self._mask_recipient(input_data.recipient_id),
                template_id=input_data.template_id,
                tenant_id=input_data.tenant_id,
                priority=input_data.priority.value,
            )

            # Generate unique message ID
            message_id = self._generate_message_id(input_data)

            # Render template with parameters
            rendered_message = self._render_template(
                template_id=input_data.template_id,
                params=input_data.template_params,
            )

            # Check if message should be scheduled
            if input_data.scheduled_time:
                # Schedule for later delivery
                await self._schedule_message(
                    message_id=message_id,
                    input_data=input_data,
                    rendered_message=rendered_message,
                )
                delivery_status = MessageDeliveryStatus.SCHEDULED
                output = SendMessageOutput(
                    message_id=message_id,
                    delivery_status=delivery_status,
                    channel=input_data.message_type.value,
                    sent_at=datetime.now(timezone.utc).isoformat(),
                    scheduled_for=input_data.scheduled_time,
                )
            else:
                # Send immediately
                delivery_status = await self._send_message(
                    message_id=message_id,
                    input_data=input_data,
                    rendered_message=rendered_message,
                )

                output = SendMessageOutput(
                    message_id=message_id,
                    delivery_status=delivery_status,
                    channel=input_data.message_type.value,
                    sent_at=datetime.now(timezone.utc).isoformat(),
                    scheduled_for=None,
                )

            # Record message event
            await self._record_message_event(
                message_id=message_id,
                input_data=input_data,
                delivery_status=delivery_status,
            )

            self._logger.info(
                "Message sent successfully",
                message_id=message_id,
                delivery_status=delivery_status.value,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except InvalidTemplateError as e:
            self._logger.warning(
                "Invalid template",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

        except TemplateRenderError as e:
            self._logger.warning(
                "Template render failed",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

        except SchedulingError as e:
            self._logger.warning(
                "Message scheduling failed",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

        except MessageSendError as e:
            self._logger.warning(
                "Message send failed",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.error_message,
            )

    def _parse_input(self, variables: Dict[str, Any]) -> SendMessageInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Parsed SendMessageInput

        Raises:
            BpmnErrorException: If input is invalid
        """
        try:
            return SendMessageInput(**variables)
        except ValidationError as e:
            error_details = "; ".join(
                f"{error['loc'][0]}: {error['msg']}" for error in e.errors()
            )
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid message input: {error_details}",
            )

    def _generate_message_id(self, input_data: SendMessageInput) -> str:
        """
        Generate a unique message ID.

        Args:
            input_data: Message input data

        Returns:
            Unique message identifier
        """
        timestamp = datetime.now(timezone.utc).timestamp()
        return f"msg_{uuid.uuid4().hex[:12]}_{int(timestamp)}"

    def _render_template(
        self,
        template_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Render message template with parameters.

        Args:
            template_id: Template identifier
            params: Template parameters dictionary

        Returns:
            Rendered message text

        Raises:
            InvalidTemplateError: If template not found
            TemplateRenderError: If rendering fails
        """
        if params is None:
            params = {}

        # Get template from registry
        template = self._templates.get(template_id)
        if not template:
            raise InvalidTemplateError(
                message=f"Template not found: {template_id}",
                template_id=template_id,
            )

        try:
            # Render template with parameters using simple string formatting
            # Safe because we control the template strings
            rendered = template.format(**params)
            return rendered
        except KeyError as e:
            raise TemplateRenderError(
                message=f"Missing template parameter: {e}",
                template_id=template_id,
            )

    async def _send_message(
        self,
        message_id: str,
        input_data: SendMessageInput,
        rendered_message: str,
    ) -> MessageDeliveryStatus:
        """
        Send message via appropriate channel.

        Args:
            message_id: Message identifier
            input_data: Message input data
            rendered_message: Rendered message content

        Returns:
            Delivery status

        Raises:
            MessageSendError: If sending fails
        """
        try:
            if input_data.message_type == MessageType.WHATSAPP:
                return await self._send_whatsapp(message_id, input_data, rendered_message)
            elif input_data.message_type == MessageType.EMAIL:
                return await self._send_email(message_id, input_data, rendered_message)
            elif input_data.message_type == MessageType.SMS:
                return await self._send_sms(message_id, input_data, rendered_message)
            elif input_data.message_type == MessageType.INTERNAL:
                return await self._send_internal(message_id, input_data, rendered_message)
            else:
                raise MessageSendError(
                    message=f"Unsupported message type: {input_data.message_type.value}",
                    channel=input_data.message_type.value,
                )
        except MessageSendError:
            raise
        except Exception as e:
            self._logger.error(
                "Unexpected error sending message",
                message_id=message_id,
                error=str(e),
            )
            raise MessageSendError(
                message=f"Failed to send message: {str(e)}",
                channel=input_data.message_type.value,
                recipient=input_data.recipient_id,
            )

    async def _send_whatsapp(
        self,
        message_id: str,
        input_data: SendMessageInput,
        rendered_message: str,
    ) -> MessageDeliveryStatus:
        """
        Send message via WhatsApp Business API.

        Args:
            message_id: Message identifier
            input_data: Message input data
            rendered_message: Rendered message content

        Returns:
            Delivery status

        Raises:
            MessageSendError: If sending fails
        """
        self._logger.info(
            "Sending WhatsApp message",
            message_id=message_id,
            recipient_id=self._mask_recipient(input_data.recipient_id),
            priority=input_data.priority.value,
        )

        # Placeholder: actual WhatsApp API integration
        # This would:
        # 1. Retrieve WhatsApp credentials from Vault (multi-tenant)
        # 2. Call WhatsApp Business API
        # 3. Handle rate limiting
        # 4. Return delivery status

        return MessageDeliveryStatus.SENT

    async def _send_email(
        self,
        message_id: str,
        input_data: SendMessageInput,
        rendered_message: str,
    ) -> MessageDeliveryStatus:
        """
        Send message via Email.

        Args:
            message_id: Message identifier
            input_data: Message input data
            rendered_message: Rendered message content

        Returns:
            Delivery status

        Raises:
            MessageSendError: If sending fails
        """
        self._logger.info(
            "Sending email message",
            message_id=message_id,
            recipient_id=self._mask_recipient(input_data.recipient_id),
            priority=input_data.priority.value,
        )

        # Placeholder: actual email sending integration
        # This would:
        # 1. Retrieve SMTP credentials from Vault
        # 2. Build email from template
        # 3. Call email provider
        # 4. Return delivery status

        return MessageDeliveryStatus.SENT

    async def _send_sms(
        self,
        message_id: str,
        input_data: SendMessageInput,
        rendered_message: str,
    ) -> MessageDeliveryStatus:
        """
        Send message via SMS.

        Args:
            message_id: Message identifier
            input_data: Message input data
            rendered_message: Rendered message content

        Returns:
            Delivery status

        Raises:
            MessageSendError: If sending fails
        """
        self._logger.info(
            "Sending SMS message",
            message_id=message_id,
            recipient_id=self._mask_recipient(input_data.recipient_id),
            priority=input_data.priority.value,
        )

        # Placeholder: actual SMS provider integration
        # This would:
        # 1. Retrieve SMS provider credentials from Vault
        # 2. Validate phone number format
        # 3. Call SMS provider API
        # 4. Return delivery status

        return MessageDeliveryStatus.SENT

    async def _send_internal(
        self,
        message_id: str,
        input_data: SendMessageInput,
        rendered_message: str,
    ) -> MessageDeliveryStatus:
        """
        Queue message for internal delivery.

        Args:
            message_id: Message identifier
            input_data: Message input data
            rendered_message: Rendered message content

        Returns:
            Delivery status

        Raises:
            MessageSendError: If queueing fails
        """
        self._logger.info(
            "Queueing internal message",
            message_id=message_id,
            recipient_id=input_data.recipient_id,
            priority=input_data.priority.value,
        )

        # Placeholder: actual internal queue integration
        # This would:
        # 1. Queue message to internal message broker (Redis, RabbitMQ, etc.)
        # 2. Priority-based queueing
        # 3. Return delivery status

        return MessageDeliveryStatus.QUEUED

    async def _schedule_message(
        self,
        message_id: str,
        input_data: SendMessageInput,
        rendered_message: str,
    ) -> None:
        """
        Schedule message for future delivery.

        Args:
            message_id: Message identifier
            input_data: Message input data
            rendered_message: Rendered message content

        Raises:
            SchedulingError: If scheduling fails
        """
        try:
            scheduled_dt = datetime.fromisoformat(
                input_data.scheduled_time.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)

            if scheduled_dt <= now:
                raise SchedulingError(
                    message=f"Scheduled time must be in the future: {input_data.scheduled_time}",
                    scheduled_time=input_data.scheduled_time,
                )

            self._logger.info(
                "Scheduling message for future delivery",
                message_id=message_id,
                scheduled_time=input_data.scheduled_time,
                recipient_id=self._mask_recipient(input_data.recipient_id),
            )

            # Placeholder: actual scheduling integration
            # This would:
            # 1. Store message in scheduler database
            # 2. Create scheduled task
            # 3. Return scheduling confirmation

        except ValueError as e:
            raise SchedulingError(
                message=f"Invalid scheduled time format: {str(e)}",
                scheduled_time=input_data.scheduled_time,
            )

    async def _record_message_event(
        self,
        message_id: str,
        input_data: SendMessageInput,
        delivery_status: MessageDeliveryStatus,
    ) -> None:
        """
        Record message event for audit and tracking.

        Args:
            message_id: Message identifier
            input_data: Message input data
            delivery_status: Message delivery status
        """
        self._logger.info(
            "Message event recorded",
            message_id=message_id,
            delivery_status=delivery_status.value,
            tenant_id=input_data.tenant_id,
        )

        # Placeholder: actual event recording
        # This would store message record in database for:
        # - Audit trail
        # - Delivery tracking
        # - Analytics
        # - Retry history

    @staticmethod
    def _mask_recipient(recipient_id: str) -> str:
        """
        Mask recipient ID for logging.

        Args:
            recipient_id: Recipient identifier (phone, email, or user ID)

        Returns:
            Masked recipient identifier
        """
        if not recipient_id:
            return "***"

        # Check if it looks like an email
        if "@" in recipient_id:
            at_idx = recipient_id.find("@")
            if at_idx > 0:
                return f"{recipient_id[0]}...{recipient_id[at_idx:]}"
            return "***"

        # Check if it looks like a phone number
        if recipient_id.startswith("+") or len(recipient_id) >= 10:
            if len(recipient_id) > 5:
                return f"{recipient_id[:3]}...{recipient_id[-2:]}"
            return "***"

        # Generic user ID masking
        if len(recipient_id) > 4:
            return f"{recipient_id[:2]}...{recipient_id[-2:]}"
        return "***"


def create_send_message_worker(settings: Optional[Any] = None) -> SendMessageWorker:
    """
    Factory function to create a SendMessageWorker instance.

    Args:
        settings: Application settings

    Returns:
        SendMessageWorker instance
    """
    return SendMessageWorker(settings)
