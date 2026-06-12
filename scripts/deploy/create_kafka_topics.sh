#!/usr/bin/env bash
# =============================================================================
# MAEZO — Criação de Tópicos Kafka
#
# Cria os tópicos necessários para:
#   1. CDC Tasy → CIB Seven  (tasy.{TENANT}.{TABLE})
#   2. Dead-letter queue     (bridge.dead-letter)
#   3. Tópicos internos Debezium (_debezium.*)
#
# Uso:
#   bash scripts/create_kafka_topics.sh
#   bash scripts/create_kafka_topics.sh --container kafka_container_name
#   bash scripts/create_kafka_topics.sh --bootstrap kafka:9092
#   bash scripts/create_kafka_topics.sh --tenants "hospital-a amh-sp-morumbi"
#   bash scripts/create_kafka_topics.sh --dry-run
# =============================================================================

set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────────
KAFKA_CONTAINER=""
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-localhost:9092}"
TENANTS="${TENANTS:-hospital-a amh-sp-morumbi amh-rj-barra amh-mg-bh}"
DRY_RUN=false

# Tabelas CDC do ERP Tasy (fontes de eventos)
CDC_TABLES=(
  ATENDIMENTO          # Episódio de atendimento (admissão, alta)
  CONTA_MEDICA         # Conta do paciente (billing)
  ITEM_CONTA           # Itens faturáveis
  PROCEDIMENTO         # Procedimentos realizados
  EVOLUCAO_CLINICA     # Evoluções do prontuário
  PRESCRICAO           # Prescrições médicas
  RESULTADO_EXAME      # Resultados de exames
)

# Partições por tipo de tópico
PARTITIONS_CDC=3          # CDC: paralelismo por domínio
PARTITIONS_DLQ=1          # Dead-letter: single partition (ordem garantida)
PARTITIONS_INTERNAL=1     # Debezium internos

# Retenção
RETENTION_CDC_MS=$((7 * 24 * 3600 * 1000))    # 7 dias
RETENTION_DLQ_MS=$((30 * 24 * 3600 * 1000))   # 30 dias (análise de falhas)

# ─── Cores ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[kafka]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }

# ─── Parse argumentos ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --container)  KAFKA_CONTAINER="$2"; shift 2 ;;
    --bootstrap)  KAFKA_BOOTSTRAP="$2"; shift 2 ;;
    --tenants)    TENANTS="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --help|-h)
      echo "Uso: $0 [--container NAME] [--bootstrap HOST:PORT] [--tenants 'a b c'] [--dry-run]"
      exit 0 ;;
    *) err "Argumento desconhecido: $1"; exit 1 ;;
  esac
done

# ─── Detectar container Kafka se não foi especificado ─────────────────────────
if [[ -z "$KAFKA_CONTAINER" ]]; then
  KAFKA_CONTAINER=$(docker ps --format "{{.Names}}" 2>/dev/null \
    | grep -iE "kafka" | grep -viE "exporter|ui|connect" | head -1 || true)
fi

# ─── Função: executar kafka-topics.sh ─────────────────────────────────────────
kafka_topics() {
  if [[ -n "$KAFKA_CONTAINER" ]]; then
    docker exec "$KAFKA_CONTAINER" kafka-topics.sh \
      --bootstrap-server localhost:9092 "$@"
  else
    # Fallback: kafka-topics.sh no PATH (sem container)
    kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP" "$@"
  fi
}

# ─── Função: criar tópico (idempotente) ───────────────────────────────────────
create_topic() {
  local topic="$1"
  local partitions="${2:-$PARTITIONS_CDC}"
  local replication="${3:-1}"
  local retention="${4:-$RETENTION_CDC_MS}"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [dry-run] $topic (partitions=$partitions, retention=${retention}ms)"
    return 0
  fi

  local output
  output=$(kafka_topics \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor "$replication" \
    --config "retention.ms=$retention" \
    2>&1 || true)

  if echo "$output" | grep -qiE "Created topic|already exists"; then
    ok "$topic"
  else
    warn "$topic — $output"
  fi
}

# ─── Banner ───────────────────────────────────────────────────────────────────
echo ""
log "════════════════════════════════════════════════════"
log "  Criação de Tópicos Kafka — MAEZO"
log "════════════════════════════════════════════════════"

if [[ -n "$KAFKA_CONTAINER" ]]; then
  log "  Container: $KAFKA_CONTAINER"
else
  log "  Bootstrap: $KAFKA_BOOTSTRAP"
fi
log "  Tenants: $TENANTS"
[[ "$DRY_RUN" == "true" ]] && warn "  Modo: DRY-RUN (sem alterações)"
echo ""

# ─── 1. Tópicos CDC por tenant × tabela ──────────────────────────────────────
log "── 1. Tópicos CDC Tasy → CIB Seven ─────────────────"
log "   Padrão: tasy.{TENANT}.{TABLE}"
echo ""

total_cdc=0
for tenant in $TENANTS; do
  log "Tenant: $tenant"
  for table in "${CDC_TABLES[@]}"; do
    topic="tasy.${tenant}.${table}"
    create_topic "$topic" "$PARTITIONS_CDC" 1 "$RETENTION_CDC_MS"
    total_cdc=$((total_cdc + 1))
  done
  echo ""
done

# ─── 2. Dead-letter queue ─────────────────────────────────────────────────────
log "── 2. Dead Letter Queue ─────────────────────────────"
create_topic "bridge.dead-letter" "$PARTITIONS_DLQ" 1 "$RETENTION_DLQ_MS"
echo ""

# ─── 3. Tópicos internos Debezium ────────────────────────────────────────────
log "── 3. Tópicos Internos Debezium ─────────────────────"
create_topic "_debezium.config"  "$PARTITIONS_INTERNAL" 1 -1   # -1 = retenção infinita
create_topic "_debezium.offsets" "$PARTITIONS_INTERNAL" 1 -1
create_topic "_debezium.status"  "$PARTITIONS_INTERNAL" 1 -1
echo ""

# ─── 4. Tópico de notificações internas ──────────────────────────────────────
log "── 4. Tópico de Notificações Internas ───────────────"
create_topic "maestro.notifications" 1 1 "$RETENTION_CDC_MS"
echo ""

# ─── Resumo ───────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════"

if [[ "$DRY_RUN" != "true" ]]; then
  echo ""
  log "Verificando tópicos criados ..."
  kafka_count=$(kafka_topics --list 2>/dev/null | grep -cE "^tasy\.|^bridge\.|^_debezium\.|^maestro\." || echo "0")
  ok "Tópicos MAEZO no cluster: $kafka_count"

  echo ""
  log "Lista de tópicos:"
  kafka_topics --list 2>/dev/null \
    | grep -E "^tasy\.|^bridge\.|^_debezium\.|^maestro\." \
    | sort \
    | sed 's/^/    /'
fi

echo ""
total_tópicos=$((total_cdc + 1 + 3 + 1))
ok "Concluído: $total_tópicos tópicos processados"
echo ""
