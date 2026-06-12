#!/usr/bin/env bash
# =============================================================================
# MAEZO — Deploy Script para Docker Swarm
#
# Uso:
#   bash scripts/deploy_swarm.sh [--env prod|staging] [--tag <image-tag>]
#
# Exemplos:
#   bash scripts/deploy_swarm.sh                       # usa .env + tag=latest
#   bash scripts/deploy_swarm.sh --tag 1bf490d         # SHA específico
#   bash scripts/deploy_swarm.sh --env prod --tag HEAD # usa git HEAD
#
# Pré-requisitos:
#   - Docker Swarm inicializado (docker swarm init)
#   - Secrets criados (ver docs/runbooks/DEPLOYMENT.md seção 1)
#   - .env preenchido (copiar de .env.prod.example)
# =============================================================================

set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────────
ENV_FILE=".env"
IMAGE_TAG="${IMAGE_TAG:-latest}"
STACK_NAME="maestro"
COMPOSE_FILE="docker-compose.swarm.yml"
DRY_RUN=false

# ─── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }

# ─── Parse argumentos ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENV_FILE=".env.$2"; shift 2 ;;
    --tag)
      if [[ "$2" == "HEAD" ]]; then
        IMAGE_TAG=$(git rev-parse --short HEAD)
      else
        IMAGE_TAG="$2"
      fi
      shift 2 ;;
    --dry-run)  DRY_RUN=true; shift ;;
    --help|-h)
      echo "Uso: $0 [--env prod|staging] [--tag <sha|latest|HEAD>] [--dry-run]"
      exit 0 ;;
    *) err "Argumento desconhecido: $1"; exit 1 ;;
  esac
done

# ─── Banner ────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║      MAEZO — Docker Swarm Deploy                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Stack:     $STACK_NAME"
echo "  Compose:   $COMPOSE_FILE"
echo "  Env file:  $ENV_FILE"
echo "  Image tag: $IMAGE_TAG"
[[ "$DRY_RUN" == "true" ]] && echo -e "  Modo:      ${YELLOW}DRY-RUN (sem alterações)${NC}"
echo ""

# ─── 1. Verificações pré-deploy ───────────────────────────────────────────────
log "Verificações pré-deploy..."

# Docker disponível
if ! docker info &>/dev/null; then
  err "Docker não disponível. Verifique se o daemon está rodando."
  exit 1
fi
ok "Docker disponível"

# Swarm ativo
if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
  err "Docker Swarm não inicializado. Execute: docker swarm init"
  exit 1
fi
ok "Docker Swarm ativo"

# Arquivo .env existe
if [[ ! -f "$ENV_FILE" ]]; then
  err "Arquivo $ENV_FILE não encontrado."
  echo "  Copie .env.prod.example para $ENV_FILE e preencha os valores."
  exit 1
fi
ok "Env file: $ENV_FILE"

# Compose file existe
if [[ ! -f "$COMPOSE_FILE" ]]; then
  err "$COMPOSE_FILE não encontrado."
  exit 1
fi
ok "Compose file: $COMPOSE_FILE"

# Carregar variáveis do .env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export IMAGE_TAG

# Verificar variáveis obrigatórias
REQUIRED_VARS=(RDS_HOST RDS_USER PG_PASS DOMAIN ACME_EMAIL KAFKA_CLUSTER_ID CIB7_USER CIB7_PASS)
MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]] || [[ "${!var}" == PREENCHER* ]]; then
    MISSING_VARS+=("$var")
  fi
done

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
  err "Variáveis obrigatórias não preenchidas:"
  for v in "${MISSING_VARS[@]}"; do
    echo "    - $v"
  done
  echo ""
  echo "  Edite $ENV_FILE e preencha os valores."
  exit 1
fi
ok "Variáveis obrigatórias presentes"

# Verificar secrets Docker
REQUIRED_SECRETS=(postgres_password)
MISSING_SECRETS=()
for secret in "${REQUIRED_SECRETS[@]}"; do
  if ! docker secret inspect "$secret" &>/dev/null 2>&1; then
    MISSING_SECRETS+=("$secret")
  fi
done

if [[ ${#MISSING_SECRETS[@]} -gt 0 ]]; then
  err "Docker Swarm Secrets não encontrados:"
  for s in "${MISSING_SECRETS[@]}"; do
    echo "    - $s"
  done
  echo ""
  echo "  Crie os secrets (ver DEPLOYMENT.md seção 1):"
  echo "    echo 'senha' | docker secret create postgres_password -"
  exit 1
fi
ok "Docker Swarm Secrets presentes (${#REQUIRED_SECRETS[@]}/${#REQUIRED_SECRETS[@]})"

# ─── 2. Validar compose file ──────────────────────────────────────────────────
log "Validando $COMPOSE_FILE..."
if docker compose -f "$COMPOSE_FILE" config > /dev/null 2>&1; then
  ok "Sintaxe válida"
else
  err "Erro de sintaxe no $COMPOSE_FILE:"
  docker compose -f "$COMPOSE_FILE" config 2>&1 | tail -20
  exit 1
fi

# ─── 3. Testar conectividade RDS ──────────────────────────────────────────────
log "Testando conectividade com RDS ($RDS_HOST)..."
if command -v nc &>/dev/null; then
  if nc -zw5 "$RDS_HOST" 5432 2>/dev/null; then
    ok "RDS acessível em $RDS_HOST:5432"
  else
    warn "Não foi possível conectar ao RDS $RDS_HOST:5432 (pode ser normal se firewall bloqueia)"
  fi
else
  warn "nc não disponível — pulando teste de conectividade RDS"
fi

# ─── 4. Dry-run ou deploy ─────────────────────────────────────────────────────
echo ""
if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY-RUN: Gerando configuração resolvida..."
  docker compose -f "$COMPOSE_FILE" config
  echo ""
  ok "Dry-run concluído. Sem alterações aplicadas."
  exit 0
fi

# Confirmação manual (não-interativo em CI)
if [[ -t 0 ]]; then
  echo -e "${YELLOW}Prestes a fazer deploy do stack '$STACK_NAME' com IMAGE_TAG=$IMAGE_TAG${NC}"
  read -r -p "Confirmar? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    log "Deploy cancelado."
    exit 0
  fi
fi

# ─── 5. Deploy ────────────────────────────────────────────────────────────────
log "Iniciando deploy do stack '$STACK_NAME'..."
DEPLOY_START=$(date +%s)

docker stack deploy \
  -c "$COMPOSE_FILE" \
  --with-registry-auth \
  --prune \
  "$STACK_NAME"

ok "Stack deployado. Aguardando estabilização dos serviços..."

# ─── 6. Aguardar serviços ficarem prontos ────────────────────────────────────
WAIT_SECONDS=90
log "Aguardando $WAIT_SECONDS segundos para serviços iniciarem..."
sleep "$WAIT_SECONDS"

# Verificar se todos os serviços têm réplicas desejadas
echo ""
log "Status dos serviços:"
docker service ls --format "table {{.Name}}\t{{.Replicas}}\t{{.Image}}" | grep "$STACK_NAME"

# Contar serviços com problemas
UNHEALTHY=$(docker service ls --format "{{.Name}} {{.Replicas}}" | grep "$STACK_NAME" | awk '{split($2,a,"/"); if(a[1]!=a[2]) print $1}')
if [[ -n "$UNHEALTHY" ]]; then
  warn "Serviços com réplicas incompletas:"
  echo "$UNHEALTHY" | while read -r svc; do
    echo "    - $svc"
    docker service ps "$svc" --no-trunc --filter "desired-state=running" | tail -3
  done
fi

# ─── 7. Smoke test rápido ─────────────────────────────────────────────────────
echo ""
log "Executando smoke test rápido..."

CIB7_PORT="${CIB7_PORT:-8080}"
FHIR_PORT="${FHIR_PORT:-8082}"

# CIB Seven
if curl -s -o /dev/null -w "%{http_code}" \
    -u "${CIB7_USER}:${CIB7_PASS}" \
    "http://localhost:${CIB7_PORT}/engine-rest/engine" \
    --max-time 10 | grep -q "200"; then
  ok "CIB Seven: UP"
else
  warn "CIB Seven: não respondeu ainda (pode precisar de mais tempo para iniciar)"
fi

# HAPI FHIR
if curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:${FHIR_PORT}/fhir/metadata" \
    --max-time 10 | grep -q "200"; then
  ok "HAPI FHIR: UP"
else
  warn "HAPI FHIR: não respondeu ainda (start_period: 90s)"
fi

# ─── 8. Bootstrap automático (BPMN + Kafka) ──────────────────────────────────
echo ""
log "Executando bootstrap automático (BPMN + Kafka)..."
if bash scripts/deploy/bootstrap.sh --env "$ENV_FILE"; then
  ok "Bootstrap concluído"
else
  warn "Bootstrap retornou erros — verifique acima"
  warn "Execute manualmente: bash scripts/deploy/bootstrap.sh --env $ENV_FILE"
fi

# ─── 9. Resumo ────────────────────────────────────────────────────────────────
DEPLOY_END=$(date +%s)
DEPLOY_TIME=$((DEPLOY_END - DEPLOY_START))

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                   DEPLOY CONCLUÍDO                      ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  %-25s %-30s ║\n" "Stack:" "$STACK_NAME"
printf "║  %-25s %-30s ║\n" "Image tag:" "$IMAGE_TAG"
printf "║  %-25s %-30s ║\n" "Tempo total:" "${DEPLOY_TIME}s"
printf "║  %-25s %-30s ║\n" "Data:" "$(date '+%Y-%m-%d %H:%M:%S')"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Próximos passos:"
echo "    1. Verificar logs:   docker service logs maestro_workers_rc -f"
echo "    2. Smoke test:       bash scripts/dev/smoke_test.sh https://bpm.${DOMAIN}"
echo "    3. Grafana:          https://grafana.${DOMAIN}"
echo "    4. CIB7 Cockpit:     https://bpm.${DOMAIN}/camunda/app/cockpit"
echo ""
echo "  Bootstrap manual (se necessário):"
echo "    bash scripts/deploy/bootstrap.sh --env $ENV_FILE"
echo ""
echo "  Em caso de problema:"
echo "    Rollback:  docker service update --image <sha-anterior> maestro_workers_rc"
echo "    Logs:      docker service logs <servico> --tail 100"
echo "    Ver doc:   docs/runbooks/INCIDENT_RESPONSE.md"
