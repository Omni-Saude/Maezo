# SWARM P - REVENUE CYCLE SERVICE WORKERS V2 MIGRATION

## Command for Copy-Paste Execution

```bash
npx @claude-flow/cli@latest hive-mind swarm \
  --workers 11 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --use-vectors \
  --use-learning \
  --task "SWARM P: Revenue Cycle Service Workers v2 Migration

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OBJECTIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Refactor 10 revenue_cycle service workers with external API integrations → ServiceWorker archetype pattern. Extract API orchestration to service layer, eliminate AP1-AP5 anti-patterns (including AP5: queen-as-coder where workers contain complex API handling logic). Target: 70-80 lines avg (current: 119.4), 100% delegation to service classes, clear separation API client/worker concerns.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE: 10 REVENUE_CYCLE SERVICE WORKERS (ACTIVE, 1194 LINES TOTAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
billing/workers/generate_tiss_xml_worker_v2.py        121 lines  TISSClient
billing/workers/retry_failed_submission_worker_v2.py   162 lines  TasyApiClient, TISSClient
billing/workers/submit_to_payer_worker_v2.py           122 lines  TasyApiClient, TISSClient
billing/workers/validate_tiss_schema_worker_v2.py      129 lines  TISSClient
coding/workers/extract_clinical_data_worker_v2.py      157 lines  FHIRClient
collection/workers/export_to_erp_worker.py              86 lines  TasyApiClient, MvSoulClient
production/workers/assign_prices_worker_v2.py          117 lines  TasyApiClient
production/workers/capture_procedure_worker_v2.py      108 lines  TasyApiClient, MvSoulClient
production/workers/enrich_procedure_worker_v2.py        92 lines  FHIRClient, TasyApiClient
production/workers/persist_production_worker_v2.py     100 lines  FHIRClient

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTI-PATTERN SIGNATURES (AP1-AP5 DETECTION)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AP1_HARDCODED_RULES: (WEIGHT=|THRESHOLD=|CONSTANT=|rates=\\{|if.*>\\s*\\d+)
AP2_EMBEDDED_WORKFLOW: (try:.*except.*fallback|for\\s+attempt|retry_count|sequential.*chain)
AP3_COMPLEX_CONDITIONALS: (def\\s+_calculate|if.*elif.*elif|nested\\s+if|_compute_|_transform_)
AP4_EMBEDDED_DECISION_TABLES: (\\w+_map\\s*=\\s*\\{|lookup_table|TYPE_.*=\\s*\\{|STATUS_MAP)
AP5_QUEEN_AS_CODER: (async\\s+def\\s+_[a-z_]{15,}|class.*:\\s*\"\"\".*\\n(\\s+def\\s+_){5,}|len\\(inspect\\.getmembers\\)>8)

Explanation AP5: Workers should be thin glue (60-80 lines). If worker has 5+ private helper methods OR 15+ char private method names OR >8 methods total, it's doing coordinator's job (queen-as-coder anti-pattern). Extract to service classes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TARGET PATTERN: ServiceWorker ARCHETYPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@worker(topic='domain.action')
class XxxWorker(BaseWorker):
    def __init__(self):
        super().__init__()
        self.service = XxxService()  # ← NEW: Dedicated service class
    
    @property
    def operation_name(self) -> str:
        return _(\"Action description\")
    
    async def execute_task(self, task_variables: dict) -> dict:
        result = await self.service.execute(
            tenant_id=get_required_tenant(),
            **extract_inputs(task_variables)
        )
        return {\"success\": True, \"data\": result}

Target: 60-80 lines, 2-3 methods, 0 helpers, 100% delegation to service layer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEW: SERVICE LAYER CLASSES (10 FILES TO CREATE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
healthcare_platform/revenue_cycle/billing/services/tiss_generation_service.py
healthcare_platform/revenue_cycle/billing/services/claim_submission_service.py
healthcare_platform/revenue_cycle/billing/services/tiss_validation_service.py
healthcare_platform/revenue_cycle/coding/services/clinical_data_extraction_service.py
healthcare_platform/revenue_cycle/collection/services/erp_export_service.py
healthcare_platform/revenue_cycle/production/services/pricing_assignment_service.py
healthcare_platform/revenue_cycle/production/services/procedure_capture_service.py
healthcare_platform/revenue_cycle/production/services/procedure_enrichment_service.py
healthcare_platform/revenue_cycle/production/services/production_persistence_service.py

Responsibility: Service classes orchestrate multiple API clients (TASY, FHIR, TISS, ANS), implement retry logic, error handling, data transformation, business workflows. Workers become thin wrappers that delegate to service.execute().

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXECUTION PHASES (5 TIERS WITH BLOCKING)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TIER 1: EXTRACTION (2 agents, parallel) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent P1A (extractor): Scan 10 workers → identify AP1-AP5 instances → map API calls → classify service patterns → output JSON manifest
Agent P1B (analyzer): Read worker code → extract API client dependencies → identify retry/fallback logic → map data transformations → output service requirements

Deliverable: swarm-P-extraction-manifest.json
{
  \"workers\": [{\"path\": \"...\", \"lines\": 121, \"api_clients\": [\"TISSClient\"], \"anti_patterns\": {\"AP1\": 2, \"AP3\": 4, \"AP5\": 8}, \"service_methods\": [\"generate_tiss_xml\", \"validate_schema\", \"retry_submission\"]}],
  \"service_classes_needed\": 9,
  \"total_api_calls\": 47,
  \"complexity\": \"MEDIUM\"
}

Validation: python3 -c 'import json; json.load(open(\"swarm-P-extraction-manifest.json\"))' && test $(jq '.workers | length' swarm-P-extraction-manifest.json) -eq 10

BLOCKING CONDITION: Manifest must exist, validate as JSON, contain 10 workers

TIER 2: SERVICE CREATION (3 agents, parallel) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent P2A (service-billing): Create 3 service classes (tiss_generation, claim_submission, tiss_validation) → extract API orchestration → implement retry logic → add error handling
Agent P2B (service-coding-collection): Create 2 service classes (clinical_data_extraction, erp_export) → multi-client coordination → data transformation
Agent P2C (service-production): Create 4 service classes (pricing_assignment, procedure_capture, procedure_enrichment, production_persistence) → API aggregation → business workflows

Deliverable: 9 service class files in healthcare_platform/revenue_cycle/*/services/
Pattern: class XxxService → __init__(self, tasy_client, fhir_client, ...) → async def execute(tenant_id, **inputs) → orchestrate API calls → return result

Validation: find healthcare_platform/revenue_cycle -path '*/services/*_service.py' -type f | wc -l | grep -q '^9$' && python3 -m py_compile healthcare_platform/revenue_cycle/*/services/*_service.py

BLOCKING CONDITION: 9 service files exist, all compile without syntax errors

TIER 3: WORKER MIGRATION (3 agents, parallel) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent P3A (migrate-billing-coding): Refactor 5 workers (4 billing + 1 coding) → replace API logic with service.execute() → reduce to 60-80 lines → eliminate AP1-AP5
Agent P3B (migrate-collection-production-1): Refactor 3 workers (1 collection + 2 production) → thin wrapper pattern → service delegation
Agent P3C (migrate-production-2): Refactor 2 workers (production persist + enrich) → remove helper methods → pure glue code

Deliverable: 10 refactored workers, avg 70 lines, 0 AP1-AP5 instances

Validation: for f in billing/workers/*_v2.py coding/workers/*_v2.py collection/workers/export_to_erp_worker.py production/workers/*_v2.py; do python3 -m py_compile healthcare_platform/revenue_cycle/\$f; done && test $(find healthcare_platform/revenue_cycle -name '*worker*v2.py' -o -name 'export_to_erp_worker.py' | xargs wc -l | tail -1 | awk '{print \$1}') -lt 800

BLOCKING CONDITION: All 10 workers compile, total lines <800 (avg 80)

TIER 4: TESTING (2 agents, parallel) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent P4A (unit-tests): Create/update unit tests for 9 service classes → mock API clients → test error handling → validate outputs
Agent P4B (integration-tests): Create/update integration tests for 10 workers → test service delegation → validate BPMN variables → check error propagation

Deliverable: >90% test pass rate

Validation: python3 -m pytest tests/revenue_cycle -v --tb=short -k 'service or worker' | tee /tmp/swarm-p-test-results.txt && grep -q 'passed' /tmp/swarm-p-test-results.txt

BLOCKING CONDITION: Test pass rate >90%, no syntax errors

TIER 5: VERIFICATION (1 agent) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent P5 (verifier): Scan 10 workers → detect AP1-AP5 → count lines → validate service delegation → check test coverage → generate completion report

Validation Commands:
1. Anti-pattern check: grep -rE 'def _[a-z_]{15,}|WEIGHT\\s*=|if.*elif.*elif' healthcare_platform/revenue_cycle/billing/workers/*_v2.py healthcare_platform/revenue_cycle/coding/workers/*_v2.py healthcare_platform/revenue_cycle/collection/workers/export_to_erp_worker.py healthcare_platform/revenue_cycle/production/workers/*_v2.py || echo 'PASS: 0 anti-patterns'
2. Line count: find healthcare_platform/revenue_cycle -name '*worker*v2.py' -o -name 'export_to_erp_worker.py' | xargs wc -l | tail -1 | awk '{if(\$1<800) print \"PASS: Total lines <800\"; else print \"FAIL\"}'
3. Service delegation: grep -r 'self\\.service\\.' healthcare_platform/revenue_cycle/billing/workers/*_v2.py healthcare_platform/revenue_cycle/coding/workers/*_v2.py healthcare_platform/revenue_cycle/collection/workers/export_to_erp_worker.py healthcare_platform/revenue_cycle/production/workers/*_v2.py | wc -l | awk '{if(\$1>=10) print \"PASS: All workers delegate to service\"; else print \"FAIL\"}'
4. Service files exist: test $(find healthcare_platform/revenue_cycle -path '*/services/*_service.py' | wc -l) -eq 9 && echo 'PASS: 9 service classes created'

Deliverable: swarm-P-completion-report.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXIT CRITERIA (11 TOTAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. All 10 workers migrated to ServiceWorker archetype pattern
2. 9 service classes created in revenue_cycle/*/services/
3. All service classes compile without syntax errors
4. All workers compile without syntax errors  
5. Test pass rate >90% (service + worker tests)
6. Anti-pattern count = 0 (AP1-AP5 eliminated)
7. Total worker lines <800 (avg <80 per worker, was 119.4)
8. All workers use self.service.execute() delegation pattern
9. 0 workers with >5 methods (thin workers enforced)
10. 0 workers with private helper methods >15 chars (queen-as-coder eliminated)
11. Code reduction >40% (1194 lines → <700 lines)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON CONTEXT (PREVENT PATTERN DIVERGENCE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BaseWorker: healthcare_platform/revenue_cycle/billing/workers/base.py
Imports: from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
         from healthcare_platform.shared.i18n import _
         from healthcare_platform.shared.multi_tenant.context import get_required_tenant
Error handling: BpmnErrorException, ExternalServiceException, ValidationError
Decorator: @worker(topic='domain.action', max_jobs=3, lock_duration=300000)
Service pattern: service.execute(tenant_id, **inputs) → return dict

ADR References:
- ADR-003: External Task Workers (thin workers, delegation mandatory)
- ADR-013: Claude Flow Swarm Intelligence (hierarchical-mesh, byzantine consensus)
- ADR-016: Thin Workers (max 100 lines, <5 methods, 0 helpers) [PROPOSED, enforce now]
- ADR-017: Worker Archetypes (ServiceWorker = API orchestration delegation) [PROPOSED, enforce now]

AP5 Queen-as-Coder Explanation: In ADR-013, architect/coordinator agents should plan and delegate, not code. Same principle applies to workers: they should coordinate (thin glue), not implement (complex logic). When workers have 8+ methods, 5+ helpers, or 15+ char private method names, they're doing service layer's job. Extract to XxxService class, worker becomes pure delegation.

Swarm O Benchmark: 48 collection workers, 7501→3333 lines (55.6% reduction), 156 anti-patterns eliminated, 12 DMN tables, 13/13 exit criteria PASSED. Follow same quality standards.

Memory Keys Available:
- swarm-O-completion: Collection workers success metrics
- collection-workers-refactoring-strategy: Anti-pattern analysis approach
- phase-3-final-summary: 95 v2 workers total, pattern compliance

Neural Patterns:
- refactoring-patterns (89% accuracy, 11.5K usage)
- code-review-patterns (90% accuracy, 16.5K usage)
- 3-tier-swarm (RECON→CODER→VERIFIER)
- thin-workers (P2: <80 lines, 0 helpers, 100% delegation)
- separation-of-concerns (P4: Worker=glue, Service=orchestration, API Client=integration)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXECUTION SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workers: 11 (2 extractors, 3 service creators, 3 migrators, 2 testers, 1 verifier)
Topology: hierarchical-mesh (1 coordinator + 10 specialists)
Consensus: byzantine (fault-tolerant voting)
Phases: 5 tiers with blocking conditions
Scope: 10 revenue_cycle service workers ONLY (billing, coding, collection, production)
Excluded: clinical_operations, patient_access, platform_services workers
Duration: 15-20 hours estimated
Model: Intelligent routing (SONNET for refactoring, reasoning for validation)
Output: 10 thin workers (60-80 lines), 9 service classes, >90% test pass rate, 0 AP1-AP5
"
```

## Pre-Task Hook Registration

```bash
npx @claude-flow/cli@latest hooks pre-task \
  --task-id "swarm-P-service-workers-v2-migration" \
  --description "Swarm P - Revenue cycle service workers v2 migration: 10 workers with external API integrations (TASY, FHIR, TISS, MvSoul) → ServiceWorker archetype. Extract API orchestration to 9 service classes, eliminate AP1-AP5 (including queen-as-coder). Target: 1194→700 lines (41% reduction), 119.4→70 avg, 100% delegation. Estimated 15-20 hours, 11 agents." \
  --namespace healthcare-platform
```

## Memory Store

```bash
npx @claude-flow/cli@latest memory store \
  --key "swarm-P-service-workers-scope" \
  --namespace healthcare-platform \
  --value "Swarm P: 10 revenue_cycle service workers (billing 4, coding 1, collection 1, production 4). Current: 1194 lines total, 119.4 avg. Target: <800 lines total, <80 avg. Create 9 service classes for API orchestration. Eliminate AP5 queen-as-coder: extract complex API handling to service layer. EXCLUDED: clinical_operations, patient_access, platform_services workers (not in scope)."
```

---

**Session:** 2026-02-16  
**Swarm:** P (Service Workers v2 Migration)  
**Benchmark:** Swarm O (55.6% reduction, 13/13 PASS)  
**Scope:** Revenue cycle only (10 workers)  
**New Anti-Pattern:** AP5 Queen-as-Coder (workers with >8 methods, >5 helpers, or complex API orchestration)
