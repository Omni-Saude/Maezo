#!/usr/bin/env bash
# compose.sh — Atalhos para docker compose local do MAEZO
#
# Grupos visíveis no Docker Desktop:
#   maezo-infra        → postgres, kafka
#   maezo-workers      → cib7, workers_rc/co/pa/ps
#   maezo-integration  → hapi_fhir, debezium, ce_api
#   maezo-observability→ kafka_exporter, postgres_exporter, prometheus, grafana
#
# Uso: ./compose.sh <comando>

set -euo pipefail

INFRA="docker compose -f docker/compose.infra.yml        -p maezo-infra"
WORKERS="docker compose -f docker/compose.workers.yml    -p maezo-workers"
INTEGRATION="docker compose -f docker/compose.integration.yml -p maezo-integration"
OBS="docker compose -f docker/compose.observability.yml  -p maezo-observability"

# Stack única (backward compat / CI)
FULL="docker compose -f docker-compose.local.yml"

cmd="${1:-help}"

case "$cmd" in

  # ── Subir grupos individuais ─────────────────────────────────────────────

  up-infra)
    echo "▶ Subindo maezo-infra (postgres + kafka)..."
    $INFRA up -d ;;

  up-workers)
    echo "▶ Subindo maezo-infra + maezo-workers..."
    $INFRA up -d
    $WORKERS up -d ;;

  up-integration)
    echo "▶ Subindo maezo-infra + maezo-integration..."
    $INFRA up -d
    $INTEGRATION up -d ;;

  up-observability)
    echo "▶ Subindo maezo-infra + maezo-observability..."
    $INFRA up -d
    $OBS up -d ;;

  up-all)
    echo "▶ Subindo todos os grupos (4 projetos Docker)..."
    $INFRA up -d
    $WORKERS up -d
    $INTEGRATION up -d
    $OBS up -d ;;

  # ── Stack única (modo legacy — 1 projeto no Docker Desktop) ─────────────

  up-full)
    echo "▶ Subindo stack única (--profile full)..."
    $FULL --profile full up -d ;;

  # ── Parar ────────────────────────────────────────────────────────────────

  down)
    echo "▼ Parando todos os grupos..."
    $OBS down        2>/dev/null || true
    $INTEGRATION down 2>/dev/null || true
    $WORKERS down    2>/dev/null || true
    $INFRA down      2>/dev/null || true
    # Para stack única também, se estiver rodando
    $FULL --profile full down 2>/dev/null || true ;;

  down-v)
    echo "▼ Parando todos os grupos e removendo volumes (APAGA DADOS)..."
    $OBS down -v       2>/dev/null || true
    $INTEGRATION down -v 2>/dev/null || true
    $WORKERS down -v   2>/dev/null || true
    $INFRA down -v     2>/dev/null || true
    $FULL --profile full down -v 2>/dev/null || true ;;

  # ── Operação ─────────────────────────────────────────────────────────────

  ps)
    echo "── maezo-infra ──"
    $INFRA ps 2>/dev/null || true
    echo ""
    echo "── maezo-workers ──"
    $WORKERS ps 2>/dev/null || true
    echo ""
    echo "── maezo-integration ──"
    $INTEGRATION ps 2>/dev/null || true
    echo ""
    echo "── maezo-observability ──"
    $OBS ps 2>/dev/null || true ;;

  logs)
    # Ex: ./compose.sh logs workers_rc  →  tenta em cada grupo
    SVC="${2:-}"
    for COMPOSE in "$INFRA" "$WORKERS" "$INTEGRATION" "$OBS"; do
      $COMPOSE logs -f "$SVC" 2>/dev/null && break || true
    done ;;

  logs-workers)
    $WORKERS logs -f workers_rc workers_co workers_pa workers_ps ;;

  build)
    echo "▶ Rebuild workers + ce_api..."
    $WORKERS build workers_rc workers_co workers_pa workers_ps
    $INTEGRATION build ce_api ;;

  rebuild)
    echo "▶ Rebuild sem cache..."
    $WORKERS build --no-cache workers_rc workers_co workers_pa workers_ps
    $INTEGRATION build --no-cache ce_api ;;

  # ── Testes ───────────────────────────────────────────────────────────────

  test-e2e)
    PYTHONPATH=./src python -m pytest tests/e2e/ -v -m e2e ;;

  test-workers)
    PYTHONPATH=./src python -m pytest tests/e2e/test_workers.py -v -m e2e ;;

  test-infra)
    PYTHONPATH=./src python -m pytest tests/e2e/test_infrastructure.py -v -m e2e ;;

  test-observability)
    PYTHONPATH=./src python -m pytest tests/e2e/test_observability.py -v -m e2e ;;

  # ── Ajuda ────────────────────────────────────────────────────────────────

  help|*)
    echo ""
    echo "Uso: ./compose.sh <comando>"
    echo ""
    echo "Grupos (4 projetos separados no Docker Desktop):"
    echo "  up-all            Sobe todos os 4 grupos"
    echo "  up-infra          maezo-infra: postgres + kafka"
    echo "  up-workers        maezo-workers: cib7 + 4 workers"
    echo "  up-integration    maezo-integration: hapi_fhir + debezium + ce_api"
    echo "  up-observability  maezo-observability: exporters + Prometheus + Grafana"
    echo ""
    echo "Stack única (1 projeto, backward compat):"
    echo "  up-full           Sobe tudo em 1 projeto (healthcare-orchest-cib7)"
    echo ""
    echo "Operação:"
    echo "  down              Para todos os grupos"
    echo "  down-v            Para todos e remove volumes (APAGA DADOS)"
    echo "  ps                Status por grupo"
    echo "  logs [serviço]    Segue logs (ex: ./compose.sh logs workers_rc)"
    echo "  logs-workers      Segue logs dos 4 workers"
    echo "  build             Reconstrói workers + ce_api"
    echo "  rebuild           Reconstrói sem cache"
    echo ""
    echo "Testes:"
    echo "  test-e2e          Suite E2E completa (78 testes)"
    echo "  test-workers      Testes dos workers"
    echo "  test-infra        Testes de infraestrutura"
    echo "  test-observability  Testes de observabilidade"
    echo ""
    ;;
esac
