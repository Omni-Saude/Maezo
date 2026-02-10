"""Brazilian late fee calculator per Lei 10.406/2002 (Código Civil).

Rules:
- Juros de mora: 1% per month (pro rata die)
- Multa: up to 2% of principal
- Correção monetária: INPC index (fetched externally)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

# Brazilian default rates
DEFAULT_MONTHLY_INTEREST_RATE = Decimal("0.01")  # 1% per month
DEFAULT_PENALTY_RATE = Decimal("0.02")  # 2% multa


@dataclass(frozen=True, slots=True)
class PenaltyBreakdown:
    """Breakdown of late fees applied to an overdue amount."""
    principal: Money
    interest: Money
    penalty: Money
    monetary_correction: Money
    total: Money
    days_overdue: int
    daily_rate: Decimal
    calculation_date: date


def calculate_penalty(
    principal: Money,
    due_date: date,
    calculation_date: date | None = None,
    monthly_interest_rate: Decimal = DEFAULT_MONTHLY_INTEREST_RATE,
    penalty_rate: Decimal = DEFAULT_PENALTY_RATE,
    inpc_factor: Decimal = Decimal("1.0"),
) -> PenaltyBreakdown:
    """Calculate late fees per Brazilian law.

    Args:
        principal: Original overdue amount (BRL).
        due_date: Original due date.
        calculation_date: Date of calculation (defaults to today).
        monthly_interest_rate: Monthly interest rate (default 1%).
        penalty_rate: One-time penalty rate (default 2%).
        inpc_factor: INPC monetary correction factor (default 1.0 = no correction).

    Returns:
        PenaltyBreakdown with all components.
    """
    if calculation_date is None:
        calculation_date = date.today()

    days_overdue = max(0, (calculation_date - due_date).days)

    if days_overdue == 0:
        zero = Money.zero()
        return PenaltyBreakdown(
            principal=principal,
            interest=zero,
            penalty=zero,
            monetary_correction=zero,
            total=principal,
            days_overdue=0,
            daily_rate=Decimal("0"),
            calculation_date=calculation_date,
        )

    # Daily interest rate (pro rata die)
    daily_rate = (monthly_interest_rate / Decimal("30")).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )

    # Interest = principal * daily_rate * days
    interest_amount = (
        principal.amount * daily_rate * Decimal(str(days_overdue))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Penalty (multa) = principal * penalty_rate (one-time)
    penalty_amount = (principal.amount * penalty_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Monetary correction (INPC)
    correction_amount = (
        principal.amount * (inpc_factor - Decimal("1.0"))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    interest_money = Money.brl(interest_amount)
    penalty_money = Money.brl(penalty_amount)
    correction_money = Money.brl(max(correction_amount, Decimal("0.00")))

    total = principal + interest_money + penalty_money + correction_money

    logger.info(
        "penalty_calculated",
        days_overdue=days_overdue,
        daily_rate=str(daily_rate),
    )

    return PenaltyBreakdown(
        principal=principal,
        interest=interest_money,
        penalty=penalty_money,
        monetary_correction=correction_money,
        total=total,
        days_overdue=days_overdue,
        daily_rate=daily_rate,
        calculation_date=calculation_date,
    )
