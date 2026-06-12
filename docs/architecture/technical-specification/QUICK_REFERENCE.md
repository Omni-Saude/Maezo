# 🚀 Claude-flow Quick Reference Card

**ADR-013 Best Practices** | **Version:** 1.0 | **Date:** 2026-02-09

---

## ⚡ Quick Commands

### Initialize Hive-Mind

```bash
npx @claude-flow/cli@latest hive-mind init \
  --topology hierarchical-mesh \
  --max-agents 15 \
  --consensus byzantine
```

### Pre-Task Hook

```bash
npx @claude-flow/cli@latest hooks pre-task \
  --description "Generate revenue cycle workers" \
  --task-id "rc-workers-001" \
  --namespace healthcare-platform
```

### Spawn Intelligent Swarm

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 10 \
  --role specialist \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --objective "[detailed task description]"
```

### Store in Memory (Not Markdown!)

```bash
npx @claude-flow/cli@latest memory store \
  --key "progress-[phase]" \
  --value "[status update]" \
  --namespace healthcare-platform
```

### Search Memory

```bash
npx @claude-flow/cli@latest memory search \
  --query "[topic]" \
  --namespace healthcare-platform
```

### Train Neural Model

```bash
npx @claude-flow/cli@latest neural train \
  --modelType moe \
  --data-source "platform/workers/[domain]" \
  --epochs 10 \
  --namespace healthcare-platform
```

### Post-Task Hook

```bash
npx @claude-flow/cli@latest hooks post-task \
  --task-id "rc-workers-001" \
  --status success \
  --output "Generated 89 workers, 0 errors"
```

---

## ✅ DO's

| Practice | Command | Why |
|---|---|---|
| Use memory for state | `memory store/search` | No file clutter |
| Pre-task hooks | `hooks pre-task` | Audit trail |
| Post-task hooks | `hooks post-task` | Track outcomes |
| Train on generated code | `neural train` | Learn patterns |
| Intelligent routing | `--model-routing intelligent` | 40-60% cost savings |
| Byzantine consensus | `--consensus byzantine` | Fault tolerance |
| Semantic search | `vector search` | Find knowledge fast |
| Extract patterns | `learn --extract-patterns` | Reusable knowledge |

---

## ❌ DON'Ts

| Anti-Pattern | Why Wrong | Alternative |
|---|---|---|
| Create `PROGRESS.md` | Clutters repo | `memory store --key "progress-X"` |
| Create `STATUS.md` | Not searchable | `memory search --query "status"` |
| Create `TODO.md` | Not versioned | `memory store --key "tasks-remaining"` |
| Single model for all | Wastes money | `--model-routing intelligent` |
| Skip pre-task hooks | No audit trail | Always use `hooks pre-task` |
| Skip neural training | Miss learning | Train after generation |
| Serial execution | Slow (8-12x) | Parallel swarms |

---

## 🎯 Workflow Template

```bash
# 1. Initialize (once per session)
npx @claude-flow/cli@latest hive-mind init \
  --topology hierarchical-mesh \
  --max-agents 15 \
  --consensus byzantine

# 2. Pre-task
npx @claude-flow/cli@latest hooks pre-task \
  --description "[what you're doing]" \
  --task-id "[unique-id]" \
  --namespace healthcare-platform

# 3. Execute with swarm
npx @claude-flow/cli@latest hive-mind spawn \
  --workers [N] \
  --claude \
  --model-routing intelligent \
  --objective "[detailed requirements]"

# 4. Train neural model on output
npx @claude-flow/cli@latest neural train \
  --modelType moe \
  --data-source "[output-path]" \
  --epochs 10 \
  --namespace healthcare-platform

# 5. Store learned patterns
npx @claude-flow/cli@latest memory store \
  --key "pattern-[name]" \
  --value "[what worked]" \
  --namespace patterns

# 6. Post-task
npx @claude-flow/cli@latest hooks post-task \
  --task-id "[unique-id]" \
  --status success \
  --output "[results summary]"
```

---

## 🔍 Debugging

### Check Daemon Status

```bash
npx @claude-flow/cli@latest hive-mind status
```

### List Memory Entries

```bash
npx @claude-flow/cli@latest memory list \
  --namespace healthcare-platform
```

### View Neural Models

```bash
npx @claude-flow/cli@latest neural list
```

### Check Vector Index

```bash
npx @claude-flow/cli@latest vector status
```

### View Task History

```bash
npx @claude-flow/cli@latest hooks list \
  --namespace healthcare-platform
```

---

## 📊 Model Routing Guide

| Task Complexity | Model | When to Use |
|---|---|---|
| Simple | claude-3-haiku | File operations, formatting, simple edits |
| Balanced | claude-3-5-sonnet | Standard workers, documentation, tests |
| Complex | claude-3-7-sonnet | Architecture, complex logic, design |
| **Auto** | `--model-routing intelligent` | Let claude-flow decide (recommended) |

---

## 🏗️ Topology Guide

| Topology | Structure | Best For | Max Agents |
|---|---|---|---|
| `hierarchical` | Coordinator → Workers | Simple tasks | 50 |
| `mesh` | Peer-to-peer | Collaborative tasks | 20 |
| `hierarchical-mesh` | Hybrid (recommended) | Complex projects | 100+ |

---

## 🛡️ Consensus Guide

| Type | Fault Tolerance | Speed | Best For |
|---|---|---|---|
| `raft` | 50% majority | Fast | Stable environments |
| `paxos` | 50% majority | Medium | Standard use |
| `byzantine` | 33% faulty nodes | Slower | Production (recommended) |

---

## 💰 Cost Optimization

### Before (No Optimization)

- All tasks use claude-3-7-sonnet
- Cost: $X per 1M tokens
- Example: 500k LOC generation = ~$2,000

### After (Intelligent Routing)

- Simple → haiku, Balanced → 3.5-sonnet, Complex → 3.7-sonnet
- Cost: 40-60% reduction
- Example: 500k LOC generation = ~$800-$1,200

**Savings:** $800-$1,200 per generation cycle

---

## 🎓 Learning Resources

| Resource | Link |
|---|---|
| ADR-013 Full Document | `docs/adr/013-claude-flow-swarm-intelligence.md` |
| Swarm Strategy | `docs/architecture/technical-specification/SWARM_EXECUTION_STRATEGY.md` |
| Claude-flow Docs | https://github.com/rodaquinoDev/claude-flow |
| RuVector Docs | https://github.com/rodaquinoDev/ruvector |

---

## 🆘 Common Issues

### Issue: "Required option missing: --query"

**Problem:** Memory search syntax error

**Solution:**
```bash
# Wrong:
npx @claude-flow/cli@latest memory search "topic" --namespace healthcare

# Correct:
npx @claude-flow/cli@latest memory search \
  --query "topic" \
  --namespace healthcare
```

### Issue: Swarm agents fail silently

**Problem:** Byzantine consensus requires 3+ agents

**Solution:**
```bash
# Wrong: Only 2 workers (can't achieve consensus)
--workers 2 --consensus byzantine

# Correct: At least 3 workers
--workers 3 --consensus byzantine
```

### Issue: Out of memory during generation

**Problem:** Too many parallel agents

**Solution:**
```bash
# Reduce parallel workers
--workers 5  # instead of 15
```

---

## 📋 Checklist Before Execution

- [ ] Claude-flow CLI >= 3.1.0 installed
- [ ] Hive-mind daemon initialized (`hive-mind init`)
- [ ] Memory namespace created (`healthcare-platform`)
- [ ] Technical specs loaded into memory
- [ ] ADRs indexed in RuVector
- [ ] Neural models trained on legacy code (optional)
- [ ] Pre-task hook executed
- [ ] Sufficient disk space (10GB+)
- [ ] Sufficient RAM (32GB+ for large swarms)
- [ ] API budget confirmed

---

**Remember:** Memory-first, no markdown status files, always use hooks, train on output!

**Quick Check:** `npx @claude-flow/cli@latest --version` (should be >= 3.1.0)
