"""
Worker para recomendação de bundles de procedimentos.

Analisa co-ocorrência de procedimentos, calcula preços de bundle,
projeta economia e identifica oportunidades de pagamento empacotado.

Archetype: FINANCIAL_CALCULATION
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
bundle_analyses_total = Counter(
    "bundle_analyses_total",
    "Total de análises de bundle realizadas",
    ["tenant_id", "bundle_type", "result"],
)
bundle_duration_seconds = Histogram(
    "bundle_duration_seconds",
    "Duração das análises de bundle em segundos",
    ["tenant_id"],
)


class BundleRecommendationError(DomainException):
    """Exceção para erros na recomendação de bundles."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="BUNDLE_RECOMMENDATION_ERROR",
            bpmn_error_code="BundleRecommendationError",
            details=details or {},
        )


class RecommendProcedureBundlesInput(BaseModel):
    """Input para recomendação de bundles de procedimentos."""

    payer_id: str | None = Field(
        default=None, description=_("ID da operadora específica")
    )
    analysis_period_days: int = Field(
        default=180, description=_("Período de análise em dias")
    )
    min_co_occurrence_count: int = Field(
        default=10, description=_("Mínimo de co-ocorrências para considerar bundle")
    )
    min_co_occurrence_rate: Decimal = Field(
        default=Decimal("0.7"),
        description=_("Taxa mínima de co-ocorrência 0-1"),
    )
    target_discount_percentage: Decimal = Field(
        default=Decimal("10.0"),
        description=_("Desconto alvo do bundle em percentual"),
    )


class ProcedureBundle(BaseModel):
    """Modelo de bundle de procedimentos recomendado."""

    bundle_id: str = Field(description=_("ID único do bundle"))
    bundle_name: str = Field(description=_("Nome descritivo do bundle"))
    procedure_codes: list[str] = Field(
        description=_("Códigos TUSS/CBHPM incluídos")
    )
    procedure_descriptions: list[str] = Field(
        description=_("Descrições dos procedimentos")
    )
    co_occurrence_count: int = Field(
        description=_("Número de vezes que ocorreram juntos")
    )
    co_occurrence_rate: Decimal = Field(
        description=_("Taxa de co-ocorrência 0-1")
    )
    individual_prices_sum: Decimal = Field(
        description=_("Soma dos preços individuais em R$")
    )
    suggested_bundle_price: Decimal = Field(
        description=_("Preço sugerido do bundle em R$")
    )
    discount_percentage: Decimal = Field(description=_("Percentual de desconto"))
    discount_amount: Decimal = Field(description=_("Valor do desconto em R$"))
    annual_volume_estimate: int = Field(
        description=_("Volume anual estimado do bundle")
    )
    projected_annual_savings: Decimal = Field(
        description=_("Economia anual projetada em R$")
    )
    patient_satisfaction_impact: str = Field(
        description=_("Impacto na satisfação: high, medium, low")
    )
    implementation_priority: str = Field(
        description=_("Prioridade: critical, high, medium, low")
    )


class RecommendProcedureBundlesOutput(BaseModel):
    """Output da recomendação de bundles."""

    analysis_id: str = Field(description=_("ID da análise"))
    payer_id: str | None = Field(description=_("ID da operadora"))
    analysis_period_start: datetime = Field(description=_("Início do período"))
    analysis_period_end: datetime = Field(description=_("Fim do período"))
    recommended_bundles: list[ProcedureBundle] = Field(
        description=_("Bundles recomendados")
    )
    total_procedures_analyzed: int = Field(
        description=_("Total de procedimentos analisados")
    )
    total_projected_savings: Decimal = Field(
        description=_("Economia total projetada anual em R$")
    )
    average_discount_percentage: Decimal = Field(
        description=_("Desconto médio percentual dos bundles")
    )
    implementation_recommendations: list[str] = Field(
        description=_("Recomendações para implementação")
    )
    market_benchmark: dict[str, Any] = Field(
        description=_("Benchmark de bundles no mercado")
    )
    analyzed_at: datetime


class RecommendProcedureBundlesProtocol(ABC):
    """Protocolo para recomendação de bundles de procedimentos."""

    @abstractmethod
    async def execute(
        self, input_data: RecommendProcedureBundlesInput
    ) -> RecommendProcedureBundlesOutput:
        """Executa recomendação de bundles."""
        pass


class RecommendProcedureBundlesStub(RecommendProcedureBundlesProtocol):
    """Implementação stub para recomendação de bundles."""

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: RecommendProcedureBundlesInput
    ) -> RecommendProcedureBundlesOutput:
        """
        Executa recomendação de bundles de procedimentos.

        Analisa co-ocorrência histórica, calcula preços otimizados,
        projeta economia e prioriza implementação.
        """
        tenant = get_required_tenant()
        _dmn = get_dmn_service()
        try:
            _dmn_result = _dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='tiss/comp_tiss_003',
                inputs={'procedure_code': input_data.procedure_code},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        analysis_id = self._generate_analysis_id()

        logger.info(
            "Iniciando análise de bundles de procedimentos",
            extra={
                "tenant_id": tenant.tenant_id,
                "analysis_id": analysis_id,
            },
        )

        with bundle_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                # Definir período
                end_date = datetime.now()
                start_date = end_date - timedelta(days=input_data.analysis_period_days)

                # Buscar dados de co-ocorrência
                co_occurrences = await self._fetch_co_occurrence_data(
                    payer_id=input_data.payer_id,
                    start_date=start_date,
                    end_date=end_date,
                )

                # Filtrar por critérios
                filtered = self._filter_by_criteria(
                    co_occurrences=co_occurrences,
                    min_count=input_data.min_co_occurrence_count,
                    min_rate=input_data.min_co_occurrence_rate,
                )

                # Criar bundles recomendados
                bundles = await self._create_bundle_recommendations(
                    co_occurrences=filtered,
                    target_discount=input_data.target_discount_percentage,
                )

                # Calcular estatísticas
                total_procedures = len(set(
                    proc for bundle in bundles for proc in bundle.procedure_codes
                ))

                total_savings = sum(
                    bundle.projected_annual_savings for bundle in bundles
                )

                avg_discount = (
                    sum(bundle.discount_percentage for bundle in bundles)
                    / len(bundles)
                    if bundles
                    else Decimal("0")
                )

                # Gerar recomendações de implementação
                impl_recommendations = self._generate_implementation_recommendations(
                    bundles=bundles
                )

                # Benchmark de mercado
                market_benchmark = self._get_market_benchmark()

                # Atualizar métricas
                bundle_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    bundle_type="procedure",
                    result="success",
                ).inc()

                logger.info(
                    "Análise de bundles concluída",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "bundles_count": len(bundles),
                        "projected_savings": float(total_savings),
                    },
                )

                return RecommendProcedureBundlesOutput(
                    analysis_id=analysis_id,
                    payer_id=input_data.payer_id,
                    analysis_period_start=start_date,
                    analysis_period_end=end_date,
                    recommended_bundles=bundles,
                    total_procedures_analyzed=total_procedures,
                    total_projected_savings=total_savings,
                    average_discount_percentage=avg_discount,
                    implementation_recommendations=impl_recommendations,
                    market_benchmark=market_benchmark,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                bundle_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    bundle_type="procedure",
                    result="error",
                ).inc()
                logger.error(
                    "Erro na análise de bundles",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                )
                raise BundleRecommendationError(
                    message=_("Erro ao recomendar bundles de procedimentos"),
                    details={
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                ) from e

    def _generate_analysis_id(self) -> str:
        """Gera ID único para análise."""
        hash_input = f"bundle{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _fetch_co_occurrence_data(
        self,
        payer_id: str | None,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Busca dados de co-ocorrência de procedimentos."""
        return [
            {
                "procedures": ["10101012", "20101020", "30101015"],
                "count": 45,
                "total_encounters": 50,
                "rate": Decimal("0.9"),
            },
            {
                "procedures": ["40101018", "50101025"],
                "count": 30,
                "total_encounters": 35,
                "rate": Decimal("0.86"),
            },
        ]

    def _filter_by_criteria(
        self,
        co_occurrences: list[dict[str, Any]],
        min_count: int,
        min_rate: Decimal,
    ) -> list[dict[str, Any]]:
        """Filtra co-ocorrências por critérios."""
        return [
            co for co in co_occurrences
            if co["count"] >= min_count and co["rate"] >= min_rate
        ]

    async def _create_bundle_recommendations(
        self,
        co_occurrences: list[dict[str, Any]],
        target_discount: Decimal,
    ) -> list[ProcedureBundle]:
        """Cria recomendações de bundles."""
        bundles = []

        for _idx, co_occ in enumerate(co_occurrences):
            procedures = co_occ["procedures"]
            count = co_occ["count"]
            rate = co_occ["rate"]

            # Buscar preços individuais
            individual_prices = await self._fetch_procedure_prices(procedures)
            total_individual = sum(individual_prices.values())

            # Calcular preço do bundle com desconto
            discount_decimal = target_discount / 100
            bundle_price = total_individual * (Decimal("1") - discount_decimal)
            discount_amount = total_individual - bundle_price

            # Estimar volume anual
            annual_volume = int(count * (365 / 180))  # Anualizar

            # Projetar economia
            annual_savings = discount_amount * annual_volume

            # Determinar prioridade
            if annual_savings > Decimal("50000"):
                priority = "critical"
            elif annual_savings > Decimal("20000"):
                priority = "high"
            elif annual_savings > Decimal("5000"):
                priority = "medium"
            else:
                priority = "low"

            bundles.append(
                ProcedureBundle(
                    bundle_id=self._generate_bundle_id(procedures),
                    bundle_name=self._generate_bundle_name(procedures),
                    procedure_codes=procedures,
                    procedure_descriptions=[
                        _("Consulta"), _("Exame"), _("Procedimento")
                    ][:len(procedures)],
                    co_occurrence_count=count,
                    co_occurrence_rate=rate,
                    individual_prices_sum=total_individual,
                    suggested_bundle_price=bundle_price,
                    discount_percentage=target_discount,
                    discount_amount=discount_amount,
                    annual_volume_estimate=annual_volume,
                    projected_annual_savings=annual_savings,
                    patient_satisfaction_impact="high" if rate > Decimal("0.8") else "medium",
                    implementation_priority=priority,
                )
            )

        return bundles

    def _generate_bundle_id(self, procedures: list[str]) -> str:
        """Gera ID único para bundle."""
        proc_str = "_".join(sorted(procedures))
        return hashlib.sha256(proc_str.encode()).hexdigest()[:12]

    def _generate_bundle_name(self, procedures: list[str]) -> str:
        """Gera nome descritivo para bundle."""
        if len(procedures) == 2:
            return _("Bundle Consulta + Exame")
        elif len(procedures) == 3:
            return _("Bundle Consulta + Exame + Procedimento")
        else:
            return _("Bundle Múltiplos Procedimentos")

    async def _fetch_procedure_prices(
        self, procedures: list[str]
    ) -> dict[str, Decimal]:
        """Busca preços dos procedimentos."""
        return {
            proc: Decimal("200.00") for proc in procedures
        }

    def _generate_implementation_recommendations(
        self, bundles: list[ProcedureBundle]
    ) -> list[str]:
        """Gera recomendações de implementação."""
        recommendations = []

        critical = [b for b in bundles if b.implementation_priority == "critical"]
        if critical:
            recommendations.append(
                _(
                    "Priorizar implementação de {count} bundle(s) crítico(s) com alto impacto financeiro"
                ).format(count=len(critical))
            )

        high_rate = [b for b in bundles if b.co_occurrence_rate > Decimal("0.85")]
        if high_rate:
            recommendations.append(
                _(
                    "Bundles com taxa de co-ocorrência >85% têm alta probabilidade de adesão"
                )
            )

        recommendations.append(
            _("Implementar gradualmente, começando com 1-2 bundles piloto")
        )

        recommendations.append(
            _("Comunicar claramente economia para pacientes e operadoras")
        )

        return recommendations

    def _get_market_benchmark(self) -> dict[str, Any]:
        """Obtém benchmark de mercado."""
        return {
            "average_bundle_discount": Decimal("12.0"),
            "common_bundle_types": [
                "Consulta + Exames",
                "Cirurgia + Anestesia + Sala",
                "Parto + Internação + Procedimentos",
            ],
            "adoption_rate": Decimal("0.35"),
            "patient_satisfaction_increase": Decimal("0.18"),
        }


# Task topic para Camunda
TOPIC = "platform.recommend_procedure_bundles"
