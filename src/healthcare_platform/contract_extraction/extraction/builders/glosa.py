"""Builder for GLOSA_RULE rule definitions."""

import re
from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()

_RE_GLOSA_CODE = re.compile(
    r"c[oó]digo\s+(?:de\s+)?glosa\s*[:=]?\s*(\w+)", re.IGNORECASE
)


def build_glosa(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a GLOSA_RULE rule dict.

    Glosa classification and appeal routing logic are delegated to DMN;
    this builder extracts the raw glosa code and financial signals.
    """
    codes = _parser.parse_procedure_codes(text)
    prices = _parser.parse_currency(text)
    glosa_code_match = _RE_GLOSA_CODE.search(text)

    return {
        "archetype": "GLOSA_RULE",
        "category": "COMPLIANCE",
        "rule_definition": {
            "procedure_code": codes[0] if codes else "",
            "amount": prices[0] if prices else 0,
            "payer_id": payer_id,
            "glosa_code": glosa_code_match.group(1) if glosa_code_match else "",
            "output_requires_auth": True,
            "output_auth_type": "glosa_appeal",
            "output_urgency_level": "",
        },
    }
