"""
ProcessPaymentWorker - Zeebe worker for processing payments through payment gateways.

This worker implements payment processing logic for the Brazilian healthcare revenue cycle:
- Payment method validation (PIX, Boleto, Credit Card, Bank Transfer)
- Payment gateway integration (authorization, processing)
- Credit card authorization with PCI-DSS compliance
- PIX instant payment validation
- Boleto generation/validation
- Multi-tenant payment gateway credentials
- Payment status tracking (AUTHORIZED, DECLINED, PENDING, ERROR)

This handles the PROCESSING logic (gateway interaction) while RecordPaymentWorker
handles the RECORDING logic (accounting integration).

Business Rule: RN-BIL-005-ProcessPayment.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00, PCI-DSS, BC 3040 (PIX)
Migrated from: com.hospital.revenuecycle.delegates.ProcessPaymentDelegate

Section references:
- Payment gateway integration and authorization
- Payment method validation and processing
- PCI-DSS compliance for card processing
- PIX and Boleto payment handling
- Payment status state tracking

Topic: process-payment
BPMN Task: Task_Process_Payment (Processar Pagamento)
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.payment.payment_gateway_models import (
    ProcessPaymentInput,
    ProcessPaymentOutput,
    PaymentProcessingStatus,
    PaymentMethod,
    CreditCardDetails,
    PIXDetails,
    BoletoDetails,
    PaymentGatewayResponse,
)

logger = structlog.get_logger(__name__)

# Payment validation constants
MIN_PAYMENT_AMOUNT = Decimal("0.01")
MAX_PAYMENT_AMOUNT = Decimal("1000000.00")  # 1M BRL limit
PIX_KEY_PATTERNS = {
    "CPF": re.compile(r"^\d{11}$"),
    "CNPJ": re.compile(r"^\d{14}$"),
    "EMAIL": re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
    "PHONE": re.compile(r"^\+?55\d{10,11}$"),
    "RANDOM": re.compile(r"^[a-f0-9-]{32,36}$"),
}


class PaymentProcessingError(BpmnErrorException):
    """Raised when payment processing fails due to business rules."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PAYMENT_PROCESSING_ERROR",
            message=message,
            details=details,
        )


class InvalidPaymentMethodError(BpmnErrorException):
    """Raised when payment method validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="INVALID_PAYMENT_METHOD",
            message=message,
            details=details,
        )


class PaymentGatewayError(BpmnErrorException):
    """Raised when payment gateway integration fails."""

    def __init__(self, message: str, gateway_code: Optional[str] = None):
        super().__init__(
            error_code="PAYMENT_GATEWAY_ERROR",
            message=message,
            details={"gateway_code": gateway_code} if gateway_code else None,
        )


class InvalidPaymentDataError(BpmnErrorException):
    """Raised when payment data validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="INVALID_PAYMENT_DATA",
            message=message,
            details=details,
        )


class PaymentTimeoutError(BpmnErrorException):
    """Raised when payment gateway times out."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PAYMENT_TIMEOUT",
            message=message,
            details=details,
        )


class PCIComplianceError(BpmnErrorException):
    """Raised when PCI-DSS compliance check fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PCI_COMPLIANCE_ERROR",
            message=message,
            details=details,
        )


@worker(topic="process-payment", max_jobs=16, lock_duration=60000)
class ProcessPaymentWorker(BaseWorker):
    """
    Zeebe worker for processing payments through payment gateways.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/02_Payment_Processing/RN-PAY-002-Process-Payment.md
        - Rule IDs: RN-PAY-002-001 (Payment Method Validation), RN-PAY-002-002 (Gateway Integration),
                    RN-PAY-002-003 (PCI-DSS Compliance)
        - Regulatory: PCI-DSS (Card Security), PIX Resolution (Central Bank Brazil),
                      FEBRABAN (Boleto Standards), TISS
        - Security: Card tokenization, No sensitive data logging, Multi-tenant credentials

    BPMN Task: Task_Process_Payment
    Topic: process-payment

    This worker:
    1. Validates payment request data
    2. Validates payment method-specific details (card, PIX, boleto)
    3. Processes payment through appropriate gateway
    4. Handles authorization for credit cards
    5. Validates PIX instant payments
    6. Generates/validates boletos
    7. Returns processing status and transaction details

    Input Variables:
        - paymentRequest: Payment details object (optional - will extract from other vars)
        - claimId: Associated claim ID (required)
        - patientId: Patient identifier (required)
        - paymentAmount: Amount to process (required, Decimal)
        - paymentMethod: PIX/BOLETO/CREDIT_CARD/BANK_TRANSFER (required)
        - cardDetails: Credit card details (for CREDIT_CARD - tokenized)
        - pixKey: PIX key (for PIX payments)
        - boletoCode: Boleto code (for BOLETO validation)
        - tenantId: Tenant identifier (for multi-tenant gateway credentials)

    Output Variables:
        - paymentProcessed: Whether successfully processed (boolean)
        - transactionId: Payment gateway transaction reference
        - authorizationCode: Authorization code (for credit cards)
        - paymentStatus: AUTHORIZED/DECLINED/PENDING/ERROR
        - errorCode: Gateway error code (if failed)
        - errorMessage: Human-readable error message (if failed)
        - processingDate: When payment was processed
        - boletoUrl: Boleto PDF URL (for BOLETO generation)
        - pixQrCode: PIX QR code (for PIX payments)

    Security:
        - Card data is assumed to be tokenized (PCI-DSS compliance)
        - No sensitive card data is logged
        - Multi-tenant gateway credentials via TenantContext
        - All payment amounts use Decimal for precision

    Example:
        Input (Credit Card):
        {
            "claimId": "CLM-2026-001",
            "patientId": "PAT-12345",
            "paymentAmount": "150.00",
            "paymentMethod": "CREDIT_CARD",
            "cardDetails": {
                "cardToken": "tok_xxxxxxxxxx",
                "cardBrand": "VISA",
                "lastFourDigits": "4242",
                "holderName": "John Doe",
                "installments": 1
            }
        }

        Output (Successful):
        {
            "paymentProcessed": true,
            "transactionId": "TXN-20260204-ABC123",
            "authorizationCode": "AUTH-456789",
            "paymentStatus": "AUTHORIZED",
            "processingDate": "2026-02-04T10:30:00Z"
        }
    """

    def __init__(
        self,
        settings=None,
        payment_gateway=None,
        payment_service=None,
        **kwargs
    ):
        """
        Initialize the worker with payment gateway clients.

        Args:
            settings: Optional worker settings
            payment_gateway: Optional payment gateway (for testing)
            payment_service: Optional payment service (for testing)
        """
        super().__init__(settings=settings)
        # In production, these would be actual gateway clients
        self._gateway_clients: dict[str, Any] = {}
        self._processed_transactions: dict[str, ProcessPaymentOutput] = {}
        # Store optional services for testing
        self._payment_gateway = payment_gateway
        self._payment_service = payment_service

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "process_payment"

    @property
    def requires_idempotency(self) -> bool:
        """This worker requires idempotency to prevent duplicate charges."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract payment identifiers for idempotency key generation.

        Uses claimId + patientId + paymentAmount + timestamp to detect duplicates.
        """
        claim_id = variables.get("claimId", "")
        patient_id = variables.get("patientId", "")
        amount = variables.get("paymentAmount", "")
        # Include payment method to allow different payment attempts
        method = variables.get("paymentMethod", "")
        return f"{claim_id}:{patient_id}:{amount}:{method}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the payment through the payment gateway.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with payment processing outcome

        Raises:
            PaymentProcessingError: If payment processing fails
            InvalidPaymentMethodError: If payment method validation fails
            PaymentGatewayError: If gateway integration fails
        """
        self._logger.info(
            "Processing payment",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
            patient_id=variables.get("patientId"),
            payment_method=variables.get("paymentMethod"),
        )

        try:
            # Parse and validate input
            input_data = ProcessPaymentInput.model_validate(variables)

            # Validate payment amount
            self._validate_payment_amount(input_data.payment_amount)

            # Validate payment method-specific details
            await self._validate_payment_method_details(input_data)

            # Process payment through gateway
            gateway_response = await self._process_through_gateway(input_data)

            # Create output based on gateway response
            output = ProcessPaymentOutput(
                paymentProcessed=gateway_response.success,
                transactionId=gateway_response.transaction_id,
                authorizationCode=gateway_response.authorization_code,
                paymentStatus=gateway_response.status,
                errorCode=gateway_response.error_code,
                errorMessage=gateway_response.error_message,
                processingDate=datetime.utcnow(),
                boletoUrl=gateway_response.boleto_url,
                pixQrCode=gateway_response.pix_qr_code,
                pixExpirationDate=gateway_response.pix_expiration_date,
                gatewayRawResponse=gateway_response.raw_response,
            )

            # Store for idempotency
            cache_key = f"{input_data.claim_id}:{input_data.patient_id}"
            self._processed_transactions[cache_key] = output

            if output.paymentProcessed:
                self._logger.info(
                    "Payment processed successfully",
                    claim_id=input_data.claim_id,
                    patient_id=input_data.patient_id,
                    transaction_id=output.transactionId,
                    status=output.paymentStatus.value,
                    amount=str(input_data.payment_amount),
                )
            else:
                self._logger.warning(
                    "Payment processing failed",
                    claim_id=input_data.claim_id,
                    patient_id=input_data.patient_id,
                    status=output.paymentStatus.value,
                    error_code=output.errorCode,
                    error_message=output.errorMessage,
                )

            # Return result based on status
            if output.paymentStatus in (
                PaymentProcessingStatus.AUTHORIZED,
                PaymentProcessingStatus.PENDING,
            ):
                return WorkerResult.ok(output.model_dump(by_alias=True))
            elif output.paymentStatus == PaymentProcessingStatus.DECLINED:
                # Declined is a business error, not a technical failure
                return WorkerResult.bpmn_error(
                    error_code="PAYMENT_DECLINED",
                    error_message=output.errorMessage or "Payment was declined by gateway",
                    variables=output.model_dump(by_alias=True),
                )
            else:
                # Processing error - allow retry
                return WorkerResult.failure(
                    error_message=output.errorMessage or "Payment processing error",
                    retry=True,
                )

        except ValidationError as e:
            self._logger.error(
                "Payment validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_PAYMENT_DATA",
                error_message=f"Payment validation failed: {e}",
            )

        except (
            PaymentProcessingError,
            InvalidPaymentMethodError,
            PaymentGatewayError,
        ) as e:
            self._logger.error(
                "Payment processing error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error processing payment",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to process payment: {e}",
                retry=True,
            )

    def _validate_payment_amount(self, amount: Decimal) -> None:
        """
        Validate payment amount is within acceptable range.

        Args:
            amount: Payment amount

        Raises:
            PaymentProcessingError: If amount is invalid
        """
        if amount < MIN_PAYMENT_AMOUNT:
            raise PaymentProcessingError(
                f"Payment amount must be at least R$ {MIN_PAYMENT_AMOUNT}",
                details={"amount": str(amount)},
            )

        if amount > MAX_PAYMENT_AMOUNT:
            raise PaymentProcessingError(
                f"Payment amount cannot exceed R$ {MAX_PAYMENT_AMOUNT}",
                details={"amount": str(amount)},
            )

    async def _validate_payment_method_details(
        self,
        input_data: ProcessPaymentInput,
    ) -> None:
        """
        Validate payment method-specific details.

        Args:
            input_data: Payment input data

        Raises:
            InvalidPaymentMethodError: If validation fails
        """
        method = input_data.payment_method

        if method == PaymentMethod.CREDIT_CARD:
            self._validate_credit_card_details(input_data.card_details)

        elif method == PaymentMethod.PIX:
            self._validate_pix_details(input_data.pix_details)

        elif method == PaymentMethod.BOLETO:
            # Boleto validation happens during generation/lookup
            pass

        elif method == PaymentMethod.BANK_TRANSFER:
            # Bank transfer is typically manual verification
            pass

        else:
            raise InvalidPaymentMethodError(
                f"Unsupported payment method: {method}",
                details={"payment_method": method.value},
            )

    def _validate_credit_card_details(
        self,
        card_details: Optional[CreditCardDetails],
    ) -> None:
        """
        Validate credit card details.

        Assumes card data is tokenized (PCI-DSS compliant).

        Args:
            card_details: Credit card details

        Raises:
            InvalidPaymentMethodError: If validation fails
        """
        if not card_details:
            raise InvalidPaymentMethodError(
                "Credit card details required for CREDIT_CARD payment method"
            )

        # Validate card token exists (actual token validation is gateway-specific)
        if not card_details.card_token or len(card_details.card_token) < 10:
            raise InvalidPaymentMethodError(
                "Invalid card token - card must be tokenized",
                details={"token_length": len(card_details.card_token or "")},
            )

        # Validate installments
        if card_details.installments < 1 or card_details.installments > 12:
            raise InvalidPaymentMethodError(
                "Installments must be between 1 and 12",
                details={"installments": card_details.installments},
            )

        # Validate last 4 digits format
        if card_details.last_four_digits:
            if not card_details.last_four_digits.isdigit() or len(
                card_details.last_four_digits
            ) != 4:
                raise InvalidPaymentMethodError(
                    "Last four digits must be 4 numeric digits",
                    details={"last_four": card_details.last_four_digits},
                )

        self._logger.info(
            "Credit card details validated",
            card_brand=card_details.card_brand,
            last_four="***" + (card_details.last_four_digits or ""),
            installments=card_details.installments,
        )

    def _validate_pix_details(self, pix_details: Optional[PIXDetails]) -> None:
        """
        Validate PIX payment details.

        Args:
            pix_details: PIX payment details

        Raises:
            InvalidPaymentMethodError: If validation fails
        """
        if not pix_details:
            raise InvalidPaymentMethodError(
                "PIX details required for PIX payment method"
            )

        if not pix_details.pix_key:
            raise InvalidPaymentMethodError("PIX key is required")

        # Validate PIX key format
        pix_key = pix_details.pix_key.strip()
        valid_format = False

        for key_type, pattern in PIX_KEY_PATTERNS.items():
            if pattern.match(pix_key):
                valid_format = True
                self._logger.info(
                    "PIX key validated",
                    key_type=key_type,
                    key_masked=self._mask_pix_key(pix_key),
                )
                break

        if not valid_format:
            raise InvalidPaymentMethodError(
                "Invalid PIX key format. Must be CPF, CNPJ, email, phone, or random key",
                details={"pix_key_length": len(pix_key)},
            )

    def _mask_pix_key(self, pix_key: str) -> str:
        """
        Mask PIX key for logging (privacy protection).

        Args:
            pix_key: PIX key to mask

        Returns:
            Masked PIX key
        """
        if len(pix_key) <= 4:
            return "****"
        return pix_key[:2] + "****" + pix_key[-2:]

    async def _process_through_gateway(
        self,
        input_data: ProcessPaymentInput,
    ) -> PaymentGatewayResponse:
        """
        Process payment through the appropriate payment gateway.

        This is a stub implementation. In production, this would:
        1. Get tenant-specific gateway credentials from TenantContext
        2. Initialize gateway client (Stripe, PagSeguro, Mercado Pago, etc.)
        3. Make actual API calls to process payment
        4. Handle gateway-specific response formats
        5. Implement proper error handling and retries

        Args:
            input_data: Payment input data

        Returns:
            Payment gateway response

        Raises:
            PaymentGatewayError: If gateway integration fails
        """
        method = input_data.payment_method

        try:
            if method == PaymentMethod.CREDIT_CARD:
                return await self._process_credit_card(input_data)
            elif method == PaymentMethod.PIX:
                return await self._process_pix(input_data)
            elif method == PaymentMethod.BOLETO:
                return await self._process_boleto(input_data)
            elif method == PaymentMethod.BANK_TRANSFER:
                return await self._process_bank_transfer(input_data)
            else:
                raise PaymentGatewayError(
                    f"Payment method not supported by gateway: {method}"
                )

        except Exception as e:
            if isinstance(e, PaymentGatewayError):
                raise
            raise PaymentGatewayError(
                f"Gateway communication failed: {e}",
                gateway_code="GATEWAY_ERROR",
            )

    async def _process_credit_card(
        self,
        input_data: ProcessPaymentInput,
    ) -> PaymentGatewayResponse:
        """
        Process credit card payment through gateway.

        In production:
        - Use tokenized card data
        - Call gateway API for authorization
        - Handle 3DS authentication if required
        - Return authorization code

        Args:
            input_data: Payment input data

        Returns:
            Payment gateway response
        """
        # TODO: PRODUCTION GATEWAY INTEGRATION REQUIRED
        # This is a stub implementation that always returns success.
        # In production, implement actual payment gateway integration:
        # 1. Get tenant-specific gateway credentials (Stripe, PagSeguro, Mercado Pago)
        # 2. Call gateway API with tokenized card data
        # 3. Handle 3DS authentication if required
        # 4. Handle gateway-specific response formats
        # 5. Implement proper error handling and retries
        # 6. Log transaction details for audit trail

        transaction_id = f"TXN-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
        authorization_code = f"AUTH-{uuid4().hex[:12].upper()}"

        # STUB: Deterministic success response for testing
        # Replace with actual gateway call in production
        self._logger.info(
            "Credit card authorization stub (PRODUCTION: integrate real gateway)",
            transaction_id=transaction_id,
            authorization_code=authorization_code,
            amount=str(input_data.payment_amount),
        )

        return PaymentGatewayResponse(
            success=True,
            transaction_id=transaction_id,
            authorization_code=authorization_code,
            status=PaymentProcessingStatus.AUTHORIZED,
            raw_response={"status": "authorized", "gateway": "stub", "note": "PRODUCTION: Replace with real gateway"},
        )

    async def _process_pix(
        self,
        input_data: ProcessPaymentInput,
    ) -> PaymentGatewayResponse:
        """
        Process PIX payment through gateway.

        In production:
        - Generate PIX QR code via gateway
        - Return QR code data and expiration
        - Set up webhook for payment confirmation

        Args:
            input_data: Payment input data

        Returns:
            Payment gateway response
        """
        transaction_id = f"PIX-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        # Generate mock PIX QR code
        pix_qr_code = self._generate_pix_qr_code(
            transaction_id=transaction_id,
            amount=input_data.payment_amount,
            pix_key=input_data.pix_details.pix_key if input_data.pix_details else "",
        )

        # PIX QR codes typically expire in 30 minutes
        from datetime import timedelta

        expiration = datetime.utcnow() + timedelta(minutes=30)

        self._logger.info(
            "PIX QR code generated",
            transaction_id=transaction_id,
            expiration=expiration.isoformat(),
        )

        return PaymentGatewayResponse(
            success=True,
            transaction_id=transaction_id,
            status=PaymentProcessingStatus.PENDING,
            pix_qr_code=pix_qr_code,
            pix_expiration_date=expiration,
            raw_response={
                "status": "pending",
                "pix_qr_code": pix_qr_code,
                "expiration": expiration.isoformat(),
            },
        )

    async def _process_boleto(
        self,
        input_data: ProcessPaymentInput,
    ) -> PaymentGatewayResponse:
        """
        Process boleto payment through gateway.

        In production:
        - Generate boleto via gateway
        - Return boleto PDF URL and barcode
        - Set up webhook for payment confirmation

        Args:
            input_data: Payment input data

        Returns:
            Payment gateway response
        """
        transaction_id = f"BOL-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        # Generate mock boleto URL
        boleto_url = f"https://gateway.example.com/boletos/{transaction_id}.pdf"

        # Generate mock boleto barcode
        boleto_code = self._generate_boleto_code(transaction_id)

        self._logger.info(
            "Boleto generated",
            transaction_id=transaction_id,
            boleto_url=boleto_url,
        )

        return PaymentGatewayResponse(
            success=True,
            transaction_id=transaction_id,
            status=PaymentProcessingStatus.PENDING,
            boleto_url=boleto_url,
            raw_response={
                "status": "pending",
                "boleto_url": boleto_url,
                "boleto_code": boleto_code,
            },
        )

    async def _process_bank_transfer(
        self,
        input_data: ProcessPaymentInput,
    ) -> PaymentGatewayResponse:
        """
        Process bank transfer payment.

        Bank transfers are typically manual and require verification.

        Args:
            input_data: Payment input data

        Returns:
            Payment gateway response
        """
        transaction_id = f"TED-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        self._logger.info(
            "Bank transfer initiated",
            transaction_id=transaction_id,
        )

        return PaymentGatewayResponse(
            success=True,
            transaction_id=transaction_id,
            status=PaymentProcessingStatus.PENDING,
            raw_response={
                "status": "pending_verification",
                "message": "Bank transfer requires manual verification",
            },
        )

    def _generate_pix_qr_code(
        self,
        transaction_id: str,
        amount: Decimal,
        pix_key: str,
    ) -> str:
        """
        Generate PIX QR code data (EMV format).

        This is a simplified stub. In production, would use proper
        PIX EMV QR code generation library.

        Args:
            transaction_id: Transaction identifier
            amount: Payment amount
            pix_key: PIX key

        Returns:
            PIX QR code string (EMV format)
        """
        # Simplified PIX QR code format (not real EMV)
        qr_data = f"{transaction_id}|{pix_key}|{amount}"
        return hashlib.sha256(qr_data.encode()).hexdigest()

    def _generate_boleto_code(self, transaction_id: str) -> str:
        """
        Generate boleto barcode (simplified).

        In production, would follow FEBRABAN boleto specifications.

        Args:
            transaction_id: Transaction identifier

        Returns:
            Boleto barcode string
        """
        # Simplified boleto code (not real FEBRABAN format)
        # Real format: Bank(3) + Currency(1) + Verification(1) + Expiry(4) + Value(10) + Field(25)
        code_data = f"237{transaction_id}"
        code_hash = hashlib.sha256(code_data.encode()).hexdigest()[:44]
        # Format as boleto barcode (5 groups)
        return f"{code_hash[:5]}.{code_hash[5:10]} {code_hash[10:15]}.{code_hash[15:21]} {code_hash[21:26]}.{code_hash[26:32]} {code_hash[32:33]} {code_hash[33:44]}"

    def _mask_sensitive_data(self, data: dict) -> dict:
        """
        Mask PCI-sensitive fields for logging.

        Args:
            data: Data dictionary to mask

        Returns:
            Dictionary with sensitive fields masked
        """
        masked_data = data.copy()

        # Mask card number if present
        if "cardNumber" in masked_data:
            masked_data["cardNumber"] = self._mask_card_number(masked_data["cardNumber"])

        # Mask CVV if present
        if "cvv" in masked_data:
            masked_data["cvv"] = "***"

        # Mask card token if present (show last 8 chars)
        if "cardToken" in masked_data and masked_data["cardToken"]:
            token = masked_data["cardToken"]
            if len(token) > 8:
                masked_data["cardToken"] = "****" + token[-8:]

        return masked_data

    def _mask_card_number(self, card_number: str) -> str:
        """
        Mask card number for PCI compliance.

        Args:
            card_number: Card number to mask

        Returns:
            Masked card number in format ****-****-****-1234
        """
        if not card_number or len(card_number) < 4:
            return "****"
        return f"****-****-****-{card_number[-4:]}"

    def _tokenize_card(self, card_data: dict) -> str:
        """
        Generate a token for card data.

        In production, this would call a payment gateway tokenization API.

        Args:
            card_data: Card data to tokenize

        Returns:
            Card token string
        """
        # Generate deterministic token for testing
        card_number = card_data.get("cardNumber", "")
        card_hash = hashlib.sha256(card_number.encode()).hexdigest()[:16]
        return f"tok_{card_hash}"

    def _select_gateway(self, payment_method: str) -> str:
        """
        Select payment gateway based on payment method.

        Args:
            payment_method: Payment method (CREDIT_CARD, PIX, BOLETO, etc.)

        Returns:
            Gateway name
        """
        gateway_map = {
            "CREDIT_CARD": "stripe",
            "PIX": "mercadopago",
            "BOLETO": "pagseguro",
            "BANK_TRANSFER": "manual",
        }
        return gateway_map.get(payment_method, "default")

    async def _process_with_failover(self, payment_data: dict) -> dict:
        """
        Process payment with failover to secondary gateway.

        Args:
            payment_data: Payment data to process

        Returns:
            Payment processing result
        """
        primary_gateway = self._select_gateway(payment_data.get("paymentMethod", ""))

        try:
            # Try primary gateway
            self._logger.info(
                "Attempting payment with primary gateway",
                gateway=primary_gateway,
            )
            # In production, would call actual gateway API
            return {"success": True, "gateway": primary_gateway}
        except Exception as e:
            # Fallback to secondary gateway
            secondary_gateway = "failover"
            self._logger.warning(
                "Primary gateway failed, using failover",
                primary_gateway=primary_gateway,
                secondary_gateway=secondary_gateway,
                error=str(e),
            )
            # In production, would call secondary gateway API
            return {"success": True, "gateway": secondary_gateway}

    def _validate_amount(self, amount: Decimal) -> bool:
        """
        Validate payment amount is positive and reasonable.

        Args:
            amount: Amount to validate

        Returns:
            True if valid, False otherwise
        """
        if amount <= Decimal("0"):
            return False
        if amount > MAX_PAYMENT_AMOUNT:
            return False
        return True

    def _update_status(self, payment_id: str, status: str) -> None:
        """
        Update payment status in storage.

        Args:
            payment_id: Payment identifier
            status: New status
        """
        self._logger.info(
            "Updating payment status",
            payment_id=payment_id,
            status=status,
        )
        # In production, would update database
        # For now, just log the status change
