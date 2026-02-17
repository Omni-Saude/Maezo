"""
Generic Clinical Alert Worker

Handles clinical alerting workflows:
- Clinical safety alerts
- Patient monitoring notifications
- Threshold breach alerts

Default error_strategy: fail_safe (alert failures should not block clinical workflows)
Ensures alert delivery without halting patient care processes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


class GenericClinicalAlertWorker(GenericWorkerBase):
    """
    Generic worker for CLINICAL_ALERT archetype.

    Handles clinical safety alerting workflows that must not block patient care.
    Enforces fail_safe strategy: logs and continues on DMN failure to prevent
    alert processing from halting clinical operations.
    """

    ARCHETYPE = "CLINICAL_ALERT"

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
        Initialize clinical alert worker.

        Enforces fail_safe as default to prevent alert failures blocking care.
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

    def _ensure_alert_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure alert result contains required alert routing fields.

        Provides defaults so downstream consumers always receive
        well-formed alert metadata even when DMN returns partial output.
        """
        if "alert_level" not in result or not result["alert_level"]:
            result["alert_level"] = "INFO"
            self.logger.info(
                "Clinical alert defaulted to INFO level",
                extra={"topic": self.topic, "reason": "No alert_level in DMN output"},
            )

        result.setdefault("requires_acknowledgment", False)
        result.setdefault("notified_roles", [])

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute clinical alert evaluation workflow.

        Evaluates DMN decisions and ensures alert fields are present.
        Uses fail_safe: returns requires_review on DMN failure.
        """
        try:
            inputs = self._map_inputs(context)

            decisions = self._build_decisions()
            if not decisions:
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Clinical alert worker has no decisions configured",
                )

            dmn_results = self._execute_dmn_pipeline(context, decisions)
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)
            output = self._ensure_alert_fields(output)

            return TaskResult.success(output)

        except Exception as e:
            return self._handle_dmn_error(e, context)
