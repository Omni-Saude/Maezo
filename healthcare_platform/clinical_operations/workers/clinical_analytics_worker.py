"""
Clinical Analytics Worker V2 - TOPIC: clinical.analytics

Refactored from 652 lines to ~130 lines using DMN-first approach.
Business rules extracted to 14 DMN tables under clinical_safety/analytics/.
Archetype: CLINICAL_SCORE (KPI thresholds, benchmarks, scoring).

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""

from __future__ import annotations
from datetime import datetime
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult

_DMN_KEYS = {
    "kpi": "analytics_kpi_threshold", "trend": "analytics_trend_analysis", "anomaly": "analytics_anomaly_detection",
    "benchmark": "analytics_benchmark_comparison", "department": "analytics_department_scoring", "provider": "analytics_provider_scoring",
    "patient_flow": "analytics_patient_flow", "resource": "analytics_resource_utilization", "outcome": "analytics_outcome_correlation",
    "predictive": "analytics_predictive_threshold", "quality": "analytics_quality_indicator", "regulatory": "analytics_regulatory_metric",
    "cost": "analytics_cost_efficiency", "efficiency": "analytics_clinical_efficiency",
}


class ClinicalAnalyticsWorker(BaseExternalTaskWorker):
    """V2 clinical analytics worker (thin worker pattern)."""

    TOPIC = "clinical.analytics"
    DMN_DECISION_KEY = "analytics_kpi_threshold"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute clinical analytics via DMN evaluation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            analytics_type = variables.get("analytics_type", "kpi")
            metric_value = variables.get("metric_value", 0.0)
            metric_name = variables.get("metric_name", "")

            self.logger.info("Processing analytics: type=%s, metric=%s", analytics_type, metric_name,
                             extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id})

            # Evaluate primary KPI threshold DMN
            decision_key = _DMN_KEYS.get(analytics_type, self.DMN_DECISION_KEY)
            kpi_result = self.evaluate_dmn(
                context=context, decision_key=decision_key,
                variables={"analyticsType": analytics_type, "metricName": metric_name, "metricValue": metric_value,
                          "department": variables.get("department_filter") or "", "granularity": variables.get("granularity", "daily")},
                category=self.DMN_CATEGORY,
            )

            action = kpi_result.get("action", "REVISAR")

            # Evaluate benchmark comparison if requested
            benchmark_result = {}
            if variables.get("benchmark_comparison", False):
                benchmark_result = self.evaluate_dmn(
                    context=context, decision_key=_DMN_KEYS["benchmark"],
                    variables={"analyticsType": analytics_type, "metricValue": metric_value, "metricName": metric_name},
                    category=self.DMN_CATEGORY,
                )

            # Evaluate quality indicator scoring
            quality_result = {}
            if analytics_type in ("quality", "kpi", "efficiency"):
                quality_result = self.evaluate_dmn(
                    context=context, decision_key=_DMN_KEYS["quality"],
                    variables={"metricName": metric_name, "metricValue": metric_value, "department": variables.get("department_filter") or ""},
                    category=self.DMN_CATEGORY,
                )

            return TaskResult.success({
                "action": action,
                "nivelAlerta": kpi_result.get("nivelAlerta", "OK"),
                "acaoRequerida": kpi_result.get("acaoRequerida", ""),
                "justificativa": kpi_result.get("justificativa", ""),
                "kpiStatus": kpi_result.get("kpiStatus", "within_target"),
                "kpiScore": kpi_result.get("kpiScore", 0.0),
                "threshold": kpi_result.get("threshold", 0.0),
                "variance": kpi_result.get("variance", 0.0),
                "benchmarkRating": benchmark_result.get("performanceRating", ""),
                "benchmarkVariance": benchmark_result.get("variance", 0.0),
                "qualityScore": quality_result.get("qualityScore", 0.0),
                "qualityLevel": quality_result.get("qualityLevel", ""),
                "analyticsType": analytics_type,
                "processedAt": datetime.utcnow().isoformat(),
                "dmnDecisionKey": decision_key,
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Analytics processing failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_CLINICAL_ANALYTICS", error_message=str(e), variables={"errorType": type(e).__name__})
