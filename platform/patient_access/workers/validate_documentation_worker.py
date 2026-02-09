"""
Patient Documentation Validation Worker.

CIB7 External Task Topic: patient.validate_documentation
BPMN Error Code: PATIENT_ACCESS_ERROR

Validates required patient documents including RG, CPF, CNS, and insurance cards.
Checks document expiry dates and returns validation status per document type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


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


class DocumentValidationInput(BaseModel):
    """Input for documentation validation."""

    patient_id: str = Field(..., description="Patient identifier")
    documents: dict[str, Any] = Field(
        ..., description="Documents to validate (type -> data)"
    )


class DocumentValidationResult(BaseModel):
    """Result for a single document validation."""

    document_type: str = Field(..., description="Type of document (RG, CPF, CNS, etc)")
    is_valid: bool = Field(..., description="Whether document is valid")
    reason: str | None = Field(None, description="Reason if invalid")
    expiry_date: date | None = Field(None, description="Document expiry date if applicable")
    days_until_expiry: int | None = Field(
        None, description="Days until expiry (negative if expired)"
    )


class DocumentValidationOutput(BaseModel):
    """Output from documentation validation."""

    patient_id: str = Field(..., description="Patient identifier")
    validation_results: list[DocumentValidationResult] = Field(
        ..., description="Validation results per document"
    )
    all_valid: bool = Field(..., description="Whether all required documents are valid")
    missing_documents: list[str] = Field(
        default_factory=list, description="List of missing required documents"
    )
    expired_documents: list[str] = Field(
        default_factory=list, description="List of expired documents"
    )
    validation_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When validation was performed"
    )


class DocumentationValidatorProtocol(ABC):
    """Protocol for patient documentation validation."""

    @abstractmethod
    async def validate_cpf(self, cpf: str) -> tuple[bool, str | None]:
        """
        Validate CPF (Cadastro de Pessoas Físicas) document.

        Args:
            cpf: CPF number to validate

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        pass

    @abstractmethod
    async def validate_rg(self, rg: str, issuer: str) -> tuple[bool, str | None]:
        """
        Validate RG (Registro Geral) document.

        Args:
            rg: RG number to validate
            issuer: Issuing authority (e.g., "SSP-SP")

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        pass

    @abstractmethod
    async def validate_cns(self, cns: str) -> tuple[bool, str | None]:
        """
        Validate CNS (Cartão Nacional de Saúde) document.

        Args:
            cns: CNS number to validate

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        pass

    @abstractmethod
    async def validate_insurance_card(
        self, card_number: str, expiry_date: date | None
    ) -> tuple[bool, str | None, int | None]:
        """
        Validate insurance card.

        Args:
            card_number: Insurance card number
            expiry_date: Card expiry date if applicable

        Returns:
            Tuple of (is_valid, reason_if_invalid, days_until_expiry)
        """
        pass


class StubDocumentationValidator(DocumentationValidatorProtocol):
    """Stub implementation of documentation validator for testing."""

    async def validate_cpf(self, cpf: str) -> tuple[bool, str | None]:
        """Validate CPF with basic format check."""
        # Remove non-digits
        cpf_digits = "".join(filter(str.isdigit, cpf))

        if len(cpf_digits) != 11:
            return False, _("CPF deve conter 11 dígitos")

        # Check for known invalid patterns
        if cpf_digits == cpf_digits[0] * 11:
            return False, _("CPF inválido - todos os dígitos são iguais")

        return True, None

    async def validate_rg(self, rg: str, issuer: str) -> tuple[bool, str | None]:
        """Validate RG with basic checks."""
        if not rg or len(rg.strip()) < 5:
            return False, _("RG inválido - número muito curto")

        if not issuer or len(issuer.strip()) < 3:
            return False, _("Órgão emissor do RG não informado")

        return True, None

    async def validate_cns(self, cns: str) -> tuple[bool, str | None]:
        """Validate CNS with format check."""
        # Remove non-digits
        cns_digits = "".join(filter(str.isdigit, cns))

        if len(cns_digits) != 15:
            return False, _("CNS deve conter 15 dígitos")

        # CNS starting with 1 or 2 are definitive, 7-9 are provisional
        first_digit = cns_digits[0]
        if first_digit not in ["1", "2", "7", "8", "9"]:
            return False, _("CNS inválido - primeiro dígito deve ser 1, 2, 7, 8 ou 9")

        return True, None

    async def validate_insurance_card(
        self, card_number: str, expiry_date: date | None
    ) -> tuple[bool, str | None, int | None]:
        """Validate insurance card."""
        if not card_number or len(card_number.strip()) < 8:
            return False, _("Número da carteirinha inválido"), None

        if expiry_date:
            today = date.today()
            days_until_expiry = (expiry_date - today).days

            if days_until_expiry < 0:
                return (
                    False,
                    _("Carteirinha vencida há {days} dias").format(days=abs(days_until_expiry)),
                    days_until_expiry,
                )

            if days_until_expiry < 30:
                # Valid but expiring soon - return as valid with warning
                return True, None, days_until_expiry

            return True, None, days_until_expiry

        return True, None, None


class ValidateDocumentationWorker:
    """
    Worker for validating patient documentation.

    Validates required documents including RG, CPF, CNS, and insurance cards.
    Checks document expiry dates and returns detailed validation results.
    """

    TOPIC = "patient.validate_documentation"

    def __init__(self, validator: DocumentationValidatorProtocol | None = None):
        """
        Initialize the documentation validation worker.

        Args:
            validator: Documentation validator implementation
        """
        self.validator = validator or StubDocumentationValidator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute documentation validation.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with validation results

        Raises:
            PatientAccessException: If validation fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = DocumentValidationInput(**task_variables)

            self.logger.info(
                "Validating documentation for patient",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "document_types": list(input_data.documents.keys()),
                },
            )

            validation_results: list[DocumentValidationResult] = []
            required_documents = {"CPF", "RG", "CNS"}
            provided_documents = set(input_data.documents.keys())
            missing_documents = list(required_documents - provided_documents)
            expired_documents = []

            # Validate CPF
            if "CPF" in input_data.documents:
                cpf_data = input_data.documents["CPF"]
                is_valid, reason = await self.validator.validate_cpf(cpf_data.get("number", ""))
                validation_results.append(
                    DocumentValidationResult(
                        document_type="CPF",
                        is_valid=is_valid,
                        reason=reason,
                    )
                )

            # Validate RG
            if "RG" in input_data.documents:
                rg_data = input_data.documents["RG"]
                is_valid, reason = await self.validator.validate_rg(
                    rg_data.get("number", ""), rg_data.get("issuer", "")
                )
                validation_results.append(
                    DocumentValidationResult(
                        document_type="RG",
                        is_valid=is_valid,
                        reason=reason,
                    )
                )

            # Validate CNS
            if "CNS" in input_data.documents:
                cns_data = input_data.documents["CNS"]
                is_valid, reason = await self.validator.validate_cns(cns_data.get("number", ""))
                validation_results.append(
                    DocumentValidationResult(
                        document_type="CNS",
                        is_valid=is_valid,
                        reason=reason,
                    )
                )

            # Validate insurance card if provided
            if "INSURANCE_CARD" in input_data.documents:
                card_data = input_data.documents["INSURANCE_CARD"]
                expiry_str = card_data.get("expiry_date")
                expiry_date = None
                if expiry_str:
                    expiry_date = datetime.fromisoformat(expiry_str).date()

                is_valid, reason, days_until_expiry = await self.validator.validate_insurance_card(
                    card_data.get("number", ""), expiry_date
                )

                validation_results.append(
                    DocumentValidationResult(
                        document_type="INSURANCE_CARD",
                        is_valid=is_valid,
                        reason=reason,
                        expiry_date=expiry_date,
                        days_until_expiry=days_until_expiry,
                    )
                )

                if not is_valid and days_until_expiry is not None and days_until_expiry < 0:
                    expired_documents.append("INSURANCE_CARD")

            # Check if all validations passed
            all_valid = all(result.is_valid for result in validation_results) and not missing_documents

            output = DocumentValidationOutput(
                patient_id=input_data.patient_id,
                validation_results=validation_results,
                all_valid=all_valid,
                missing_documents=missing_documents,
                expired_documents=expired_documents,
            )

            self.logger.info(
                "Documentation validation completed",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "all_valid": all_valid,
                    "missing_count": len(missing_documents),
                    "expired_count": len(expired_documents),
                },
            )

            return output.model_dump(mode="json")

        except Exception as e:
            self.logger.error(
                "Documentation validation failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                _("Falha ao validar documentação do paciente: {error}").format(error=str(e)),
                details={"tenant_id": tenant_id, "error": str(e)},
            )
