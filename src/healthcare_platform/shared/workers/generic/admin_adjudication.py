"""
Generic Admin Adjudication Worker

Handles administrative decision-making workflows:
- Claim validation
- Authorization approval
- Coverage determination

Default error_strategy: fail_closed (BLOQUEAR on DMN failure)
Never proceeds with approval if decision rules fail.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


class GenericAdminAdjudicationWorker(GenericWorkerBase):
    """
    Generic worker for ADMIN_ADJUDICATION archetype.

    Handles administrative decision-making workflows that require explicit actions.
    Enforces fail_closed strategy: blocks on DMN failure to prevent unauthorized approvals.
    """

    ARCHETYPE = "ADMIN_ADJUDICATION"

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
        Initialize admin adjudication worker.

        Enforces fail_closed as default for admin decisions.
        """
        if "error_strategy" not in registry_config:
            registry_config["error_strategy"] = "fail_closed"

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

    def _validate_admin_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure admin decisions always have an explicit action.

        If DMN returns no action, default to REVISAR (manual review).
        This prevents workflows from proceeding without explicit authorization.
        """
        if "action" not in result or not result["action"]:
            result["action"] = "REVISAR"
            result["reason"] = "DMN returned no explicit action — flagged for manual review"
            self.logger.info(
                "Admin decision defaulted to REVISAR",
                extra={
                    "topic": self.topic,
                    "reason": "No explicit action in DMN output",
                },
            )

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute admin adjudication workflow.

        Evaluates DMN decision and validates explicit action is present.
        """
        try:
            # Map inputs
            _inputs = self._map_inputs(context)

            # Execute DMN decision
            decisions = self._build_decisions()
            if not decisions:
                # No decisions configured, return error
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Admin adjudication worker has no decisions configured",
                )

            # Execute pipeline
            dmn_results = self._execute_dmn_pipeline(context, decisions)

            # Merge and map outputs
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)

            # Validate admin result
            output = self._validate_admin_result(output)

            return TaskResult.success(output)

        except Exception as e:
            return self._handle_dmn_error(e, context)
