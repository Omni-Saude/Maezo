"""
NegotiatePaymentWorker - Negotiate payment plans respecting CDC compliance requirements.

Business Rule: RN-COL-007.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 (fair collection practices), Art. 71 (contact restrictions)
Migrated from: com.hospital.revenuecycle.delegates.collection.NegotiatePaymentDelegate

This worker handles payment plan negotiation with patients/responsible parties,
including capacity assessment, term calculation, and plan creation.

Topic: negotiate-payment
BPMN Task: Task_Negotiate_Payment (Negociar Plano de Pagamento)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class CdcOverpaymentError(BpmnErrorException):
    """Raised when payment plan total exceeds debt owed (CDC Art. 42 violation)."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="CDC_OVERPAYMENT_VIOLATION",
            message=message,
            details=details,
        )


@worker(topic="negotiate-payment", max_jobs=8, lock_duration=30000)
class NegotiatePaymentWorker(BaseWorker):
    """
    Zeebe worker for negotiating payment plans with debtors.

    BPMN Task: Task_Negotiate_Payment
    Topic: negotiate-payment

    This worker:
    - Validates patient payment capacity
    - Calculates flexible payment plan terms
    - Creates installment schedules
    - Documents negotiation outcome
    - Handles plan acceptance/rejection

    Input Variables:
        - claimId: Claim identifier (required)
        - patientId: Patient identifier
        - debtAmount: Outstanding debt amount (Decimal)
        - collectionStatus: Current collection status
        - previousPaymentPlans: History of payment plans (optional)
        - maxPaymentPerMonth: Maximum patient can pay (optional)
        - patientIncome: Patient monthly income (optional)

    Output Variables:
        - paymentPlanId: Unique identifier
        - paymentPlanAccepted: Whether plan was accepted
        - monthlyPayment: Monthly installment amount
        - planStartDate: When payments begin
        - planEndDate: When plan completes
        - totalMonths: Duration in months
        - negotiationNotes: Details of negotiation
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "negotiate_payment"

    def _validate_cdc_art_42(
        self,
        amount_to_collect: Decimal,
        amount_owed: Decimal,
    ) -> None:
        """
        Validate CDC Art. 42 - Cannot charge more than owed.

        CDC Lei 8.078/90, Art. 42:
        "Na cobrança de débitos, o consumidor inadimplente não será
        exposto a ridículo, nem será submetido a qualquer tipo de
        constrangimento ou ameaça."

        Art. 42 § único: O consumidor cobrado em quantia indevida tem
        direito à repetição do indébito, por valor igual ao dobro do que
        pagou em excesso, acrescido de correção monetária e juros legais.

        Translation: If overpayment occurs, consumer is entitled to
        double the amount plus interest.

        Args:
            amount_to_collect: Total amount payment plan will collect
            amount_owed: Actual amount owed by consumer

        Raises:
            CdcOverpaymentError: If payment plan total exceeds debt owed
        """
        # Round to 2 decimal places for comparison (currency precision)
        # This avoids false positives from Decimal division precision artifacts
        collect_rounded = amount_to_collect.quantize(Decimal("0.01"))
        owed_rounded = amount_owed.quantize(Decimal("0.01"))
        if collect_rounded > owed_rounded:
            self._logger.error(
                "CDC Art. 42 violation detected - payment plan exceeds debt",
                amount_to_collect=str(amount_to_collect),
                amount_owed=str(amount_owed),
                excess=str(amount_to_collect - amount_owed),
            )
            raise CdcOverpaymentError(
                f"CDC Art. 42 violation: Payment plan total R${amount_to_collect} "
                f"exceeds debt owed R${amount_owed}. Excess: R${amount_to_collect - amount_owed}. "
                f"AVISO LEGAL: Cobrança indevida sujeita à devolução em dobro (CDC Art. 42 § único).",
                details={
                    "plan_total": str(amount_to_collect),
                    "amount_owed": str(amount_owed),
                    "excess_amount": str(amount_to_collect - amount_owed),
                    "legal_reference": "CDC Lei 8.078/90, Art. 42",
                    "penalty": "Devolução em dobro + correção monetária + juros legais",
                },
            )

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the payment plan negotiation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with payment plan details
        """
        self._logger.info(
            "Processing payment plan negotiation",
            claim_id=variables.get("claimId"),
            debt_amount=variables.get("debtAmount"),
        )

        try:
            claim_id = variables.get("claimId")
            patient_id = variables.get("patientId", "")
            debt_amount = Decimal(str(variables.get("debtAmount", 0)))
            collection_status = variables.get("collectionStatus", "IN_PROGRESS")
            max_payment_per_month = variables.get("maxPaymentPerMonth")
            patient_income = variables.get("patientIncome")

            # Validate inputs
            if debt_amount <= 0:
                return WorkerResult.failure(
                    error_message="Debt amount must be positive",
                    retry=False,
                )

            # Generate payment plan ID
            payment_plan_id = f"PP-{claim_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Calculate payment plan terms
            plan_terms = self._calculate_payment_plan_terms(
                debt_amount=debt_amount,
                max_payment_per_month=max_payment_per_month,
                patient_income=patient_income,
            )

            # Validate CDC Art. 42 compliance if plan terms exist
            if plan_terms is not None:
                total_plan_amount = plan_terms["monthly_payment"] * plan_terms["total_months"]
                self._validate_cdc_art_42(
                    amount_to_collect=total_plan_amount,
                    amount_owed=debt_amount,
                )

            if plan_terms is None:
                self._logger.warning(
                    "Unable to calculate feasible payment plan",
                    claim_id=claim_id,
                    debt_amount=float(debt_amount),
                )
                return WorkerResult.ok(
                    {
                        "paymentPlanId": payment_plan_id,
                        "paymentPlanAccepted": False,
                        "negotiationNotes": "No feasible payment plan could be calculated",
                        "debtAmount": float(debt_amount),
                    }
                )

            # Extract plan details
            total_months = plan_terms["total_months"]
            monthly_payment = plan_terms["monthly_payment"]

            # Calculate plan dates
            plan_start_date = datetime.utcnow()
            plan_end_date = plan_start_date + timedelta(days=30 * total_months)

            # Create installment schedule
            installment_schedule = self._create_installment_schedule(
                monthly_payment=monthly_payment,
                total_months=total_months,
                start_date=plan_start_date,
                debt_amount=debt_amount,
            )

            output = {
                "paymentPlanId": payment_plan_id,
                "paymentPlanAccepted": True,
                "monthlyPayment": float(monthly_payment),
                "planStartDate": plan_start_date.isoformat(),
                "planEndDate": plan_end_date.isoformat(),
                "totalMonths": total_months,
                "installmentSchedule": installment_schedule,
                "debtAmount": float(debt_amount),
                "collectionStatus": collection_status,
                "negotiationNotes": f"Payment plan negotiated: {total_months} months at {float(monthly_payment):.2f} per month",
            }

            self._logger.info(
                "Payment plan negotiated",
                claim_id=claim_id,
                payment_plan_id=payment_plan_id,
                monthly_payment=float(monthly_payment),
                total_months=total_months,
            )

            return WorkerResult.ok(output)

        except CdcOverpaymentError as e:
            self._logger.error("CDC Art. 42 violation - payment plan overpayment", error=str(e))
            return WorkerResult.bpmn_error(
                error_code="CDC_OVERPAYMENT_VIOLATION",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Error negotiating payment plan",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Payment negotiation failed: {e}",
                retry=True,
            )

    def _calculate_payment_plan_terms(
        self,
        debt_amount: Decimal,
        max_payment_per_month: Optional[float] = None,
        patient_income: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Calculate payment plan terms based on debt and capacity.

        Args:
            debt_amount: Total debt amount
            max_payment_per_month: Maximum patient can pay monthly
            patient_income: Patient monthly income

        Returns:
            Dict with total_months and monthly_payment, or None if no feasible plan
        """
        # Standard payment plan options in order of smallest to largest (best for debtors)
        # Try 3, 6, 12, 18 months - use the shortest plan that fits within constraints
        plan_options = [
            (3, debt_amount / 3),
            (6, debt_amount / 6),
            (12, debt_amount / 12),
            (18, debt_amount / 18),
        ]

        # If max payment is specified, find the longest plan that fits
        if max_payment_per_month is not None:
            max_payment = Decimal(str(max_payment_per_month))
            # Find longest plan that fits (lowest monthly payment)
            selected_plan = None
            for months, monthly_payment in plan_options:
                if monthly_payment <= max_payment:
                    selected_plan = (months, monthly_payment)

            if selected_plan:
                return {
                    "total_months": selected_plan[0],
                    "monthly_payment": selected_plan[1],
                }
            # No plan fits within max payment
            return None

        # If income is specified, use capacity-based approach
        if patient_income is not None:
            patient_income = Decimal(str(patient_income))
            # CDC allows up to 10% of monthly income for debt payment
            max_from_income = patient_income * Decimal("0.10")

            # Find longest plan that fits within income capacity
            selected_plan = None
            for months, monthly_payment in plan_options:
                if monthly_payment <= max_from_income:
                    selected_plan = (months, monthly_payment)

            if selected_plan:
                return {
                    "total_months": selected_plan[0],
                    "monthly_payment": selected_plan[1],
                }
            # Use longest plan (18 months) if no smaller plan fits
            return {
                "total_months": 18,
                "monthly_payment": debt_amount / 18,
            }

        # Default: 12-month plan
        return {
            "total_months": 12,
            "monthly_payment": debt_amount / 12,
        }

    def _create_installment_schedule(
        self,
        monthly_payment: Decimal,
        total_months: int,
        start_date: datetime,
        debt_amount: Decimal,
    ) -> list[dict[str, Any]]:
        """
        Create installment payment schedule.

        Args:
            monthly_payment: Monthly payment amount
            total_months: Total number of months
            start_date: When first payment is due
            debt_amount: Total debt (for proration of last payment)

        Returns:
            List of installment details
        """
        schedule = []
        current_date = start_date
        remaining_balance = debt_amount

        for installment_num in range(1, total_months + 1):
            # Last payment may be adjusted for rounding
            if installment_num == total_months:
                payment = remaining_balance
            else:
                payment = monthly_payment
                remaining_balance -= payment

            schedule.append(
                {
                    "installmentNumber": installment_num,
                    "dueDate": current_date.isoformat(),
                    "amount": float(payment),
                    "status": "PENDING",
                }
            )
            current_date += timedelta(days=30)

        return schedule
