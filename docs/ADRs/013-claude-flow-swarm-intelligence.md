# ADR-013: Claude-flow Swarm Intelligence & Best Practices

**Status:** Approved  
**Date:** 2026-02-09  
**Context:** Code generation using AI swarm intelligence  
**Decision Makers:** Technical Leadership

---

## Context

The Healthcare Orchestration Platform requires generating 500,000+ lines of production code (BPMN processes, Python workers, DMN tables, infrastructure, tests) based on a comprehensive technical specification and 12 architectural decision records. Traditional incremental development would take 8-12 months. We need an accelerated, intelligent approach leveraging AI swarm coordination with claude-flow CLI tools.

This ADR establishes **mandatory best practices** for all code generation tasks using claude-flow and related tools (RuVector, flow-nexus, hive-mind).

---

## Decision

We will use **claude-flow swarm intelligence** as the primary code generation methodology, following these binding principles:

### 1. Memory-First Architecture (No Temporary Markdown Files)

**RULE:** Use claude-flow memory system for all temporary state, progress tracking, and learned patterns. **DO NOT** create markdown files like `PROGRESS.md`, `STATUS.md`, `TODO.md` for tracking work.

**Rationale:**
- Markdown files consume repository space and create noise
- Memory system is semantic-searchable with RuVector HNSW
- Memory entries can be versioned and namespaced
- Automatic cleanup of obsolete state

**Implementation:**
```bash
# Store progress
npx @claude-flow/cli@latest memory store \
  --key "progress-[phase]" \
  --value "[description]" \
  --namespace healthcare-platform

# Store patterns learned
npx @claude-flow/cli@latest memory store \
  --key "pattern-[name]" \
  --value "[what worked]" \
  --namespace patterns

# Search prior work
npx @claude-flow/cli@latest memory search \
  --query "[topic]" \
  --namespace healthcare-platform
```

### 2. Intelligent Model Routing (Cost Efficiency)

**RULE:** Use claude-flow's built-in model routing to automatically select optimal model per task complexity.

**Rationale:**
- Simple tasks (file copying, formatting) → smaller models
- Complex tasks (architecture design, business logic) → advanced models
- Reduces API costs by 40-60%
- Maintains quality where needed

**Implementation:**
```bash
# Automatic routing based on task complexity
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 10 \
  --claude \
  --model-routing intelligent \
  --objective "[task]"

# Models available: claude-3-7-sonnet, claude-3-5-sonnet, claude-3-haiku
# Routing algorithm: Task complexity analysis → model assignment
```

### 3. Lifecycle Hooks (Task Tracking)

**RULE:** Use pre-task and post-task hooks for all significant operations.

**Implementation:**
```bash
# Before any major task
npx @claude-flow/cli@latest hooks pre-task \
  --description "[task description]" \
  --task-id "[unique-id]" \
  --namespace healthcare-platform

# After success
npx @claude-flow/cli@latest hooks post-task \
  --task-id "[unique-id]" \
  --status success \
  --output "[results summary]"

# After failure
npx @claude-flow/cli@latest hooks post-task \
  --task-id "[unique-id]" \
  --status failure \
  --error "[error details]"
```

### 4. Neural Learning (Pattern Extraction)

**RULE:** Train neural models on generated code to continuously improve pattern recognition.

**Implementation:**
```bash
# After generating workers/BPMN/DMN
npx @claude-flow/cli@latest neural train \
  --modelType moe \
  --data-source "platform/workers/[domain]" \
  --epochs 10 \
  --namespace healthcare-platform

# For classification tasks (routing, prioritization)
npx @claude-flow/cli@latest neural train \
  --modelType classifier \
  --training-data .claude-flow/training-data.jsonl \
  --epochs 15

# For complex pattern synthesis
npx @claude-flow/cli@latest neural train \
  --modelType transformer \
  --data-source "platform/" \
  --epochs 20
```

### 5. Hive-Mind Swarm Coordination

**RULE:** Use hierarchical-mesh topology with Byzantine consensus for all parallel code generation.

**Rationale:**
- Hierarchical: Coordinator agents manage specialist agents
- Mesh: Specialists can communicate peer-to-peer
- Byzantine consensus: Fault-tolerant decision making (tolerates up to 33% malicious/failed agents)

**Topology Comparison:**

| Topology | Best For | Max Agents | Fault Tolerance |
|---|---|---|---|
| `hierarchical` | Simple tasks, clear decomposition | 50 | Low |
| `mesh` | Collaborative tasks, peer review | 20 | Medium |
| `hierarchical-mesh` | Complex multi-domain projects | 100+ | High (Byzantine) |

**Implementation:**
```bash
# Initialize swarm
npx @claude-flow/cli@latest hive-mind init \
  --topology hierarchical-mesh \
  --max-agents 15 \
  --consensus byzantine

# Spawn coordinated swarm
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 10 \
  --role specialist \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --objective "[detailed objective]"
```

### 6. RuVector Semantic Search (Knowledge Base)

**RULE:** Store all technical specifications, ADRs, templates in RuVector for semantic retrieval.

**Implementation:**
```bash
# Index documentation
npx @claude-flow/cli@latest vector index \
  --source "docs/" \
  --namespace healthcare-platform \
  --algorithm hnsw \
  --dimensions 768

# Semantic search during generation
npx @claude-flow/cli@latest vector search \
  --query "multi-tenant worker authentication pattern" \
  --namespace healthcare-platform \
  --top-k 5
```

### 7. Comprehensive Tool Usage

**MANDATORY:** Use ALL available claude-flow capabilities, not just basic commands.

**Tool Checklist:**

- [x] `memory` — Store/search context, patterns, progress
- [x] `neural` — Train models on generated code
- [x] `vector` — Semantic search across documentation
- [x] `hive-mind` — Swarm coordination
- [x] `hooks` — Lifecycle tracking
- [x] `patterns` — Pattern library management
- [x] `learn` — Extract patterns from existing code
- [x] `validate` — Quality checks on generated code
- [x] `analyze` — Gap analysis vs. requirements

---

## Consequences

### Positive

- **40-60% cost reduction** via intelligent model routing
- **No repository clutter** from temporary status files
- **Continuous learning** from generated code patterns
- **Fault-tolerant** parallel execution (Byzantine consensus)
- **Semantic knowledge retrieval** (RuVector HNSW)
- **Reproducible** code generation (hooks track all tasks)
- **Scalable** to 100+ parallel agents

### Negative

- **Learning curve** for team (2-3 days training on claude-flow CLI)
- **Dependency** on claude-flow ecosystem (mitigation: open source, Apache 2.0)
- **Complexity** in debugging swarm failures (mitigation: comprehensive logging, dead-letter queues)

---

## Example: Revenue Cycle Worker Generation

### ❌ OLD APPROACH (Avoid)

```bash
# Manually generate workers one by one
# Create progress.md to track status
# No pattern learning
# No cost optimization
# Serial execution only
```

### ✅ NEW APPROACH (Required)

```bash
# 1. Initialize swarm
npx @claude-flow/cli@latest hive-mind init \
  --topology hierarchical-mesh \
  --max-agents 15 \
  --consensus byzantine

# 2. Pre-task hook
npx @claude-flow/cli@latest hooks pre-task \
  --description "Generate revenue cycle workers (89 total)" \
  --task-id "rc-workers-001" \
  --namespace healthcare-platform

# 3. Spawn swarm with intelligent routing
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 10 \
  --role specialist \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --objective "
    Generate 89 revenue cycle Python workers following:
    - Technical spec: docs/Technical specification/technical-specification.md
    - Template: docs/Technical specification/CIB7_WORKER_TEMPLATE.md
    - ADRs: 003 (Python workers), 002 (multi-tenant), 008 (OAuth2)
    - Output: platform/workers/revenue_cycle/
    
    Use memory namespace 'healthcare-platform' for context.
    Store learned patterns in namespace 'patterns'.
    No temporary markdown files.
  "

# 4. Train neural model on generated code
npx @claude-flow/cli@latest neural train \
  --modelType moe \
  --data-source "platform/workers/revenue_cycle/" \
  --epochs 10 \
  --namespace healthcare-platform

# 5. Post-task hook
npx @claude-flow/cli@latest hooks post-task \
  --task-id "rc-workers-001" \
  --status success \
  --output "Generated 89 workers, 25 patterns extracted, 87% test coverage"

# 6. Store patterns for future use
npx @claude-flow/cli@latest memory store \
  --key "pattern-rc-workers" \
  --value "Multi-tenant worker with OAuth2, BPMN error handling, idempotency" \
  --namespace patterns
```

---

## Compliance Verification

Before any code generation sprint:

```bash
# Verify claude-flow version
npx @claude-flow/cli@latest --version
# Required: >= 3.1.0

# Verify RuVector availability
npx @claude-flow/cli@latest vector status

# Verify memory namespace
npx @claude-flow/cli@latest memory list --namespace healthcare-platform

# Verify neural models trained
npx @claude-flow/cli@latest neural list

# Verify hive-mind daemon
npx @claude-flow/cli@latest hive-mind status
```

---

## Related ADRs

- ADR-001: CIB Seven as BPM Engine
- ADR-003: Python External Task Workers
- ADR-009: Mono-repo folder per concern
- ADR-010: Observability stack (logs, metrics)

---

## References

- [claude-flow CLI Documentation](https://github.com/rodaquinoDev/claude-flow)
- [RuVector HNSW Implementation](https://github.com/rodaquinoDev/ruvector)
- [Byzantine Consensus Primer](https://en.wikipedia.org/wiki/Byzantine_fault)
- [Swarm Execution Strategy](./docs/Technical%20specification/SWARM_EXECUTION_STRATEGY.md)

---

**Next Steps:**
1. Team training on claude-flow CLI (scheduled 2026-02-10)
2. Execute Phase 0 of swarm strategy (memory preparation)
3. Pilot swarm execution on revenue cycle domain
4. Measure cost savings and quality metrics
5. Iterate and scale to all domains
