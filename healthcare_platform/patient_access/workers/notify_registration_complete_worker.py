"""
Registration Completion Notification Worker.

CIB7 External Task Topic: patient.notify_registration
BPMN Error Code: PATIENT_ACCESS_ERROR

Sends WhatsApp notification in Portuguese about completed patient registration.
Uses WhatsApp template "registro_completo". NEVER logs phone numbers (LGPD).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


class PatientAccessException(DomainException):
    """Exception for patient access domain errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "PATIENT_ACCESS_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, details)
        self.bpmn_error_code = "PATIENT_ACCESS_ERROR"


class RegistrationNotificationInput(BaseModel):
    """Input for registration notification."""

    patient_id: str = Field(..., description="Patient identifier")
    patient_name: str = Field(..., description="Patient full name")
    phone_number: str = Field(..., description="Patient phone number (E.164 format)")
    mrn: str = Field(..., description="Medical Record Number")
    card_number: str = Field(..., description="Patient card number")
    facility_name: str = Field(..., description="Healthcare facility name")
    card_url: str | None = Field(None, description="URL to digital card")


class RegistrationNotificationOutput(BaseModel):
    """Output from registration notification."""

    patient_id: str = Field(..., description="Patient identifier")
    phone_number_hash: str = Field(..., description="SHA-256 hash of phone number")
    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: str | None = Field(None, description="WhatsApp message ID if sent")
    error_message: str | None = Field(None, description="Error message if failed")
    sent_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When notification was sent"
    )


class WhatsAppClientProtocol(ABC):
    """Protocol for WhatsApp integration."""

    @abstractmethod
    async def send_template_message(
        self,
        phone_number: str,
        template_name: str,
        template_params: dict[str, str],
        language: str = "pt_BR",
    ) -> str:
        """
        Send WhatsApp template message.

        Args:
            phone_number: Recipient phone number (E.164 format)
            template_name: Template name
            template_params: Template parameters
            language: Language code (default: pt_BR)

        Returns:
            Message ID

        Raises:
            Exception: If sending fails
        """
        pass


class StubWhatsAppClient(WhatsAppClientProtocol):
    """Stub implementation of WhatsApp client for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_coding_005
        # Inputs: {'registration_id': registration_id, 'phone_number': phone_number}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_coding_005', inputs={...})


    def __init__(self):
        self._sent_messages: list[dict[str, Any]] = []
        self._message_counter = 1

    async def send_template_message(
        self,
        phone_number: str,
        template_name: str,
        template_params: dict[str, str],
        language: str = "pt_BR",
    ) -> str:
        """Send WhatsApp template message (stub)."""
        message_id = f"wamid.{self._message_counter}"
        self._message_counter += 1

        # Store message (with hashed phone number for security)
        phone_hash = hashlib.sha256(phone_number.encode("utf-8")).hexdigest()[:16]
        self._sent_messages.append(
            {
                "message_id": message_id,
                "phone_hash": phone_hash,
                "template_name": template_name,
                "template_params": template_params,
                "language": language,
                "timestamp": datetime.utcnow(),
            }
        )

        return message_id


class RegistrationNotifierProtocol(ABC):
    """Protocol for registration notification."""

    @abstractmethod
    async def send_registration_notification(
        self,
        phone_number: str,
        patient_name: str,
        mrn: str,
        card_number: str,
        facility_name: str,
        card_url: str | None,
    ) -> tuple[bool, str | None, str | None]:
        """
        Send registration completion notification.

        Args:
            phone_number: Patient phone number
            patient_name: Patient full name
            mrn: Medical Record Number
            card_number: Card number
            facility_name: Facility name
            card_url: URL to digital card (optional)

        Returns:
            Tuple of (success, message_id, error_message)
        """
        pass


class StubRegistrationNotifier(RegistrationNotifierProtocol):
    """Stub implementation of registration notifier for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_coding_005
        # Inputs: {'registration_id': registration_id, 'phone_number': phone_number}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_coding_005', inputs={...})


    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None):
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    async def send_registration_notification(
        self,
        phone_number: str,
        patient_name: str,
        mrn: str,
        card_number: str,
        facility_name: str,
        card_url: str | None,
    ) -> tuple[bool, str | None, str | None]:
        """Send registration notification via WhatsApp."""
        try:
            # Prepare template parameters
            template_params = {
                "patient_name": patient_name,
                "mrn": mrn,
                "card_number": card_number,
                "facility_name": facility_name,
            }

            # Add card URL if available
            if card_url:
                template_params["card_url"] = card_url

            # Send WhatsApp message using template "registro_completo"
            message_id = await self.whatsapp_client.send_template_message(
                phone_number=phone_number,
                template_name="registro_completo",
                template_params=template_params,
                language="pt_BR",
            )

            return True, message_id, None

        except Exception as e:
            return False, None, str(e)


class NotifyRegistrationCompleteWorker:
    """
    Worker for sending registration completion notifications.

    Sends WhatsApp notifications to patients in Portuguese upon registration completion.
    Uses template "registro_completo" with MRN, card number, and facility details.
    NEVER logs phone numbers for LGPD compliance - only SHA-256 hashes.
    """

    TOPIC = "patient.notify_registration"

    def __init__(self, notifier: RegistrationNotifierProtocol | None = None):
        """
        Initialize the registration notification worker.

        Args:
            notifier: Registration notifier implementation
        """
        self.notifier = notifier or StubRegistrationNotifier()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _hash_phone_number(self, phone_number: str) -> str:
        """
        Hash phone number using SHA-256.

        Args:
            phone_number: Phone number to hash

        Returns:
            SHA-256 hash (hex)
        """
        return hashlib.sha256(phone_number.encode("utf-8")).hexdigest()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute registration notification.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with notification results

        Raises:
            PatientAccessException: If notification fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = RegistrationNotificationInput(**task_variables)

            # Hash phone number for logging (LGPD compliance)
            phone_hash = self._hash_phone_number(input_data.phone_number)

            self.logger.info(
                "Sending registration notification",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "phone_hash": phone_hash[:16],  # Only log first 16 chars of hash
                },
            )

            # Send notification
            success, message_id, error_message = await self.notifier.send_registration_notification(
                phone_number=input_data.phone_number,
                patient_name=input_data.patient_name,
                mrn=input_data.mrn,
                card_number=input_data.card_number,
                facility_name=input_data.facility_name,
                card_url=input_data.card_url,
            )

            output = RegistrationNotificationOutput(
                patient_id=input_data.patient_id,
                phone_number_hash=phone_hash,
                notification_sent=success,
                message_id=message_id,
                error_message=error_message,
            )

            if success:
                self.logger.info(
                    "Registration notification sent successfully",
                    extra={
                        "tenant_id": tenant_id,
                        "patient_id": input_data.patient_id,
                        "message_id": message_id,
                        "phone_hash": phone_hash[:16],
                    },
                )
            else:
                self.logger.warning(
                    "Registration notification failed",
                    extra={
                        "tenant_id": tenant_id,
                        "patient_id": input_data.patient_id,
                        "phone_hash": phone_hash[:16],
                        "error": error_message,
                    },
                )

                # In production, might retry or send via alternative channel
                raise PatientAccessException(
                    _("Falha ao enviar notificação de registro: {error}").format(
                        error=error_message or "desconhecido"
                    ),
                    details={
                        "tenant_id": tenant_id,
                        "patient_id": input_data.patient_id,
                        "error": error_message,
                    },
                )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "Registration notification failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                _("Falha ao processar notificação de registro: {error}").format(error=str(e)),
                details={"tenant_id": tenant_id, "error": str(e)},
            )
