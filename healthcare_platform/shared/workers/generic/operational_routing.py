"""
Generic Operational Routing Worker

Handles routing decision workflows:
- Triage routing
- Bed assignment
- Department routing

Default error_strategy: fail_closed (routing must be deterministic)
Routing failures must block rather than silently misdirect patients.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


class GenericOperationalRoutingWorker(GenericWorkerBase):
    """
    Generic worker for OPERATIONAL_ROUTING archetype.

    Handles routing decision workflows that must be deterministic and explicit.
    Enforces fail_closed strategy: blocks on DMN failure to prevent patients
    or resources from being silently misdirected.
    Post-processing guarantees next_state and assigned_to fields are present.
    """

    ARCHETYPE = "OPERATIONAL_ROUTING"

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
        Initialize operational routing worker.

        Enforces fail_closed as default: routing errors must never be silent.
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

    def _validate_routing_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure routing result contains required destination fields.

        Both next_state and assigned_to must be present for downstream
        BPMN gateways to route correctly. Missing fields default to PENDING
        and UNASSIGNED respectively, with a warning logged.
        """
        if "next_state" not in result or not result["next_state"]:
            result["next_state"] = "PENDING"
            self.logger.warning(
                "Routing decision missing next_state — defaulted to PENDING",
                extra={"topic": self.topic},
            )

        if "assigned_to" not in result or not result["assigned_to"]:
            result["assigned_to"] = "UNASSIGNED"
            self.logger.warning(
                "Routing decision missing assigned_to — defaulted to UNASSIGNED",
                extra={"topic": self.topic},
            )

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute operational routing decision workflow.

        Evaluates DMN decisions and validates routing destination fields.
        Uses fail_closed: raises BPMN error on DMN failure.
        """
        try:
            inputs = self._map_inputs(context)

            decisions = self._build_decisions()
            if not decisions:
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Operational routing worker has no decisions configured",
                )

            dmn_results = self._execute_dmn_pipeline(context, decisions)
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)
            output = self._validate_routing_result(output)

            return TaskResult.success(output)

        except Exception as e:
            result = self._handle_dmn_error(e, context)
            current_state = context.variables.get("current_state", "unknown")
            if hasattr(result, 'variables') and isinstance(result.variables, dict):
                result.variables["current_state"] = current_state
                result.variables["escalate_to_supervisor"] = True
            return result
