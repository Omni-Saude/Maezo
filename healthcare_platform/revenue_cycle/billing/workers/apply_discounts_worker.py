"""Worker for applying contractual discounts.

Archetype: FINANCIAL_CALCULATION
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.exceptions import BillingException
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-apply-discounts", max_jobs=1, lock_duration=300000)
class ApplyDiscountsWorker(BaseWorker):
    """Applies contractual discounts to billing line items.

    This worker applies various types of discounts based on contract terms,
    including volume discounts, early payment discounts, and package deals.

    Input Variables:
        line_items: List[Dict] - Line items with:
            - sequence: int - Line sequence number
            - code: str - Procedure code
            - total_price: Decimal - Line total before discount
        discount_rules: List[Dict] - Discount rules with:
            - type: str - Discount type (volume, early_payment, package)
            - percentage: Decimal - Discount percentage
            - conditions: Dict - Conditions for applying discount

    Output Variables:
        discounted_items: List[Dict] - Items with discounts applied
        total_discount: Decimal - Total discount amount
        final_amount: Decimal - Final amount after discounts
    """

    # Supported discount types
    DISCOUNT_TYPES = {
        "volume": "Volume discount based on quantity thresholds",
        "early_payment": "Early payment discount",
        "package": "Package deal discount",
        "promotional": "Promotional discount",
        "contractual": "Standard contractual discount",
        "senior": "Senior citizen discount",
        "emergency": "Emergency service discount"
    }

    def __init__(self, tasy_api_client: TasyApiClientProtocol | None = None) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()
        self._tasy_api_client = tasy_api_client

    @property
    def operation_name(self) -> str:
        """Get operation name."""
        return _("Aplicar descontos contratuais")

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
        """Process discount application.

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with discounted items and totals

        Raises:
            BillingException: If discount application fails
        """
        # Validate required input variables
        line_items = variables.get("line_items")
        if not line_items or not isinstance(line_items, list):
            raise BillingException(
                message=_("Itens de linha são obrigatórios"),
                bpmn_error_code="MISSING_LINE_ITEMS",
                retryable=False,
                details={"variables": list(variables.keys())}
            )

        discount_rules = variables.get("discount_rules") or []
        if not isinstance(discount_rules, list):
            raise BillingException(
                message=_("Regras de desconto devem ser uma lista"),
                bpmn_error_code="INVALID_DISCOUNT_RULES_FORMAT",
                retryable=False,
                details={"type": type(discount_rules).__name__}
            )

        # Optionally fetch contract rules from TASY API
        if self._tasy_api_client:
            contract_id = variables.get("contract_id")
            if contract_id:
                try:
                    self._logger.debug("Fetching contract rules from TASY", contract_id="[REDACTED]")
                    # Fetch contract data from TASY
                    contract_pricing = await self._tasy_api_client.get_contract_pricing(contract_id)
                    tasy_discount_rules = contract_pricing.get("discount_rules", [])

                    if tasy_discount_rules:
                        self._logger.info(
                            "Loaded discount rules from TASY contract",
                            contract_id="[REDACTED]",
                            tasy_rule_count=len(tasy_discount_rules),
                            original_rule_count=len(discount_rules),
                        )
                        # Merge TASY rules with provided rules (TASY rules take precedence)
                        discount_rules = tasy_discount_rules + discount_rules
                except Exception as e:
                    # Log but don't fail - fall back to provided discount_rules
                    self._logger.warning(
                        "Failed to fetch contract rules from TASY, using provided rules",
                        error=str(e)
                    )

        self._logger.info(
            "Applying discounts",
            line_item_count=len(line_items),
            discount_rule_count=len(discount_rules)
        )

        try:
            # Apply discounts to line items
            result = await self._apply_discounts(line_items, discount_rules)

            self._logger.info(
                "Discounts applied successfully",
                total_discount=result["total_discount"],
                final_amount=result["final_amount"]
            )

            return WorkerResult.ok(result)

        except Exception as e:
            self._logger.error(
                "Error applying discounts",
                error=str(e),
                exc_info=True
            )
            raise

    async def _apply_discounts(
        self,
        line_items: List[Dict[str, Any]],
        discount_rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Apply discounts to line items.

        Args:
            line_items: List of line items to discount
            discount_rules: List of discount rules to apply

        Returns:
            Dictionary with discounted items and totals

        Raises:
            BillingException: If discount calculation fails
        """
        discounted_items = []
        original_total = Money.zero()
        total_discount = Money.zero()

        # First pass: calculate original total and validate items
        for item in line_items:
            total_price_raw = item.get("total_price")
            if total_price_raw is None:
                raise BillingException(
                    message=_("Preço total do item é obrigatório"),
                    bpmn_error_code="MISSING_ITEM_TOTAL",
                    retryable=False,
                    details={"item": item}
                )

            try:
                total_price = Money.brl(Decimal(str(total_price_raw)))
                original_total += total_price
            except (ValueError, TypeError):
                raise BillingException(
                    message=_("Preço total do item inválido"),
                    bpmn_error_code="INVALID_ITEM_TOTAL",
                    retryable=False,
                    details={"item": item, "total_price": total_price_raw}
                )

        # Second pass: apply discounts
        for idx, item in enumerate(line_items):
            code = item.get("code", "")
            sequence = item.get("sequence", idx + 1)
            total_price = Money.brl(Decimal(str(item.get("total_price", "0"))))

            # Find applicable discounts
            applicable_rules = self._get_applicable_discount_rules(
                discount_rules,
                item,
                line_items,
                original_total
            )

            # Apply each discount rule
            item_discount = Money.zero()
            applied_discounts = []

            for rule in applicable_rules:
                discount_amount = await self._calculate_discount(
                    total_price,
                    rule,
                    item,
                    line_items
                )

                item_discount += discount_amount
                applied_discounts.append({
                    "type": rule.get("type"),
                    "percentage": str(rule.get("percentage", "0")),
                    "amount": str(discount_amount.amount)
                })

                self._logger.debug(
                    "Discount applied to item",
                    sequence=sequence,
                    code=code,
                    discount_type=rule.get("type"),
                    amount=str(discount_amount)
                )

            # Calculate final item price
            final_price = total_price - item_discount
            if final_price.amount < Decimal("0"):
                self._logger.warning(
                    "Negative price after discounts, setting to zero",
                    sequence=sequence,
                    original=str(total_price),
                    discount=str(item_discount)
                )
                final_price = Money.zero()
                item_discount = total_price

            total_discount += item_discount

            # Create discounted item
            discounted_item = {
                **item,
                "original_price": str(total_price.amount),
                "discount_amount": str(item_discount.amount),
                "final_price": str(final_price.amount),
                "applied_discounts": applied_discounts
            }

            discounted_items.append(discounted_item)

        final_amount = original_total - total_discount

        return {
            "discounted_items": discounted_items,
            "total_discount": str(total_discount.amount),
            "final_amount": str(final_amount.amount),
            "original_amount": str(original_total.amount),
            "discount_percentage": str(
                (total_discount.amount / original_total.amount * Decimal("100"))
                if original_total.amount > Decimal("0")
                else Decimal("0")
            )
        }

    def _get_applicable_discount_rules(
        self,
        rules: List[Dict[str, Any]],
        item: Dict[str, Any],
        all_items: List[Dict[str, Any]],
        total_amount: Money
    ) -> List[Dict[str, Any]]:
        """Get discount rules applicable to an item.

        Args:
            rules: All discount rules
            item: Current line item
            all_items: All line items
            total_amount: Total amount of all items

        Returns:
            List of applicable discount rules
        """
        applicable = []

        for rule in rules:
            if self._is_rule_applicable(rule, item, all_items, total_amount):
                applicable.append(rule)

        return applicable

    def _is_rule_applicable(
        self,
        rule: Dict[str, Any],
        item: Dict[str, Any],
        all_items: List[Dict[str, Any]],
        total_amount: Money
    ) -> bool:
        """Check if a discount rule is applicable.

        Args:
            rule: Discount rule to check
            item: Current line item
            all_items: All line items
            total_amount: Total amount of all items

        Returns:
            True if rule is applicable
        """
        conditions = rule.get("conditions", {})

        # Check procedure code condition
        applies_to_code = conditions.get("procedure_code")
        if applies_to_code:
            item_code = item.get("code", "")
            if applies_to_code != item_code:
                # Check wildcard match
                if "*" in applies_to_code:
                    pattern = applies_to_code.replace("*", "")
                    if not item_code.startswith(pattern):
                        return False
                else:
                    return False

        # Check minimum quantity condition
        min_quantity = conditions.get("min_quantity")
        if min_quantity is not None:
            try:
                item_quantity = int(item.get("quantity", 0))
                if item_quantity < int(min_quantity):
                    return False
            except (ValueError, TypeError):
                return False

        # Check minimum amount condition
        min_amount = conditions.get("min_amount")
        if min_amount is not None:
            try:
                min_money = Money.brl(Decimal(str(min_amount)))
                if total_amount < min_money:
                    return False
            except (ValueError, TypeError):
                return False

        # Check date-based conditions (if present)
        valid_from = conditions.get("valid_from")
        valid_until = conditions.get("valid_until")
        # Note: Date validation would require current date context
        # Skipping for now as it's not in the input variables

        return True

    async def _calculate_discount(
        self,
        base_amount: Money,
        rule: Dict[str, Any],
        item: Dict[str, Any],
        all_items: List[Dict[str, Any]]
    ) -> Money:
        """Calculate discount amount for a rule.

        Args:
            base_amount: Base amount before discount
            rule: Discount rule to apply
            item: Current line item
            all_items: All line items

        Returns:
            Discount amount

        Raises:
            BillingException: If discount calculation fails
        """
        discount_type = rule.get("type", "")
        percentage = rule.get("percentage")

        if percentage is None:
            self._logger.warning(
                "Discount rule missing percentage",
                type=discount_type
            )
            return Money.zero()

        try:
            percentage_decimal = Decimal(str(percentage))

            # Validate percentage range
            if percentage_decimal < Decimal("0") or percentage_decimal > Decimal("100"):
                raise BillingException(
                    message=_("Percentual de desconto deve estar entre 0 e 100"),
                    bpmn_error_code="INVALID_DISCOUNT_PERCENTAGE",
                    retryable=False,
                    details={"type": discount_type, "percentage": percentage}
                )

            # Calculate discount based on type
            if discount_type == "volume":
                # Volume discounts may have tiered percentages
                discount_amount = await self._calculate_volume_discount(
                    base_amount,
                    percentage_decimal,
                    item,
                    all_items
                )
            else:
                # Standard percentage discount
                discount_amount = base_amount * (percentage_decimal / Decimal("100"))

            return discount_amount

        except (ValueError, TypeError) as e:
            raise BillingException(
                message=_("Percentual de desconto inválido"),
                bpmn_error_code="INVALID_DISCOUNT_PERCENTAGE",
                retryable=False,
                details={"type": discount_type, "percentage": percentage, "error": str(e)}
            )

    async def _calculate_volume_discount(
        self,
        base_amount: Money,
        percentage: Decimal,
        item: Dict[str, Any],
        all_items: List[Dict[str, Any]]
    ) -> Money:
        """Calculate volume-based discount.

        Volume discounts may increase with quantity thresholds.

        Args:
            base_amount: Base amount before discount
            percentage: Base discount percentage
            item: Current line item
            all_items: All line items

        Returns:
            Discount amount
        """
        quantity = int(item.get("quantity", 1))

        # Apply tiered discount based on quantity
        if quantity >= 100:
            adjusted_percentage = percentage * Decimal("1.5")  # 50% bonus
        elif quantity >= 50:
            adjusted_percentage = percentage * Decimal("1.3")  # 30% bonus
        elif quantity >= 20:
            adjusted_percentage = percentage * Decimal("1.15")  # 15% bonus
        else:
            adjusted_percentage = percentage

        # Cap at 100%
        adjusted_percentage = min(adjusted_percentage, Decimal("100"))

        return base_amount * (adjusted_percentage / Decimal("100"))
