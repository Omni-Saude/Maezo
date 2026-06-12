"""
TISS 4.01 Client for XML Generation and Submission.

This module provides client interfaces and implementations for generating,
validating, and submitting TISS (Troca de Informação em Saúde Suplementar)
guides to insurance payers following the TISS 4.01 standard.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.enums import TISSGuideType
from healthcare_platform.shared.domain.exceptions import (
    TISSException,
    TISSSchemaError,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

SERVICE_NAME = "tiss"

logger = get_logger(__name__)


# ============================================================================
# DTOs
# ============================================================================


class TISSGuideDTO(BaseModel):
    """TISS Guide Data Transfer Object."""

    guide_type: TISSGuideType
    guide_number: str
    payer_id: str
    provider_id: str
    patient_id: str

    # Clinical data
    admission_date: datetime | None = None
    discharge_date: datetime | None = None
    diagnosis_codes: list[str] = Field(default_factory=list)
    procedure_codes: list[str] = Field(default_factory=list)

    # Financial data
    total_amount: float = 0.0
    authorized_amount: float | None = None

    # Additional metadata
    authorization_number: str | None = None
    attending_physician_id: str | None = None
    requested_date: datetime | None = None

    # Line items
    items: list[dict[str, Any]] = Field(default_factory=list)

    class Config:
        """Pydantic config."""
        json_encoders = {datetime: lambda v: v.isoformat()}


class TISSSubmissionResult(BaseModel):
    """Result of a TISS submission."""

    success: bool
    protocol_number: str | None = None
    submission_timestamp: datetime | None = None
    payer_response_code: str | None = None
    payer_response_message: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    processing_errors: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic config."""
        json_encoders = {datetime: lambda v: v.isoformat()}


class TISSBatchDTO(BaseModel):
    """Batch submission of multiple TISS guides."""

    batch_id: str
    payer_id: str
    guides: list[TISSGuideDTO]
    submission_date: datetime | None = None

    class Config:
        """Pydantic config."""
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============================================================================
# Protocol
# ============================================================================


class TISSClientProtocol(ABC):
    """Protocol for TISS client implementations."""

    @abstractmethod
    async def generate_guide_xml(self, guide: TISSGuideDTO) -> str:
        """
        Generate TISS 4.01 compliant XML for a guide.

        Args:
            guide: Guide data to convert to XML

        Returns:
            XML string in TISS 4.01 format

        Raises:
            TISSValidationError: If guide data is invalid
            TISSSchemaError: If XML generation fails
        """
        ...

    @abstractmethod
    async def validate_guide(self, guide: TISSGuideDTO) -> list[str]:
        """
        Validate guide against TISS 4.01 schema.

        Args:
            guide: Guide to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        ...

    @abstractmethod
    async def submit_guide(self, guide_xml: str, payer_id: str) -> TISSSubmissionResult:
        """
        Submit a TISS guide XML to a payer.

        Args:
            guide_xml: TISS 4.01 XML content
            payer_id: Target payer identifier

        Returns:
            Submission result with protocol number

        Raises:
            TISSException: If submission fails
        """
        ...

    @abstractmethod
    async def submit_batch(self, batch: TISSBatchDTO) -> TISSSubmissionResult:
        """
        Submit a batch of TISS guides.

        Args:
            batch: Batch containing multiple guides

        Returns:
            Submission result for the batch

        Raises:
            TISSException: If batch submission fails
        """
        ...

    @abstractmethod
    async def check_submission_status(self, protocol_number: str) -> TISSSubmissionResult:
        """
        Check the status of a submitted guide.

        Args:
            protocol_number: Protocol number from initial submission

        Returns:
            Current submission status

        Raises:
            TISSException: If status check fails
        """
        ...


# ============================================================================
# Production Implementation
# ============================================================================


class TISSClient(BaseIntegrationClient, TISSClientProtocol):
    """Production TISS client implementation."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = 30):
        """
        Initialize TISS client.

        Args:
            base_url: Base URL for TISS submission endpoint
            api_key: API key for authentication (if required)
            timeout: Request timeout in seconds
        """
        super().__init__(service_name=SERVICE_NAME, base_url=base_url, timeout=timeout)
        self._api_key = api_key
        logger.info("TISS client initialized", extra={"base_url": base_url})

    @track_api_call(service_name=SERVICE_NAME, operation="generate_guide_xml")
    async def generate_guide_xml(self, guide: TISSGuideDTO) -> str:
        """Generate TISS 4.01 compliant XML."""
        try:
            # Create root element with TISS namespace
            root = ET.Element("tissComunicacao", {
                "xmlns": "http://www.ans.gov.br/padroes/tiss/schemas",
                "versao": "4.01.00"
            })

            # Header
            header = ET.SubElement(root, "cabecalho")
            ET.SubElement(header, "codigoPrestador").text = guide.provider_id
            ET.SubElement(header, "codigoOperadora").text = guide.payer_id
            ET.SubElement(header, "numeroGuia").text = guide.guide_number

            # Guide type specific content
            if guide.guide_type == TISSGuideType.SADT:
                self._add_sadt_content(root, guide)
            elif guide.guide_type == TISSGuideType.HOSPITALIZATION:
                self._add_hospitalization_content(root, guide)
            elif guide.guide_type == TISSGuideType.CONSULTATION:
                self._add_consultation_content(root, guide)
            elif guide.guide_type == TISSGuideType.EMERGENCY:
                self._add_emergency_content(root, guide)
            else:
                raise TISSSchemaError(_("Tipo de guia não suportado: {}").format(guide.guide_type))

            # Convert to string
            xml_string = ET.tostring(root, encoding="unicode", method="xml")
            logger.debug("Generated TISS XML", extra={"guide_number": guide.guide_number})
            return xml_string

        except Exception as e:
            logger.error("Failed to generate TISS XML", extra={"error": str(e)})
            raise TISSSchemaError(_("Falha na geração de XML: {}").format(e)) from e

    def _add_sadt_content(self, root: ET.Element, guide: TISSGuideDTO) -> None:
        """Add SADT (Support and Diagnostic Therapy) specific content."""
        sadt = ET.SubElement(root, "guiaSP-SADT")

        if guide.requested_date:
            ET.SubElement(sadt, "dataRealizacao").text = guide.requested_date.strftime("%Y-%m-%d")

        if guide.authorization_number:
            ET.SubElement(sadt, "numeroAutorizacao").text = guide.authorization_number

        # Procedures
        if guide.items:
            procedures = ET.SubElement(sadt, "procedimentos")
            for item in guide.items:
                proc = ET.SubElement(procedures, "procedimento")
                ET.SubElement(proc, "codigo").text = item.get("code", "")
                ET.SubElement(proc, "descricao").text = item.get("description", "")
                ET.SubElement(proc, "quantidade").text = str(item.get("quantity", 1))
                ET.SubElement(proc, "valorUnitario").text = f"{item.get('unit_price', 0):.2f}"

    def _add_hospitalization_content(self, root: ET.Element, guide: TISSGuideDTO) -> None:
        """Add hospitalization specific content."""
        hosp = ET.SubElement(root, "guiaInternacao")

        if guide.admission_date:
            ET.SubElement(hosp, "dataInternacao").text = guide.admission_date.strftime("%Y-%m-%d")

        if guide.discharge_date:
            ET.SubElement(hosp, "dataAlta").text = guide.discharge_date.strftime("%Y-%m-%d")

        if guide.diagnosis_codes:
            diagnosticos = ET.SubElement(hosp, "diagnosticos")
            for code in guide.diagnosis_codes:
                diag = ET.SubElement(diagnosticos, "diagnostico")
                ET.SubElement(diag, "codigo").text = code

    def _add_consultation_content(self, root: ET.Element, guide: TISSGuideDTO) -> None:
        """Add consultation specific content."""
        consult = ET.SubElement(root, "guiaConsulta")

        if guide.requested_date:
            ET.SubElement(consult, "dataConsulta").text = guide.requested_date.strftime("%Y-%m-%d")

        if guide.attending_physician_id:
            ET.SubElement(consult, "codigoProfissional").text = guide.attending_physician_id

    def _add_emergency_content(self, root: ET.Element, guide: TISSGuideDTO) -> None:
        """Add emergency specific content."""
        emerg = ET.SubElement(root, "guiaAtendimentoEmergencia")

        if guide.admission_date:
            ET.SubElement(emerg, "dataAtendimento").text = guide.admission_date.strftime("%Y-%m-%d")

    @track_api_call(service_name=SERVICE_NAME, operation="validate_guide")
    async def validate_guide(self, guide: TISSGuideDTO) -> list[str]:
        """Validate guide against TISS 4.01 schema."""
        errors: list[str] = []

        # Basic validations
        if not guide.guide_number:
            errors.append(_("Número da guia é obrigatório"))

        if not guide.payer_id:
            errors.append(_("ID da operadora é obrigatório"))

        if not guide.provider_id:
            errors.append(_("ID do prestador é obrigatório"))

        # Type-specific validations
        if guide.guide_type == TISSGuideType.HOSPITALIZATION:
            if not guide.admission_date:
                errors.append(_("Data de internação é obrigatória para hospitalização"))

        if guide.guide_type in [TISSGuideType.SADT, TISSGuideType.CONSULTATION]:
            if not guide.items and not guide.procedure_codes:
                errors.append(_("Procedimentos são obrigatórios"))

        logger.debug("Validated TISS guide", extra={
            "guide_number": guide.guide_number,
            "error_count": len(errors)
        })
        return errors

    @track_api_call(service_name=SERVICE_NAME, operation="submit_guide")
    async def submit_guide(self, guide_xml: str, payer_id: str) -> TISSSubmissionResult:
        """Submit a TISS guide XML to a payer."""
        headers = {"Content-Type": "application/xml"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = await self.post(
                f"/payers/{payer_id}/submit",
                data=guide_xml.encode("utf-8"),
                headers=headers
            )

            result = TISSSubmissionResult(
                success=response.get("success", False),
                protocol_number=response.get("protocol_number"),
                submission_timestamp=datetime.fromisoformat(response["timestamp"]) if "timestamp" in response else None,
                payer_response_code=response.get("response_code"),
                payer_response_message=response.get("message")
            )

            logger.info("Submitted TISS guide", extra={
                "payer_id": payer_id,
                "protocol": result.protocol_number
            })
            return result

        except Exception as e:
            logger.error("TISS submission failed", extra={"error": str(e), "payer_id": payer_id})
            raise TISSException(_("Falha no envio: {}").format(e)) from e

    @track_api_call(service_name=SERVICE_NAME, operation="submit_batch")
    async def submit_batch(self, batch: TISSBatchDTO) -> TISSSubmissionResult:
        """Submit a batch of TISS guides."""
        try:
            # Generate XML for all guides
            guide_xmls = []
            for guide in batch.guides:
                xml = await self.generate_guide_xml(guide)
                guide_xmls.append(xml)

            # Create batch XML wrapper
            batch_xml = self._create_batch_xml(batch.batch_id, guide_xmls)

            # Submit batch
            result = await self.submit_guide(batch_xml, batch.payer_id)
            logger.info("Submitted TISS batch", extra={
                "batch_id": batch.batch_id,
                "guide_count": len(batch.guides)
            })
            return result

        except Exception as e:
            logger.error("TISS batch submission failed", extra={"error": str(e)})
            raise TISSException(_("Falha no envio em lote: {}").format(e)) from e

    def _create_batch_xml(self, batch_id: str, guide_xmls: list[str]) -> str:
        """Create batch XML wrapper."""
        root = ET.Element("tissLote", {
            "xmlns": "http://www.ans.gov.br/padroes/tiss/schemas",
            "versao": "4.01.00"
        })
        ET.SubElement(root, "identificadorLote").text = batch_id

        guias = ET.SubElement(root, "guias")
        for xml_str in guide_xmls:
            # Parse each guide XML and append to batch
            guide_elem = ET.fromstring(xml_str)
            guias.append(guide_elem)

        return ET.tostring(root, encoding="unicode", method="xml")

    @track_api_call(service_name=SERVICE_NAME, operation="check_submission_status")
    async def check_submission_status(self, protocol_number: str) -> TISSSubmissionResult:
        """Check the status of a submitted guide."""
        try:
            response = await self.get(f"/submissions/{protocol_number}/status")

            result = TISSSubmissionResult(
                success=response.get("success", False),
                protocol_number=protocol_number,
                payer_response_code=response.get("status_code"),
                payer_response_message=response.get("status_message"),
                validation_errors=response.get("validation_errors", []),
                processing_errors=response.get("processing_errors", [])
            )

            logger.debug("Checked TISS submission status", extra={"protocol": protocol_number})
            return result

        except Exception as e:
            logger.error("Status check failed", extra={"error": str(e), "protocol": protocol_number})
            raise TISSException(_("Falha na verificação de status: {}").format(e)) from e


# ============================================================================
# Stub Implementation for Testing
# ============================================================================


class StubTISSClient(TISSClientProtocol):
    """Stub TISS client for testing."""

    def __init__(self):
        """Initialize stub client."""
        self._submissions: dict[str, TISSSubmissionResult] = {}
        self._protocol_counter = 1000
        logger.info("Stub TISS client initialized")

    async def generate_guide_xml(self, guide: TISSGuideDTO) -> str:
        """Generate mock XML."""
        return f'<tiss><guide number="{guide.guide_number}" type="{guide.guide_type.value}"/></tiss>'

    async def validate_guide(self, guide: TISSGuideDTO) -> list[str]:
        """Always returns empty (valid)."""
        return []

    async def submit_guide(self, guide_xml: str, payer_id: str) -> TISSSubmissionResult:
        """Mock submission."""
        protocol = f"STUB-{self._protocol_counter}"
        self._protocol_counter += 1

        result = TISSSubmissionResult(
            success=True,
            protocol_number=protocol,
            submission_timestamp=datetime.utcnow(),
            payer_response_code="OK",
            payer_response_message="Stub submission accepted"
        )

        self._submissions[protocol] = result
        return result

    async def submit_batch(self, batch: TISSBatchDTO) -> TISSSubmissionResult:
        """Mock batch submission."""
        protocol = f"BATCH-STUB-{self._protocol_counter}"
        self._protocol_counter += 1

        result = TISSSubmissionResult(
            success=True,
            protocol_number=protocol,
            submission_timestamp=datetime.utcnow(),
            payer_response_code="OK",
            payer_response_message=f"Stub batch with {len(batch.guides)} guides accepted"
        )

        self._submissions[protocol] = result
        return result

    async def check_submission_status(self, protocol_number: str) -> TISSSubmissionResult:
        """Return stored submission result."""
        if protocol_number in self._submissions:
            return self._submissions[protocol_number]

        return TISSSubmissionResult(
            success=False,
            protocol_number=protocol_number,
            payer_response_code="NOT_FOUND",
            payer_response_message="Submission not found"
        )
