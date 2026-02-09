"""
Pydantic models for payment gateway processing.

These models provide type-safe validation for payment processing through
payment gateways (credit card, PIX, boleto, bank transfer).

Follows PCI-DSS requirements (tokenized card data only, no sensitive data in logs).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from revenue_cycle.workers.payment.models import PaymentMethod


class PaymentProcessingStatus(str, Enum):
    """
    Status of payment processing through gateway.

    Attributes:
        AUTHORIZED: Payment authorized and captured
        DECLINED: Payment declined by gateway/issuer
        PENDING: Payment pending confirmation (PIX, boleto)
        ERROR: Processing error occurred
        CANCELLED: Payment cancelled
        REFUNDED: Payment refunded
    """

    AUTHORIZED = "AUTHORIZED"
    DECLINED = "DECLINED"
    PENDING = "PENDING"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class CreditCardBrand(str, Enum):
    """
    Supported credit card brands.

    Attributes:
        VISA: Visa
        MASTERCARD: Mastercard
        AMEX: American Express
        ELO: Elo (Brazilian card brand)
        HIPERCARD: Hipercard (Brazilian card brand)
        DISCOVER: Discover
    """

    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    AMEX = "AMEX"
    ELO = "ELO"
    HIPERCARD = "HIPERCARD"
    DISCOVER = "DISCOVER"


class CreditCardDetails(BaseModel):
    """
    Credit card payment details.

    NOTE: Card data MUST be tokenized for PCI-DSS compliance.
    This model accepts only tokens, not raw card numbers.
    """

    card_token: str = Field(
        ...,
        alias="cardToken",
        min_length=10,
        description="Tokenized card data (PCI-DSS compliant)",
    )
    card_brand: Optional[CreditCardBrand] = Field(
        None,
        alias="cardBrand",
        description="Card brand (VISA, MASTERCARD, etc.)",
    )
    last_four_digits: Optional[str] = Field(
        None,
        alias="lastFourDigits",
        min_length=4,
        max_length=4,
        description="Last 4 digits of card (for display only)",
    )
    holder_name: Optional[str] = Field(
        None,
        alias="holderName",
        max_length=100,
        description="Cardholder name",
    )
    installments: int = Field(
        1,
        ge=1,
        le=12,
        description="Number of installments (1-12)",
    )
    cvv_token: Optional[str] = Field(
        None,
        alias="cvvToken",
        description="Tokenized CVV (optional)",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "cardToken": "tok_1234567890abcdef",
                    "cardBrand": "VISA",
                    "lastFourDigits": "4242",
                    "holderName": "JOAO SILVA",
                    "installments": 1,
                }
            ]
        },
    }


class PIXDetails(BaseModel):
    """
    PIX instant payment details.

    PIX is the Brazilian instant payment system.
    """

    pix_key: str = Field(
        ...,
        alias="pixKey",
        min_length=1,
        max_length=77,  # Max PIX key length
        description="PIX key (CPF, CNPJ, email, phone, or random key)",
    )
    payer_name: Optional[str] = Field(
        None,
        alias="payerName",
        max_length=100,
        description="Payer name",
    )
    payer_document: Optional[str] = Field(
        None,
        alias="payerDocument",
        max_length=14,
        description="Payer CPF/CNPJ",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "pixKey": "12345678901",
                    "payerName": "João Silva",
                    "payerDocument": "12345678901",
                }
            ]
        },
    }


class BoletoDetails(BaseModel):
    """
    Boleto payment details.

    Boleto is a Brazilian payment slip.
    """

    boleto_code: Optional[str] = Field(
        None,
        alias="boletoCode",
        min_length=47,
        max_length=48,
        description="Boleto barcode/digitable line (for validation)",
    )
    payer_name: Optional[str] = Field(
        None,
        alias="payerName",
        max_length=100,
        description="Payer name",
    )
    payer_document: Optional[str] = Field(
        None,
        alias="payerDocument",
        max_length=14,
        description="Payer CPF/CNPJ",
    )
    payer_address: Optional[str] = Field(
        None,
        alias="payerAddress",
        max_length=200,
        description="Payer address (for boleto generation)",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "payerName": "João Silva",
                    "payerDocument": "12345678901",
                    "payerAddress": "Rua Example, 123, São Paulo, SP",
                }
            ]
        },
    }


class ProcessPaymentInput(BaseModel):
    """
    Input model for ProcessPaymentWorker.

    Validates payment processing request with method-specific details.
    """

    # Required fields
    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Associated claim identifier",
    )
    patient_id: str = Field(
        ...,
        alias="patientId",
        min_length=1,
        description="Patient identifier",
    )
    payment_amount: Decimal = Field(
        ...,
        alias="paymentAmount",
        gt=0,
        description="Payment amount to process",
    )
    payment_method: PaymentMethod = Field(
        ...,
        alias="paymentMethod",
        description="Payment method",
    )

    # Method-specific details
    card_details: Optional[CreditCardDetails] = Field(
        None,
        alias="cardDetails",
        description="Credit card details (for CREDIT_CARD method)",
    )
    pix_details: Optional[PIXDetails] = Field(
        None,
        alias="pixDetails",
        description="PIX payment details (for PIX method)",
    )
    boleto_details: Optional[BoletoDetails] = Field(
        None,
        alias="boletoDetails",
        description="Boleto payment details (for BOLETO method)",
    )

    # Optional metadata
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Payment description",
    )
    reference: Optional[str] = Field(
        None,
        max_length=100,
        description="External reference/order ID",
    )
    ip_address: Optional[str] = Field(
        None,
        alias="ipAddress",
        max_length=45,
        description="Payer IP address (for fraud detection)",
    )

    # Multi-tenant support
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier (for gateway credentials)",
    )

    @field_validator("payment_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "claimId": "CLM-2026-001",
                    "patientId": "PAT-12345",
                    "paymentAmount": "150.00",
                    "paymentMethod": "CREDIT_CARD",
                    "cardDetails": {
                        "cardToken": "tok_1234567890abcdef",
                        "cardBrand": "VISA",
                        "lastFourDigits": "4242",
                        "holderName": "JOAO SILVA",
                        "installments": 1,
                    },
                    "description": "Hospital service payment",
                }
            ]
        },
    }


class ProcessPaymentOutput(BaseModel):
    """
    Output model for ProcessPaymentWorker.

    Contains payment processing results and transaction details.
    """

    payment_processed: bool = Field(
        ...,
        alias="paymentProcessed",
        description="Whether payment was successfully processed",
    )
    transaction_id: str = Field(
        ...,
        alias="transactionId",
        description="Payment gateway transaction ID",
    )
    authorization_code: Optional[str] = Field(
        None,
        alias="authorizationCode",
        description="Authorization code (for credit cards)",
    )
    payment_status: PaymentProcessingStatus = Field(
        ...,
        alias="paymentStatus",
        description="Payment processing status",
    )

    # Error details (if failed)
    error_code: Optional[str] = Field(
        None,
        alias="errorCode",
        description="Gateway error code (if failed)",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Human-readable error message (if failed)",
    )

    # Processing metadata
    processing_date: datetime = Field(
        ...,
        alias="processingDate",
        description="When payment was processed",
    )

    # Method-specific outputs
    boleto_url: Optional[str] = Field(
        None,
        alias="boletoUrl",
        description="Boleto PDF URL (for BOLETO method)",
    )
    pix_qr_code: Optional[str] = Field(
        None,
        alias="pixQrCode",
        description="PIX QR code data (for PIX method)",
    )
    pix_expiration_date: Optional[datetime] = Field(
        None,
        alias="pixExpirationDate",
        description="PIX QR code expiration (for PIX method)",
    )

    # Raw gateway response (for debugging)
    gateway_raw_response: Optional[dict[str, Any]] = Field(
        None,
        alias="gatewayRawResponse",
        description="Raw gateway response (for debugging)",
    )

    @field_validator("processing_date", "pix_expiration_date", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # Try ISO format first
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                # Try common formats
                from dateutil import parser

                return parser.parse(v)
        raise ValueError(f"Cannot convert {type(v).__name__} to datetime")

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        },
        "json_schema_extra": {
            "examples": [
                {
                    "paymentProcessed": True,
                    "transactionId": "TXN-20260204-ABC123",
                    "authorizationCode": "AUTH-456789",
                    "paymentStatus": "AUTHORIZED",
                    "processingDate": "2026-02-04T10:30:00Z",
                }
            ]
        },
    }


class PaymentGatewayResponse(BaseModel):
    """
    Internal model for payment gateway responses.

    Used to standardize responses from different payment gateways.
    """

    success: bool
    transaction_id: str
    status: PaymentProcessingStatus
    authorization_code: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    boleto_url: Optional[str] = None
    pix_qr_code: Optional[str] = None
    pix_expiration_date: Optional[datetime] = None
    raw_response: Optional[dict[str, Any]] = None
