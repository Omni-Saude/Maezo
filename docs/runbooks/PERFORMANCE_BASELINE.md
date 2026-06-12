# Performance Baseline

> MAEZO Healthcare Platform - Production Performance Targets

## Expected Metrics (Production)

### Latency

| Metric | P50 | P95 | P99 |
|--------|-----|-----|-----|
| Process Start Latency | <200ms | <500ms | <1s |
| External Task Fetch | <100ms | <300ms | <500ms |
| DMN Evaluation | <50ms | <150ms | <300ms |
| FHIR Read | <100ms | <250ms | <500ms |
| FHIR Write | <200ms | <500ms | <1s |
| Worker Task Execution | <2s | <5s | <10s |

### Throughput

| Metric | Sustained | Peak |
|--------|-----------|------|
| Process Instances/day | 10,000 | 50,000 |
| External Tasks/minute | 500 | 2,000 |
| DMN Evaluations/second | 100 | 500 |
| FHIR Operations/minute | 1,000 | 5,000 |
| CDC Events/second | 200 | 1,000 |

### Error Rate

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Process start failures | <0.1% | >1% |
| Worker task failures (after retries) | <1% | >5% |
| FHIR API errors | <0.5% | >2% |
| CDC message processing | <0.01% | >0.1% |
| Authentication failures | <0.1% | >1% |

## Resource Utilization

| Resource | Normal | Warning | Critical |
|----------|--------|---------|----------|
| CIB Seven CPU | 60-80% | >85% | >90% |
| CIB Seven Memory | 50-70% | >80% | >90% |
| PostgreSQL Connections | <70% (35/50) | >80% | >90% |
| PostgreSQL Disk | <60% | >75% | >85% |
| Kafka Consumer Lag | <1,000 msgs | >5,000 | >10,000 |
| Redis Memory | <80% | >85% | >90% |
| Worker CPU | 40-60% | >75% | >85% |

## SLA Thresholds (Alertmanager)

| Condition | Duration | Severity |
|-----------|----------|----------|
| P95 latency >1s | 5min | P2 - Warning |
| P99 latency >3s | 5min | P1 - Critical |
| Error rate >5% | 2min | P1 - Critical |
| Error rate >2% | 5min | P2 - Warning |
| Database pool >80% | 3min | P2 - Warning |
| Database pool >90% | 1min | P1 - Critical |
| Worker OOMKilled | immediate | P1 - Critical |
| Kafka lag >10,000 | 5min | P1 - Critical |
| Pod restart loop (>3 in 10min) | 10min | P1 - Critical |

## Grafana Dashboard Queries

### Process Instance Rate
```promql
rate(camunda_bpm_process_instance_start_total[5m])
```

### External Task Latency P95
```promql
histogram_quantile(0.95, rate(camunda_bpm_external_task_duration_seconds_bucket[5m]))
```

### Worker Error Rate
```promql
rate(worker_task_failures_total[5m]) / rate(worker_task_total[5m]) * 100
```

### Database Connection Pool Usage
```promql
hikaricp_connections_active / hikaricp_connections_max * 100
```

## Baseline Capture Script

```bash
#!/usr/bin/env bash
# Run after deployment to capture baseline metrics
echo "=== MAEZO Performance Baseline Capture ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""
echo "--- Pod Status ---"
kubectl -n maestro get pods -o wide
echo ""
echo "--- Resource Usage ---"
kubectl -n maestro top pods
echo ""
echo "--- Engine Health ---"
curl -s https://bpm.austa.com.br/engine-rest/engine | jq .
echo ""
echo "--- Process Instance Count ---"
curl -s https://bpm.austa.com.br/engine-rest/process-instance/count | jq .
echo ""
echo "--- Active External Tasks ---"
curl -s https://bpm.austa.com.br/engine-rest/external-task/count | jq .
```
