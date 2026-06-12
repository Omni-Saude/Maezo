# Runbook: Resposta a Incidentes — MAEZO Healthcare Platform

**Versão:** 1.0 | **Última atualização:** 2026-02-27

---

## Tipos de Incidentes e Resposta

### INC-001: Workers pararam de processar

**Sintomas:**
- `docker service ls` mostra replicas "0/N" ou "Replicating"
- Kafka consumer lag crescendo continuamente
- Alertmanager: `WorkerDown` ou `KafkaConsumerLag`

**Diagnóstico:**
```bash
# 1. Verificar status do serviço
docker service ps maestro_workers_rc --no-trunc | head -20

# 2. Ver logs do container com falha
docker service logs maestro_workers_rc --tail 100

# 3. Checar se CIB Seven está respondendo
curl -s -u admin:$CIB7_PASS http://localhost:8080/engine-rest/engine
```

**Ação corretiva:**
```bash
# Forçar re-criação dos containers
docker service update --force maestro_workers_rc

# Se OOM (Out of Memory):
docker service update --limit-memory 2G maestro_workers_rc

# Se não resolve, scale to 0 e voltar
docker service scale maestro_workers_rc=0
sleep 5
docker service scale maestro_workers_rc=2
```

**Escalonamento:** Se não resolver em 15 minutos → P1, acionar SRE.

---

### INC-002: CIB Seven Engine inoperante

**Sintomas:**
- `curl http://localhost:8080/engine-rest/engine` retorna 503 ou timeout
- Workers logs: `ConnectionRefused` ou `EngineUnavailable`
- Cockpit inacessível

**Diagnóstico:**
```bash
# 1. Status do container
docker service ps maestro_cib7 --no-trunc

# 2. Logs do engine (JVM, GC, out of heap)
docker service logs maestro_cib7 --tail 200 | grep -E "ERROR|WARN|GC"

# 3. Conectividade com RDS
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -c "SELECT 1" 2>&1
```

**Ação corretiva:**
```bash
# Restart do serviço
docker service update --force maestro_cib7

# Se heap insuficiente, aumentar JVM args
docker service update \
  --env-add JAVA_OPTS="-Xmx4g -Xms2g -XX:+UseG1GC" \
  maestro_cib7

# Aguardar health check (start_period: 60s)
watch "docker service ps maestro_cib7 --no-trunc | head -5"
```

**Verificação pós-correção:**
```bash
curl -s -u admin:$CIB7_PASS http://localhost:8080/engine-rest/engine | jq .
```

---

### INC-003: RDS PostgreSQL inacessível

**Sintomas:**
- Todos os serviços com erros de banco
- `psql` command timeout
- Alertas AWS: `DBInstanceNotAvailable` ou `HighDatabaseConnections`

**Diagnóstico:**
```bash
# 1. Testar conectividade
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -c "SELECT 1" --connect-timeout=5

# 2. Ver conexões abertas no banco
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -c "
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# 3. Checar AWS Console → RDS → Events
```

**Ação corretiva:**
```bash
# Se connection pool esgotado — restart dos serviços que fazem conexão
docker service update --force maestro_cib7
docker service update --force maestro_hapi_fhir

# Se RDS Multi-AZ failover em andamento — aguardar (tipicamente 60-120s automático)

# Verificar se instância RDS está em maintenance window
# AWS Console → RDS → Maintenance
```

**Escalonamento:** Acionar DBA imediatamente se RDS não recover em 5 minutos.

---

### INC-004: Kafka Consumer Lag Crescente

**Sintomas:**
- `kafka-consumer-groups.sh --describe` mostra lag crescendo
- Alertmanager: `KafkaConsumerLag > 10000`
- Processos BPMN não iniciando

**Diagnóstico:**
```bash
KAFKA_CONTAINER=$(docker ps -qf name=kafka)

# 1. Consumer lag por topic
docker exec $KAFKA_CONTAINER \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --all-groups 2>/dev/null | grep -v "^$"

# 2. Checar se CDC bridge está processando
docker service logs maestro_cib7 2>&1 | grep "cdc-bridge" | tail -20

# 3. Verificar topics existentes
docker exec $KAFKA_CONTAINER \
  kafka-topics.sh --bootstrap-server localhost:9092 --list | wc -l
```

**Ação corretiva:**
```bash
# Scale up do CDC bridge (se usar workers Kafka)
docker service scale maestro_workers_rc=4

# Se lag no dead-letter — investigar mensagens não-processáveis
docker exec $KAFKA_CONTAINER \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic bridge.dead-letter \
  --from-beginning --max-messages 5

# Reset de offset (CUIDADO — apenas após investigação)
# docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
#   --bootstrap-server localhost:9092 \
#   --group cdc-bridge-consumer \
#   --reset-offsets --to-latest --execute \
#   --topic tasy.hospital-a.ATENDIMENTO
```

---

### INC-005: Webhook Callbacks Falhando

**Sintomas:**
- Operadoras reportam timeouts ao enviar callbacks
- Logs do serviço de webhooks: `WebhookTimeout` ou `SignatureValidationError`
- Processos BPMN aguardando correlação que nunca chega

**Diagnóstico:**
```bash
# 1. Testar webhook endpoint
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://webhooks.austa.com.br/webhooks/tiss/response \
  -H "Content-Type: application/json" \
  -H "X-HMAC-Signature: test" \
  -d '{"test": true}'
# Esperado: 400 (invalid signature, mas endpoint acessível)

# 2. Verificar certificado TLS
echo | openssl s_client -connect webhooks.austa.com.br:443 2>/dev/null | openssl x509 -noout -dates
```

**Nota:** o serviço FastAPI de webhooks vive em `src/healthcare_platform/shared/webhooks/` mas ainda não está incluído nos `docker-compose.*.yml` (era servido pelo n8n, que foi removido). Para reativar o domínio `webhooks.${DOMAIN}`, é necessário adicionar um service que execute o ASGI desse módulo.

---

### INC-006: HAPI FHIR Lento (>2s por request)

**Sintomas:**
- Workers logs: `FHIRTimeout` ou `SlowResponse`
- Alertmanager: `FHIRLatencyP95 > 500ms`
- Processos de enriquecimento de pacientes atrasando

**Diagnóstico:**
```bash
# 1. Latência atual do FHIR
time curl -s http://localhost:8082/fhir/metadata -o /dev/null

# 2. Slow queries no PostgreSQL
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -d hapi_fhir -c "
  SELECT query, calls, mean_exec_time, total_exec_time
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;"

# 3. Tamanho das tabelas FHIR
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -d hapi_fhir -c "
  SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
  FROM pg_catalog.pg_statio_user_tables
  ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;"
```

**Ação corretiva:**
```bash
# Aumentar conexões DB do HAPI FHIR
docker service update \
  --env-add spring.datasource.hikari.maximum-pool-size=20 \
  maestro_hapi_fhir

# VACUUM/ANALYZE nas tabelas FHIR
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -d hapi_fhir -c "VACUUM ANALYZE;"
```

---

### INC-007: Glosa Rate Acima do Threshold

**Sintomas:**
- KPI dashboard: taxa de glosa >6%
- Business alert via Slack: `GlosaRateAlert`
- Operadoras reportando rejeições aumentadas

**Diagnóstico:**
```bash
# Ver processos de glosa com incidentes
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/incident?incidentType=failedJob&processDefinitionKey=SP-RC*" \
  | jq '.[] | {processInstanceId, incidentMessage}' | head -20

# Analisar padrão das glosas (via FHIR)
curl -s "$FHIR_URL/fhir/ClaimResponse?outcome=error&_count=50" \
  | jq '.entry[].resource.error[].code.coding[].code' | sort | uniq -c | sort -rn
```

**Ação corretiva:**
1. Identificar qual DMN rule está causando a rejeição
2. Verificar se houve mudança de contrato com a operadora
3. Acionar analista de negócios para revisão das regras DMN
4. Se regra DMN incorreta: corrigir a tabela e fazer re-deploy

---

## Playbook de Comunicação

### Template de Status Update (Slack)

```
🔴 [P1] MAEZO - Incidente em andamento
Serviço: [nome]
Impacto: [descrição do impacto clínico/financeiro]
Início: [HH:MM]
Status: Investigando / Mitigado / Resolvido
Próxima atualização: em 30 minutos
Responsável: @nome
```

### Post-Mortem (após P1/P2)

Após resolução de incidentes P1 e P2, criar documento em `docs/audit/INCIDENT_<data>.md` com:
- Timeline do incidente
- Root cause
- Impacto (processos afetados, valor estimado em risco)
- Ações corretivas imediatas
- Ações preventivas (melhorias)

---

## Ferramentas de Diagnóstico Rápido

```bash
# Snapshot completo do sistema
cat <<'EOF' > /tmp/maezo_diagnosis.sh
echo "=== Services ===" && docker service ls
echo "=== CIB7 ===" && curl -s -u admin:$CIB7_PASS http://localhost:8080/engine-rest/engine | jq .
echo "=== FHIR ===" && curl -s -o /dev/null -w "%{http_code}" http://localhost:8082/fhir/metadata
echo "=== CE API ===" && curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
echo "=== Incidents ===" && curl -s -u admin:$CIB7_PASS http://localhost:8080/engine-rest/incident/count | jq .
echo "=== Kafka lag ===" && docker exec $(docker ps -qf name=kafka) kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups 2>/dev/null | grep -v "^$"
EOF
bash /tmp/maezo_diagnosis.sh
```
