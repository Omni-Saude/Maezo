"""Tasy to FHIR R4 adapters for healthcare integration.

This package provides adapters that convert Tasy JSON responses to FHIR R4 resources,
enabling standardized data exchange per ADR-005.

Available adapters:
    TasyPatientAdapter: PACIENTE table -> FHIR Patient
    TasyCoverageAdapter: CONVENIO_PACIENTE -> FHIR Coverage
    TasyEncounterAdapter: ATENDIMENTO -> FHIR Encounter
    TasyBillingAdapter: CONTA_MEDICA + ITEM_CONTA -> FHIR Claim
    TasyPrescriptionAdapter: PRESCRICAO -> FHIR MedicationRequest
    TasyVitalSignsAdapter: SINAL_VITAL -> FHIR Observation

Usage:
    from healthcare_platform.shared.integrations.tasy_adapters import TasyPatientAdapter
    from healthcare_platform.shared.integrations.fhir_client import FHIRClient

    fhir_client = FHIRClient(base_url="https://fhir.example.org/fhir")
    adapter = TasyPatientAdapter(fhir_client=fhir_client, tenant_id="hospital-a")

    tasy_data = {"NR_PACIENTE": "123456", "NM_PACIENTE": "João Silva", ...}
    fhir_patient = await adapter.adapt(tasy_data)
"""

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
    TasyToFhirAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.billing_adapter import (
    TasyBillingAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.coverage_adapter import (
    TasyCoverageAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.encounter_adapter import (
    TasyEncounterAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.patient_adapter import (
    TasyPatientAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.prescription_adapter import (
    TasyPrescriptionAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.vital_signs_adapter import (
    TasyVitalSignsAdapter,
)

__all__ = [
    "TasyToFhirAdapter",
    "BaseTasyFhirAdapter",
    "TasyPatientAdapter",
    "TasyCoverageAdapter",
    "TasyEncounterAdapter",
    "TasyBillingAdapter",
    "TasyPrescriptionAdapter",
    "TasyVitalSignsAdapter",
]
