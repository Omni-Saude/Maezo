from __future__ import annotations

"""Tenant fixtures para testes."""

from typing import Dict, Any
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.multi_tenant.context import TenantContext


TENANT_AUSTA: Dict[str, Any] = {
    "tenant_id": "austa-001",
    "tenant_code": TenantCode.HOSPITAL_A,
    "name": "AUSTA Hospital",
    "database_config": {
        "host": "localhost",
        "port": 5432,
        "database": "austa_db",
        "schema": "austa",
    },
    "fhir_base_url": "http://fhir.austa.local/fhir/r4",
    "erp_integration": {
        "system": "TASY",
        "base_url": "http://tasy.austa.local/api",
        "tenant_code": "HOSPITAL_A",
    },
    "insurance_types": ["SUS", "AMB", "CBHPM", "PRIVATE"],
    "features": {
        "whatsapp_notifications": True,
        "ai_medical_coding": True,
        "automatic_billing": True,
        "glosa_prevention": True,
    },
    "business_rules": {
        "appointment_advance_days": 30,
        "cancellation_hours": 24,
        "rescheduling_allowed": True,
        "max_reschedules": 2,
    },
}

TENANT_AMH_SP: Dict[str, Any] = {
    "tenant_id": "hpa-001",
    "tenant_code": TenantCode.AMH_SP,
    "name": "HPA Saúde",
    "database_config": {
        "host": "localhost",
        "port": 5432,
        "database": "hpa_db",
        "schema": "hpa",
    },
    "fhir_base_url": "http://fhir.hpa.local/fhir/r4",
    "erp_integration": {
        "system": "MV_SOUL",
        "base_url": "http://mvsoul.hpa.local/api",
        "tenant_code": "HPA",
    },
    "insurance_types": ["SUS", "UNIMED", "BRADESCO", "PRIVATE"],
    "features": {
        "whatsapp_notifications": True,
        "ai_medical_coding": False,
        "automatic_billing": True,
        "glosa_prevention": True,
    },
    "business_rules": {
        "appointment_advance_days": 60,
        "cancellation_hours": 48,
        "rescheduling_allowed": True,
        "max_reschedules": 3,
    },
}


def tenant_configuration(
    tenant_code: TenantCode,
    overrides: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """
    Factory function para criar configurações de tenant com overrides.

    Args:
        tenant_code: Código do tenant (AUSTA ou HPA)
        overrides: Dicionário com valores a sobrescrever

    Returns:
        Configuração completa do tenant

    Example:
        >>> config = tenant_configuration(
        ...     TenantCode.HOSPITAL_A,
        ...     {"features": {"whatsapp_notifications": False}}
        ... )
    """
    base_config = TENANT_AUSTA.copy() if tenant_code == TenantCode.HOSPITAL_A else TENANT_AMH_SP.copy()

    if overrides:
        # Deep merge of overrides
        for key, value in overrides.items():
            if isinstance(value, dict) and key in base_config:
                base_config[key] = {**base_config[key], **value}
            else:
                base_config[key] = value

    return base_config
