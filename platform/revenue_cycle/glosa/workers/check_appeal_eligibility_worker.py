"""
Check Appeal Eligibility Worker

Validates if analyzed glosas are eligible for appeal according to ANS RN 424/2017.
Checks appealability, deadlines, and documentation requirements.

Topic: check-appeal-eligibility
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from platform.revenue_cycle.billing.workers.base import WorkerResult, worker
from platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from platform.shared.domain.enums import GlosaType, GlosaReasonCode
from platform.shared.domain.exceptions import (
    GlosaAppealDeadlineExpired,
    GlosaException,
    GlosaNotAppealable,
)
from platform.shared.domain.value_objects import Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


# Non-appealable glosa types per ANS regulations
NON_APPEALABLE_TYPES = {GlosaType.TOTAL}

# Required documentation per glosa reason code
REQUIRED_DOCUMENTATION = {
    GlosaReasonCode.MISSING_SIGNATURE: ["medical_authorization", "signed_forms"],
    GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION: [
        "medical_report",
        "clinical_notes",
    ],
    GlosaReasonCode.INVALID_CODE: ["procedure_documentation", "code_justification"],
    GlosaReasonCode.DUPLICATE_BILLING: ["original_invoice", "procedure_log"],
    GlosaReasonCode.NOT_COVERED_PROCEDURE: [
        "contract_terms",
        "coverage_documentation",
    ],
    GlosaReasonCode.LACK_OF_PRIOR_AUTHORIZATION: [
        "authorization_request",
        "emergency_documentation",
    ],
}

# ANS RN 424/2017: Appeal deadline in days
APPEAL_DEADLINE_DAYS = 30


@worker(topic="check-appeal-eligibility", max_jobs=10, lock_duration=30000)
class CheckAppealEligibilityWorker(GlosaWorkerMixin):
    """
    Worker that checks if glosas are eligible for appeal.

    Validates:
    1. Glosa type is appealable (TOTAL glosas are not appealable)
    2. Within 30-day deadline per ANS RN 424/2017
    3. Required documentation is available

    Raises:
        GlosaAppealDeadlineExpired: If appeal deadline has passed
        GlosaNotAppealable: If glosa type is not appealable
    """

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Process appeal eligibility check.

        Args:
            job: Zeebe job instance
            variables: Task variables containing:
                - analyzedGlosas: List of analyzed glosa dicts
                - glosaDate: ISO date string when glosa was issued
                - claimId: Claim identifier
                - availableDocumentation (optional): List of available doc types

        Returns:
            WorkerResult with eligibility analysis

        Raises:
            GlosaAppealDeadlineExpired: If deadline expired
            GlosaNotAppealable: If glosas not appealable
        """
        claim_id = variables.get("claimId", "UNKNOWN")
        logger.info(
            _("Verificando elegibilidade de recurso para conta {claim_id}").format(
                claim_id=claim_id
            )
        )

        try:
            # Parse input
            analyzed_glosas = variables.get("analyzedGlosas", [])
            glosa_date_str = variables.get("glosaDate")
            available_docs = set(variables.get("availableDocumentation", []))

            if not analyzed_glosas:
                raise GlosaException(_("Nenhuma glosa encontrada para análise"))

            if not glosa_date_str:
                raise GlosaException(_("Data da glosa não informada"))

            # Parse glosa date
            glosa_date = datetime.fromisoformat(
                glosa_date_str.replace("Z", "+00:00")
            )
            if glosa_date.tzinfo is None:
                glosa_date = glosa_date.replace(tzinfo=timezone.utc)

            # Calculate deadline per ANS RN 424/2017
            appeal_deadline = glosa_date + timedelta(days=APPEAL_DEADLINE_DAYS)
            now = datetime.now(timezone.utc)
            days_remaining = (appeal_deadline - now).days

            # Check if deadline expired
            if days_remaining < 0:
                raise GlosaAppealDeadlineExpired(
                    _(
                        "Prazo de recurso expirado. Data da glosa: {glosa_date}, "
                        "Prazo final: {deadline} (ANS RN 424/2017)"
                    ).format(
                        glosa_date=glosa_date.isoformat(),
                        deadline=appeal_deadline.isoformat(),
                    )
                )

            # Analyze each glosa
            eligible_glosas = []
            ineligible_glosas = []
            total_eligible_amount = Money.brl(0)

            for glosa in analyzed_glosas:
                glosa_type_str = glosa.get("type")
                reason_code_str = glosa.get("reasonCode")
                amount_brl = self._parse_money(glosa.get("amountBRL", "0,00"))

                # Parse enums
                try:
                    glosa_type = GlosaType[glosa_type_str]
                except (KeyError, TypeError):
                    logger.warning(
                        _("Tipo de glosa inválido: {type}").format(type=glosa_type_str)
                    )
                    ineligible_glosas.append(
                        {
                            **glosa,
                            "ineligibilityReason": _("Tipo de glosa inválido"),
                        }
                    )
                    continue

                try:
                    reason_code = GlosaReasonCode[reason_code_str]
                except (KeyError, TypeError):
                    reason_code = None

                # Check if type is appealable
                if glosa_type in NON_APPEALABLE_TYPES:
                    ineligible_glosas.append(
                        {
                            **glosa,
                            "ineligibilityReason": _(
                                "Glosas do tipo {type} não são passíveis de recurso"
                            ).format(type=glosa_type.value),
                        }
                    )
                    continue

                # Check required documentation
                required_docs = REQUIRED_DOCUMENTATION.get(reason_code, [])
                missing_docs = [doc for doc in required_docs if doc not in available_docs]

                if missing_docs:
                    ineligible_glosas.append(
                        {
                            **glosa,
                            "ineligibilityReason": _(
                                "Documentação obrigatória ausente: {docs}"
                            ).format(docs=", ".join(missing_docs)),
                            "missingDocumentation": missing_docs,
                        }
                    )
                    continue

                # Glosa is eligible
                eligible_glosas.append(glosa)
                total_eligible_amount += amount_brl

            # If no eligible glosas, raise error
            if not eligible_glosas:
                reasons = [g.get("ineligibilityReason", "") for g in ineligible_glosas]
                raise GlosaNotAppealable(
                    _("Nenhuma glosa elegível para recurso. Motivos: {reasons}").format(
                        reasons="; ".join(reasons)
                    )
                )

            # Success
            logger.info(
                _(
                    "Recurso elegível: {eligible}/{total} glosas, "
                    "valor total R$ {amount}, {days} dias restantes"
                ).format(
                    eligible=len(eligible_glosas),
                    total=len(analyzed_glosas),
                    amount=total_eligible_amount.format_brl(),
                    days=days_remaining,
                )
            )

            return WorkerResult(
                variables={
                    "eligibleGlosas": eligible_glosas,
                    "ineligibleGlosas": ineligible_glosas,
                    "appealDeadline": appeal_deadline.isoformat(),
                    "daysRemaining": days_remaining,
                    "totalEligibleAmount": total_eligible_amount.format_brl(),
                    "appealEligible": True,
                },
                success=True,
            )

        except (GlosaAppealDeadlineExpired, GlosaNotAppealable) as e:
            logger.warning(_("Glosa não elegível para recurso: {error}").format(error=str(e)))
            raise

        except Exception as e:
            logger.error(
                _("Erro ao verificar elegibilidade de recurso: {error}").format(error=str(e))
            )
            return WorkerResult(
                variables={
                    "eligibleGlosas": [],
                    "appealEligible": False,
                    "error": str(e),
                },
                success=False,
            )
