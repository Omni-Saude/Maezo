"""Builder for ROUTING rule definitions."""

import re
from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()

_RE_NEONATAL = re.compile(r"neonatal", re.IGNORECASE)
_RE_PEDIATRIC = re.compile(r"pedi[aá]tric", re.IGNORECASE)
_RE_AGE_BAND = re.compile(r"(\d+)\s*(?:anos?|dias?)", re.IGNORECASE)


def build_routing(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return a ROUTING rule dict.

    Bed type and handler classification are extracted from raw text signals;
    DMN decides the routing outcome and handler assignment.
    """
    codes = _parser.parse_procedure_codes(text)

    # Extract raw bed/unit type signal from text — DMN decides the canonical value
    if _RE_NEONATAL.search(text):
        bed_type_signal = "neonatal"
    elif _RE_PEDIATRIC.search(text):
        bed_type_signal = "pediatrico"
    else:
        bed_type_signal = "adulto"

    # Extract age band raw text for DMN consumption
    age_match = _RE_AGE_BAND.search(text)
    age_band = age_match.group(0) if age_match else ""

    return {
        "archetype": "ROUTING",
        "category": "AUTHORIZATION",
        "rule_definition": {
            "patient_type": bed_type_signal,
            "age_band": age_band,
            "bed_type": bed_type_signal,
            "payer_id": payer_id,
            "procedure_code": codes[0] if codes else "",
            "output_route": "",
            "output_handler": "",
            "output_approved": True,
        },
    }
