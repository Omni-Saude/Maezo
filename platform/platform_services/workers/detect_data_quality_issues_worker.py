"""
Worker para detecção de problemas de qualidade de dados.

Monitora completude, acurácia, pontualidade e consistência de dados
entre sistemas (Tasy, MV Soul, FHIR, data lake).

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD com hash de identificadores
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)

# Métricas Prometheus
quality_checks_total = Counter(
    "data_quality_checks_total",
    "Total de verificações de qualidade de dados",
    ["tenant_id", "check_type", "status"],
)

quality_duration_seconds = Histogram(
    "data_quality_check_duration_seconds",
    "Duração das verificações de qualidade",
    ["tenant_id", "check_type"],
)

quality_issues_gauge = Gauge(
    "data_quality_issues_active",
    "Problemas de qualidade de dados ativos",
    ["tenant_id", "severity", "dimension"],
)


class DataQualityException(DomainException):
    """Exceção lançada quando ocorrem erros na detecção de qualidade."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="DATA_QUALITY_ERROR",
            bpmn_error_code="DataQualityError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class DetectDataQualityIssuesInput(BaseModel):
    """Input para detecção de problemas de qualidade."""

    quality_dimensions: list[
        Literal["completeness", "accuracy", "timeliness", "consistency"]
    ] = Field(..., description=_("Dimensões de qualidade a verificar"))
    data_sources: list[Literal["tasy", "mv_soul", "fhir", "data_lake"]] = Field(
        ..., description=_("Fontes de dados a verificar")
    )
    entity_types: list[Literal["patient", "encounter", "procedure", "lab_result"]] = (
        Field(..., description=_("Tipos de entidade a verificar"))
    )
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    severity_threshold: Literal["low", "medium", "high", "critical"] = Field(
        default="medium", description=_("Severidade mínima para reportar")
    )


class QualityIssue(BaseModel):
    """Problema de qualidade de dados identificado."""

    issue_id: str = Field(..., description=_("ID único do problema"))
    dimension: Literal["completeness", "accuracy", "timeliness", "consistency"] = (
        Field(..., description=_("Dimensão de qualidade afetada"))
    )
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description=_("Severidade do problema")
    )
    data_source: str = Field(..., description=_("Fonte de dados afetada"))
    entity_type: str = Field(..., description=_("Tipo de entidade afetado"))
    field_name: str | None = Field(None, description=_("Campo específico afetado"))
    issue_description: str = Field(..., description=_("Descrição do problema"))
    affected_records: int = Field(..., description=_("Registros afetados"))
    sample_records: list[str] = Field(
        default_factory=list, description=_("IDs de registros exemplo")
    )
    detected_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da detecção"),
    )
    recommended_action: str = Field(
        ..., description=_("Ação recomendada para correção")
    )


class DetectDataQualityIssuesOutput(BaseModel):
    """Output da detecção de problemas de qualidade."""

    check_id: str = Field(..., description=_("ID único da verificação"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    issues: list[QualityIssue] = Field(
        ..., description=_("Problemas identificados")
    )
    quality_score: float = Field(
        ..., description=_("Score geral de qualidade (0-100)")
    )
    dimensions_checked: list[str] = Field(
        ..., description=_("Dimensões verificadas")
    )
    sources_checked: list[str] = Field(
        ..., description=_("Fontes verificadas")
    )
    total_records_checked: int = Field(
        ..., description=_("Total de registros verificados")
    )
    issues_by_severity: dict[str, int] = Field(
        ..., description=_("Contagem de problemas por severidade")
    )
    checked_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da verificação"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class DetectDataQualityIssuesProtocol(ABC):
    """Protocolo para detecção de problemas de qualidade."""

    @abstractmethod
    async def check_completeness(
        self,
        data_source: str,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """
        Verifica completude dos dados (campos obrigatórios preenchidos).

        Args:
            data_source: Fonte de dados
            entity_type: Tipo de entidade
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de problemas de completude
        """
        pass

    @abstractmethod
    async def check_accuracy(
        self,
        data_source: str,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """
        Verifica acurácia dos dados (valores válidos e consistentes).

        Args:
            data_source: Fonte de dados
            entity_type: Tipo de entidade
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de problemas de acurácia
        """
        pass

    @abstractmethod
    async def check_timeliness(
        self,
        data_source: str,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """
        Verifica pontualidade dos dados (atualizações em tempo adequado).

        Args:
            data_source: Fonte de dados
            entity_type: Tipo de entidade
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de problemas de pontualidade
        """
        pass

    @abstractmethod
    async def check_consistency(
        self,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """
        Verifica consistência entre fontes de dados.

        Args:
            entity_type: Tipo de entidade
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de problemas de consistência
        """
        pass

    @abstractmethod
    async def calculate_quality_score(
        self, issues: list[QualityIssue], total_records: int
    ) -> float:
        """
        Calcula score geral de qualidade.

        Args:
            issues: Lista de problemas identificados
            total_records: Total de registros verificados

        Returns:
            Score de qualidade (0-100)
        """
        pass


class DetectDataQualityIssuesStub(DetectDataQualityIssuesProtocol):
    """Implementação stub para detecção de qualidade."""

    async def check_completeness(
        self,
        data_source: str,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """Verifica completude dos dados."""
        issues = []

        # Simular problema de completude
        if entity_type == "patient":
            issues.append(
                QualityIssue(
                    issue_id=f"compl_{data_source}_{entity_type}_001",
                    dimension="completeness",
                    severity="medium",
                    data_source=data_source,
                    entity_type=entity_type,
                    field_name="phone",
                    issue_description=_(
                        "Telefone de contato ausente em 15% dos registros"
                    ),
                    affected_records=128,
                    sample_records=["PAT001", "PAT045", "PAT123"],
                    recommended_action=_(
                        "Solicitar atualização cadastral no próximo atendimento"
                    ),
                )
            )

        return issues

    async def check_accuracy(
        self,
        data_source: str,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """Verifica acurácia dos dados."""
        issues = []

        if entity_type == "lab_result":
            issues.append(
                QualityIssue(
                    issue_id=f"acc_{data_source}_{entity_type}_001",
                    dimension="accuracy",
                    severity="high",
                    data_source=data_source,
                    entity_type=entity_type,
                    field_name="value",
                    issue_description=_(
                        "Valores numéricos fora de faixas fisiologicamente possíveis"
                    ),
                    affected_records=8,
                    sample_records=["LAB123", "LAB456"],
                    recommended_action=_(
                        "Revisar calibração de equipamentos e protocolo de digitação"
                    ),
                )
            )

        return issues

    async def check_timeliness(
        self,
        data_source: str,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """Verifica pontualidade dos dados."""
        issues = []

        if entity_type == "encounter":
            issues.append(
                QualityIssue(
                    issue_id=f"time_{data_source}_{entity_type}_001",
                    dimension="timeliness",
                    severity="low",
                    data_source=data_source,
                    entity_type=entity_type,
                    field_name="discharge_date",
                    issue_description=_(
                        "Fechamento de prontuário com atraso >24h em 5% dos casos"
                    ),
                    affected_records=42,
                    sample_records=["ENC234", "ENC567"],
                    recommended_action=_(
                        "Reforçar treinamento sobre prazos de documentação"
                    ),
                )
            )

        return issues

    async def check_consistency(
        self,
        entity_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[QualityIssue]:
        """Verifica consistência entre fontes."""
        issues = []

        if entity_type == "patient":
            issues.append(
                QualityIssue(
                    issue_id=f"cons_{entity_type}_001",
                    dimension="consistency",
                    severity="critical",
                    data_source="tasy,mv_soul",
                    entity_type=entity_type,
                    field_name="cpf",
                    issue_description=_(
                        "CPF divergente entre sistemas para o mesmo paciente"
                    ),
                    affected_records=3,
                    sample_records=["PAT789"],
                    recommended_action=_(
                        "Realizar reconciliação manual e definir sistema autoritativo"
                    ),
                )
            )

        return issues

    async def calculate_quality_score(
        self, issues: list[QualityIssue], total_records: int
    ) -> float:
        """Calcula score de qualidade."""
        if total_records == 0:
            return 100.0

        # Pesos por severidade
        severity_weights = {
            "low": 1,
            "medium": 3,
            "high": 7,
            "critical": 15,
        }

        # Calcular penalidade total
        penalty = sum(
            severity_weights.get(issue.severity, 1) * issue.affected_records
            for issue in issues
        )

        # Score = 100 - (penalidade / total_records * 100)
        score = max(0, 100 - (penalty / total_records * 100))

        return round(score, 2)


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa detecção de problemas de qualidade de dados.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado da verificação

    Raises:
        DataQualityException: Se houver erro na verificação
    """
    tenant = get_required_tenant()
    parsed_input = DetectDataQualityIssuesInput(**input_data)

    check_id = (
        f"quality_check_{int(parsed_input.period_start.timestamp())}_"
        f"{int(parsed_input.period_end.timestamp())}"
    )

    logger.info(
        _("Iniciando verificação de qualidade de dados"),
        extra={
            "tenant_id": tenant.id,
            "check_id": check_id,
            "dimensions": parsed_input.quality_dimensions,
            "sources": parsed_input.data_sources,
        },
    )

    start_time = datetime.utcnow()

    try:
        service = DetectDataQualityIssuesStub()

        all_issues = []

        # Verificar cada dimensão de qualidade
        for dimension in parsed_input.quality_dimensions:
            for data_source in parsed_input.data_sources:
                for entity_type in parsed_input.entity_types:
                    if dimension == "completeness":
                        issues = await service.check_completeness(
                            data_source,
                            entity_type,
                            parsed_input.period_start,
                            parsed_input.period_end,
                        )
                    elif dimension == "accuracy":
                        issues = await service.check_accuracy(
                            data_source,
                            entity_type,
                            parsed_input.period_start,
                            parsed_input.period_end,
                        )
                    elif dimension == "timeliness":
                        issues = await service.check_timeliness(
                            data_source,
                            entity_type,
                            parsed_input.period_start,
                            parsed_input.period_end,
                        )
                    else:
                        continue

                    all_issues.extend(issues)

            # Verificar consistência entre fontes
            if dimension == "consistency":
                for entity_type in parsed_input.entity_types:
                    issues = await service.check_consistency(
                        entity_type,
                        parsed_input.period_start,
                        parsed_input.period_end,
                    )
                    all_issues.extend(issues)

        # Filtrar por severidade
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        threshold_level = severity_order[parsed_input.severity_threshold]

        filtered_issues = [
            issue
            for issue in all_issues
            if severity_order.get(issue.severity, 0) >= threshold_level
        ]

        # Contar por severidade
        issues_by_severity = {
            "low": sum(1 for i in filtered_issues if i.severity == "low"),
            "medium": sum(1 for i in filtered_issues if i.severity == "medium"),
            "high": sum(1 for i in filtered_issues if i.severity == "high"),
            "critical": sum(1 for i in filtered_issues if i.severity == "critical"),
        }

        # Calcular score de qualidade
        total_records = 1000  # Simulado
        quality_score = await service.calculate_quality_score(
            filtered_issues, total_records
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = DetectDataQualityIssuesOutput(
            check_id=check_id,
            period_start=parsed_input.period_start,
            period_end=parsed_input.period_end,
            issues=filtered_issues,
            quality_score=quality_score,
            dimensions_checked=parsed_input.quality_dimensions,
            sources_checked=parsed_input.data_sources,
            total_records_checked=total_records,
            issues_by_severity=issues_by_severity,
            duration_ms=duration_ms,
        )

        # Métricas
        for dimension in parsed_input.quality_dimensions:
            quality_checks_total.labels(
                tenant_id=tenant.id,
                check_type=dimension,
                status="success",
            ).inc()

            quality_duration_seconds.labels(
                tenant_id=tenant.id,
                check_type=dimension,
            ).observe(duration_ms / 1000.0)

        # Atualizar gauge de problemas ativos
        for severity, count in issues_by_severity.items():
            for dimension in parsed_input.quality_dimensions:
                quality_issues_gauge.labels(
                    tenant_id=tenant.id,
                    severity=severity,
                    dimension=dimension,
                ).set(count)

        logger.info(
            _("Verificação de qualidade concluída"),
            extra={
                "tenant_id": tenant.id,
                "check_id": check_id,
                "issues_found": len(filtered_issues),
                "quality_score": quality_score,
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro na verificação de qualidade de dados"),
            extra={
                "tenant_id": tenant.id,
                "check_id": check_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise DataQualityException(
            message=_("Falha ao verificar qualidade de dados"),
            details={"check_id": check_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.services.detect-data-quality-issues"
