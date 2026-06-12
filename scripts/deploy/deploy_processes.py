#!/usr/bin/env python3
"""
MAEZO — Deploy de Processos BPMN e Tabelas DMN no CIB Seven

Estratégia:
  BPMN: 1 deployment por arquivo (57 arquivos) — cada processo tem seu nome único
  DMN:  1 deployment por subdiretório (~50-80 batches) — agrupa tabelas relacionadas
        Evita limite de args do shell ao trabalhar com 1.274+ arquivos

Uso:
  python3 scripts/deploy_processes.py --url http://localhost:8080/engine-rest
  python3 scripts/deploy_processes.py --url ... --dry-run   # sem enviar
"""

import argparse
import sys
import time
from pathlib import Path
from collections import defaultdict

# Garantir UTF-8 no Windows (evita UnicodeEncodeError com caracteres box-drawing)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ─── Mapeamento domínio → código de tenant ────────────────────────────────────
DOMAIN_TENANT_MAP = {
    "revenue_cycle":       "rc",
    "clinical_operations": "co",
    "patient_access":      "pa",
    "platform_services":   "ps",
    "contract_extraction": "ce",
}

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("✗ requests não instalado. Execute: pip install requests")
    sys.exit(1)

# ─── Cores (terminal) ─────────────────────────────────────────────────────────
GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE   = "\033[0;34m"
RED    = "\033[0;31m"
NC     = "\033[0m"

def log(msg):   print(f"{BLUE}[deploy]{NC} {msg}")
def ok(msg):    print(f"{GREEN}✓{NC} {msg}")
def warn(msg):  print(f"{YELLOW}⚠{NC}  {msg}")
def err(msg):   print(f"{RED}✗{NC} {msg}", file=sys.stderr)


# ─── Parsing de argumentos ────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="Deploy BPMN/DMN no CIB Seven")
    parser.add_argument("--url",      default="http://localhost:8080/engine-rest")
    parser.add_argument("--user",     default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--source-dir", default="src/healthcare_platform",
                        help="Raiz onde ficam os subdomínios (default: src/healthcare_platform)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Listar o que seria deployado sem enviar")
    parser.add_argument("--bpmn-only", action="store_true")
    parser.add_argument("--dmn-only",  action="store_true")
    parser.add_argument("--domain", default=None,
                        help="Filtrar por domínio (ex: revenue_cycle). Deploya apenas arquivos deste domínio.")
    parser.add_argument("--tenant-prefix", default=None,
                        help="Prefixo do tenant (ex: Maezo → Maezo_rc). Sem prefixo = sem tenant.")
    parser.add_argument("--clean", action="store_true",
                        help="Remove TODOS os deployments existentes no engine antes de deployar.")
    return parser.parse_args()


# ─── Resolver tenant por caminho ──────────────────────────────────────────────
def resolve_tenant(file_path: Path, source_dir: Path, prefix: str) -> str | None:
    """Extrai domínio do path e retorna tenant-id. Ex: Maezo_rc"""
    try:
        rel = file_path.relative_to(source_dir)
        code = DOMAIN_TENANT_MAP.get(rel.parts[0])
        return f"{prefix}_{code}" if code else None
    except ValueError:
        return None


# ─── Limpar todos os deployments existentes ───────────────────────────────────
def clean_engine(session: requests.Session, url: str) -> None:
    """Remove todos os deployments do engine (cascade=true)."""
    log("── LIMPEZA ────────────────────────────────────────────────")
    log("Buscando deployments existentes ...")
    try:
        resp = session.get(f"{url}/deployment?maxResults=1000", timeout=30)
        deployments = resp.json()
    except Exception as e:
        err(f"Falha ao listar deployments: {e}")
        return

    if not deployments:
        ok("Nenhum deployment encontrado — engine já está limpo.")
        return

    log(f"Encontrados {len(deployments)} deployments — removendo ...")
    for d in deployments:
        did = d["id"]
        name = d.get("name", did)
        r = session.delete(
            f"{url}/deployment/{did}?cascade=true&skipCustomListeners=true",
            timeout=30,
        )
        if r.status_code == 204:
            print(f"  {GREEN}✓{NC} removido: {name}")
        else:
            warn(f"  falha ao remover '{name}': HTTP {r.status_code}")
    ok("Limpeza concluída.")


# ─── Utilitário: deploy de um conjunto de arquivos ───────────────────────────
def deploy_resources(
    session: requests.Session,
    url: str,
    deployment_name: str,
    files: list[Path],
    dry_run: bool = False,
    source: str = "bootstrap",
    tenant_id: str | None = None,
) -> bool:
    """Faz upload de uma lista de arquivos como um único deployment."""
    if not files:
        return True

    if dry_run:
        tenant_label = f" [{tenant_id}]" if tenant_id else ""
        log(f"  [dry-run] {deployment_name}{tenant_label}: {len(files)} arquivo(s)")
        return True

    multipart = [
        ("deployment-name",              (None, deployment_name)),
        ("enable-duplicate-filtering",   (None, "true")),
        ("deployment-source",            (None, source)),
    ]
    if tenant_id:
        multipart.append(("tenant-id", (None, tenant_id)))
    for path in files:
        multipart.append(
            (path.name, (path.name, path.read_bytes(), "application/xml"))
        )

    try:
        resp = session.post(f"{url}/deployment/create", files=multipart, timeout=60)
        if resp.status_code == 200:
            return True
        else:
            warn(f"  {deployment_name}: HTTP {resp.status_code} — {resp.text[:200]}")
            return False
    except requests.RequestException as e:
        warn(f"  {deployment_name}: erro de conexão — {e}")
        return False


# ─── Deploy BPMN ──────────────────────────────────────────────────────────────
def deploy_bpmn(session, url, source_dir: Path, dry_run: bool,
                domain: str | None = None, tenant_prefix: str | None = None) -> tuple[int, int]:
    """Deploya cada BPMN como um deployment individual."""
    log("Buscando arquivos BPMN ...")

    bpmn_files = sorted(
        p for p in source_dir.rglob("*.bpmn")
        if "archive" not in p.parts
        and "TEMPLATE_" not in p.name
    )

    if domain:
        bpmn_files = [p for p in bpmn_files if domain in p.parts]

    log(f"Encontrados: {len(bpmn_files)} arquivos BPMN")
    ok_count = err_count = 0

    for bpmn_path in bpmn_files:
        name = bpmn_path.stem  # ex: SP-RC-001_Scheduling_Registration
        tenant_id = resolve_tenant(bpmn_path, source_dir, tenant_prefix) if tenant_prefix else None
        tenant_label = f" [{tenant_id}]" if tenant_id else ""
        success = deploy_resources(
            session, url,
            deployment_name=name,
            files=[bpmn_path],
            dry_run=dry_run,
            tenant_id=tenant_id,
        )
        if success:
            ok_count += 1
            print(f"  {GREEN}✓{NC} {name}{tenant_label}")
        else:
            err_count += 1

    return ok_count, err_count


# ─── Deploy DMN (batches por subdiretório) ────────────────────────────────────
def deploy_dmn(session, url, source_dir: Path, dry_run: bool,
               domain: str | None = None, tenant_prefix: str | None = None) -> tuple[int, int]:
    """
    Agrupa arquivos DMN por subdiretório e faz um deployment por grupo.
    Com 1.274 arquivos em ~80 subdirs, resulta em ~80 deployments.
    """
    log("Buscando arquivos DMN ...")

    # Agrupar por diretório pai
    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for dmn_path in sorted(source_dir.rglob("*.dmn")):
        if domain and domain not in dmn_path.parts:
            continue
        by_dir[dmn_path.parent].append(dmn_path)
        

    total_files = sum(len(v) for v in by_dir.values())
    log(f"Encontrados: {total_files} arquivos DMN em {len(by_dir)} diretórios")

    ok_count = err_count = 0

    for dir_path, files in sorted(by_dir.items()):
        # Nome do deployment: "dmn-{domain}-{subdir}"
        # ex: dmn-clinical_operations-clinical_safety-aki
        rel = dir_path.relative_to(source_dir)
        deployment_name = "dmn-" + "-".join(rel.parts)
        tenant_id = resolve_tenant(files[0], source_dir, tenant_prefix) if tenant_prefix else None
        tenant_label = f" [{tenant_id}]" if tenant_id else ""

        success = deploy_resources(
            session, url,
            deployment_name=deployment_name,
            files=files,
            dry_run=dry_run,
            tenant_id=tenant_id,
        )
        if success:
            ok_count += len(files)
            print(f"  {GREEN}✓{NC} {deployment_name} ({len(files)} tabelas){tenant_label}")
        else:
            err_count += len(files)

    return ok_count, err_count


# ─── Verificar conectividade ──────────────────────────────────────────────────
def check_connection(session, url, user):
    log(f"Verificando conexão com CIB Seven: {url}")
    try:
        resp = session.get(f"{url}/engine", timeout=10)
        if resp.status_code == 200:
            engines = resp.json()
            engine_name = engines[0].get("name", "?") if engines else "?"
            ok(f"Conectado — engine: {engine_name}")
            return True
        else:
            err(f"CIB Seven retornou HTTP {resp.status_code}")
            return False
    except Exception as e:
        err(f"Falha ao conectar em {url}: {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    source_dir = Path(args.source_dir)

    if not source_dir.exists():
        err(f"Diretório não encontrado: {source_dir}")
        err(f"Execute o script a partir da raiz do projeto.")
        sys.exit(1)

    session = requests.Session()
    session.auth = HTTPBasicAuth(args.user, args.password)

    # Verificar conexão
    if not args.dry_run:
        if not check_connection(session, args.url, args.user):
            sys.exit(1)

    # Limpar engine se --clean
    if args.clean and not args.dry_run:
        print("")
        clean_engine(session, args.url)

    start = time.time()
    bpmn_ok = bpmn_err = 0
    dmn_ok = dmn_err = 0

    # Deploy BPMN
    if not args.dmn_only:
        print("")
        log("── BPMN ──────────────────────────────────────────────────────")
        bpmn_ok, bpmn_err = deploy_bpmn(
            session, args.url, source_dir, args.dry_run,
            domain=args.domain, tenant_prefix=args.tenant_prefix,
        )

    # Deploy DMN
    if not args.bpmn_only:
        print("")
        log("── DMN ───────────────────────────────────────────────────────")
        dmn_ok, dmn_err = deploy_dmn(
            session, args.url, source_dir, args.dry_run,
            domain=args.domain, tenant_prefix=args.tenant_prefix,
        )

    # Relatório
    elapsed = round(time.time() - start, 1)
    print("")
    log("── Relatório ─────────────────────────────────────────────────")
    print(f"  BPMN: {GREEN}{bpmn_ok} deployados{NC}  {RED}{bpmn_err} erros{NC}")
    print(f"  DMN:  {GREEN}{dmn_ok} deployados{NC}   {RED}{dmn_err} erros{NC}")
    print(f"  Tempo: {elapsed}s")

    if bpmn_err > 0 or dmn_err > 0:
        warn("Alguns deployments falharam — verifique os logs acima")
        sys.exit(1)
    else:
        ok("Todos os processos deployados com sucesso")

    if not args.dry_run:
        # Contar o que foi efetivamente deployado no engine
        try:
            n_proc = session.get(f"{args.url}/process-definition/count", timeout=10).json().get("count", "?")
            n_dec  = session.get(f"{args.url}/decision-definition/count", timeout=10).json().get("count", "?")
            print("")
            log(f"Estado atual do engine:")
            print(f"  Processos BPMN:   {n_proc}")
            print(f"  Decisões DMN:     {n_dec}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
