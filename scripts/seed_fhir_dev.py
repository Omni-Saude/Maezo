#!/usr/bin/env python3
"""
MAEZO — Seed completo de dados FHIR RC no HAPI FHIR dev.

Cria/atualiza recursos FHIR R4 via PUT idempotente para todos os cenários
do Revenue Cycle. Rodar N vezes = mesmo resultado.

Uso:
  python scripts/seed_fhir_dev.py
  python scripts/seed_fhir_dev.py --url http://192.168.1.10:8082/fhir
  python scripts/seed_fhir_dev.py --scenario happy_path
  python scripts/seed_fhir_dev.py --tenant amh-sp-morumbi --scenario all
  python scripts/seed_fhir_dev.py --no-wait
"""

import argparse
import sys
import time
from pathlib import Path

# Garante que tests/ está no path para importar fhir_seed
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import httpx
except ImportError:
    print("httpx não instalado. Execute: pip install httpx")
    sys.exit(1)

try:
    import importlib.util
    _seed_path = Path(__file__).parent.parent / "tests" / "fixtures" / "fhir_seed.py"
    _spec = importlib.util.spec_from_file_location("fhir_seed", _seed_path)
    _mod  = importlib.util.module_from_spec(_spec)
    sys.modules["fhir_seed"] = _mod
    _spec.loader.exec_module(_mod)
    get_rc_resources = _mod.get_rc_resources
except Exception as e:
    print(f"Erro ao importar fhir_seed: {e}")
    print("Execute a partir da raiz do repositório.")
    sys.exit(1)

# --- Cores ---
GREEN = "\033[0;32m"
RED   = "\033[0;31m"
BLUE  = "\033[0;34m"
YELL  = "\033[0;33m"
NC    = "\033[0m"


def ok(msg: str):   print(f"{GREEN}  ok{NC}   {msg}")
def err(msg: str):  print(f"{RED}  FAIL{NC} {msg}")
def log(msg: str):  print(f"{BLUE}[seed]{NC} {msg}")
def warn(msg: str): print(f"{YELL} warn{NC}  {msg}")


SCENARIOS = ["happy_path", "auth_denied", "glosa_denial", "overdue_collection", "resubmit_approved"]

TENANTS = ["austa-hospital", "amh-sp-morumbi", "amh-rj-barra", "amh-mg-bh"]


def seed_resource(client: httpx.Client, resource: dict) -> bool:
    """PUT idempotente de um recurso FHIR."""
    rtype = resource["resourceType"]
    rid   = resource["id"]
    try:
        resp = client.put(f"/{rtype}/{rid}", json=resource)
        if resp.status_code in (200, 201):
            ok(f"{rtype}/{rid}")
            return True
        err(f"{rtype}/{rid} — HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except httpx.ConnectError:
        err(f"{rtype}/{rid} — conexão recusada")
        return False
    except httpx.TimeoutException:
        err(f"{rtype}/{rid} — timeout")
        return False


def wait_for_fhir(client: httpx.Client, timeout: int = 120) -> bool:
    """Aguarda HAPI FHIR responder (imagem distroless sem healthcheck interno)."""
    log(f"Aguardando HAPI FHIR... (timeout {timeout}s)")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = client.get("/metadata")
            if resp.status_code == 200:
                ok("HAPI FHIR pronto")
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(3)
        print(".", end="", flush=True)
    print()
    err(f"HAPI FHIR não respondeu em {timeout}s")
    return False


def seed_scenario(client: httpx.Client, tenant_id: str, scenario: str) -> tuple[int, int]:
    """Seed de um cenário. Retorna (sucesso, total)."""
    log(f"Cenário: {scenario}  |  tenant: {tenant_id}")
    resources = get_rc_resources(tenant_id=tenant_id, scenario=scenario)
    success = sum(1 for r in resources if seed_resource(client, r))
    return success, len(resources)


def main():
    parser = argparse.ArgumentParser(
        description="Seed FHIR RC data no HAPI FHIR dev",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8082/fhir",
        help="HAPI FHIR base URL (padrão: $HAPI_FHIR_URL ou http://localhost:8082/fhir)",
    )
    parser.add_argument(
        "--tenant",
        default="austa-hospital",
        choices=TENANTS,
        help="Tenant alvo (padrão: austa-hospital)",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all"] + SCENARIOS,
        help="Cenário(s) a popular (padrão: all)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Não aguardar HAPI FHIR ficar pronto",
    )
    args = parser.parse_args()

    # Prioridade: --url > HAPI_FHIR_URL env > default
    import os
    url = args.url if args.url != "http://localhost:8082/fhir" else os.getenv("HAPI_FHIR_URL", args.url)

    client = httpx.Client(
        base_url=url,
        headers={"Content-Type": "application/fhir+json"},
        timeout=30.0,
    )

    log(f"HAPI FHIR: {url}")

    if not args.no_wait:
        if not wait_for_fhir(client):
            sys.exit(1)

    scenarios = SCENARIOS if args.scenario == "all" else [args.scenario]

    total_ok  = 0
    total_all = 0

    for scenario in scenarios:
        ok_n, all_n = seed_scenario(client, args.tenant, scenario)
        total_ok  += ok_n
        total_all += all_n
        print()

    if total_ok == total_all:
        log(f"Seed completo: {total_ok}/{total_all} recursos ({len(scenarios)} cenários)")
    else:
        warn(f"Seed parcial: {total_ok}/{total_all} recursos ({total_all - total_ok} falharam)")
        sys.exit(1)


if __name__ == "__main__":
    main()
