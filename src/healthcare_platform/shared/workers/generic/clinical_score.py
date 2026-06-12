"""
Generic Clinical Score Worker

Handles score calculation workflows:
- Audit scores
- Compliance scores
- Risk scores

Default error_strategy: fail_safe (score failures should not block clinical workflows)
Ensures numeric output clamped to 0-100 range when applicable.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase

_SCORE_FIELDS = ("score", "audit_score", "compliance_score", "risk_score")


class GenericClinicalScoreWorker(GenericWorkerBase):
    """
    Generic worker for CLINICAL_SCORE archetype.

    Handles score calculation workflows producing numeric outputs.
    Enforces fail_safe strategy: returns requires_review on DMN failure so
    clinical operations are not blocked by scoring engine errors.
    Post-processing guarantees numeric score output clamped to [0, 100].
    """

    ARCHETYPE = "CLINICAL_SCORE"

    def __init__(
        self,
        topic: str,
        registry_config: dict,
        dmn_service: Optional[FederatedDMNService] = None,
        tenant_resolver: Optional[TenantResolver] = None,
        lgpd_hasher: Optional[LGPDHasher] = None,
        metrics: Optional[WorkerMetrics] = None,
        logger=None,
        **kwargs,
    ):
        """
        Initialize clinical score worker.

        Enforces fail_safe as default: score failures must not block workflows.
        """
        if "error_strategy" not in registry_config:
            registry_config["error_strategy"] = "fail_safe"

        super().__init__(
            topic=topic,
            registry_config=registry_config,
            dmn_service=dmn_service,
            tenant_resolver=tenant_resolver,
            lgpd_hasher=lgpd_hasher,
            metrics=metrics,
            logger=logger,
            **kwargs,
        )

    def _normalize_scores(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure numeric score fields exist and clamp values to [0, 100].

        Iterates known score field names and coerces to float, clamping
        any out-of-range value. Non-numeric values are replaced with 0.0.
        """
        for field in _SCORE_FIELDS:
            if field in result:
                try:
                    value = float(result[field])
                    result[field] = max(0.0, min(100.0, value))
                except (TypeError, ValueError):
                    self.logger.warning(
                        "Non-numeric score field replaced with 0.0",
                        extra={"topic": self.topic, "field": field, "value": result[field]},
                    )
                    result[field] = 0.0

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute clinical score calculation workflow.

        Evaluates DMN decisions and normalizes numeric score outputs.
        Uses fail_safe: returns requires_review on DMN failure.
        """
        try:
            _inputs = self._map_inputs(context)

            decisions = self._build_decisions()
            if not decisions:
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Clinical score worker has no decisions configured",
                )

            dmn_results = self._execute_dmn_pipeline(context, decisions)
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)
            output = self._normalize_scores(output)

            return TaskResult.success(output)

        except Exception as e:
            result = self._handle_dmn_error(e, context)
            if hasattr(result, 'variables') and isinstance(result.variables, dict):
                result.variables.update({"score": 0, "level": "unknown"})
            return result
