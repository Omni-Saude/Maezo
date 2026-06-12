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
    TasyPricingAdapter: Brasindice/SIMPRO -> FHIR pricing data
    TasyPaymentAdapter: PAGAMENTO -> FHIR Payment
    TasyInsuranceAuthAdapter: AUTORIZACAO -> FHIR CoverageEligibilityRequest
    TasyGlosaAdapter: GLOSA -> FHIR ClaimResponse (RC-GAP-3)
    TasySurgicalAdapter: REGISTRO_CIRURGICO -> FHIR Procedure (Wave 3.6)
    TasyClaimAdapter: CONTA_MEDICA -> FHIR Claim with TUSS/CBHPM/CID-10 (Wave 3.7b)
    TasyClaimResponseAdapter: GLOSA -> FHIR ClaimResponse with ANS codes (Wave 3.7b)
    TasyObservationAdapter: Vitals/Lab -> FHIR Observation with LOINC (Wave 3.7b)
    TasyMedicationRequestAdapter: PRESCRICAO -> FHIR MedicationRequest with ANVISA (Wave 3.7b)
    TasyMedicationDispenseAdapter: DISPENSACAO -> FHIR MedicationDispense (Wave 6.1)
    TasyPharmacyInventoryAdapter: ESTOQUE_FARMACIA -> FHIR SupplyDelivery (Wave 6.1)
    TasyDrugInteractionAdapter: INTERACAO_MEDICAMENTOSA -> FHIR DetectedIssue (Wave 6.1)

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
from healthcare_platform.shared.integrations.tasy_adapters.pricing_adapter import (
    TasyPricingAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.payment_adapter import (
    TasyPaymentAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.insurance_auth_adapter import (
    TasyInsuranceAuthAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.glosa_adapter import (
    TasyGlosaAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.scoring_adapter import (
    TasyScoringAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.claim_adapter import (
    TasyClaimAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.claim_response_adapter import (
    TasyClaimResponseAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.observation_adapter import (
    TasyObservationAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.medication_request_adapter import (
    TasyMedicationRequestAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.medication_dispense_adapter import (
    TasyMedicationDispenseAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.pharmacy_inventory_adapter import (
    TasyPharmacyInventoryAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.drug_interaction_adapter import (
    TasyDrugInteractionAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.organization_adapter import (
    TasyOrganizationAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.procedure_adapter import (
    TasyProcedureAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.authorization_adapter import (
    TasyAuthorizationAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.practitioner_adapter import (
    TasyPractitionerAdapter,
)
from healthcare_platform.shared.integrations.tasy_adapters.condition_adapter import (
    TasyConditionAdapter,
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
    "TasyPricingAdapter",
    "TasyPaymentAdapter",
    "TasyInsuranceAuthAdapter",
    "TasyGlosaAdapter",
    "TasyScoringAdapter",
    "TasySurgicalAdapter",
    "TasyClaimAdapter",
    "TasyClaimResponseAdapter",
    "TasyObservationAdapter",
    "TasyMedicationRequestAdapter",
    "TasyMedicationDispenseAdapter",
    "TasyPharmacyInventoryAdapter",
    "TasyDrugInteractionAdapter",
    "TasyOrganizationAdapter",
    "TasyProcedureAdapter",
    "TasyAuthorizationAdapter",
    "TasyPractitionerAdapter",
    "TasyConditionAdapter",
]
