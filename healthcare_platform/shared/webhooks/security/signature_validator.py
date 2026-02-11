"""Signature validation for webhook payloads (ADR-014).

Supports HMAC-SHA256 (TASY, WhatsApp), RSA (PIX), and API key (Payers).
Uses constant-time comparison to prevent timing attacks.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils

from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class SignatureValidationError(Exception):
    """Raised when webhook signature validation fails."""


class SignatureValidator:
    """Validates webhook payload signatures using multiple algorithms."""

    @staticmethod
    def validate_hmac_sha256(
        payload: bytes, signature: str, secret: str
    ) -> bool:
        """Validate HMAC-SHA256 signature (TASY TIE, WhatsApp).

        Args:
            payload: Raw request body bytes.
            signature: Hex-encoded HMAC signature from header.
            secret: Shared secret key.

        Returns:
            True if signature is valid.

        Raises:
            SignatureValidationError: If signature does not match.
        """
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Strip common prefixes like "sha256="
        sig_value = signature.removeprefix("sha256=")

        if not hmac.compare_digest(expected, sig_value):
            logger.warning("HMAC-SHA256 signature mismatch")
            raise SignatureValidationError("Invalid HMAC-SHA256 signature")

        return True

    @staticmethod
    def validate_rsa(
        payload: bytes, signature: bytes, cert_path: str
    ) -> bool:
        """Validate RSA-SHA256 signature (PIX/Banco Central).

        Args:
            payload: Raw request body bytes.
            signature: DER-encoded RSA signature.
            cert_path: Path to PEM public certificate.

        Returns:
            True if signature is valid.

        Raises:
            SignatureValidationError: If signature does not match or cert is invalid.
        """
        try:
            cert_data = Path(cert_path).read_bytes()
            public_key = serialization.load_pem_public_key(cert_data)
            # SHA-256 digest
            digest = hashlib.sha256(payload).digest()
            public_key.verify(  # type: ignore[union-attr]
                signature,
                digest,
                padding.PKCS1v15(),  # type: ignore[arg-type]
                utils.Prehashed(hashes.SHA256()),
            )
        except InvalidSignature:
            logger.warning("RSA signature mismatch")
            raise SignatureValidationError("Invalid RSA signature")
        except (OSError, ValueError) as exc:
            logger.error("Certificate error", error=str(exc))
            raise SignatureValidationError(f"Certificate error: {exc}") from exc

        return True

    @staticmethod
    def validate_api_key(api_key: str, valid_keys: dict[str, str]) -> str:
        """Validate API key for payer callbacks.

        Args:
            api_key: API key from request header.
            valid_keys: Mapping of payer_id → api_key.

        Returns:
            The payer_id associated with the key.

        Raises:
            SignatureValidationError: If API key is not recognized.
        """
        for payer_id, expected_key in valid_keys.items():
            if hmac.compare_digest(api_key, expected_key):
                return payer_id

        logger.warning("Unknown API key presented")
        raise SignatureValidationError("Invalid API key")
