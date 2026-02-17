"""
Forecast Revenue Trends Worker.

ML-based revenue forecasting using time-series analysis with Prophet/ARIMA
for monthly projections, seasonal decomposition, and confidence intervals.
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
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
forecasts_total = Counter(
    "forecast_revenue_trends_total",
    "Total revenue forecasts generated",
    ["tenant_id", "forecast_horizon"],
)
forecast_duration_seconds = Histogram(
    "forecast_revenue_trends_duration_seconds",
    "Duration of revenue forecasting",
    ["tenant_id"],
)


class RevenueForecastingError(DomainException):
    """    Exception raised when revenue forecasting fails.
    
        Archetype: FINANCIAL_CALCULATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="REVENUE_FORECASTING_ERROR",
            bpmn_error_code="RevenueForecastingError",
            details=details or {},
        )


class ForecastRevenueTrendsInput(BaseModel):
    """Input model for revenue trend forecasting."""

    historical_months: int = Field(
        12, description=_("Meses de histórico para análise")
    )
    forecast_months: int = Field(
        6, description=_("Meses para projeção futura")
    )
    include_seasonality: bool = Field(
        True, description=_("Incluir análise de sazonalidade")
    )
    include_trends: bool = Field(
        True, description=_("Incluir análise de tendências")
    )
    confidence_level: Decimal = Field(
        Decimal("95.0"), description=_("Nível de confiança (%)")
    )
    payer_breakdown: bool = Field(
        True, description=_("Incluir detalhamento por operadora")
    )
    service_line_breakdown: bool = Field(
        True, description=_("Incluir detalhamento por linha de serviço")
    )


class MonthlyForecast(BaseModel):
    """Monthly revenue forecast."""

    month: str = Field(..., description=_("Mês (YYYY-MM)"))
    forecasted_revenue: Decimal = Field(
        ..., description=_("Receita prevista (R$)")
    )
    lower_bound: Decimal = Field(
        ..., description=_("Limite inferior do intervalo de confiança (R$)")
    )
    upper_bound: Decimal = Field(
        ..., description=_("Limite superior do intervalo de confiança (R$)")
    )
    trend_component: Decimal = Field(
        ..., description=_("Componente de tendência (R$)")
    )
    seasonal_component: Decimal = Field(
        ..., description=_("Componente sazonal (R$)")
    )
    confidence: Decimal = Field(
        ..., description=_("Nível de confiança da previsão (%)")
    )


class PayerForecast(BaseModel):
    """Revenue forecast by payer."""

    payer_name: str = Field(..., description=_("Nome da operadora"))
    forecasted_revenue: Decimal = Field(
        ..., description=_("Receita prevista (R$)")
    )
    growth_rate: Decimal = Field(
        ..., description=_("Taxa de crescimento projetada (%)")
    )
    risk_level: str = Field(
        ..., description=_("Nível de risco (LOW/MEDIUM/HIGH)")
    )


class ServiceLineForecast(BaseModel):
    """Revenue forecast by service line."""

    service_line: str = Field(..., description=_("Linha de serviço"))
    forecasted_revenue: Decimal = Field(
        ..., description=_("Receita prevista (R$)")
    )
    volume_trend: str = Field(
        ..., description=_("Tendência de volume (INCREASING/STABLE/DECREASING)")
    )


class ForecastRevenueTrendsOutput(BaseModel):
    """Output model for revenue trend forecasting."""

    monthly_forecasts: list[MonthlyForecast] = Field(
        ..., description=_("Previsões mensais")
    )
    payer_forecasts: list[PayerForecast] | None = Field(
        None, description=_("Previsões por operadora")
    )
    service_line_forecasts: list[ServiceLineForecast] | None = Field(
        None, description=_("Previsões por linha de serviço")
    )
    overall_trend: str = Field(
        ..., description=_("Tendência geral (GROWING/STABLE/DECLINING)")
    )
    seasonality_detected: bool = Field(
        ..., description=_("Sazonalidade detectada")
    )
    forecast_accuracy: Decimal = Field(
        ..., description=_("Acurácia estimada da previsão (%)")
    )
    risk_factors: list[str] = Field(
        ..., description=_("Fatores de risco identificados")
    )
    recommendations: list[str] = Field(
        ..., description=_("Recomendações estratégicas")
    )
    forecast_timestamp: datetime = Field(
        ..., description=_("Timestamp da previsão")
    )


class ForecastRevenueTrendsProtocol(ABC):
    """Protocol for forecasting revenue trends."""

    @abstractmethod
    async def execute(
        self, input_data: ForecastRevenueTrendsInput
    ) -> ForecastRevenueTrendsOutput:
        """
        Forecast revenue trends using ML time-series analysis.

        Args:
            input_data: Forecasting parameters

        Returns:
            ForecastRevenueTrendsOutput with forecasts and recommendations

        Raises:
            RevenueForecastingError: If forecasting fails
        """
        pass


class ForecastRevenueTrendsWorkerStub(ForecastRevenueTrendsProtocol):
    """Stub implementation for forecasting revenue trends."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    def _generate_historical_data(
        self, months: int
    ) -> list[tuple[datetime, Decimal]]:
        """Generate synthetic historical revenue data."""
        data = []
        base_revenue = Decimal("500000")
        current_date = datetime.now().replace(day=1)

        for i in range(months, 0, -1):
            month_date = current_date - timedelta(days=30 * i)
            # Add trend (5% annual growth)
            trend = base_revenue * (Decimal("1.05") ** (i / 12))
            # Add seasonality (higher in Q4, lower in Q1)
            month_num = month_date.month
            if month_num in [10, 11, 12]:
                seasonal = Decimal("1.15")
            elif month_num in [1, 2, 3]:
                seasonal = Decimal("0.90")
            else:
                seasonal = Decimal("1.0")

            revenue = trend * seasonal * (Decimal("0.95") + Decimal(i % 10) / 50)
            data.append((month_date, revenue))

        return data

    def _forecast_monthly_revenue(
        self,
        historical_data: list[tuple[datetime, Decimal]],
        forecast_months: int,
        confidence_level: Decimal,
    ) -> list[MonthlyForecast]:
        """Generate monthly revenue forecasts."""
        forecasts = []

        # Simple trend-based forecasting (stub for Prophet/ARIMA)
        if not historical_data:
            return forecasts

        # Calculate trend
        revenues = [rev for _, rev in historical_data]
        avg_growth = (revenues[-1] - revenues[0]) / len(revenues)

        last_date = historical_data[-1][0]
        last_revenue = historical_data[-1][1]

        for i in range(1, forecast_months + 1):
            forecast_date = last_date + timedelta(days=30 * i)
            month_str = forecast_date.strftime("%Y-%m")

            # Apply trend
            base_forecast = last_revenue + (avg_growth * i)

            # Apply seasonality
            month_num = forecast_date.month
            if month_num in [10, 11, 12]:
                seasonal_factor = Decimal("1.15")
            elif month_num in [1, 2, 3]:
                seasonal_factor = Decimal("0.90")
            else:
                seasonal_factor = Decimal("1.0")

            forecasted = base_forecast * seasonal_factor

            # Calculate confidence intervals
            margin = forecasted * (Decimal("100") - confidence_level) / 100
            lower = forecasted - margin
            upper = forecasted + margin

            # Decompose components
            trend = base_forecast - last_revenue
            seasonal = forecasted - base_forecast

            forecast = MonthlyForecast(
                month=month_str,
                forecasted_revenue=forecasted,
                lower_bound=lower,
                upper_bound=upper,
                trend_component=trend,
                seasonal_component=seasonal,
                confidence=confidence_level,
            )
            forecasts.append(forecast)

        return forecasts

    def _forecast_by_payer(
        self, total_forecast: Decimal
    ) -> list[PayerForecast]:
        """Generate payer-specific forecasts."""
        payers = [
            ("Unimed", Decimal("0.30"), Decimal("3.5"), "LOW"),
            ("Amil", Decimal("0.25"), Decimal("2.8"), "MEDIUM"),
            ("Bradesco Saúde", Decimal("0.20"), Decimal("4.2"), "LOW"),
            ("SulAmérica", Decimal("0.15"), Decimal("1.5"), "MEDIUM"),
            ("SUS", Decimal("0.10"), Decimal("-0.5"), "HIGH"),
        ]

        forecasts = []
        for payer, share, growth, risk in payers:
            payer_revenue = total_forecast * share
            forecast = PayerForecast(
                payer_name=payer,
                forecasted_revenue=payer_revenue,
                growth_rate=growth,
                risk_level=risk,
            )
            forecasts.append(forecast)

        return forecasts

    def _forecast_by_service_line(
        self, total_forecast: Decimal
    ) -> list[ServiceLineForecast]:
        """Generate service line forecasts."""
        service_lines = [
            ("Cirurgia", Decimal("0.35"), "INCREASING"),
            ("Clínica Médica", Decimal("0.25"), "STABLE"),
            ("Diagnóstico", Decimal("0.20"), "INCREASING"),
            ("Emergência", Decimal("0.15"), "STABLE"),
            ("Reabilitação", Decimal("0.05"), "DECREASING"),
        ]

        forecasts = []
        for service_line, share, trend in service_lines:
            service_revenue = total_forecast * share
            forecast = ServiceLineForecast(
                service_line=service_line,
                forecasted_revenue=service_revenue,
                volume_trend=trend,
            )
            forecasts.append(forecast)

        return forecasts

    def _detect_overall_trend(
        self, forecasts: list[MonthlyForecast]
    ) -> str:
        """Detect overall revenue trend."""
        if not forecasts or len(forecasts) < 2:
            return "STABLE"

        first_revenue = forecasts[0].forecasted_revenue
        last_revenue = forecasts[-1].forecasted_revenue

        growth = ((last_revenue - first_revenue) / first_revenue) * 100

        if growth > 5:
            return "GROWING"
        elif growth < -5:
            return "DECLINING"
        else:
            return "STABLE"

    def _identify_risk_factors(
        self,
        trend: str,
        payer_forecasts: list[PayerForecast] | None,
    ) -> list[str]:
        """Identify risk factors in forecasts."""
        risks = []

        if trend == "DECLINING":
            risks.append(_("Tendência de declínio de receita detectada"))

        if payer_forecasts:
            high_risk_payers = [p for p in payer_forecasts if p.risk_level == "HIGH"]
            if high_risk_payers:
                risks.append(
                    _(
                        f"{len(high_risk_payers)} operadora(s) de alto risco identificada(s)"
                    )
                )

            negative_growth = [
                p for p in payer_forecasts if p.growth_rate < 0
            ]
            if negative_growth:
                risks.append(
                    _(
                        f"Crescimento negativo previsto para {len(negative_growth)} operadora(s)"
                    )
                )

        return risks

    def _generate_recommendations(
        self,
        trend: str,
        risks: list[str],
        service_line_forecasts: list[ServiceLineForecast] | None,
    ) -> list[str]:
        """Generate strategic recommendations."""
        recommendations = []

        if trend == "GROWING":
            recommendations.append(
                _("Planejar expansão de capacidade para acomodar crescimento")
            )
        elif trend == "DECLINING":
            recommendations.append(
                _("Implementar estratégias de recuperação de receita urgentemente")
            )

        if service_line_forecasts:
            increasing = [
                s for s in service_line_forecasts if s.volume_trend == "INCREASING"
            ]
            if increasing:
                recommendations.append(
                    _(
                        f"Investir em linhas de serviço em crescimento: {', '.join(s.service_line for s in increasing)}"
                    )
                )

            decreasing = [
                s for s in service_line_forecasts if s.volume_trend == "DECREASING"
            ]
            if decreasing:
                recommendations.append(
                    _(
                        f"Revisar estratégia para linhas em declínio: {', '.join(s.service_line for s in decreasing)}"
                    )
                )

        recommendations.append(
            _("Monitorar previsões mensalmente e ajustar planos operacionais")
        )

        return recommendations

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: ForecastRevenueTrendsInput
    ) -> ForecastRevenueTrendsOutput:
        """Execute revenue trend forecasting."""
        tenant_id = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='ans/comp_ans_004',
                inputs={'forecast_horizon': input_data.forecast_horizon_months},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        logger.info(
            "Forecasting revenue trends",
            extra={
                "tenant_id": tenant_id,
                "forecast_months": input_data.forecast_months,
            },
        )

        with forecast_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                # Generate historical data
                historical_data = self._generate_historical_data(
                    input_data.historical_months
                )

                # Generate monthly forecasts
                monthly_forecasts = self._forecast_monthly_revenue(
                    historical_data,
                    input_data.forecast_months,
                    input_data.confidence_level,
                )

                # Calculate total forecast for breakdowns
                total_forecast = (
                    sum(f.forecasted_revenue for f in monthly_forecasts)
                    if monthly_forecasts
                    else Decimal("0")
                )

                # Generate payer forecasts
                payer_forecasts = None
                if input_data.payer_breakdown and total_forecast > 0:
                    payer_forecasts = self._forecast_by_payer(
                        total_forecast / input_data.forecast_months
                    )

                # Generate service line forecasts
                service_line_forecasts = None
                if input_data.service_line_breakdown and total_forecast > 0:
                    service_line_forecasts = self._forecast_by_service_line(
                        total_forecast / input_data.forecast_months
                    )

                # Detect trends
                overall_trend = self._detect_overall_trend(monthly_forecasts)

                # Identify risks
                risk_factors = self._identify_risk_factors(
                    overall_trend, payer_forecasts
                )

                # Generate recommendations
                recommendations = self._generate_recommendations(
                    overall_trend, risk_factors, service_line_forecasts
                )

                result = ForecastRevenueTrendsOutput(
                    monthly_forecasts=monthly_forecasts,
                    payer_forecasts=payer_forecasts,
                    service_line_forecasts=service_line_forecasts,
                    overall_trend=overall_trend,
                    seasonality_detected=input_data.include_seasonality,
                    forecast_accuracy=Decimal("85.5"),  # Simulated accuracy
                    risk_factors=risk_factors,
                    recommendations=recommendations,
                    forecast_timestamp=datetime.now(),
                )

                forecasts_total.labels(
                    tenant_id=tenant_id, forecast_horizon=f"{input_data.forecast_months}m"
                ).inc()

                logger.info(
                    "Revenue forecasting completed",
                    extra={
                        "tenant_id": tenant_id,
                        "trend": overall_trend,
                        "total_forecast": float(total_forecast),
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Revenue forecasting failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise RevenueForecastingError(
                    _("Falha ao prever tendências de receita"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "platform.forecast_revenue_trends"
