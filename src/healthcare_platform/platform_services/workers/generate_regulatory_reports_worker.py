"""
Worker para geração de relatórios regulatórios (ANS, ANVISA, CNES).

Gera relatórios obrigatórios:
- RN 124 (SIP - Sistema de Informações de Produtos)
- RN 209 (Utilização de Serviços)
- RN 388 (Indicadores de Qualidade)
- RN 424 (Transparência e Padrão TISS)

Padrão: Protocol ABC + Stub implementation
Decorators: @require_tenant, @track_task_execution
Métricas: Prometheus Counter, Histogram
LGPD: Anonimização de dados pessoais em relatórios
i18n: Todas strings user-facing via _()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
regulatory_reports_total = Counter(
    "regulatory_reports_total",
    "Total regulatory reports generated",
    ["tenant_id", "report_type", "status"],
)
report_duration_seconds = Histogram(
    "report_duration_seconds",
    "Duration of regulatory report generation",
    ["tenant_id", "report_type"],
)

TOPIC = "platform.generate_regulatory_reports"


class RegulatoryReportException(DomainException):
    """    Exceção de geração de relatório regulatório.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="REGULATORY_REPORT_ERROR",
            details=details or {},
        )


class GenerateRegulatoryReportsInput(BaseModel):
    """Input para geração de relatórios regulatórios."""

    report_type: str = Field(
        ...,
        description=_("Tipo: RN_124_SIP, RN_209_UTILIZATION, RN_388_QUALITY, RN_424_TRANSPARENCY"),
    )
    reference_period: str = Field(..., description=_("Período de referência: YYYY-MM ou YYYY-QN (trimestre)"))
    ans_registry_code: str = Field(..., description=_("Código de registro ANS da operadora"))
    include_subsidiaries: bool = Field(default=False, description=_("Incluir dados de subsidiárias/filiais"))
    output_format: str = Field(default="xml", description=_("Formato de saída: xml, csv, json"))
    auto_submit_ans: bool = Field(default=False, description=_("Enviar automaticamente para ANS via webservice"))


class RegulatoryReportMetric(BaseModel):
    """Métrica do relatório regulatório."""

    metric_code: str = Field(..., description=_("Código da métrica (ex: IDSS_05, QUALISS_02)"))
    metric_name: str = Field(..., description=_("Nome da métrica"))
    value: float = Field(..., description=_("Valor calculado"))
    unit: str = Field(..., description=_("Unidade (%, days, count)"))
    target_value: float | None = Field(None, description=_("Meta ANS (se aplicável)"))
    compliant: bool = Field(..., description=_("Se está em conformidade com meta ANS"))


class GenerateRegulatoryReportsOutput(BaseModel):
    """Output da geração de relatório regulatório."""

    report_id: str = Field(..., description=_("ID único do relatório"))
    report_type: str = Field(..., description=_("Tipo do relatório"))
    reference_period: str = Field(..., description=_("Período de referência"))
    metrics: list[RegulatoryReportMetric] = Field(default_factory=list, description=_("Métricas calculadas"))
    total_beneficiaries: int = Field(..., description=_("Total de beneficiários ativos no período"))
    total_claims: int = Field(..., description=_("Total de guias/sinistros no período"))
    compliance_rate: float = Field(..., description=_("Taxa de conformidade com metas ANS (%)"))
    file_path: str = Field(..., description=_("Caminho do arquivo gerado (S3/GCS)"))
    ans_submission_protocol: str | None = Field(None, description=_("Protocolo de envio ANS (se auto_submit)"))
    generated_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp de geração"))
    duration_seconds: float = Field(..., description=_("Duração da geração em segundos"))


class GenerateRegulatoryReportsProtocol(ABC):
    """Protocol para geração de relatórios regulatórios."""

    @abstractmethod
    async def execute(self, input_data: GenerateRegulatoryReportsInput) -> GenerateRegulatoryReportsOutput:
        """
        Gera relatório regulatório obrigatório.

        Args:
            input_data: Parâmetros do relatório

        Returns:
            GenerateRegulatoryReportsOutput com métricas calculadas

        Raises:
            RegulatoryReportException: Erro na geração do relatório
        """
        pass


class GenerateRegulatoryReportsStub(GenerateRegulatoryReportsProtocol):
    """Stub implementation para geração de relatórios regulatórios."""

    def __init__(self, ans_client: ANSClientProtocol | None = None):
        """
        Inicializa o worker de relatórios regulatórios.

        Args:
            ans_client: Cliente ANS para envio de relatórios
        """
        self.ans_client = ans_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: GenerateRegulatoryReportsInput) -> GenerateRegulatoryReportsOutput:
        """
        Gera relatório regulatório obrigatório.

        Fluxo:
        1. Valida período de referência
        2. Extrai dados operacionais (claims, encounters, beneficiaries)
        3. Calcula métricas específicas do relatório (RN_124, RN_209, etc)
        4. Valida conformidade com metas ANS
        5. Gera arquivo XML/CSV conforme layout padrão ANS
        6. Se auto_submit=True, envia via webservice ANS
        7. Armazena arquivo em object storage
        8. Atualiza métricas Prometheus

        LGPD: Anonimiza dados pessoais em relatórios agregados.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='ans/comp_ans_001',
                inputs={'report_type': input_data.report_type, 'reference_period': input_data.reference_period},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        start_time = datetime.utcnow()

        logger.info(
            _("Gerando relatório regulatório {report_type} para período {period}").format(
                report_type=input_data.report_type,
                period=input_data.reference_period,
            ),
            extra={
                "tenant_id": tenant.tenant_code,
                "ans_code": input_data.ans_registry_code,
            },
        )

        try:
            # Valida período de referência
            await self._validate_reference_period(input_data.reference_period)

            # Extrai dados operacionais
            operational_data = await self._extract_operational_data(
                report_type=input_data.report_type,
                reference_period=input_data.reference_period,
                include_subsidiaries=input_data.include_subsidiaries,
            )

            # Calcula métricas específicas do relatório
            metrics = await self._calculate_report_metrics(
                report_type=input_data.report_type,
                operational_data=operational_data,
            )

            # Valida conformidade com metas ANS
            compliance_rate = await self._validate_compliance(metrics)

            # Gera arquivo no formato padrão ANS
            file_path = await self._generate_report_file(
                report_type=input_data.report_type,
                reference_period=input_data.reference_period,
                metrics=metrics,
                operational_data=operational_data,
                output_format=input_data.output_format,
            )

            # Envia para ANS (se auto_submit)
            ans_protocol = None
            if input_data.auto_submit_ans and self.ans_client:
                ans_protocol = await self._submit_to_ans(
                    report_type=input_data.report_type,
                    file_path=file_path,
                    ans_registry_code=input_data.ans_registry_code,
                )

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Atualiza métricas Prometheus
            regulatory_reports_total.labels(
                tenant_id=tenant.tenant_code,
                report_type=input_data.report_type,
                status="success",
            ).inc()

            report_duration_seconds.labels(
                tenant_id=tenant.tenant_code,
                report_type=input_data.report_type,
            ).observe(duration)

            report_id = f"REG-{tenant.tenant_code}-{input_data.report_type}-{input_data.reference_period}"

            output = GenerateRegulatoryReportsOutput(
                report_id=report_id,
                report_type=input_data.report_type,
                reference_period=input_data.reference_period,
                metrics=metrics,
                total_beneficiaries=operational_data["total_beneficiaries"],
                total_claims=operational_data["total_claims"],
                compliance_rate=compliance_rate,
                file_path=file_path,
                ans_submission_protocol=ans_protocol,
                duration_seconds=duration,
            )

            logger.info(
                _("Relatório regulatório gerado: {metrics_count} métricas, conformidade={compliance}%").format(
                    metrics_count=len(metrics),
                    compliance=round(compliance_rate, 1),
                ),
                extra={
                    "tenant_id": tenant.tenant_code,
                    "report_id": report_id,
                },
            )

            return output

        except Exception as e:
            regulatory_reports_total.labels(
                tenant_id=tenant.tenant_code,
                report_type=input_data.report_type,
                status="error",
            ).inc()
            logger.error(_("Erro ao gerar relatório regulatório: {error}").format(error=str(e)))
            raise RegulatoryReportException(
                message=_("Falha ao gerar relatório regulatório"),
                details={"error": str(e)},
            ) from e

    async def _validate_reference_period(self, reference_period: str) -> None:
        """Valida formato do período de referência (YYYY-MM ou YYYY-QN)."""
        # Stub: validação simples
        if not (len(reference_period) in [7, 7] and "-" in reference_period):
            raise RegulatoryReportException(
                message=_("Período de referência inválido"),
                details={"period": reference_period},
            )

    async def _extract_operational_data(
        self,
        report_type: str,
        reference_period: str,
        include_subsidiaries: bool,
    ) -> dict[str, Any]:
        """Extrai dados operacionais para o relatório (stub)."""
        return {
            "total_beneficiaries": 15000,
            "total_claims": 8500,
            "total_encounters": 12000,
            "total_procedures": 25000,
            "claims_data": [{"id": f"CLAIM-{i}", "amount": 500.0} for i in range(100)],
        }

    async def _calculate_report_metrics(
        self,
        report_type: str,
        operational_data: dict[str, Any],
    ) -> list[RegulatoryReportMetric]:
        """Calcula métricas específicas do relatório regulatório."""
        metrics = []

        # Stub: métricas simuladas por tipo de relatório
        if report_type == "RN_124_SIP":
            metrics.append(
                RegulatoryReportMetric(
                    metric_code="SIP_01",
                    metric_name=_("Cobertura de produtos"),
                    value=98.5,
                    unit="%",
                    target_value=95.0,
                    compliant=True,
                )
            )
        elif report_type == "RN_209_UTILIZATION":
            metrics.append(
                RegulatoryReportMetric(
                    metric_code="UTIL_01",
                    metric_name=_("Taxa de utilização de consultas"),
                    value=3.2,
                    unit="consultas/beneficiário/ano",
                    target_value=None,
                    compliant=True,
                )
            )
        elif report_type == "RN_388_QUALITY":
            metrics.append(
                RegulatoryReportMetric(
                    metric_code="QUALISS_02",
                    metric_name=_("Tempo médio de atendimento"),
                    value=15.0,
                    unit="dias",
                    target_value=21.0,
                    compliant=True,
                )
            )
        elif report_type == "RN_424_TRANSPARENCY":
            metrics.append(
                RegulatoryReportMetric(
                    metric_code="TISS_01",
                    metric_name=_("Conformidade com padrão TISS"),
                    value=99.2,
                    unit="%",
                    target_value=100.0,
                    compliant=False,
                )
            )

        return metrics

    async def _validate_compliance(self, metrics: list[RegulatoryReportMetric]) -> float:
        """Valida conformidade com metas ANS e retorna taxa de conformidade."""
        if not metrics:
            return 100.0

        compliant_count = sum(1 for m in metrics if m.compliant)
        return (compliant_count / len(metrics)) * 100.0

    async def _generate_report_file(
        self,
        report_type: str,
        reference_period: str,
        metrics: list[RegulatoryReportMetric],
        operational_data: dict[str, Any],
        output_format: str,
    ) -> str:
        """Gera arquivo XML/CSV no formato padrão ANS."""
        # Stub: retorna caminho simulado
        file_name = f"{report_type}_{reference_period}.{output_format}"
        return f"s3://healthcare-regulatory/{report_type}/{file_name}"

    async def _submit_to_ans(
        self,
        report_type: str,
        file_path: str,
        ans_registry_code: str,
    ) -> str:
        """Envia relatório para ANS via webservice (stub)."""
        if not self.ans_client:
            return "PROTOCOL-SIMULATED"

        # Stub: simula envio
        protocol = f"ANS-PROTOCOL-{int(datetime.utcnow().timestamp())}"
        logger.info(
            _("Relatório enviado para ANS: protocolo={protocol}").format(protocol=protocol)
        )
        return protocol
