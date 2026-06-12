"""
PII Redaction Rules - Brazilian Healthcare Data (LGPD Compliance).

ADR-011: All logs MUST redact PII before storage/transmission.
Patterns: CPF, email, phone, patient names, RG, CNS (Cartao Nacional de Saude).
"""

from __future__ import annotations

import re
from typing import Any



# Compiled regex patterns for performance
_PATTERNS: dict[str, re.Pattern] = {
    "cpf": re.compile(
        r"\b(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-.\s]?(\d{2})\b"
    ),
    "cnpj": re.compile(
        r"\b(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[/\s]?(\d{4})[-.\s]?(\d{2})\b"
    ),
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),
    "phone_br": re.compile(
        r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?\d{4,5}[-.\s]?\d{4}\b"
    ),
    "cns": re.compile(
        r"\b\d{3}\s?\d{4}\s?\d{4}\s?\d{4}\b"
    ),
    "rg": re.compile(
        r"\b(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[-.\s]?(\d{1})\b"
    ),
    "credit_card": re.compile(
        r"\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b"
    ),
    "date_of_birth": re.compile(
        r"\b(\d{2})[/\-](\d{2})[/\-](\d{4})\b"
    ),
}

_REDACTION_MAP: dict[str, str] = {
    "cpf": "***.***.***-**",
    "cnpj": "**.***.***/****..**",
    "email": "***@***.***",
    "phone_br": "(XX) XXXXX-XXXX",
    "cns": "*** **** **** ****",
    "rg": "**.***.***-*",
    "credit_card": "****-****-****-****",
    "date_of_birth": "**/**/****",
}


class PIIRedactor:
    """Redacts PII from strings, dicts, and log records.

    Thread-safe, stateless. Instantiate once and reuse.
    """

    def __init__(
        self,
        extra_patterns: dict[str, tuple[re.Pattern, str]] | None = None,
    ) -> None:
        self._patterns = dict(_PATTERNS)
        self._replacements = dict(_REDACTION_MAP)
        if extra_patterns:
            for name, (pattern, replacement) in extra_patterns.items():
                self._patterns[name] = pattern
                self._replacements[name] = replacement

    def redact_string(self, text: str) -> str:
        """Redact all known PII patterns from a string."""
        if not isinstance(text, str):
            return text
        result = text
        for name, pattern in self._patterns.items():
            result = pattern.sub(self._replacements[name], result)
        return result

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact PII from dict values."""
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                redacted[key] = self.redact_string(value)
            elif isinstance(value, dict):
                redacted[key] = self.redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self.redact_string(v) if isinstance(v, str)
                    else self.redact_dict(v) if isinstance(v, dict)
                    else v
                    for v in value
                ]
            else:
                redacted[key] = value
        return redacted

    def __call__(self, text: str) -> str:
        """Shorthand for redact_string."""
        return self.redact_string(text)


# Module-level singleton
_default_redactor = PIIRedactor()


def redact(text: str) -> str:
    """Redact PII from text using the default redactor."""
    return _default_redactor.redact_string(text)


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Redact PII from dict using the default redactor."""
    return _default_redactor.redact_dict(data)
