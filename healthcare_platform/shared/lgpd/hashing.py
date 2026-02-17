"""
LGPD Hashing Module
Provides LGPD-compliant hashing for PII fields.
"""
from __future__ import annotations

import hashlib


class LGPDHasher:
    """
    LGPD-compliant hasher for PII fields.
    
    Uses SHA-256 with field-specific salts for deterministic,
    one-way hashing of sensitive data (CPF, RG, phone, etc.)
    """

    def __init__(self, salt_prefix: str = "lgpd_"):
        self.salt_prefix = salt_prefix

    def hash(self, value: str, field_name: str) -> str:
        """
        Hash a PII value with field-specific salt.
        
        Args:
            value: PII value to hash
            field_name: Field name for salt derivation
            
        Returns:
            Hexadecimal hash string
        """
        salted = f"{self.salt_prefix}{field_name}:{value}"
        return hashlib.sha256(salted.encode()).hexdigest()
