"""Pricing assignment service - extracted from AssignPricesWorker.

Handles price lookup (TASY first, FHIR fallback) and pricing loop.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class PricingAssignmentService:
    """Orchestrates price assignment to procedures."""

    def __init__(
        self,
        fhir_client: Optional[FHIRClientProtocol] = None,
        tasy_api_client: Optional[TasyApiClientProtocol] = None,
    ) -> None:
        self.fhir_client = fhir_client
        self.tasy_api_client = tasy_api_client

    def assign_prices(
        self, procedures: List[Dict[str, Any]], contract_id: str, price_table_id: str
    ) -> Dict[str, Any]:
        """Assign prices to procedures. Returns priced_procedures, total_amount, missing_codes."""
        priced: List[Dict[str, Any]] = []
        total = Decimal("0.00")
        missing_prices: List[str] = []

        for proc in procedures:
            code = proc.get("code", "")
            quantity = proc.get("quantity", 1)
            result_proc = {**proc}

            unit_price = self._lookup_price(code, price_table_id)

            if unit_price is None or unit_price == Decimal("0.00"):
                missing_prices.append(code)
                result_proc["unit_price"] = "0.00"
                result_proc["total_price"] = "0.00"
                result_proc["currency"] = "BRL"
                result_proc["price_source"] = "missing"
            else:
                proc_total = unit_price * Decimal(str(quantity))
                result_proc["unit_price"] = str(unit_price)
                result_proc["total_price"] = str(proc_total)
                result_proc["currency"] = "BRL"
                result_proc["price_source"] = "lookup"
                total += proc_total

            priced.append(result_proc)

        return {
            "priced_procedures": priced,
            "total_amount": str(total),
            "currency": "BRL",
            "missing_codes": missing_prices,
        }

    def _lookup_price(self, code: str, price_table_id: str) -> Optional[Decimal]:
        """Look up price for a procedure code. TASY first, FHIR fallback."""
        if self.tasy_api_client:
            try:
                result = self.tasy_api_client.get_procedure_price(
                    procedure_code=code, table=price_table_id
                )
                if result and result.get("unit_price"):
                    return Decimal(str(result["unit_price"]))
            except Exception:
                logger.debug(f"TASY price lookup failed for {code}, trying FHIR")

        if self.fhir_client:
            try:
                items = self.fhir_client.search(
                    "ChargeItemDefinition",
                    {"code": code, "status": "active"},
                )
                if items:
                    price_comps = (
                        items[0].get("propertyGroup", [{}])[0].get("priceComponent", [])
                    )
                    for comp in price_comps:
                        if comp.get("type") == "base":
                            return Decimal(str(comp["amount"]["value"]))
            except Exception:
                logger.debug(f"FHIR price lookup failed for {code}")

        return None
