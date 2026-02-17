# SWARM P - MISSING INITIALIZATION COMMAND

## What's Missing: Hive-Mind Init

Before running the swarm command, you need to initialize the hive-mind topology:

```bash
npx @claude-flow/cli@latest hive-mind init \
  --topology hierarchical-mesh \
  --max-agents 15 \
  --consensus byzantine
```

**Why this is required (from ADR-013):**
- Sets up hierarchical-mesh topology (coordinator + specialists)
- Configures Byzantine consensus (fault-tolerant, tolerates 33% failures)
- Prepares swarm infrastructure before spawning workers

## Complete Execution Sequence

```bash
# STEP 1: Initialize hive-mind (MISSING - run this first!)
npx @claude-flow/cli@latest hive-mind init \
  --topology hierarchical-mesh \
  --max-agents 15 \
  --consensus byzantine

# STEP 2: Register pre-task hook
npx @claude-flow/cli@latest hooks pre-task \
  --task-id "swarm-P-service-workers-v2-migration" \
  --description "Swarm P - Revenue cycle service workers v2 migration: 10 workers with external API integrations (TASY, FHIR, TISS, MvSoul) → ServiceWorker archetype. Extract API orchestration to 9 service classes, eliminate AP1-AP5 (including queen-as-coder). Target: 1194→700 lines (41% reduction), 119.4→70 avg, 100% delegation. Estimated 15-20 hours, 11 agents." \
  --namespace healthcare-platform

# STEP 3: Store scope in memory
npx @claude-flow/cli@latest memory store \
  --key "swarm-P-service-workers-scope" \
  --namespace healthcare-platform \
  --value "Swarm P: 10 revenue_cycle service workers (billing 4, coding 1, collection 1, production 4). Current: 1194 lines total, 119.4 avg. Target: <800 lines total, <80 avg. Create 9 service classes for API orchestration. Eliminate AP5 queen-as-coder: extract complex API handling to service layer. EXCLUDED: clinical_operations, patient_access, platform_services workers (not in scope)."

# STEP 4: Run the swarm (already provided in SWARM_P_COMMAND.md)
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
  --task "[full task from SWARM_P_COMMAND.md]"
```

## ADR-013 Reference

From section 5 "Hive-Mind Swarm Coordination":

> **Implementation:**
> ```bash
> # Initialize swarm
> npx @claude-flow/cli@latest hive-mind init \
>   --topology hierarchical-mesh \
>   --max-agents 15 \
>   --consensus byzantine
> 
> # Spawn coordinated swarm
> npx @claude-flow/cli@latest hive-mind spawn \
>   --workers 10 \
>   --role specialist \
>   --topology hierarchical-mesh \
>   --consensus byzantine \
>   --claude \
>   --objective "[detailed objective]"
> ```

The `init` command was in the standard pattern but wasn't included in the Swarm P command document.
