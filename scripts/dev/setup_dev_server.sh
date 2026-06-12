#!/usr/bin/env bash
# =============================================================================
# MAEZO — Setup do ambiente DEV no servidor Linux
#
# Executa no servidor:
#   1. Para containers Camunda antigos (com confirmacao)
#   2. Sobe stack dev (PostgreSQL + Kafka + CIB Seven + HAPI FHIR)
#   3. Deploya BPMN/DMN no CIB Seven
#   4. Popula HAPI FHIR com dados stub
#
# Uso:
#   bash scripts/dev/setup_dev_server.sh              # setup completo
#   bash scripts/dev/setup_dev_server.sh --skip-stop   # nao para containers antigos
#   bash scripts/dev/setup_dev_server.sh --down        # para stack dev
#   bash scripts/dev/setup_dev_server.sh --reset       # para + apaga volumes
#   bash scripts/dev/setup_dev_server.sh --status      # mostra status
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

COMPOSE="docker compose -f docker-compose.dev.yml"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[maezo-dev]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }

# -- Parse args ---------------------------------------------------------------
MODE="setup"
SKIP_STOP=false
case "${1:-}" in
  --skip-stop) SKIP_STOP=true ;;
  --down)      MODE="down" ;;
  --reset)     MODE="reset" ;;
  --status)    MODE="status" ;;
  --help|-h)
    echo "Uso: $0 [--skip-stop|--down|--reset|--status]"
    exit 0 ;;
esac

# -- Down ---------------------------------------------------------------------
if [[ "$MODE" == "down" ]]; then
  log "Parando stack dev..."
  $COMPOSE down
  ok "Stack dev parada (volumes mantidos)"
  exit 0
fi

# -- Reset --------------------------------------------------------------------
if [[ "$MODE" == "reset" ]]; then
  warn "Isso vai APAGAR todos os dados (bancos, kafka). Confirmar? [y/N]"
  read -r confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Cancelado."
    exit 0
  fi
  $COMPOSE down -v --remove-orphans
  ok "Reset completo"
  exit 0
fi

# -- Status -------------------------------------------------------------------
if [[ "$MODE" == "status" ]]; then
  $COMPOSE ps
  exit 0
fi

# =============================================================================
# Setup completo
# =============================================================================

echo "╔══════════════════════════════════════════════════════════╗"
echo "║        MAEZO — Setup Ambiente DEV (servidor)            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# -- 1. Parar containers Camunda antigos (se necessario) ----------------------
if [[ "$SKIP_STOP" == false ]]; then
  CAMUNDA_CONTAINERS="camunda_tomcat_dev camunda_postgres_dev camunda_tomcat camunda_postgres"
  RUNNING=""
  for c in $CAMUNDA_CONTAINERS; do
    if docker ps -q -f name="^${c}$" 2>/dev/null | grep -q .; then
      RUNNING="$RUNNING $c"
    fi
  done

  if [[ -n "$RUNNING" ]]; then
    warn "Containers Camunda rodando:$RUNNING"
    warn "Parar esses containers? (imagens serao mantidas) [y/N]"
    read -r confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
      log "Parando containers Camunda..."
      for c in $RUNNING; do
        docker stop "$c" 2>/dev/null && ok "Parado: $c" || true
      done
    else
      warn "Containers Camunda mantidos — possiveis conflitos de porta (5432, 8080)"
    fi
  else
    ok "Nenhum container Camunda rodando"
  fi
fi

# -- 2. Verificar pre-requisitos ----------------------------------------------
log "Verificando pre-requisitos..."

if ! docker info &>/dev/null; then
  fail "Docker nao esta rodando"
  exit 1
fi
ok "Docker disponivel"

if ! docker compose version &>/dev/null 2>&1; then
  fail "docker compose v2 nao encontrado"
  exit 1
fi
ok "docker compose v2 disponivel"

# Verificar que metabase continua rodando
if docker ps -q -f name="metabase_prd" | grep -q .; then
  ok "Metabase continua rodando (porta 3030)"
fi

# -- 3. Subir stack dev -------------------------------------------------------
log "Subindo stack dev (PostgreSQL + Kafka + CIB Seven + HAPI FHIR)..."
$COMPOSE up -d

# -- 4. Aguardar PostgreSQL ---------------------------------------------------
log "Aguardando PostgreSQL..."
MAX_WAIT=60
WAITED=0
until docker compose -f docker-compose.dev.yml exec -T postgres \
    pg_isready -U maestro -d cibseven &>/dev/null 2>&1; do
  sleep 2
  WAITED=$((WAITED + 2))
  if [[ $WAITED -ge $MAX_WAIT ]]; then
    fail "PostgreSQL nao ficou pronto em ${MAX_WAIT}s"
    $COMPOSE logs postgres | tail -10
    exit 1
  fi
  echo -n "."
done
echo ""
ok "PostgreSQL pronto"

# -- 5. Aguardar CIB Seven ---------------------------------------------------
log "Aguardando CIB Seven (pode levar ~90s na primeira vez)..."
MAX_WAIT=180
WAITED=0
until curl -sf -u admin:admin http://localhost:8085/engine-rest/engine &>/dev/null; do
  sleep 5
  WAITED=$((WAITED + 5))
  if [[ $WAITED -ge $MAX_WAIT ]]; then
    warn "CIB Seven nao respondeu em ${MAX_WAIT}s — continuando mesmo assim"
    break
  fi
  echo -n "."
done
echo ""
if curl -sf -u admin:admin http://localhost:8085/engine-rest/engine &>/dev/null; then
  ok "CIB Seven pronto"
fi

# -- 6. Deploy BPMN/DMN ------------------------------------------------------
log "Deployando processos BPMN e tabelas DMN..."
if [[ -f scripts/deploy/deploy_processes.py ]]; then
  # Instalar requests se nao disponivel
  python3 -c "import requests" 2>/dev/null || pip3 install requests --quiet
  python3 scripts/deploy/deploy_processes.py \
    --url http://localhost:8085/engine-rest \
    --user admin --password admin
  ok "BPMN/DMN deployados"
else
  warn "scripts/deploy/deploy_processes.py nao encontrado — skip"
fi

# -- 7. Seed FHIR stub data --------------------------------------------------
log "Populando HAPI FHIR com dados stub..."
if [[ -f scripts/dev/seed_fhir_data.py ]]; then
  python3 -c "import httpx" 2>/dev/null || pip3 install httpx --quiet
  python3 scripts/dev/seed_fhir_data.py --url http://localhost:8082/fhir
  ok "FHIR seed completo"
else
  warn "scripts/dev/seed_fhir_data.py nao encontrado — skip"
fi

# -- 8. Status final ----------------------------------------------------------
echo ""
$COMPOSE ps
echo ""

SERVER_IP=$(hostname -I | awk '{print $1}')

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              AMBIENTE DEV PRONTO                            ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  CIB Seven Cockpit: http://${SERVER_IP}:8085/cibseven       "
echo "║  CIB Seven REST:    http://${SERVER_IP}:8085/engine-rest     "
echo "║  HAPI FHIR:         http://${SERVER_IP}:8082/fhir/metadata   "
echo "║  PostgreSQL:        ${SERVER_IP}:5435 (maestro/maestro_dev)  "
echo "║  Kafka:             ${SERVER_IP}:9092                        "
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Metabase:          http://${SERVER_IP}:3030  (inalterado)   "
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Para workers no Windows, configure .env.dev.windows com:    "
echo "║    DEV_SERVER_IP=${SERVER_IP}                                 "
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Parar:  bash scripts/dev/setup_dev_server.sh --down         "
echo "║  Reset:  bash scripts/dev/setup_dev_server.sh --reset        "
echo "║  Status: bash scripts/dev/setup_dev_server.sh --status       "
echo "╚══════════════════════════════════════════════════════════════╝"
