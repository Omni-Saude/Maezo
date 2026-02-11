# MAEZO Healthcare Platform - Infrastructure Quick Start
**Master of Automation for Ecosystems & Orchestration**
# This README guides DevOps through deploying the platform

## Prerequisites

- AWS CLI configured with appropriate permissions
- kubectl installed and configured
- Helm 3.14+
- Docker (for local testing)

## Quick Start (Development)

### 1. Local Development with Docker Compose

```bash
# Start all services locally
docker-compose up -d

# Verify services
docker-compose ps

# Access services:
# - CIB Seven Cockpit: http://localhost:8080
# - HAPI FHIR: http://localhost:8081/fhir
# - Keycloak: http://localhost:8082
# - Grafana: http://localhost:3000
# - Prometheus: http://localhost:9090
```

### 2. Deploy to Kubernetes (Dev Environment)

```bash
# Create namespace and apply base resources
kubectl apply -f k8s/base/namespace.yaml

# Create secrets (EDIT FIRST - replace all CHANGE_ME values!)
kubectl apply -f k8s/base/secrets.yaml

# Add Bitnami repo for dependencies
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install with Helm (dev environment)
helm upgrade --install maestro ./helm/maestro \
  --namespace maestro \
  --values helm/maestro/values.yaml \
  --values helm/maestro/values-dev.yaml \
  --wait

# Verify deployment
kubectl -n maestro get pods
kubectl -n maestro get services
```

### 3. Deploy to Staging/Production

```bash
# For staging
helm upgrade --install maestro ./helm/maestro \
  --namespace maestro \
  --values helm/maestro/values.yaml \
  --values helm/maestro/values-staging.yaml \
  --wait

# For production (use external secrets!)
helm upgrade --install maestro ./helm/maestro \
  --namespace maestro \
  --values helm/maestro/values.yaml \
  --set-file postgresql.auth.existingSecret=/path/to/external-secrets \
  --wait
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGRESS (nginx)                          │
├─────────────────────────────────────────────────────────────────┤
│  bpm.austa.com.br  │  fhir.austa.com.br  │  webhooks.austa.com.br│
└─────────┬──────────┴─────────┬───────────┴─────────┬────────────┘
          │                    │                     │
          ▼                    ▼                     ▼
    ┌──────────┐        ┌──────────┐        ┌────────────────┐
    │ CIB Seven│        │ HAPI FHIR│        │Webhook Receiver│
    │  (BPM)   │        │   (R4)   │        │  (ADR-014)     │
    └────┬─────┘        └────┬─────┘        └───────┬────────┘
         │                   │                      │
         │    ┌──────────────┼──────────────────────┤
         │    │              │                      │
         ▼    ▼              ▼                      ▼
    ┌──────────────────────────────────────────────────┐
    │                    KAFKA (KRaft)                  │
    │  Topics: tasy.*, callbacks.*, bridge.dead-letter │
    └──────────────────────────────────────────────────┘
         │                   │                      │
         │                   │                      │
         ▼                   ▼                      ▼
    ┌──────────┐    ┌────────────────┐    ┌──────────────┐
    │CDC Bridge│    │  Workers (4)   │    │   Debezium   │
    │          │◄───┤ - revenue_cycle│    │(Oracle→Kafka)│
    └──────────┘    │ - patient_access│   └──────────────┘
                    │ - clinical_ops │
                    │ - platform_svcs│
                    └───────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │PostgreSQL│  │  Redis   │  │ Keycloak │
        │   (RDS)  │  │(Sentinel)│  │  (Auth)  │
        └──────────┘  └──────────┘  └──────────┘
```

## Key Configuration

### Multi-Tenancy (ADR-002)

4 tenants configured:
- `austa-hospital` (default) - TASY ERP
- `amh-sp-morumbi` - MV Soul
- `amh-rj-barra` - MV Soul
- `amh-mg-bh` - MV Soul

### Worker Domains (ADR-003)

| Domain | Workers | HPA Range |
|--------|---------|-----------|
| revenue_cycle | 89 | 1-4 |
| patient_access | 47 | 1-3 |
| clinical_operations | 32 | 1-4 |
| platform_services | 16 | 1-3 |

### HAPI FHIR (ADR-005)

Brazilian healthcare search parameters included:
- CPF (patient identifier)
- CNS (Cartão Nacional de Saúde)
- CRM (medical license)
- TUSS (procedure codes)
- CNES (facility codes)

### Keycloak Clients (ADR-008)

14 OAuth2 clients configured:
- 4 domain workers
- 8 legacy workers
- cdc-bridge
- webhook-receiver

## Secrets Management

⚠️ **CRITICAL**: Never commit real secrets to Git!

### Option 1: Kubernetes Secrets (Dev only)
Edit `k8s/base/secrets.yaml` and replace all `CHANGE_ME` values.

### Option 2: AWS Secrets Manager (Recommended)
```bash
# Create secrets in AWS
aws secretsmanager create-secret \
  --name maezo/db-credentials \
  --secret-string '{"password":"secure-password"}'

# Use External Secrets Operator
helm install external-secrets external-secrets/external-secrets
```

### Option 3: HashiCorp Vault
Integrate with Vault CSI driver for secrets injection.

## Monitoring

### Grafana Dashboards

Pre-configured dashboards:
- MAEZO Overview (BPM metrics)
- Worker Performance
- FHIR Server Health
- Revenue Cycle KPIs

Access: https://grafana.{env}.austa.com.br

### Prometheus Alerts

Critical alerts configured:
- CIB Seven down
- Worker external task timeout
- FHIR server latency > 500ms
- Kafka consumer lag > 1000

### Log Aggregation

All components output JSON logs compatible with:
- Fluentd → Elasticsearch
- AWS CloudWatch
- Datadog

## Troubleshooting

### CIB Seven not starting
```bash
kubectl -n maezo logs -l app.kubernetes.io/component=bpm-engine
kubectl -n maezo describe pod -l app.kubernetes.io/component=bpm-engine
```

### Workers not processing tasks
```bash
# Check external task locks
kubectl -n maezo exec -it deploy/maezo-cib-seven -- \
  curl http://localhost:8080/engine-rest/external-task?active=true
```

### FHIR queries slow
```bash
# Check PostgreSQL connections
kubectl -n maezo exec -it maezo-postgresql-0 -- \
  psql -U fhir -c "SELECT count(*) FROM pg_stat_activity"
```

## CI/CD

GitHub Actions workflow at `.github/workflows/ci-cd.yaml`:
- Lint + static analysis
- Unit tests with coverage
- DMN/BPMN validation
- Docker image build
- Helm deployment
- Integration tests

## Next Steps

1. [ ] Configure AWS EKS cluster
2. [ ] Set up Debezium for TASY CDC
3. [ ] Configure external secrets
4. [ ] Enable TLS with cert-manager
5. [ ] Run shadow mode with Bradesco
