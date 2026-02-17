# SWARM P - CORRECTED EXECUTION COMMANDS

## Issue Found

The command used `hive-mind swarm` but the correct subcommand is `hive-mind spawn`.

**Error causes:**
- `--task` parameter doesn't exist (should be `--objective` or `-o`)
- `hive-mind swarm` subcommand doesn't exist
- Validation commands with shell escaping issues embedded in task description

## Corrected Execution Sequence

```bash
# STEP 1: Initialize hive-mind
npx @claude-flow/cli@latest hive-mind init

# STEP 2: Spawn swarm with --claude flag (launches interactive Claude Code sessions)
npx @claude-flow/cli@latest hive-mind spawn \
  -n 11 \
  --claude \
  -o "SWARM P: Revenue Cycle Service Workers v2 Migration

OBJECTIVE: Refactor 10 revenue_cycle service workers with external API integrations to ServiceWorker archetype pattern. Extract API orchestration to service layer, eliminate AP1-AP5 anti-patterns (AP5: queen-as-coder where workers contain complex API handling logic). Target: 70-80 lines avg (current: 119.4), 100% delegation to service classes.

SCOPE - 10 REVENUE_CYCLE SERVICE WORKERS (1194 LINES TOTAL):
- billing/workers/generate_tiss_xml_worker_v2.py (121 lines, TISSClient)
- billing/workers/retry_failed_submission_worker_v2.py (162 lines, TasyApiClient, TISSClient)
- billing/workers/submit_to_payer_worker_v2.py (122 lines, TasyApiClient, TISSClient)
- billing/workers/validate_tiss_schema_worker_v2.py (129 lines, TISSClient)
- coding/workers/extract_clinical_data_worker_v2.py (157 lines, FHIRClient)
- collection/workers/export_to_erp_worker.py (86 lines, TasyApiClient, MvSoulClient)
- production/workers/assign_prices_worker_v2.py (117 lines, TasyApiClient)
- production/workers/capture_procedure_worker_v2.py (108 lines, TasyApiClient, MvSoulClient)
- production/workers/enrich_procedure_worker_v2.py (92 lines, FHIRClient, TasyApiClient)
- production/workers/persist_production_worker_v2.py (100 lines, FHIRClient)

ANTI-PATTERNS TO ELIMINATE:
AP1_HARDCODED_RULES: WEIGHT=, THRESHOLD=, hardcoded rates
AP2_EMBEDDED_WORKFLOW: try/except fallback chains, retry loops
AP3_COMPLEX_CONDITIONALS: _calculate methods, if/elif chains
AP4_EMBEDDED_DECISION_TABLES: lookup dicts, TYPE_MAP constants
AP5_QUEEN_AS_CODER: 5+ private helpers, 15+ char method names, 8+ methods total

TARGET PATTERN - ServiceWorker Archetype:
@worker(topic='domain.action')
class XxxWorker(BaseWorker):
    def __init__(self):
        super().__init__()
        self.service = XxxService()  # NEW: Dedicated service class
    
    async def execute_task(self, task_variables: dict) -> dict:
        result = await self.service.execute(
            tenant_id=get_required_tenant(),
            **extract_inputs(task_variables)
        )
        return {\"success\": True, \"data\": result}

NEW SERVICE LAYER - 9 SERVICE CLASSES TO CREATE:
healthcare_platform/revenue_cycle/billing/services/tiss_generation_service.py
healthcare_platform/revenue_cycle/billing/services/claim_submission_service.py
healthcare_platform/revenue_cycle/billing/services/tiss_validation_service.py
healthcare_platform/revenue_cycle/coding/services/clinical_data_extraction_service.py
healthcare_platform/revenue_cycle/collection/services/erp_export_service.py
healthcare_platform/revenue_cycle/production/services/pricing_assignment_service.py
healthcare_platform/revenue_cycle/production/services/procedure_capture_service.py
healthcare_platform/revenue_cycle/production/services/procedure_enrichment_service.py
healthcare_platform/revenue_cycle/production/services/production_persistence_service.py

EXECUTION PHASES (5 TIERS WITH BLOCKING):
TIER 1 (2 agents): Scan workers, identify AP1-AP5, map API calls, output JSON manifest
TIER 2 (3 agents): Create 9 service classes with API orchestration
TIER 3 (3 agents): Refactor 10 workers to thin wrappers (60-80 lines)
TIER 4 (2 agents): Unit + integration tests, 90% pass rate
TIER 5 (1 agent): Verify 0 anti-patterns, generate completion report

EXIT CRITERIA (11 TOTAL):
1. All 10 workers migrated to ServiceWorker archetype
2. 9 service classes created in revenue_cycle/*/services/
3. All service classes compile without errors
4. All workers compile without errors
5. Test pass rate >90%
6. Anti-pattern count = 0 (AP1-AP5 eliminated)
7. Total worker lines <800 (avg <80, was 119.4)
8. All workers use self.service.execute() delegation
9. 0 workers with >5 methods
10. 0 workers with private helpers >15 chars
11. Code reduction >40% (1194 → <700 lines)

COMMON CONTEXT:
- BaseWorker: healthcare_platform/revenue_cycle/billing/workers/base.py
- ADR-003: External Task Workers (thin, delegation mandatory)
- ADR-013: Swarm Intelligence (hierarchical-mesh, byzantine)
- ADR-016: Thin Workers max 100 lines (PROPOSED, enforce now)
- ADR-017: Worker Archetypes (PROPOSED, enforce now)
- Swarm O Benchmark: 55.6% reduction, 13/13 PASS, 156 anti-patterns eliminated
- Memory namespace: healthcare-platform
- Excluded: clinical_operations, patient_access, platform_services workers

AGENT ROLES:
- 2 extractors (anti-pattern analysis, service requirements)
- 3 service creators (billing, coding/collection, production)
- 3 migrators (thin worker refactoring)
- 2 testers (unit, integration)
- 1 verifier (final validation, completion report)
"
```

## Alternative: Simplified Task Submission

If the above is too long, use the `task` subcommand to submit the objective separately:

```bash
# STEP 1: Initialize
npx @claude-flow/cli@latest hive-mind init

# STEP 2: Submit task to hive
npx @claude-flow/cli@latest hive-mind task \
  --description "Swarm P: Refactor 10 revenue_cycle service workers to ServiceWorker archetype. Create 9 service classes for API orchestration. Eliminate AP1-AP5 anti-patterns. Target: 1194→700 lines (40% reduction), avg 119→70 lines/worker. See docs/audit/SWARM_P_COMMAND.md for full specification." \
  --priority high

# STEP 3: Spawn workers to execute the task
npx @claude-flow/cli@latest hive-mind spawn \
  -n 11 \
  --claude
```

## Post-Execution Commands

After swarm completes, run:

```bash
# Register completion
npx @claude-flow/cli@latest hooks post-task \
  --task-id "swarm-P-service-workers-v2-migration" \
  --status success \
  --namespace healthcare-platform

# Store completion metrics
npx @claude-flow/cli@latest memory store \
  --key "swarm-P-completion" \
  --namespace healthcare-platform \
  --value "Swarm P COMPLETE: 10 service workers migrated, 9 service classes created, <stats from completion report>"
```

## Key Differences from Original Command

**WRONG (what was attempted):**
- `hive-mind swarm` → doesn't exist
- `--task "long text"` → doesn't exist
- Embedded validation commands with escaping issues

**CORRECT (ADR-013 pattern):**
- `hive-mind spawn` → correct subcommand
- `-o "objective"` or `--objective` → correct parameter
- `-n 11` → number of workers
- `--claude` → launches interactive Claude Code sessions
- No embedded shell commands in objective text
