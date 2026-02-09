"""
TISS XML Generator for Hospital Revenue Cycle.

Generates TISS 4.0 compliant XML for Brazilian healthcare claims.

TISS (Troca de Informacoes em Saude Suplementar) is the standard
defined by ANS (Agencia Nacional de Saude Suplementar) for
electronic data exchange in the Brazilian supplementary health sector.

Supported claim types:
- SP-SADT: Servicos Profissionais / SADT (outpatient)
- Internacao: Hospitalization claims
- Consulta: Consultation claims

References:
- ANS RN 305/2012
- TISS 4.0 Technical Specification
"""

import base64
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from xml.dom import minidom
from xml.etree import ElementTree as ET

import structlog

from revenue_cycle.workers.billing.models import ClaimType, ClaimLineItem

logger = structlog.get_logger(__name__)


class TissXmlGenerationError(Exception):
    """Exception raised when TISS XML generation fails."""

    def __init__(self, message: str, claim_id: Optional[str] = None):
        self.message = message
        self.claim_id = claim_id
        super().__init__(message)


@dataclass
class TissValidationResult:
    """
    Result of TISS XML validation.

    Attributes:
        valid: Whether the XML is valid
        errors: List of validation errors
        warnings: List of validation warnings
    """

    valid: bool
    errors: List[str]
    warnings: List[str]

    @property
    def status(self) -> str:
        """Get validation status string."""
        if not self.valid:
            return "ERRORS"
        if self.warnings:
            return "WARNINGS"
        return "VALID"


@dataclass
class ClaimData:
    """
    Data required for TISS claim generation.

    Contains all the information needed to generate a complete TISS XML.
    """

    claim_id: str
    encounter_id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_cpf: Optional[str] = None
    patient_card_number: Optional[str] = None
    payer_id: Optional[str] = None
    payer_ans_code: Optional[str] = None
    provider_cnes: Optional[str] = None
    provider_name: Optional[str] = None
    claim_type: ClaimType = ClaimType.SP_SADT
    items: List[ClaimLineItem] = None
    total_amount: Decimal = Decimal("0")
    authorization_number: Optional[str] = None
    service_date: Optional[datetime] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []


# Alias for test compatibility - tests expect ValidationResult
ValidationResult = TissValidationResult


class TissXmlGenerator:
    """
    TISS XML Generator for Brazilian healthcare claims.

    Generates TISS 4.0 compliant XML with support for:
    - SP-SADT (outpatient services)
    - Internacao (hospitalization)
    - Consulta (consultations)

    The generated XML follows ANS TISS 4.0 schema requirements.
    """

    # TISS 4.0 namespace
    TISS_NAMESPACE = "http://www.ans.gov.br/padroes/tiss/schemas"

    # TISS version
    TISS_VERSION = "4.01.00"

    def __init__(self, default_provider_cnes: Optional[str] = None):
        """
        Initialize TISS XML generator.

        Args:
            default_provider_cnes: Default CNES code for the provider
        """
        self.default_provider_cnes = default_provider_cnes or "0000000"
        self._logger = logger.bind(service="TissXmlGenerator")

    def generate(self, claim_data: ClaimData) -> str:
        """
        Generate TISS XML for a claim.

        Args:
            claim_data: Claim data to generate XML for

        Returns:
            TISS XML as string

        Raises:
            TissXmlGenerationError: If generation fails
        """
        self._logger.info(
            "Generating TISS XML",
            claim_id=claim_data.claim_id,
            claim_type=claim_data.claim_type.value,
        )

        try:
            if claim_data.claim_type == ClaimType.SP_SADT:
                xml = self.generate_sp_sadt(claim_data)
            elif claim_data.claim_type == ClaimType.INTERNACAO:
                xml = self.generate_internacao(claim_data)
            elif claim_data.claim_type == ClaimType.CONSULTA:
                xml = self.generate_consulta(claim_data)
            else:
                xml = self.generate_sp_sadt(claim_data)

            self._logger.info(
                "TISS XML generated successfully",
                claim_id=claim_data.claim_id,
                xml_size=len(xml),
            )
            return xml

        except Exception as e:
            self._logger.error(
                "TISS XML generation failed",
                claim_id=claim_data.claim_id,
                error=str(e),
            )
            raise TissXmlGenerationError(
                f"Failed to generate TISS XML: {e}",
                claim_id=claim_data.claim_id,
            )

    def generate_sp_sadt(self, claim_data: ClaimData) -> str:
        """
        Generate SP-SADT (Servicos Profissionais / SADT) XML.

        SP-SADT is used for outpatient procedures, exams, and
        professional services.

        Args:
            claim_data: Claim data

        Returns:
            SP-SADT TISS XML string
        """
        root = self._create_root_element("guiaSP-SADT")

        # Add header
        self._add_header(root, claim_data)

        # Add identification
        identificacao = ET.SubElement(root, "identificacaoGuia")
        self._add_text_element(identificacao, "numeroGuiaPrestador", claim_data.claim_id)
        if claim_data.authorization_number:
            self._add_text_element(
                identificacao, "numeroGuiaOperadora", claim_data.authorization_number
            )

        # Add beneficiary data
        self._add_beneficiary(root, claim_data)

        # Add contratado (provider) data
        self._add_provider(root, claim_data)

        # Add procedures
        procedimentos = ET.SubElement(root, "procedimentosRealizados")
        for item in claim_data.items:
            self._add_procedure_sp_sadt(procedimentos, item)

        # Add totals
        totais = ET.SubElement(root, "valorTotal")
        self._add_text_element(totais, "valorProcedimentos", str(claim_data.total_amount))
        self._add_text_element(totais, "valorTotal", str(claim_data.total_amount))

        return self._to_string(root)

    def generate_internacao(self, claim_data: ClaimData) -> str:
        """
        Generate Internacao (hospitalization) XML.

        Used for inpatient hospitalization claims.

        Args:
            claim_data: Claim data

        Returns:
            Internacao TISS XML string
        """
        root = self._create_root_element("guiaResumoInternacao")

        # Add header
        self._add_header(root, claim_data)

        # Add identification
        identificacao = ET.SubElement(root, "identificacaoGuia")
        self._add_text_element(identificacao, "numeroGuiaPrestador", claim_data.claim_id)
        if claim_data.authorization_number:
            self._add_text_element(
                identificacao, "numeroGuiaOperadora", claim_data.authorization_number
            )

        # Add beneficiary data
        self._add_beneficiary(root, claim_data)

        # Add provider data
        self._add_provider(root, claim_data)

        # Add internacao data
        internacao = ET.SubElement(root, "dadosInternacao")
        self._add_text_element(
            internacao,
            "caraterAtendimento",
            "1",  # 1=Eletivo, 2=Urgencia
        )
        self._add_text_element(
            internacao,
            "tipoFaturamento",
            "1",  # 1=Total, 2=Parcial
        )
        if claim_data.service_date:
            self._add_text_element(
                internacao,
                "dataInicioFaturamento",
                claim_data.service_date.strftime("%Y-%m-%d"),
            )
            self._add_text_element(
                internacao,
                "horaInicioFaturamento",
                claim_data.service_date.strftime("%H:%M:%S"),
            )

        # Add procedures
        procedimentos = ET.SubElement(root, "procedimentosRealizados")
        for item in claim_data.items:
            self._add_procedure_internacao(procedimentos, item)

        # Add totals
        totais = ET.SubElement(root, "valorTotal")
        self._add_text_element(totais, "valorProcedimentos", str(claim_data.total_amount))
        self._add_text_element(totais, "valorDiarias", "0.00")
        self._add_text_element(totais, "valorTaxasAlugueis", "0.00")
        self._add_text_element(totais, "valorMateriais", "0.00")
        self._add_text_element(totais, "valorMedicamentos", "0.00")
        self._add_text_element(totais, "valorOPME", "0.00")
        self._add_text_element(totais, "valorGasesMedicinais", "0.00")
        self._add_text_element(totais, "valorTotalGeral", str(claim_data.total_amount))

        return self._to_string(root)

    def generate_consulta(self, claim_data: ClaimData) -> str:
        """
        Generate Consulta (consultation) XML.

        Used for medical consultation claims.

        Args:
            claim_data: Claim data

        Returns:
            Consulta TISS XML string
        """
        root = self._create_root_element("guiaConsulta")

        # Add header
        self._add_header(root, claim_data)

        # Add identification
        identificacao = ET.SubElement(root, "identificacaoGuia")
        self._add_text_element(identificacao, "numeroGuiaPrestador", claim_data.claim_id)

        # Add beneficiary data
        self._add_beneficiary(root, claim_data)

        # Add provider data
        self._add_provider(root, claim_data)

        # Add consultation data
        consulta = ET.SubElement(root, "dadosConsulta")
        if claim_data.service_date:
            self._add_text_element(
                consulta,
                "dataAtendimento",
                claim_data.service_date.strftime("%Y-%m-%d"),
            )
        self._add_text_element(consulta, "tipoConsulta", "1")  # 1=Primeira

        # Add procedure (single procedure for consultation)
        if claim_data.items:
            item = claim_data.items[0]
            procedimento = ET.SubElement(consulta, "procedimento")
            self._add_text_element(procedimento, "codigoProcedimento", item.procedure_code)
            self._add_text_element(procedimento, "valorProcedimento", str(item.total_price))

        return self._to_string(root)

    def validate_xml(self, xml: str) -> TissValidationResult:
        """
        Validate TISS XML against basic rules.

        Performs structural validation without full XSD validation.

        Args:
            xml: TISS XML string to validate

        Returns:
            TissValidationResult with validation status
        """
        errors = []
        warnings = []

        try:
            # Parse XML
            root = ET.fromstring(xml)

            # Check for required elements
            required_elements = [
                "cabecalho",
                "identificacaoGuia",
            ]

            for element_name in required_elements:
                if root.find(f".//{element_name}") is None:
                    errors.append(f"Missing required element: {element_name}")

            # Check for beneficiary data
            beneficiario = root.find(".//dadosBeneficiario")
            if beneficiario is None:
                warnings.append("Missing beneficiary data (dadosBeneficiario)")

            # Check for provider data
            contratado = root.find(".//dadosContratado") or root.find(
                ".//contratadoExecutante"
            )
            if contratado is None:
                warnings.append("Missing provider data (dadosContratado)")

            # Check for procedure data
            procedimentos = root.find(".//procedimentosRealizados")
            if procedimentos is not None:
                if len(list(procedimentos)) == 0:
                    errors.append("No procedures found in procedimentosRealizados")

        except ET.ParseError as e:
            errors.append(f"XML parse error: {e}")

        valid = len(errors) == 0

        self._logger.info(
            "TISS XML validation completed",
            valid=valid,
            errors=len(errors),
            warnings=len(warnings),
        )

        return TissValidationResult(valid=valid, errors=errors, warnings=warnings)

    def encode_base64(self, xml: str) -> str:
        """
        Encode TISS XML to base64.

        Args:
            xml: TISS XML string

        Returns:
            Base64 encoded XML
        """
        return base64.b64encode(xml.encode("utf-8")).decode("utf-8")

    def _create_root_element(self, tag: str) -> ET.Element:
        """Create root element with TISS namespace."""
        root = ET.Element(tag)
        root.set("xmlns", self.TISS_NAMESPACE)
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        return root

    def _add_header(self, parent: ET.Element, claim_data: ClaimData) -> None:
        """Add TISS header element."""
        cabecalho = ET.SubElement(parent, "cabecalho")
        self._add_text_element(cabecalho, "versaoTISS", self.TISS_VERSION)
        self._add_text_element(
            cabecalho,
            "dataGeracao",
            datetime.now().strftime("%Y-%m-%d"),
        )
        self._add_text_element(
            cabecalho,
            "horaGeracao",
            datetime.now().strftime("%H:%M:%S"),
        )
        self._add_text_element(
            cabecalho, "transacao", claim_data.claim_type.tiss_code
        )
        self._add_text_element(cabecalho, "sequencialTransacao", "1")

        # Add origem (origin)
        origem = ET.SubElement(cabecalho, "origem")
        identificacao = ET.SubElement(origem, "identificacaoPrestador")
        self._add_text_element(
            identificacao,
            "codigoPrestadorNaOperadora",
            claim_data.provider_cnes or self.default_provider_cnes,
        )

        # Add destino (destination)
        destino = ET.SubElement(cabecalho, "destino")
        self._add_text_element(
            destino,
            "registroANS",
            claim_data.payer_ans_code or "000000",
        )

    def _add_beneficiary(self, parent: ET.Element, claim_data: ClaimData) -> None:
        """Add beneficiary (patient) data."""
        beneficiario = ET.SubElement(parent, "dadosBeneficiario")
        self._add_text_element(
            beneficiario,
            "numeroCarteira",
            claim_data.patient_card_number or claim_data.patient_id,
        )
        self._add_text_element(
            beneficiario,
            "nomeBeneficiario",
            claim_data.patient_name or "Beneficiario",
        )
        if claim_data.patient_cpf:
            self._add_text_element(beneficiario, "cpf", claim_data.patient_cpf)

    def _add_provider(self, parent: ET.Element, claim_data: ClaimData) -> None:
        """Add provider (contratado) data."""
        contratado = ET.SubElement(parent, "contratadoExecutante")
        identificacao = ET.SubElement(contratado, "identificacaoContratado")
        self._add_text_element(
            identificacao,
            "codigoPrestadorNaOperadora",
            claim_data.provider_cnes or self.default_provider_cnes,
        )
        self._add_text_element(
            contratado,
            "nomeContratado",
            claim_data.provider_name or "Prestador",
        )
        self._add_text_element(
            contratado,
            "CNES",
            claim_data.provider_cnes or self.default_provider_cnes,
        )

    def _add_procedure_sp_sadt(
        self, parent: ET.Element, item: ClaimLineItem
    ) -> None:
        """Add procedure for SP-SADT claim."""
        procedimento = ET.SubElement(parent, "procedimento")
        self._add_text_element(procedimento, "sequencialItem", str(item.line_number))
        self._add_text_element(
            procedimento,
            "dataExecucao",
            datetime.now().strftime("%Y-%m-%d"),
        )
        self._add_text_element(
            procedimento,
            "horaInicial",
            datetime.now().strftime("%H:%M:%S"),
        )
        self._add_text_element(procedimento, "codigoTabela", "22")  # TUSS
        self._add_text_element(
            procedimento, "codigoProcedimento", item.procedure_code
        )
        if item.description:
            self._add_text_element(
                procedimento, "descricaoProcedimento", item.description[:50]
            )
        self._add_text_element(
            procedimento, "quantidadeExecutada", str(item.quantity)
        )
        self._add_text_element(
            procedimento, "valorUnitario", f"{item.unit_price:.2f}"
        )
        self._add_text_element(procedimento, "valorTotal", f"{item.total_price:.2f}")

    def _add_procedure_internacao(
        self, parent: ET.Element, item: ClaimLineItem
    ) -> None:
        """Add procedure for Internacao claim."""
        procedimento = ET.SubElement(parent, "procedimento")
        self._add_text_element(procedimento, "sequencialItem", str(item.line_number))
        self._add_text_element(
            procedimento,
            "dataExecucao",
            datetime.now().strftime("%Y-%m-%d"),
        )
        self._add_text_element(procedimento, "codigoTabela", "22")  # TUSS
        self._add_text_element(
            procedimento, "codigoProcedimento", item.procedure_code
        )
        self._add_text_element(
            procedimento, "quantidadeExecutada", str(item.quantity)
        )
        self._add_text_element(procedimento, "viaAcesso", "1")  # 1=Unica
        self._add_text_element(procedimento, "tecnicaUtilizada", "1")  # 1=Convencional
        self._add_text_element(
            procedimento, "valorUnitario", f"{item.unit_price:.2f}"
        )
        self._add_text_element(procedimento, "valorTotal", f"{item.total_price:.2f}")

    def _add_text_element(
        self, parent: ET.Element, tag: str, text: str
    ) -> ET.Element:
        """Add a text element to parent."""
        element = ET.SubElement(parent, tag)
        element.text = text
        return element

    def _to_string(self, root: ET.Element) -> str:
        """Convert ElementTree to formatted XML string."""
        raw_xml = ET.tostring(root, encoding="unicode")
        # Pretty print
        dom = minidom.parseString(raw_xml)
        return dom.toprettyxml(indent="  ", encoding=None)
