"""Test fixtures for Healthcare-Orchest-CIB7."""

from __future__ import annotations

from .tenant_fixtures import (
    TENANT_AUSTA,
    TENANT_AMH_SP,
    tenant_configuration,
)
from .patient_fixtures import (
    PATIENT_VALID,
    PATIENT_INVALID_CPF,
    PATIENT_MISSING_FIELDS,
    PATIENT_WITH_CNS,
    PATIENT_PEDIATRIC,
    PATIENT_GERIATRIC,
    PATIENT_NEWBORN,
    PATIENT_FOREIGN,
)
from .appointment_fixtures import (
    APPOINTMENT_CONSULTATION,
    APPOINTMENT_SURGICAL,
    APPOINTMENT_DIAGNOSTIC,
    APPOINTMENT_FOLLOW_UP,
    APPOINTMENT_CANCELLED,
    APPOINTMENT_RESCHEDULED,
    SLOT_AVAILABLE,
    PRACTITIONER_GENERAL,
)
from .billing_fixtures import (
    INVOICE_SUS,
    INVOICE_AMB,
    CONTRACT_RULE_SUS,
    CONTRACT_RULE_CBHPM,
    BILLING_INPUT_CONSULTATION,
    BILLING_INPUT_SURGICAL,
    GLOSA_SAMPLE,
)
from .dmn_fixtures import (
    DMN_INPUT_BILLING,
    DMN_INPUT_CLINICAL,
    DMN_INPUT_CODING,
    DMN_INPUT_GLOSA,
    DMN_INPUT_ACCESS_CONTROL,
    DMN_INPUT_NULL_VALUES,
    DMN_INPUT_BOUNDARY,
)
from .engine_fixtures import (
    EXTERNAL_TASK_SAMPLE,
    PROCESS_INSTANCE_SAMPLE,
    VARIABLE_MAP_SAMPLE,
)
from .fhir_seed import (
    FHIRSeedData,
    create_rc_seed,
    get_rc_resources,
    build_bundle,
    HAPPY_PATH_IDS,
    AUTH_DENIED_IDS,
    GLOSA_DENIAL_IDS,
    OVERDUE_COLLECTION_IDS,
    RESUBMIT_APPROVED_IDS,
)

__all__ = [
    # Tenant fixtures
    "TENANT_AUSTA",
    "TENANT_AMH_SP",
    "tenant_configuration",
    # Patient fixtures
    "PATIENT_VALID",
    "PATIENT_INVALID_CPF",
    "PATIENT_MISSING_FIELDS",
    "PATIENT_WITH_CNS",
    "PATIENT_PEDIATRIC",
    "PATIENT_GERIATRIC",
    "PATIENT_NEWBORN",
    "PATIENT_FOREIGN",
    # Appointment fixtures
    "APPOINTMENT_CONSULTATION",
    "APPOINTMENT_SURGICAL",
    "APPOINTMENT_DIAGNOSTIC",
    "APPOINTMENT_FOLLOW_UP",
    "APPOINTMENT_CANCELLED",
    "APPOINTMENT_RESCHEDULED",
    "SLOT_AVAILABLE",
    "PRACTITIONER_GENERAL",
    # Billing fixtures
    "INVOICE_SUS",
    "INVOICE_AMB",
    "CONTRACT_RULE_SUS",
    "CONTRACT_RULE_CBHPM",
    "BILLING_INPUT_CONSULTATION",
    "BILLING_INPUT_SURGICAL",
    "GLOSA_SAMPLE",
    # DMN fixtures
    "DMN_INPUT_BILLING",
    "DMN_INPUT_CLINICAL",
    "DMN_INPUT_CODING",
    "DMN_INPUT_GLOSA",
    "DMN_INPUT_ACCESS_CONTROL",
    "DMN_INPUT_NULL_VALUES",
    "DMN_INPUT_BOUNDARY",
    # Engine fixtures
    "EXTERNAL_TASK_SAMPLE",
    "PROCESS_INSTANCE_SAMPLE",
    "VARIABLE_MAP_SAMPLE",
    # FHIR seed
    "FHIRSeedData",
    "create_rc_seed",
    "get_rc_resources",
    "build_bundle",
    "HAPPY_PATH_IDS",
    "AUTH_DENIED_IDS",
    "GLOSA_DENIAL_IDS",
    "OVERDUE_COLLECTION_IDS",
    "RESUBMIT_APPROVED_IDS",
]
