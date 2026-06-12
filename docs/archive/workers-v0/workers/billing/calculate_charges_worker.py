"""Worker for calculating billing charges."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.exceptions import BillingException
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-calculate-charges", max_jobs=1, lock_duration=300000)
class CalculateChargesWorker(BaseWorker):
    """Calculates billing charges for procedures.

    This worker calculates line items with proper monetary handling,
    including modifier adjustments and quantity-based pricing.

    Input Variables:
        procedures: List[Dict] - Procedures with:
            - code: str - Procedure code
            - quantity: int - Quantity performed
            - unit_price: Decimal - Unit price in BRL
            - description: Optional[str]
        modifiers: Optional[List[Dict]] - Modifiers with:
            - code: str - Modifier code
            - type: str - Modifier type (percentage, fixed)
            - value: Decimal - Adjustment value
            - applies_to: Optional[str] - Specific procedure code

    Output Variables:
        line_items: List[Dict] - Calculated line items
        total_amount: Decimal - Total amount in BRL
        modifier_adjustments: Decimal - Total modifier adjustments
    """

    # Standard modifier types and their default behaviors
    MODIFIER_TYPES = {
        "multiple_procedure": -50.0,  # 50% reduction for multiple procedures
        "assistant_surgeon": 20.0,  # 20% of surgeon fee
        "bilateral": 50.0,  # 50% increase for bilateral procedures
        "unusual_circumstances": 25.0,  # 25% increase for unusual circumstances
        "professional_component": -40.0,  # 40% reduction for professional component only
        "technical_component": -60.0,  # 60% reduction for technical component only
    }

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        """Get operation name."""
        return _("Calcular valores de cobrança")

    def _evaluate_billing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate billing DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='billing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """Process charge calculation.

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with calculated line items and totals

        Raises:
            BillingException: If calculation fails
        """
        # Validate required input variables
        procedures = variables.get("procedures")
        if not procedures or not isinstance(procedures, list):
            raise BillingException(
                message=_("Lista de procedimentos é obrigatória"),
                bpmn_error_code="MISSING_PROCEDURES",
                retryable=False,
                details={"variables": list(variables.keys())}
            )

        modifiers = variables.get("modifiers") or []
        if not isinstance(modifiers, list):
            raise BillingException(
                message=_("Modificadores devem ser uma lista"),
                bpmn_error_code="INVALID_MODIFIERS_FORMAT",
                retryable=False,
                details={"type": type(modifiers).__name__}
            )

        self._logger.info(
            "Calculating charges",
            procedure_count=len(procedures),
            modifier_count=len(modifiers)
        )

        try:
            # Calculate line items
            line_items, total_amount, total_adjustments = await self._calculate_line_items(
                procedures,
                modifiers
            )

            self._logger.info(
                "Charges calculated successfully",
                line_item_count=len(line_items),
                total_amount=str(total_amount),
                total_adjustments=str(total_adjustments)
            )

            return WorkerResult.ok({
                "line_items": line_items,
                "total_amount": str(total_amount.amount),
                "modifier_adjustments": str(total_adjustments.amount),
                "line_item_count": len(line_items)
            })

        except Exception as e:
            self._logger.error(
                "Error calculating charges",
                error=str(e),
                exc_info=True
            )
            raise

    async def _calculate_line_items(
        self,
        procedures: List[Dict[str, Any]],
        modifiers: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], Money, Money]:
        """Calculate line items with modifiers.

        Args:
            procedures: List of procedures to calculate
            modifiers: List of modifiers to apply

        Returns:
            Tuple of (line_items, total_amount, total_adjustments)

        Raises:
            BillingException: If calculation fails
        """
        line_items = []
        running_total = Money.zero()
        total_adjustments = Money.zero()

        for idx, proc in enumerate(procedures):
            # Extract and validate procedure data
            code = proc.get("code")
            if not code:
                raise BillingException(
                    message=_("Código do procedimento é obrigatório"),
                    bpmn_error_code="MISSING_PROCEDURE_CODE",
                    retryable=False,
                    details={"index": idx}
                )

            quantity = proc.get("quantity", 1)
            try:
                quantity = int(quantity)
                if quantity <= 0:
                    raise ValueError("Quantity must be positive")
            except (ValueError, TypeError):
                raise BillingException(
                    message=_("Quantidade inválida para procedimento"),
                    bpmn_error_code="INVALID_QUANTITY",
                    retryable=False,
                    details={"index": idx, "code": code, "quantity": quantity}
                )

            unit_price_raw = proc.get("unit_price")
            if unit_price_raw is None:
                raise BillingException(
                    message=_("Preço unitário é obrigatório"),
                    bpmn_error_code="MISSING_UNIT_PRICE",
                    retryable=False,
                    details={"index": idx, "code": code}
                )

            try:
                unit_price = Money.brl(Decimal(str(unit_price_raw)))
                if unit_price.amount < Decimal("0"):
                    raise ValueError("Unit price cannot be negative")
            except (ValueError, TypeError) as e:
                raise BillingException(
                    message=_("Preço unitário inválido"),
                    bpmn_error_code="INVALID_UNIT_PRICE",
                    retryable=False,
                    details={"index": idx, "code": code, "unit_price": unit_price_raw, "error": str(e)}
                )

            # Calculate base amount
            base_amount = unit_price * Decimal(str(quantity))

            # Apply modifiers
            applicable_modifiers = self._get_applicable_modifiers(modifiers, code)
            adjusted_amount, adjustment_total = await self._apply_modifiers(
                base_amount,
                applicable_modifiers,
                code
            )

            # Update totals
            running_total += adjusted_amount
            total_adjustments += adjustment_total

            # Create line item
            line_item = {
                "sequence": idx + 1,
                "code": code,
                "description": proc.get("description", ""),
                "quantity": quantity,
                "unit_price": str(unit_price.amount),
                "base_amount": str(base_amount.amount),
                "adjustments": str(adjustment_total.amount),
                "total_price": str(adjusted_amount.amount),
                "modifiers": [
                    {
                        "code": mod.get("code"),
                        "type": mod.get("type"),
                        "value": str(mod.get("value", "0"))
                    }
                    for mod in applicable_modifiers
                ]
            }

            line_items.append(line_item)

            self._logger.debug(
                "Line item calculated",
                sequence=idx + 1,
                code=code,
                base_amount=str(base_amount),
                total_price=str(adjusted_amount),
                modifier_count=len(applicable_modifiers)
            )

        return line_items, running_total, total_adjustments

    def _get_applicable_modifiers(
        self,
        modifiers: List[Dict[str, Any]],
        procedure_code: str
    ) -> List[Dict[str, Any]]:
        """Get modifiers applicable to a specific procedure.

        Args:
            modifiers: List of all modifiers
            procedure_code: Procedure code to check

        Returns:
            List of applicable modifiers
        """
        applicable = []

        for modifier in modifiers:
            applies_to = modifier.get("applies_to")

            # If no specific code, applies to all
            if not applies_to:
                applicable.append(modifier)
            # If specific code matches
            elif applies_to == procedure_code:
                applicable.append(modifier)
            # If wildcard pattern (e.g., "1*" for all codes starting with 1)
            elif "*" in applies_to:
                pattern = applies_to.replace("*", "")
                if procedure_code.startswith(pattern):
                    applicable.append(modifier)

        return applicable

    async def _apply_modifiers(
        self,
        base_amount: Money,
        modifiers: List[Dict[str, Any]],
        procedure_code: str
    ) -> tuple[Money, Money]:
        """Apply modifiers to base amount.

        Args:
            base_amount: Base amount before modifiers
            modifiers: List of modifiers to apply
            procedure_code: Procedure code for logging

        Returns:
            Tuple of (adjusted_amount, total_adjustment)

        Raises:
            BillingException: If modifier is invalid
        """
        if not modifiers:
            return base_amount, Money.zero()

        adjusted = base_amount
        total_adjustment = Money.zero()

        for modifier in modifiers:
            mod_code = modifier.get("code", "unknown")
            mod_type = modifier.get("type", "percentage")
            mod_value = modifier.get("value")

            if mod_value is None:
                # Try to get default value from standard modifiers
                mod_value = self.MODIFIER_TYPES.get(mod_type)
                if mod_value is None:
                    self._logger.warning(
                        "Modifier value not specified and no default available",
                        code=mod_code,
                        type=mod_type,
                        procedure=procedure_code
                    )
                    continue

            try:
                value_decimal = Decimal(str(mod_value))
            except (ValueError, TypeError):
                raise BillingException(
                    message=_("Valor do modificador inválido"),
                    bpmn_error_code="INVALID_MODIFIER_VALUE",
                    retryable=False,
                    details={"modifier": mod_code, "value": mod_value}
                )

            # Calculate adjustment based on type
            if mod_type == "percentage":
                adjustment = base_amount * (value_decimal / Decimal("100"))
            elif mod_type == "fixed":
                adjustment = Money.brl(value_decimal)
            else:
                raise BillingException(
                    message=_("Tipo de modificador desconhecido: {type}").format(type=mod_type),
                    bpmn_error_code="UNKNOWN_MODIFIER_TYPE",
                    retryable=False,
                    details={"modifier": mod_code, "type": mod_type}
                )

            adjusted += adjustment
            total_adjustment += adjustment

            self._logger.debug(
                "Modifier applied",
                code=mod_code,
                type=mod_type,
                value=str(value_decimal),
                adjustment=str(adjustment),
                procedure=procedure_code
            )

        # Ensure non-negative result
        if adjusted.amount < Decimal("0"):
            self._logger.warning(
                "Negative amount after modifiers, setting to zero",
                procedure=procedure_code,
                adjusted=str(adjusted)
            )
            adjusted = Money.zero()

        return adjusted, total_adjustment
