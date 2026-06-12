"""FHIR R4 seed data factory para Revenue Cycle — MAEZO.

Fornece:
  FHIRSeedData       — dataclass com IDs de todos os recursos de um cenário
  create_rc_seed()   — fábrica async que popula StubFHIRClient
  get_rc_resources() — lista de recursos em ordem topológica (para PUT no HAPI FHIR)
  build_bundle()     — FHIR transaction Bundle para POST direto no HAPI FHIR
  HAPPY_PATH_IDS, AUTH_DENIED_IDS, GLOSA_DENIAL_IDS, OVERDUE_COLLECTION_IDS

Cenários:
  happy_path          — fluxo RC completo aprovado, pagamento recebido
  auth_denied         — autorização negada em RC-002, sem encounter/procedure
  glosa_denial        — glosa parcial em RC-007, sem pagamento
  overdue_collection  — 3 contas em atraso para RC-009
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Sistemas de nomenclatura FHIR ---
TENANT_TAG_SYSTEM = "http://maezo.austa.com.br/fhir/tenant"
_CPF     = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf"
_CNS     = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns"
_MRN     = "http://tasy.com/fhir/identifier/mrn"
_CNES    = "http://www.saude.gov.br/fhir/r4/NamingSystem/cnes"
_CRM     = "http://www.saude.gov.br/fhir/r4/NamingSystem/crm"
_ANS     = "http://www.ans.gov.br/fhir/NamingSystem/registroANS"
_TUSS    = "http://www.ans.gov.br/tiss/procedimentos"
_CBHPM   = "http://www.cbhpm.com.br/procedimentos"
_ICD10   = "http://hl7.org/fhir/sid/icd-10"
_NF      = "http://tasy.com/fhir/identifier/nota-fiscal"
_ATEND   = "http://tasy.com/fhir/identifier/atendimento"

_TENANT_SLUGS: dict[str, str] = {
    "austa-hospital":  "austa",
    "amh-sp-morumbi":  "amh-sp",
    "amh-rj-barra":    "amh-rj",
    "amh-mg-bh":       "amh-mg",
}

# ---------------------------------------------------------------------------
# Dicionários de IDs por cenário
# ---------------------------------------------------------------------------

HAPPY_PATH_IDS: dict[str, str] = {
    "org_payer":    "rc-org-payer-bradesco",
    "patient":      "rc-patient-happy-001",
    "coverage":     "rc-coverage-happy-001",
    "appointment":  "rc-appt-happy-001",
    "sr":           "rc-sr-happy-001",
    "cer":          "rc-cer-happy-001",
    "ceres":        "rc-ceres-happy-001",
    "encounter":    "rc-encounter-happy-001",
    "procedure":    "rc-procedure-happy-001",
    "claim":        "rc-claim-happy-001",
    "cr":           "rc-claimresponse-happy-001",
    "account":      "rc-account-happy-001",
    "ci":           "rc-chargeitem-happy-001",
    "invoice":      "rc-invoice-happy-001",
    "pn":           "rc-paynotice-happy-001",
}

AUTH_DENIED_IDS: dict[str, str] = {
    "org_payer":    "rc-org-payer-unimed",
    "patient":      "rc-patient-auth-001",
    "coverage":     "rc-coverage-auth-001",
    "appointment":  "rc-appt-auth-001",
    "sr":           "rc-sr-auth-001",
    "cer":          "rc-cer-auth-001",
    "ceres":        "rc-ceres-auth-001",
    "claim":        "rc-claim-auth-001",
    "cr":           "rc-claimresponse-auth-001",
    "account":      "rc-account-auth-001",
}

GLOSA_DENIAL_IDS: dict[str, str] = {
    "org_payer":    "rc-org-payer-amil",
    "patient":      "rc-patient-glosa-001",
    "coverage":     "rc-coverage-glosa-001",
    "appointment":  "rc-appt-glosa-001",
    "sr":           "rc-sr-glosa-001",
    "cer":          "rc-cer-glosa-001",
    "ceres":        "rc-ceres-glosa-001",
    "encounter":    "rc-encounter-glosa-001",
    "procedure":    "rc-procedure-glosa-001",
    "claim":        "rc-claim-glosa-001",
    "cr":           "rc-claimresponse-glosa-001",
    "account":      "rc-account-glosa-001",
    "ci":           "rc-chargeitem-glosa-001",
    "invoice":      "rc-invoice-glosa-001",
}

OVERDUE_COLLECTION_IDS: dict[str, str] = {
    "org_payer":    "rc-org-payer-bradesco",
    "patient":      "rc-patient-overdue-001",
    "coverage":     "rc-coverage-overdue-001",
    # Encounter/claim sets (3 contas vencidas)
    "encounter_1":  "rc-encounter-overdue-001",
    "encounter_2":  "rc-encounter-overdue-002",
    "encounter_3":  "rc-encounter-overdue-003",
    "claim_1":      "rc-claim-overdue-001",
    "claim_2":      "rc-claim-overdue-002",
    "claim_3":      "rc-claim-overdue-003",
    "cr_1":         "rc-claimresponse-overdue-001",
    "cr_2":         "rc-claimresponse-overdue-002",
    "cr_3":         "rc-claimresponse-overdue-003",
    "account_1":    "rc-account-overdue-001",
    "account_2":    "rc-account-overdue-002",
    "account_3":    "rc-account-overdue-003",
    "ci_1":         "rc-chargeitem-overdue-001",
    "ci_2":         "rc-chargeitem-overdue-002",
    "ci_3":         "rc-chargeitem-overdue-003",
    "invoice_1":    "rc-invoice-overdue-001",
    "invoice_2":    "rc-invoice-overdue-002",
    "invoice_3":    "rc-invoice-overdue-003",
}

# Cenário 5 — SP-RC-000 orquestrador: glosa → resubmissão → aprovado → variância de pagamento
# Exerce: gateway_billing_approved=NO → gateway_denial_resolution=YES → gateway_payment_variance=YES
RESUBMIT_APPROVED_IDS: dict[str, str] = {
    "org_payer":      "rc-org-payer-sulamerica",
    "patient":        "rc-patient-resubmit-001",
    "coverage":       "rc-coverage-resubmit-001",
    "appointment":    "rc-appt-resubmit-001",
    "sr":             "rc-sr-resubmit-001",
    "cer":            "rc-cer-resubmit-001",
    "ceres":          "rc-ceres-resubmit-001",
    "encounter":      "rc-encounter-resubmit-001",
    "procedure":      "rc-procedure-resubmit-001",
    "claim":          "rc-claim-resubmit-001",          # original glosado (G002)
    "cr":             "rc-claimresponse-resubmit-001",  # partial — G002 Divergência CID-10
    "claim_resubmit": "rc-claim-resubmit-002",          # resubmissão corrigida
    "cr_resubmit":    "rc-claimresponse-resubmit-002",  # complete — aprovado
    "account":        "rc-account-resubmit-001",
    "ci":             "rc-chargeitem-resubmit-001",
    "invoice":        "rc-invoice-resubmit-001",
    "pn":             "rc-paynotice-resubmit-001",
    "pr":             "rc-payreconcile-resubmit-001",   # PaymentReconciliation (variância)
}

# ---------------------------------------------------------------------------
# FHIRSeedData
# ---------------------------------------------------------------------------

@dataclass
class FHIRSeedData:
    """IDs de recursos FHIR de um cenário RC populado no StubFHIRClient."""

    scenario: str
    tenant_id: str
    # Infraestrutura (sempre presente)
    organization_hospital_id: str
    organization_payer_id: str
    practitioner_id: str
    location_ward_id: str
    # Paciente e cobertura (sempre presente)
    patient_id: str
    coverage_id: str
    # Pré-atendimento (sempre presente)
    appointment_id: str
    service_request_id: str
    coverage_eligibility_request_id: str
    coverage_eligibility_response_id: str
    # Cobrança (sempre presente)
    claim_id: str
    claim_response_id: str
    account_id: str
    # Clínico (ausente em auth_denied)
    encounter_id: str | None = None
    procedure_id: str | None = None
    # Financeiro (ausente em auth_denied e glosa_denial não tem pagamento)
    charge_item_id: str | None = None
    invoice_id: str | None = None
    payment_notice_id: str | None = None
    # Extras por cenário
    glosa_claim_response_id: str | None = None
    overdue_account_ids: list[str] = field(default_factory=list)
    # resubmit_approved: segunda claim após glosa e reconciliação de pagamento
    resubmit_claim_id: str | None = None
    resubmit_claim_response_id: str | None = None
    payment_reconciliation_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta(tenant_id: str) -> dict[str, Any]:
    return {"tag": [{"system": TENANT_TAG_SYSTEM, "code": tenant_id}]}


def _ref(rtype: str, rid: str) -> dict[str, str]:
    return {"reference": f"{rtype}/{rid}"}


def _money(value: float) -> dict[str, Any]:
    return {"value": value, "currency": "BRL"}


def _tuss(code: str, display: str) -> dict[str, Any]:
    return {"coding": [{"system": _TUSS, "code": code, "display": display}]}


def _cbhpm(code: str, display: str) -> dict[str, Any]:
    return {"coding": [{"system": _CBHPM, "code": code, "display": display}]}


# ---------------------------------------------------------------------------
# Builders de infraestrutura (tenant-fixos, cenário-independentes)
# ---------------------------------------------------------------------------

def _b_org_hospital(slug: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": f"rc-org-hospital-{slug}",
        "meta": _meta(tenant_id),
        "identifier": [{"system": _CNES, "value": "2076004"}],
        "active": True,
        "name": "Hospital Austa — São José do Rio Preto",
        "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/organization-type", "code": "prov", "display": "Healthcare Provider"}]}],
        "address": [{"line": ["Av. Brigadeiro Faria Lima, 5544"], "city": "São José do Rio Preto", "state": "SP", "postalCode": "15090-000", "country": "BR"}],
    }


def _b_org_payer(payer_id: str, name: str, ans: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": payer_id,
        "meta": _meta(tenant_id),
        "identifier": [{"system": _ANS, "value": ans}],
        "active": True,
        "name": name,
        "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/organization-type", "code": "ins", "display": "Insurance Company"}]}],
    }


def _b_practitioner(pract_id: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Practitioner",
        "id": pract_id,
        "meta": _meta(tenant_id),
        "identifier": [{"system": _CRM, "value": "CRM/SP 234567"}],
        "active": True,
        "name": [{"use": "official", "family": "Mendes", "given": ["Ricardo", "Augusto"]}],
        "qualification": [{"code": {"coding": [{"system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BROcupacao", "code": "225125", "display": "Médico Clínico"}]}}],
    }


def _b_location(loc_id: str, org_id: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Location",
        "id": loc_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "name": "Ala de Internação A",
        "mode": "instance",
        "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode", "code": "HOSP"}]}],
        "managingOrganization": _ref("Organization", org_id),
    }


def _infra_resources(slug: str, tenant_id: str) -> list[dict[str, Any]]:
    org_id = f"rc-org-hospital-{slug}"
    return [
        _b_org_hospital(slug, tenant_id),
        _b_org_payer("rc-org-payer-bradesco",   "Bradesco Saúde S.A.",                           "346659", tenant_id),
        _b_org_payer("rc-org-payer-unimed",     "Unimed Nacional",                                "368253", tenant_id),
        _b_org_payer("rc-org-payer-amil",       "Amil Assistência Médica Internacional S.A.",     "326305", tenant_id),
        _b_org_payer("rc-org-payer-sulamerica", "Sul América Saúde S.A.",                         "582956", tenant_id),
        _b_practitioner("rc-pract-001", tenant_id),
        _b_location("rc-location-ward-001", org_id, tenant_id),
    ]


# ---------------------------------------------------------------------------
# Builders de recursos clínicos
# ---------------------------------------------------------------------------

def _b_patient(pid: str, cpf: str, cns: str, mrn: str,
               family: str, given: list[str], gender: str, dob: str,
               org_id: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": pid,
        "meta": _meta(tenant_id),
        "identifier": [
            {"system": _CPF, "value": cpf},
            {"system": _CNS, "value": cns},
            {"system": _MRN, "value": mrn},
        ],
        "name": [{"use": "official", "family": family, "given": given}],
        "gender": gender,
        "birthDate": dob,
        "managingOrganization": _ref("Organization", org_id),
    }


def _b_coverage(cov_id: str, patient_id: str, payer_id: str,
                plan_code: str, plan_name: str, period_end: str,
                tenant_id: str, status: str = "active") -> dict[str, Any]:
    return {
        "resourceType": "Coverage",
        "id": cov_id,
        "meta": _meta(tenant_id),
        "status": status,
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "HIP", "display": "health insurance plan policy"}]},
        "subscriber": _ref("Patient", patient_id),
        "beneficiary": _ref("Patient", patient_id),
        "subscriberId": "876543210123",
        "payor": [_ref("Organization", payer_id)],
        "class": [{"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/coverage-class", "code": "plan"}]}, "value": plan_code, "name": plan_name}],
        "period": {"end": period_end},
    }


def _b_service_request(sr_id: str, patient_id: str, pract_id: str,
                       coverage_id: str, tenant_id: str,
                       code: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "resourceType": "ServiceRequest",
        "id": sr_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "intent": "order",
        "code": code or _tuss("40101010", "Consulta médica em consultório"),
        "subject": _ref("Patient", patient_id),
        "requester": _ref("Practitioner", pract_id),
        "insurance": [_ref("Coverage", coverage_id)],
        "reasonCode": [{"coding": [{"system": _ICD10, "code": "K80.2", "display": "Colecistite"}]}],
        "authoredOn": "2026-03-14",
    }


def _b_appointment(appt_id: str, patient_id: str, pract_id: str,
                   loc_id: str, sr_id: str, status: str,
                   tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Appointment",
        "id": appt_id,
        "meta": _meta(tenant_id),
        "status": status,
        "serviceType": [_tuss("40101010", "Consulta médica em consultório")],
        "start": "2026-03-15T10:00:00-03:00",
        "end":   "2026-03-15T10:30:00-03:00",
        "participant": [
            {"actor": _ref("Patient",       patient_id), "status": "accepted"},
            {"actor": _ref("Practitioner",  pract_id),   "status": "accepted"},
            {"actor": _ref("Location",      loc_id),     "status": "accepted"},
        ],
        "basedOn": [_ref("ServiceRequest", sr_id)],
    }


def _b_cer(cer_id: str, patient_id: str, coverage_id: str,
           payer_id: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "CoverageEligibilityRequest",
        "id": cer_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "purpose": ["auth-requirements"],
        "patient": _ref("Patient", patient_id),
        "created": "2026-03-14",
        "insurer": _ref("Organization", payer_id),
        "insurance": [{"coverage": _ref("Coverage", coverage_id)}],
        "item": [{"productOrService": _tuss("40101010", "Consulta médica em consultório")}],
    }


def _b_ceres(ceres_id: str, cer_id: str, patient_id: str,
             payer_id: str, outcome: str, disposition: str,
             tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "CoverageEligibilityResponse",
        "id": ceres_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "purpose": ["auth-requirements"],
        "patient": _ref("Patient", patient_id),
        "created": "2026-03-14",
        "request": _ref("CoverageEligibilityRequest", cer_id),
        "outcome": outcome,
        "disposition": disposition,
        "insurer": _ref("Organization", payer_id),
    }


def _b_encounter(enc_id: str, patient_id: str, pract_id: str,
                 loc_id: str, org_id: str, status: str, enc_class: str,
                 start: str, end: str | None, atend_nr: str,
                 tenant_id: str, type_code: str = "04",
                 type_display: str = "Ambulatorial") -> dict[str, Any]:
    r: dict[str, Any] = {
        "resourceType": "Encounter",
        "id": enc_id,
        "meta": _meta(tenant_id),
        "identifier": [{"system": _ATEND, "value": atend_nr}],
        "status": status,
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": enc_class},
        "type": [{"coding": [{"system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRTipoAtendimento", "code": type_code, "display": type_display}]}],
        "subject": _ref("Patient", patient_id),
        "participant": [{"individual": _ref("Practitioner", pract_id)}],
        "period": {"start": start},
        "location": [{"location": _ref("Location", loc_id)}],
        "serviceProvider": _ref("Organization", org_id),
        "reasonCode": [{"coding": [{"system": _ICD10, "code": "K80.2", "display": "Colecistite"}]}],
    }
    if end:
        r["period"]["end"] = end
    return r


def _b_procedure(proc_id: str, patient_id: str, enc_id: str,
                 pract_id: str, sr_id: str, performed: str,
                 tenant_id: str, code: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "resourceType": "Procedure",
        "id": proc_id,
        "meta": _meta(tenant_id),
        "status": "completed",
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", enc_id),
        "code": code or _tuss("40101010", "Consulta médica em consultório"),
        "performedDateTime": performed,
        "performer": [{"actor": _ref("Practitioner", pract_id)}],
        "basedOn": [_ref("ServiceRequest", sr_id)],
    }


def _b_claim(claim_id: str, patient_id: str, org_id: str,
             coverage_id: str, items: list[dict[str, Any]],
             total: float, tenant_id: str, created: str = "2026-03-15") -> dict[str, Any]:
    return {
        "resourceType": "Claim",
        "id": claim_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
        "use": "claim",
        "patient": _ref("Patient", patient_id),
        "created": created,
        "provider": _ref("Organization", org_id),
        "priority": {"coding": [{"code": "normal"}]},
        "insurance": [{"sequence": 1, "focal": True, "coverage": _ref("Coverage", coverage_id)}],
        "item": items,
        "total": _money(total),
    }


def _claim_item(seq: int, tuss_code: str, tuss_display: str,
                amount: float, enc_id: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "sequence": seq,
        "productOrService": _tuss(tuss_code, tuss_display),
        "quantity": {"value": 1},
        "unitPrice": _money(amount),
        "net": _money(amount),
    }
    if enc_id:
        item["encounter"] = [_ref("Encounter", enc_id)]
    return item


def _b_claimresponse(cr_id: str, claim_id: str, patient_id: str,
                     payer_id: str, outcome: str, disposition: str,
                     adjudication_items: list[dict[str, Any]],
                     totals: list[dict[str, Any]],
                     tenant_id: str,
                     payment: dict[str, Any] | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {
        "resourceType": "ClaimResponse",
        "id": cr_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
        "use": "claim",
        "patient": _ref("Patient", patient_id),
        "created": "2026-03-16",
        "insurer": _ref("Organization", payer_id),
        "request": _ref("Claim", claim_id),
        "outcome": outcome,
        "disposition": disposition,
        "item": adjudication_items,
        "total": totals,
    }
    if payment:
        r["payment"] = payment
    return r


def _b_account(acct_id: str, patient_id: str, coverage_id: str,
               org_id: str, status: str, start: str, end: str | None,
               tenant_id: str) -> dict[str, Any]:
    r: dict[str, Any] = {
        "resourceType": "Account",
        "id": acct_id,
        "meta": _meta(tenant_id),
        "status": status,
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "PBILLACCT"}]},
        "subject": [_ref("Patient", patient_id)],
        "servicePeriod": {"start": start},
        "coverage": [{"coverage": _ref("Coverage", coverage_id), "priority": 1}],
        "owner": _ref("Organization", org_id),
    }
    if end:
        r["servicePeriod"]["end"] = end
    return r


def _b_charge_item(ci_id: str, patient_id: str, enc_id: str,
                   acct_id: str, pract_id: str, org_id: str,
                   amount: float, performed: str, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "ChargeItem",
        "id": ci_id,
        "meta": _meta(tenant_id),
        "status": "billable",
        "code": _tuss("40101010", "Consulta médica em consultório"),
        "subject": _ref("Patient", patient_id),
        "context": _ref("Encounter", enc_id),
        "occurrenceDateTime": performed,
        "performer": [{"actor": _ref("Practitioner", pract_id)}],
        "requestingOrganization": _ref("Organization", org_id),
        "quantity": {"value": 1},
        "priceOverride": _money(amount),
        "account": [_ref("Account", acct_id)],
    }


def _b_invoice(inv_id: str, patient_id: str, org_id: str,
               ci_id: str, amount: float, status: str,
               tenant_id: str, nf_number: str = "NF-RC-2026-001") -> dict[str, Any]:
    return {
        "resourceType": "Invoice",
        "id": inv_id,
        "meta": _meta(tenant_id),
        "identifier": [{"system": _NF, "value": nf_number}],
        "status": status,
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/invoice-type", "code": "patient-invoice"}]},
        "subject": _ref("Patient", patient_id),
        "date": "2026-03-15",
        "participant": [{"role": {"coding": [{"code": "issuer"}]}, "actor": _ref("Organization", org_id)}],
        "lineItem": [{"chargeItemReference": _ref("ChargeItem", ci_id), "priceComponent": [{"type": "base", "amount": _money(amount)}]}],
        "totalNet":   _money(amount),
        "totalGross": _money(amount),
    }


def _b_payment_notice(pn_id: str, claim_id: str, cr_id: str,
                      org_id: str, payer_id: str, amount: float,
                      tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "PaymentNotice",
        "id": pn_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "request": _ref("Claim", claim_id),
        "response": _ref("ClaimResponse", cr_id),
        "created": "2026-03-20",
        "reporter": _ref("Organization", org_id),
        "payment": {"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/ex-paymenttype", "code": "complete"}]}},
        "paymentDate": "2026-03-20",
        "payee": _ref("Organization", org_id),
        "recipient": _ref("Organization", payer_id),
        "amount": _money(amount),
    }


def _b_payment_reconciliation(pr_id: str, claim_id: str, cr_id: str,
                               payer_id: str, org_id: str,
                               expected: float, received: float,
                               tenant_id: str) -> dict[str, Any]:
    """Reconciliação de pagamento — captura variância entre esperado e recebido."""
    variance = round(expected - received, 2)
    return {
        "resourceType": "PaymentReconciliation",
        "id": pr_id,
        "meta": _meta(tenant_id),
        "status": "active",
        "period": {"start": "2026-04-01", "end": "2026-04-30"},
        "created": "2026-04-05",
        "paymentIssuer": _ref("Organization", payer_id),
        "outcome": "partial" if variance > 0 else "complete",
        "disposition": (
            f"Pagamento recebido R${received:,.2f} — "
            f"variância R${variance:,.2f} aguardando regularização"
        ),
        "paymentDate": "2026-04-05",
        "paymentAmount": _money(received),
        "detail": [
            {
                "type":     {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/payment-type", "code": "payment"}]},
                "request":  _ref("Claim",         claim_id),
                "response": _ref("ClaimResponse", cr_id),
                "date":     "2026-04-05",
                "payee":    _ref("Organization", org_id),
                "amount":   _money(received),
            },
            {
                "type":   {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/payment-type", "code": "adjustment"}]},
                "date":   "2026-04-05",
                "payee":  _ref("Organization", payer_id),
                "amount": _money(-variance),
            },
        ],
    }


# ---------------------------------------------------------------------------
# Recursos por cenário
# ---------------------------------------------------------------------------

def _happy_path_resources(slug: str, tenant_id: str) -> list[dict[str, Any]]:
    ids    = HAPPY_PATH_IDS
    org_id = f"rc-org-hospital-{slug}"
    pract  = "rc-pract-001"
    loc    = "rc-location-ward-001"

    adjudication_item = [{"itemSequence": 1, "adjudication": [{"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)}]}]
    totals   = [{"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)}]
    payment  = {"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/ex-paymenttype", "code": "complete"}]}, "date": "2026-03-20", "amount": _money(150.00)}

    return [
        _b_patient(ids["patient"], "32165498700", "271000567810001", "MRN-RC-HAPPY-001",
                   "Silva", ["João", "Pedro"], "male", "1980-05-15", org_id, tenant_id),
        _b_coverage(ids["coverage"], ids["patient"], ids["org_payer"],
                    "BRADESCO-NACIONAL-PLUS", "Bradesco Saúde Nacional Plus", "2027-12-31", tenant_id),
        _b_service_request(ids["sr"], ids["patient"], pract, ids["coverage"], tenant_id),
        _b_appointment(ids["appointment"], ids["patient"], pract, loc, ids["sr"], "booked", tenant_id),
        _b_cer(ids["cer"], ids["patient"], ids["coverage"], ids["org_payer"], tenant_id),
        _b_ceres(ids["ceres"], ids["cer"], ids["patient"], ids["org_payer"],
                 "complete", "Procedimento autorizado", tenant_id),
        _b_encounter(ids["encounter"], ids["patient"], pract, loc, org_id,
                     "finished", "AMB", "2026-03-15T10:00:00-03:00", "2026-03-15T10:30:00-03:00",
                     "ATD-2026-RC-001", tenant_id),
        _b_procedure(ids["procedure"], ids["patient"], ids["encounter"], pract, ids["sr"],
                     "2026-03-15T10:00:00-03:00", tenant_id),
        _b_claim(ids["claim"], ids["patient"], org_id, ids["coverage"],
                 [_claim_item(1, "40101010", "Consulta médica em consultório", 150.00, ids["encounter"])],
                 150.00, tenant_id),
        _b_claimresponse(ids["cr"], ids["claim"], ids["patient"], ids["org_payer"],
                         "complete", "Reivindicação processada com sucesso",
                         adjudication_item, totals, tenant_id, payment=payment),
        _b_account(ids["account"], ids["patient"], ids["coverage"], org_id,
                   "active", "2026-03-15", "2026-03-15", tenant_id),
        _b_charge_item(ids["ci"], ids["patient"], ids["encounter"], ids["account"],
                       pract, org_id, 150.00, "2026-03-15T10:00:00-03:00", tenant_id),
        _b_invoice(ids["invoice"], ids["patient"], org_id, ids["ci"], 150.00, "issued", tenant_id),
        _b_payment_notice(ids["pn"], ids["claim"], ids["cr"], org_id, ids["org_payer"], 150.00, tenant_id),
    ]


def _auth_denied_resources(slug: str, tenant_id: str) -> list[dict[str, Any]]:
    ids    = AUTH_DENIED_IDS
    org_id = f"rc-org-hospital-{slug}"
    pract  = "rc-pract-001"
    loc    = "rc-location-ward-001"

    cr_error: dict[str, Any] = {
        "resourceType": "ClaimResponse",
        "id": ids["cr"],
        "meta": _meta(tenant_id),
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
        "use": "claim",
        "patient": _ref("Patient", ids["patient"]),
        "created": "2026-03-16",
        "insurer": _ref("Organization", ids["org_payer"]),
        "request": _ref("Claim", ids["claim"]),
        "outcome": "error",
        "disposition": "Procedimento não coberto pela apólice vigente",
        "error": [{"code": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/adjudication-error", "code": "A001", "display": "Not covered"}]}}],
    }

    return [
        _b_patient(ids["patient"], "74185296300", "274000123456001", "MRN-RC-AUTH-001",
                   "Rocha", ["Maria", "Clara"], "female", "1975-09-22", org_id, tenant_id),
        _b_coverage(ids["coverage"], ids["patient"], ids["org_payer"],
                    "UNIMED-NACIONAL-FLEX", "Unimed Nacional Flex", "2027-06-30", tenant_id),
        _b_service_request(ids["sr"], ids["patient"], pract, ids["coverage"], tenant_id),
        _b_appointment(ids["appointment"], ids["patient"], pract, loc, ids["sr"], "booked", tenant_id),
        _b_cer(ids["cer"], ids["patient"], ids["coverage"], ids["org_payer"], tenant_id),
        _b_ceres(ids["ceres"], ids["cer"], ids["patient"], ids["org_payer"],
                 "error", "Procedimento não coberto pela apólice vigente", tenant_id),
        _b_claim(ids["claim"], ids["patient"], org_id, ids["coverage"],
                 [_claim_item(1, "40101010", "Consulta médica em consultório", 150.00)],
                 150.00, tenant_id),
        cr_error,
        _b_account(ids["account"], ids["patient"], ids["coverage"], org_id,
                   "active", "2026-03-15", None, tenant_id),
    ]


def _glosa_denial_resources(slug: str, tenant_id: str) -> list[dict[str, Any]]:
    ids    = GLOSA_DENIAL_IDS
    org_id = f"rc-org-hospital-{slug}"
    pract  = "rc-pract-001"
    loc    = "rc-location-ward-001"

    adj_partial = [
        {"itemSequence": 1, "adjudication": [{"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)}]},
        {"itemSequence": 2, "adjudication": [
            {"category": {"coding": [{"code": "submitted"}]}, "amount": _money(80.00)},
            {"category": {"coding": [{"code": "eligible"}]}, "amount": _money(0.00),
             "reason": {"coding": [{"system": "http://www.ans.gov.br/fhir/CodeSystem/motivoGlosa", "code": "G001", "display": "Documentação insuficiente"}]}},
        ]},
    ]
    totals_partial = [
        {"category": {"coding": [{"code": "submitted"}]}, "amount": _money(230.00)},
        {"category": {"coding": [{"code": "benefit"}]},   "amount": _money(150.00)},
    ]

    return [
        _b_patient(ids["patient"], "96325874100", "276000987654001", "MRN-RC-GLOSA-001",
                   "Mota", ["Carlos", "Eduardo"], "male", "1968-03-10", org_id, tenant_id),
        _b_coverage(ids["coverage"], ids["patient"], ids["org_payer"],
                    "AMIL-NACIONAL-PREMIUM", "Amil Nacional Premium", "2027-03-31", tenant_id),
        _b_service_request(ids["sr"], ids["patient"], pract, ids["coverage"], tenant_id),
        _b_appointment(ids["appointment"], ids["patient"], pract, loc, ids["sr"], "booked", tenant_id),
        _b_cer(ids["cer"], ids["patient"], ids["coverage"], ids["org_payer"], tenant_id),
        _b_ceres(ids["ceres"], ids["cer"], ids["patient"], ids["org_payer"],
                 "complete", "Procedimento autorizado com condições", tenant_id),
        _b_encounter(ids["encounter"], ids["patient"], pract, loc, org_id,
                     "finished", "AMB", "2026-03-15T14:00:00-03:00", "2026-03-15T14:45:00-03:00",
                     "ATD-2026-RC-002", tenant_id),
        _b_procedure(ids["procedure"], ids["patient"], ids["encounter"], pract, ids["sr"],
                     "2026-03-15T14:00:00-03:00", tenant_id),
        _b_claim(ids["claim"], ids["patient"], org_id, ids["coverage"],
                 [_claim_item(1, "40101010", "Consulta médica em consultório", 150.00, ids["encounter"]),
                  _claim_item(2, "40301362", "Hemograma completo",              80.00, ids["encounter"])],
                 230.00, tenant_id),
        _b_claimresponse(ids["cr"], ids["claim"], ids["patient"], ids["org_payer"],
                         "partial", "Reivindicação parcialmente aprovada — item 2 glosado (G001)",
                         adj_partial, totals_partial, tenant_id),
        _b_account(ids["account"], ids["patient"], ids["coverage"], org_id,
                   "active", "2026-03-15", "2026-03-15", tenant_id),
        _b_charge_item(ids["ci"], ids["patient"], ids["encounter"], ids["account"],
                       pract, org_id, 150.00, "2026-03-15T14:00:00-03:00", tenant_id),
        _b_invoice(ids["invoice"], ids["patient"], org_id, ids["ci"], 230.00,
                   "cancelled", tenant_id, "NF-RC-2026-002"),
    ]


def _overdue_collection_resources(slug: str, tenant_id: str) -> list[dict[str, Any]]:
    ids    = OVERDUE_COLLECTION_IDS
    org_id = f"rc-org-hospital-{slug}"
    pract  = "rc-pract-001"
    loc    = "rc-location-ward-001"
    pid    = ids["patient"]
    cov_id = ids["coverage"]
    payer  = ids["org_payer"]

    # (enc_id, acct_id, claim_id, cr_id, ci_id, inv_id, start, end, date, atend_nr, nf_nr)
    _sets = [
        (ids["encounter_1"], ids["account_1"], ids["claim_1"], ids["cr_1"], ids["ci_1"], ids["invoice_1"],
         "2026-02-14T09:00:00-03:00", "2026-02-14T09:30:00-03:00", "2026-02-14", "ATD-2026-OVD-001", "NF-RC-2026-OVD-001"),
        (ids["encounter_2"], ids["account_2"], ids["claim_2"], ids["cr_2"], ids["ci_2"], ids["invoice_2"],
         "2026-01-15T11:00:00-03:00", "2026-01-15T11:30:00-03:00", "2026-01-15", "ATD-2026-OVD-002", "NF-RC-2026-OVD-002"),
        (ids["encounter_3"], ids["account_3"], ids["claim_3"], ids["cr_3"], ids["ci_3"], ids["invoice_3"],
         "2025-12-16T15:00:00-03:00", "2025-12-16T15:30:00-03:00", "2025-12-16", "ATD-2025-OVD-003", "NF-RC-2025-OVD-003"),
    ]

    adj_ok = [{"itemSequence": 1, "adjudication": [{"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)}]}]
    totals_ok = [{"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)}]

    resources: list[dict[str, Any]] = [
        _b_patient(pid, "15975348600", "278000345678001", "MRN-RC-OVERDUE-001",
                   "Santos", ["Ana", "Beatriz"], "female", "1985-07-18", org_id, tenant_id),
        _b_coverage(cov_id, pid, payer,
                    "BRADESCO-NACIONAL-FLEX", "Bradesco Saúde Nacional Flex", "2025-12-31",
                    tenant_id, status="active"),
    ]

    for enc_id, acct_id, claim_id, cr_id, ci_id, inv_id, start, end, date, atend, nf in _sets:
        resources.extend([
            _b_encounter(enc_id, pid, pract, loc, org_id, "finished", "AMB",
                         start, end, atend, tenant_id),
            _b_claim(claim_id, pid, org_id, cov_id,
                     [_claim_item(1, "40101010", "Consulta médica em consultório", 150.00, enc_id)],
                     150.00, tenant_id, created=date),
            _b_claimresponse(cr_id, claim_id, pid, payer, "complete",
                             "Reivindicação processada — aguardando pagamento",
                             adj_ok, totals_ok, tenant_id),
            _b_account(acct_id, pid, cov_id, org_id, "active", date, date, tenant_id),
            _b_charge_item(ci_id, pid, enc_id, acct_id, pract, org_id, 150.00, start, tenant_id),
            _b_invoice(inv_id, pid, org_id, ci_id, 150.00, "issued", tenant_id, nf),
        ])

    return resources


def _resubmit_approved_resources(slug: str, tenant_id: str) -> list[dict[str, Any]]:
    """Cenário SP-RC-000: glosa G002 → resubmissão → aprovado → variância de pagamento.

    Exerce os três gateways do orquestrador:
      gateway_billing_approved   = NO  (ClaimResponse partial G002)
      gateway_denial_resolution  = YES (resubmit com CID-10 corrigido)
      gateway_payment_variance   = YES (R$3.200 recebido vs R$3.500 esperado)
    """
    ids    = RESUBMIT_APPROVED_IDS
    org_id = f"rc-org-hospital-{slug}"
    pract  = "rc-pract-001"
    loc    = "rc-location-ward-001"
    pid    = ids["patient"]

    surgery_code = _cbhpm("31003117", "Colecistectomia Laparoscópica")

    # Items da claim: consulta pré-op + cirurgia
    claim_items = [
        _claim_item(1, "40101010", "Consulta médica em consultório", 150.00, ids["encounter"]),
        {
            "sequence": 2,
            "productOrService": surgery_code,
            "quantity": {"value": 1},
            "unitPrice": _money(3350.00),
            "net":       _money(3350.00),
            "encounter": [_ref("Encounter", ids["encounter"])],
        },
    ]

    # ClaimResponse original — partial (item 2 glosado G002 Divergência CID-10)
    adj_partial = [
        {"itemSequence": 1, "adjudication": [
            {"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)},
        ]},
        {"itemSequence": 2, "adjudication": [
            {"category": {"coding": [{"code": "submitted"}]}, "amount": _money(3350.00)},
            {"category": {"coding": [{"code": "eligible"}]},  "amount": _money(0.00),
             "reason": {"coding": [{"system": "http://www.ans.gov.br/fhir/CodeSystem/motivoGlosa",
                                    "code": "G002", "display": "Divergência de CID-10"}]}},
        ]},
    ]
    totals_partial = [
        {"category": {"coding": [{"code": "submitted"}]}, "amount": _money(3500.00)},
        {"category": {"coding": [{"code": "benefit"}]},   "amount": _money(150.00)},
    ]

    # ClaimResponse resubmissão — complete, pagamento R$3.200 (variância -R$300)
    adj_full = [
        {"itemSequence": 1, "adjudication": [
            {"category": {"coding": [{"code": "benefit"}]}, "amount": _money(150.00)},
        ]},
        {"itemSequence": 2, "adjudication": [
            {"category": {"coding": [{"code": "benefit"}]}, "amount": _money(3350.00)},
        ]},
    ]
    totals_full = [{"category": {"coding": [{"code": "benefit"}]}, "amount": _money(3500.00)}]
    payment_partial = {
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/ex-paymenttype",
                              "code": "partial"}]},
        "date":   "2026-04-05",
        "amount": _money(3200.00),  # Sul América pagou R$300 a menos
    }

    return [
        _b_patient(pid, "85296374100", "281000456789001", "MRN-RC-RSB-001",
                   "Alves", ["Pedro", "Henrique"], "male", "1972-11-05", org_id, tenant_id),
        _b_coverage(ids["coverage"], pid, ids["org_payer"],
                    "SULAMERICA-EXECUTIVO-MASTER", "Sul América Executivo Master",
                    "2027-09-30", tenant_id),
        _b_service_request(ids["sr"], pid, pract, ids["coverage"], tenant_id,
                           code=surgery_code),
        _b_appointment(ids["appointment"], pid, pract, loc, ids["sr"], "booked", tenant_id),
        _b_cer(ids["cer"], pid, ids["coverage"], ids["org_payer"], tenant_id),
        _b_ceres(ids["ceres"], ids["cer"], pid, ids["org_payer"],
                 "complete", "Cirurgia autorizada — colecistectomia laparoscópica", tenant_id),
        # Encounter internação (3 dias)
        _b_encounter(ids["encounter"], pid, pract, loc, org_id,
                     "finished", "IMP",
                     "2026-03-20T07:00:00-03:00", "2026-03-23T15:00:00-03:00",
                     "ATD-2026-RSB-001", tenant_id,
                     type_code="01", type_display="Internação"),
        _b_procedure(ids["procedure"], pid, ids["encounter"], pract, ids["sr"],
                     "2026-03-21T09:00:00-03:00", tenant_id, code=surgery_code),
        # Claim original (glosado G002)
        _b_claim(ids["claim"], pid, org_id, ids["coverage"],
                 claim_items, 3500.00, tenant_id, created="2026-03-24"),
        _b_claimresponse(ids["cr"], ids["claim"], pid, ids["org_payer"],
                         "partial",
                         "Reivindicação parcialmente aprovada — item 2 glosado (G002: Divergência de CID-10)",
                         adj_partial, totals_partial, tenant_id),
        # Claim resubmissão (aprovada)
        _b_claim(ids["claim_resubmit"], pid, org_id, ids["coverage"],
                 claim_items, 3500.00, tenant_id, created="2026-03-28"),
        _b_claimresponse(ids["cr_resubmit"], ids["claim_resubmit"], pid, ids["org_payer"],
                         "complete",
                         "Reivindicação aprovada após resubmissão com CID-10 K80.2 corrigido",
                         adj_full, totals_full, tenant_id, payment=payment_partial),
        _b_account(ids["account"], pid, ids["coverage"], org_id,
                   "active", "2026-03-20", "2026-03-23", tenant_id),
        _b_charge_item(ids["ci"], pid, ids["encounter"], ids["account"],
                       pract, org_id, 3500.00, "2026-03-21T09:00:00-03:00", tenant_id),
        _b_invoice(ids["invoice"], pid, org_id, ids["ci"], 3500.00, "issued", tenant_id,
                   "NF-RC-2026-RSB-001"),
        _b_payment_notice(ids["pn"], ids["claim_resubmit"], ids["cr_resubmit"],
                          org_id, ids["org_payer"], 3200.00, tenant_id),
        _b_payment_reconciliation(ids["pr"], ids["claim_resubmit"], ids["cr_resubmit"],
                                   ids["org_payer"], org_id, 3500.00, 3200.00, tenant_id),
    ]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

_SCENARIO_BUILDERS = {
    "happy_path":         _happy_path_resources,
    "auth_denied":        _auth_denied_resources,
    "glosa_denial":       _glosa_denial_resources,
    "overdue_collection": _overdue_collection_resources,
    "resubmit_approved":  _resubmit_approved_resources,
}

_SCENARIO_IDS = {
    "happy_path":         HAPPY_PATH_IDS,
    "auth_denied":        AUTH_DENIED_IDS,
    "glosa_denial":       GLOSA_DENIAL_IDS,
    "overdue_collection": OVERDUE_COLLECTION_IDS,
    "resubmit_approved":  RESUBMIT_APPROVED_IDS,
}


def get_rc_resources(
    tenant_id: str = "austa-hospital",
    scenario: str = "happy_path",
) -> list[dict[str, Any]]:
    """Retorna todos os recursos FHIR do cenário em ordem topológica."""
    slug = _TENANT_SLUGS.get(tenant_id, tenant_id.split("-")[0])
    return _infra_resources(slug, tenant_id) + _SCENARIO_BUILDERS[scenario](slug, tenant_id)


def build_bundle(
    tenant_id: str = "austa-hospital",
    scenario: str = "happy_path",
) -> dict[str, Any]:
    """Retorna um FHIR Bundle (transaction) com todos os recursos do cenário."""
    resources = get_rc_resources(tenant_id, scenario)
    return {
        "resourceType": "Bundle",
        "id": f"rc-seed-{scenario.replace('_', '-')}",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": f"{r['resourceType']}/{r['id']}",
                "resource": r,
                "request": {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"},
            }
            for r in resources
        ],
    }


def _make_seed_data(slug: str, tenant_id: str, scenario: str) -> FHIRSeedData:
    ids    = _SCENARIO_IDS[scenario]
    org_id = f"rc-org-hospital-{slug}"

    kwargs: dict[str, Any] = dict(
        scenario=scenario,
        tenant_id=tenant_id,
        organization_hospital_id=org_id,
        organization_payer_id=ids["org_payer"],
        practitioner_id="rc-pract-001",
        location_ward_id="rc-location-ward-001",
        patient_id=ids["patient"],
        coverage_id=ids["coverage"],
        appointment_id=ids.get("appointment", ""),
        service_request_id=ids.get("sr", ""),
        coverage_eligibility_request_id=ids.get("cer", ""),
        coverage_eligibility_response_id=ids.get("ceres", ""),
        claim_id=ids.get("claim", ""),
        claim_response_id=ids.get("cr", ""),
        account_id=ids.get("account_1", ids.get("account", "")),
        encounter_id=ids.get("encounter") or ids.get("encounter_1"),
        procedure_id=ids.get("procedure"),
        charge_item_id=ids.get("ci") or ids.get("ci_1"),
        invoice_id=ids.get("invoice") or ids.get("invoice_1"),
        payment_notice_id=ids.get("pn"),
    )

    if scenario == "glosa_denial":
        kwargs["glosa_claim_response_id"] = ids.get("cr")
    if scenario == "overdue_collection":
        kwargs["overdue_account_ids"] = [ids["account_1"], ids["account_2"], ids["account_3"]]
    if scenario == "resubmit_approved":
        kwargs["glosa_claim_response_id"]    = ids.get("cr")
        kwargs["resubmit_claim_id"]          = ids.get("claim_resubmit")
        kwargs["resubmit_claim_response_id"] = ids.get("cr_resubmit")
        kwargs["payment_reconciliation_id"]  = ids.get("pr")

    return FHIRSeedData(**kwargs)


async def create_rc_seed(
    stub_client: Any,
    tenant_id: str = "austa-hospital",
    scenario: str = "happy_path",
) -> FHIRSeedData:
    """Popula StubFHIRClient com dados RC do cenário e retorna os IDs.

    Args:
        stub_client: Instância de StubFHIRClient (ou qualquer objeto com add_resource)
        tenant_id:   Tenant alvo (default: austa-hospital)
        scenario:    Cenário de dados (happy_path | auth_denied | glosa_denial | overdue_collection)

    Returns:
        FHIRSeedData com todos os IDs de recursos criados
    """
    slug = _TENANT_SLUGS.get(tenant_id, tenant_id.split("-")[0])
    for resource in get_rc_resources(tenant_id, scenario):
        stub_client.add_resource(resource["resourceType"], resource["id"], resource)
    return _make_seed_data(slug, tenant_id, scenario)


# ---------------------------------------------------------------------------
# Geração dos JSON Bundles (python -m tests.fixtures.fhir_seed)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import pathlib

    output_dir = pathlib.Path(__file__).parent / "fhir"
    output_dir.mkdir(exist_ok=True)

    for _scenario in ["happy_path", "auth_denied", "glosa_denial", "overdue_collection", "resubmit_approved"]:
        _bundle = build_bundle(scenario=_scenario)
        _fname  = f"rc_{_scenario}.json"
        (output_dir / _fname).write_text(
            json.dumps(_bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ok  {_fname}  ({len(_bundle['entry'])} recursos)")
