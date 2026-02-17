"""Builder for OPME rule definitions."""

from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()


def build_opme(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return an OPME rule dict.

    Quantity limits are extracted from raw text; DMN decides enforcement logic.
    """
    codes = _parser.parse_procedure_codes(text)
    quantities = _parser.parse_quantities(text)

    return {
        "archetype": "OPME",
        "category": "OPME",
        "rule_definition": {
            "item_code": codes[0] if codes else "",
            "max_quantity": quantities[0] if quantities else 1,
            "payer_id": payer_id,
        },
    }
