npx @claude-flow/cli@latest hive-mind spawn \
  --workers 6 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --use-vectors \
  --use-learning \
  --objective "SWARM PRODUCTION_PREP: IaC + CI/CD Readiness | 7 deliverables | ADR-002,010,012 compliance

MEMORY: production-prep-scope, pattern-complete-swarm-workflow, handoff-production-prep
WORKSPACE: /Users/rodrigo/claude-projects/Ochestrator-CIB7-OP/Healthcare-Orchest-CIB7
DURATION: 25-35min | PYTHON: 3.12

PRIMARY DELIVERABLES:
1. helm/maestro/values-prod.yaml
2. k8s/overlays/staging/kustomization.yaml + patches
3. k8s/overlays/prod/kustomization.yaml + patches  
4. tests/smoke/__init__.py + conftest.py + 5 test files
5. docs/runbooks/ROLLBACK.md
6. docs/runbooks/PERFORMANCE_BASELINE.md
7. scripts/validate_tenant_isolation.py

ANTI-PATTERNS TO AVOID:
❌AP7: No throwaway scripts in .swarm/ - commit to proper locations
❌AP1: No hardcoded credentials - use K8s secrets references
❌AP2: No single-tenant assumptions - validate tenant markers
❌ Queen coding directly — DELEGATE to specialist agents
❌ Skip verification — Tier 6 MUST validate all changes

━━━ EXISTING CODE (READ BEFORE WRITING) ━━━
HELM BASE: helm/maestro/values.yaml (679 LOC)
  cibSeven.replicaCount: 2 (ADR-012)
  global.tenants: 4 tenants (hospital-a, amh-sp-morumbi, amh-rj-barra, amh-mg-bh)
  observability: prometheus+grafana+alertmanager (ADR-010)
  workers.domains: revenueCycle, patientAccess, clinicalOperations, platformServices
  postgresql.primary.persistence.size: 100Gi
  kafka.broker.replicaCount: 3
  
HELM STAGING: helm/maestro/values-staging.yaml (157 LOC)
  global.environment: staging
  global.domain: staging.austa.com.br
  cibSeven.replicaCount: 2
  workers reduced replicas, smaller autoscaling
  observability.prometheus.retention: 15d
  
CI/CD: .github/workflows/ci-cd.yaml (363 LOC)
  jobs: lint, test, dmn-validation, validate-bpmn, build, deploy, integration-test
  helm upgrade --install with values overlay pattern
  Docker images: workers, cdc-bridge, webhook-receiver
  
K8S BASE: k8s/base/namespace.yaml (103 LOC), network-policies.yaml, secrets.yaml
  namespace: maestro
  serviceAccount: maestro
  Role: read configmaps/secrets/pods

DOCKER-COMPOSE: docker-compose.yml (local stack reference)

ADR-002: Multi-tenancy with tenant markers, federation model, 4 tenants
ADR-010: Observability stack (Prometheus, Grafana, AlertManager, ins7ght)
ADR-012: Engine replicas phased (1→2, database locking, jdbcPoolSize: 50)

━━━ PHASE 1: RECON (1 agent) ━━━
READ: helm/maestro/values.yaml, values-staging.yaml, .github/workflows/ci-cd.yaml, k8s/base/*.yaml, docker-compose.yml
READ: docs/ADRs/002-single-engine-tenant-markers.md, 010-observability-stack.md, 012-engine-replicas-phased.md
EXTRACT: Production requirements (replica counts, resource limits, ingress domains, TLS secrets, PDB configs, autoscaling thresholds)
OUTPUT: .swarm/phase1-requirements.json (internal, for Phase 2-6)

━━━ PHASE 2: HELM PRODUCTION VALUES (1 agent) ━━━
CREATE: helm/maestro/values-prod.yaml
SPEC:
  global:
    environment: production
    domain: austa.com.br  # NOT staging subdomain
  
  cibSeven:
    replicaCount: 2  # ADR-012 Phase 2+
    resources:  # SAME as values.yaml base (full production sizing)
      requests: {memory: 2Gi, cpu: 1000m}
      limits: {memory: 4Gi, cpu: 2000m}
    ingress:
      hosts: [{host: bpm.austa.com.br}]
      tls: [{secretName: bpm-tls, hosts: [bpm.austa.com.br]}]
  
  workers:
    domains:
      revenueCycle: {replicaCount: 3, autoscaling: {minReplicas: 2, maxReplicas: 6}}
      patientAccess: {replicaCount: 2, autoscaling: {minReplicas: 2, maxReplicas: 4}}
      clinicalOperations: {replicaCount: 2, autoscaling: {minReplicas: 2, maxReplicas: 6}}
      platformServices: {replicaCount: 2, autoscaling: {minReplicas: 2, maxReplicas: 4}}
  
  hapiFhir:
    replicaCount: 2
    resources: {requests: {memory: 2Gi, cpu: 1000m}, limits: {memory: 4Gi, cpu: 2000m}}
    ingress:
      hosts: [{host: fhir.austa.com.br}]
      tls: [{secretName: fhir-tls, hosts: [fhir.austa.com.br]}]
  
  postgresql:
    primary: {persistence: {size: 100Gi}}
    readReplicas: {replicaCount: 1}
  
  kafka:
    controller: {replicaCount: 3}
    broker: {replicaCount: 3, persistence: {size: 50Gi}}
  
  redis:
    replica: {replicaCount: 2}
  
  observability:
    prometheus: {retention: 30d}  # NOT 15d like staging
    grafana:
      ingress:
        hosts: [grafana.austa.com.br]
        tls: [{secretName: grafana-tls, hosts: [grafana.austa.com.br]}]
  
  networkPolicies: {enabled: true}
  podDisruptionBudgets:
    cibSeven: {minAvailable: 1}
    hapiFhir: {minAvailable: 1}
    workers: {minAvailable: 1}

VALIDATE: helm template maestro helm/maestro -f helm/maestro/values.yaml -f helm/maestro/values-prod.yaml 2>&1 | grep -i error

━━━ PHASE 3: KUSTOMIZE OVERLAYS (2 agents, parallel) ━━━
P3A - STAGING OVERLAY:
  CREATE: k8s/overlays/staging/kustomization.yaml
  SPEC:
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    namespace: maestro-staging
    bases: [../../base]
    namePrefix: staging-
    commonLabels: {environment: staging}
    patches: [{patch: reduce replicas to 1 for non-HA resources}]
  VALIDATE: kubectl kustomize k8s/overlays/staging/ 2>&1 | grep -i error

P3B - PROD OVERLAY:
  CREATE: k8s/overlays/prod/kustomization.yaml
  SPEC:
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    namespace: maestro
    bases: [../../base]
    namePrefix: prod-
    commonLabels: {environment: production}
    patches: [{patch: strict network policies}, {patch: PodDisruptionBudgets minAvailable=1}]
  VALIDATE: kubectl kustomize k8s/overlays/prod/ 2>&1 | grep -i error

━━━ PHASE 4: SMOKE TESTS (1 agent) ━━━
CREATE: tests/smoke/__init__.py (empty marker)

CREATE: tests/smoke/conftest.py
  FIXTURES: camunda_client, fhir_client, kafka_producer, redis_client, keycloak_client
  ENV VARS: CAMUNDA_BASE_URL, FHIR_BASE_URL, KAFKA_BOOTSTRAP_SERVERS, REDIS_URL, KEYCLOAK_URL
  
CREATE: tests/smoke/test_health.py
  test_cib_seven_health: GET /engine-rest/engine → 200
  test_fhir_server_health: GET /fhir/metadata → 200
  test_redis_ping: redis.ping() → True
  test_kafka_broker_list: kafka.list_topics() → success

CREATE: tests/smoke/test_auth.py
  test_keycloak_realm_exists: GET /auth/realms/austa-bpm → 200
  test_worker_service_account_token: obtain token, verify valid

CREATE: tests/smoke/test_tenant.py (ADR-002)
  test_tenant_markers_in_deployments: list deployments, verify tenantId in metadata
  test_cross_tenant_isolation: start process in tenant A, verify tenant B cannot see it

CREATE: tests/smoke/test_bpmn.py
  test_deploy_simple_process: deploy hello-world.bpmn → 200
  test_start_process_instance: start process, verify state=ACTIVE

CREATE: tests/smoke/test_dmn.py
  test_deploy_dmn_table: deploy simple DMN → 200
  test_evaluate_decision: evaluate with test input, verify output matches expected

DEPENDENCIES: pytest, requests, httpx, redis, kafka-python
VALIDATE: pytest tests/smoke/ --collect-only 2>&1 | grep -c 'test session starts' → 1

━━━ PHASE 5: RUNBOOKS (2 agents, parallel) ━━━
P5A - ROLLBACK RUNBOOK:
  CREATE: docs/runbooks/ROLLBACK.md
  STRUCTURE:
    # Rollback Procedure
    ## 3-Step Rollback
    ### Step 1: Helm Rollback
    helm rollback maestro <REVISION> -n maestro --wait
    kubectl -n maestro get pods -w
    ### Step 2: Verify Deployments  
    kubectl -n maestro rollout status deployment/maestro-cib-seven
    kubectl -n maestro get pods | grep -v Running
    ### Step 3: Validate Engine Health
    curl https://bpm.austa.com.br/engine-rest/engine
    
    ## Common Failure Scenarios
    - Migration failure → helm rollback, restore DB snapshot
    - Worker OOMKilled → reduce autoscaling maxReplicas
    - Database connection pool exhausted → increase jdbcPoolSize in values
    - Kafka consumer lag spike → check worker logs, scale up replicas
    
    ## Emergency Contacts
    DevOps Lead: devops@austa.com.br
    Slack: #incidents-maestro
    PagerDuty: https://austa.pagerduty.com

P5B - PERFORMANCE BASELINE:
  CREATE: docs/runbooks/PERFORMANCE_BASELINE.md
  STRUCTURE:
    # Performance Baseline
    ## Expected Metrics (Production)
    | Metric | P50 | P95 | P99 |
    |--------|-----|-----|-----|
    | Process Start Latency | <200ms | <500ms | <1s |
    | External Task Fetch | <100ms | <300ms | <500ms |
    | DMN Evaluation | <50ms | <150ms | <300ms |
    | FHIR Read | <100ms | <250ms | <500ms |
    | Worker Task Execution | <2s | <5s | <10s |
    
    ## Throughput
    - Process Instances/day: 10,000 target, 50,000 peak capacity
    - External Tasks/minute: 500 sustained, 2,000 burst
    - DMN Evaluations/second: 100 sustained
    
    ## Error Rate
    - Process start failures: <0.1%
    - Worker task failures: <1% (after 3 retries)
    - FHIR API errors: <0.5%
    
    ## Resource Utilization
    - CIB Seven CPU: 60-80% avg, <90% peak
    - PostgreSQL connections: <70% pool usage (35/50)
    - Kafka consumer lag: <1,000 messages
    - Redis memory: <80% capacity
    
    ## SLA Thresholds (Alertmanager)
    - P95 latency >1s for 5min → P2 alert
    - Error rate >5% for 2min → P1 alert
    - Database pool >80% for 3min → P2 alert
    - Worker OOMKilled → P1 alert

━━━ PHASE 6: TENANT ISOLATION VALIDATOR (1 agent) ━━━
CREATE: scripts/validate_tenant_isolation.py
SPEC:
  SHEBANG: Use triple quotes or escaped version to avoid zsh history expansion
  IMPORTS: psycopg2, sys, os, typing
  
  def check_tenant_columns() -> List[str]:
    # Query information_schema for ACT_* tables
    # Verify tenant_id_ column exists in all process/task tables
    # Return list of tables missing tenant_id_
  
  def check_cross_tenant_leakage() -> List[Dict]:
    # Query ACT_RU_EXECUTION, ACT_RU_TASK for valid tenant IDs
    # Verify all rows have tenant_id_ in (hospital-a, amh-sp-morumbi, amh-rj-barra, amh-mg-bh)
    # Return list of rows with invalid/null tenant_id_
  
  def check_deployment_isolation() -> List[Dict]:
    # Query ACT_RE_DEPLOYMENT for tenant markers
    # Verify no global deployments without tenant_id_ (except bootstrap)
  
  def main():
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://camunda:camunda@localhost:5432/camunda')
    conn = psycopg2.connect(DATABASE_URL)
    issues = []
    issues += check_tenant_columns()
    issues += check_cross_tenant_leakage()
    issues += check_deployment_isolation()
    if issues:
      print(f'FAIL: {len(issues)} tenant isolation issues found')
      for issue in issues: print(f'  - {issue}')
      sys.exit(1)
    else:
      print('PASS: Tenant isolation validated')
      sys.exit(0)
  
  if __name__ == '__main__':
    main()

VALIDATE: python3 scripts/validate_tenant_isolation.py --help 2>&1 | head -5

━━━ PHASE 7: VERIFICATION (1 agent) ━━━
OUTPUT: .swarm/production-prep-verification.txt

V1: helm template maestro helm/maestro -f helm/maestro/values-prod.yaml 2>&1 | grep -ci error → 0
V2: kubectl kustomize k8s/overlays/staging/ 2>&1 | grep -ci error → 0
V3: kubectl kustomize k8s/overlays/prod/ 2>&1 | grep -ci error → 0
V4: pytest tests/smoke/ --collect-only 2>&1 | grep -c 'test session starts' → 1
V5: pytest tests/smoke/ --collect-only 2>&1 | grep -oP '\\d+ tests? collected' | grep -oP '\\d+' → >=5
V6: python3 scripts/validate_tenant_isolation.py --help 2>&1 | grep -c 'usage\\|Usage' → >=0
V7: grep -c '### Step' docs/runbooks/ROLLBACK.md → 3
V8: grep -c '| P50 | P95 | P99 |' docs/runbooks/PERFORMANCE_BASELINE.md → >=1
V9: wc -l helm/maestro/values-prod.yaml | awk '{print \$1}' → >100
V10: find k8s/overlays -name 'kustomization.yaml' | wc -l → 2

━━━ EXIT CRITERIA (10 checks) ━━━
✅ helm template values-prod.yaml → valid YAML, 0 errors
✅ kubectl kustomize overlays/staging + overlays/prod → valid manifests, 0 errors
✅ tests/smoke/ → 5+ tests collected
✅ ROLLBACK.md → 3-step procedure documented
✅ PERFORMANCE_BASELINE.md → metrics table with P50/P95/P99
✅ validate_tenant_isolation.py → executable, has main()
✅ values-prod.yaml → production domain (austa.com.br, NOT staging)
✅ values-prod.yaml → 2 replicas for cibSeven (ADR-012)
✅ All deliverables in correct paths (NO .swarm/ files except verification report)
✅ All files pass syntax validation

ROLLBACK: If validation fails, report issues in .swarm/production-prep-verification.txt, do NOT auto-fix

ESTIMATED TIME: 25-35 minutes (6 workers, 7 phases, some parallel)
"