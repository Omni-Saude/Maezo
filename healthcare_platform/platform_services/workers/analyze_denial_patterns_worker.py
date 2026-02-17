"""
Worker para análise de padrões de glosa.

Analisa histórico de glosas por operadora, procedimento e código de negativa,
utilizando reconhecimento de padrões ML para prevenção proativa.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
denial_analyses_total = Counter(
    "denial_analyses_total",
    "Total de análises de glosa realizadas",
    ["tenant_id", "payer_type", "result"],
)
denial_duration_seconds = Histogram(
    "denial_duration_seconds",
    "Duração das análises de glosa em segundos",
    ["tenant_id"],
)
patterns_detected_gauge = Gauge(
    "denial_patterns_detected",
    "Número de padrões de glosa detectados",
    ["tenant_id", "pattern_type"],
)


class DenialPatternAnalysisError(DomainException):
    """    Exceção para erros na análise de padrões de glosa.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="DENIAL_PATTERN_ANALYSIS_ERROR",
            bpmn_error_code="DenialPatternAnalysisError",
            details=details or {},
        )


class AnalyzeDenialPatternsInput(BaseModel):
    """Input para análise de padrões de glosa."""

    payer_id: str = Field(description=_("ID da operadora"))
    analysis_period_days: int = Field(
        default=90, description=_("Período de análise em dias")
    )
    procedure_filter: list[str] | None = Field(
        default=None, description=_("Filtro de procedimentos específicos")
    )
    provider_id: str | None = Field(
        default=None, description=_("ID do prestador para análise específica")
    )
    include_ml_predictions: bool = Field(
        default=True, description=_("Incluir predições ML")
    )
    min_pattern_frequency: int = Field(
        default=3, description=_("Frequência mínima para considerar padrão")
    )


class DenialPattern(BaseModel):
    """Modelo de padrão de glosa identificado."""

    pattern_id: str = Field(description=_("ID único do padrão"))
    denial_reason_code: str = Field(description=_("Código de motivo de glosa"))
    denial_reason_description: str = Field(description=_("Descrição do motivo"))
    affected_procedures: list[str] = Field(
        description=_("Códigos de procedimentos afetados")
    )
    frequency: int = Field(description=_("Frequência de ocorrência"))
    total_denied_amount: Decimal = Field(description=_("Valor total glosado em R$"))
    average_denial_rate: Decimal = Field(description=_("Taxa média de glosa 0-1"))
    root_causes: list[str] = Field(description=_("Causas raízes identificadas"))
    prevention_recommendations: list[str] = Field(
        description=_("Recomendações de prevenção")
    )
    risk_score: Decimal = Field(description=_("Score de risco 0-1"))
    trend: str = Field(description=_("Tendência: increasing, stable, decreasing"))


class MLPrediction(BaseModel):
    """Modelo de predição ML para glosas futuras."""

    procedure_code: str = Field(description=_("Código do procedimento"))
    predicted_denial_probability: Decimal = Field(
        description=_("Probabilidade de glosa 0-1")
    )
    confidence_interval: tuple[Decimal, Decimal] = Field(
        description=_("Intervalo de confiança 95%")
    )
    key_risk_factors: list[str] = Field(description=_("Principais fatores de risco"))
    model_accuracy: Decimal = Field(description=_("Acurácia do modelo"))


class AnalyzeDenialPatternsOutput(BaseModel):
    """Output da análise de padrões de glosa."""

    analysis_id: str = Field(description=_("ID da análise"))
    payer_id: str = Field(description=_("ID da operadora"))
    analysis_period_start: datetime = Field(description=_("Início do período"))
    analysis_period_end: datetime = Field(description=_("Fim do período"))
    patterns: list[DenialPattern] = Field(description=_("Padrões identificados"))
    ml_predictions: list[MLPrediction] = Field(
        description=_("Predições ML futuras")
    )
    total_denials_analyzed: int = Field(description=_("Total de glosas analisadas"))
    total_denied_amount: Decimal = Field(description=_("Valor total glosado"))
    overall_denial_rate: Decimal = Field(description=_("Taxa geral de glosa"))
    high_risk_patterns_count: int = Field(
        description=_("Número de padrões de alto risco")
    )
    actionable_insights: list[str] = Field(
        description=_("Insights acionáveis prioritários")
    )
    analyzed_at: datetime


class AnalyzeDenialPatternsProtocol(ABC):
    """Protocolo para análise de padrões de glosa."""

    @abstractmethod
    async def execute(
        self, input_data: AnalyzeDenialPatternsInput
    ) -> AnalyzeDenialPatternsOutput:
        """Executa análise de padrões de glosa."""
        pass


class AnalyzeDenialPatternsStub(AnalyzeDenialPatternsProtocol):
    """Implementação stub para análise de padrões de glosa."""

    def __init__(self, ans_client: ANSClientProtocol):
        self.ans_client = ans_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: AnalyzeDenialPatternsInput
    ) -> AnalyzeDenialPatternsOutput:
        """
        Executa análise de padrões de glosa.

        Analisa histórico de negativas, identifica padrões recorrentes,
        aplica ML para predições, gera recomendações de prevenção.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='tiss/comp_tiss_001',
                inputs={'payer_code': input_data.payer_code},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        analysis_id = self._generate_analysis_id(input_data.payer_id)

        logger.info(
            "Iniciando análise de padrões de glosa",
            extra={
                "tenant_id": tenant.tenant_id,
                "payer_id": input_data.payer_id,
                "analysis_id": analysis_id,
            },
        )

        with denial_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                # Definir período de análise
                end_date = datetime.now()
                start_date = end_date - timedelta(days=input_data.analysis_period_days)

                # Buscar histórico de glosas
                denials = await self._fetch_denial_history(
                    payer_id=input_data.payer_id,
                    start_date=start_date,
                    end_date=end_date,
                    procedure_filter=input_data.procedure_filter,
                    provider_id=input_data.provider_id,
                )

                # Identificar padrões
                patterns = self._identify_patterns(
                    denials=denials,
                    min_frequency=input_data.min_pattern_frequency,
                )

                # ML predictions
                ml_predictions = []
                if input_data.include_ml_predictions:
                    ml_predictions = await self._generate_ml_predictions(
                        denials=denials, patterns=patterns
                    )

                # Calcular estatísticas
                total_denials = len(denials)
                total_amount = sum(d.get("denied_amount", Decimal("0")) for d in denials)
                overall_rate = self._calculate_denial_rate(denials)

                # Contar padrões de alto risco
                high_risk_count = sum(
                    1 for p in patterns if p.risk_score > Decimal("0.7")
                )

                # Gerar insights acionáveis
                insights = self._generate_actionable_insights(
                    patterns=patterns, predictions=ml_predictions
                )

                # Atualizar métricas
                denial_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    payer_type="health_insurance",
                    result="success",
                ).inc()

                for pattern in patterns:
                    patterns_detected_gauge.labels(
                        tenant_id=tenant.tenant_id,
                        pattern_type=pattern.denial_reason_code,
                    ).set(pattern.frequency)

                logger.info(
                    "Análise de padrões de glosa concluída",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "patterns_count": len(patterns),
                        "high_risk_count": high_risk_count,
                    },
                )

                return AnalyzeDenialPatternsOutput(
                    analysis_id=analysis_id,
                    payer_id=input_data.payer_id,
                    analysis_period_start=start_date,
                    analysis_period_end=end_date,
                    patterns=patterns,
                    ml_predictions=ml_predictions,
                    total_denials_analyzed=total_denials,
                    total_denied_amount=total_amount,
                    overall_denial_rate=overall_rate,
                    high_risk_patterns_count=high_risk_count,
                    actionable_insights=insights,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                denial_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    payer_type="health_insurance",
                    result="error",
                ).inc()
                logger.error(
                    "Erro na análise de padrões de glosa",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                )
                raise DenialPatternAnalysisError(
                    message=_("Erro ao analisar padrões de glosa"),
                    details={
                        "analysis_id": analysis_id,
                        "payer_id": input_data.payer_id,
                        "error": str(e),
                    },
                )

    def _generate_analysis_id(self, payer_id: str) -> str:
        """Gera ID único para análise."""
        hash_input = f"{payer_id}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _fetch_denial_history(
        self,
        payer_id: str,
        start_date: datetime,
        end_date: datetime,
        procedure_filter: list[str] | None,
        provider_id: str | None,
    ) -> list[dict[str, Any]]:
        """Busca histórico de glosas."""
        return [
            {
                "denial_id": "D001",
                "procedure_code": "10101012",
                "denial_reason_code": "D01",
                "denied_amount": Decimal("150.00"),
                "denial_date": datetime.now() - timedelta(days=30),
            },
            {
                "denial_id": "D002",
                "procedure_code": "10101012",
                "denial_reason_code": "D01",
                "denied_amount": Decimal("150.00"),
                "denial_date": datetime.now() - timedelta(days=20),
            },
            {
                "denial_id": "D003",
                "procedure_code": "10101012",
                "denial_reason_code": "D01",
                "denied_amount": Decimal("150.00"),
                "denial_date": datetime.now() - timedelta(days=10),
            },
        ]

    def _identify_patterns(
        self, denials: list[dict[str, Any]], min_frequency: int
    ) -> list[DenialPattern]:
        """Identifica padrões recorrentes de glosa."""
        patterns = []

        # Agrupar por motivo de negativa
        reason_groups: dict[str, list[dict[str, Any]]] = {}
        for denial in denials:
            reason = denial.get("denial_reason_code", "UNKNOWN")
            if reason not in reason_groups:
                reason_groups[reason] = []
            reason_groups[reason].append(denial)

        # Criar padrões para grupos frequentes
        for reason_code, group in reason_groups.items():
            if len(group) >= min_frequency:
                total_amount = sum(
                    d.get("denied_amount", Decimal("0")) for d in group
                )
                procedures = list(set(d.get("procedure_code", "") for d in group))

                patterns.append(
                    DenialPattern(
                        pattern_id=self._generate_pattern_id(reason_code),
                        denial_reason_code=reason_code,
                        denial_reason_description=_(
                            "Documentação insuficiente para procedimento"
                        ),
                        affected_procedures=procedures,
                        frequency=len(group),
                        total_denied_amount=total_amount,
                        average_denial_rate=Decimal("0.35"),
                        root_causes=[
                            _("Falta de justificativa clínica"),
                            _("Documentação incompleta"),
                        ],
                        prevention_recommendations=[
                            _("Incluir relatório médico detalhado"),
                            _("Documentar indicação clínica"),
                        ],
                        risk_score=Decimal("0.75"),
                        trend="increasing",
                    )
                )

        return patterns

    def _generate_pattern_id(self, reason_code: str) -> str:
        """Gera ID único para padrão."""
        hash_input = f"{reason_code}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:12]

    async def _generate_ml_predictions(
        self, denials: list[dict[str, Any]], patterns: list[DenialPattern]
    ) -> list[MLPrediction]:
        """Gera predições ML para glosas futuras."""
        return [
            MLPrediction(
                procedure_code="10101012",
                predicted_denial_probability=Decimal("0.42"),
                confidence_interval=(Decimal("0.38"), Decimal("0.46")),
                key_risk_factors=[
                    _("Operadora com alta taxa histórica"),
                    _("Procedimento frequentemente glosado"),
                ],
                model_accuracy=Decimal("0.87"),
            )
        ]

    def _calculate_denial_rate(self, denials: list[dict[str, Any]]) -> Decimal:
        """Calcula taxa geral de glosa."""
        if not denials:
            return Decimal("0")
        return Decimal("0.28")

    def _generate_actionable_insights(
        self, patterns: list[DenialPattern], predictions: list[MLPrediction]
    ) -> list[str]:
        """Gera insights acionáveis prioritários."""
        insights = []

        high_risk = [p for p in patterns if p.risk_score > Decimal("0.7")]
        if high_risk:
            insights.append(
                _(
                    "Priorizar ação em {count} padrões de alto risco identificados"
                ).format(count=len(high_risk))
            )

        increasing_trends = [p for p in patterns if p.trend == "increasing"]
        if increasing_trends:
            insights.append(
                _("Tendência crescente em {count} tipos de glosa - ação imediata requerida").format(
                    count=len(increasing_trends)
                )
            )

        return insights


# Task topic para Camunda
TOPIC = "analyze-denial-patterns"
