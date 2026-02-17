"""Regex-based clause parser for Brazilian healthcare contract text."""

import re
from typing import List


# Compiled patterns (module-level for performance)
_RE_PROC_CODE = re.compile(r"\d{2}\.\d{2}\.\d{2}\.\d{3}-\d")
_RE_PROC_CODE_9DIGIT = re.compile(r"(?<!\d)(\d{9})(?!\d)")
_RE_CURRENCY = re.compile(r"R\$\s*([\d.]+,\d{2})")
_RE_PERCENTAGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_RE_QUANTITY = re.compile(r"limitad[oa]\s+a\s+(\d+)", re.IGNORECASE)
_RE_PAYER = re.compile(r"(SES[-/][A-Z]{2}|ANS-\d{6})")
_RE_TIME_WINDOW = re.compile(r"(\d+)\s*(?:h(?:oras?)?|hrs?)\b", re.IGNORECASE)
_RE_DEADLINE_DAYS = re.compile(r"(?:em\s+)?at[eé]\s+(\d+)\s+dias", re.IGNORECASE)


def _br_currency_to_float(raw: str) -> float:
    """Convert Brazilian currency string to float: '1.234,56' -> 1234.56."""
    return float(raw.replace(".", "").replace(",", "."))


class ClauseParser:
    """Parse Brazilian healthcare contract clauses using only stdlib ``re``."""

    def parse_procedure_codes(self, text: str) -> List[str]:
        """Extract TUSS/SIGTAP procedure codes (XX.XX.XX.XXX-X or 9-digit)."""
        dotted = _RE_PROC_CODE.findall(text)
        nine_digit = _RE_PROC_CODE_9DIGIT.findall(text)
        return dotted + nine_digit

    def parse_currency(self, text: str) -> List[float]:
        """Extract BRL currency values. R$ 1.234,56 -> 1234.56."""
        return [_br_currency_to_float(m) for m in _RE_CURRENCY.findall(text)]

    def parse_percentages(self, text: str) -> List[float]:
        """Extract percentage values. '5%' -> 5.0."""
        return [float(v.replace(",", ".")) for v in _RE_PERCENTAGE.findall(text)]

    def parse_quantities(self, text: str) -> List[int]:
        """Extract quantity limits. 'limitado a 3' -> 3."""
        return [int(v) for v in _RE_QUANTITY.findall(text)]

    def parse_payer_ids(self, text: str) -> List[str]:
        """Extract payer IDs (SES-XX, SES/XX, or ANS-XXXXXX)."""
        return _RE_PAYER.findall(text)

    def parse_time_windows(self, text: str) -> List[int]:
        """Extract time windows in hours. '72h' -> 72, '24 horas' -> 24."""
        return [int(v) for v in _RE_TIME_WINDOW.findall(text)]

    def parse_deadline_days(self, text: str) -> List[int]:
        """Extract deadline in days. 'até 30 dias' -> 30."""
        return [int(v) for v in _RE_DEADLINE_DAYS.findall(text)]
