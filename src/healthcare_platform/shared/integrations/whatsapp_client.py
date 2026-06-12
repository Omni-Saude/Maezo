"""WhatsApp Business API Client for patient notifications.

CRITICAL PRIVACY NOTICE:
- NEVER log phone numbers or message content (LGPD compliance)
- ONLY log message_id and status codes
- All PII redaction handled by platform.shared.observability.logging

Provides:
- WhatsAppClientProtocol (ABC)
- WhatsAppClient (production implementation)
- StubWhatsAppClient (testing)
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Protocol

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

SERVICE_NAME = "whatsapp"

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class WhatsAppTemplate(BaseModel):
    """WhatsApp template message configuration."""

    name: str = Field(..., description="Template name registered in WhatsApp Business")
    language: str = Field(default="pt_BR", description="Template language code")
    components: list[dict] = Field(
        default_factory=list, description="Template component parameters"
    )


class MessageDeliveryStatus(BaseModel):
    """WhatsApp message delivery status."""

    message_id: str
    status: str = Field(
        ...,
        description="sent, delivered, read, failed",
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    error_code: str | None = Field(default=None, description="Error code if failed")
    error_message: str | None = Field(
        default=None, description="Error message if failed"
    )


class WhatsAppMessage(BaseModel):
    """WhatsApp text message."""

    message_id: str
    status: str
    timestamp: str


# ---------------------------------------------------------------------------
# Protocol (ABC)
# ---------------------------------------------------------------------------


class WhatsAppClientProtocol(Protocol):
    """Protocol for WhatsApp Business API client.

    PRIVACY: All implementations MUST NOT log phone numbers or message content.
    """

    @abstractmethod
    async def send_template_message(
        self, phone: str, template: WhatsAppTemplate
    ) -> str:
        """Send template message to phone number.

        Args:
            phone: E.164 format (e.g., +5511999999999)
            template: Template configuration

        Returns:
            message_id for tracking

        Raises:
            ExternalServiceException: API error
        """
        ...

    @abstractmethod
    async def send_text_message(self, phone: str, text: str) -> str:
        """Send plain text message.

        Args:
            phone: E.164 format
            text: Message content (will NOT be logged)

        Returns:
            message_id for tracking

        Raises:
            ExternalServiceException: API error
        """
        ...

    @abstractmethod
    async def get_delivery_status(self, message_id: str) -> MessageDeliveryStatus:
        """Get delivery status for a sent message.

        Args:
            message_id: Message ID from send operation

        Returns:
            Delivery status

        Raises:
            ExternalServiceException: API error
        """
        ...

    @abstractmethod
    async def send_document(
        self, phone: str, document_url: str, caption: str
    ) -> str:
        """Send document (PDF, image, etc.) to phone number.

        Args:
            phone: E.164 format
            document_url: Public URL to document
            caption: Document caption (will NOT be logged)

        Returns:
            message_id for tracking

        Raises:
            ExternalServiceException: API error
        """
        ...


# ---------------------------------------------------------------------------
# Production Client
# ---------------------------------------------------------------------------


class WhatsAppClient(BaseIntegrationClient, WhatsAppClientProtocol):
    """Production WhatsApp Business API client.

    Uses WhatsApp Business Platform (Cloud API).
    Requires phone_number_id and access_token in tenant config.

    PRIVACY GUARANTEE: Does NOT log phone numbers or message content.
    """

    SERVICE_NAME = SERVICE_NAME

    @track_api_call(service=SERVICE_NAME, endpoint="/messages", method="POST")
    async def send_template_message(
        self, phone: str, template: WhatsAppTemplate
    ) -> str:
        """Send template message."""
        tenant = self._get_tenant_context()
        phone_number_id = tenant.metadata.get("whatsapp_phone_number_id")
        access_token = tenant.metadata.get("whatsapp_access_token")

        if not phone_number_id or not access_token:
            raise ExternalServiceException(
                _("Credenciais WhatsApp não configuradas para o tenant"),
                service_name=SERVICE_NAME,
                operation="send_template_message",
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template.name,
                "language": {"code": template.language},
                "components": template.components,
            },
        }

        self._logger.info(
            "Sending template message",
            template_name=template.name,
            tenant_id=tenant.tenant_id,
        )

        resp = await self._request(
            "POST",
            f"/{phone_number_id}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        data = resp.json()
        message_id = data.get("messages", [{}])[0].get("id", "")

        self._logger.info(
            "Template message sent",
            message_id=message_id,
            tenant_id=tenant.tenant_id,
        )
        return message_id

    @track_api_call(service=SERVICE_NAME, endpoint="/messages", method="POST")
    async def send_text_message(self, phone: str, text: str) -> str:
        """Send plain text message."""
        tenant = self._get_tenant_context()
        phone_number_id = tenant.metadata.get("whatsapp_phone_number_id")
        access_token = tenant.metadata.get("whatsapp_access_token")

        if not phone_number_id or not access_token:
            raise ExternalServiceException(
                _("Credenciais WhatsApp não configuradas para o tenant"),
                service_name=SERVICE_NAME,
                operation="send_text_message",
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text},
        }

        # CRITICAL: Never log text content or phone number
        self._logger.info("Sending text message", tenant_id=tenant.tenant_id)

        resp = await self._request(
            "POST",
            f"/{phone_number_id}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        data = resp.json()
        message_id = data.get("messages", [{}])[0].get("id", "")

        self._logger.info(
            "Text message sent",
            message_id=message_id,
            tenant_id=tenant.tenant_id,
        )
        return message_id

    @track_api_call(service=SERVICE_NAME, endpoint="/messages/{id}", method="GET")
    async def get_delivery_status(self, message_id: str) -> MessageDeliveryStatus:
        """Get delivery status."""
        tenant = self._get_tenant_context()
        access_token = tenant.metadata.get("whatsapp_access_token")

        if not access_token:
            raise ExternalServiceException(
                _("Credenciais WhatsApp não configuradas para o tenant"),
                service_name=SERVICE_NAME,
                operation="get_delivery_status",
            )

        self._logger.info("Fetching delivery status", message_id=message_id)

        resp = await self._request(
            "GET",
            f"/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        data = resp.json()
        status = MessageDeliveryStatus(
            message_id=message_id,
            status=data.get("status", "unknown"),
            timestamp=data.get("timestamp", ""),
            error_code=data.get("error", {}).get("code"),
            error_message=data.get("error", {}).get("message"),
        )

        self._logger.info(
            "Delivery status retrieved",
            message_id=message_id,
            status=status.status,
        )
        return status

    @track_api_call(service=SERVICE_NAME, endpoint="/messages", method="POST")
    async def send_document(
        self, phone: str, document_url: str, caption: str
    ) -> str:
        """Send document."""
        tenant = self._get_tenant_context()
        phone_number_id = tenant.metadata.get("whatsapp_phone_number_id")
        access_token = tenant.metadata.get("whatsapp_access_token")

        if not phone_number_id or not access_token:
            raise ExternalServiceException(
                _("Credenciais WhatsApp não configuradas para o tenant"),
                service_name=SERVICE_NAME,
                operation="send_document",
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "document",
            "document": {"link": document_url, "caption": caption},
        }

        # CRITICAL: Never log caption or phone number
        self._logger.info("Sending document", tenant_id=tenant.tenant_id)

        resp = await self._request(
            "POST",
            f"/{phone_number_id}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        data = resp.json()
        message_id = data.get("messages", [{}])[0].get("id", "")

        self._logger.info(
            "Document sent",
            message_id=message_id,
            tenant_id=tenant.tenant_id,
        )
        return message_id


# ---------------------------------------------------------------------------
# Stub Client (Testing)
# ---------------------------------------------------------------------------


class StubWhatsAppClient(WhatsAppClientProtocol):
    """Stub WhatsApp client for testing.

    Returns deterministic message IDs without making API calls.
    """

    def __init__(self) -> None:
        self._counter = 0
        self._logger = get_logger(f"integration.{SERVICE_NAME}.stub")

    async def send_template_message(
        self, phone: str, template: WhatsAppTemplate
    ) -> str:
        self._counter += 1
        message_id = f"stub_template_{self._counter}"
        self._logger.info(
            "Stub: template message",
            message_id=message_id,
            template_name=template.name,
        )
        return message_id

    async def send_text_message(self, phone: str, text: str) -> str:
        self._counter += 1
        message_id = f"stub_text_{self._counter}"
        self._logger.info("Stub: text message", message_id=message_id)
        return message_id

    async def get_delivery_status(self, message_id: str) -> MessageDeliveryStatus:
        self._logger.info("Stub: delivery status", message_id=message_id)
        return MessageDeliveryStatus(
            message_id=message_id,
            status="delivered",
            timestamp="2025-01-01T00:00:00Z",
        )

    async def send_document(
        self, phone: str, document_url: str, caption: str
    ) -> str:
        self._counter += 1
        message_id = f"stub_document_{self._counter}"
        self._logger.info("Stub: document", message_id=message_id)
        return message_id
