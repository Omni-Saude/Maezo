# Runbook: Operações Diárias — MAEZO Healthcare Platform

**Versão:** 1.0 | **Última atualização:** 2026-02-27
**Audiência:** Equipe de Operações / SRE

---

## Checks Diários (Morning Handoff)

Execute estes checks todo dia pela manhã antes das 08h:

```bash
# 1. Status geral dos serviços
docker service ls

# 2. Erros críticos nas últimas 12h
for svc in cib7 workers_rc workers_co workers_pa workers_ps ce_api; do
  echo "=== $svc ==="
  docker service logs maestro_$svc --since 12h 2>&1 | grep -E "ERROR|FATAL|Exception" | tail -20
done

# 3. Kafka consumer lag
docker exec -it $(docker ps -qf name=kafka) \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --all-groups | grep -v "^$" | head -50

# 4. Health checks ativos
bash scripts/dev/smoke_test.sh

# 5. Instâncias com incidentes no CIB Seven
curl -s -u admin:$CIB7_PASS \
  http://localhost:8080/engine-rest/incident/count | jq .count
```

**Threshold de alerta:** >0 incidentes → investigar imediatamente.

---

## Monitoramento de KPIs

| KPI | Target | Alertar Se |
|-----|--------|------------|
| Taxa de glosa | <4% | >6% |
| Tempo fechamento conta | <2h | >4h |
| Latência external task (P95) | <5s | >10s |
| Taxa de erro workers | <1% | >5% |
| Kafka consumer lag | <1.000 | >10.000 |
| RDS CPU | <70% | >90% |
| Memory workers | <80% | >95% |

```bash
# Consultar KPIs via API CIB Seven
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/process-instance/count?active=true" | jq .

# Latência média das external tasks (útimo 1h)
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/history/external-task-log" \
  -G --data "state=successful&createdAfter=$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%S.000+0000')" \
  | jq '[.[].duration] | add / length / 1000 | . * 100 | round / 100'
```

---

## Gestão de Incidentes no CIB Seven

### Ver incidentes ativos

```bash
# Todos os incidentes
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/incident" | jq '.[] | {id, type: .incidentType, message: .incidentMessage, processInstanceId}'
```

### Investigar um incidente

```bash
INCIDENT_ID="<incident-id>"
PROCESS_INSTANCE_ID="<process-instance-id>"

# Detalhes do incidente
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/incident/$INCIDENT_ID" | jq .

# Variáveis do processo
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/process-instance/$PROCESS_INSTANCE_ID/variables" | jq .

# Histórico de atividades
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/history/activity-instance?processInstanceId=$PROCESS_INSTANCE_ID" \
  | jq '.[] | {activityName, startTime, endTime, durationInMillis}'
```

### Retomar processo com falha (após correção)

```bash
# Retomar atividade específica (retry)
curl -X POST -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/process-instance/$PROCESS_INSTANCE_ID/modification" \
  -H "Content-Type: application/json" \
  -d '{
    "instructions": [{
      "type": "startBeforeActivity",
      "activityId": "<activity-id-to-retry>"
    }]
  }'

# Cancelar processo irrecuperável
curl -X DELETE -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/process-instance/$PROCESS_INSTANCE_ID"
```

---

## Gestão de External Tasks

### Ver tasks presas (stuck tasks)

```bash
# Tasks com lock expirado há mais de 5 minutos
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/external-task?notLocked=true&priorityHigherThanOrEquals=0" \
  | jq 'length'

# Ver quais topics têm mais tasks pendentes
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/external-task" \
  | jq 'group_by(.topicName) | .[] | {topic: .[0].topicName, count: length}' | head -50
```

### Desbloquear task travada

```bash
TASK_ID="<external-task-id>"

# Desbloquear (liberar o lock)
curl -X POST -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/external-task/$TASK_ID/unlock"
```

### Aumentar retries de uma task com falha

```bash
curl -X PUT -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/external-task/$TASK_ID/retries" \
  -H "Content-Type: application/json" \
  -d '{"retries": 3}'
```

---

## Gestão de Kafka

### Ver consumer groups e lag

```bash
KAFKA_CONTAINER=$(docker ps -qf name=kafka)

# Listar consumer groups
docker exec -it $KAFKA_CONTAINER \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list

# Lag detalhado
docker exec -it $KAFKA_CONTAINER \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group cdc-bridge-consumer

# Tópicos existentes
docker exec -it $KAFKA_CONTAINER \
  kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
```

### Dead Letter Queue

```bash
# Ver mensagens no dead letter
docker exec -it $KAFKA_CONTAINER \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic bridge.dead-letter \
  --from-beginning \
  --max-messages 10
```

---

## Gestão do HAPI FHIR

### Checar volumes de recursos

```bash
# Contar recursos por tipo
for resource in Patient Encounter Claim ClaimResponse Observation; do
  count=$(curl -s "$FHIR_URL/fhir/$resource?_summary=count" | jq .total)
  echo "$resource: $count"
done
```

### Limpar recursos de teste

```bash
# CUIDADO: use apenas em dev/staging!
# Deletar recursos de smoke test
curl -X DELETE "$FHIR_URL/fhir/Patient?identifier=SMOKE-TEST-PATIENT"
```

---

## Scaling Manual de Workers

### Scale up (emergência — alto volume)

```bash
# Aumentar replicas do worker RC (Revenue Cycle — mais crítico)
docker service scale maestro_workers_rc=5

# Verificar escala
docker service ls | grep workers
```

### Scale down (manutenção)

```bash
# Drain gracioso — stop_grace_period=90s
docker service update --replicas 1 maestro_workers_rc
```

---

## Manutenção do RDS PostgreSQL

### Conexões ativas

```bash
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -c "
  SELECT count(*), state
  FROM pg_stat_activity
  WHERE datname IN ('cibseven', 'hapi_fhir', 'maestro')
  GROUP BY state;
"
```

### Verificar tamanho dos schemas

```bash
PGPASSWORD="$PG_PASS" psql -h "$RDS_HOST" -U maestro -c "
  SELECT schemaname, pg_size_pretty(sum(pg_total_relation_size(schemaname||'.'||tablename))) as size
  FROM pg_tables
  WHERE schemaname IN ('public', 'act_hi_procinst', 'hapi_fhir')
  GROUP BY schemaname
  ORDER BY sum(pg_total_relation_size(schemaname||'.'||tablename)) DESC;
"
```

### History Cleanup CIB Seven (LGPD — ADR-011)

O history cleanup automático é configurado no CIB Seven. Para verificar:

```bash
# Ver processos históricos mais antigos que 180 dias
curl -s -u admin:$CIB7_PASS \
  "http://localhost:8080/engine-rest/history/process-instance/count?finishedBefore=$(date -u -d '180 days ago' '+%Y-%m-%dT%H:%M:%S.000+0000')"
```

---

## Logs Estruturados (structlog)

### Buscar erros por correlation ID

```bash
# No Kibana / Elasticsearch
# Filtro: correlation_id: "abc-123"

# Via docker logs (dev)
docker service logs maestro_workers_rc 2>&1 | grep '"correlation_id": "abc-123"'
```

### Formato dos logs

```json
{
  "timestamp": "2026-02-27T10:00:00Z",
  "level": "error",
  "logger": "healthcare_platform.revenue_cycle.billing",
  "event": "DMN evaluation failed",
  "worker": "validate_eligibility",
  "topic": "validate_eligibility",
  "tenant_id": "hospital-a",
  "correlation_id": "abc-123-def-456",
  "process_instance_id": "xxxxxxxx-xxxx",
  "exception": "ConnectionError: FHIR server timeout"
}
```

---

## Escalation Matrix

| Severidade | Critério | Ação | SLA Resposta |
|-----------|---------|------|-------------|
| P1 — Crítico | Serviço inoperante, perda de receita ativa | PagerDuty imediato | 15 min |
| P2 — Alto | Degradação >20% throughput, lag Kafka >10k | Slack #ops-maezo + on-call | 1h |
| P3 — Médio | Incidentes isolados, workers com retries | Ticket Jira | 4h |
| P4 — Baixo | Aviso de performance, log de debug | Ticket Jira | 24h |
