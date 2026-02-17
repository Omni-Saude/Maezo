"""Assign prices to procedures from TUSS price tables.

CIB7 External Task Topic: production.assign_prices
BPMN Error Codes: CONTRACT_RULE_VIOLATION, BILLING_ERROR
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import (
    BillingException,
    ContractRuleViolation,
    ExternalServiceException,
)
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


class PriceTableEntry:
    """In-memory price table entry."""

    __slots__ = ("code", "unit_price", "currency", "effective_date", "contract_id")

    def __init__(
        self,
        code: str,
        unit_price: Decimal,
        currency: str = "BRL",
        effective_date: str = "",
        contract_id: str = "",
    ) -> None:
        self.code = code
        self.unit_price = unit_price
        self.currency = currency
        self.effective_date = effective_date
        self.contract_id = contract_id


class AssignPricesWorker:
    """Assigns unit and total prices to procedures.

    Looks up prices from tenant-specific contract/price tables.
    Supports TUSS reference table and custom contract prices.

    Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = "production.assign_prices"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._tasy = tasy_api_client
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
    @track_task_execution(metric_name="production_assign_prices")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Assign prices to quantified procedures.

        Task Variables (input):
            quantified_procedures: list[dict] - Procedures with quantities
            contract_id: str | None - Specific contract to use
            price_table_id: str | None - Price table identifier

        Returns:
            priced_procedures: list[dict] - Procedures with prices assigned
            total_amount: str - Total amount as decimal string
            currency: str - Currency code (BRL)
        """
        ctx = get_required_tenant()
        procedures: list[dict[str, Any]] = task_variables.get("quantified_procedures", [])
        contract_id: str = task_variables.get("contract_id", "")
        price_table_id: str = task_variables.get("price_table_id", "tuss_default")

        self._logger.info(
            "assigning_prices",
            procedure_count=len(procedures),
            contract_id=contract_id or "default",
            price_table_id=price_table_id,
            tenant_id=ctx.tenant_id,
        )

        priced: list[dict[str, Any]] = []
        total = Decimal("0.00")
        missing_prices: list[str] = []

        # Try TASY pricing first if available
        tasy_pricing_available = self._tasy is not None
        tasy_price_source = "tasy_api"

        for proc in procedures:
            code = proc.get("code", "")
            quantity = proc.get("quantity", 1)
            result_proc = {**proc}

            unit_price: Decimal | None = None
            currency = "BRL"
            price_source = "unknown"

            # Strategy 1: Try TASY pricing (Brasindice/SIMPRO/Contract)
            if tasy_pricing_available:
                try:
                    # Try get_procedure_price first for TUSS/procedure codes
                    tasy_result = await self._tasy.get_procedure_price(
                        procedure_code=code, table=price_table_id
                    )
                    unit_price = Decimal(str(tasy_result.get("unit_price", 0)))
                    currency = tasy_result.get("currency", "BRL")
                    price_source = f"tasy:{tasy_result.get('table', price_table_id)}"

                    self._logger.debug(
                        "price_from_tasy",
                        code=code,
                        unit_price=str(unit_price),
                        source=price_source,
                        tenant_id=ctx.tenant_id,
                    )
                except ExternalServiceException as exc:
                    # TASY price not found, will try fallback
                    self._logger.debug(
                        "tasy_price_not_found",
                        code=code,
                        error=str(exc),
                        tenant_id=ctx.tenant_id,
                    )

            # Strategy 2: Fallback to FHIR ChargeItemDefinition
            if unit_price is None:
                price_table = await self._load_price_table(price_table_id, contract_id)
                price_entry = price_table.get(code)

                if price_entry:
                    unit_price = price_entry.unit_price
                    currency = price_entry.currency
                    price_source = f"fhir:{price_entry.contract_id or price_table_id}"

                    self._logger.debug(
                        "price_from_fhir_fallback",
                        code=code,
                        unit_price=str(unit_price),
                        source=price_source,
                        tenant_id=ctx.tenant_id,
                    )

            # Assign price or mark as missing
            if unit_price is None or unit_price == Decimal("0.00"):
                missing_prices.append(code)
                self._logger.warning(
                    "price_not_found",
                    code=code,
                    contract_id=contract_id,
                    tasy_tried=tasy_pricing_available,
                    tenant_id=ctx.tenant_id,
                )
                result_proc["unit_price"] = "0.00"
                result_proc["total_price"] = "0.00"
                result_proc["currency"] = currency
                result_proc["price_source"] = "missing"
            else:
                proc_total = unit_price * Decimal(str(quantity))
                result_proc["unit_price"] = str(unit_price)
                result_proc["total_price"] = str(proc_total)
                result_proc["currency"] = currency
                result_proc["price_source"] = price_source
                total += proc_total

            priced.append(result_proc)

        if missing_prices:
            raise ContractRuleViolation(
                _("Price not found for procedure {code} in contract {contract_id}").format(
                    code=", ".join(missing_prices),
                    contract_id=contract_id or price_table_id,
                ),
                details={
                    "missing_codes": missing_prices,
                    "contract_id": contract_id,
                },
            )

        self._logger.info(
            "prices_assigned",
            procedure_count=len(priced),
            total_amount=str(total),
            currency="BRL",
            tenant_id=ctx.tenant_id,
        )

        return {
            "priced_procedures": priced,
            "total_amount": str(total),
            "currency": "BRL",
        }

    async def _load_price_table(
        self, table_id: str, contract_id: str
    ) -> dict[str, PriceTableEntry]:
        """Load price table from FHIR or configuration.

        In production, this queries FHIR ChargeItemDefinition resources
        or a dedicated pricing microservice.
        """
        ctx = get_required_tenant()

        try:
            # Search for ChargeItemDefinition resources
            charge_items = await self._fhir.search(
                "ChargeItemDefinition",
                {"status": "active", "_tag": ctx.tenant_id},
            )

            table: dict[str, PriceTableEntry] = {}
            for item in charge_items:
                code = ""
                for coding in item.get("code", {}).get("coding", []):
                    code = coding.get("code", "")
                    break

                price_components = item.get("propertyGroup", [{}])[0].get(
                    "priceComponent", []
                )
                unit_price = Decimal("0.00")
                for comp in price_components:
                    if comp.get("type") == "base":
                        amount = comp.get("amount", {})
                        unit_price = Decimal(str(amount.get("value", 0)))
                        break

                if code:
                    table[code] = PriceTableEntry(
                        code=code,
                        unit_price=unit_price,
                        contract_id=contract_id,
                    )

            return table

        except Exception as exc:
            self._logger.warning(
                "price_table_load_failed",
                table_id=table_id,
                error=str(exc),
                tenant_id=ctx.tenant_id,
            )
            raise BillingException(
                _("No active price table found for tenant {tenant_id}").format(
                    tenant_id=ctx.tenant_id
                ),
                bpmn_error_code="BILLING_ERROR",
            ) from exc
