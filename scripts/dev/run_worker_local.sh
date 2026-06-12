#!/usr/bin/env bash
# =============================================================================
# MAEZO — Rodar worker localmente (Windows Git Bash / Linux)
#
# Conecta na infra do servidor Linux remoto.
# Permite debug com breakpoints no VSCode.
#
# Uso:
#   bash scripts/dev/run_worker_local.sh --domain revenue_cycle
#   bash scripts/dev/run_worker_local.sh --domain clinical_operations
#   bash scripts/dev/run_worker_local.sh --topics billing-calculate-charges,identify-glosa
#   bash scripts/dev/run_worker_local.sh --all
#
# Pre-requisitos:
#   1. Python 3.11+ com dependencias instaladas: pip install -e .
#   2. Arquivo .env.dev.windows.local com DEV_SERVER_IP configurado
#      (copie .env.dev.windows e edite o IP)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[worker]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }

# -- Carregar .env.dev.windows.local -----------------------------------------
ENV_FILE=".env.dev.windows.local"
if [[ ! -f "$ENV_FILE" ]]; then
  ENV_FILE=".env.dev.windows"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Arquivo $ENV_FILE nao encontrado."
  echo "  Copie .env.dev.windows para .env.dev.windows.local e configure DEV_SERVER_IP"
  exit 1
fi

# Ler variaveis do .env (suporta ${VAR} expansion)
eval_env_file() {
  local file="$1"
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Ignorar comentarios e linhas vazias
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    # Exportar variavel
    export "${line%%#*}"
  done < "$file"
}

eval_env_file "$ENV_FILE"

# Verificar que IP foi configurado
if [[ "${DEV_SERVER_IP:-}" == "<SERVER_IP>" || -z "${DEV_SERVER_IP:-}" ]]; then
  fail "DEV_SERVER_IP nao configurado em $ENV_FILE"
  echo "  Edite o arquivo e substitua <SERVER_IP> pelo IP do servidor Linux"
  exit 1
fi

# -- Expandir variaveis que usam ${DEV_SERVER_IP} ----------------------------
export CIBSEVEN_ENGINE_URL="http://${DEV_SERVER_IP}:8085/engine-rest"
export CIB7_BASE_URL="http://${DEV_SERVER_IP}:8085/engine-rest"
export CIB7_USER="${CIB7_USER:-admin}"
export CIB7_PASSWORD="${CIB7_PASSWORD:-admin}"
export FHIR_BASE_URL="http://${DEV_SERVER_IP}:8082/fhir"
export DATABASE_URL="postgresql://maestro:maestro_dev@${DEV_SERVER_IP}:5435/maestro"
export KAFKA_BOOTSTRAP_SERVERS="${DEV_SERVER_IP}:9092"
export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"
export PYTHONPATH="src"

# -- Verificar conexao com CIB Seven -----------------------------------------
log "Testando conexao com CIB Seven em ${DEV_SERVER_IP}:8085..."
if curl -sf -u admin:admin "http://${DEV_SERVER_IP}:8085/engine-rest/engine" &>/dev/null; then
  ok "CIB Seven acessivel"
else
  fail "CIB Seven nao acessivel em http://${DEV_SERVER_IP}:8085/engine-rest"
  echo "  Verifique se o servidor esta rodando: ssh austa@${DEV_SERVER_IP} 'docker ps'"
  exit 1
fi

# -- Verificar Python --------------------------------------------------------
if ! python -c "import healthcare_platform" 2>/dev/null && \
   ! python -c "import sys; sys.path.insert(0,'src'); import healthcare_platform" 2>/dev/null; then
  warn "Modulo healthcare_platform nao encontrado. Executando com PYTHONPATH=src"
fi

# -- Executar worker ----------------------------------------------------------
log "Iniciando worker..."
log "  Engine: $CIBSEVEN_ENGINE_URL"
log "  FHIR:   $FHIR_BASE_URL"
log "  DB:     postgresql://maestro:***@${DEV_SERVER_IP}:5435/maestro"
log "  Args:   $*"
echo ""

python -m healthcare_platform.shared.runtime.worker_runner "$@"
