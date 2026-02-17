"""Builder for DISCOUNT rule definitions."""

import re
from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()
_RE_DAYS = re.compile(r"(?:em\s+)?at[eé]\s+(\d+)\s+dias", re.IGNORECASE)


def build_discount(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a DISCOUNT rule dict.

    Discount thresholds are extracted as raw values; DMN decides application logic.
    """
    percentages = _parser.parse_percentages(text)
    days_match = _RE_DAYS.search(text)
    days = int(days_match.group(1)) if days_match else 0

    return {
        "archetype": "DISCOUNT",
        "category": "DISCOUNT",
        "rule_definition": {
            "payer_id": payer_id,
            "discount_percentage": percentages[0] if percentages else 0,
            "payment_days": days,
        },
    }
