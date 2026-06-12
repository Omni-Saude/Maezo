"""
Base Worker Components for Glosa Management

Provides common utilities and mixins for glosa-related workers.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict

from healthcare_platform.revenue_cycle.billing.workers.base import (
    BaseWorker,
    WorkerResult,
    worker,
)
from healthcare_platform.shared.domain.enums import GlosaReasonCode
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _

__all__ = ["BaseWorker", "WorkerResult", "worker", "GlosaWorkerMixin"]


class GlosaWorkerMixin:
    """
    Mixin providing common utilities for glosa management workers.
    """

    # Portuguese descriptions for each glosa reason code
    REASON_DISPLAY: Dict[GlosaReasonCode, str] = {
        GlosaReasonCode.MISSING_AUTH: _("Autorização ausente ou inválida"),
        GlosaReasonCode.EXPIRED_AUTH: _("Autorização expirada"),
        GlosaReasonCode.DUPLICATE_CHARGE: _("Cobrança duplicada"),
        GlosaReasonCode.EXCEEDS_QUANTITY: _("Quantidade excede limite autorizado"),
        GlosaReasonCode.NOT_COVERED: _("Procedimento não coberto pelo plano"),
        GlosaReasonCode.WRONG_CODE: _("Código de procedimento incorreto"),
        GlosaReasonCode.MISSING_DOCUMENTATION: _("Documentação obrigatória ausente"),
        GlosaReasonCode.INCOMPATIBLE_PROCEDURE: _(
            "Procedimento incompatível com diagnóstico"
        ),
        GlosaReasonCode.PRICE_DIVERGENCE: _("Divergência no valor cobrado"),
        GlosaReasonCode.TISS_VALIDATION: _("Erro de validação TISS"),
    }

    def _parse_money(self, value) -> Money:
        """
        Parse a monetary value into a Money object with BRL currency.

        Args:
            value: Value to parse (str, int, float, Decimal, or Money)

        Returns:
            Money object in BRL currency
        """
        if isinstance(value, Money):
            return value

        if isinstance(value, str):
            # Remove currency symbols and normalize decimal separator
            value = value.replace("R$", "").replace(".", "").replace(",", ".").strip()

        return Money.brl(Decimal(str(value)))

    def _get_glosa_reason_display(self, code: GlosaReasonCode) -> str:
        """
        Get Portuguese description for a glosa reason code.

        Args:
            code: GlosaReasonCode enum value

        Returns:
            Portuguese description string
        """
        return self.REASON_DISPLAY.get(
            code, _("Motivo de glosa desconhecido: {code}").format(code=code.value)
        )

    def _calculate_deadline(self, glosa_date: datetime, days: int) -> datetime:
        """
        Calculate deadline date from glosa notification date.

        Args:
            glosa_date: Date the glosa was notified
            days: Number of business days for the deadline

        Returns:
            Deadline datetime
        """
        if not isinstance(glosa_date, datetime):
            raise ValueError(_("glosa_date deve ser um objeto datetime"))

        # Simple calculation - in production, should account for business days
        # and Brazilian holidays
        return glosa_date + timedelta(days=days)
