"""Builder for SLA_TIME_BOUND rule definitions."""

from typing import Dict

from ..clause_parser import ClauseParser

_parser = ClauseParser()


def build_sla(text: str, payer_id: str) -> Dict:
    """Extract inputs from clause text and return an SLA_TIME_BOUND rule dict.

    SLA enforcement logic is delegated to DMN; this builder extracts
    raw deadline and time window signals from the text.
    """
    deadlines = _parser.parse_deadline_days(text)
    time_windows = _parser.parse_time_windows(text)
    codes = _parser.parse_procedure_codes(text)

    return {
        "archetype": "SLA_TIME_BOUND",
        "category": "COMPLIANCE",
        "rule_definition": {
            "procedure_code": codes[0] if codes else "",
            "amount": 0,
            "payer_id": payer_id,
            "deadline_days": deadlines[0] if deadlines else 0,
            "time_window_hours": time_windows[0] if time_windows else 0,
            "output_requires_auth": False,
            "output_auth_type": "sla_enforcement",
            "output_urgency_level": "",
        },
    }
