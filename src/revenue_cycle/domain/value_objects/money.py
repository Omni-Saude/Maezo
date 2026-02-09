"""
Money value object for handling monetary values.

Implements proper decimal handling for financial calculations
following best practices for currency representation.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Union

from pydantic import BaseModel, field_validator, model_validator


class Money(BaseModel):
    """
    Immutable value object representing monetary amounts.

    Uses Decimal for precise financial calculations, avoiding
    floating-point precision issues.

    Attributes:
        amount: The monetary amount as Decimal
        currency: ISO 4217 currency code (default: BRL)

    Example:
        >>> money = Money(amount=Decimal("100.50"), currency="BRL")
        >>> money2 = Money.from_float(100.50)
        >>> total = money + money2
        >>> print(total.formatted)
        'R$ 201,00'
    """

    amount: Decimal
    currency: str = "BRL"

    model_config = {
        "frozen": True,  # Immutable
        "json_schema_extra": {
            "examples": [
                {"amount": "1500.00", "currency": "BRL"},
                {"amount": "250.50", "currency": "USD"},
            ]
        }
    }

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v: Any) -> Decimal:
        """Parse amount from various input types."""
        if v is None:
            raise ValueError("Amount cannot be None")

        if isinstance(v, Decimal):
            return v

        if isinstance(v, (int, float)):
            return Decimal(str(v))

        if isinstance(v, str):
            # Handle Brazilian format (1.234,56)
            v = v.strip()
            if "," in v and "." in v:
                # Brazilian format: 1.234,56
                v = v.replace(".", "").replace(",", ".")
            elif "," in v:
                # Only comma: 1234,56
                v = v.replace(",", ".")

            try:
                return Decimal(v)
            except InvalidOperation as e:
                raise ValueError(f"Invalid amount format: {v}") from e

        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code."""
        v = v.upper().strip()
        if len(v) != 3:
            raise ValueError("Currency must be a 3-letter ISO 4217 code")
        return v

    @model_validator(mode="after")
    def round_amount(self) -> "Money":
        """Round amount to 2 decimal places."""
        # Since model is frozen, we need to use object.__setattr__
        rounded = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", rounded)
        return self

    @classmethod
    def from_float(cls, value: float, currency: str = "BRL") -> "Money":
        """
        Create Money from float value.

        Args:
            value: Float amount
            currency: Currency code (default: BRL)

        Returns:
            Money instance
        """
        return cls(amount=Decimal(str(value)), currency=currency)

    @classmethod
    def from_cents(cls, cents: int, currency: str = "BRL") -> "Money":
        """
        Create Money from cents (integer).

        Args:
            cents: Amount in cents (e.g., 1050 = R$ 10.50)
            currency: Currency code (default: BRL)

        Returns:
            Money instance
        """
        return cls(amount=Decimal(cents) / Decimal(100), currency=currency)

    @classmethod
    def zero(cls, currency: str = "BRL") -> "Money":
        """
        Create zero Money instance.

        Args:
            currency: Currency code (default: BRL)

        Returns:
            Money instance with zero amount
        """
        return cls(amount=Decimal("0.00"), currency=currency)

    def __add__(self, other: "Money") -> "Money":
        """Add two Money instances."""
        self._check_currency_compatibility(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: "Money") -> "Money":
        """Subtract two Money instances."""
        self._check_currency_compatibility(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, multiplier: Union[int, float, Decimal]) -> "Money":
        """Multiply Money by a scalar."""
        if isinstance(multiplier, (int, float)):
            multiplier = Decimal(str(multiplier))
        return Money(amount=self.amount * multiplier, currency=self.currency)

    def __rmul__(self, multiplier: Union[int, float, Decimal]) -> "Money":
        """Right multiply Money by a scalar."""
        return self.__mul__(multiplier)

    def __truediv__(self, divisor: Union[int, float, Decimal]) -> "Money":
        """Divide Money by a scalar."""
        if isinstance(divisor, (int, float)):
            divisor = Decimal(str(divisor))
        if divisor == 0:
            raise ZeroDivisionError("Cannot divide Money by zero")
        return Money(amount=self.amount / divisor, currency=self.currency)

    def __neg__(self) -> "Money":
        """Negate Money amount."""
        return Money(amount=-self.amount, currency=self.currency)

    def __abs__(self) -> "Money":
        """Get absolute value of Money."""
        return Money(amount=abs(self.amount), currency=self.currency)

    def __lt__(self, other: "Money") -> bool:
        """Less than comparison."""
        self._check_currency_compatibility(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        """Less than or equal comparison."""
        self._check_currency_compatibility(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        """Greater than comparison."""
        self._check_currency_compatibility(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        """Greater than or equal comparison."""
        self._check_currency_compatibility(other)
        return self.amount >= other.amount

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount == other.amount and self.currency == other.currency

    def __hash__(self) -> int:
        """Hash for use in sets and dicts."""
        return hash((self.amount, self.currency))

    def __str__(self) -> str:
        """String representation."""
        return f"{self.currency} {self.amount:,.2f}"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"Money(amount={self.amount!r}, currency={self.currency!r})"

    def _check_currency_compatibility(self, other: "Money") -> None:
        """Check that currencies match for arithmetic operations."""
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot perform operation with different currencies: "
                f"{self.currency} and {other.currency}"
            )

    @property
    def is_positive(self) -> bool:
        """Check if amount is positive."""
        return self.amount > 0

    @property
    def is_negative(self) -> bool:
        """Check if amount is negative."""
        return self.amount < 0

    @property
    def is_zero(self) -> bool:
        """Check if amount is zero."""
        return self.amount == 0

    @property
    def cents(self) -> int:
        """Get amount in cents (integer)."""
        return int(self.amount * 100)

    @property
    def formatted(self) -> str:
        """
        Get formatted string for display.

        Returns:
            Formatted string (e.g., "R$ 1.234,56" for BRL)
        """
        if self.currency == "BRL":
            # Brazilian format: R$ 1.234,56
            integer_part = int(self.amount)
            decimal_part = abs(int((self.amount % 1) * 100))

            # Format with thousand separators
            formatted_int = f"{integer_part:,}".replace(",", ".")
            return f"R$ {formatted_int},{decimal_part:02d}"
        elif self.currency == "USD":
            return f"$ {self.amount:,.2f}"
        else:
            return f"{self.currency} {self.amount:,.2f}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "amount": str(self.amount),
            "currency": self.currency,
        }

    def allocate(self, ratios: list[int]) -> list["Money"]:
        """
        Allocate money according to ratios (e.g., for splitting payments).

        Uses the "largest remainder" algorithm to ensure the total
        exactly matches the original amount.

        Args:
            ratios: List of integer ratios (e.g., [1, 2, 3] for 1:2:3 split)

        Returns:
            List of Money instances

        Example:
            >>> Money.from_float(100.00).allocate([1, 1, 1])
            [Money(33.34), Money(33.33), Money(33.33)]
        """
        if not ratios or sum(ratios) == 0:
            raise ValueError("Ratios must be non-empty and sum to positive")

        total_ratio = sum(ratios)
        results: list[Money] = []
        remainder = self.amount

        for i, ratio in enumerate(ratios):
            if i == len(ratios) - 1:
                # Last allocation gets the remainder
                results.append(Money(amount=remainder, currency=self.currency))
            else:
                share = (self.amount * ratio / total_ratio).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                results.append(Money(amount=share, currency=self.currency))
                remainder -= share

        return results
