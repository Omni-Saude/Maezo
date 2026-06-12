"""Generic archetype-specific worker implementations.

Provides base class, concrete archetype implementations, and registry loading
for DMN-driven workers organized by business archetype.

Archetypes
----------
ADMIN_ADJUDICATION    Authorization, eligibility, claims adjudication
CLINICAL_ALERT        Sepsis, NEWS2, critical thresholds (immediate escalation)
CLINICAL_SCORE        Risk scores, SOFA, qSOFA (diagnostic, non-blocking)
OPERATIONAL_ROUTING   Triage, bed allocation, staff assignment
COMPLIANCE_VALIDATION LGPD, audit trail, documentation integrity
FINANCIAL_CALCULATION Pricing, denial analysis, revenue impact
DATA_ENRICHMENT       FHIR normalization, data quality enhancement
"""

from healthcare_platform.shared.workers.generic.base_generic import (
    ACTION_PRIORITY,
    GenericWorkerBase,
    GenericWorkerConfigError,
)
from healthcare_platform.shared.workers.generic.registry_loader import (
    RegistryValidationError,
    get_topic_config,
    load_registry,
)
from healthcare_platform.shared.workers.generic.admin_adjudication import GenericAdminAdjudicationWorker
from healthcare_platform.shared.workers.generic.clinical_alert import GenericClinicalAlertWorker
from healthcare_platform.shared.workers.generic.clinical_score import GenericClinicalScoreWorker
from healthcare_platform.shared.workers.generic.operational_routing import GenericOperationalRoutingWorker
from healthcare_platform.shared.workers.generic.compliance_validation import GenericComplianceValidationWorker
from healthcare_platform.shared.workers.generic.financial_calculation import GenericFinancialCalculationWorker
from healthcare_platform.shared.workers.generic.data_enrichment import GenericDataEnrichmentWorker

# Archetype name constants — use these in registry_config["archetype"]
ARCHETYPE_ADMIN_ADJUDICATION = "ADMIN_ADJUDICATION"
ARCHETYPE_CLINICAL_ALERT = "CLINICAL_ALERT"
ARCHETYPE_CLINICAL_SCORE = "CLINICAL_SCORE"
ARCHETYPE_OPERATIONAL_ROUTING = "OPERATIONAL_ROUTING"
ARCHETYPE_COMPLIANCE_VALIDATION = "COMPLIANCE_VALIDATION"
ARCHETYPE_FINANCIAL_CALCULATION = "FINANCIAL_CALCULATION"
ARCHETYPE_DATA_ENRICHMENT = "DATA_ENRICHMENT"

__all__ = [
    # Base class and exceptions
    "GenericWorkerBase",
    "GenericWorkerConfigError",
    "ACTION_PRIORITY",
    # Registry loader
    "load_registry",
    "get_topic_config",
    "RegistryValidationError",
    # Concrete archetype workers
    "GenericAdminAdjudicationWorker",
    "GenericClinicalAlertWorker",
    "GenericClinicalScoreWorker",
    "GenericOperationalRoutingWorker",
    "GenericComplianceValidationWorker",
    "GenericFinancialCalculationWorker",
    "GenericDataEnrichmentWorker",
    # Archetype constants
    "ARCHETYPE_ADMIN_ADJUDICATION",
    "ARCHETYPE_CLINICAL_ALERT",
    "ARCHETYPE_CLINICAL_SCORE",
    "ARCHETYPE_OPERATIONAL_ROUTING",
    "ARCHETYPE_COMPLIANCE_VALIDATION",
    "ARCHETYPE_FINANCIAL_CALCULATION",
    "ARCHETYPE_DATA_ENRICHMENT",
]
