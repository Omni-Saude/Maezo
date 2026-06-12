"""
Benchmark Payer Performance Worker.

Compares payer performance across payment timeliness, denial rates,
negotiated rates vs market, and contract compliance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
benchmarks_total = Counter(
    "benchmark_payer_performance_total",
    "Total payer performance benchmarks performed",
    ["tenant_id", "payer"],
)
benchmark_duration_seconds = Histogram(
    "benchmark_payer_performance_duration_seconds",
    "Duration of payer benchmarking",
    ["tenant_id"],
)


class PayerBenchmarkingError(DomainException):
    """    Exception raised when payer benchmarking fails.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="PAYER_BENCHMARKING_ERROR",
            bpmn_error_code="PayerBenchmarkingError",
            details=details or {},
        )


class BenchmarkPayerPerformanceInput(BaseModel):
    """Input model for benchmarking payer performance."""

    analysis_period_days: int = Field(
        90, description=_("Período de análise em dias")
    )
    payer_ids: list[str] | None = Field(
        None, description=_("IDs de operadoras específicas (None = todas)")
    )
    include_timeliness: bool = Field(
        True, description=_("Incluir análise de pontualidade de pagamento")
    )
    include_denial_rates: bool = Field(
        True, description=_("Incluir análise de taxas de glosa")
    )
    include_rate_comparison: bool = Field(
        True, description=_("Incluir comparação de tabelas vs mercado")
    )
    include_contract_compliance: bool = Field(
        True, description=_("Incluir análise de compliance contratual")
    )
    market_benchmark_source: str = Field(
        "ANS", description=_("Fonte de benchmark de mercado")
    )


class PaymentTimeliness(BaseModel):
    """Payment timeliness metrics."""

    average_days_to_payment: Decimal = Field(
        ..., description=_("Dias médios até pagamento")
    )
    on_time_payment_rate: Decimal = Field(
        ..., description=_("Taxa de pagamento no prazo (%)")
    )
    late_payment_count: int = Field(
        ..., description=_("Total de pagamentos atrasados")
    )
    longest_delay_days: int = Field(
        ..., description=_("Maior atraso em dias")
    )


class DenialMetrics(BaseModel):
    """Denial/glosa metrics."""

    denial_rate: Decimal = Field(
        ..., description=_("Taxa de glosa (%)")
    )
    denial_amount: Decimal = Field(
        ..., description=_("Valor total glosado (R$)")
    )
    successful_appeal_rate: Decimal = Field(
        ..., description=_("Taxa de sucesso em recursos (%)")
    )
    top_denial_reasons: list[str] = Field(
        ..., description=_("Principais razões de glosa")
    )


class RateComparison(BaseModel):
    """Rate comparison vs market."""

    contracted_rate: Decimal = Field(
        ..., description=_("Taxa contratada (R$)")
    )
    market_rate: Decimal = Field(
        ..., description=_("Taxa de mercado (R$)")
    )
    variance_percentage: Decimal = Field(
        ..., description=_("Variação vs mercado (%)")
    )
    competitiveness: str = Field(
        ..., description=_("Competitividade (ABOVE/AT/BELOW)")
    )


class ContractCompliance(BaseModel):
    """Contract compliance metrics."""

    compliance_score: Decimal = Field(
        ..., description=_("Score de compliance (0-100)")
    )
    contract_violations: int = Field(
        ..., description=_("Violações contratuais")
    )
    sla_adherence: Decimal = Field(
        ..., description=_("Aderência a SLAs (%)")
    )
    authorization_adherence: Decimal = Field(
        ..., description=_("Aderência a processo de autorização (%)")
    )


class PayerBenchmark(BaseModel):
    """Comprehensive payer benchmark."""

    payer_id: str = Field(..., description=_("ID da operadora"))
    payer_name: str = Field(..., description=_("Nome da operadora"))
    overall_score: Decimal = Field(
        ..., description=_("Score geral de performance (0-100)")
    )
    timeliness: PaymentTimeliness | None = Field(
        None, description=_("Métricas de pontualidade")
    )
    denial_metrics: DenialMetrics | None = Field(
        None, description=_("Métricas de glosa")
    )
    rate_comparison: RateComparison | None = Field(
        None, description=_("Comparação de taxas")
    )
    contract_compliance: ContractCompliance | None = Field(
        None, description=_("Compliance contratual")
    )
    ranking: int = Field(
        ..., description=_("Ranking entre operadoras")
    )
    revenue_contribution: Decimal = Field(
        ..., description=_("Contribuição de receita (%)")
    )
    risk_level: str = Field(
        ..., description=_("Nível de risco (LOW/MEDIUM/HIGH)")
    )


class BenchmarkPayerPerformanceOutput(BaseModel):
    """Output model for payer performance benchmarking."""

    payer_benchmarks: list[PayerBenchmark] = Field(
        ..., description=_("Benchmarks por operadora")
    )
    best_performer: str = Field(
        ..., description=_("Operadora com melhor performance")
    )
    worst_performer: str = Field(
        ..., description=_("Operadora com pior performance")
    )
    market_averages: dict[str, Decimal] = Field(
        ..., description=_("Médias de mercado")
    )
    action_items: list[str] = Field(
        ..., description=_("Itens de ação recomendados")
    )
    contract_renegotiation_opportunities: list[str] = Field(
        ..., description=_("Oportunidades de renegociação")
    )
    benchmark_timestamp: datetime = Field(
        ..., description=_("Timestamp do benchmark")
    )


class BenchmarkPayerPerformanceProtocol(ABC):
    """Protocol for benchmarking payer performance."""

    @abstractmethod
    async def execute(
        self, input_data: BenchmarkPayerPerformanceInput
    ) -> BenchmarkPayerPerformanceOutput:
        """
        Benchmark payer performance across multiple dimensions.

        Args:
            input_data: Benchmarking parameters

        Returns:
            BenchmarkPayerPerformanceOutput with comparative analysis

        Raises:
            PayerBenchmarkingError: If benchmarking fails
        """
        pass


class BenchmarkPayerPerformanceWorkerStub(BenchmarkPayerPerformanceProtocol):
    """Stub implementation for benchmarking payer performance."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    def _get_payer_list(self, payer_ids: list[str] | None) -> list[tuple[str, str]]:
        """Get list of payers to benchmark."""
        all_payers = [
            ("PAY001", "Unimed"),
            ("PAY002", "Amil"),
            ("PAY003", "Bradesco Saúde"),
            ("PAY004", "SulAmérica"),
            ("PAY005", "SUS"),
        ]

        if payer_ids:
            return [p for p in all_payers if p[0] in payer_ids]
        return all_payers

    def _analyze_timeliness(self, payer_id: str) -> PaymentTimeliness:
        """Analyze payment timeliness."""
        # Simulate different performance by payer
        payer_num = int(payer_id[-1])

        avg_days = Decimal(str(30 + payer_num * 5))
        on_time_rate = Decimal(str(95 - payer_num * 8))
        late_count = payer_num * 3
        longest_delay = 30 + payer_num * 10

        return PaymentTimeliness(
            average_days_to_payment=avg_days,
            on_time_payment_rate=max(on_time_rate, Decimal("40")),
            late_payment_count=late_count,
            longest_delay_days=longest_delay,
        )

    def _analyze_denial_metrics(self, payer_id: str) -> DenialMetrics:
        """Analyze denial/glosa metrics."""
        payer_num = int(payer_id[-1])

        denial_rate = Decimal(str(5 + payer_num * 2))
        denial_amount = Decimal(str(50000 + payer_num * 10000))
        appeal_rate = Decimal(str(70 - payer_num * 5))

        top_reasons = [
            _("Falta de autorização prévia"),
            _("Procedimento não coberto"),
            _("Documentação incompleta"),
        ]

        return DenialMetrics(
            denial_rate=denial_rate,
            denial_amount=denial_amount,
            successful_appeal_rate=appeal_rate,
            top_denial_reasons=top_reasons[:payer_num] if payer_num > 0 else top_reasons[:1],
        )

    def _compare_rates(
        self, payer_id: str, market_source: str
    ) -> RateComparison:
        """Compare contracted rates to market."""
        payer_num = int(payer_id[-1])

        market_rate = Decimal("1000.00")
        contracted_rate = market_rate * (Decimal("0.90") + Decimal(payer_num) / 50)
        variance = ((contracted_rate - market_rate) / market_rate) * 100

        if variance > 5:
            competitiveness = "ABOVE"
        elif variance < -5:
            competitiveness = "BELOW"
        else:
            competitiveness = "AT"

        return RateComparison(
            contracted_rate=contracted_rate,
            market_rate=market_rate,
            variance_percentage=variance,
            competitiveness=competitiveness,
        )

    def _analyze_contract_compliance(self, payer_id: str) -> ContractCompliance:
        """Analyze contract compliance."""
        payer_num = int(payer_id[-1])

        compliance = Decimal(str(90 - payer_num * 5))
        violations = payer_num
        sla_adherence = Decimal(str(92 - payer_num * 4))
        auth_adherence = Decimal(str(88 - payer_num * 6))

        return ContractCompliance(
            compliance_score=compliance,
            contract_violations=violations,
            sla_adherence=sla_adherence,
            authorization_adherence=auth_adherence,
        )

    def _calculate_overall_score(
        self,
        timeliness: PaymentTimeliness | None,
        denial: DenialMetrics | None,
        rate: RateComparison | None,
        compliance: ContractCompliance | None,
    ) -> Decimal:
        """Calculate overall payer performance score."""
        score = Decimal("0")
        components = 0

        if timeliness:
            score += timeliness.on_time_payment_rate * Decimal("0.25")
            components += 1

        if denial:
            denial_score = (100 - denial.denial_rate) * Decimal("0.25")
            score += denial_score
            components += 1

        if rate:
            if rate.competitiveness == "ABOVE":
                score += Decimal("25")
            elif rate.competitiveness == "AT":
                score += Decimal("20")
            else:
                score += Decimal("15")
            components += 1

        if compliance:
            score += compliance.compliance_score * Decimal("0.25")
            components += 1

        return score if components > 0 else Decimal("50")

    def _determine_risk_level(self, overall_score: Decimal) -> str:
        """Determine risk level based on overall score."""
        if overall_score >= 75:
            return "LOW"
        elif overall_score >= 50:
            return "MEDIUM"
        else:
            return "HIGH"

    def _generate_action_items(
        self, benchmarks: list[PayerBenchmark]
    ) -> list[str]:
        """Generate action items based on benchmarks."""
        actions = []

        high_denial = [b for b in benchmarks if b.denial_metrics and b.denial_metrics.denial_rate > 10]
        if high_denial:
            actions.append(
                _(
                    f"Reduzir glosas com {len(high_denial)} operadora(s) através de melhor documentação"
                )
            )

        late_payers = [
            b
            for b in benchmarks
            if b.timeliness and b.timeliness.on_time_payment_rate < 80
        ]
        if late_payers:
            actions.append(
                _(
                    f"Escalar atrasos de pagamento com {len(late_payers)} operadora(s)"
                )
            )

        low_compliance = [
            b
            for b in benchmarks
            if b.contract_compliance and b.contract_compliance.compliance_score < 80
        ]
        if low_compliance:
            actions.append(
                _(
                    f"Revisar compliance contratual com {len(low_compliance)} operadora(s)"
                )
            )

        return actions

    def _identify_renegotiation_opportunities(
        self, benchmarks: list[PayerBenchmark]
    ) -> list[str]:
        """Identify contract renegotiation opportunities."""
        opportunities = []

        below_market = [
            b
            for b in benchmarks
            if b.rate_comparison and b.rate_comparison.competitiveness == "BELOW"
        ]
        if below_market:
            for benchmark in below_market:
                opportunities.append(
                    _(
                        f"{benchmark.payer_name}: Taxa {benchmark.rate_comparison.variance_percentage:.1f}% abaixo do mercado"
                    )
                )

        high_performers = [b for b in benchmarks if b.overall_score > 80]
        if high_performers:
            for benchmark in high_performers:
                opportunities.append(
                    _(
                        f"{benchmark.payer_name}: Alto desempenho - negociar volume adicional"
                    )
                )

        return opportunities

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: BenchmarkPayerPerformanceInput
    ) -> BenchmarkPayerPerformanceOutput:
        """Execute payer performance benchmarking."""
        tenant_id = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant_id.tenant_code,
                category='compliance',
                table_name='tiss/comp_tiss_004',
                inputs={'payer_code': input_data.payer_code},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        logger.info(
            "Benchmarking payer performance",
            extra={"tenant_id": tenant_id, "period_days": input_data.analysis_period_days},
        )

        with benchmark_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                payers = self._get_payer_list(input_data.payer_ids)
                benchmarks: list[PayerBenchmark] = []

                for payer_id, payer_name in payers:
                    timeliness = (
                        self._analyze_timeliness(payer_id)
                        if input_data.include_timeliness
                        else None
                    )

                    denial = (
                        self._analyze_denial_metrics(payer_id)
                        if input_data.include_denial_rates
                        else None
                    )

                    rate = (
                        self._compare_rates(payer_id, input_data.market_benchmark_source)
                        if input_data.include_rate_comparison
                        else None
                    )

                    compliance = (
                        self._analyze_contract_compliance(payer_id)
                        if input_data.include_contract_compliance
                        else None
                    )

                    overall_score = self._calculate_overall_score(
                        timeliness, denial, rate, compliance
                    )

                    risk = self._determine_risk_level(overall_score)

                    # Simulate revenue contribution
                    payer_num = int(payer_id[-1])
                    revenue_contrib = Decimal(str(30 - payer_num * 4))

                    benchmark = PayerBenchmark(
                        payer_id=payer_id,
                        payer_name=payer_name,
                        overall_score=overall_score,
                        timeliness=timeliness,
                        denial_metrics=denial,
                        rate_comparison=rate,
                        contract_compliance=compliance,
                        ranking=0,  # Will be set after sorting
                        revenue_contribution=revenue_contrib,
                        risk_level=risk,
                    )
                    benchmarks.append(benchmark)

                    benchmarks_total.labels(
                        tenant_id=tenant_id, payer=payer_name
                    ).inc()

                # Sort by overall score and assign rankings
                benchmarks.sort(key=lambda x: x.overall_score, reverse=True)
                for idx, benchmark in enumerate(benchmarks, 1):
                    benchmark.ranking = idx

                # Market averages
                market_averages = {
                    "average_payment_days": Decimal("35.0"),
                    "average_denial_rate": Decimal("8.5"),
                    "average_compliance_score": Decimal("85.0"),
                }

                action_items = self._generate_action_items(benchmarks)
                renegotiation_opps = self._identify_renegotiation_opportunities(
                    benchmarks
                )

                result = BenchmarkPayerPerformanceOutput(
                    payer_benchmarks=benchmarks,
                    best_performer=benchmarks[0].payer_name if benchmarks else "N/A",
                    worst_performer=benchmarks[-1].payer_name if benchmarks else "N/A",
                    market_averages=market_averages,
                    action_items=action_items,
                    contract_renegotiation_opportunities=renegotiation_opps,
                    benchmark_timestamp=datetime.now(),
                )

                logger.info(
                    "Payer benchmarking completed",
                    extra={
                        "tenant_id": tenant_id,
                        "payers_analyzed": len(benchmarks),
                        "best_performer": result.best_performer,
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Payer benchmarking failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise PayerBenchmarkingError(
                    _("Falha ao realizar benchmark de operadoras"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "platform.benchmark_payer_performance"
