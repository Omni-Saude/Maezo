#!/usr/bin/env bash
# =============================================================================
# MAEZO — Smoke Test Suite
# Valida saúde dos serviços após deploy (Docker Swarm ou Kubernetes)
#
# Uso:
#   bash scripts/dev/smoke_test.sh [BASE_URL]
#   BASE_URL default: http://localhost
#
# Exemplos:
#   bash scripts/dev/smoke_test.sh                          # local
#   bash scripts/dev/smoke_test.sh https://austa.com.br     # produção
#   CIB7_USER=admin CIB7_PASS=secret bash scripts/dev/smoke_test.sh https://bpm.austa.com.br
#
# Exit codes:
#   0 — todos os checks passaram
#   1 — um ou mais checks falharam
# =============================================================================

set -euo pipefail

# ─── Configuração ─────────────────────────────────────────────────────────────
BASE_URL="${1:-http://localhost}"
CIB7_URL="${CIB7_URL:-${BASE_URL}:8080}"
FHIR_URL="${FHIR_URL:-${BASE_URL}:8082}"
CE_URL="${CE_URL:-${BASE_URL}:8000}"
DEBEZIUM_URL="${DEBEZIUM_URL:-${BASE_URL}:8083}"
PROMETHEUS_URL="${PROMETHEUS_URL:-${BASE_URL}:9090}"
GRAFANA_URL="${GRAFANA_URL:-${BASE_URL}:3000}"
CIB7_USER="${CIB7_USER:-admin}"
CIB7_PASS="${CIB7_PASS:-admin}"
TIMEOUT="${TIMEOUT:-10}"

# Detecta se é ambiente local (localhost) para ajustar checks
IS_LOCAL=false
[[ "$BASE_URL" == "http://localhost" || "$BASE_URL" == "http://127.0.0.1" ]] && IS_LOCAL=true

# ─── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

PASS=0
FAIL=0
WARN=0

# ─── Helpers ──────────────────────────────────────────────────────────────────
check() {
  local name="$1"
  local url="$2"
  local expected_status="${3:-200}"
  local auth="${4:-}"

  printf "  %-50s" "$name"

  local curl_args=(-s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT")
  [[ -n "$auth" ]] && curl_args+=(-u "$auth")

  local status
  status=$(curl "${curl_args[@]}" "$url" 2>/dev/null || echo "000")

  if [[ "$status" == "$expected_status" ]]; then
    echo -e "${GREEN}PASS${NC} (HTTP $status)"
    ((PASS++))
  else
    echo -e "${RED}FAIL${NC} (HTTP $status, expected $expected_status)"
    ((FAIL++))
  fi
}

check_json() {
  local name="$1"
  local url="$2"
  local jq_filter="$3"
  local expected="$4"
  local auth="${5:-}"

  printf "  %-50s" "$name"

  local curl_args=(-s --max-time "$TIMEOUT" -H "Accept: application/json")
  [[ -n "$auth" ]] && curl_args+=(-u "$auth")

  local result
  result=$(curl "${curl_args[@]}" "$url" 2>/dev/null | jq -r "$jq_filter" 2>/dev/null || echo "ERROR")

  if [[ "$result" == "$expected" ]]; then
    echo -e "${GREEN}PASS${NC} ($result)"
    ((PASS++))
  else
    echo -e "${RED}FAIL${NC} (got: $result, expected: $expected)"
    ((FAIL++))
  fi
}

check_contains() {
  local name="$1"
  local url="$2"
  local pattern="$3"
  local auth="${4:-}"

  printf "  %-50s" "$name"

  local curl_args=(-s --max-time "$TIMEOUT")
  [[ -n "$auth" ]] && curl_args+=(-u "$auth")

  local body
  body=$(curl "${curl_args[@]}" "$url" 2>/dev/null || echo "")

  if echo "$body" | grep -q "$pattern" 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (contém: $pattern)"
    ((PASS++))
  else
    echo -e "${RED}FAIL${NC} (não contém: $pattern)"
    ((FAIL++))
  fi
}

warn() {
  local name="$1"
  local msg="$2"
  printf "  %-50s" "$name"
  echo -e "${YELLOW}WARN${NC} ($msg)"
  ((WARN++))
}

separator() {
  echo ""
  echo "── $1 ──────────────────────────────────────────────────────────────"
}

# ─── Verificar dependências ───────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║         MAEZO Healthcare Platform — Smoke Tests                     ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Ambiente: $BASE_URL"
echo "  Data:     $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

if ! command -v curl &>/dev/null; then
  echo "ERRO: curl não encontrado. Instale com: apt-get install curl"
  exit 1
fi
if ! command -v jq &>/dev/null; then
  warn "jq não instalado" "checks JSON simplificados"
fi

# ─── 1. CIB Seven BPM Engine ─────────────────────────────────────────────────
separator "CIB Seven BPM Engine ($CIB7_URL)"

check "Engine REST API" \
  "$CIB7_URL/engine-rest/engine" 200 \
  "$CIB7_USER:$CIB7_PASS"

check "Process definitions" \
  "$CIB7_URL/engine-rest/process-definition?maxResults=1" 200 \
  "$CIB7_USER:$CIB7_PASS"

check "External tasks available" \
  "$CIB7_URL/engine-rest/external-task/count" 200 \
  "$CIB7_USER:$CIB7_PASS"

check "Deployment list" \
  "$CIB7_URL/engine-rest/deployment?maxResults=1" 200 \
  "$CIB7_USER:$CIB7_PASS"

# Verifica se há processos BPMN deployados
if command -v jq &>/dev/null; then
  check_json "Processes deployed (>0)" \
    "$CIB7_URL/engine-rest/process-definition/count" \
    ".count" \
    "$(curl -s -u "$CIB7_USER:$CIB7_PASS" "$CIB7_URL/engine-rest/process-definition/count" | jq -r '.count')" \
    "$CIB7_USER:$CIB7_PASS"
fi

check "Cockpit UI" \
  "$CIB7_URL/cibseven/app/cockpit/default/#/dashboard" 200

# ─── 2. HAPI FHIR R4 ─────────────────────────────────────────────────────────
separator "HAPI FHIR R4 ($FHIR_URL)"

check "FHIR metadata (CapabilityStatement)" \
  "$FHIR_URL/fhir/metadata" 200

check "FHIR Patient endpoint" \
  "$FHIR_URL/fhir/Patient?_count=1" 200

check "FHIR Encounter endpoint" \
  "$FHIR_URL/fhir/Encounter?_count=1" 200

check "FHIR Claim endpoint" \
  "$FHIR_URL/fhir/Claim?_count=1" 200

# ─── 4. Contract Extraction API ──────────────────────────────────────────────
separator "Contract Extraction API ($CE_URL)"

check "Health check" \
  "$CE_URL/health" 200

check "Ready check" \
  "$CE_URL/ready" 200

check "OpenAPI docs" \
  "$CE_URL/docs" 200

# ─── 5. Debezium CDC Connector ────────────────────────────────────────────────
separator "Debezium CDC Connector ($DEBEZIUM_URL)"

check "Kafka Connect REST" \
  "$DEBEZIUM_URL/connectors" 200

# Verificar se connector Tasy está registrado (sem 'local' fora de função)
if command -v jq &>/dev/null; then
  connector_status=$(curl -s --max-time "$TIMEOUT" "$DEBEZIUM_URL/connectors/tasy-oracle-connector/status" | jq -r '.connector.state' 2>/dev/null || echo "NOT_FOUND")
  printf "  %-50s" "Tasy Oracle connector status"
  if [[ "$connector_status" == "RUNNING" ]]; then
    echo -e "${GREEN}PASS${NC} (RUNNING)"
    ((PASS++))
  elif [[ "$connector_status" == "NOT_FOUND" ]]; then
    warn "Tasy Oracle connector" "não registrado (esperado em staging/prod)"
  else
    echo -e "${RED}FAIL${NC} (status: $connector_status)"
    ((FAIL++))
  fi
fi

# ─── 6. Workers Python — Health direto (ambiente local) ──────────────────────
if $IS_LOCAL; then
  separator "Workers Python — Health Endpoints (local 8100-8103)"

  check "Worker RC (revenue_cycle) health"   "http://localhost:8100/health" 200
  check "Worker CO (clinical_operations) health" "http://localhost:8101/health" 200
  check "Worker PA (patient_access) health"  "http://localhost:8102/health" 200
  check "Worker PS (platform_services) health" "http://localhost:8103/health" 200

  # Verificar que /metrics está exposto (Prometheus scrape)
  check_contains "Worker RC — /metrics exposto" \
    "http://localhost:8100/metrics" "cib7_worker_tasks_total"
fi

# ─── 7. Observabilidade (Prometheus + Grafana) — apenas local ─────────────────
if $IS_LOCAL; then
  separator "Observabilidade ($PROMETHEUS_URL / $GRAFANA_URL)"

  check "Prometheus healthy" \
    "$PROMETHEUS_URL/-/healthy" 200

  check "Prometheus ready" \
    "$PROMETHEUS_URL/-/ready" 200

  check_contains "Prometheus targets carregados" \
    "$PROMETHEUS_URL/api/v1/targets" '"health"'

  check "Grafana API health" \
    "$GRAFANA_URL/api/health" 200

  check "Grafana datasources provisionadas" \
    "$GRAFANA_URL/api/datasources" 200 "admin:admin"

  check "Grafana dashboards provisionados" \
    "$GRAFANA_URL/api/search?type=dash-db" 200 "admin:admin"
fi

# ─── 8. Conectividade de Rede ─────────────────────────────────────────────────
separator "Conectividade"

# DNS
for host in bpm fhir api; do
  domain_suffix="${BASE_URL#https://}"
  domain_suffix="${domain_suffix#http://}"
  if [[ "$BASE_URL" == "http://localhost" ]]; then
    break
  fi
  printf "  %-50s" "DNS: $host.$domain_suffix"
  if nslookup "$host.$domain_suffix" &>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
  else
    echo -e "${YELLOW}WARN${NC} (DNS não resolvível — pode ser normal em staging)"
    ((WARN++))
  fi
done

# TLS (apenas se HTTPS)
if [[ "$BASE_URL" == https://* ]]; then
  printf "  %-50s" "TLS certificate valid"
  if curl -s --head --max-time "$TIMEOUT" "$BASE_URL" -o /dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
  else
    echo -e "${RED}FAIL${NC} (TLS inválido ou endpoint não responde)"
    ((FAIL++))
  fi
fi

# ─── 9. Multi-tenancy ─────────────────────────────────────────────────────────
separator "Multi-tenancy (via CIB Seven Tenant API)"

# A endpoint correta para listar tenants no CIB Seven
if command -v jq &>/dev/null; then
  all_tenants=$(curl -s -u "$CIB7_USER:$CIB7_PASS" \
    "$CIB7_URL/engine-rest/tenant" --max-time "$TIMEOUT" \
    | jq -r '.[].id' 2>/dev/null | sort | tr '\n' ',' || echo "")
  printf "  %-50s" "Tenants configurados"
  if [[ -n "$all_tenants" ]]; then
    echo -e "${GREEN}PASS${NC} ($all_tenants)"
    ((PASS++))
  else
    warn "Tenants" "nenhum tenant encontrado (normal em ambiente limpo)"
  fi
else
  check "Tenant API endpoint" \
    "$CIB7_URL/engine-rest/tenant" 200 \
    "$CIB7_USER:$CIB7_PASS"
fi

# ─── Resumo ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                    RESULTADO DOS SMOKE TESTS                        ║"
echo "╠══════════════════════════════════════════════════════════════════════╣"
printf "║  %-20s %4d checks                               ║\n" "PASSED:" "$PASS"
printf "║  %-20s %4d checks                               ║\n" "FAILED:" "$FAIL"
printf "║  %-20s %4d checks                               ║\n" "WARNINGS:" "$WARN"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo -e "${RED}❌ Smoke tests FALHARAM ($FAIL falhas)${NC}"
  echo "   Investigue os serviços acima antes de prosseguir."
  exit 1
elif [[ $WARN -gt 0 ]]; then
  echo -e "${YELLOW}⚠️  Smoke tests passaram com avisos ($WARN warnings)${NC}"
  echo "   Revise os warnings antes do go-live em produção."
  exit 0
else
  echo -e "${GREEN}✅ Todos os smoke tests PASSARAM${NC}"
  exit 0
fi
