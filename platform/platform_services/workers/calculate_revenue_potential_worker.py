"""
Worker para cálculo de potencial de receita.

Projeta receita sob diferentes estratégias: crescimento de volume,
mudança de mix de operadoras, otimização de preços, e combinações.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)

# Prometheus metrics
potential_calculations_total = Counter(
    "potential_calculations_total",
    "Total de cálculos de potencial realizados",
    ["tenant_id", "scenario_type", "result"],
)
potential_duration_seconds = Histogram(
    "potential_duration_seconds",
    "Duração dos cálculos de potencial em segundos",
    ["tenant_id"],
)


class RevenuePotentialCalculationError(DomainException):
    """Exceção para erros no cálculo de potencial de receita."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="REVENUE_POTENTIAL_CALCULATION_ERROR",
            bpmn_error_code="RevenuePotentialCalculationError",
            details=details or {},
        )


class CalculateRevenuePotentialInput(BaseModel):
    """Input para cálculo de potencial de receita."""

    current_annual_revenue: Decimal = Field(
        description=_("Receita anual atual em R$")
    )
    volume_growth_scenarios: list[Decimal] = Field(
        default=[Decimal("5.0"), Decimal("10.0"), Decimal("15.0")],
        description=_("Cenários de crescimento de volume em percentual"),
    )
    pricing_optimization_scenarios: list[Decimal] = Field(
        default=[Decimal("5.0"), Decimal("10.0"), Decimal("15.0")],
        description=_("Cenários de otimização de preços em percentual"),
    )
    payer_mix_scenarios: list[dict[str, Any]] | None = Field(
        default=None,
        description=_("Cenários de mudança de mix de operadoras"),
    )
    include_bundle_impact: bool = Field(
        default=True, description=_("Incluir impacto de bundles")
    )
    include_coding_improvements: bool = Field(
        default=True, description=_("Incluir melhorias de codificação")
    )
    time_horizon_months: int = Field(
        default=12, description=_("Horizonte de tempo em meses")
    )


class RevenueScenario(BaseModel):
    """Modelo de cenário de receita."""

    scenario_id: str = Field(description=_("ID único do cenário"))
    scenario_name: str = Field(description=_("Nome do cenário"))
    scenario_type: str = Field(
        description=_("Tipo: volume_growth, pricing, payer_mix, combined")
    )
    baseline_revenue: Decimal = Field(description=_("Receita baseline em R$"))
    projected_revenue: Decimal = Field(description=_("Receita projetada em R$"))
    revenue_increase: Decimal = Field(description=_("Aumento de receita em R$"))
    revenue_increase_percentage: Decimal = Field(
        description=_("Aumento percentual")
    )
    key_drivers: list[str] = Field(description=_("Principais drivers do cenário"))
    assumptions: list[str] = Field(description=_("Premissas do cenário"))
    implementation_difficulty: str = Field(
        description=_("Dificuldade: low, medium, high")
    )
    time_to_implement_months: int = Field(
        description=_("Tempo para implementar em meses")
    )
    risk_level: str = Field(description=_("Nível de risco: low, medium, high"))
    confidence_level: Decimal = Field(description=_("Nível de confiança 0-1"))


class CalculateRevenuePotentialOutput(BaseModel):
    """Output do cálculo de potencial de receita."""

    calculation_id: str = Field(description=_("ID do cálculo"))
    current_annual_revenue: Decimal = Field(description=_("Receita anual atual"))
    scenarios: list[RevenueScenario] = Field(description=_("Cenários projetados"))
    best_case_scenario: RevenueScenario = Field(
        description=_("Melhor cenário identificado")
    )
    conservative_scenario: RevenueScenario = Field(
        description=_("Cenário conservador")
    )
    recommended_scenario: RevenueScenario = Field(
        description=_("Cenário recomendado")
    )
    maximum_potential_increase: Decimal = Field(
        description=_("Aumento máximo potencial em R$")
    )
    maximum_potential_percentage: Decimal = Field(
        description=_("Aumento máximo percentual")
    )
    strategic_recommendations: list[str] = Field(
        description=_("Recomendações estratégicas")
    )
    action_plan: dict[str, Any] = Field(description=_("Plano de ação sugerido"))
    calculated_at: datetime


class CalculateRevenuePotentialProtocol(ABC):
    """Protocolo para cálculo de potencial de receita."""

    @abstractmethod
    async def execute(
        self, input_data: CalculateRevenuePotentialInput
    ) -> CalculateRevenuePotentialOutput:
        """Executa cálculo de potencial de receita."""
        pass


class CalculateRevenuePotentialStub(CalculateRevenuePotentialProtocol):
    """Implementação stub para cálculo de potencial de receita."""

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: CalculateRevenuePotentialInput
    ) -> CalculateRevenuePotentialOutput:
        """
        Executa cálculo de potencial de receita.

        Projeta receita sob múltiplos cenários, identifica melhor caso,
        cenário conservador e recomendado, gera plano de ação.
        """
        tenant = get_required_tenant()
        calculation_id = self._generate_calculation_id()

        logger.info(
            "Iniciando cálculo de potencial de receita",
            extra={
                "tenant_id": tenant.tenant_id,
                "calculation_id": calculation_id,
            },
        )

        with potential_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                scenarios: list[RevenueScenario] = []

                # Cenários de crescimento de volume
                for growth_pct in input_data.volume_growth_scenarios:
                    scenario = self._create_volume_growth_scenario(
                        baseline=input_data.current_annual_revenue,
                        growth_pct=growth_pct,
                    )
                    scenarios.append(scenario)

                # Cenários de otimização de preços
                for pricing_pct in input_data.pricing_optimization_scenarios:
                    scenario = self._create_pricing_scenario(
                        baseline=input_data.current_annual_revenue,
                        pricing_pct=pricing_pct,
                    )
                    scenarios.append(scenario)

                # Cenários de mix de operadoras
                if input_data.payer_mix_scenarios:
                    for mix_scenario in input_data.payer_mix_scenarios:
                        scenario = self._create_payer_mix_scenario(
                            baseline=input_data.current_annual_revenue,
                            mix_data=mix_scenario,
                        )
                        scenarios.append(scenario)

                # Cenários combinados
                combined = self._create_combined_scenarios(
                    baseline=input_data.current_annual_revenue,
                    volume_growth=input_data.volume_growth_scenarios[0],
                    pricing_improvement=input_data.pricing_optimization_scenarios[0],
                )
                scenarios.extend(combined)

                # Adicionar impactos de bundles
                if input_data.include_bundle_impact:
                    bundle_scenario = self._create_bundle_scenario(
                        baseline=input_data.current_annual_revenue
                    )
                    scenarios.append(bundle_scenario)

                # Adicionar melhorias de codificação
                if input_data.include_coding_improvements:
                    coding_scenario = self._create_coding_improvement_scenario(
                        baseline=input_data.current_annual_revenue
                    )
                    scenarios.append(coding_scenario)

                # Identificar cenários chave
                best_case = max(
                    scenarios, key=lambda s: s.projected_revenue
                )

                conservative = min(
                    [s for s in scenarios if s.risk_level == "low"],
                    key=lambda s: s.projected_revenue,
                    default=scenarios[0],
                )

                recommended = self._identify_recommended_scenario(scenarios)

                # Calcular potencial máximo
                max_increase = best_case.revenue_increase
                max_percentage = best_case.revenue_increase_percentage

                # Gerar recomendações estratégicas
                strategic_recs = self._generate_strategic_recommendations(
                    scenarios=scenarios,
                    recommended=recommended,
                )

                # Criar plano de ação
                action_plan = self._create_action_plan(
                    recommended=recommended,
                    scenarios=scenarios,
                )

                # Atualizar métricas
                potential_calculations_total.labels(
                    tenant_id=tenant.tenant_id,
                    scenario_type="combined",
                    result="success",
                ).inc()

                logger.info(
                    "Cálculo de potencial concluído",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "calculation_id": calculation_id,
                        "scenarios_count": len(scenarios),
                        "max_potential": float(max_increase),
                    },
                )

                return CalculateRevenuePotentialOutput(
                    calculation_id=calculation_id,
                    current_annual_revenue=input_data.current_annual_revenue,
                    scenarios=scenarios,
                    best_case_scenario=best_case,
                    conservative_scenario=conservative,
                    recommended_scenario=recommended,
                    maximum_potential_increase=max_increase,
                    maximum_potential_percentage=max_percentage,
                    strategic_recommendations=strategic_recs,
                    action_plan=action_plan,
                    calculated_at=datetime.now(),
                )

            except Exception as e:
                potential_calculations_total.labels(
                    tenant_id=tenant.tenant_id,
                    scenario_type="combined",
                    result="error",
                ).inc()
                logger.error(
                    "Erro no cálculo de potencial",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "calculation_id": calculation_id,
                        "error": str(e),
                    },
                )
                raise RevenuePotentialCalculationError(
                    message=_("Erro ao calcular potencial de receita"),
                    details={
                        "calculation_id": calculation_id,
                        "error": str(e),
                    },
                )

    def _generate_calculation_id(self) -> str:
        """Gera ID único para cálculo."""
        hash_input = f"revenue_potential{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _create_volume_growth_scenario(
        self, baseline: Decimal, growth_pct: Decimal
    ) -> RevenueScenario:
        """Cria cenário de crescimento de volume."""
        increase_decimal = growth_pct / 100
        projected = baseline * (Decimal("1") + increase_decimal)
        increase = projected - baseline

        return RevenueScenario(
            scenario_id=self._generate_scenario_id("volume", growth_pct),
            scenario_name=_("Crescimento de Volume {pct}%").format(pct=float(growth_pct)),
            scenario_type="volume_growth",
            baseline_revenue=baseline,
            projected_revenue=projected,
            revenue_increase=increase,
            revenue_increase_percentage=growth_pct,
            key_drivers=[
                _("Aumento de capacidade"),
                _("Expansão de mercado"),
                _("Marketing e captação"),
            ],
            assumptions=[
                _("Manutenção de preços atuais"),
                _("Mix de operadoras constante"),
                _("Capacidade física disponível"),
            ],
            implementation_difficulty="medium",
            time_to_implement_months=6,
            risk_level="medium",
            confidence_level=Decimal("0.75"),
        )

    def _create_pricing_scenario(
        self, baseline: Decimal, pricing_pct: Decimal
    ) -> RevenueScenario:
        """Cria cenário de otimização de preços."""
        increase_decimal = pricing_pct / 100
        projected = baseline * (Decimal("1") + increase_decimal)
        increase = projected - baseline

        return RevenueScenario(
            scenario_id=self._generate_scenario_id("pricing", pricing_pct),
            scenario_name=_("Otimização de Preços {pct}%").format(pct=float(pricing_pct)),
            scenario_type="pricing",
            baseline_revenue=baseline,
            projected_revenue=projected,
            revenue_increase=increase,
            revenue_increase_percentage=pricing_pct,
            key_drivers=[
                _("Renegociação de contratos"),
                _("Alinhamento com mercado"),
                _("Melhoria de codificação"),
            ],
            assumptions=[
                _("Volume de atendimentos constante"),
                _("Operadoras aceitam ajustes"),
            ],
            implementation_difficulty="high",
            time_to_implement_months=12,
            risk_level="medium",
            confidence_level=Decimal("0.65"),
        )

    def _create_payer_mix_scenario(
        self, baseline: Decimal, mix_data: dict[str, Any]
    ) -> RevenueScenario:
        """Cria cenário de mudança de mix de operadoras."""
        impact_pct = mix_data.get("impact_percentage", Decimal("8.0"))
        increase_decimal = impact_pct / 100
        projected = baseline * (Decimal("1") + increase_decimal)
        increase = projected - baseline

        return RevenueScenario(
            scenario_id=self._generate_scenario_id("payer_mix", impact_pct),
            scenario_name=_("Mudança de Mix de Operadoras"),
            scenario_type="payer_mix",
            baseline_revenue=baseline,
            projected_revenue=projected,
            revenue_increase=increase,
            revenue_increase_percentage=impact_pct,
            key_drivers=[
                _("Aumento de pacientes premium"),
                _("Redução de SUS/particular"),
            ],
            assumptions=[
                _("Capacidade de captar operadoras melhores"),
                _("Manutenção de volume"),
            ],
            implementation_difficulty="high",
            time_to_implement_months=18,
            risk_level="high",
            confidence_level=Decimal("0.55"),
        )

    def _create_combined_scenarios(
        self, baseline: Decimal, volume_growth: Decimal, pricing_improvement: Decimal
    ) -> list[RevenueScenario]:
        """Cria cenários combinados."""
        vol_decimal = volume_growth / 100
        price_decimal = pricing_improvement / 100
        total_impact = (Decimal("1") + vol_decimal) * (Decimal("1") + price_decimal) - Decimal("1")
        total_pct = total_impact * 100

        projected = baseline * (Decimal("1") + total_impact)
        increase = projected - baseline

        combined = RevenueScenario(
            scenario_id=self._generate_scenario_id("combined", total_pct),
            scenario_name=_("Estratégia Combinada"),
            scenario_type="combined",
            baseline_revenue=baseline,
            projected_revenue=projected,
            revenue_increase=increase,
            revenue_increase_percentage=total_pct,
            key_drivers=[
                _("Crescimento de volume"),
                _("Otimização de preços"),
            ],
            assumptions=[
                _("Execução paralela de iniciativas"),
                _("Investimento em capacidade"),
            ],
            implementation_difficulty="high",
            time_to_implement_months=18,
            risk_level="medium",
            confidence_level=Decimal("0.70"),
        )

        return [combined]

    def _create_bundle_scenario(self, baseline: Decimal) -> RevenueScenario:
        """Cria cenário de impacto de bundles."""
        impact_pct = Decimal("5.0")
        increase_decimal = impact_pct / 100
        projected = baseline * (Decimal("1") + increase_decimal)
        increase = projected - baseline

        return RevenueScenario(
            scenario_id=self._generate_scenario_id("bundles", impact_pct),
            scenario_name=_("Implementação de Bundles"),
            scenario_type="combined",
            baseline_revenue=baseline,
            projected_revenue=projected,
            revenue_increase=increase,
            revenue_increase_percentage=impact_pct,
            key_drivers=[_("Bundles de procedimentos"), _("Aumento de volume")],
            assumptions=[_("Adesão de 30% dos casos aplicáveis")],
            implementation_difficulty="low",
            time_to_implement_months=6,
            risk_level="low",
            confidence_level=Decimal("0.80"),
        )

    def _create_coding_improvement_scenario(self, baseline: Decimal) -> RevenueScenario:
        """Cria cenário de melhorias de codificação."""
        impact_pct = Decimal("7.0")
        increase_decimal = impact_pct / 100
        projected = baseline * (Decimal("1") + increase_decimal)
        increase = projected - baseline

        return RevenueScenario(
            scenario_id=self._generate_scenario_id("coding", impact_pct),
            scenario_name=_("Melhorias de Codificação"),
            scenario_type="combined",
            baseline_revenue=baseline,
            projected_revenue=projected,
            revenue_increase=increase,
            revenue_increase_percentage=impact_pct,
            key_drivers=[
                _("Upcoding compliant"),
                _("Documentação aprimorada"),
            ],
            assumptions=[_("Treinamento de equipe"), _("Auditoria contínua")],
            implementation_difficulty="medium",
            time_to_implement_months=9,
            risk_level="low",
            confidence_level=Decimal("0.75"),
        )

    def _generate_scenario_id(self, scenario_type: str, value: Decimal) -> str:
        """Gera ID único para cenário."""
        hash_input = f"{scenario_type}_{value}_{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:12]

    def _identify_recommended_scenario(
        self, scenarios: list[RevenueScenario]
    ) -> RevenueScenario:
        """Identifica cenário recomendado."""
        # Score = revenue_increase * confidence * (1 / implementation_difficulty_score)
        def score_scenario(s: RevenueScenario) -> Decimal:
            diff_score = {"low": 3, "medium": 2, "high": 1}[s.implementation_difficulty]
            return s.revenue_increase * s.confidence_level * diff_score

        return max(scenarios, key=score_scenario)

    def _generate_strategic_recommendations(
        self, scenarios: list[RevenueScenario], recommended: RevenueScenario
    ) -> list[str]:
        """Gera recomendações estratégicas."""
        recommendations = []

        recommendations.append(
            _(
                "Cenário recomendado: {name} com potencial de R$ {amount:,.2f}"
            ).format(
                name=recommended.scenario_name,
                amount=float(recommended.revenue_increase),
            )
        )

        low_risk = [s for s in scenarios if s.risk_level == "low"]
        if low_risk:
            total_low_risk = sum(s.revenue_increase for s in low_risk)
            recommendations.append(
                _(
                    "Priorizar {count} iniciativa(s) de baixo risco com potencial de R$ {amount:,.2f}"
                ).format(count=len(low_risk), amount=float(total_low_risk))
            )

        recommendations.append(
            _("Implementar por fases: baixo risco primeiro, alto risco após validação")
        )

        return recommendations

    def _create_action_plan(
        self, recommended: RevenueScenario, scenarios: list[RevenueScenario]
    ) -> dict[str, Any]:
        """Cria plano de ação."""
        return {
            "phase_1_quick_wins": [
                _("Implementar bundles de procedimentos"),
                _("Melhorar documentação clínica"),
            ],
            "phase_2_medium_term": [
                _("Otimizar precificação com operadoras-chave"),
                _("Expandir capacidade de atendimento"),
            ],
            "phase_3_long_term": [
                _("Renegociar contratos completos"),
                _("Mudar mix de operadoras"),
            ],
            "timeline_months": recommended.time_to_implement_months,
            "investment_required": _("Médio"),
            "expected_roi": _(">300% no primeiro ano"),
        }


# Task topic para Camunda
TOPIC = "calculate-revenue-potential"
