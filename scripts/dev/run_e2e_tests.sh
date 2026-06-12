#!/usr/bin/env bash
# =============================================================================
# MAEZO — Execução dos testes E2E (ambiente local Docker)
#
# Uso:
#   bash scripts/run_e2e_tests.sh              # todos os testes e2e
#   bash scripts/run_e2e_tests.sh infra        # só infraestrutura
#   bash scripts/run_e2e_tests.sh bpm          # só CIB Seven BPM
#   bash scripts/run_e2e_tests.sh fhir         # só HAPI FHIR
#   bash scripts/run_e2e_tests.sh workers      # só workers Python
#   bash scripts/run_e2e_tests.sh observability # só Prometheus + Grafana
#   bash scripts/run_e2e_tests.sh flow         # só fluxos end-to-end
#   bash scripts/run_e2e_tests.sh --report     # gera relatório HTML
#
# Pré-requisitos:
#   1. Ambiente local rodando: bash scripts/start_local.sh --infra
#   2. Python com dependências: pip install -r tests/e2e/requirements-e2e.txt
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()  { echo -e "${GREEN}✓${NC} $*"; }
err() { echo -e "${RED}✗${NC} $*"; }

# ─── Detectar modo ────────────────────────────────────────────────────────────
MODE="${1:-all}"
REPORT=false
[[ "${1:-}" == "--report" ]] && { MODE="all"; REPORT=true; }
[[ "${2:-}" == "--report" ]] && REPORT=true

# ─── Base pytest args ─────────────────────────────────────────────────────────
PYTEST_ARGS=("-v" "--tb=short" "--timeout=30" "-m" "e2e")

if $REPORT; then
  REPORT_FILE="reports/e2e-report-$(date '+%Y%m%d-%H%M%S').html"
  mkdir -p reports
  PYTEST_ARGS+=("--html=$REPORT_FILE" "--self-contained-html")
  log "Relatório HTML: $REPORT_FILE"
fi

# ─── Selecionar arquivo de teste ──────────────────────────────────────────────
case "$MODE" in
  all)          TEST_PATH="tests/e2e/" ;;
  infra)        TEST_PATH="tests/e2e/test_infrastructure.py" ;;
  bpm)          TEST_PATH="tests/e2e/test_bpm_engine.py" ;;
  fhir)         TEST_PATH="tests/e2e/test_fhir.py" ;;
  workers)      TEST_PATH="tests/e2e/test_workers.py" ;;
  observability) TEST_PATH="tests/e2e/test_observability.py" ;;
  flow)         TEST_PATH="tests/e2e/test_full_flow.py" ;;
  *)
    err "Modo desconhecido: $MODE"
    echo "  Modos: all, infra, bpm, fhir, workers, observability, flow"
    exit 1 ;;
esac

# ─── Verificar pré-requisitos ─────────────────────────────────────────────────
log "Verificando pré-requisitos..."

if ! command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
  err "Python não encontrado. Instale Python 3.11+."
  exit 1
fi

PYTHON=$(command -v python3 || command -v python)

if ! $PYTHON -c "import pytest" 2>/dev/null; then
  err "pytest não encontrado. Execute: pip install -r tests/e2e/requirements-e2e.txt"
  exit 1
fi

if ! docker compose -f docker-compose.local.yml ps --format "{{.Service}}" 2>/dev/null | grep -q postgres; then
  err "Containers não estão rodando. Execute: bash scripts/start_local.sh --infra"
  exit 1
fi

ok "Pré-requisitos OK"

# ─── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   MAEZO — E2E Tests (ambiente local Docker)     ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Modo:   $MODE"
echo "  Testes: $TEST_PATH"
echo ""

# ─── Executar testes ─────────────────────────────────────────────────────────
log "Executando testes e2e..."
set +e
$PYTHON -m pytest "${PYTEST_ARGS[@]}" "$TEST_PATH"
EXIT_CODE=$?
set -e

# ─── Resultado ───────────────────────────────────────────────────────────────
echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
  ok "Todos os testes E2E passaram!"
elif [[ $EXIT_CODE -eq 5 ]]; then
  echo -e "${YELLOW}⚠${NC}  Nenhum teste encontrado para modo '$MODE'"
  EXIT_CODE=0
else
  err "Testes E2E com falhas (exit code: $EXIT_CODE)"
  echo "  Verifique se todos os serviços estão rodando:"
  echo "    bash scripts/start_local.sh --infra"
  echo "  Veja os logs:"
  echo "    docker compose -f docker-compose.local.yml logs [service]"
fi

$REPORT && ok "Relatório salvo em: $REPORT_FILE"

exit $EXIT_CODE
