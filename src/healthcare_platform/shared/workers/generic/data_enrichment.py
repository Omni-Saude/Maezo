"""
Generic Data Enrichment Worker

Handles data enrichment and lookup workflows:
- Patient record enrichment
- Clinical data augmentation
- Reference data lookups

Default error_strategy: fail_safe (enrichment failures should not block processing)
Missing enrichment data is acceptable; core workflows must continue unimpeded.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver
from healthcare_platform.shared.workers.base import TaskContext, TaskResult
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


class GenericDataEnrichmentWorker(GenericWorkerBase):
    """
    Generic worker for DATA_ENRICHMENT archetype.

    Handles data enrichment and lookup workflows that augment existing records.
    Enforces fail_safe strategy: enrichment failures must not block processing
    since the underlying data is still valid without the enriched fields.
    Post-processing marks enriched fields with an _enriched metadata flag.
    """

    ARCHETYPE = "DATA_ENRICHMENT"

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
        Initialize data enrichment worker.

        Enforces fail_safe as default: enrichment failures must not block workflows.
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

    def _tag_enriched_fields(
        self,
        result: Dict[str, Any],
        original_keys: set,
    ) -> Dict[str, Any]:
        """
        Mark fields added by enrichment with an _enriched metadata entry.

        Compares current result keys against the original context variable keys
        to identify newly added fields, then records them in the _enriched list.
        This allows consumers to distinguish authoritative data from lookups.
        """
        enriched_fields = [key for key in result if key not in original_keys]

        if enriched_fields:
            result["_enriched"] = enriched_fields
            self.logger.debug(
                "Data enrichment tagged fields",
                extra={"topic": self.topic, "enriched_fields": enriched_fields},
            )
        else:
            result["_enriched"] = []

        return result

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute data enrichment workflow.

        Evaluates DMN decisions and tags newly added fields with _enriched metadata.
        Uses fail_safe: returns requires_review on DMN failure.
        """
        try:
            _inputs = self._map_inputs(context)
            original_keys: set = set(context.variables.keys())

            decisions = self._build_decisions()
            if not decisions:
                return TaskResult.bpmn_error(
                    error_code="NO_DECISIONS_CONFIGURED",
                    error_message="Data enrichment worker has no decisions configured",
                )

            dmn_results = self._execute_dmn_pipeline(context, decisions)
            merged = self._merge_results(dmn_results)
            output = self._map_outputs(merged, context)
            output = self._tag_enriched_fields(output, original_keys)

            return TaskResult.success(output)

        except Exception as e:
            return self._handle_dmn_error(e, context)
