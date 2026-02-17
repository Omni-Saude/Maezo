"""Worker for detecting revenue anomalies using statistical methods."""
from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class RevenueAnomaly(BaseModel):
    """    Anomalia detectada nas receitas.
    
        Archetype: FINANCIAL_CALCULATION
        """

    category: str
    description: str
    current_value: float
    expected_value: float
    deviation: float
    z_score: float
    severity: str  # low, medium, high, critical


class AlertAnomaliesWorker:
    """Detecta anomalias nas receitas usando z-score (>2 desvios padrão)."""

    WORKER_TYPE = "alert_anomalies"

    def __init__(self) -> None:
        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)

    def _evaluate_cash_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate cash_operations DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id='default',
                category='cash_operations',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @track_task_execution(metric_name="alert_anomalies")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Detecta anomalias usando análise estatística.

        Args:
            task_variables: {
                "current_period": {
                    "collections": float,
                    "denials": int,
                    "payment_time_avg": float
                },
                "historical_data": list[dict] (last 30-90 days)
            }

        Returns:
            {
                "anomalies": list[RevenueAnomaly],
                "total_anomalies": int,
                "critical_anomalies": int,
                "requires_attention": bool
            }
        """
        current = task_variables["current_period"]
        historical = task_variables["historical_data"]

        logger.info(
            _("Detectando anomalias nas receitas"),
            extra={
                "historical_periods": len(historical),
                "current_collections": current["collections"],
            },
        )

        if len(historical) < 7:
            logger.warning(
                _("Dados históricos insuficientes para análise de anomalias")
            )
            return {
                "anomalies": [],
                "total_anomalies": 0,
                "critical_anomalies": 0,
                "requires_attention": False,
            }

        anomalies: list[RevenueAnomaly] = []

        # Check collections
        collections_anomaly = self._detect_anomaly(
            current_value=current["collections"],
            historical_values=[h["collections"] for h in historical],
            category="collections",
            description=_("Arrecadação do período"),
        )
        if collections_anomaly:
            anomalies.append(collections_anomaly)

        # Check denials
        denials_anomaly = self._detect_anomaly(
            current_value=float(current["denials"]),
            historical_values=[float(h["denials"]) for h in historical],
            category="denials",
            description=_("Número de negativas"),
        )
        if denials_anomaly:
            anomalies.append(denials_anomaly)

        # Check payment time
        payment_time_anomaly = self._detect_anomaly(
            current_value=current["payment_time_avg"],
            historical_values=[h["payment_time_avg"] for h in historical],
            category="payment_time",
            description=_("Tempo médio de pagamento"),
        )
        if payment_time_anomaly:
            anomalies.append(payment_time_anomaly)

        critical_anomalies = sum(
            1 for a in anomalies if a.severity in ["high", "critical"]
        )

        logger.info(
            _("Detecção de anomalias concluída"),
            extra={
                "total_anomalies": len(anomalies),
                "critical_anomalies": critical_anomalies,
            },
        )

        return {
            "anomalies": [a.model_dump() for a in anomalies],
            "total_anomalies": len(anomalies),
            "critical_anomalies": critical_anomalies,
            "requires_attention": critical_anomalies > 0,
        }

    def _detect_anomaly(
        self,
        current_value: float,
        historical_values: list[float],
        category: str,
        description: str,
    ) -> RevenueAnomaly | None:
        """Detect anomaly using z-score (>2 std dev)."""
        if len(historical_values) < 7:
            return None

        mean = statistics.mean(historical_values)
        stdev = statistics.stdev(historical_values)

        if stdev == 0:
            return None

        z_score = (current_value - mean) / stdev

        # Only report if z-score > 2 (significant deviation)
        if abs(z_score) <= 2:
            return None

        deviation = ((current_value - mean) / mean) * 100

        # Determine severity based on z-score
        if abs(z_score) >= 4:
            severity = "critical"
        elif abs(z_score) >= 3:
            severity = "high"
        elif abs(z_score) >= 2.5:
            severity = "medium"
        else:
            severity = "low"

        return RevenueAnomaly(
            category=category,
            description=description,
            current_value=round(current_value, 2),
            expected_value=round(mean, 2),
            deviation=round(deviation, 2),
            z_score=round(z_score, 2),
            severity=severity,
        )
