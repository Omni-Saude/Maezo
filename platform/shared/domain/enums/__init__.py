"""Domain enums for Healthcare Orchestration Platform."""
from __future__ import annotations
from enum import StrEnum, unique

from platform.shared.i18n import _

# -- Coverage / Insurance --
@unique
class CoverageStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    DRAFT = "draft"
    ENTERED_IN_ERROR = "entered-in-error"
    SUSPENDED = "suspended"  # ANS carência

@unique
class CoverageType(StrEnum):
    INDIVIDUAL = "individual"
    CORPORATE = "corporate"
    ADHESION = "adhesion"  # adesão
    COLLECTIVE = "collective"
    SUS = "sus"

# -- Billing --
@unique
class BillingStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CODED = "coded"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    DENIED = "denied"
    APPEALED = "appealed"
    WRITTEN_OFF = "written_off"
    CANCELLED = "cancelled"

# -- Glosa (Denial) --
@unique
class GlosaType(StrEnum):
    ADMINISTRATIVE = "administrative"  # Glosa administrativa
    TECHNICAL = "technical"           # Glosa técnica
    LINEAR = "linear"                 # Glosa linear (cut %)
    TOTAL = "total"                   # Glosa total
    PARTIAL = "partial"              # Glosa parcial

@unique
class GlosaReasonCode(StrEnum):
    MISSING_AUTH = "GLOSA_001"          # Autorização ausente
    EXPIRED_AUTH = "GLOSA_002"          # Autorização vencida
    DUPLICATE_CHARGE = "GLOSA_003"      # Cobrança duplicada
    EXCEEDS_QUANTITY = "GLOSA_004"      # Quantidade excedida
    NOT_COVERED = "GLOSA_005"           # Procedimento não coberto
    WRONG_CODE = "GLOSA_006"            # Código incorreto
    MISSING_DOCUMENTATION = "GLOSA_007" # Documentação ausente
    INCOMPATIBLE_PROCEDURE = "GLOSA_008"# Procedimento incompatível
    PRICE_DIVERGENCE = "GLOSA_009"      # Divergência de preço
    TISS_VALIDATION = "GLOSA_010"       # Falha validação TISS

# -- Authorization --
@unique
class AuthorizationStatus(StrEnum):
    REQUESTED = "requested"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXTENDED = "extended"

# -- Encounter --
@unique
class EncounterStatus(StrEnum):
    PLANNED = "planned"
    ARRIVED = "arrived"
    TRIAGED = "triaged"
    IN_PROGRESS = "in-progress"
    ON_LEAVE = "onleave"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered-in-error"

@unique
class EncounterClass(StrEnum):
    AMBULATORY = "AMB"
    EMERGENCY = "EMER"
    INPATIENT = "IMP"
    SHORT_STAY = "SS"
    HOME_HEALTH = "HH"
    OBSERVATION = "OBSENC"
    DAY_HOSPITAL = "DH"      # Hospital-dia (Brazilian)

# -- Claim --
@unique
class ClaimStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered-in-error"

@unique
class ClaimUse(StrEnum):
    CLAIM = "claim"
    PREAUTHORIZATION = "preauthorization"
    PREDETERMINATION = "predetermination"

# -- TISS (Brazilian standard) --
@unique
class TISSGuideType(StrEnum):
    SP_SADT = "sp_sadt"                 # Guia SP/SADT
    CONSULTATION = "consultation"        # Guia de Consulta
    ADMISSION = "admission"              # Guia de Internação
    EXTENSION = "extension"              # Guia de Prorrogação
    HONORARIOS = "honorarios"            # Guia de Honorários
    SUMMARY = "summary"                  # Resumo de Internação

# -- Tenant --
@unique
class TenantCode(StrEnum):
    AUSTA = "AUSTA"
    AMH_SP = "AMH-SP"
    AMH_RJ = "AMH-RJ"
    AMH_MG = "AMH-MG"
