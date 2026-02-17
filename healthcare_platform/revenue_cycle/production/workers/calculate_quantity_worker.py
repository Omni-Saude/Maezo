"""Calculate billable quantities for clinical procedures.

CIB7 External Task Topic: production.calculate_quantity
BPMN Error Codes: CODING_ERROR
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

# Procedure-specific quantity rules
_DURATION_BASED_CODES: set[str] = {
    "20101012",  # Anesthesia - per 15min block
    "20201010",  # Ventilator support - per hour
    "31303072",  # ICU daily rate
}

_MAX_QUANTITY_MAP: dict[str, int] = {
    "40101010": 4,   # Office visit - max 4/day
    "40201010": 2,   # Specialist consult - max 2/day
    "20101012": 48,  # Anesthesia - max 12h (48 x 15min)
}


class CalculateQuantityWorker:
    """Calculates billable quantity for each procedure.

    Handles:
    - Simple quantity (1 per occurrence)
    - Duration-based (anesthesia, ICU, ventilator)
    - Frequency limits per procedure type
    - Multi-unit procedures

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "production.calculate_quantity"

    def __init__(self) -> None:
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    def _evaluate_pricing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate pricing DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='pricing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @require_tenant
    @track_task_execution(metric_name="production_calculate_quantity")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Calculate billable quantity for procedures.

        Task Variables (input):
            enriched_procedures: list[dict] - Procedures with clinical data
            encounter_start: str | None - Encounter start datetime (ISO)
            encounter_end: str | None - Encounter end datetime (ISO)

        Returns:
            quantified_procedures: list[dict] - Procedures with calculated quantities
            total_items: int - Total number of billable items
        """
        ctx = get_required_tenant()
        procedures: list[dict[str, Any]] = task_variables.get("enriched_procedures", [])
        encounter_start_str: str | None = task_variables.get("encounter_start")
        encounter_end_str: str | None = task_variables.get("encounter_end")

        self._logger.info(
            "calculating_quantities",
            procedure_count=len(procedures),
            tenant_id=ctx.tenant_id,
        )

        encounter_start: datetime | None = None
        encounter_end: datetime | None = None

        if encounter_start_str:
            try:
                encounter_start = datetime.fromisoformat(encounter_start_str)
            except ValueError:
                pass
        if encounter_end_str:
            try:
                encounter_end = datetime.fromisoformat(encounter_end_str)
            except ValueError:
                pass

        quantified: list[dict[str, Any]] = []
        total_items = 0

        for proc in procedures:
            code = proc.get("code", "")
            existing_qty = proc.get("quantity", 1)
            result_proc = {**proc}

            if code in _DURATION_BASED_CODES and encounter_start and encounter_end:
                # Calculate duration-based quantity
                duration_minutes = (encounter_end - encounter_start).total_seconds() / 60
                if code == "20101012":
                    # Anesthesia: 15-minute blocks
                    calculated_qty = max(1, int(Decimal(str(duration_minutes)) / Decimal("15")))
                elif code == "20201010":
                    # Ventilator: per hour
                    calculated_qty = max(1, int(Decimal(str(duration_minutes)) / Decimal("60")))
                else:
                    # Daily rate
                    calculated_qty = max(1, int(Decimal(str(duration_minutes)) / Decimal("1440")) + 1)

                result_proc["quantity"] = calculated_qty
                result_proc["quantity_method"] = "duration"
                result_proc["duration_minutes"] = round(duration_minutes, 2)
            else:
                result_proc["quantity"] = max(1, existing_qty)
                result_proc["quantity_method"] = "direct"

            # Enforce maximum quantity limits
            max_qty = _MAX_QUANTITY_MAP.get(code)
            if max_qty and result_proc["quantity"] > max_qty:
                self._logger.warning(
                    "quantity_capped",
                    code=code,
                    original=result_proc["quantity"],
                    max_allowed=max_qty,
                    tenant_id=ctx.tenant_id,
                )
                result_proc["quantity"] = max_qty
                result_proc["quantity_capped"] = True

            # Validate positive quantity
            if result_proc["quantity"] < 1:
                raise CodingException(
                    _("Quantity must be positive for procedure {code}").format(code=code),
                    bpmn_error_code="CODING_ERROR",
                    details={"code": code, "quantity": result_proc["quantity"]},
                )

            total_items += result_proc["quantity"]
            quantified.append(result_proc)

        self._logger.info(
            "quantities_calculated",
            procedure_count=len(quantified),
            total_items=total_items,
            tenant_id=ctx.tenant_id,
        )

        return {
            "quantified_procedures": quantified,
            "total_items": total_items,
        }
