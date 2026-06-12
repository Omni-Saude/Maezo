"""
Update Payment After Glosa Worker.

Recalculates expected payment after glosa appeal outcome.
Determines payment adjustments and billing status updates.
"""

from decimal import Decimal
from typing import Any, Dict

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="update-payment-after-glosa", max_jobs=10, lock_duration=10000)
class UpdatePaymentWorker(BaseWorker, GlosaWorkerMixin):
    """
    Update payment calculations after glosa appeal outcome.

    Recalculates expected payment, determines adjustment type,
    and updates billing status based on recovery results.

        Archetype: FINANCIAL_CALCULATION
    """

    # Payment adjustment type thresholds
    FULL_RECOVERY_THRESHOLD = Decimal("0.95")  # 95% recovered
    WRITE_OFF_THRESHOLD = Decimal("0.10")  # Less than 10% recovered

    def __init__(self) -> None:
        """Initialize worker."""
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

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Update payment after glosa appeal outcome.

        Args:
            job: Zeebe job instance
            variables: Input variables containing:
                - claimId: Claim identifier
                - appealStatus: Appeal outcome status
                - originalAmount: Original claim amount (BRL)
                - deniedAmount: Total denied amount (BRL)
                - recoveredAmount: Amount recovered from appeal (BRL)
                - glosaItems: List of glosa items

        Returns:
            WorkerResult with updated payment details
        """
        try:
            claim_id = variables.get("claimId")
            appeal_status = variables.get("appealStatus")
            original_amount = self._parse_money(variables.get("originalAmount", "0"))
            denied_amount = self._parse_money(variables.get("deniedAmount", "0"))
            recovered_amount = self._parse_money(variables.get("recoveredAmount", "0"))
            # TODO: glosa_items sera usado na atualizacao detalhada dos itens glosados
            # glosa_items = variables.get("glosaItems", [])

            logger.info(
                "Updating payment after glosa",
                extra={
                    "claim_id": claim_id,
                    "appeal_status": appeal_status,
                    "original_amount": str(original_amount),
                    "denied_amount": str(denied_amount),
                    "recovered_amount": str(recovered_amount),
                }
            )

            # Validate inputs
            if not claim_id:
                raise GlosaException(_("ID da conta é obrigatório"))

            if original_amount <= Decimal("0"):
                raise GlosaException(_("Valor original deve ser maior que zero"))

            # Calculate adjusted payment
            adjusted_payment = self._calculate_adjusted_payment(
                original_amount=original_amount,
                denied_amount=denied_amount,
                recovered_amount=recovered_amount,
            )

            # Determine adjustment type
            adjustment_type = self._determine_adjustment_type(
                denied_amount=denied_amount,
                recovered_amount=recovered_amount,
            )

            # Determine new billing status
            new_billing_status = self._determine_billing_status(
                adjustment_type=adjustment_type,
                adjusted_payment=adjusted_payment,
            )

            # Calculate write-off amount if applicable
            write_off_amount = self._calculate_write_off(
                adjustment_type=adjustment_type,
                denied_amount=denied_amount,
                recovered_amount=recovered_amount,
            )

            # Generate financial summary
            financial_summary = self._generate_financial_summary(
                original_amount=original_amount,
                denied_amount=denied_amount,
                recovered_amount=recovered_amount,
                adjusted_payment=adjusted_payment,
                adjustment_type=adjustment_type,
                write_off_amount=write_off_amount,
            )

            output_vars = {
                "adjustedPaymentBRL": str(adjusted_payment),
                "paymentAdjustmentType": adjustment_type,
                "newBillingStatus": new_billing_status,
                "financialSummary": financial_summary,
                "writeOffAmount": str(write_off_amount),
            }

            logger.info(
                "Payment updated after glosa",
                extra={
                    "claim_id": claim_id,
                    "adjusted_payment": str(adjusted_payment),
                    "adjustment_type": adjustment_type,
                    "new_status": new_billing_status,
                }
            )

            return WorkerResult.success(output_vars)

        except GlosaException as e:
            logger.error("Glosa exception during payment update", exc_info=e)
            return WorkerResult.failure(error_message=str(e))
        except Exception as e:
            logger.error("Unexpected error updating payment", exc_info=e)
            return WorkerResult.failure(
                error_message=_("Erro ao atualizar pagamento: {}").format(str(e))
            )

    def _calculate_adjusted_payment(
        self,
        original_amount: Decimal,
        denied_amount: Decimal,
        recovered_amount: Decimal,
    ) -> Decimal:
        """
        Calculate new expected payment amount.

        Formula: original - denied + recovered

        Args:
            original_amount: Original claim amount
            denied_amount: Total denied amount
            recovered_amount: Amount recovered from appeal

        Returns:
            Adjusted payment amount
        """
        adjusted = original_amount - denied_amount + recovered_amount
        return max(adjusted, Decimal("0"))

    def _determine_adjustment_type(
        self,
        denied_amount: Decimal,
        recovered_amount: Decimal,
    ) -> str:
        """
        Determine payment adjustment type based on recovery rate.

        Args:
            denied_amount: Total denied amount
            recovered_amount: Amount recovered

        Returns:
            Adjustment type: FULL_RECOVERY, PARTIAL_RECOVERY, NO_RECOVERY, WRITE_OFF
        """
        if denied_amount <= Decimal("0"):
            return "NO_ADJUSTMENT"

        recovery_rate = recovered_amount / denied_amount

        if recovery_rate >= self.FULL_RECOVERY_THRESHOLD:
            return "FULL_RECOVERY"
        elif recovery_rate >= self.WRITE_OFF_THRESHOLD:
            return "PARTIAL_RECOVERY"
        elif recovery_rate > Decimal("0"):
            return "MINIMAL_RECOVERY"
        else:
            return "WRITE_OFF"

    def _determine_billing_status(
        self,
        adjustment_type: str,
        adjusted_payment: Decimal,
    ) -> str:
        """
        Determine new billing status based on adjustment.

        Args:
            adjustment_type: Type of payment adjustment
            adjusted_payment: Adjusted payment amount

        Returns:
            New billing status
        """
        if adjustment_type == "FULL_RECOVERY":
            return "PAYMENT_EXPECTED"
        elif adjustment_type in ["PARTIAL_RECOVERY", "MINIMAL_RECOVERY"]:
            return "PARTIAL_PAYMENT_EXPECTED"
        elif adjustment_type == "WRITE_OFF" or adjusted_payment <= Decimal("0"):
            return "WRITTEN_OFF"
        else:
            return "PAYMENT_EXPECTED"

    def _calculate_write_off(
        self,
        adjustment_type: str,
        denied_amount: Decimal,
        recovered_amount: Decimal,
    ) -> Decimal:
        """
        Calculate write-off amount if applicable.

        Args:
            adjustment_type: Type of adjustment
            denied_amount: Total denied amount
            recovered_amount: Amount recovered

        Returns:
            Amount to write off
        """
        if adjustment_type in ["WRITE_OFF", "PARTIAL_RECOVERY", "MINIMAL_RECOVERY"]:
            return max(denied_amount - recovered_amount, Decimal("0"))
        return Decimal("0")

    def _generate_financial_summary(
        self,
        original_amount: Decimal,
        denied_amount: Decimal,
        recovered_amount: Decimal,
        adjusted_payment: Decimal,
        adjustment_type: str,
        write_off_amount: Decimal,
    ) -> str:
        """
        Generate financial summary text in Portuguese.

        Args:
            original_amount: Original amount
            denied_amount: Denied amount
            recovered_amount: Recovered amount
            adjusted_payment: Final adjusted payment
            adjustment_type: Type of adjustment
            write_off_amount: Write-off amount

        Returns:
            Financial summary text
        """
        summary_lines = [
            _("Resumo Financeiro - Recurso de Glosa:"),
            _("Valor Original: R$ {}").format(original_amount),
            _("Valor Glosado: R$ {}").format(denied_amount),
            _("Valor Recuperado: R$ {}").format(recovered_amount),
            _("Pagamento Ajustado: R$ {}").format(adjusted_payment),
        ]

        if write_off_amount > Decimal("0"):
            summary_lines.append(_("Valor Baixado: R$ {}").format(write_off_amount))

        adjustment_labels = {
            "FULL_RECOVERY": _("Recuperação Total"),
            "PARTIAL_RECOVERY": _("Recuperação Parcial"),
            "MINIMAL_RECOVERY": _("Recuperação Mínima"),
            "WRITE_OFF": _("Baixa Contábil"),
            "NO_ADJUSTMENT": _("Sem Ajuste"),
        }

        summary_lines.append(
            _("Tipo de Ajuste: {}").format(adjustment_labels.get(adjustment_type, adjustment_type))
        )

        return "\n".join(summary_lines)
