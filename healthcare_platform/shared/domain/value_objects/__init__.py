"""Immutable value objects for Healthcare domain (Brazilian healthcare specifics)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from healthcare_platform.shared.i18n import _


class Money(BaseModel, frozen=True):
    """Monetary value with BRL currency support."""

    amount: Decimal = Field(..., decimal_places=2, description="Value in currency")
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(_("Não é possível somar {} e {}").format(self.currency, other.currency))
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(_("Não é possível subtrair {} e {}").format(self.currency, other.currency))
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: Decimal | int | float) -> Money:
        return Money(amount=self.amount * Decimal(str(factor)), currency=self.currency)

    @classmethod
    def zero(cls, currency: str = "BRL") -> Money:
        return cls(amount=Decimal("0.00"), currency=currency)

    @classmethod
    def brl(cls, amount: Decimal | str | float) -> Money:
        return cls(amount=Decimal(str(amount)), currency="BRL")


class CPF(BaseModel, frozen=True):
    """Brazilian individual taxpayer registry (CPF) - LGPD: store hashed only."""

    hash_value: str = Field(..., description="SHA-256 hash of CPF (LGPD: no raw PII)")

    @field_validator("hash_value")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        if not re.match(r"^[a-f0-9]{64}$", v):
            raise ValueError(_("Hash do CPF deve ser um digest SHA-256 hexadecimal válido"))
        return v

    @classmethod
    def from_raw(cls, raw_cpf: str) -> CPF:
        """Create from raw CPF string (validates and hashes immediately)."""
        import hashlib
        digits = re.sub(r"\D", "", raw_cpf)
        if len(digits) != 11:
            raise ValueError(_("CPF deve ter exatamente 11 dígitos"))
        if digits == digits[0] * 11:
            raise ValueError(_("CPF inválido: todos os dígitos são iguais"))
        # Validate check digits
        for i in range(9, 11):
            total = sum(int(digits[j]) * ((i + 1) - j) for j in range(i))
            remainder = total % 11
            digit = 0 if remainder < 2 else 11 - remainder
            if int(digits[i]) != digit:
                raise ValueError(_("Dígitos verificadores do CPF inválidos"))
        return cls(hash_value=hashlib.sha256(digits.encode()).hexdigest())


class CNS(BaseModel, frozen=True):
    """Cartão Nacional de Saúde (SUS card number) - LGPD: store hashed only."""

    hash_value: str = Field(..., description="SHA-256 hash of CNS (LGPD: no raw PII)")

    @field_validator("hash_value")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        if not re.match(r"^[a-f0-9]{64}$", v):
            raise ValueError(_("Hash do CNS deve ser um digest SHA-256 hexadecimal válido"))
        return v

    @classmethod
    def from_raw(cls, raw_cns: str) -> CNS:
        """Create from raw CNS string (validates and hashes immediately)."""
        import hashlib
        digits = re.sub(r"\D", "", raw_cns)
        if len(digits) != 15:
            raise ValueError(_("CNS deve ter exatamente 15 dígitos"))
        return cls(hash_value=hashlib.sha256(digits.encode()).hexdigest())


class InsuranceCard(BaseModel, frozen=True):
    """Insurance card / carteirinha do convênio."""

    card_number: str = Field(..., min_length=1, max_length=20)
    operator_code: str = Field(..., description="ANS registry number of operator")
    plan_code: str = Field(default="", description="Plan identifier")
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError(_("valid_from deve ser anterior a valid_until"))
        return self


class CodedValue(BaseModel, frozen=True):
    """FHIR CodeableConcept equivalent - a coded value from a terminology."""

    system: str = Field(..., description="Terminology system URI")
    code: str = Field(..., min_length=1)
    display: str = Field(default="", description="Human-readable display")
    version: str | None = None

    @classmethod
    def tuss(cls, code: str, display: str = "") -> CodedValue:
        """TUSS procedure code (Terminologia Unificada da Saúde Suplementar)."""
        return cls(system="http://www.ans.gov.br/tuss", code=code, display=display)

    @classmethod
    def cid10(cls, code: str, display: str = "") -> CodedValue:
        """CID-10 (ICD-10) diagnosis code."""
        return cls(system="http://hl7.org/fhir/sid/icd-10", code=code, display=display)

    @classmethod
    def cbhpm(cls, code: str, display: str = "") -> CodedValue:
        """CBHPM procedure code."""
        return cls(system="http://www.amb.org.br/cbhpm", code=code, display=display)

    @classmethod
    def sigtap(cls, code: str, display: str = "") -> CodedValue:
        """SIGTAP (SUS) procedure code."""
        return cls(system="http://sigtap.datasus.gov.br", code=code, display=display)


class FHIRReference(BaseModel, frozen=True):
    """FHIR Reference - pointer to another resource (LGPD: references only, no PII)."""

    reference: str = Field(..., description="Relative reference e.g. Patient/123")
    type: str | None = Field(default=None, description="Resource type")
    display: str | None = Field(default=None, description="Human-readable (no PII)")

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError(_("Referência FHIR deve estar no formato 'ResourceType/id'"))
        return v
