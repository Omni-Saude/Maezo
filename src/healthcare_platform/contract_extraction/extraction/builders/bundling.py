"""Builder for BUNDLING rule definitions."""

from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()


def build_bundling(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a BUNDLING rule dict.

    Bundle pricing logic is delegated to DMN; this builder extracts
    raw codes and prices from the text.
    """
    codes = _parser.parse_procedure_codes(text)
    prices = _parser.parse_currency(text)

    return {
        "archetype": "BUNDLING",
        "category": "BUNDLE",
        "rule_definition": {
            "primary_code": codes[0] if codes else "",
            "secondary_code": codes[1] if len(codes) > 1 else "",
            "same_act": True,
            "output_is_bundled": True,
            "output_bundle_price": prices[0] if prices else 0,
            "output_bundle_code": (
                "-".join(codes[:2]) if len(codes) >= 2 else ""
            ),
        },
    }
