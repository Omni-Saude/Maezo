"""WhatsApp Business API HTTP client."""

import asyncio
from typing import Dict, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager, WhatsAppCredentials
from revenue_cycle.integrations.whatsapp.models import (
    WhatsAppMessageResponse,
    WhatsAppMessageStatus,
    WhatsAppTemplateComponent,
    WhatsAppTemplateParameter,
    WhatsAppTemplateMessage,
    WhatsAppTextMessage,
    WhatsAppTemplateType,
)

logger = structlog.get_logger(__name__)


class WhatsAppClientError(Exception):
    """Base exception for WhatsApp client errors."""

    pass


class WhatsAppRateLimitError(WhatsAppClientError):
    """Rate limit exceeded error."""

    pass


class WhatsAppClient:
    """
    WhatsApp Business API client for patient notifications.

    Integrates with Meta WhatsApp Business API (Graph API v21.0) to send
    template messages and text messages to patients for:
    - Hospitalization notifications
    - Discharge notifications
    - Payment reminders
    - Test results
    - Appointment confirmations

    Rate Limits:
    - Production: 1000 requests/minute
    - Development: 80 requests/hour

    Example:
        manager = TenantCredentialManager(settings)
        await manager.initialize()
        
        client = WhatsAppClient(manager, "tenant-123")
        
        # Send template message
        response = await client.send_template_message(
            to="+5511999887766",
            template_name="internacao_notificacao",
            template_params={
                "patient_name": "João Silva",
                "hospital_name": "Hospital ABC",
                "admission_date": "05/02/2026"
            }
        )
    """

    # Rate limit tracking
    _rate_limit_lock = asyncio.Lock()
    _request_timestamps: list = []
    _rate_limit_window = 60  # seconds
    _max_requests_per_window = 1000  # production limit

    def __init__(
        self,
        credential_manager: TenantCredentialManager,
        tenant_id: str,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize WhatsApp client.

        Args:
            credential_manager: Tenant credential manager (initialized)
            tenant_id: Tenant identifier
            settings: Application settings
        """
        self._credential_manager = credential_manager
        self._tenant_id = tenant_id
        self._settings = settings or get_settings()
        self._base_url = self._settings.integration.whatsapp_api_url
        self._timeout = httpx.Timeout(30.0, connect=5.0)
        self._credentials: Optional[WhatsAppCredentials] = None

    async def _get_credentials(self) -> WhatsAppCredentials:
        """Get WhatsApp credentials from credential manager."""
        if not self._credentials:
            self._credentials = await self._credential_manager.get_whatsapp_token(
                self._tenant_id
            )
        return self._credentials

    def _get_headers(self, access_token: str) -> dict:
        """Get HTTP headers with authentication."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

    def _format_phone_number(self, phone: str) -> str:
        """
        Format phone number for WhatsApp API.

        Ensures phone number has +55 prefix for Brazil.

        Args:
            phone: Phone number (with or without +55)

        Returns:
            Formatted phone number with country code
        """
        # Remove all non-digit characters except +
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")

        # Add +55 if not present
        if not cleaned.startswith("+55"):
            if cleaned.startswith("55"):
                cleaned = "+" + cleaned
            else:
                cleaned = "+55" + cleaned

        return cleaned

    async def _check_rate_limit(self) -> None:
        """
        Check and enforce rate limits.

        Raises:
            WhatsAppRateLimitError: If rate limit exceeded
        """
        async with self._rate_limit_lock:
            import time

            now = time.time()

            # Remove timestamps outside the window
            self._request_timestamps = [
                ts for ts in self._request_timestamps if now - ts < self._rate_limit_window
            ]

            # Check if we're at the limit
            if len(self._request_timestamps) >= self._max_requests_per_window:
                oldest = self._request_timestamps[0]
                wait_time = self._rate_limit_window - (now - oldest)
                logger.warning(
                    "Rate limit reached",
                    tenant_id=self._tenant_id,
                    wait_time=wait_time,
                )
                raise WhatsAppRateLimitError(
                    f"Rate limit exceeded. Try again in {wait_time:.1f} seconds."
                )

            # Add current request
            self._request_timestamps.append(now)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        template_params: dict,
        language_code: str = "pt_BR",
    ) -> WhatsAppMessageResponse:
        """
        Send template message via WhatsApp Business.

        Template messages are pre-approved message templates required by
        WhatsApp for business-initiated conversations.

        Args:
            to: Recipient phone number (will be formatted with +55)
            template_name: Template name (e.g., "internacao_notificacao")
            template_params: Template parameter values
            language_code: Template language code (default: pt_BR)

        Returns:
            Message response with status

        Raises:
            WhatsAppClientError: If message sending fails
            WhatsAppRateLimitError: If rate limit exceeded
        """
        # Check rate limit
        await self._check_rate_limit()

        # Get credentials
        creds = await self._get_credentials()
        phone_number_id = creds.phone_number_id
        access_token = creds.access_token.get_secret_value()

        # Format phone number
        formatted_to = self._format_phone_number(to)

        # Build template parameters
        parameters = [
            WhatsAppTemplateParameter(type="text", text=str(value))
            for value in template_params.values()
        ]

        # Build template message
        message = WhatsAppTemplateMessage(
            to=formatted_to,
            template={
                "name": template_name,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": [p.model_dump(by_alias=True) for p in parameters],
                    }
                ],
            },
        )

        url = f"{self._base_url}/{phone_number_id}/messages"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "Sending WhatsApp template message",
                    tenant_id=self._tenant_id,
                    to=formatted_to,
                    template=template_name,
                )

                response = await client.post(
                    url,
                    json=message.model_dump(by_alias=True, exclude_none=True),
                    headers=self._get_headers(access_token),
                )
                response.raise_for_status()

                data = response.json()

                # Extract message ID from response
                message_id = data.get("messages", [{}])[0].get("id", "unknown")

                result = WhatsAppMessageResponse(
                    messageId=message_id,
                    recipient=formatted_to,
                    status=WhatsAppMessageStatus.SENT,
                )

                logger.info(
                    "WhatsApp template message sent",
                    tenant_id=self._tenant_id,
                    message_id=message_id,
                    to=formatted_to,
                )

                return result

        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            error_message = error_data.get("error", {}).get("message", str(e))
            error_code = error_data.get("error", {}).get("code")

            logger.error(
                "HTTP error sending WhatsApp template message",
                tenant_id=self._tenant_id,
                to=formatted_to,
                template=template_name,
                status_code=e.response.status_code,
                error_code=error_code,
                error=error_message,
            )

            return WhatsAppMessageResponse(
                messageId="failed",
                recipient=formatted_to,
                status=WhatsAppMessageStatus.FAILED,
                errorCode=str(error_code) if error_code else None,
                errorMessage=error_message,
            )

        except httpx.HTTPError as e:
            logger.error(
                "Network error sending WhatsApp template message",
                tenant_id=self._tenant_id,
                to=formatted_to,
                error=str(e),
            )
            raise WhatsAppClientError(f"Network error sending WhatsApp message: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def send_text_message(self, to: str, text: str) -> WhatsAppMessageResponse:
        """
        Send simple text message.

        Note: Text messages can only be sent within 24 hours of user-initiated
        conversation. For business-initiated messages, use send_template_message.

        Args:
            to: Recipient phone number (will be formatted with +55)
            text: Message text (max 4096 characters)

        Returns:
            Message response with status

        Raises:
            WhatsAppClientError: If message sending fails
            WhatsAppRateLimitError: If rate limit exceeded
        """
        # Check rate limit
        await self._check_rate_limit()

        # Get credentials
        creds = await self._get_credentials()
        phone_number_id = creds.phone_number_id
        access_token = creds.access_token.get_secret_value()

        # Format phone number
        formatted_to = self._format_phone_number(to)

        # Build text message
        message = WhatsAppTextMessage(to=formatted_to, text={"body": text})

        url = f"{self._base_url}/{phone_number_id}/messages"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "Sending WhatsApp text message",
                    tenant_id=self._tenant_id,
                    to=formatted_to,
                )

                response = await client.post(
                    url,
                    json=message.model_dump(by_alias=True, exclude_none=True),
                    headers=self._get_headers(access_token),
                )
                response.raise_for_status()

                data = response.json()

                # Extract message ID from response
                message_id = data.get("messages", [{}])[0].get("id", "unknown")

                result = WhatsAppMessageResponse(
                    messageId=message_id,
                    recipient=formatted_to,
                    status=WhatsAppMessageStatus.SENT,
                )

                logger.info(
                    "WhatsApp text message sent",
                    tenant_id=self._tenant_id,
                    message_id=message_id,
                    to=formatted_to,
                )

                return result

        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            error_message = error_data.get("error", {}).get("message", str(e))
            error_code = error_data.get("error", {}).get("code")

            logger.error(
                "HTTP error sending WhatsApp text message",
                tenant_id=self._tenant_id,
                to=formatted_to,
                status_code=e.response.status_code,
                error_code=error_code,
                error=error_message,
            )

            return WhatsAppMessageResponse(
                messageId="failed",
                recipient=formatted_to,
                status=WhatsAppMessageStatus.FAILED,
                errorCode=str(error_code) if error_code else None,
                errorMessage=error_message,
            )

        except httpx.HTTPError as e:
            logger.error(
                "Network error sending WhatsApp text message",
                tenant_id=self._tenant_id,
                to=formatted_to,
                error=str(e),
            )
            raise WhatsAppClientError(f"Network error sending WhatsApp message: {e}") from e
