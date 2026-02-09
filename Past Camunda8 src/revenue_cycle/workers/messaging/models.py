"""
Pydantic models for messaging workers input/output validation.

These models provide type-safe validation for notification sending and
messaging-related Camunda process variables.

Includes support for WhatsApp, email, and SMS notifications with
Brazilian phone number formatting and template variable handling.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Regex patterns for Brazilian phone numbers and email validation
# =============================================================================
BRAZILIAN_PHONE_PATTERN = re.compile(r"^(?:\+?55)?[\s\-]?(?:\(?[1-9]{2}\)?)?[\s\-]?9?[\s\-]?(\d{4})[\s\-]?(\d{4})$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class NotificationType(str, Enum):
    """
    Types of notifications supported by the messaging system.

    Attributes:
        APPOINTMENT_REMINDER: Reminder for upcoming appointments
        BILLING_ALERT: Billing and payment notifications
        PAYMENT_REMINDER: Payment due reminders
        TEST_RESULTS: Laboratory or diagnostic test results
        DISCHARGE_SUMMARY: Hospital discharge and summary information
        AUTHORIZATION_REQUEST: Prior authorization requests
        DOCUMENT_REQUEST: Request for missing documentation
        GENERAL_NOTIFICATION: General informational messages
    """

    APPOINTMENT_REMINDER = "APPOINTMENT_REMINDER"
    BILLING_ALERT = "BILLING_ALERT"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"
    TEST_RESULTS = "TEST_RESULTS"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    AUTHORIZATION_REQUEST = "AUTHORIZATION_REQUEST"
    DOCUMENT_REQUEST = "DOCUMENT_REQUEST"
    GENERAL_NOTIFICATION = "GENERAL_NOTIFICATION"


class NotificationChannel(str, Enum):
    """
    Channels for delivering notifications.

    Attributes:
        WHATSAPP: WhatsApp Business API
        EMAIL: Email via SMTP
        SMS: Short Message Service
        PUSH: Push notification
    """

    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"


class DeliveryStatus(str, Enum):
    """
    Status of notification delivery.

    Attributes:
        PENDING: Notification created, not yet sent
        QUEUED: Notification queued for delivery
        SENT: Notification sent successfully
        DELIVERED: Notification delivered to recipient
        FAILED: Delivery failed
        BOUNCED: Delivery bounced (email)
        READ: Message read by recipient (WhatsApp)
    """

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    READ = "READ"


class SendNotificationInput(BaseModel):
    """
    Input variables for SendNotificationWorker.

    Attributes:
        notificationType: Type of notification to send
        channel: Delivery channel (WHATSAPP, EMAIL, SMS)
        recipientPhone: Recipient phone number (WhatsApp/SMS)
        recipientEmail: Recipient email address (optional)
        templateId: WhatsApp template ID or email template name
        templateVariables: Dictionary of template parameter values
        patientName: Patient name
        patientId: Patient identifier
        encounterId: Encounter identifier (optional)
        encounterDate: Date of encounter (optional)
        documentId: Document identifier (optional)
        additionalData: Additional context data (optional)
    """

    notification_type: NotificationType = Field(..., alias="notificationType")
    channel: NotificationChannel = NotificationChannel.WHATSAPP
    recipient_phone: Optional[str] = Field(None, alias="recipientPhone")
    recipient_email: Optional[str] = Field(None, alias="recipientEmail")
    template_id: str = Field(..., alias="templateId")
    template_variables: Dict[str, Any] = Field(default_factory=dict, alias="templateVariables")
    patient_name: str = Field(..., alias="patientName")
    patient_id: str = Field(..., alias="patientId")
    encounter_id: Optional[str] = Field(None, alias="encounterId")
    encounter_date: Optional[str] = Field(None, alias="encounterDate")
    document_id: Optional[str] = Field(None, alias="documentId")
    additional_data: Optional[Dict[str, Any]] = Field(None, alias="additionalData")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        use_enum_values = False

    @field_validator("recipient_phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate and normalize Brazilian phone number.

        Args:
            v: Phone number string

        Returns:
            Normalized phone number in +55XXXXXXXXXX format

        Raises:
            ValueError: If phone number is invalid
        """
        if v is None:
            return None

        # Remove common separators
        cleaned = re.sub(r"[\s\-\(\)]", "", v)

        # Check if it matches Brazilian phone pattern
        if not BRAZILIAN_PHONE_PATTERN.match(cleaned):
            raise ValueError(
                f"Invalid Brazilian phone number format: {v}. "
                "Expected format: +55 11 98765-4321 or variations"
            )

        # Ensure +55 prefix
        if not cleaned.startswith("+55"):
            if cleaned.startswith("55"):
                cleaned = "+" + cleaned
            else:
                cleaned = "+55" + cleaned

        return cleaned

    @field_validator("recipient_email", mode="before")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate email address.

        Args:
            v: Email address string

        Returns:
            Email address (lowercased)

        Raises:
            ValueError: If email is invalid
        """
        if v is None:
            return None

        email = v.lower().strip()
        if not EMAIL_PATTERN.match(email):
            raise ValueError(f"Invalid email address format: {v}")

        return email

    @model_validator(mode="after")
    def validate_channels_requirements(self) -> "SendNotificationInput":
        """
        Validate channel-specific requirements.

        Raises:
            ValueError: If required fields for channel are missing
        """
        if self.channel == NotificationChannel.WHATSAPP:
            if not self.recipient_phone:
                raise ValueError("recipient_phone is required for WHATSAPP channel")
        elif self.channel == NotificationChannel.EMAIL:
            if not self.recipient_email:
                raise ValueError("recipient_email is required for EMAIL channel")
        elif self.channel == NotificationChannel.SMS:
            if not self.recipient_phone:
                raise ValueError("recipient_phone is required for SMS channel")

        return self


class SendNotificationOutput(BaseModel):
    """
    Output variables from SendNotificationWorker.

    Attributes:
        notificationSent: Whether notification was sent successfully
        messageId: Unique identifier for the sent message
        channel: Delivery channel used
        deliveryStatus: Current delivery status
        sentAt: Timestamp when notification was sent
        errorMessage: Error message if delivery failed
        errorCode: Error code for failed deliveries
        deliveryAttempts: Number of delivery attempts made
    """

    notification_sent: bool = Field(..., alias="notificationSent")
    message_id: Optional[str] = Field(None, alias="messageId")
    channel: NotificationChannel
    delivery_status: DeliveryStatus = Field(..., alias="deliveryStatus")
    sent_at: Optional[str] = Field(None, alias="sentAt")
    error_message: Optional[str] = Field(None, alias="errorMessage")
    error_code: Optional[str] = Field(None, alias="errorCode")
    delivery_attempts: int = Field(default=1, alias="deliveryAttempts")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        use_enum_values = False

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Override model_dump to handle enum serialization."""
        data = super().model_dump(**kwargs)
        # Ensure enums are converted to their string values for Camunda
        if "channel" in data and isinstance(data["channel"], NotificationChannel):
            data["channel"] = data["channel"].value
        if "delivery_status" in data and isinstance(data["delivery_status"], DeliveryStatus):
            data["delivery_status"] = data["delivery_status"].value
        return data


class WhatsAppCredentials(BaseModel):
    """
    WhatsApp Business API credentials.

    Attributes:
        api_key: WhatsApp Business API key
        phone_number_id: WhatsApp phone number ID
        business_account_id: Business account ID
        api_endpoint: WhatsApp API endpoint URL
        api_version: API version (e.g., v18.0)
    """

    api_key: str
    phone_number_id: str
    business_account_id: str
    api_endpoint: str = "https://graph.instagram.com"
    api_version: str = "v18.0"

    class Config:
        """Pydantic configuration."""

        frozen = True  # Make credentials immutable


class WhatsAppTemplate(BaseModel):
    """
    WhatsApp message template definition.

    Attributes:
        template_id: Template identifier
        template_name: Human-readable template name
        language: Template language code (e.g., pt_BR)
        parameters: List of required parameter names
        example_variables: Example variable values for testing
    """

    template_id: str
    template_name: str
    language: str = "pt_BR"
    parameters: List[str] = Field(default_factory=list)
    example_variables: Dict[str, str] = Field(default_factory=dict)

    class Config:
        """Pydantic configuration."""

        frozen = True


class NotificationEvent(BaseModel):
    """
    Event record for notification tracking.

    Attributes:
        event_type: Type of event (SENT, DELIVERED, FAILED, etc.)
        timestamp: When the event occurred
        message_id: Message identifier
        channel: Delivery channel
        status: Current status
        error_code: Error code if applicable
        details: Additional event details
    """

    event_type: str
    timestamp: str
    message_id: str
    channel: NotificationChannel
    status: DeliveryStatus
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    class Config:
        """Pydantic configuration."""

        use_enum_values = False
