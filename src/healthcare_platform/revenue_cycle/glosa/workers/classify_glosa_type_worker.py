"""
Classify Glosa Type Worker

Worker responsible for classifying glosas into types (administrative, technical,
linear, total, partial) based on reason codes and denial patterns.
"""

from decimal import Decimal
from typing import Any, Dict

from healthcare_platform.revenue_cycle.glosa.workers.base import (
    BaseWorker,
    GlosaWorkerMixin,
    WorkerResult,
    worker,
)
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import GlosaReasonCode, GlosaType
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="classify-glosa-type", max_jobs=10, lock_duration=30000)
class ClassifyGlosaTypeWorker(BaseWorker, GlosaWorkerMixin):
    """
    Worker that classifies glosas by type.

    Analyzes glosa items to determine if they are administrative, technical,
    linear, total, or partial denials based on reason codes and amounts.

    Input Variables:
        - glosaItems: List of identified glosa items
        - reasonCode: Optional specific reason code to filter

    Output Variables:
        - classifiedGlosas: List of glosas with type classification added
        - glosaTypeDistribution: Dict mapping type to count
        - hasAdministrative: Boolean for administrative glosas
        - hasTechnical: Boolean for technical glosas

        Archetype: CLINICAL_SCORE
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    def _evaluate_glosa_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate glosa_prevention DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='glosa_prevention',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    def _evaluate_appeal_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate revenue_recovery DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='revenue_recovery',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    # Mapping of reason codes to glosa categories
    REASON_TO_CATEGORY = {
        GlosaReasonCode.MISSING_AUTH: "administrative",
        GlosaReasonCode.EXPIRED_AUTH: "administrative",
        GlosaReasonCode.DUPLICATE_CHARGE: "administrative",
        GlosaReasonCode.EXCEEDS_QUANTITY: "technical",
        GlosaReasonCode.NOT_COVERED: "technical",
        GlosaReasonCode.WRONG_CODE: "technical",
        GlosaReasonCode.MISSING_DOCUMENTATION: "technical",
        GlosaReasonCode.INCOMPATIBLE_PROCEDURE: "technical",
        GlosaReasonCode.PRICE_DIVERGENCE: "linear",
        GlosaReasonCode.TISS_VALIDATION: "technical",
    }

    async def process_task(self, job: Any, variables: Dict[str, Any]) -> WorkerResult:
        """
        Process glosa items to classify by type.

        Args:
            job: Zeebe job object
            variables: Process variables containing glosaItems

        Returns:
            WorkerResult with classified glosas and distribution
        """
        logger.info(
            _("Iniciando classificação de tipos de glosa"),
            extra={"job_key": job.key if hasattr(job, "key") else None},
        )

        try:
            # Extract glosa items
            glosa_items = variables.get("glosaItems", [])
            if not glosa_items:
                logger.warning(_("Nenhuma glosa encontrada para classificação"))
                return WorkerResult.success(
                    {
                        "classifiedGlosas": [],
                        "glosaTypeDistribution": {},
                        "hasAdministrative": False,
                        "hasTechnical": False,
                    }
                )

            # Optional filter by reason code
            reason_code_filter = variables.get("reasonCode")

            # Classify each glosa
            classified_glosas = []
            type_counts = {
                GlosaType.ADMINISTRATIVE.value: 0,
                GlosaType.TECHNICAL.value: 0,
                GlosaType.LINEAR.value: 0,
                GlosaType.TOTAL.value: 0,
                GlosaType.PARTIAL.value: 0,
            }

            for glosa in glosa_items:
                # Filter if reason code specified
                if reason_code_filter and glosa.get("reason_code") != reason_code_filter:
                    continue

                # Classify this glosa
                classified = self._classify_glosa(glosa)
                classified_glosas.append(classified)

                # Update counts
                glosa_type = classified.get("glosa_type")
                if glosa_type:
                    type_counts[glosa_type] = type_counts.get(glosa_type, 0) + 1

            # Build output
            output_variables = {
                "classifiedGlosas": classified_glosas,
                "glosaTypeDistribution": type_counts,
                "hasAdministrative": type_counts.get(
                    GlosaType.ADMINISTRATIVE.value, 0
                )
                > 0,
                "hasTechnical": type_counts.get(GlosaType.TECHNICAL.value, 0) > 0,
            }

            logger.info(
                _("Classificadas {count} glosas").format(count=len(classified_glosas)),
                extra={"distribution": type_counts},
            )

            return WorkerResult.success(output_variables)

        except Exception as e:
            logger.exception(_("Erro inesperado ao classificar glosas"))
            return WorkerResult.failure(
                _("Erro ao classificar tipos de glosa: {error}").format(error=str(e))
            )

    def _classify_glosa(self, glosa: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single glosa by type.

        Args:
            glosa: Glosa item dictionary

        Returns:
            Glosa with glosa_type field added
        """
        classified = glosa.copy()

        # Get reason code
        reason_code_str = glosa.get("reason_code")
        try:
            reason_code = GlosaReasonCode(reason_code_str)
        except (ValueError, TypeError):
            logger.warning(
                _("Código de motivo inválido: {code}").format(code=reason_code_str)
            )
            reason_code = GlosaReasonCode.TISS_VALIDATION

        # Determine category (administrative, technical, linear)
        category = self.REASON_TO_CATEGORY.get(reason_code, "technical")

        # Determine if total or partial denial
        denied_amount = Decimal(str(glosa.get("denied_amount", 0)))
        original_amount = Decimal(str(glosa.get("original_amount", 0)))

        if original_amount > 0:
            denial_ratio = denied_amount / original_amount
            if denial_ratio >= Decimal("1.0"):
                # 100% denied = total
                extent = GlosaType.TOTAL.value
            elif denial_ratio > 0:
                # Partial denial
                extent = GlosaType.PARTIAL.value
            else:
                # No denial?
                extent = GlosaType.PARTIAL.value
        else:
            extent = GlosaType.TOTAL.value

        # For linear glosas (price divergence), always mark as PARTIAL
        # unless the entire amount was denied
        if category == "linear":
            classified["glosa_type"] = GlosaType.LINEAR.value
        else:
            # Use category (administrative/technical) as primary type
            if category == "administrative":
                classified["glosa_type"] = GlosaType.ADMINISTRATIVE.value
            else:
                classified["glosa_type"] = GlosaType.TECHNICAL.value

        # Add secondary classification for extent
        classified["glosa_extent"] = extent
        classified["denial_ratio"] = float(
            denied_amount / original_amount if original_amount > 0 else 0
        )

        return classified
