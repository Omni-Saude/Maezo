"""Builder for PENALTY_FINANCIAL rule definitions."""

from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()


def build_penalty(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a PENALTY_FINANCIAL rule dict.

    Penalty calculation logic is delegated to DMN; this builder extracts
    raw percentage, price, and code signals from the text.
    """
    percentages = _parser.parse_percentages(text)
    prices = _parser.parse_currency(text)
    codes = _parser.parse_procedure_codes(text)

    return {
        "archetype": "PENALTY_FINANCIAL",
        "category": "COMPLIANCE",
        "rule_definition": {
            "procedure_code": codes[0] if codes else "",
            "payer_id": payer_id,
            "quantity": 1,
            "item_code": codes[0] if codes else "",
            "reference_price": prices[0] if prices else 0,
            "monthly_volume": 0,
            "payment_days": 0,
            "penalty_percentage": percentages[0] if percentages else 0,
            "output_unit_price": prices[0] if prices else 0,
            "output_total_price": prices[0] if prices else 0,
            "output_currency": "BRL",
        },
    }
