#!/usr/bin/env python3
"""
MAEZO — Script de teste do catalogo Patient no HAPI FHIR R4.

Verifica:
  1. Quantos pacientes estao cadastrados (total)
  2. Busca por nome
  3. Busca por CPF (identifier)
  4. Busca por ID especifico
  5. Resumo dos campos preenchidos (completude)

Uso:
  python scripts/dev/test_fhir_patient.py
  python scripts/dev/test_fhir_patient.py --name "Silva"
  python scripts/dev/test_fhir_patient.py --cpf "12345678900"
  python scripts/dev/test_fhir_patient.py --id "patient-123"
  python scripts/dev/test_fhir_patient.py --summary
"""

import argparse
import sys

try:
    import httpx
except ImportError:
    print("httpx nao instalado. Execute: pip install httpx")
    sys.exit(1)

# -- Config -------------------------------------------------------------------
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
    print(f"\n{BOLD}{CYAN}{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}{NC}\n")


# -- Helpers ------------------------------------------------------------------

def get_client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=TIMEOUT,
        headers={"Accept": "application/fhir+json"},
    )


def fetch_bundle(client: httpx.Client, url: str, params: dict | None = None) -> dict:
    r = client.get(url, params=params)
    r.raise_for_status()
    return r.json()


def extract_total(bundle: dict) -> int | None:
    return bundle.get("total")


def extract_entries(bundle: dict) -> list[dict]:
    return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]


def print_patient_summary(patient: dict, index: int = 0):
    pid = patient.get("id", "?")
    names = patient.get("name", [])
    name_str = "?"
    if names:
        n = names[0]
        given = " ".join(n.get("given", []))
        family = n.get("family", "")
        text = n.get("text", "")
        name_str = text if text else f"{given} {family}".strip()

    gender = patient.get("gender", "?")
    birth = patient.get("birthDate", "?")

    # CPF
    cpf = "?"
    for ident in patient.get("identifier", []):
        sys_val = ident.get("system", "")
        if "cpf" in sys_val.lower() or "cpf" in ident.get("type", {}).get("text", "").lower():
            cpf = ident.get("value", "?")
            break

    # Telefone
    phone = "?"
    mobile = "?"
    for telecom in patient.get("telecom", []):
        use = telecom.get("use", "")
        system = telecom.get("system", "")
        if system == "phone" and use == "mobile":
            mobile = telecom.get("value", "?")
        elif system == "phone":
            phone = telecom.get("value", "?")

    print(f"  {CYAN}#{index + 1}{NC} ID: {BOLD}{pid}{NC}")
    print(f"      Nome:       {name_str}")
    print(f"      Nascimento: {birth}")
    print(f"      Sexo:       {gender}")
    print(f"      CPF:        {cpf}")
    print(f"      Telefone:   {phone}  |  Celular: {mobile}")
    print()


# -- Testes -------------------------------------------------------------------

def test_count(client: httpx.Client):
    """Conta total de pacientes cadastrados."""
    header("1. TOTAL DE PACIENTES CADASTRADOS")
    bundle = fetch_bundle(client, "/Patient", params={"_summary": "count"})
    total = extract_total(bundle)
    if total is not None:
        ok(f"Total de pacientes: {BOLD}{total}{NC}")
    else:
        warn("Servidor nao retornou campo 'total' no Bundle")
    return total


def test_search_name(client: httpx.Client, name: str):
    """Busca pacientes por nome."""
    header(f"2. BUSCA POR NOME: '{name}'")
    bundle = fetch_bundle(client, "/Patient", params={"name": name, "_count": "10"})
    total = extract_total(bundle)
    entries = extract_entries(bundle)
    info(f"Resultados encontrados: {total if total is not None else len(entries)}")
    if not entries:
        warn("Nenhum paciente encontrado com esse nome")
        return
    for i, p in enumerate(entries):
        print_patient_summary(p, i)


def test_search_cpf(client: httpx.Client, cpf: str):
    """Busca paciente por CPF (identifier)."""
    header(f"3. BUSCA POR CPF: '{cpf}'")
    # Tenta busca pelo system padrao brasileiro de CPF
    systems = [
        f"http://hl7.org/fhir/sid/us-ssn|{cpf}",  # fallback generico
        f"https://fhir.saude.gov.br/sid/cpf|{cpf}",
        f"http://www.saude.gov.br/fhir/r4/NamingSystem/cpf|{cpf}",
        cpf,  # busca sem system
    ]
    for sys_val in systems:
        bundle = fetch_bundle(client, "/Patient", params={"identifier": sys_val, "_count": "5"})
        entries = extract_entries(bundle)
        if entries:
            ok(f"Encontrado via identifier={sys_val.split('|')[0] if '|' in sys_val else 'valor direto'}")
            for i, p in enumerate(entries):
                print_patient_summary(p, i)
            return
    warn(f"Nenhum paciente encontrado com CPF {cpf} nos systems testados")


def test_read_by_id(client: httpx.Client, patient_id: str):
    """Busca paciente por ID logico."""
    header(f"4. BUSCA POR ID: '{patient_id}'")
    try:
        r = client.get(f"/Patient/{patient_id}")
        if r.status_code == 404:
            warn(f"Patient/{patient_id} nao encontrado (404)")
            return
        r.raise_for_status()
        patient = r.json()
        ok(f"Patient/{patient_id} encontrado")
        print_patient_summary(patient, 0)

        # Mostra todos os identifiers
        identifiers = patient.get("identifier", [])
        if identifiers:
            print(f"  {BOLD}Identifiers:{NC}")
            for ident in identifiers:
                sys_name = ident.get("system", "?")
                val = ident.get("value", "?")
                print(f"    - {sys_name}: {val}")
            print()

        # Mostra extensions
        extensions = patient.get("extension", [])
        if extensions:
            print(f"  {BOLD}Extensions:{NC}")
            for ext in extensions:
                print(f"    - {ext.get('url', '?')}: {ext.get('valueString', ext.get('valueCode', ext.get('valueBoolean', '?')))}")
            print()

    except httpx.HTTPStatusError as e:
        err(f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}")


def test_summary(client: httpx.Client):
    """Analisa completude dos campos nos primeiros 50 pacientes."""
    header("5. ANALISE DE COMPLETUDE (amostra)")
    bundle = fetch_bundle(client, "/Patient", params={"_count": "50"})
    entries = extract_entries(bundle)
    total_bundle = extract_total(bundle)

    if not entries:
        warn("Nenhum paciente para analisar")
        return

    info(f"Analisando {len(entries)} pacientes (de {total_bundle or '?'} total)")
    print()

    fields = {
        "name": 0,
        "birthDate": 0,
        "gender": 0,
        "identifier (CPF)": 0,
        "telecom (phone)": 0,
        "telecom (mobile)": 0,
        "telecom (email)": 0,
        "address": 0,
        "managingOrganization": 0,
        "active": 0,
        "extension": 0,
    }

    for p in entries:
        if p.get("name"):
            fields["name"] += 1
        if p.get("birthDate"):
            fields["birthDate"] += 1
        if p.get("gender"):
            fields["gender"] += 1
        if p.get("address"):
            fields["address"] += 1
        if p.get("managingOrganization"):
            fields["managingOrganization"] += 1
        if p.get("active") is not None:
            fields["active"] += 1
        if p.get("extension"):
            fields["extension"] += 1
        for ident in p.get("identifier", []):
            if "cpf" in ident.get("system", "").lower() or "cpf" in str(ident.get("type", {})).lower():
                fields["identifier (CPF)"] += 1
                break
        for telecom in p.get("telecom", []):
            if telecom.get("system") == "phone" and telecom.get("use") == "mobile":
                fields["telecom (mobile)"] += 1
            elif telecom.get("system") == "phone":
                fields["telecom (phone)"] += 1
            elif telecom.get("system") == "email":
                fields["telecom (email)"] += 1

    n = len(entries)
    print(f"  {'Campo':<30} {'Preenchido':<12} {'%':<8}")
    print(f"  {'-' * 50}")
    for field, count in fields.items():
        pct = (count / n) * 100
        color = GREEN if pct >= 80 else (YELLOW if pct >= 50 else RED)
        print(f"  {field:<30} {count:>4}/{n:<6} {color}{pct:>5.1f}%{NC}")

    print()

    # Amostra dos primeiros 3
    info("Amostra (primeiros 3 pacientes):")
    print()
    for i, p in enumerate(entries[:3]):
        print_patient_summary(p, i)


def test_first_patients(client: httpx.Client, count: int = 5):
    """Lista os primeiros N pacientes."""
    header(f"6. PRIMEIROS {count} PACIENTES")
    bundle = fetch_bundle(client, "/Patient", params={"_count": str(count), "_sort": "-_lastUpdated"})
    entries = extract_entries(bundle)
    total = extract_total(bundle)

    info(f"Total no servidor: {total or '?'}")
    info(f"Exibindo: {len(entries)}")
    print()
    for i, p in enumerate(entries):
        print_patient_summary(p, i)


# -- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Teste do catalogo Patient - HAPI FHIR MAEZO")
    parser.add_argument("--url", default=FHIR_BASE, help=f"URL base do FHIR (default: {FHIR_BASE})")
    parser.add_argument("--name", help="Buscar paciente por nome (ex: 'Silva')")
    parser.add_argument("--cpf", help="Buscar paciente por CPF (ex: '12345678900')")
    parser.add_argument("--id", help="Buscar paciente por ID logico (ex: 'patient-123')")
    parser.add_argument("--summary", action="store_true", help="Analise de completude dos campos")
    parser.add_argument("--count", type=int, default=5, help="Qtd de pacientes a listar (default: 5)")
    args = parser.parse_args()

    header(f"MAEZO — Teste Catalogo Patient\n  {args.url}/Patient")

    client = get_client(args.url)

    # Teste de conectividade
    try:
        r = client.get("/metadata")
        r.raise_for_status()
        ok(f"Servidor FHIR acessivel ({r.status_code})")
    except Exception as e:
        err(f"Servidor FHIR inacessivel: {e}")
        sys.exit(1)

    # 1 — Sempre conta total
    total = test_count(client)

    # 2 — Busca por nome
    if args.name:
        test_search_name(client, args.name)

    # 3 — Busca por CPF
    if args.cpf:
        test_search_cpf(client, args.cpf)

    # 4 — Busca por ID
    if args.id:
        test_read_by_id(client, args.id)

    # 5 — Analise de completude
    if args.summary:
        test_summary(client)

    # 6 — Lista primeiros pacientes (se nenhuma busca especifica)
    if not (args.name or args.cpf or args.id or args.summary):
        test_first_patients(client, args.count)

    print(f"\n{GREEN}Done.{NC}\n")


if __name__ == "__main__":
    main()
