"""
Patient Card Generation Worker.

CIB7 External Task Topic: patient.generate_card
BPMN Error Code: PATIENT_ACCESS_ERROR

Generates physical and digital patient identification cards.
Includes QR code with hashed patient reference and MRN.
"""

from __future__ import annotations

import hashlib
import json
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


class PatientCardGenerationInput(BaseModel):
    """Input for patient card generation."""

    patient_id: str = Field(..., description="Patient identifier")
    mrn: str = Field(..., description="Medical Record Number")
    patient_name: str = Field(..., description="Patient full name")
    facility_name: str = Field(..., description="Healthcare facility name")
    facility_cnes_code: str = Field(..., description="CNES code of the facility")


class PatientCardData(BaseModel):
    """Patient card data structure."""

    card_number: str = Field(..., description="Unique card number")
    patient_id_hash: str = Field(..., description="SHA-256 hash of patient ID")
    mrn: str = Field(..., description="Medical Record Number")
    patient_name: str = Field(..., description="Patient full name")
    facility_name: str = Field(..., description="Healthcare facility name")
    facility_cnes_code: str = Field(..., description="CNES code of the facility")
    issue_date: datetime = Field(default_factory=datetime.utcnow, description="Card issue date")
    qr_code_content: str = Field(..., description="QR code data (JSON)")


class PatientCardGenerationOutput(BaseModel):
    """Output from patient card generation."""

    patient_id: str = Field(..., description="Patient identifier")
    card_data: PatientCardData = Field(..., description="Generated card data")
    card_url: str | None = Field(None, description="URL to digital card (if generated)")
    qr_code_url: str | None = Field(None, description="URL to QR code image (if generated)")


class PatientCardGeneratorProtocol(ABC):
    """Protocol for patient card generation."""

    @abstractmethod
    async def generate_card_number(self, patient_id: str, facility_cnes_code: str) -> str:
        """
        Generate unique card number.

        Args:
            patient_id: Patient identifier
            facility_cnes_code: CNES code of facility

        Returns:
            Unique card number
        """
        pass

    @abstractmethod
    async def generate_qr_code_content(
        self, patient_id_hash: str, mrn: str, card_number: str
    ) -> str:
        """
        Generate QR code content (JSON).

        Args:
            patient_id_hash: SHA-256 hash of patient ID
            mrn: Medical Record Number
            card_number: Card number

        Returns:
            QR code content as JSON string
        """
        pass

    @abstractmethod
    async def generate_digital_card(
        self, card_data: PatientCardData
    ) -> tuple[str | None, str | None]:
        """
        Generate digital card and QR code images.

        Args:
            card_data: Card data

        Returns:
            Tuple of (card_url, qr_code_url) - None if not generated
        """
        pass


class StubPatientCardGenerator(PatientCardGeneratorProtocol):
    """Stub implementation of patient card generator for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_coding_004
        # Inputs: {'patient_id': patient_id}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_coding_004', inputs={...})


    def __init__(self):
        self._card_counter = 1
        self._generated_cards: dict[str, PatientCardData] = {}

    async def generate_card_number(self, patient_id: str, facility_cnes_code: str) -> str:
        """Generate unique card number."""
        # Format: CNES-SEQUENCE
        cnes_digits = "".join(filter(str.isdigit, facility_cnes_code))
        card_sequence = str(self._card_counter).zfill(8)
        self._card_counter += 1
        return f"{cnes_digits}-{card_sequence}"

    async def generate_qr_code_content(
        self, patient_id_hash: str, mrn: str, card_number: str
    ) -> str:
        """Generate QR code content."""
        qr_data = {
            "patient_id_hash": patient_id_hash,
            "mrn": mrn,
            "card_number": card_number,
            "version": "1.0",
        }
        return json.dumps(qr_data, sort_keys=True)

    async def generate_digital_card(
        self, card_data: PatientCardData
    ) -> tuple[str | None, str | None]:
        """Generate digital card (stub returns placeholder URLs)."""
        self._generated_cards[card_data.card_number] = card_data

        # In production, this would generate actual images and upload to storage
        card_url = f"https://storage.example.com/cards/{card_data.card_number}.pdf"
        qr_code_url = f"https://storage.example.com/qrcodes/{card_data.card_number}.png"

        return card_url, qr_code_url


class GeneratePatientCardWorker:
    """
    Worker for generating patient identification cards.

    Generates physical and digital patient cards with QR codes.
    QR codes contain hashed patient references for security.
    """

    TOPIC = "patient.generate_card"

    def __init__(self, generator: PatientCardGeneratorProtocol | None = None):
        """
        Initialize the patient card generation worker.

        Args:
            generator: Patient card generator implementation
        """
        self.generator = generator or StubPatientCardGenerator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _hash_patient_id(self, patient_id: str) -> str:
        """
        Hash patient ID using SHA-256.

        Args:
            patient_id: Patient identifier

        Returns:
            SHA-256 hash (hex)
        """
        return hashlib.sha256(patient_id.encode("utf-8")).hexdigest()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute patient card generation.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with card generation results

        Raises:
            PatientAccessException: If generation fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = PatientCardGenerationInput(**task_variables)

            self.logger.info(
                "Generating patient card",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "mrn": input_data.mrn,
                },
            )

            # Hash patient ID for QR code (LGPD compliance)
            patient_id_hash = self._hash_patient_id(input_data.patient_id)

            # Generate card number
            card_number = await self.generator.generate_card_number(
                input_data.patient_id, input_data.facility_cnes_code
            )

            # Generate QR code content
            qr_code_content = await self.generator.generate_qr_code_content(
                patient_id_hash, input_data.mrn, card_number
            )

            # Create card data
            card_data = PatientCardData(
                card_number=card_number,
                patient_id_hash=patient_id_hash,
                mrn=input_data.mrn,
                patient_name=input_data.patient_name,
                facility_name=input_data.facility_name,
                facility_cnes_code=input_data.facility_cnes_code,
                qr_code_content=qr_code_content,
            )

            # Generate digital card
            card_url, qr_code_url = await self.generator.generate_digital_card(card_data)

            output = PatientCardGenerationOutput(
                patient_id=input_data.patient_id,
                card_data=card_data,
                card_url=card_url,
                qr_code_url=qr_code_url,
            )

            self.logger.info(
                "Patient card generated successfully",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "card_number": card_number,
                    "has_digital_card": card_url is not None,
                },
            )

            return output.model_dump(mode="json")

        except Exception as e:
            self.logger.error(
                "Patient card generation failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                _("Falha ao gerar cartão do paciente: {error}").format(error=str(e)),
                details={"tenant_id": tenant_id, "error": str(e)},
            )
