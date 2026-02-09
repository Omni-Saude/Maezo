"""WhatsApp Business API data models."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WhatsAppTemplateType(str, Enum):
    """Supported WhatsApp template types."""

    INTERNACAO_NOTIFICACAO = "internacao_notificacao"  # Hospitalization notification
    ALTA_HOSPITALAR = "alta_hospitalar"  # Discharge notification
    COBRANCA_LEMBRETE = "cobranca_lembrete"  # Payment reminder
    RESULTADO_EXAME = "resultado_exame"  # Test results notification
    AGENDAMENTO_CONSULTA = "agendamento_consulta"  # Appointment scheduling
    CONFIRMACAO_PAGAMENTO = "confirmacao_pagamento"  # Payment confirmation


class WhatsAppMessageStatus(str, Enum):
    """WhatsApp message status."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class WhatsAppMessageResponse(BaseModel):
    """WhatsApp message sending response."""

    message_id: str = Field(alias="messageId", description="WhatsApp message ID")
    recipient: str = Field(description="Recipient phone number")
    status: WhatsAppMessageStatus = Field(description="Message status")
    timestamp: Optional[str] = Field(default=None, description="Message timestamp")
    error_code: Optional[str] = Field(
        default=None, alias="errorCode", description="Error code if failed"
    )
    error_message: Optional[str] = Field(
        default=None, alias="errorMessage", description="Error message if failed"
    )

    class Config:
        """Pydantic config."""

        populate_by_name = True


class WhatsAppTemplateParameter(BaseModel):
    """WhatsApp template parameter."""

    type: str = Field(default="text", description="Parameter type")
    text: str = Field(description="Parameter value")


class WhatsAppTemplateComponent(BaseModel):
    """WhatsApp template component."""

    type: str = Field(default="body", description="Component type")
    parameters: List[WhatsAppTemplateParameter] = Field(description="Template parameters")


class WhatsAppTemplateMessage(BaseModel):
    """WhatsApp template message request."""

    messaging_product: str = Field(default="whatsapp", alias="messaging_product")
    recipient_type: str = Field(default="individual", alias="recipient_type")
    to: str = Field(description="Recipient phone number with country code")
    type: str = Field(default="template")
    template: Dict = Field(description="Template definition")

    class Config:
        """Pydantic config."""

        populate_by_name = True


class WhatsAppTextMessage(BaseModel):
    """WhatsApp text message request."""

    messaging_product: str = Field(default="whatsapp", alias="messaging_product")
    recipient_type: str = Field(default="individual", alias="recipient_type")
    to: str = Field(description="Recipient phone number with country code")
    type: str = Field(default="text")
    text: Dict = Field(description="Text message body")

    class Config:
        """Pydantic config."""

        populate_by_name = True
