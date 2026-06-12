"""
Worker para otimização de estratégia de preços.

Analisa contratos com operadoras, benchmarks de mercado, identifica
oportunidades de negociação para maximização de receita.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
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
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
pricing_analyses_total = Counter(
    "pricing_analyses_total",
    "Total de análises de precificação realizadas",
    ["tenant_id", "analysis_type", "result"],
)
pricing_duration_seconds = Histogram(
    "pricing_duration_seconds",
    "Duração das análises de precificação em segundos",
    ["tenant_id"],
)


class PricingOptimizationError(DomainException):
    """Exceção para erros na otimização de preços."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="PricingOptimizationError",
            details=details or {},
        )


class OptimizePricingStrategyInput(BaseModel):
    """Input para otimização de estratégia de preços."""

    payer_id: str = Field(description=_("ID da operadora"))
    contract_id: str = Field(description=_("ID do contrato"))
    procedure_codes: list[str] | None = Field(
        default=None, description=_("Procedimentos específicos para análise")
    )
    include_market_benchmark: bool = Field(
        default=True, description=_("Incluir benchmark de mercado")
    )
    target_margin_percentage: Decimal = Field(
        default=Decimal("15.0"), description=_("Margem alvo em percentual")
    )
    analysis_scope: str = Field(
        default="full", description=_("Escopo: full, quick, procedures_only")
    )


class PricingOpportunity(BaseModel):
    """Modelo de oportunidade de precificação."""

    procedure_code: str = Field(description=_("Código TUSS/CBHPM"))
    procedure_description: str = Field(description=_("Descrição do procedimento"))
    current_price: Decimal = Field(description=_("Preço atual em R$"))
    market_average: Decimal = Field(description=_("Média de mercado em R$"))
    market_percentile_75: Decimal = Field(description=_("Percentil 75 do mercado"))
    suggested_price: Decimal = Field(description=_("Preço sugerido em R$"))
    price_increase_percentage: Decimal = Field(
        description=_("Aumento percentual sugerido")
    )
    annual_volume: int = Field(description=_("Volume anual do procedimento"))
    projected_revenue_increase: Decimal = Field(
        description=_("Aumento de receita projetado anual")
    )
    negotiation_priority: str = Field(
        description=_("Prioridade: critical, high, medium, low")
    )
    justification: str = Field(description=_("Justificativa para negociação"))


class OptimizePricingStrategyOutput(BaseModel):
    """Output da otimização de estratégia de preços."""

    analysis_id: str = Field(description=_("ID da análise"))
    contract_id: str = Field(description=_("ID do contrato"))
    payer_name: str = Field(description=_("Nome da operadora"))
    opportunities: list[PricingOpportunity] = Field(
        description=_("Oportunidades identificadas")
    )
    total_projected_increase: Decimal = Field(
        description=_("Aumento total projetado anual em R$")
    )
    current_annual_revenue: Decimal = Field(
        description=_("Receita anual atual do contrato")
    )
    optimized_annual_revenue: Decimal = Field(
        description=_("Receita anual otimizada projetada")
    )
    average_price_gap_percentage: Decimal = Field(
        description=_("Gap médio percentual vs mercado")
    )
    negotiation_recommendations: list[str] = Field(
        description=_("Recomendações para negociação")
    )
    market_benchmark_summary: dict[str, Any] = Field(
        description=_("Sumário do benchmark de mercado")
    )
    analyzed_at: datetime


class OptimizePricingStrategyProtocol(ABC):
    """Protocolo para otimização de estratégia de preços."""

    @abstractmethod
    async def execute(
        self, input_data: OptimizePricingStrategyInput
    ) -> OptimizePricingStrategyOutput:
        """Executa otimização de precificação."""
        pass


class OptimizePricingStrategyStub(OptimizePricingStrategyProtocol):
    """Implementação stub para otimização de estratégia de preços."""

    def __init__(self, ans_client: ANSClientProtocol):
        self.ans_client = ans_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: OptimizePricingStrategyInput
    ) -> OptimizePricingStrategyOutput:
        """
        Executa otimização de estratégia de preços.

        Analisa contratos atuais, compara com mercado, identifica gaps
        de precificação, sugere ajustes e prioriza negociações.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='ans/comp_ans_002',
                inputs={'analysis_scope': input_data.analysis_scope},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        analysis_id = self._generate_analysis_id(input_data.contract_id)

        logger.info(
            "Iniciando otimização de precificação",
            extra={
                "tenant_id": tenant.tenant_id,
                "contract_id": input_data.contract_id,
                "analysis_id": analysis_id,
            },
        )

        with pricing_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                # Buscar dados do contrato
                contract = await self._fetch_contract_details(
                    input_data.contract_id, input_data.payer_id
                )

                # Buscar benchmark de mercado
                market_data = {}
                if input_data.include_market_benchmark:
                    market_data = await self._fetch_market_benchmark(
                        procedure_codes=input_data.procedure_codes,
                        payer_type=contract.get("payer_type"),
                    )

                # Analisar gaps de precificação
                opportunities = self._analyze_pricing_gaps(
                    contract_prices=contract.get("prices", {}),
                    market_data=market_data,
                    annual_volumes=contract.get("volumes", {}),
                    target_margin=input_data.target_margin_percentage,
                )

                # Calcular projeções
                current_revenue = self._calculate_current_revenue(
                    contract.get("prices", {}), contract.get("volumes", {})
                )

                total_increase = sum(
                    opp.projected_revenue_increase for opp in opportunities
                )

                optimized_revenue = current_revenue + total_increase

                # Calcular gap médio
                avg_gap = self._calculate_average_gap(opportunities)

                # Gerar recomendações de negociação
                recommendations = self._generate_negotiation_recommendations(
                    opportunities=opportunities,
                    contract=contract,
                    market_data=market_data,
                )

                # Sumário de benchmark
                benchmark_summary = self._create_benchmark_summary(market_data)

                # Atualizar métricas
                pricing_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    analysis_type=input_data.analysis_scope,
                    result="success",
                ).inc()

                logger.info(
                    "Otimização de precificação concluída",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "opportunities_count": len(opportunities),
                        "projected_increase": float(total_increase),
                    },
                )

                return OptimizePricingStrategyOutput(
                    analysis_id=analysis_id,
                    contract_id=input_data.contract_id,
                    payer_name=contract.get("payer_name", "Operadora"),
                    opportunities=opportunities,
                    total_projected_increase=total_increase,
                    current_annual_revenue=current_revenue,
                    optimized_annual_revenue=optimized_revenue,
                    average_price_gap_percentage=avg_gap,
                    negotiation_recommendations=recommendations,
                    market_benchmark_summary=benchmark_summary,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                pricing_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    analysis_type=input_data.analysis_scope,
                    result="error",
                ).inc()
                logger.error(
                    "Erro na otimização de precificação",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                )
                raise PricingOptimizationError(
                    message=_("Erro ao otimizar estratégia de preços"),
                    details={
                        "analysis_id": analysis_id,
                        "contract_id": input_data.contract_id,
                        "error": str(e),
                    },
                )

    def _generate_analysis_id(self, contract_id: str) -> str:
        """Gera ID único para análise."""
        hash_input = f"{contract_id}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _fetch_contract_details(
        self, contract_id: str, payer_id: str
    ) -> dict[str, Any]:
        """Busca detalhes do contrato."""
        return {
            "contract_id": contract_id,
            "payer_id": payer_id,
            "payer_name": "Operadora XYZ",
            "payer_type": "health_insurance",
            "prices": {
                "10101012": Decimal("180.00"),
                "20101020": Decimal("450.00"),
            },
            "volumes": {"10101012": 1200, "20101020": 300},
        }

    async def _fetch_market_benchmark(
        self, procedure_codes: list[str] | None, payer_type: str
    ) -> dict[str, Any]:
        """Busca benchmark de mercado."""
        return {
            "10101012": {
                "average": Decimal("220.00"),
                "percentile_25": Decimal("190.00"),
                "percentile_50": Decimal("220.00"),
                "percentile_75": Decimal("250.00"),
                "percentile_90": Decimal("280.00"),
            },
            "20101020": {
                "average": Decimal("520.00"),
                "percentile_25": Decimal("480.00"),
                "percentile_50": Decimal("520.00"),
                "percentile_75": Decimal("560.00"),
                "percentile_90": Decimal("600.00"),
            },
        }

    def _analyze_pricing_gaps(
        self,
        contract_prices: dict[str, Decimal],
        market_data: dict[str, Any],
        annual_volumes: dict[str, int],
        target_margin: Decimal,
    ) -> list[PricingOpportunity]:
        """Analisa gaps de precificação."""
        opportunities = []

        for proc_code, current_price in contract_prices.items():
            if proc_code not in market_data:
                continue

            market = market_data[proc_code]
            market_avg = market["average"]
            market_p75 = market["percentile_75"]

            # Calcular preço sugerido (percentil 75)
            suggested_price = market_p75
            increase_pct = (
                (suggested_price - current_price) / current_price * 100
            )

            # Projetar aumento de receita
            volume = annual_volumes.get(proc_code, 0)
            revenue_increase = (suggested_price - current_price) * volume

            # Determinar prioridade
            if increase_pct > 20:
                priority = "critical"
            elif increase_pct > 10:
                priority = "high"
            elif increase_pct > 5:
                priority = "medium"
            else:
                priority = "low"

            opportunities.append(
                PricingOpportunity(
                    procedure_code=proc_code,
                    procedure_description=_("Consulta médica"),
                    current_price=current_price,
                    market_average=market_avg,
                    market_percentile_75=market_p75,
                    suggested_price=suggested_price,
                    price_increase_percentage=increase_pct,
                    annual_volume=volume,
                    projected_revenue_increase=revenue_increase,
                    negotiation_priority=priority,
                    justification=_(
                        "Preço atual {gap}% abaixo do percentil 75 do mercado"
                    ).format(gap=float(increase_pct)),
                )
            )

        return opportunities

    def _calculate_current_revenue(
        self, prices: dict[str, Decimal], volumes: dict[str, int]
    ) -> Decimal:
        """Calcula receita anual atual."""
        total = Decimal("0")
        for proc_code, price in prices.items():
            volume = volumes.get(proc_code, 0)
            total += price * volume
        return total

    def _calculate_average_gap(
        self, opportunities: list[PricingOpportunity]
    ) -> Decimal:
        """Calcula gap médio percentual."""
        if not opportunities:
            return Decimal("0")
        total_gap = sum(opp.price_increase_percentage for opp in opportunities)
        return total_gap / len(opportunities)

    def _generate_negotiation_recommendations(
        self,
        opportunities: list[PricingOpportunity],
        contract: dict[str, Any],
        market_data: dict[str, Any],
    ) -> list[str]:
        """Gera recomendações de negociação."""
        recommendations = []

        critical = [o for o in opportunities if o.negotiation_priority == "critical"]
        if critical:
            recommendations.append(
                _(
                    "Priorizar {count} procedimentos com gap crítico (>20%) na próxima negociação"
                ).format(count=len(critical))
            )

        total_increase = sum(o.projected_revenue_increase for o in opportunities)
        if total_increase > Decimal("50000"):
            recommendations.append(
                _(
                    "Potencial de aumento de R$ {amount:,.2f}/ano justifica renegociação completa do contrato"
                ).format(amount=float(total_increase))
            )

        recommendations.append(
            _("Usar percentil 75 de mercado como baseline para negociação")
        )

        return recommendations

    def _create_benchmark_summary(self, market_data: dict[str, Any]) -> dict[str, Any]:
        """Cria sumário do benchmark de mercado."""
        return {
            "procedures_analyzed": len(market_data),
            "data_source": "ANS + Mercado Regional",
            "last_updated": datetime.now().isoformat(),
            "confidence_level": "high",
        }


# Task topic para Camunda
TOPIC = "optimize-pricing-strategy"
