COMPOSE = docker compose -f docker-compose.local.yml
COMPOSE_DEV = docker compose -f docker-compose.dev.yml

.PHONY: up-full up-workers up-observability up-bpm up-fhir up-integration up-api up-core \
        down down-v ps logs build rebuild test-e2e \
        dev-up dev-down dev-down-v dev-deploy dev-status dev-worker help

.DEFAULT_GOAL := help

# ── Subir grupos ────────────────────────────────────────────────────────────

up-full: ## Sobe toda a stack (postgres + kafka + todos os grupos)
	$(COMPOSE) --profile full up -d

up-core: ## Sobe apenas a infra core (PostgreSQL + Kafka)
	$(COMPOSE) up -d

up-bpm: ## Sobe BPM engine (core + CIB Seven)
	$(COMPOSE) --profile bpm up -d

up-fhir: ## Sobe HAPI FHIR R4 (core + FHIR)
	$(COMPOSE) --profile fhir up -d

up-integration: ## Sobe integrações CDC (core + Debezium)
	$(COMPOSE) --profile integration up -d

up-workers: ## Sobe workers Python (core + CIB Seven + 4 workers)
	$(COMPOSE) --profile workers up -d

up-api: ## Sobe Contract Extraction API (core + CIB Seven + ce_api)
	$(COMPOSE) --profile api up -d

up-observability: ## Sobe monitoramento (core + exporters + Prometheus + Grafana)
	$(COMPOSE) --profile observability up -d

# ── Parar ───────────────────────────────────────────────────────────────────

down: ## Para todos os containers
	$(COMPOSE) --profile full down

down-v: ## Para todos os containers e remove volumes (APAGA DADOS)
	$(COMPOSE) --profile full down -v

# ── Build ────────────────────────────────────────────────────────────────────

build: ## Reconstrói imagens dos workers e ce_api
	$(COMPOSE) build workers_rc workers_co workers_pa workers_ps ce_api

rebuild: ## Reconstrói do zero (sem cache)
	$(COMPOSE) build --no-cache workers_rc workers_co workers_pa workers_ps ce_api

# ── Operação ─────────────────────────────────────────────────────────────────

ps: ## Status dos containers
	$(COMPOSE) ps

logs: ## Segue logs de um serviço (ex: make logs SERVICE=workers_rc)
	$(COMPOSE) logs -f $(SERVICE)

logs-workers: ## Segue logs de todos os workers
	$(COMPOSE) logs -f workers_rc workers_co workers_pa workers_ps

# ── Testes ───────────────────────────────────────────────────────────────────

test-e2e: ## Roda suite de testes E2E completa (requer stack rodando)
	PYTHONPATH=./src python -m pytest tests/e2e/ -v -m e2e

test-e2e-workers: ## Roda apenas testes dos workers E2E
	PYTHONPATH=./src python -m pytest tests/e2e/test_workers.py -v -m e2e

test-e2e-infra: ## Roda apenas testes de infraestrutura E2E
	PYTHONPATH=./src python -m pytest tests/e2e/test_infrastructure.py -v -m e2e

test-e2e-observability: ## Roda apenas testes de observabilidade E2E
	PYTHONPATH=./src python -m pytest tests/e2e/test_observability.py -v -m e2e

# ── Dev Server (Linux remoto) ──────────────────────────────────────────────

dev-up: ## [DEV] Setup completo no servidor (PG + Kafka + CIB7 + FHIR + deploy + seed)
	bash scripts/dev/setup_dev_server.sh

dev-down: ## [DEV] Para stack dev no servidor (mantem dados)
	$(COMPOSE_DEV) down

dev-down-v: ## [DEV] Para stack dev + remove volumes (APAGA DADOS)
	$(COMPOSE_DEV) down -v

dev-deploy: ## [DEV] Re-deploy BPMN/DMN + re-seed FHIR (sem reiniciar containers)
	python3 scripts/deploy/deploy_processes.py --url http://localhost:8085/engine-rest
	python3 scripts/dev/seed_fhir_data.py --url http://localhost:8082/fhir --no-wait

dev-status: ## [DEV] Status dos containers dev
	$(COMPOSE_DEV) ps

dev-worker: ## [DEV] Roda worker local no Windows (ex: make dev-worker ARGS="--domain revenue_cycle")
	bash scripts/dev/run_worker_local.sh $(ARGS)

# ── Ajuda ────────────────────────────────────────────────────────────────────

help: ## Exibe esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'
