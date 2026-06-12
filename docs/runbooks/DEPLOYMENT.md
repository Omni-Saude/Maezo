# Runbook: Deployment — MAEZO Healthcare Platform

**Versão:** 1.0 | **Última atualização:** 2026-02-27
**Stack:** Docker Swarm (atual) | Kubernetes via Helm (futuro)

---

## Pré-requisitos

Antes de qualquer deploy, confirme:

| Item | Verificação |
|------|-------------|
| Docker Swarm inicializado | `docker info \| grep Swarm` |
| Secrets criados | `docker secret ls` (ver seção 1) |
| Imagens Docker buildadas | `docker image ls \| grep maestro` |
| RDS PostgreSQL acessível | `psql postgresql://maestro@$RDS_HOST:5432/cibseven -c '\l'` |
| Variáveis de ambiente setadas | `cat .env` |
| CI/CD verde | GitHub Actions ✅ |

---

## 1. Preparação dos Secrets (primeira vez)

```bash
# Gerar valor seguro para cada secret
# Nota: CIB7_PASS e PG_PASS vão no .env (não como secrets Docker)
read -s -p "postgres_password (HAPI FHIR): " PG_S  && echo "$PG_S"     | docker secret create postgres_password -

# Verificar
docker secret ls
```

> ⚠️ **NUNCA** commite secrets no git. Use o AWS Secrets Manager em produção.

---

## 2. Configuração do .env

```bash
cp .env.example .env
nano .env  # editar todos os valores CHANGE_ME

# Valores obrigatórios para produção:
# RDS_HOST=maezo.xxxxxxxx.us-east-1.rds.amazonaws.com
# DOMAIN=austa.com.br
# ACME_EMAIL=devops@austa.com.br
# CIB7_USER=admin
# TASY_API_URL=https://tasy.austa.com.br/api
# TASY_API_KEY=<api-key-do-tasy>
# KAFKA_CLUSTER_ID=$(docker run --rm confluentinc/cp-kafka:7.7.0 kafka-storage random-uuid)
```

---

## 3. Inicializar Banco de Dados (primeira vez)

```bash
# Conectar ao RDS e criar schemas
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -f config/postgres/init.sql

# Verificar schemas criados
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -c '\l'
# Esperado: cibseven, hapi_fhir, maestro
```

---

## 4. Build das Imagens Docker

```bash
# Buildar imagem dos workers (all domains)
docker build -f Dockerfile.worker -t ghcr.io/austa/maestro-workers:$(git rev-parse --short HEAD) .

# Buildar imagem da Contract Extraction API
docker build -f Dockerfile.contract-extraction -t ghcr.io/austa/maestro-ce:$(git rev-parse --short HEAD) .

# Fazer push para o registry
docker push ghcr.io/austa/maestro-workers:$(git rev-parse --short HEAD)
docker push ghcr.io/austa/maestro-ce:$(git rev-parse --short HEAD)
```

---

## 5. Deploy Docker Swarm

### 5.1 Deploy completo (primeira vez ou full update)

```bash
# Exportar variáveis
export IMAGE_TAG=$(git rev-parse --short HEAD)
export RDS_HOST=maezo.xxxxxxxx.us-east-1.rds.amazonaws.com
export RDS_USER=maestro
export CIB7_USER=admin
export DOMAIN=austa.com.br
export ACME_EMAIL=devops@austa.com.br
export KAFKA_CLUSTER_ID=$(docker run --rm confluentinc/cp-kafka:7.7.0 kafka-storage random-uuid)

# Validar docker-compose antes do deploy
docker compose -f docker-compose.swarm.yml config > /dev/null && echo "Config válida"

# Deploy
docker stack deploy \
  -c docker-compose.swarm.yml \
  --with-registry-auth \
  maestro

# Verificar status dos serviços
watch docker service ls
```

### 5.2 Update de imagem (workers ou CE API)

```bash
export IMAGE_TAG=$(git rev-parse --short HEAD)

# Update workers
docker service update \
  --image ghcr.io/austa/maestro-workers:$IMAGE_TAG \
  --update-parallelism 1 \
  --update-delay 30s \
  maestro_workers_rc

# (repetir para workers_co, workers_pa, workers_ps)

# Update Contract Extraction API
docker service update \
  --image ghcr.io/austa/maestro-ce:$IMAGE_TAG \
  maestro_ce_api
```

### 5.3 Verificar saúde após deploy

```bash
# Status dos serviços
docker service ls

# Logs em tempo real (exemplo: workers RC)
docker service logs maestro_workers_rc -f --tail=100

# Verificar health checks
docker ps --filter "label=com.docker.swarm.service.name" --format "table {{.Names}}\t{{.Status}}"
```

---

## 6. Registrar Conector Debezium CDC (após primeiro deploy)

```bash
# Aguardar Debezium estar ready (~60 segundos)
sleep 60

# Registrar conector Oracle → Kafka
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @config/debezium/oracle-connector.json

# Verificar status do conector
curl http://localhost:8083/connectors/tasy-oracle-connector/status | jq .
# Esperado: "state": "RUNNING"
```

> ⚠️ Requer Oracle LogMiner habilitado no Tasy. Ver [pendencias-desenvolvedores.md](../pending/pendencias-desenvolvedores.md)

---

## 7. Deploy via Helm (Kubernetes — futuro)

```bash
# Adicionar repositório (quando publicado)
helm repo add maezo https://charts.austa.com.br

# Deploy em staging
helm upgrade --install maezo ./helm/maezo \
  -n maezo \
  --create-namespace \
  -f helm/maezo/values-staging.yaml \
  --set image.tag=$(git rev-parse --short HEAD)

# Deploy em produção
helm upgrade --install maezo ./helm/maezo \
  -n maezo \
  --create-namespace \
  -f helm/maezo/values-prod.yaml \
  --set image.tag=$(git rev-parse --short HEAD) \
  --atomic \
  --timeout 10m

# Verificar status
helm status maezo -n maezo
kubectl rollout status deployment/cib7 -n maezo
kubectl rollout status deployment/workers-rc -n maezo
```

---

## 8. Smoke Tests Pós-Deploy

```bash
# Execução básica (shell)
bash scripts/dev/smoke_test.sh https://bpm.austa.com.br

# Execução completa (pytest)
CIB7_URL=https://bpm.austa.com.br/engine-rest \
FHIR_URL=https://fhir.austa.com.br \
CE_URL=https://api.austa.com.br \
CIB7_USER=admin \
CIB7_PASS="$(cat .env.prod | grep CIB7_PASS | cut -d= -f2)" \
pytest tests/smoke/ -v --timeout=30 -m "not integration"
```

---

## 9. Rollback

Ver [ROLLBACK.md](ROLLBACK.md) para procedimento completo.

```bash
# Rollback rápido Docker Swarm
export IMAGE_TAG=<sha-anterior>
docker service update --image ghcr.io/austa/maestro-workers:$IMAGE_TAG maestro_workers_rc
# (repetir para todos os workers)

# Rollback Helm
helm rollback maezo 0 -n maezo  # 0 = revisão anterior
```

---

## 10. Checklist de Go-Live

Antes de habilitar tráfego de produção:

- [ ] Todos os serviços Docker em estado `Running` (não `Replicating` ou `Paused`)
- [ ] `docker service ls` sem erros
- [ ] Smoke tests passando: `bash scripts/dev/smoke_test.sh`
- [ ] Kafka consumer groups ativos: `docker exec -it $(docker ps -qf name=kafka) kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list`
- [ ] BPMN deployados no CIB Seven (via Cockpit UI)
- [ ] DMN tabelas acessíveis (avaliar 1 regra de teste)
- [ ] Logs sem erros críticos (ERROR/FATAL) nos últimos 5 minutos
- [ ] Grafana dashboards carregando com dados
- [ ] Alertmanager configurado (não silenciado)
- [ ] Backups RDS habilitados e testados

---

## Contatos de Emergência

| Papel | Responsável | Contato |
|-------|-------------|---------|
| DevOps/SRE | — | Slack: #ops-maezo |
| BPM/CIB Seven | — | Slack: #bpm-support |
| DBA (RDS) | — | PagerDuty: Database |
| On-call | — | PagerDuty: MAEZO-PROD |
