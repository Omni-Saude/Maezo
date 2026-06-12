#!/usr/bin/env python3
"""
MAEZO — Verifica catalogos FHIR necessarios para SP-RC-002 (Pre-Service).

Recursos necessarios:
  - Patient       (V02) — ja verificado, 163k registros
  - Procedure     (V04) — procedimentos TUSS
  - Coverage      (V05) — convenio do paciente
  - ClaimResponse (V06) — autorizacoes (preAuth)
  - Organization  (V24) — operadoras/convenios

Para cada recurso: conta total, mostra amostra e analisa completude
dos campos exigidos pelos workers do RC-002.

Uso:
  python scripts/dev/test_fhir_rc002_catalogs.py
  python scripts/dev/test_fhir_rc002_catalogs.py --url http://localhost:8082/fhir
  python scripts/dev/test_fhir_rc002_catalogs.py --verbose
"""

import argparse
import json
import sys

try:
    import httpx
except ImportError:
    print("httpx nao instalado. Execute: pip install httpx")
    sys.exit(1)

FHIR_BASE = "https://fhir.austahospital.com.br/fhir"
TIMEOUT = 30

# -- Cores --------------------------------------------------------------------
GREEN = "\033[0;32m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"{GREEN}  [OK]{NC} {msg}")


def err(msg):
    print(f"{RED}  [FAIL]{NC} {msg}")


def info(msg):
    print(f"{BLUE}  [INFO]{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}  [WARN]{NC} {msg}")


def header(msg):
    print(f"\n{BOLD}{CYAN}{'=' * 64}")
    print(f"  {msg}")
    print(f"{'=' * 64}{NC}\n")


def subheader(msg):
    print(f"\n  {BOLD}{msg}{NC}")
    print(f"  {'-' * 56}")


# -- FHIR helpers -------------------------------------------------------------

def get_client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=TIMEOUT,
        headers={"Accept": "application/fhir+json"},
    )


def count_resource(client: httpx.Client, resource_type: str) -> int | None:
    try:
        r = client.get(f"/{resource_type}", params={"_summary": "count"})
        r.raise_for_status()
        return r.json().get("total")
    except Exception as e:
        err(f"Erro ao contar {resource_type}: {e}")
        return None


def fetch_sample(client: httpx.Client, resource_type: str, count: int = 20, params: dict | None = None) -> list[dict]:
    p = {"_count": str(count)}
    if params:
        p.update(params)
    try:
        r = client.get(f"/{resource_type}", params=p)
        r.raise_for_status()
        bundle = r.json()
        return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
    except Exception as e:
        err(f"Erro ao buscar {resource_type}: {e}")
        return []


def print_json_sample(resource: dict, max_lines: int = 25):
    """Imprime JSON indentado (truncado)."""
    txt = json.dumps(resource, indent=2, ensure_ascii=False)
    lines = txt.split("\n")
    for line in lines[:max_lines]:
        print(f"    {line}")
    if len(lines) > max_lines:
        print(f"    ... (+{len(lines) - max_lines} linhas)")


def analyze_completeness(entries: list[dict], field_map: dict[str, str]) -> dict[str, int]:
    """Analisa completude. field_map: {label: json_path_simple}."""
    counts = {label: 0 for label in field_map}
    for resource in entries:
        for label, path in field_map.items():
            if _has_field(resource, path):
                counts[label] += 1
    return counts


def _has_field(resource: dict, path: str) -> bool:
    """Checa se campo existe (suporta dot notation simples e array check)."""
    parts = path.split(".")
    current = resource
    for part in parts:
        if part.endswith("[]"):
            key = part[:-2]
            current = current.get(key, [])
            if not current:
                return False
            current = current[0] if isinstance(current, list) else current
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return False
            if current is None:
                return False
    return True


def print_completeness(counts: dict[str, int], total: int, bpmn_vars: dict[str, str] | None = None):
    var_col = "  Var BPMN RC-002" if bpmn_vars else ""
    print(f"\n  {'Campo FHIR':<35} {'Preenchido':<12} {'%':<8}{var_col}")
    print(f"  {'-' * (55 + (20 if bpmn_vars else 0))}")
    for label, count in counts.items():
        pct = (count / total) * 100 if total > 0 else 0
        color = GREEN if pct >= 80 else (YELLOW if pct >= 50 else RED)
        var = ""
        if bpmn_vars and label in bpmn_vars:
            var = f"  {bpmn_vars[label]}"
        print(f"  {label:<35} {count:>4}/{total:<6} {color}{pct:>5.1f}%{NC}{var}")


# ==============================================================================
# Catalogo: Procedure (V04)
# ==============================================================================

def check_procedure(client: httpx.Client, verbose: bool):
    header("PROCEDURE (V04) — Procedimentos TUSS")
    info("Workers RC-002: check_authorization, request_authorization, validate_procedure")
    info("Vars BPMN: procedureCode, procedureStatus, tussCodes, quantity")

    total = count_resource(client, "Procedure")
    if total is not None:
        ok(f"Total de Procedures: {BOLD}{total}{NC}")
    else:
        err("Nao foi possivel contar Procedures")
        return total

    entries = fetch_sample(client, "Procedure", count=30)
    if not entries:
        warn("Nenhum registro retornado na amostra")
        return total

    fields = {
        "id": "id",
        "status": "status",
        "code.coding (TUSS)": "code.coding[]",
        "code.coding.code": "code.coding[].code",
        "code.coding.display": "code.coding[].display",
        "subject (patientId)": "subject",
        "encounter": "encounter",
        "performedDateTime": "performedDateTime",
        "performedPeriod": "performedPeriod",
        "performer": "performer[]",
        "extension (authorization)": "extension[]",
    }
    bpmn = {
        "code.coding (TUSS)": "procedureCode",
        "status": "procedureStatus",
        "subject (patientId)": "patientId",
        "encounter": "encounterId",
        "performer": "performerPractitioner",
    }
    counts = analyze_completeness(entries, fields)
    print_completeness(counts, len(entries), bpmn)

    if verbose and entries:
        subheader("Amostra (primeiro registro):")
        print_json_sample(entries[0])

    # Check coding systems
    subheader("Coding systems encontrados:")
    systems = set()
    for e in entries:
        for coding in e.get("code", {}).get("coding", []):
            systems.add(coding.get("system", "?"))
    for s in sorted(systems):
        info(s)

    return total


# ==============================================================================
# Catalogo: Coverage (V05)
# ==============================================================================

def check_coverage(client: httpx.Client, verbose: bool):
    header("COVERAGE (V05) — Convenio do Paciente")
    info("Workers RC-002: check_authorization, request_authorization, validate_procedure")
    info("Vars BPMN: payerId, payerName, planCode, cardNumber, coverageType, isActive, contractId")

    total = count_resource(client, "Coverage")
    if total is not None:
        ok(f"Total de Coverages: {BOLD}{total}{NC}")
    else:
        err("Nao foi possivel contar Coverages")
        return total

    entries = fetch_sample(client, "Coverage", count=30)
    if not entries:
        warn("Nenhum registro retornado na amostra")
        return total

    fields = {
        "id": "id",
        "status": "status",
        "beneficiary (patient)": "beneficiary",
        "payor (operadora)": "payor[]",
        "identifier (carteirinha)": "identifier[]",
        "class (plano)": "class[]",
        "type (cobertura)": "type",
        "period": "period",
        "subscriber": "subscriber",
        "subscriberId": "subscriberId",
    }
    bpmn = {
        "status": "isActive",
        "beneficiary (patient)": "patientId",
        "payor (operadora)": "payerId",
        "identifier (carteirinha)": "cardNumber",
        "class (plano)": "planCode",
        "type (cobertura)": "coverageType",
        "period": "coverageEndDate",
    }
    counts = analyze_completeness(entries, fields)
    print_completeness(counts, len(entries), bpmn)

    if verbose and entries:
        subheader("Amostra (primeiro registro):")
        print_json_sample(entries[0])

    # Status distribution
    subheader("Distribuicao de status:")
    statuses = {}
    for e in entries:
        s = e.get("status", "?")
        statuses[s] = statuses.get(s, 0) + 1
    for s, c in sorted(statuses.items(), key=lambda x: -x[1]):
        info(f"{s}: {c}")

    return total


# ==============================================================================
# Catalogo: ClaimResponse (V06) — Autorizacoes
# ==============================================================================

def check_claim_response(client: httpx.Client, verbose: bool):
    header("CLAIMRESPONSE (V06) — Autorizacoes / PreAuth")
    info("Workers RC-002: check_authorization, request_authorization, pending_authorization, manual_review")
    info("Vars BPMN: authorizationStatus, authNumber, approvedAmount, denialReason, authorizedDays")

    total = count_resource(client, "ClaimResponse")
    if total is not None:
        ok(f"Total de ClaimResponses: {BOLD}{total}{NC}")
    else:
        err("Nao foi possivel contar ClaimResponses")
        return total

    entries = fetch_sample(client, "ClaimResponse", count=30)
    if not entries:
        warn("Nenhum registro retornado na amostra")
        return total

    fields = {
        "id": "id",
        "status": "status",
        "outcome": "outcome",
        "type": "type",
        "patient": "patient",
        "insurer": "insurer",
        "request (claim ref)": "request",
        "preAuthRef": "preAuthRef",
        "item (adjudication)": "item[]",
        "total": "total[]",
        "created": "created",
        "disposition": "disposition",
        "error": "error[]",
        "extension": "extension[]",
    }
    bpmn = {
        "status": "authorizationStatus",
        "outcome": "authorizationStatus",
        "preAuthRef": "authNumber",
        "insurer": "payerId",
        "patient": "patientId",
        "disposition": "denialReason",
        "total": "approvedAmount",
    }
    counts = analyze_completeness(entries, fields)
    print_completeness(counts, len(entries), bpmn)

    if verbose and entries:
        subheader("Amostra (primeiro registro):")
        print_json_sample(entries[0])

    # Outcome distribution
    subheader("Distribuicao de outcomes:")
    outcomes = {}
    for e in entries:
        o = e.get("outcome", "?")
        outcomes[o] = outcomes.get(o, 0) + 1
    for o, c in sorted(outcomes.items(), key=lambda x: -x[1]):
        info(f"{o}: {c}")

    return total


# ==============================================================================
# Catalogo: Organization (V24) — Operadoras
# ==============================================================================

def check_organization(client: httpx.Client, verbose: bool):
    header("ORGANIZATION (V24) — Operadoras / Convenios")
    info("Referenciado por todos os fluxos RC via payerId")
    info("Vars BPMN: payerId, payerName, payerCnpj, payerAnsCode")

    total = count_resource(client, "Organization")
    if total is not None:
        ok(f"Total de Organizations: {BOLD}{total}{NC}")
    else:
        err("Nao foi possivel contar Organizations")
        return total

    entries = fetch_sample(client, "Organization", count=30)
    if not entries:
        warn("Nenhum registro retornado na amostra")
        return total

    fields = {
        "id": "id",
        "name": "name",
        "active": "active",
        "identifier (CNPJ)": "identifier[]",
        "type": "type[]",
        "telecom": "telecom[]",
        "address": "address[]",
    }
    bpmn = {
        "id": "payerId",
        "name": "payerName",
        "identifier (CNPJ)": "payerCnpj",
    }
    counts = analyze_completeness(entries, fields)
    print_completeness(counts, len(entries), bpmn)

    if verbose and entries:
        subheader("Amostra (primeiro registro):")
        print_json_sample(entries[0])

    # List first organizations
    subheader("Operadoras cadastradas (amostra):")
    for e in entries[:10]:
        oid = e.get("id", "?")
        name = e.get("name", "?")
        active = e.get("active", "?")
        # ANS
        ans = "?"
        cnpj = "?"
        for ident in e.get("identifier", []):
            sys_val = ident.get("system", "").lower()
            if "ans" in sys_val:
                ans = ident.get("value", "?")
            elif "cnpj" in sys_val:
                cnpj = ident.get("value", "?")
        info(f"ID={oid}  {name:<40} active={active}  ANS={ans}  CNPJ={cnpj}")

    return total


# ==============================================================================
# Catalogo: Encounter (bonus — referenciado por RC-002 indiretamente)
# ==============================================================================

def check_encounter(client: httpx.Client, verbose: bool):
    header("ENCOUNTER (V01) — Atendimentos (referencia indireta RC-002)")
    info("Usado como contexto: encounterId vincula procedimentos e autorizacoes")

    total = count_resource(client, "Encounter")
    if total is not None:
        ok(f"Total de Encounters: {BOLD}{total}{NC}")
    else:
        err("Nao foi possivel contar Encounters")
        return total

    entries = fetch_sample(client, "Encounter", count=20)
    if not entries:
        warn("Nenhum registro retornado na amostra")
        return total

    fields = {
        "id": "id",
        "status": "status",
        "class": "class",
        "subject (patient)": "subject",
        "period.start": "period.start",
        "period.end": "period.end",
        "serviceProvider": "serviceProvider",
        "participant": "participant[]",
        "type": "type[]",
        "location": "location[]",
    }
    counts = analyze_completeness(entries, fields)
    print_completeness(counts, len(entries))

    if verbose and entries:
        subheader("Amostra (primeiro registro):")
        print_json_sample(entries[0])

    # Status distribution
    subheader("Distribuicao de status:")
    statuses = {}
    for e in entries:
        s = e.get("status", "?")
        statuses[s] = statuses.get(s, 0) + 1
    for s, c in sorted(statuses.items(), key=lambda x: -x[1]):
        info(f"{s}: {c}")

    return total


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Verifica catalogos FHIR para SP-RC-002")
    parser.add_argument("--url", default=FHIR_BASE, help=f"URL base FHIR (default: {FHIR_BASE})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostra JSON da amostra")
    args = parser.parse_args()

    header(f"MAEZO — Catalogos FHIR para SP-RC-002 (Pre-Service)\n  {args.url}")

    client = get_client(args.url)

    # Conectividade
    try:
        r = client.get("/metadata")
        r.raise_for_status()
        ok(f"Servidor FHIR acessivel ({r.status_code})")
    except Exception as e:
        err(f"Servidor FHIR inacessivel: {e}")
        sys.exit(1)

    # Verificar cada catalogo
    results = {}
    results["Patient"] = count_resource(client, "Patient")
    ok(f"Patient: {BOLD}{results['Patient']}{NC} (ja verificado)")

    results["Procedure"] = check_procedure(client, args.verbose)
    results["Coverage"] = check_coverage(client, args.verbose)
    results["ClaimResponse"] = check_claim_response(client, args.verbose)
    results["Organization"] = check_organization(client, args.verbose)
    results["Encounter"] = check_encounter(client, args.verbose)

    # Resumo final
    header("RESUMO — Prontidao dos Catalogos RC-002")
    print(f"  {'Recurso FHIR':<20} {'View':<8} {'Registros':<12} {'Status':<20}")
    print(f"  {'-' * 60}")
    for resource, total in results.items():
        view = {"Patient": "V02", "Procedure": "V04", "Coverage": "V05",
                "ClaimResponse": "V06", "Organization": "V24", "Encounter": "V01"}.get(resource, "?")
        if total is None:
            status = f"{RED}ERRO{NC}"
            count_str = "?"
        elif total == 0:
            status = f"{RED}VAZIO — BLOQUEANTE{NC}"
            count_str = "0"
        else:
            status = f"{GREEN}OK{NC}"
            count_str = f"{total:,}"
        print(f"  {resource:<20} {view:<8} {count_str:<12} {status}")

    # Veredicto
    missing = [r for r, t in results.items() if t is None or t == 0]
    print()
    if not missing:
        ok(f"{BOLD}Todos os catalogos do RC-002 tem registros!{NC}")
    else:
        err(f"{BOLD}Catalogos sem registros (bloqueantes): {', '.join(missing)}{NC}")
        info("Esses catalogos precisam ser populados antes de ativar o SP-RC-002")

    print()


if __name__ == "__main__":
    main()
