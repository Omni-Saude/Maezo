"""
Generic Worker Base: Archetype-specific DMN wrapper

Provides generic DMN evaluation framework for workers organized by business archetype.
Extends BaseExternalTaskWorker with:
- Registry-based DMN selection
- Error strategy pattern (fail_closed vs fail_safe)
- Pipeline execution for multi-table DMN workflows
- Result merging with configurable merge strategies
- Registry-based input/output key mapping
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult

# Priority order for restrictiveness (higher index = more restrictive; 0 = most restrictive)
ACTION_PRIORITY: Dict[str, int] = {
    "BLOQUEAR": 3,
    "REVISAR": 2,
    "PROSSEGUIR": 1,
}


class GenericWorkerConfigError(ValueError):
    """Raised when the registry config for a topic is invalid or incomplete."""


class GenericWorkerBase(BaseExternalTaskWorker):
    """
    Base class for generic archetype-specific workers.

    Provides DMN registry management and error handling strategies:
    - Registry: Maps archetypes to DMN decisions
    - Error strategies: fail_closed (BLOQUEAR) or fail_safe (REVISAR)
    - Pipeline execution: Chain multiple DMN evaluations
    """

    ARCHETYPE: Optional[str] = None  # Override in subclass

    def __init__(
        self,
        topic: str,
        registry_config: dict,
        dmn_service: Optional[FederatedDMNService] = None,
        tenant_resolver: Optional[TenantResolver] = None,
        lgpd_hasher: Optional[LGPDHasher] = None,
        metrics: Optional[WorkerMetrics] = None,
        logger: Optional[logging.Logger] = None,
        **kwargs,
    ):
        """
        Initialize generic worker with registry configuration.

        Args:
            topic: Worker topic name
            registry_config: Registry config with error_strategy, decisions, etc.
            dmn_service: DMN evaluation service
            tenant_resolver: Tenant resolution service
            lgpd_hasher: LGPD hashing service
            metrics: Metrics collector
            logger: Logger instance
        """
        super().__init__(
            dmn_service=dmn_service,
            tenant_resolver=tenant_resolver,
            lgpd_hasher=lgpd_hasher,
            metrics=metrics,
            logger=logger,
            **kwargs,
        )
        self.TOPIC: str = topic
        self.topic: str = topic  # alias kept for concrete subclasses
        self.registry_config: Dict[str, Any] = registry_config
        self._error_strategy: str = registry_config.get("error_strategy", "fail_closed")
        self.error_strategy: str = self._error_strategy  # alias for subclasses

        # Attributes for the template-method execute()
        self._dmn_pipeline: List[Dict[str, Any]] = registry_config.get("dmn_pipeline", [])
        self._single_dmn: Optional[str] = registry_config.get("dmn_key")
        self._dmn_category: str = registry_config.get("dmn_category", "clinical_safety")
        self._input_map: Dict[str, str] = registry_config.get("input_map", {})
        self._output_map: Dict[str, str] = registry_config.get("output_map", {})
        self._merge_strategy: str = registry_config.get("merge_strategy", "worst_case")

    # ------------------------------------------------------------------
    # Template method — concrete subclasses may override for enrichment
    # ------------------------------------------------------------------

    def execute(self, context: TaskContext) -> TaskResult:
        """Map inputs -> evaluate DMN(s) -> map outputs -> return TaskResult.

        Drives the full template-method lifecycle for config-driven workers.
        Concrete archetype subclasses may override this to add validation or
        enrichment while still calling the helper methods below.
        """
        _variables = self._map_inputs(context)
        decisions = self._build_decisions()

        if not decisions:
            return TaskResult.bpmn_error(
                error_code="NO_DMN_CONFIGURED",
                error_message=(
                    f"Topic '{self.TOPIC}' has no 'dmn_key', 'dmn_pipeline', "
                    "or 'decisions' in registry."
                ),
            )

        dmn_results = self._execute_dmn_pipeline(context, decisions)
        raw_result = self._merge_results(dmn_results, decisions)
        output = self._map_outputs(raw_result, context)

        resultado = raw_result.get("resultado", "PROSSEGUIR")
        if resultado == "BLOQUEAR":
            acao = raw_result.get("acao", "Blocked by DMN rule")
            return TaskResult.bpmn_error(
                error_code=f"{self.TOPIC.upper().replace('.', '_')}_BLOCKED",
                error_message=acao,
                variables=output,
            )

        return TaskResult.success(output)

    # ------------------------------------------------------------------
    # Input / output mapping
    # ------------------------------------------------------------------

    def _map_inputs(self, context: TaskContext) -> Dict[str, Any]:
        """
        Map task context variables to DMN inputs.

        Applies registry_config["input_map"] to rename context variable keys before
        passing them to DMN evaluation.  Keys not present in input_map are forwarded
        unchanged.

        Example registry_config::

            input_map:
              patientId: patient_id      # rename context key "patientId" → "patient_id"
              procedureCode: proc_code
        """
        variables = dict(context.variables)
        input_map: Dict[str, str] = self.registry_config.get("input_map", {})
        if not input_map:
            return variables

        mapped: Dict[str, Any] = {}
        for key, value in variables.items():
            mapped[input_map.get(key, key)] = value
        return mapped

    def _execute_single_dmn(
        self,
        context: TaskContext,
        decision_key: str,
        inputs: Dict[str, Any],
        category: str = "clinical_safety",
    ) -> Dict[str, Any]:
        """Evaluate a single DMN table and return its raw output dict.

        On error, applies the configured error_strategy:
          fail_closed — re-raise the exception.
          fail_safe   — log a warning and return an empty dict (pipeline continues).
        """
        try:
            return self.evaluate_dmn(context, decision_key, inputs, category)
        except Exception:
            if self._error_strategy == "fail_closed":
                raise
            self.logger.warning(
                "DMN evaluation failed (fail_safe): %s",
                decision_key,
                exc_info=True,
                extra={"topic": self.TOPIC, "decision_key": decision_key},
            )
            return {}

    def _build_decisions(self) -> List[Dict[str, Any]]:
        """
        Build the decisions list from registry_config.

        Supports three configuration formats (in priority order):

        1. ``dmn_pipeline`` — explicit list of step dicts (new format from topic_registry.yaml).
        2. ``dmn_key`` — single DMN key; wrapped into a one-item pipeline list.
        3. ``decisions`` — legacy format used by existing workers.

        Each step dict may contain:
            key (str): DMN decision table key — required.
            category (str): DMN category/tenant scope — defaults to "default".
            inputs (dict): Extra static inputs merged with mapped context variables.
            merge_strategy (str): How to merge this step's output — defaults to "override".
        """
        if "dmn_pipeline" in self.registry_config:
            return list(self.registry_config["dmn_pipeline"])

        if "dmn_key" in self.registry_config:
            return [{"key": self.registry_config["dmn_key"]}]

        # Legacy format — existing workers (GenericAdminAdjudicationWorker,
        # GenericClinicalAlertWorker) pass this directly.
        return list(self.registry_config.get("decisions", []))

    def _execute_dmn_pipeline(
        self,
        context: TaskContext,
        decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute pipeline of DMN decisions.

        Args:
            context: Task execution context.
            decisions: Explicit decisions list.  When ``None`` (or when the caller
                passes an explicit list obtained from registry_config["decisions"]),
                the pipeline is also resolved via :meth:`_build_decisions` as a
                fallback so that all three registry_config formats work:
                ``dmn_pipeline``, ``dmn_key``, and ``decisions``.

        Returns:
            List of raw DMN result dicts, one per pipeline step.  The ordering
            matches the decisions list so that callers can zip them together
            when they need per-step merge_strategy data.
        """
        if decisions is None:
            decisions = self._build_decisions()

        results: List[Dict[str, Any]] = []
        running_vars = dict(context.variables)

        for decision_config in decisions:
            # Support both "key" (legacy) and "dmn_key" (new format) field names
            decision_key: str = decision_config.get("key") or decision_config.get("dmn_key", "")
            category: str = decision_config.get(
                "category", decision_config.get("dmn_category", self._dmn_category)
            )
            # Merge running context with any static extra inputs for this stage
            extra_inputs: Dict[str, Any] = decision_config.get(
                "inputs", decision_config.get("static_inputs", {})
            )
            stage_inputs = {**running_vars, **extra_inputs}

            result = self._execute_single_dmn(context, decision_key, stage_inputs, category)
            results.append(result)
            # Propagate stage outputs as inputs for subsequent stages
            running_vars.update(result)

        return results

    def _apply_merge_strategy(
        self,
        accumulated: Dict[str, Any],
        new_result: Dict[str, Any],
        strategy: str,
    ) -> Dict[str, Any]:
        """
        Apply a single merge step using the given strategy.

        Strategies
        ----------
        override
            ``new_result`` overwrites every key in ``accumulated``.  This is the
            legacy behaviour (equivalent to ``dict.update``).

        worst_case
            For fields named ``"resultado"`` or ``"action"``, keep whichever
            value has the *higher* ``ACTION_PRIORITY`` (most restrictive).
            All other fields use ``override`` semantics.

        best_case
            Same as ``worst_case`` but keeps the *lower* priority value (least
            restrictive).  All other fields use ``override`` semantics.

        append
            Values for each key are collected into a list.  Existing scalar
            values are wrapped in a list on first collision.

        Args:
            accumulated: The running merged result so far.
            new_result: Output from the latest DMN step.
            strategy: One of ``"override"``, ``"worst_case"``, ``"best_case"``,
                ``"append"``.  Unknown values fall back to ``"override"``.

        Returns:
            New accumulated dict after applying the strategy.
        """
        ACTION_FIELDS = {"resultado", "action"}

        if strategy == "append":
            merged = dict(accumulated)
            for key, value in new_result.items():
                if key in merged:
                    existing = merged[key]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        merged[key] = [existing, value]
                else:
                    merged[key] = value
            return merged

        if strategy in ("worst_case", "best_case"):
            merged = dict(accumulated)
            for key, value in new_result.items():
                if key in ACTION_FIELDS and key in merged:
                    existing_priority = ACTION_PRIORITY.get(str(merged[key]).upper(), 0)
                    new_priority = ACTION_PRIORITY.get(str(value).upper(), 0)
                    if strategy == "worst_case":
                        # Keep the more restrictive (higher priority) value
                        if new_priority > existing_priority:
                            merged[key] = value
                    else:  # best_case
                        # Keep the less restrictive (lower priority) value
                        if new_priority < existing_priority:
                            merged[key] = value
                else:
                    # Non-action fields always take the new value
                    merged[key] = value
            return merged

        # Default: "override" — new result wins for every key
        merged = dict(accumulated)
        if new_result:
            merged.update(new_result)
        return merged

    def _merge_results(
        self,
        results: List[Dict[str, Any]],
        decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Merge pipeline results into a single output dict.

        When ``decisions`` is provided each step's ``merge_strategy`` key is
        used to control how that step's output is folded into the accumulator.
        When ``decisions`` is omitted the default ``"override"`` strategy is
        applied to every step (backward-compatible behaviour).

        Args:
            results: List of DMN result dicts returned by :meth:`_execute_dmn_pipeline`.
            decisions: Optional parallel decisions list so per-step
                ``merge_strategy`` values can be read.

        Returns:
            Single merged dict.
        """
        merged: Dict[str, Any] = {}
        for idx, result in enumerate(results):
            if not result:
                continue
            # Per-step merge_strategy overrides the global one; global is the fallback
            global_strategy = self._merge_strategy
            if decisions is not None and idx < len(decisions):
                strategy = decisions[idx].get("merge_strategy", global_strategy)
            else:
                strategy = global_strategy
            merged = self._apply_merge_strategy(merged, result, strategy)
        return merged

    def _map_outputs(self, merged: Dict[str, Any], context: TaskContext) -> Dict[str, Any]:
        """
        Map DMN output keys to the names expected by downstream BPMN tasks.

        Applies registry_config["output_map"] to rename fields in the merged
        DMN result.  Keys not present in output_map are forwarded unchanged.

        Example registry_config::

            output_map:
              resultado: authorization_result   # rename DMN field → BPMN variable
              motivo: denial_reason
        """
        output_map: Dict[str, str] = self.registry_config.get("output_map", {})
        if not output_map:
            return merged

        remapped: Dict[str, Any] = {}
        for key, value in merged.items():
            remapped[output_map.get(key, key)] = value
        return remapped

    def _handle_dmn_error(self, error: Exception, context: TaskContext) -> TaskResult:
        """Handle a DMN evaluation error per the configured error_strategy.

        fail_safe:    log a warning and return TaskResult.success with a REVISAR
                      sentinel so the pipeline can continue (no exception raised).
        fail_closed:  return TaskResult.bpmn_error with BLOQUEAR so the BPMN
                      error boundary is triggered without re-raising.
        """
        if self._error_strategy == "fail_safe":
            self.logger.warning(
                "DMN error handled with fail_safe (topic=%s, tenant=%s): %s",
                self.TOPIC,
                context.tenant_id,
                error,
                exc_info=True,
            )
            return TaskResult.success({
                "resultado": "REVISAR",
                "acao": "Revisão manual necessária",
                "risco": "ALTO",
                "dmn_error": str(error),
            })

        # fail_closed: surface as BPMN error so Camunda triggers the error boundary
        self.logger.error(
            "DMN error handled with fail_closed (topic=%s, tenant=%s): %s",
            self.TOPIC,
            context.tenant_id,
            error,
            exc_info=True,
        )
        return TaskResult.bpmn_error(
            error_code="DMN_ERROR_BLOCKED",
            error_message=str(error),
            variables={
                "resultado": "BLOQUEAR",
                "acao": "Bloqueado por erro DMN",
                "risco": "CRITICO",
                "dmn_error": str(error),
            },
        )
