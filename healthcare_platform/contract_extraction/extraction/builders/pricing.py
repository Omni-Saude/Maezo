"""Builder for PRICING rule definitions."""

from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()


def build_pricing(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a PRICING rule dict.

    All threshold logic is delegated to DMN; this builder only extracts
    raw signal values from the text.
    """
    codes = _parser.parse_procedure_codes(text)
    prices = _parser.parse_currency(text)
    price = prices[0] if prices else 0

    return {
        "archetype": "PRICING",
        "category": "PRICING",
        "rule_definition": {
            "procedure_code": codes[0] if codes else "",
            "payer_id": payer_id,
            "quantity": 1,
            "item_code": codes[0] if codes else "",
            "reference_price": price,
            "monthly_volume": 0,
            "payment_days": 0,
            "output_unit_price": price,
            "output_total_price": price,
            "output_currency": "BRL",
        },
    }
