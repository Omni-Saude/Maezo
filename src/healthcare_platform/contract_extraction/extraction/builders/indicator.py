"""Builder for INDICATOR_QUALITY_METRIC rule definitions."""

import re
from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()

_RE_INDICATOR_NAME = re.compile(
    r"(IMR|PAV|IPCSL|mortalidade|infec[cç][aã]o|evento\s+adverso)",
    re.IGNORECASE,
)


def build_indicator(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return an INDICATOR_QUALITY_METRIC rule dict.

    Indicator threshold and discount logic are delegated to DMN;
    this builder extracts the raw indicator name and percentage signals.
    """
    percentages = _parser.parse_percentages(text)
    indicator_match = _RE_INDICATOR_NAME.search(text)

    # Pass the extracted indicator name to DMN; fall back to empty string
    # so DMN can apply its own defaulting logic rather than hardcoding "IMR"
    indicator_name = indicator_match.group(1).upper() if indicator_match else ""

    return {
        "archetype": "INDICATOR_QUALITY_METRIC",
        "category": "QUALITY",
        "rule_definition": {
            "indicator_name": indicator_name,
            "payer_id": payer_id,
            "discount_percentage": percentages[0] if percentages else 0,
            "payment_days": 0,
        },
    }
