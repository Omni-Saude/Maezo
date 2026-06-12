"""Tenant-aware credential management (ADR-020).

Workers autenticam no CIB Seven via Basic Auth (CIB7_USER / CIB7_PASSWORD).
Multi-tenancy é mantido via path /tenant-id/{id} — sem necessidade de
credenciais por tenant.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceCredentials:
    """Basic Auth credentials for CIB Seven engine (ADR-020)."""

    user: str
    password: str


def get_service_credentials() -> ServiceCredentials:
    """Load CIB Seven Basic Auth credentials from environment variables."""
    return ServiceCredentials(
        user=os.getenv("CIB7_USER", "admin"),
        password=os.getenv("CIB7_PASSWORD", ""),
    )
