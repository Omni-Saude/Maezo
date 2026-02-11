"""
Worker para detecção de anomalias em dados financeiros, clínicos e operacionais.

Usa métodos estatísticos (z-score, IQR) para detectar outliers:
- Faturamento fora do padrão
- Tempos de atendimento anormais
- Taxas de glosa atípicas
- Picos de volume de guias

Dispara alertas via configuração de thresholds.

Padrão: Protocol ABC + Stub implementation
Decorators: @require_tenant, @track_task_execution
Métricas: Prometheus Counter, Histogram, Gauge
LGPD: Hash de identificadores antes de log
i18n: Todas strings user-facing via _()
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
anomaly_scans_total = Counter(
    "anomaly_scans_total",
    "Total anomaly detection scans executed",
    ["tenant_id", "metric_type", "status"],
)
anomaly_duration_seconds = Histogram(
    "anomaly_duration_seconds",
    "Duration of anomaly detection scan",
    ["tenant_id", "metric_type"],
)
anomalies_detected_gauge = Gauge(
    "anomalies_detected_gauge",
    "Current number of detected anomalies",
    ["tenant_id", "metric_type", "severity"],
)

TOPIC = "platform.alert_on_anomalies"


class AnomalyDetectionException(DomainException):
    """Exceção de detecção de anomalias."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="ANOMALY_DETECTION_ERROR",
            details=details or {},
        )


class AlertOnAnomaliesInput(BaseModel):
    """Input para detecção de anomalias."""

    metric_type: str = Field(
        ...,
        description=_("Tipo de métrica: revenue, claim_volume, glosa_rate, cycle_time, clinical_event"),
    )
    detection_method: str = Field(
        default="z_score",
        description=_("Método: z_score (z>3), iqr (interquartile range), moving_avg"),
    )
    lookback_days: int = Field(default=30, description=_("Janela de lookback para baseline (dias)"))
    sensitivity: str = Field(
        default="medium",
        description=_("Sensibilidade: low (z>4), medium (z>3), high (z>2)"),
    )
    auto_alert: bool = Field(default=True, description=_("Dispara alertas automaticamente"))
    alert_channel: str = Field(default="email", description=_("Canal de alerta: email, slack, sms"))


class DetectedAnomaly(BaseModel):
    """Anomalia detectada."""

    metric_type: str = Field(..., description=_("Tipo de métrica"))
    timestamp: datetime = Field(..., description=_("Timestamp da anomalia"))
    observed_value: float = Field(..., description=_("Valor observado"))
    expected_value: float = Field(..., description=_("Valor esperado (baseline)"))
    deviation_percent: float = Field(..., description=_("Desvio percentual em relação ao esperado"))
    z_score: float | None = Field(None, description=_("Z-score (se método z_score)"))
    severity: str = Field(..., description=_("Severidade: low, medium, high, critical"))
    alert_sent: bool = Field(default=False, description=_("Se alerta foi enviado"))
    alert_channel: str | None = Field(None, description=_("Canal do alerta enviado"))


class AlertOnAnomaliesOutput(BaseModel):
    """Output da detecção de anomalias."""

    scan_id: str = Field(..., description=_("ID único do scan"))
    metric_type: str = Field(..., description=_("Tipo de métrica analisada"))
    detection_method: str = Field(..., description=_("Método de detecção"))
    total_data_points: int = Field(..., description=_("Total de pontos de dados analisados"))
    anomalies_detected: list[DetectedAnomaly] = Field(
        default_factory=list,
        description=_("Anomalias detectadas"),
    )
    anomaly_count: int = Field(..., description=_("Total de anomalias detectadas"))
    alerts_sent: int = Field(default=0, description=_("Total de alertas enviados"))
    baseline_mean: float = Field(..., description=_("Média do baseline"))
    baseline_std_dev: float = Field(..., description=_("Desvio padrão do baseline"))
    scanned_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp do scan"))
    duration_seconds: float = Field(..., description=_("Duração do scan em segundos"))


class AlertOnAnomaliesProtocol(ABC):
    """Protocol para detecção de anomalias."""

    @abstractmethod
    async def execute(self, input_data: AlertOnAnomaliesInput) -> AlertOnAnomaliesOutput:
        """
        Detecta anomalias em dados financeiros, clínicos e operacionais.

        Args:
            input_data: Parâmetros da detecção

        Returns:
            AlertOnAnomaliesOutput com anomalias detectadas

        Raises:
            AnomalyDetectionException: Erro na detecção
        """
        pass


class AlertOnAnomaliesStub(AlertOnAnomaliesProtocol):
    """Stub implementation para detecção de anomalias."""

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: AlertOnAnomaliesInput) -> AlertOnAnomaliesOutput:
        """
        Detecta anomalias em dados financeiros, clínicos e operacionais.

        Fluxo:
        1. Extrai dados históricos (lookback_days)
        2. Calcula baseline (média, desvio padrão)
        3. Aplica método de detecção (z-score, IQR, moving avg)
        4. Classifica anomalias por severidade
        5. Se auto_alert=True, dispara alertas via canal configurado
        6. Atualiza métricas Prometheus

        Métodos:
        - z_score: detecta valores com |z| > threshold
        - iqr: detecta valores fora de [Q1-1.5*IQR, Q3+1.5*IQR]
        - moving_avg: detecta desvios >3x MAD (median absolute deviation)

        LGPD: Hash de patient_id/claim_id antes de logar.
        """
        tenant = get_required_tenant()
        _dmn = get_dmn_service()
        try:
            _dmn_result = _dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='vigil/comp_vigil_001',
                inputs={'metric_type': input_data.metric_type, 'sensitivity': input_data.sensitivity},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        start_time = datetime.utcnow()

        logger.info(
            _("Iniciando detecção de anomalias: {metric_type}, método={method}").format(
                metric_type=input_data.metric_type,
                method=input_data.detection_method,
            ),
            extra={
                "tenant_id": tenant.tenant_code,
                "lookback_days": input_data.lookback_days,
            },
        )

        try:
            # Extrai dados históricos
            historical_data = await self._extract_historical_data(
                metric_type=input_data.metric_type,
                lookback_days=input_data.lookback_days,
            )

            logger.info(
                _("Extraídos {count} pontos de dados").format(count=len(historical_data))
            )

            # Calcula baseline (média, desvio padrão)
            baseline_mean, baseline_std_dev = await self._calculate_baseline(historical_data)

            # Aplica método de detecção
            anomalies = await self._detect_anomalies(
                data=historical_data,
                method=input_data.detection_method,
                baseline_mean=baseline_mean,
                baseline_std_dev=baseline_std_dev,
                sensitivity=input_data.sensitivity,
                metric_type=input_data.metric_type,
            )

            # Classifica por severidade
            for anomaly in anomalies:
                anomaly.severity = await self._classify_severity(
                    deviation_percent=anomaly.deviation_percent,
                    z_score=anomaly.z_score,
                )

            # Dispara alertas
            alerts_sent = 0
            if input_data.auto_alert:
                alerts_sent = await self._send_alerts(
                    anomalies=anomalies,
                    channel=input_data.alert_channel,
                )

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Atualiza métricas Prometheus
            anomaly_scans_total.labels(
                tenant_id=tenant.tenant_code,
                metric_type=input_data.metric_type,
                status="success",
            ).inc()

            anomaly_duration_seconds.labels(
                tenant_id=tenant.tenant_code,
                metric_type=input_data.metric_type,
            ).observe(duration)

            # Gauge por severidade
            for severity in ["low", "medium", "high", "critical"]:
                count = len([a for a in anomalies if a.severity == severity])
                anomalies_detected_gauge.labels(
                    tenant_id=tenant.tenant_code,
                    metric_type=input_data.metric_type,
                    severity=severity,
                ).set(count)

            scan_id = f"ANOM-{tenant.tenant_code}-{int(start_time.timestamp())}"

            output = AlertOnAnomaliesOutput(
                scan_id=scan_id,
                metric_type=input_data.metric_type,
                detection_method=input_data.detection_method,
                total_data_points=len(historical_data),
                anomalies_detected=anomalies,
                anomaly_count=len(anomalies),
                alerts_sent=alerts_sent,
                baseline_mean=baseline_mean,
                baseline_std_dev=baseline_std_dev,
                duration_seconds=duration,
            )

            logger.info(
                _("Detecção concluída: {count} anomalias, {alerts} alertas enviados").format(
                    count=len(anomalies),
                    alerts=alerts_sent,
                ),
                extra={
                    "tenant_id": tenant.tenant_code,
                    "scan_id": scan_id,
                },
            )

            return output

        except Exception as e:
            anomaly_scans_total.labels(
                tenant_id=tenant.tenant_code,
                metric_type=input_data.metric_type,
                status="error",
            ).inc()
            logger.error(_("Erro na detecção de anomalias: {error}").format(error=str(e)))
            raise AnomalyDetectionException(
                message=_("Falha ao detectar anomalias"),
                details={"error": str(e)},
            )

    async def _extract_historical_data(
        self,
        metric_type: str,
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        """Extrai dados históricos para baseline (stub)."""
        # Stub: gera dados sintéticos
        data = []
        base_value = 10000.0 if metric_type == "revenue" else 100.0

        for i in range(lookback_days * 24):  # Dados por hora
            timestamp = datetime.utcnow() - timedelta(hours=lookback_days * 24 - i)
            value = base_value + (i % 100) * 10

            # Injeta anomalias (5% dos dados)
            if i % 20 == 0:
                value *= 2.5  # Anomalia positiva

            data.append({"timestamp": timestamp, "value": value})

        return data

    async def _calculate_baseline(
        self,
        data: list[dict[str, Any]],
    ) -> tuple[float, float]:
        """Calcula média e desvio padrão do baseline."""
        values = [d["value"] for d in data]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = variance**0.5

        return mean, std_dev

    async def _detect_anomalies(
        self,
        data: list[dict[str, Any]],
        method: str,
        baseline_mean: float,
        baseline_std_dev: float,
        sensitivity: str,
        metric_type: str,
    ) -> list[DetectedAnomaly]:
        """Detecta anomalias usando método configurado."""
        anomalies = []

        # Threshold por sensibilidade
        z_threshold_map = {"low": 4.0, "medium": 3.0, "high": 2.0}
        z_threshold = z_threshold_map.get(sensitivity, 3.0)

        for point in data:
            value = point["value"]
            timestamp = point["timestamp"]

            if method == "z_score" and baseline_std_dev > 0:
                z_score = (value - baseline_mean) / baseline_std_dev

                if abs(z_score) > z_threshold:
                    deviation_percent = ((value - baseline_mean) / baseline_mean) * 100.0
                    anomalies.append(
                        DetectedAnomaly(
                            metric_type=metric_type,
                            timestamp=timestamp,
                            observed_value=value,
                            expected_value=baseline_mean,
                            deviation_percent=deviation_percent,
                            z_score=z_score,
                            severity="high",  # Classificado depois
                        )
                    )

        return anomalies

    async def _classify_severity(
        self,
        deviation_percent: float,
        z_score: float | None,
    ) -> str:
        """Classifica severidade da anomalia."""
        abs_deviation = abs(deviation_percent)

        if abs_deviation > 100:
            return "critical"
        elif abs_deviation > 50:
            return "high"
        elif abs_deviation > 25:
            return "medium"
        else:
            return "low"

    async def _send_alerts(
        self,
        anomalies: list[DetectedAnomaly],
        channel: str,
    ) -> int:
        """Envia alertas via canal configurado (stub)."""
        # Stub: marca anomalias como alertadas
        alerts_sent = 0
        for anomaly in anomalies:
            if anomaly.severity in ["high", "critical"]:
                anomaly.alert_sent = True
                anomaly.alert_channel = channel
                alerts_sent += 1

        return alerts_sent
