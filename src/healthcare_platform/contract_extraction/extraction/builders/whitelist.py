"""Builder for WHITELIST rule definitions."""

import re
from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()

_RE_SES = re.compile(r"SES", re.IGNORECASE)
_RE_AMB = re.compile(r"AMB", re.IGNORECASE)


def build_whitelist(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a WHITELIST rule dict.

    Reference table classification is extracted as raw signals from text;
    DMN decides the canonical table name and authorization logic.
    """
    codes = _parser.parse_procedure_codes(text)

    # Extract which reference table signal is present — DMN resolves canonical name
    if _RE_SES.search(text):
        reference_table_signal = "SES"
    elif _RE_AMB.search(text):
        reference_table_signal = "AMB"
    else:
        reference_table_signal = ""

    # Extract a short description from the first sentence
    first_sentence = text.split(".")[0].strip()
    item_name = first_sentence[:120] if first_sentence else ""

    return {
        "archetype": "WHITELIST",
        "category": "AUTHORIZATION",
        "rule_definition": {
            "code": codes[0] if codes else "",
            "payer_id": payer_id,
            "reference_table_signal": reference_table_signal,
            "output_authorized": True,
            "output_item_name": item_name,
            "output_reference_table": "",
        },
    }
