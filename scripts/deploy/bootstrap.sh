#!/usr/bin/env bash
# =============================================================================
# MAEZO — Bootstrap Automático do Ambiente
#
# Configura o stack após subir, sem intervenção manual:
#   1. Aguarda CIB Seven ficar healthy
#   2. Deploya todos os processos BPMN (57 arquivos) e tabelas DMN (1.274 arquivos)
#   3. Cria tópicos Kafka para CDC (tasy.{TENANT}.{TABLE})
#
# Uso:
#   bash scripts/deploy/bootstrap.sh                      # lê .env local
#   bash scripts/deploy/bootstrap.sh --env prod           # lê .env.prod
#   bash scripts/deploy/bootstrap.sh --skip-kafka         # pula criação de tópicos
#   bash scripts/deploy/bootstrap.sh --skip-bpmn          # pula BPMN/DMN
#
# Pré-requisitos:
#   - python3 com 'requests' (pip install requests)
#   - curl
# =============================================================================

set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────────
ENV_FILE=".env"
SKIP_BPMN=false
SKIP_KAFKA=false

# ─── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }

# ─── Parse argumentos ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)        ENV_FILE=".env.$2"; shift 2 ;;
    --skip-bpmn)  SKIP_BPMN=true; shift ;;
    --skip-kafka) SKIP_KAFKA=true; shift ;;
    --help|-h)
      echo "Uso: $0 [--env prod|staging] [--skip-bpmn] [--skip-kafka]"
      exit 0 ;;
    *) err "Argumento desconhecido: $1"; exit 1 ;;
  esac
done

# ─── Carregar .env ────────────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  ok "Env carregado: $ENV_FILE"
else
  warn "$ENV_FILE não encontrado — usando variáveis já exportadas"
fi

# ─── Configurações (com defaults) ─────────────────────────────────────────────
CIB7_HOST="${CIB7_HOST:-localhost}"
CIB7_PORT="${CIB7_PORT:-8080}"
CIB7_URL="http://${CIB7_HOST}:${CIB7_PORT}/engine-rest"
CIB7_USER="${CIB7_USER:-admin}"
CIB7_PASS="${CIB7_PASS:-admin}"

# Tenants ativos (espaço-separados)
TENANTS="${TENANTS:-hospital-a amh-sp-morumbi amh-rj-barra amh-mg-bh}"

# ─── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         MAEZO — Bootstrap Automático do Ambiente        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  CIB Seven: $CIB7_URL"
echo "  Tenants:   $TENANTS"
echo ""

# ─── Função: aguardar serviço HTTP ────────────────────────────────────────────
wait_for_service() {
  local url="$1"
  local name="$2"
  local max_wait="${3:-300}"
  local interval=10
  local elapsed=0

  log "Aguardando $name ..."
  while ! curl -sf --max-time 5 "$url" -o /dev/null 2>/dev/null; do
    elapsed=$((elapsed + interval))
    if [[ $elapsed -ge $max_wait ]]; then
      err "$name não ficou disponível em ${max_wait}s — abortando"
      exit 1
    fi
    printf "  \e[33m⟳\e[0m %ds / %ds \r" "$elapsed" "$max_wait"
    sleep "$interval"
  done
  echo ""
  ok "$name disponível"
}

# =============================================================================
# ETAPA 1 — Aguardar CIB Seven
# =============================================================================
echo ""
log "════════════════════════════════════════════"
log " ETAPA 1: CIB Seven"
log "════════════════════════════════════════════"

wait_for_service "$CIB7_URL/engine" "CIB Seven (engine-rest)" 300

# Verificar quantos processos já existem
existing=$(curl -sf -u "$CIB7_USER:$CIB7_PASS" \
  "$CIB7_URL/process-definition/count" 2>/dev/null \
  | grep -o '"count":[0-9]*' | grep -o '[0-9]*' || echo "0")
log "Processos já deployados: $existing"

# =============================================================================
# ETAPA 2 — Deploy BPMN + DMN
# =============================================================================
if [[ "$SKIP_BPMN" == "false" ]]; then
  echo ""
  log "════════════════════════════════════════════"
  log " ETAPA 2: Deploy BPMN + DMN"
  log "════════════════════════════════════════════"

  if ! command -v python3 &>/dev/null; then
    err "Python3 não encontrado — instale python3 e 'pip install requests'"
    err "Pule esta etapa com: --skip-bpmn"
    exit 1
  fi

  python3 scripts/deploy/deploy_processes.py \
    --url "$CIB7_URL" \
    --user "$CIB7_USER" \
    --password "$CIB7_PASS"

else
  warn "ETAPA 2: BPMN/DMN — pulando (--skip-bpmn)"
fi

# =============================================================================
# ETAPA 3 — Tópicos Kafka
# =============================================================================
if [[ "$SKIP_KAFKA" == "false" ]]; then
  echo ""
  log "════════════════════════════════════════════"
  log " ETAPA 3: Tópicos Kafka"
  log "════════════════════════════════════════════"

  # Detectar container Kafka
  KAFKA_CONTAINER=$(docker ps --format "{{.Names}}" 2>/dev/null \
    | grep -i kafka | grep -v exporter | head -1 || true)

  if [[ -z "$KAFKA_CONTAINER" ]]; then
    warn "Container Kafka não encontrado via docker ps"
    warn "Execute manualmente: bash scripts/deploy/create_kafka_topics.sh --bootstrap kafka:9092"
  else
    bash scripts/deploy/create_kafka_topics.sh \
      --container "$KAFKA_CONTAINER" \
      --tenants "$TENANTS"
  fi
else
  warn "ETAPA 3: Kafka — pulando (--skip-kafka)"
fi

# ─── Resumo final ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              BOOTSTRAP CONCLUÍDO                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Links úteis:"
printf "    CIB Seven Cockpit:  http://%s:%s/camunda/app/cockpit\n" "$CIB7_HOST" "$CIB7_PORT"
echo ""
echo "  Verificações:"
echo "    Processos deployados:"
echo "      curl -u \$CIB7_USER:\$CIB7_PASS $CIB7_URL/process-definition/count"
echo "    Decisões (DMN) deployadas:"
echo "      curl -u \$CIB7_USER:\$CIB7_PASS $CIB7_URL/decision-definition/count"
echo "    Tópicos Kafka:"
echo "      docker exec \$(docker ps -qf name=kafka) kafka-topics.sh --bootstrap-server localhost:9092 --list"
echo ""
