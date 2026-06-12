#!/usr/bin/env bash
# =============================================================================
# MAEZO — Inicialização do ambiente LOCAL
#
# Sobe todos os serviços com PostgreSQL local (simula RDS)
# Útil para desenvolvimento, validação e testes de integração
#
# Uso:
#   bash scripts/start_local.sh            # sobe tudo
#   bash scripts/start_local.sh --infra    # só infra (postgres, kafka, cib7, fhir)
#   bash scripts/start_local.sh --down     # para e remove containers
#   bash scripts/start_local.sh --reset    # para, remove volumes e recomeça
#   bash scripts/start_local.sh --logs     # segue logs em tempo real
# =============================================================================

set -euo pipefail

COMPOSE="docker compose -f docker-compose.local.yml"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }

# ─── Parse args ──────────────────────────────────────────────────────────────
MODE="up"
case "${1:-}" in
  --infra)  MODE="infra" ;;
  --down)   MODE="down" ;;
  --reset)  MODE="reset" ;;
  --logs)   MODE="logs" ;;
  --help|-h)
    echo "Uso: $0 [--infra|--down|--reset|--logs]"
    echo ""
    echo "  (sem args)  Sobe todos os serviços"
    echo "  --infra     Sobe apenas infraestrutura (postgres, kafka, cib7, fhir, debezium, prometheus, grafana)"
    echo "  --down      Para e remove containers (mantém volumes/dados)"
    echo "  --reset     Para, remove containers E volumes (banco zerado)"
    echo "  --logs      Segue logs de todos os serviços"
    exit 0 ;;
esac

# ─── Down ────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "down" ]]; then
  log "Parando serviços..."
  $COMPOSE down
  ok "Serviços parados (volumes mantidos)"
  exit 0
fi

# ─── Reset ───────────────────────────────────────────────────────────────────
if [[ "$MODE" == "reset" ]]; then
  warn "Isso vai APAGAR todos os dados (bancos, kafka). Confirmar? [y/N]"
  read -r confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Cancelado."
    exit 0
  fi
  log "Removendo containers e volumes..."
  $COMPOSE down -v --remove-orphans
  ok "Reset completo. Execute novamente para subir do zero."
  exit 0
fi

# ─── Logs ────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "logs" ]]; then
  $COMPOSE logs -f
  exit 0
fi

# ─── Banner ──────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║        MAEZO — Ambiente Local (desenvolvimento)         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ─── Verificações ────────────────────────────────────────────────────────────
log "Verificando pré-requisitos..."

if ! docker info &>/dev/null; then
  echo -e "${RED}Docker não está rodando.${NC} Inicie o Docker Desktop e tente novamente."
  exit 1
fi
ok "Docker disponível"

# docker compose v2
if ! docker compose version &>/dev/null 2>&1; then
  echo -e "${RED}docker compose v2 não encontrado.${NC}"
  echo "  Atualize o Docker Desktop ou instale: https://docs.docker.com/compose/install/"
  exit 1
fi
ok "docker compose v2 disponível"

# ─── Build das imagens dos workers (se necessário) ───────────────────────────
log "Verificando se as imagens precisam ser buildadas..."

if [[ "$MODE" == "up" ]]; then
  log "Buildando imagens dos workers (isso pode demorar na primeira vez)..."
  $COMPOSE build --parallel workers_rc workers_co workers_pa workers_ps ce_api
  ok "Imagens buildadas"
fi

# ─── Subir infraestrutura primeiro ───────────────────────────────────────────
INFRA_SERVICES="postgres kafka cib7 hapi_fhir debezium kafka_exporter postgres_exporter prometheus grafana"

log "Subindo infraestrutura: $INFRA_SERVICES"
$COMPOSE up -d $INFRA_SERVICES

# ─── Aguardar PostgreSQL ─────────────────────────────────────────────────────
log "Aguardando PostgreSQL ficar pronto..."
MAX_WAIT=60
WAITED=0
until docker compose -f docker-compose.local.yml exec -T postgres \
    pg_isready -U maestro -d cibseven &>/dev/null 2>&1; do
  sleep 2
  WAITED=$((WAITED + 2))
  if [[ $WAITED -ge $MAX_WAIT ]]; then
    echo -e "${RED}PostgreSQL não ficou pronto em ${MAX_WAIT}s${NC}"
    $COMPOSE logs postgres | tail -20
    exit 1
  fi
  echo -n "."
done
echo ""
ok "PostgreSQL pronto"

# ─── Aguardar CIB Seven ──────────────────────────────────────────────────────
log "Aguardando CIB Seven BPM Engine (pode levar ~90s na primeira inicialização)..."
MAX_WAIT=180
WAITED=0
until curl -s -u admin:admin http://localhost:8080/engine-rest/engine &>/dev/null 2>&1; do
  sleep 5
  WAITED=$((WAITED + 5))
  if [[ $WAITED -ge $MAX_WAIT ]]; then
    warn "CIB Seven não respondeu em ${MAX_WAIT}s — pode precisar de mais tempo"
    warn "Verifique: docker compose -f docker-compose.local.yml logs cib7"
    break
  fi
  echo -n "."
done
echo ""
if curl -s -u admin:admin http://localhost:8080/engine-rest/engine &>/dev/null 2>&1; then
  ok "CIB Seven pronto"
fi

# ─── Subir workers (modo completo) ────────────────────────────────────────────
if [[ "$MODE" == "up" ]]; then
  log "Subindo workers..."
  $COMPOSE up -d workers_rc workers_co workers_pa workers_ps ce_api
  ok "Workers iniciados"
fi

# ─── Status final ─────────────────────────────────────────────────────────────
echo ""
log "Status dos serviços:"
$COMPOSE ps

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              AMBIENTE LOCAL PRONTO                          ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  CIB Seven Cockpit:  http://localhost:8080/cibseven         ║"
echo "║  HAPI FHIR:          http://localhost:8082/fhir/metadata     ║"
echo "║  CE API docs:        http://localhost:8000/docs              ║"
echo "║  Debezium:           http://localhost:8083/connectors        ║"
echo "║  PostgreSQL:         localhost:5432 (maestro/maestro_local)  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Workers health:     http://localhost:810{0-3}/health        ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Prometheus:         http://localhost:9090                   ║"
echo "║  Grafana:            http://localhost:3000  (admin/admin)    ║"
echo "║    └─ Dashboard:     MAEZO → Workers Overview               ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Logs:   bash scripts/start_local.sh --logs                 ║"
echo "║  Stop:   bash scripts/start_local.sh --down                 ║"
echo "║  Reset:  bash scripts/start_local.sh --reset                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Smoke test rápido
log "Executando smoke test rápido..."
sleep 5
bash scripts/dev/smoke_test.sh http://localhost 2>/dev/null || true
