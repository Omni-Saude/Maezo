"""Worker to calculate financial impact of classified glosas."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import GlosaType
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="calculate-glosa-impact", max_jobs=5, lock_duration=60000)
class CalculateGlosaImpactWorker(BaseWorker, GlosaWorkerMixin):
    """Calculate total financial impact and recovery potential of glosas."""

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
        return _("Calcular Impacto Financeiro de Glosas")

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """Calculate glosa impact metrics.

        Input variables:
            - classifiedGlosas: List of glosa dicts with denied_amount, original_amount, glosa_type

        Output variables:
            - totalImpactBRL: Total denied amount as Decimal
            - impactByType: Dict mapping glosa type to denied amount
            - denialPercentage: Percentage of claim denied (0-100)
            - recoveryPotentialBRL: Expected recoverable amount
            - impactSummary: Portuguese summary text
        """
        classified_glosas = variables.get("classifiedGlosas", [])

        if not classified_glosas:
            return WorkerResult.bpmn_error(
                error_code="NO_GLOSAS",
                error_message=_("Nenhuma glosa classificada para calcular impacto")
            )

        try:
            # Calculate total impact
            total_impact = self._calculate_total_impact(classified_glosas)

            # Calculate impact by type
            impact_by_type = self._calculate_impact_by_type(classified_glosas)

            # Calculate denial percentage
            denial_percentage = self._calculate_denial_percentage(classified_glosas)

            # Calculate recovery potential
            recovery_potential = self._calculate_recovery_potential(classified_glosas)

            # Generate summary
            summary = self._generate_impact_summary(
                total_impact,
                impact_by_type,
                denial_percentage,
                recovery_potential,
                len(classified_glosas)
            )

            self._logger.info(
                "Glosa impact calculated",
                total_impact=float(total_impact),
                denial_percentage=denial_percentage,
                recovery_potential=float(recovery_potential),
                glosa_count=len(classified_glosas)
            )

            return WorkerResult.ok({
                "totalImpactBRL": total_impact,
                "impactByType": impact_by_type,
                "denialPercentage": denial_percentage,
                "recoveryPotentialBRL": recovery_potential,
                "impactSummary": summary
            })

        except GlosaException as e:
            self._logger.error("Glosa calculation error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )
        except Exception as e:
            self._logger.error("Unexpected error calculating glosa impact", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=str(e),
                retry=True
            )

    def _calculate_total_impact(self, glosas: list[dict[str, Any]]) -> Decimal:
        """Calculate total denied amount across all glosas."""
        total = Decimal("0.00")
        for glosa in glosas:
            denied_amount = self._parse_money(glosa.get("denied_amount", 0))
            total += denied_amount
        return total

    def _calculate_impact_by_type(self, glosas: list[dict[str, Any]]) -> dict[str, Decimal]:
        """Calculate denied amounts grouped by glosa type."""
        impact_by_type: dict[str, Decimal] = {}

        for glosa in glosas:
            glosa_type = glosa.get("glosa_type", GlosaType.PARTIAL)
            denied_amount = self._parse_money(glosa.get("denied_amount", 0))

            if glosa_type not in impact_by_type:
                impact_by_type[glosa_type] = Decimal("0.00")

            impact_by_type[glosa_type] += denied_amount

        return impact_by_type

    def _calculate_denial_percentage(self, glosas: list[dict[str, Any]]) -> float:
        """Calculate percentage of total claim that was denied."""
        total_original = Decimal("0.00")
        total_denied = Decimal("0.00")

        for glosa in glosas:
            original_amount = self._parse_money(glosa.get("original_amount", 0))
            denied_amount = self._parse_money(glosa.get("denied_amount", 0))

            total_original += original_amount
            total_denied += denied_amount

        if total_original == Decimal("0.00"):
            return 0.0

        percentage = (total_denied / total_original) * Decimal("100")
        return float(percentage)

    def _calculate_recovery_potential(self, glosas: list[dict[str, Any]]) -> Decimal:
        """Calculate expected recoverable amount based on glosa types."""
        recovery_potential = Decimal("0.00")

        for glosa in glosas:
            denied_amount = self._parse_money(glosa.get("denied_amount", 0))
            glosa_type = glosa.get("glosa_type", GlosaType.PARTIAL)

            recovery_rate = self._get_recovery_rate(glosa_type)
            recovery_potential += denied_amount * recovery_rate

        return recovery_potential

    def _generate_impact_summary(
        self,
        total_impact: Decimal,
        impact_by_type: dict[str, Decimal],
        denial_percentage: float,
        recovery_potential: Decimal,
        glosa_count: int
    ) -> str:
        """Generate Portuguese summary of glosa impact."""
        summary_lines = [
            f"Impacto total: R$ {total_impact:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"Total de glosas: {glosa_count}",
            f"Percentual negado: {denial_percentage:.1f}%",
            f"Potencial de recuperação: R$ {recovery_potential:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "",
            "Impacto por tipo:"
        ]

        for glosa_type, amount in sorted(impact_by_type.items(), key=lambda x: x[1], reverse=True):
            formatted = f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            summary_lines.append(f"  - {glosa_type}: {formatted}")

        return "\n".join(summary_lines)
