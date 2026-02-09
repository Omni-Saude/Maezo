"""
Credential redaction processor for structlog.

Implements comprehensive redaction of sensitive data in logs to prevent
credential leakage. Uses pattern-based matching and recursive traversal
of nested data structures.

Features:
- Pattern-based redaction (passwords, tokens, API keys, credentials)
- Recursive redaction of nested dictionaries and lists
- Exception message redaction to prevent traceback leaks
- SecretStr value redaction
- Configurable redaction patterns
- Performance-optimized with caching

Security:
- All credentials redacted with [REDACTED] placeholder
- Exception messages sanitized before logging
- Traceback messages scanned for credentials
- Safe handling of various data types
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Pattern

# Credential redaction patterns - matches common credential formats
REDACTION_PATTERNS: list[tuple[str, Pattern[str]]] = [
    # API Keys and tokens
    ("api_key", re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("api_token", re.compile(r"api[_-]?token[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # Passwords
    ("password", re.compile(r"password[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("pwd", re.compile(r"pwd[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("passwd", re.compile(r"passwd[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # Tokens and secrets
    ("token", re.compile(r"token[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("secret", re.compile(r"secret[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("access_token", re.compile(r"access[_-]?token[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("refresh_token", re.compile(r"refresh[_-]?token[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # Credentials
    ("credential", re.compile(r"credential[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("credentials", re.compile(r"credentials[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # Authorization headers
    ("bearer_token", re.compile(r"Bearer\s+([a-zA-Z0-9\-._~+/]+=*)", re.IGNORECASE)),
    ("basic_auth", re.compile(r"Basic\s+([a-zA-Z0-9+/]+=*)", re.IGNORECASE)),

    # AWS credentials
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret", re.compile(r"aws[_-]?secret[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # OpenAI and other AI provider keys
    ("openai_key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[a-zA-Z0-9]{20,}")),

    # GitHub tokens
    ("github_token", re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    ("github_app_token", re.compile(r"ghu_[a-zA-Z0-9]{36}")),

    # GitLab tokens
    ("gitlab_token", re.compile(r"glpat-[a-zA-Z0-9\-_]{20,}")),

    # Database connection strings and credentials
    ("db_password", re.compile(r"(?:mongodb|postgres|mysql|redis)://[^:]+:([^@]+)@", re.IGNORECASE)),
    ("connection_string", re.compile(r"(?:Server|Host|Password|User ID)=([^;,\s]+)", re.IGNORECASE)),

    # Private keys (PEM format)
    ("private_key", re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP).*?PRIVATE KEY.*?-----", re.IGNORECASE | re.DOTALL)),

    # Cloud provider credentials
    ("azure_key", re.compile(r"(?:AZURE|Azure)[_-]?[a-zA-Z]+[_-]?[a-zA-Z]*[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("gcp_key", re.compile(r"(?:GOOGLE|GCP)[_-]?[a-zA-Z]+[_-]?[a-zA-Z]*[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # OAuth credentials
    ("oauth_token", re.compile(r"oauth[_-]?token[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("client_secret", re.compile(r"client[_-]?secret[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("client_id", re.compile(r"client[_-]?id[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # SSO/SAML credentials
    ("saml_assertion", re.compile(r"SAMLResponse[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # JWT tokens
    ("jwt_token", re.compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*")),

    # Vault tokens
    ("vault_token", re.compile(r"vault[_-]?token[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),
    ("vault_secret", re.compile(r"vault[_-]?secret[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]+)", re.IGNORECASE)),

    # Generic secret/key patterns
    ("generic_secret", re.compile(r"(?:secret|key)[_-]?[a-zA-Z]*[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}\n]{8,})", re.IGNORECASE)),
]

# Sensitive field names - redact values without pattern matching
SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "bearer_token",
    "auth_token",
    "api_token",
    "session_token",
    "jwt",
    "jwt_token",
    "credential",
    "credentials",
    "client_secret",
    "client_id",
    "oauth_token",
    "oauth_secret",
    "saml_response",
    "saml_assertion",
    "private_key",
    "signing_key",
    "encryption_key",
    "vault_token",
    "vault_secret",
    "aws_access_key",
    "aws_secret_key",
    "azure_key",
    "gcp_key",
    "github_token",
    "gitlab_token",
    "authorization",
    "x_api_key",
    "x-api-key",
    "api-key",
    "apitoken",
}

# Field name pattern for case-insensitive matching
SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?:" + "|".join(re.escape(name) for name in SENSITIVE_FIELD_NAMES) + r")$",
    re.IGNORECASE,
)

REDACTION_PLACEHOLDER = "[REDACTED]"


@lru_cache(maxsize=1024)
def _is_sensitive_field(field_name: str) -> bool:
    """Check if field name indicates sensitive data."""
    if not isinstance(field_name, str):
        return False
    return SENSITIVE_FIELD_PATTERN.match(field_name) is not None


def _redact_string(value: str) -> str:
    """
    Redact sensitive data from a string using pattern matching.

    Args:
        value: String that may contain credentials

    Returns:
        String with credentials replaced by [REDACTED]
    """
    if not isinstance(value, str) or not value:
        return value

    result = value

    # Apply all patterns
    for name, pattern in REDACTION_PATTERNS:
        result = pattern.sub(lambda m: REDACTION_PLACEHOLDER, result)

    return result


def _redact_value(value: Any) -> Any:
    """
    Redact a single value if it contains sensitive data.

    Args:
        value: Value to potentially redact

    Returns:
        Redacted value or original value
    """
    if isinstance(value, str):
        return _redact_string(value)

    # Handle SecretStr from pydantic
    if hasattr(value, "get_secret_value"):
        # This is a SecretStr - always redact
        return REDACTION_PLACEHOLDER

    return value


def _redact_recursive(data: Any, depth: int = 0, max_depth: int = 10) -> Any:
    """
    Recursively redact sensitive data from nested structures.

    Args:
        data: Data structure to redact
        depth: Current recursion depth
        max_depth: Maximum recursion depth to prevent stack overflow

    Returns:
        Redacted data structure
    """
    # Prevent infinite recursion
    if depth > max_depth:
        return data

    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            # If field name is sensitive, redact the value
            if _is_sensitive_field(key):
                redacted[key] = REDACTION_PLACEHOLDER
            # Otherwise recursively redact the value
            else:
                redacted[key] = _redact_recursive(value, depth + 1, max_depth)
        return redacted

    elif isinstance(data, (list, tuple)):
        redacted = [_redact_recursive(item, depth + 1, max_depth) for item in data]
        return type(data)(redacted) if isinstance(data, tuple) else redacted

    elif isinstance(data, str):
        return _redact_string(data)

    elif hasattr(data, "get_secret_value"):
        # Pydantic SecretStr
        return REDACTION_PLACEHOLDER

    else:
        return data


class RedactionProcessor:
    """
    Structlog processor that redacts sensitive data from log records.

    This processor should be added early in the processor chain to redact
    credentials before they are formatted and output.

    Usage:
        processors = [
            RedactionProcessor(),
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    """

    def __init__(self, max_depth: int = 10):
        """
        Initialize the redaction processor.

        Args:
            max_depth: Maximum recursion depth for nested structures
        """
        self.max_depth = max_depth

    def __call__(self, logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Process a log record and redact sensitive data.

        Args:
            logger: The structlog logger
            method_name: The name of the method called (debug, info, error, etc.)
            event_dict: The event dictionary

        Returns:
            Redacted event dictionary
        """
        # Redact all fields in the event dictionary
        redacted = {}
        for key, value in event_dict.items():
            # Redact field value based on name or content
            if _is_sensitive_field(key):
                # Field name indicates sensitive data
                redacted[key] = REDACTION_PLACEHOLDER
            else:
                # Recursively redact the value
                redacted[key] = _redact_recursive(value, max_depth=self.max_depth)

        return redacted


def redact_exception_message(exception: Exception) -> str:
    """
    Redact sensitive data from an exception message.

    Args:
        exception: The exception to redact

    Returns:
        Redacted exception message
    """
    message = str(exception)
    return _redact_string(message)


def should_redact_field(field_name: str) -> bool:
    """
    Check if a field should be redacted based on its name.

    Args:
        field_name: Name of the field

    Returns:
        True if the field should be redacted
    """
    return _is_sensitive_field(field_name)


def redact_for_logging(value: Any) -> Any:
    """
    Redact a value for safe logging.

    This is a public API for manual redaction of values before logging.

    Args:
        value: Value to redact

    Returns:
        Redacted value or [REDACTED] if sensitive
    """
    return _redact_recursive(value, max_depth=10)
