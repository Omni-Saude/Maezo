# Rollback Procedure

> MAEZO Healthcare Platform - Production Rollback Guide

## Prerequisites

- `kubectl` configured with production cluster access
- `helm` v3.x installed
- Access to `maestro` namespace

## 3-Step Rollback

### Step 1: Helm Rollback

```bash
# List release history
helm history maestro -n maestro

# Rollback to previous revision
helm rollback maestro <REVISION> -n maestro --wait --timeout=10m

# Watch pods restart
kubectl -n maestro get pods -w
```

### Step 2: Verify Deployments

```bash
# Check all deployments are healthy
kubectl -n maestro rollout status deployment/maestro-cib-seven --timeout=300s
kubectl -n maestro rollout status deployment/maestro-hapi-fhir --timeout=300s
kubectl -n maestro rollout status deployment/maestro-workers-revenue-cycle --timeout=300s

# Verify no pods in error state
kubectl -n maestro get pods | grep -v Running | grep -v Completed
```

### Step 3: Validate Engine Health

```bash
# Check CIB Seven engine
curl -s https://bpm.austa.com.br/engine-rest/engine | jq .

# Check FHIR server
curl -s https://fhir.austa.com.br/fhir/metadata | jq '.status'

# Check process instance count (should match pre-rollback)
curl -s https://bpm.austa.com.br/engine-rest/process-instance/count | jq .
```

## Common Failure Scenarios

### Migration Failure

```bash
# 1. Helm rollback
helm rollback maestro <REVISION> -n maestro --wait

# 2. Restore database snapshot (if schema changed)
# Contact DBA team for RDS snapshot restore
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier maestro-prod \
  --target-db-instance-identifier maestro-prod-restored \
  --restore-time <ISO-8601-timestamp>
```

### Worker OOMKilled

```bash
# Check which workers are OOMKilled
kubectl -n maestro get pods | grep OOMKilled

# Temporarily increase memory limits
kubectl -n maestro set resources deployment/maestro-workers-revenue-cycle \
  --limits=memory=2Gi

# Long-term: update values-prod.yaml and redeploy
```

### Database Connection Pool Exhausted

```bash
# Check connection count
kubectl -n maestro exec -it deploy/maestro-postgresql-primary -- \
  psql -U camunda -c "SELECT count(*) FROM pg_stat_activity;"

# Restart CIB Seven to release stale connections
kubectl -n maestro rollout restart deployment/maestro-cib-seven
```

### Kafka Consumer Lag Spike

```bash
# Check consumer lag
kubectl -n maestro exec -it kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group cdc-to-bpm-bridge

# Scale up workers if needed
kubectl -n maestro scale deployment/maestro-workers-revenue-cycle --replicas=5
```

## Emergency Contacts

| Role | Contact |
|------|---------|
| DevOps Lead | devops@austa.com.br |
| DBA Team | dba@austa.com.br |
| Slack Channel | #incidents-maestro |
| PagerDuty | https://austa.pagerduty.com |
