"""
Generic Compliance Validation Worker

Handles regulatory compliance check workflows:
- ANS (Agência Nacional de Saúde Suplementar) rules
- SUS (Sistema Único de Saúde) requirements
- LGPD (Lei Geral de Proteção de Dados) checks

Default error_strategy: fail_closed (compliance failures must block processing)
Regulatory violations must never be silently ignored.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


class GenericComplianceValidationWorker(GenericWorkerBase):
    """
    Generic worker for COMPLIANCE_VALIDATION archetype.

    Handles regulatory compliance checks for ANS, SUS, and LGPD frameworks.
    Enforces fail_closed strategy: compliance evaluation failures must block
    processing to prevent regulatory violations from passing undetected.
    Post-processing guarantees compliant boolean and violations list are present.
    """

    ARCHETYPE = "COMPLIANCE_VALIDATION"

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
        Initialize compliance validation worker.

        Enforces fail_closed as default: compliance errors must block workflows.
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

    def _ensure_compliance_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure compliance result contains required regulatory fields.

        The compliant boolean and violations list must always be present so
        downstream gateways can evaluate regulatory status unambiguously.
        If DMN omits these fields, the result is treated as non-compliant
        with an explanatory violation entry.
        """
        if "compliant" not in result:
            result["compliant"] = False
            self.logger.warning(
                "Compliance result missing 'compliant' field — defaulted to False",
                extra={"topic": self.topic},
            )

        if not isinstance(result.get("violations"), list):
            existing: Any = result.get("violations")
            violations: List[str] = [str(existing)] if existing else []
            if not result["compliant"] and not violations:
                violations.append("Compliance status unclear: DMN returned no violation details")
            result["violations"] = violations

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute compliance validation workflow.

        Evaluates DMN decisions and ensures compliance verdict fields exist.
        Uses fail_closed: raises BPMN error on DMN failure.
        """
        try:
            _inputs = self._map_inputs(context)

            decisions = self._build_decisions()
            if not decisions:
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Compliance validation worker has no decisions configured",
                )

            dmn_results = self._execute_dmn_pipeline(context, decisions)
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)
            output = self._ensure_compliance_fields(output)

            return TaskResult.success(output)

        except Exception as e:
            return self._handle_dmn_error(e, context)
