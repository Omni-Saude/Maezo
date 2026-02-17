"""Builder for AUTHORIZATION rule definitions."""

from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()


def build_authorization(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return an AUTHORIZATION rule dict.

    Auth type and urgency level are left empty for DMN to determine;
    this builder only extracts raw signals from the text.
    """
    codes = _parser.parse_procedure_codes(text)
    prices = _parser.parse_currency(text)

    return {
        "archetype": "AUTHORIZATION",
        "category": "AUTHORIZATION",
        "rule_definition": {
            "procedure_code": codes[0] if codes else "",
            "amount": prices[0] if prices else 0,
            "payer_id": payer_id,
            "output_requires_auth": True,
            "output_auth_type": "",
            "output_urgency_level": "",
        },
    }
