"""
Generic Financial Calculation Worker

Handles financial computation workflows:
- Pricing calculations
- Discount determination
- Penalty assessments

Default error_strategy: fail_closed (financial errors must block processing)
Financial calculation failures must never silently produce incorrect amounts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase

_CURRENCY_FIELDS = (
    "amount",
    "total",
    "price",
    "discount",
    "penalty",
    "reimbursement",
    "copay",
    "deductible",
)


class GenericFinancialCalculationWorker(GenericWorkerBase):
    """
    Generic worker for FINANCIAL_CALCULATION archetype.

    Handles financial computation workflows producing monetary outputs.
    Enforces fail_closed strategy: financial calculation errors must block
    processing to prevent incorrect billing or reimbursement amounts.
    Post-processing rounds all numeric currency fields to 2 decimal places.
    """

    ARCHETYPE = "FINANCIAL_CALCULATION"

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
        Initialize financial calculation worker.

        Enforces fail_closed as default: financial errors must never be silent.
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

    def _round_currency_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Round all currency fields to 2 decimal places.

        Iterates known financial field names, coercing values to float and
        rounding to BRL-safe precision. Non-numeric values raise ValueError
        to trigger fail_closed error handling.
        """
        for field in _CURRENCY_FIELDS:
            if field in result:
                try:
                    result[field] = round(float(result[field]), 2)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Financial field '{field}' contains non-numeric value: {result[field]!r}"
                    ) from exc

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute financial calculation workflow.

        Evaluates DMN decisions and rounds currency fields to 2 decimal places.
        Uses fail_closed: raises BPMN error on DMN or rounding failure.
        """
        try:
            inputs = self._map_inputs(context)

            decisions = self._build_decisions()
            if not decisions:
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Financial calculation worker has no decisions configured",
                )

            dmn_results = self._execute_dmn_pipeline(context, decisions)
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)
            output = self._round_currency_fields(output)

            return TaskResult.success(output)

        except Exception as e:
            return self._handle_dmn_error(e, context)
