"""
Worker para integração com PACS/DICOM (sistemas de imagem médica).

Recebe notificações de estudos de imagem, cria recursos FHIR ImagingStudy,
rastreia modalidades e disponibiliza metadados para visualização.

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD com hash de identificadores
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Métricas Prometheus
imaging_integrations_total = Counter(
    "imaging_integrations_total",
    "Total de integrações de imagens processadas",
    ["tenant_id", "modality", "status"],
)

imaging_duration_seconds = Histogram(
    "imaging_integration_duration_seconds",
    "Duração das integrações de imagens",
    ["tenant_id", "modality"],
)

imaging_studies_gauge = Gauge(
    "imaging_studies_total",
    "Total de estudos de imagem armazenados",
    ["tenant_id", "modality"],
)


class ImagingIntegrationException(DomainException):
    """    Exceção lançada quando ocorrem erros na integração de imagens.
    
        Archetype: FINANCIAL_CALCULATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="IMAGING_INTEGRATION_ERROR",
            bpmn_error_code="ImagingIntegrationError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class IntegrateImagingInput(BaseModel):
    """Input para integração de imagens médicas."""

    patient_id: str = Field(..., description=_("ID do paciente"))
    accession_number: str = Field(..., description=_("Número de acesso do estudo"))
    study_instance_uid: str = Field(
        ..., description=_("UID único do estudo DICOM")
    )
    modality: Literal["CT", "MR", "XR", "US", "NM", "PT", "CR", "DX"] = Field(
        ..., description=_("Modalidade do exame (CT, MR, XR, etc.)")
    )
    study_description: str = Field(..., description=_("Descrição do estudo"))
    body_part: str | None = Field(None, description=_("Parte do corpo examinada"))
    series_count: int = Field(..., description=_("Quantidade de séries"))
    instance_count: int = Field(..., description=_("Quantidade de instâncias"))
    study_date: datetime = Field(..., description=_("Data do estudo"))
    referring_physician: str | None = Field(
        None, description=_("Médico solicitante")
    )
    pacs_url: str = Field(..., description=_("URL do servidor PACS"))
    dicom_metadata: dict[str, Any] | None = Field(
        None, description=_("Metadados DICOM adicionais")
    )


class SeriesInfo(BaseModel):
    """Informações de série DICOM."""

    series_instance_uid: str = Field(..., description=_("UID da série"))
    series_number: int = Field(..., description=_("Número da série"))
    series_description: str = Field(..., description=_("Descrição da série"))
    instance_count: int = Field(..., description=_("Quantidade de instâncias"))
    modality: str = Field(..., description=_("Modalidade"))


class IntegrateImagingOutput(BaseModel):
    """Output da integração de imagens."""

    integration_id: str = Field(..., description=_("ID único da integração"))
    patient_id: str = Field(..., description=_("ID do paciente"))
    study_instance_uid: str = Field(..., description=_("UID do estudo DICOM"))
    accession_number: str = Field(..., description=_("Número de acesso"))
    modality: str = Field(..., description=_("Modalidade"))
    series_info: list[SeriesInfo] = Field(
        default_factory=list, description=_("Informações das séries")
    )
    fhir_imaging_study_id: str = Field(
        ..., description=_("ID do recurso FHIR ImagingStudy")
    )
    viewer_url: str | None = Field(
        None, description=_("URL para visualização do estudo")
    )
    study_status: Literal["available", "processing", "failed"] = Field(
        ..., description=_("Status do estudo")
    )
    total_size_mb: float = Field(0.0, description=_("Tamanho total em MB"))
    integrated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da integração"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class IntegrateImagingProtocol(ABC):
    """Protocolo para integração de imagens médicas."""

    @abstractmethod
    async def parse_dicom_metadata(
        self, study_instance_uid: str
    ) -> dict[str, Any]:
        """
        Extrai metadados DICOM do estudo.

        Args:
            study_instance_uid: UID do estudo DICOM

        Returns:
            Metadados estruturados
        """
        pass

    @abstractmethod
    async def create_fhir_imaging_study(
        self, study_data: dict[str, Any]
    ) -> str:
        """
        Cria recurso FHIR ImagingStudy.

        Args:
            study_data: Dados do estudo

        Returns:
            ID do recurso FHIR criado
        """
        pass

    @abstractmethod
    async def generate_viewer_url(
        self, study_instance_uid: str, pacs_url: str
    ) -> str:
        """
        Gera URL para visualização do estudo em viewer DICOM.

        Args:
            study_instance_uid: UID do estudo
            pacs_url: URL do servidor PACS

        Returns:
            URL do viewer
        """
        pass

    @abstractmethod
    async def calculate_study_size(self, study_instance_uid: str) -> float:
        """
        Calcula tamanho total do estudo em MB.

        Args:
            study_instance_uid: UID do estudo

        Returns:
            Tamanho em MB
        """
        pass


class IntegrateImagingStub(IntegrateImagingProtocol):
    """Implementação stub para integração de imagens."""

    def __init__(self, fhir_client: FHIRClientProtocol):
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    async def parse_dicom_metadata(
        self, study_instance_uid: str
    ) -> dict[str, Any]:
        """Extrai metadados DICOM do estudo."""
        # Simulação de parsing DICOM
        return {
            "series": [
                {
                    "series_instance_uid": f"{study_instance_uid}.1",
                    "series_number": 1,
                    "series_description": "Axial",
                    "instance_count": 150,
                    "modality": "CT",
                },
                {
                    "series_instance_uid": f"{study_instance_uid}.2",
                    "series_number": 2,
                    "series_description": "Coronal",
                    "instance_count": 120,
                    "modality": "CT",
                },
            ],
            "patient_position": "HFS",
            "manufacturer": "Siemens",
            "station_name": "CT01",
        }

    async def create_fhir_imaging_study(
        self, study_data: dict[str, Any]
    ) -> str:
        """Cria recurso FHIR ImagingStudy."""
        # Simulação de criação FHIR
        study_id = f"ImagingStudy/{study_data.get('study_instance_uid')}"

        logger.info(
            _("Recurso FHIR ImagingStudy criado"),
            extra={"fhir_id": study_id},
        )

        return study_id

    async def generate_viewer_url(
        self, study_instance_uid: str, pacs_url: str
    ) -> str:
        """Gera URL para visualização do estudo."""
        return f"{pacs_url}/viewer?studyUID={study_instance_uid}"

    async def calculate_study_size(self, study_instance_uid: str) -> float:
        """Calcula tamanho total do estudo."""
        # Simulação de cálculo de tamanho
        return 245.7  # MB


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa integração de estudos de imagem DICOM.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado da integração

    Raises:
        ImagingIntegrationException: Se houver erro na integração
    """
    tenant = get_required_tenant()
    parsed_input = IntegrateImagingInput(**input_data)


    integration_id = (
        f"img_{parsed_input.patient_id}_{parsed_input.accession_number}_"
        f"{int(parsed_input.study_date.timestamp())}"
    )

    patient_id_hash = hashlib.sha256(
        parsed_input.patient_id.encode()
    ).hexdigest()[:16]

    logger.info(
        _("Iniciando integração de imagem médica"),
        extra={
            "tenant_id": tenant.tenant_code,
            "integration_id": integration_id,
            "patient_id_hash": patient_id_hash,
            "modality": parsed_input.modality,
            "study_instance_uid": parsed_input.study_instance_uid,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.tenant_code,
            category='infrastructure',
            table_name='config/infra_002',
            inputs={'study_type': parsed_input.study_type},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        # Inicializar cliente FHIR (mock)
        from healthcare_platform.shared.integrations.fhir_client import FHIRClientStub

        fhir_client = FHIRClientStub()
        service = IntegrateImagingStub(fhir_client=fhir_client)

        # Parsear metadados DICOM
        dicom_metadata = await service.parse_dicom_metadata(
            parsed_input.study_instance_uid
        )

        # Criar objetos SeriesInfo
        series_info = [
            SeriesInfo(**s) for s in dicom_metadata.get("series", [])
        ]

        # Criar recurso FHIR ImagingStudy
        fhir_id = await service.create_fhir_imaging_study(
            {
                "study_instance_uid": parsed_input.study_instance_uid,
                "patient_id": parsed_input.patient_id,
                "modality": parsed_input.modality,
                "study_description": parsed_input.study_description,
                "series": dicom_metadata.get("series", []),
            }
        )

        # Gerar URL do viewer
        viewer_url = await service.generate_viewer_url(
            parsed_input.study_instance_uid,
            parsed_input.pacs_url,
        )

        # Calcular tamanho
        total_size_mb = await service.calculate_study_size(
            parsed_input.study_instance_uid
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = IntegrateImagingOutput(
            integration_id=integration_id,
            patient_id=parsed_input.patient_id,
            study_instance_uid=parsed_input.study_instance_uid,
            accession_number=parsed_input.accession_number,
            modality=parsed_input.modality,
            series_info=series_info,
            fhir_imaging_study_id=fhir_id,
            viewer_url=viewer_url,
            study_status="available",
            total_size_mb=total_size_mb,
            duration_ms=duration_ms,
        )

        # Métricas
        imaging_integrations_total.labels(
            tenant_id=tenant.tenant_code,
            modality=parsed_input.modality,
            status="success",
        ).inc()

        imaging_duration_seconds.labels(
            tenant_id=tenant.tenant_code,
            modality=parsed_input.modality,
        ).observe(duration_ms / 1000.0)

        imaging_studies_gauge.labels(
            tenant_id=tenant.tenant_code,
            modality=parsed_input.modality,
        ).inc()

        logger.info(
            _("Integração de imagem concluída com sucesso"),
            extra={
                "tenant_id": tenant.tenant_code,
                "integration_id": integration_id,
                "patient_id_hash": patient_id_hash,
                "series_count": len(series_info),
                "total_size_mb": total_size_mb,
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro na integração de imagem"),
            extra={
                "tenant_id": tenant.tenant_code,
                "integration_id": integration_id,
                "patient_id_hash": patient_id_hash,
                "error": str(e),
            },
            exc_info=True,
        )
        raise ImagingIntegrationException(
            message=_("Falha ao integrar estudo de imagem"),
            details={"integration_id": integration_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.integrate_imaging"
