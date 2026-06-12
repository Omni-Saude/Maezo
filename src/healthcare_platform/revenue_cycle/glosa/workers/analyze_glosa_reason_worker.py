"""Worker to analyze glosa reasons and identify patterns."""
from __future__ import annotations

from collections import Counter
from typing import Any

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import GlosaReasonCode, GlosaType
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="analyze-glosa-reason", max_jobs=5, lock_duration=90000)
class AnalyzeGlosaReasonWorker(BaseWorker, GlosaWorkerMixin):
    """Analyze glosa reasons and identify systemic patterns.

        Archetype: FINANCIAL_CALCULATION
    """

    # Pattern detection thresholds
    PATTERN_THRESHOLD = 3  # Minimum occurrences to flag a pattern
    SYSTEMIC_THRESHOLD = 0.5  # 50% of glosas with same reason = systemic

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

    @property
    def operation_name(self) -> str:
        return _("Analisar Motivos de Glosas")

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """Analyze glosa reasons and identify patterns.

        Input variables:
            - classifiedGlosas: List of glosa dicts
            - claimId: Claim identifier for context

        Output variables:
            - analyzedGlosas: Enriched list with reason codes and descriptions
            - reasonDistribution: Dict mapping reason code to count
            - rootCausePatterns: List of identified patterns
            - systemicIssues: List of systemic issues in Portuguese
        """
        classified_glosas = variables.get("classifiedGlosas", [])
        claim_id = variables.get("claimId", "unknown")

        if not classified_glosas:
            return WorkerResult.bpmn_error(
                error_code="NO_GLOSAS",
                error_message=_("Nenhuma glosa para analisar")
            )

        try:
            # Map glosas to reason codes
            analyzed_glosas = self._map_to_reason_codes(classified_glosas)

            # Calculate reason distribution
            reason_distribution = self._calculate_reason_distribution(analyzed_glosas)

            # Identify root cause patterns
            root_cause_patterns = self._identify_root_cause_patterns(
                analyzed_glosas,
                reason_distribution
            )

            # Detect systemic issues
            systemic_issues = self._detect_systemic_issues(
                reason_distribution,
                len(analyzed_glosas)
            )

            self._logger.info(
                "Glosa reasons analyzed",
                claim_id=claim_id,
                glosa_count=len(analyzed_glosas),
                unique_reasons=len(reason_distribution),
                patterns_found=len(root_cause_patterns),
                systemic_issues=len(systemic_issues)
            )

            return WorkerResult.ok({
                "analyzedGlosas": analyzed_glosas,
                "reasonDistribution": reason_distribution,
                "rootCausePatterns": root_cause_patterns,
                "systemicIssues": systemic_issues
            })

        except GlosaException as e:
            self._logger.error("Glosa analysis error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )
        except Exception as e:
            self._logger.error("Unexpected error analyzing glosas", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=str(e),
                retry=True
            )

    def _map_to_reason_codes(self, glosas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map each glosa to a GlosaReasonCode and enrich with description."""
        analyzed = []

        for glosa in glosas:
            reason_code = self._infer_reason_code(glosa)
            enriched = {
                **glosa,
                "reason_code": reason_code,
                "reason_description": self._get_glosa_reason_display(reason_code)
            }
            analyzed.append(enriched)

        return analyzed

    def _infer_reason_code(self, glosa: dict[str, Any]) -> str:
        """Infer the appropriate GlosaReasonCode from glosa data."""
        # Check for explicit reason code first
        if "reason_code" in glosa:
            return glosa["reason_code"]

        # Infer from glosa type and description
        glosa_type = glosa.get("glosa_type", "")
        description = glosa.get("description", "").lower()

        # Authorization-related
        if "autorização" in description or "auth" in description:
            if "ausente" in description or "missing" in description:
                return GlosaReasonCode.MISSING_AUTH
            if "vencida" in description or "expired" in description:
                return GlosaReasonCode.EXPIRED_AUTH

        # Documentation-related
        if "documentação" in description or "documento" in description:
            return GlosaReasonCode.MISSING_DOCUMENTATION

        # Code-related
        if "código" in description or "code" in description:
            if "incompatível" in description:
                return GlosaReasonCode.INCOMPATIBLE_PROCEDURE
            return GlosaReasonCode.WRONG_CODE

        # Duplicate
        if "duplicad" in description or "duplicate" in description:
            return GlosaReasonCode.DUPLICATE_CHARGE

        # Quantity
        if "quantidade" in description or "quantity" in description:
            return GlosaReasonCode.EXCEEDS_QUANTITY

        # Coverage
        if "cobertura" in description or "covered" in description:
            return GlosaReasonCode.NOT_COVERED

        # Price
        if "preço" in description or "price" in description or "valor" in description:
            return GlosaReasonCode.PRICE_DIVERGENCE

        # TISS validation
        if "tiss" in description or "validação" in description:
            return GlosaReasonCode.TISS_VALIDATION

        # Default based on type
        if glosa_type == GlosaType.ADMINISTRATIVE:
            return GlosaReasonCode.MISSING_DOCUMENTATION
        elif glosa_type == GlosaType.TECHNICAL:
            return GlosaReasonCode.INCOMPATIBLE_PROCEDURE

        return GlosaReasonCode.MISSING_DOCUMENTATION

    def _calculate_reason_distribution(
        self,
        analyzed_glosas: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Calculate distribution of glosas by reason code."""
        reason_codes = [g["reason_code"] for g in analyzed_glosas]
        counter = Counter(reason_codes)
        return dict(counter)

    def _identify_root_cause_patterns(
        self,
        analyzed_glosas: list[dict[str, Any]],
        reason_distribution: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Identify root cause patterns from glosa reasons."""
        patterns = []

        # Check for repeated authorization issues
        auth_issues = sum(
            count for code, count in reason_distribution.items()
            if code in [GlosaReasonCode.MISSING_AUTH, GlosaReasonCode.EXPIRED_AUTH]
        )
        if auth_issues >= self.PATTERN_THRESHOLD:
            patterns.append({
                "pattern_type": "authorization_process",
                "description": "Múltiplas glosas relacionadas a autorização",
                "occurrences": auth_issues,
                "severity": "high" if auth_issues >= 5 else "medium"
            })

        # Check for documentation issues
        doc_count = reason_distribution.get(GlosaReasonCode.MISSING_DOCUMENTATION, 0)
        if doc_count >= self.PATTERN_THRESHOLD:
            patterns.append({
                "pattern_type": "documentation_gap",
                "description": "Documentação incompleta ou ausente",
                "occurrences": doc_count,
                "severity": "high" if doc_count >= 5 else "medium"
            })

        # Check for coding issues
        coding_issues = sum(
            count for code, count in reason_distribution.items()
            if code in [GlosaReasonCode.WRONG_CODE, GlosaReasonCode.INCOMPATIBLE_PROCEDURE]
        )
        if coding_issues >= self.PATTERN_THRESHOLD:
            patterns.append({
                "pattern_type": "coding_accuracy",
                "description": "Problemas de codificação de procedimentos",
                "occurrences": coding_issues,
                "severity": "medium"
            })

        # Check for duplicate charges
        dup_count = reason_distribution.get(GlosaReasonCode.DUPLICATE_CHARGE, 0)
        if dup_count >= self.PATTERN_THRESHOLD:
            patterns.append({
                "pattern_type": "billing_control",
                "description": "Cobranças duplicadas",
                "occurrences": dup_count,
                "severity": "critical"
            })

        return patterns

    def _detect_systemic_issues(
        self,
        reason_distribution: dict[str, int],
        total_glosas: int
    ) -> list[str]:
        """Detect systemic issues from reason distribution."""
        systemic_issues = []

        for reason_code, count in reason_distribution.items():
            percentage = count / total_glosas if total_glosas > 0 else 0

            if percentage >= self.SYSTEMIC_THRESHOLD:
                reason_name = self._get_glosa_reason_display(reason_code)
                systemic_issues.append(
                    f"Problema sistêmico identificado: {reason_name} "
                    f"({count} de {total_glosas} glosas = {percentage*100:.1f}%)"
                )

        return systemic_issues
