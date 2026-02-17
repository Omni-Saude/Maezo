
# 📋 Plan Mode Analysis: discharge_planning_worker.py

## Executive Summary

The discharge_planning_worker.py contains **significant workflow logic, decision rules, and orchestration concerns that violate separation of concerns principles**. The worker has evolved into a "God Worker" that mixes:

1. **Orchestration logic** (workflow sequencing) that belongs in BPMN
2. **Business rules** (readiness scoring, barrier identification) that belong in DMN
3. **Integration concerns** (FHIR fetching, TASY integration) that are appropriate for workers

---

## 🔴 Critical Findings

### 1. **Embedded Workflow Logic (Should Be BPMN)**

| Location | Code Pattern | Issue | Recommended BPMN Element |
|----------|--------------|-------|--------------------------|
| Lines 230-295 | Sequential execution: fetch encounter → build checklist → assess readiness → check meds → check education → check transport → build follow-up → identify barriers | **Process orchestration embedded in Python** | Call Activities / Service Tasks with explicit sequence flows |
| Lines 263-278 | Conditional logic for TASY readmission risk → append checklist item | **Gateway decision embedded in code** | Exclusive Gateway + Business Rule Task |
| Lines 292-295 | `estimated_discharge_date` calculation with conditional logic | **Business process decision** | DMN + intermediate message events |

**The worker executes a complete sub-process internally instead of relying on BPMN orchestration.**

### 2. **Business Rules in Code (Should Be DMN)**

| Method | Lines | Rule Type | Recommended DMN Table |
|--------|-------|-----------|----------------------|
| `_assess_discharge_readiness()` | 393-413 | Scoring thresholds: 90% = ready, 70% = conditional | `discharge_readiness_score.dmn` |
| `_identify_barriers_to_discharge()` | 448-467 | Barrier enumeration rules | `discharge_barriers.dmn` |
| `_estimate_discharge_date()` | 486-493 | Date estimation logic | `discharge_date_estimation.dmn` |
| `_check_transport_arrangements()` | 435-441 | Transport requirement rules per destination | `transport_requirements.dmn` |
| `_build_discharge_checklist()` | 354-384 | Standard checklist items definition | `discharge_checklist_items.dmn` |

**These are classic decision table patterns that should be tenant-overridable per ADR-007.**

### 3. **Missing BPMN Subprocess**

The current architecture has:
- clinical-ops-main.bpmn → throws `msg_discharge_completed` message
- SP-PA-012_Post_Discharge_Followup.bpmn → catches discharge message for follow-up

**Missing:** A `SP-CO-008_Discharge_Planning.bpmn` that:
- Receives discharge planning trigger
- Orchestrates checklist validation, readiness assessment, barrier resolution
- Coordinates with care team, pharmacy, transport
- Sends discharge completed message

---

## 📊 Hierarchy & Composition Analysis

### Super-Set / Sub-Set Relationships

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     BPMN ORCHESTRATION LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  clinical-ops-main.bpmn                                                     │
│    └─► [MISSING] SP-CO-008_Discharge_Planning.bpmn (Call Activity)         │
│           ├─► ServiceTask: clinical.discharge_checklist_build              │
│           ├─► BusinessRuleTask: DMN discharge_readiness_score              │
│           ├─► BusinessRuleTask: DMN discharge_barriers                      │
│           ├─► ServiceTask: clinical.medications_reconciliation              │
│           ├─► ServiceTask: clinical.patient_education                       │
│           ├─► ServiceTask: clinical.transport_arrangement                   │
│           ├─► Exclusive Gateway: All criteria met?                          │
│           │     ├─► Yes: ServiceTask: clinical.discharge_summary            │
│           │     └─► No: Loop back / Escalation                              │
│           └─► Message Throw: msg_discharge_completed                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DMN DECISION LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  discharge_readiness_score.dmn                                              │
│    ├── Input: completedItems, totalItems, criticalItemsPending              │
│    └── Output: readinessStatus (ready|conditional|not_ready), score         │
│                                                                             │
│  discharge_barriers.dmn                                                     │
│    ├── Input: medicationsReconciled, educationComplete, transportNeeded,   │
│    │          checklistPendingItems[]                                        │
│    └── Output: barriers[], severity, requiredActions[]                      │
│                                                                             │
│  discharge_checklist_items.dmn (tenant-overridable per ADR-007)             │
│    ├── Input: encounterType, admissionCategory, specialtyCode              │
│    └── Output: requiredChecklistItems[], optionalItems[]                    │
│                                                                             │
│  transport_requirements.dmn                                                 │
│    ├── Input: dischargeDestination, patientMobility, distance              │
│    └── Output: transportRequired, transportType, escortRequired             │
│                                                                             │
│  discharge_date_estimation.dmn                                              │
│    ├── Input: readinessScore, pendingBarriers[], targetDate                │
│    └── Output: estimatedDate, confidence, delayReasons[]                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WORKER IMPLEMENTATION LAYER                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  discharge_checklist_build_worker.py                                        │
│    └── Pure integration: FHIR queries, checklist status fetching            │
│                                                                             │
│  medications_reconciliation_worker.py                                       │
│    └── Pure integration: FHIR MedicationStatement queries                   │
│                                                                             │
│  patient_education_worker.py                                                │
│    └── Pure integration: FHIR Procedure/DocumentReference queries           │
│                                                                             │
│  transport_arrangement_worker.py                                            │
│    └── Pure integration: FHIR Task queries, transport system calls          │
│                                                                             │
│  discharge_summary_worker.py                                                │
│    └── Pure integration: Generate FHIR DocumentReference, notify systems    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Current vs. Ideal Responsibility Matrix

| Concern | Current Location | Ideal Location | Issue |
|---------|------------------|----------------|-------|
| "What checklist items are required?" | `_build_discharge_checklist()` hardcoded list | `discharge_checklist_items.dmn` | Not tenant-configurable |
| "What does readiness score mean?" | `_assess_discharge_readiness()` thresholds | `discharge_readiness_score.dmn` | Thresholds are business rules |
| "What barriers exist?" | `_identify_barriers_to_discharge()` | `discharge_barriers.dmn` | Rule enumeration is DMN |
| "When will patient discharge?" | `_estimate_discharge_date()` | `discharge_date_estimation.dmn` | Estimation logic is a rule |
| "Is transport needed?" | `_check_transport_arrangements()` | `transport_requirements.dmn` | Conditional logic is DMN |
| "Execute FHIR read operations" | `_fetch_encounter()`, `_fetch_patient()` | Worker (correct) | ✅ Appropriate |
| "Call TASY API" | TASY integration code | Worker (correct) | ✅ Appropriate |

---

## 🔄 Overlaps & Conflicts Detected

### 1. **Overlap with doctor_discharge_readiness_worker.py**

| Worker | Topic | Function |
|--------|-------|----------|
| discharge_planning_worker.py | `clinical.discharge_planning` | Assesses readiness, builds checklist |
| doctor_discharge_readiness_worker.py | `inpatient.discharge_ready` | Notifies doctor when criteria met |

**Conflict:** Both workers calculate/assess discharge readiness independently. The `doctor_discharge_readiness_worker` assumes criteria are already evaluated externally, but `discharge_planning_worker` embeds this logic internally.

**Resolution:** 
- BPMN should orchestrate: checklist worker → DMN readiness assessment → conditional gateway → notify doctor worker
- Neither worker should contain readiness assessment logic

### 2. **Overlap with SP-PA-012_Post_Discharge_Followup.bpmn**

The BPMN subprocess `SP-PA-012` starts with `Message_DischargeInitiated` but assumes discharge planning is complete. There is no explicit BPMN process for the discharge planning workflow itself.

### 3. **Missing Message Correlation**

clinical-ops-main.bpmn throws `msg_discharge_completed` (line 265) but there's no intermediate discharge planning orchestration that:
- Validates readiness before emitting the message
- Handles barriers and loops back for resolution
- Coordinates parallel tasks (meds reconciliation, education, transport)

---

## 🏗️ Recommended Architecture Refactoring

### Phase 1: Extract DMN Tables

Create the following DMN tables in `healthcare_platform/clinical_operations/dmn/discharge/`:

1. **`discharge_checklist_items.dmn`** - Hit Policy: COLLECT
   - Define standard and specialty-specific checklist items
   - Allow tenant overrides per ADR-007

2. **`discharge_readiness_assessment.dmn`** - Hit Policy: FIRST
   - Scoring thresholds and readiness determination
   - Business-analyst maintainable

3. **`discharge_barriers_identification.dmn`** - Hit Policy: COLLECT
   - Barrier detection rules
   - Severity classification

4. **`discharge_transport_requirements.dmn`** - Hit Policy: FIRST
   - Transport requirement determination
   - Escort requirements

5. **`discharge_date_estimation.dmn`** - Hit Policy: FIRST
   - Estimated date calculation
   - Confidence scoring

### Phase 2: Create Missing BPMN Subprocess

Create `SP-CO-008_Discharge_Planning.bpmn`:

```xml
<!-- Pseudo-structure -->
Process: SP_CO_008_Discharge_Planning
├── Start: Discharge Planning Initiated
├── ServiceTask: Build Discharge Checklist (clinical.discharge_checklist_build)
├── BusinessRuleTask: Evaluate Checklist Items (DMN: discharge_checklist_items)
├── Parallel Gateway: Fork Validation Tasks
│   ├── ServiceTask: Check Medications Reconciliation
│   ├── ServiceTask: Check Patient Education
│   └── ServiceTask: Check Transport Arrangements
├── Parallel Gateway: Join
├── BusinessRuleTask: Assess Readiness (DMN: discharge_readiness_assessment)
├── BusinessRuleTask: Identify Barriers (DMN: discharge_barriers_identification)
├── Exclusive Gateway: Readiness Status?
│   ├── [ready]: ServiceTask: Generate Discharge Summary
│   ├── [conditional]: UserTask: Review Conditional Items
│   └── [not_ready]: Timer Event → Loop to Checklist Build
├── BusinessRuleTask: Estimate Discharge Date (DMN: discharge_date_estimation)
├── ServiceTask: Notify Doctor (inpatient.discharge_ready)
├── Message Throw: msg_discharge_completed
└── End: Discharge Planning Complete
```

### Phase 3: Refactor Worker to Pure Integration

The discharge_planning_worker.py should become:

```python
class DischargeChecklistBuildWorker:
    """Pure FHIR integration - fetches checklist item statuses"""
    TOPIC = "clinical.discharge_checklist_build"
    
    async def execute(self, task_variables):
        # Only FHIR queries - no business logic
        # Return raw data for DMN evaluation
```

---

## 📈 Impact Assessment

| Metric | Current State | After Refactoring |
|--------|---------------|-------------------|
| Business rule visibility | Hidden in Python | Visible in DMN Studio |
| Tenant customization | Requires code changes | DMN override per ADR-007 |
| Process visibility | Black-box worker | Full BPMN auditability |
| Testing | Unit tests in Python | DMN test harness + process tests |
| Business analyst autonomy | None | Full DMN editing capability |
| Compliance auditing | Log analysis | Process instance history |

---

## ✅ Recommended Next Steps

1. **Create DMN directory**: `healthcare_platform/clinical_operations/dmn/discharge/`
2. **Implement DMN tables** in priority order: readiness → barriers → checklist → transport → estimation
3. **Create BPMN subprocess**: `SP-CO-008_Discharge_Planning.bpmn`
4. **Update clinical-ops-main.bpmn**: Add Call Activity before `msg_discharge_completed`
5. **Refactor worker**: Split into smaller, integration-only workers
6. **Remove doctor_discharge_readiness_worker.py overlap**: Consolidate notification into BPMN flow
7. **Add tenant override tests** per ADR-007 governance

---

**Severity Assessment:** 🔴 **High** - Current architecture violates separation of concerns, reduces business analyst autonomy, and creates untraceable business logic in code. 

Completed (4/5) *Analyze hierarchy/composition*

## Summary

Your discharge_planning_worker.py has **significant architectural issues**:

### 🔴 What's Wrong

1. **Workflow Logic in Worker**: The `execute()` method orchestrates 10+ sequential steps that should be separate BPMN tasks with explicit sequence flows, gateways, and error handling.

2. **Business Rules in Code**: Methods like `_assess_discharge_readiness()` (90%/70% thresholds), `_identify_barriers_to_discharge()`, and `_estimate_discharge_date()` contain decision logic that should be DMN tables — making them invisible to business analysts and impossible to override per-tenant (violating ADR-007).

3. **Missing BPMN Subprocess**: There's no `SP-CO-008_Discharge_Planning.bpmn`. The main orchestrator jumps from clinical compliance directly to throwing `msg_discharge_completed` without a proper discharge planning sub-process.

4. **Overlap with doctor_discharge_readiness_worker.py**: Two workers independently assess discharge readiness, creating potential inconsistencies.

### ✅ Best-in-Class Target

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **BPMN** | Orchestration, sequencing, gateways, events | `SP-CO-008_Discharge_Planning.bpmn` |
| **DMN** | Business rules, thresholds, scoring, barriers | `dmn/discharge/*.dmn` |
| **Worker** | Pure integration (FHIR/TASY API calls only) | Minimal `_worker.py` files |

The worker should shrink to **pure integration duties** (FHIR reads, TASY calls), while all orchestration moves to BPMN and all decision logic moves to DMN tables that business analysts can maintain and tenants can override.

# 🎯 Plan Mode: Systematic Refactoring of 100+ Workers

## Deep Analysis & Strategic Framework

---

## 1. Is This a Classical Problem of Process Design/Automation?

**Yes, absolutely.** This is a well-documented anti-pattern in BPM literature with several established names:

### 1.1 The "Smart Endpoint, Dumb Pipe" Inversion

Your architecture exhibits the **inverse** of the recommended microservices pattern. Instead of:
- **Dumb endpoints** (workers doing pure integration)
- **Smart orchestration** (BPMN controlling flow)

You have:
- **Smart endpoints** (workers containing workflow + rules + integration)
- **Dumb orchestration** (BPMN reduced to task dispatch)

### 1.2 Known Anti-Patterns Present

| Anti-Pattern | Description | Evidence in Your Codebase |
|--------------|-------------|---------------------------|
| **"God Service"** | Single component doing too many things | discharge_planning_worker.py with 10+ internal steps |
| **"Embedded Workflow"** | Procedural code mimicking process flow | Sequential method calls in `execute()` |
| **"Hardcoded Rules"** | Business rules in code instead of rule engine | Threshold values, scoring formulas in Python |
| **"Shadow Process"** | Actual process diverges from documented process | BPMN shows simple task, worker executes complex sub-process |
| **"Copy-Paste Rules"** | Same rule implemented multiple times | Likely across 100+ workers |
| **"Orchestration Drift"** | Multiple sources of truth for flow control | BPMN + Python workers both making routing decisions |

### 1.3 Root Cause Analysis

This typically happens through organic growth:

```
Year 1: Simple worker → fetch data → return result
Year 2: "Add this validation" → if/else in worker
Year 3: "Add this scoring" → formula in worker  
Year 4: "Add conditional logic" → match/case in worker
Year 5: Worker is now a 500-line orchestrator with embedded rules
```

**The BPMN becomes a "menu" of capabilities rather than the actual process definition.**

---

## 2. Literature & Best Practices Parallels

### 2.1 Academic & Industry Frameworks

| Source | Concept | Application to Your Case |
|--------|---------|--------------------------|
| **Camunda Best Practices** | "External Tasks should be stateless and focused" | Workers should do ONE thing |
| **DMN Specification (OMG)** | "Decisions should be externalized from process logic" | All `if/elif/else` on business data → DMN |
| **Workflow Patterns (van der Aalst)** | "Separation of control flow from task implementation" | BPMN owns sequencing, workers own integration |
| **Domain-Driven Design** | "Ubiquitous Language in model" | BPMN/DMN readable by business analysts |
| **Clean Architecture (Martin)** | "Dependencies point inward" | Workers depend on domain, not vice versa |
| **TOGAF** | "Separation of concerns across architecture layers" | Orchestration ≠ Rules ≠ Integration |

### 2.2 The "Three-Layer Cake" Pattern

From BPM literature, the ideal architecture is:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER (BPMN)                   │
│  • Process flow, gateways, events, timers, error handling      │
│  • Human-readable, auditable, version-controlled               │
│  • Business analysts can modify without code changes           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION LAYER (DMN)                         │
│  • Business rules, scoring, classification, routing logic      │
│  • Tenant-overridable, testable in isolation                   │
│  • Business analysts can modify without code changes           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    INTEGRATION LAYER (Workers)                  │
│  • Pure I/O: API calls, database queries, file operations      │
│  • Stateless, horizontally scalable                            │
│  • Developers maintain, business logic-free                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Relevant Literature References

1. **"Fundamentals of Business Process Management"** (Dumas, La Rosa, Mendling, Reijers)
   - Chapter on "Process Implementation" discusses this exact separation

2. **"Real-Life BPMN"** (Freund, Rücker)
   - Camunda-specific patterns for external task workers

3. **"Decision Model and Notation (DMN): The Real-Life Guide"** (Debevoise, Taylor)
   - When to use DMN vs. code for decisions

4. **"Process Mining: Data Science in Action"** (van der Aalst)
   - Detecting "shadow processes" through conformance checking

---

## 3. Expected Challenges in Fixing This

### 3.1 Discovery Challenges

| Challenge | Description | Risk Level |
|-----------|-------------|------------|
| **Rule Duplication Detection** | Same rule in multiple workers with slight variations | 🔴 High |
| **Semantic Equivalence** | Two rules doing "same thing" but written differently | 🔴 High |
| **Conflict Detection** | Same input, different output across workers | 🔴 Critical |
| **Coverage Gaps** | Rules in workers not covered by any DMN | 🟡 Medium |
| **Orphan DMN** | DMN tables that exist but aren't used | 🟡 Medium |
| **Version Drift** | DMN updated but worker still has old logic | 🔴 High |

### 3.2 Decomposition Challenges

| Challenge | Description | Risk Level |
|-----------|-------------|------------|
| **Granularity Decisions** | How small should each worker be? | 🟡 Medium |
| **Transaction Boundaries** | Where does one "unit of work" end? | 🔴 High |
| **State Management** | Workers currently share state via instance variables | 🟡 Medium |
| **Error Handling Migration** | Try/except in workers → BPMN error events | 🔴 High |
| **Testing Strategy Shift** | Unit tests → Process tests + DMN tests | 🟡 Medium |

### 3.3 Organizational Challenges

| Challenge | Description | Risk Level |
|-----------|-------------|------------|
| **Team Skillset** | Developers comfortable with Python, less with BPMN/DMN | 🟡 Medium |
| **Ownership Boundaries** | Who owns BPMN? Who owns DMN? Who owns workers? | 🔴 High |
| **Business Analyst Involvement** | They need to validate extracted rules | 🟡 Medium |
| **Regression Risk** | Behavior changes during refactoring | 🔴 Critical |
| **Parallel Development** | Can't freeze 100+ workers during refactoring | 🔴 High |
| **Documentation Debt** | Current behavior undocumented, only in code | 🟡 Medium |

### 3.4 Technical Debt Compound Interest

```
Each worker refactored = N hours
N workers = 100+
But: Each refactoring may discover conflicts with previously refactored workers
This creates O(N²) discovery complexity, not O(N)
```

---

## 4. Reflection on Multiple Possibilities

### 4.1 Approach A: "Big Bang" Refactoring

**Description:** Stop all feature development, systematically refactor all workers.

| Pros | Cons |
|------|------|
| Clean, consistent result | Business stops for months |
| No parallel version maintenance | High regression risk |
| Team focused on one goal | Team burnout |

**Verdict:** ❌ Not viable for a production healthcare system

### 4.2 Approach B: "Strangler Fig" Pattern

**Description:** New features use correct architecture; gradually migrate old workers.

| Pros | Cons |
|------|------|
| Business continues | Two architectures coexist for years |
| Risk spread over time | Cognitive load on team |
| Learn as you go | Inconsistent developer experience |

**Verdict:** ✅ Viable, but needs governance

### 4.3 Approach C: "Discovery First" (Recommended Foundation)

**Description:** Before any refactoring, build a complete inventory of what exists.

```
Phase 1: Automated Discovery
├── Static analysis of all workers
├── Extract all business rules (if/elif/else, thresholds, formulas)
├── Map worker → BPMN topic → process location
├── Identify rule clusters (similar rules across workers)
└── Generate conflict/overlap report

Phase 2: Rationalization
├── Business analyst review of discovered rules
├── Canonical rule definition (one source of truth)
├── DMN table design with tenant override structure
├── BPMN subprocess design
└── Migration priority matrix

Phase 3: Incremental Migration
├── Highest-value/highest-risk workers first
├── Feature-flag controlled rollout
├── A/B testing old vs. new behavior
└── Gradual traffic shift
```

**Verdict:** ✅ This is the mature approach

### 4.4 Approach D: "Domain-Driven Decomposition"

**Description:** Group workers by bounded context, refactor one domain at a time.

```
Domains in your codebase:
├── clinical_operations/     → Refactor as unit
├── revenue_cycle/          → Refactor as unit
├── patient_access/         → Refactor as unit
└── platform_services/      → Refactor as unit
```

| Pros | Cons |
|------|------|
| Natural boundaries | Cross-domain rules exist |
| Team ownership clear | Some domains larger than others |
| Incremental delivery | Dependencies between domains |

**Verdict:** ✅ Combine with Approach C for best results

### 4.5 Approach E: "Test-Driven Extraction"

**Description:** For each worker, first write comprehensive tests capturing current behavior, then refactor.

```python
# Before refactoring
def test_discharge_readiness_90_percent():
    """Current behavior: 90%+ completed = ready"""
    result = worker._assess_discharge_readiness(checklist_90_percent)
    assert result == ("ready", 0.9)

# This test becomes the contract for the DMN table
# DMN must produce same output for same input
```

| Pros | Cons |
|------|------|
| Regression safety | Testing effort upfront |
| Behavior documentation | Some behaviors may be bugs |
| Refactoring confidence | Slow start |

**Verdict:** ✅ Essential companion to any approach

---

## 5. What I Would Ask/Be Concerned About in Your Position

### 5.1 Strategic Questions

1. **What is the business driver for this refactoring?**
   - Regulatory compliance? (LGPD, ANS audits)
   - Operational efficiency? (Business analysts blocked by developers)
   - Technical debt? (Slowing down feature delivery)
   - Multi-tenant scaling? (New hospital units need different rules)
   
   *The answer shapes priority and timeline.*

2. **What is the tolerance for behavioral changes?**
   - Must behavior be 100% identical post-refactoring?
   - Are there known bugs that should be fixed during migration?
   - Are there known rules that business wants to change?

3. **Who owns the extracted DMN tables?**
   - Business analysts with developer review?
   - Developers with business analyst validation?
   - Shared ownership with formal governance?

4. **What is the release strategy for refactored components?**
   - Shadow mode (new runs parallel, results compared)?
   - Canary release (percentage of traffic)?
   - Blue/green deployment?

### 5.2 Technical Concerns

5. **How do we handle rules that span multiple workers?**
   ```
   Worker A: if patient.age > 65 → high_risk
   Worker B: if patient.age >= 65 → needs_escort
   Worker C: if patient.age > 60 → extended_followup
   ```
   *These are related but different. Do we unify or keep separate?*

6. **How do we handle conditional DMN invocation?**
   - Some rules only apply for certain encounter types
   - DMN filtering vs. BPMN conditional routing?

7. **What about performance?**
   - Current: One worker call, all logic internal
   - Future: Multiple external task cycles + DMN evaluations
   - Is latency increase acceptable?

8. **What about observability?**
   - Current: Logs inside worker show all steps
   - Future: Process instance history shows orchestration, but DMN evaluation details?

### 5.3 Organizational Concerns

9. **Do we have business analyst capacity?**
   - Extracting 100+ workers means reviewing hundreds of rules
   - Who validates that extracted rules match business intent?

10. **How do we prevent regression to old patterns?**
    - New developers join, see 50 "old style" workers, copy that pattern
    - Need architectural guardrails (linting, PR reviews, templates)

11. **What about the workers currently in development?**
    - Features in progress are adding more technical debt
    - Freeze new worker development until patterns are established?

### 5.4 Risk Concerns

12. **What if extracted rules reveal business logic conflicts?**
    - Worker A says "X", Worker B says "not X" for same input
    - Discovery is valuable but creates uncomfortable conversations

13. **What about rules that are "wrong but relied upon"?**
    - A threshold is incorrect, but downstream processes expect it
    - Fixing the rule breaks dependent systems

14. **What about undocumented tenant-specific behavior?**
    - Some workers may have `if tenant == "hospital-a"` hidden in code
    - Need to surface these as explicit DMN overrides

---

## 6. Proposed Maturation Path

### 6.1 Immediate Actions (This Week)

| Action | Owner | Deliverable |
|--------|-------|-------------|
| Confirm business driver and priority | Stakeholders | Written mandate |
| Identify pilot domain (smallest bounded context) | Tech Lead | Domain selection |
| Establish governance model for DMN ownership | Product + Tech | RACI matrix |

### 6.2 Discovery Phase (2-4 Weeks)

| Action | Owner | Deliverable |
|--------|-------|-------------|
| Build automated rule extraction tool | Dev Team | Python AST analyzer |
| Generate worker inventory | Dev Team | CSV/JSON with all workers, topics, methods |
| Extract rule fingerprints | Dev Team | Clustered rules by similarity |
| Generate conflict report | Dev Team | Rules with same input, different output |
| Map existing DMN coverage | Dev Team | DMN ↔ Worker matrix |

### 6.3 Design Phase (2-4 Weeks)

| Action | Owner | Deliverable |
|--------|-------|-------------|
| Canonical rule design workshops | BA + Dev | Rule catalog |
| DMN table structure decisions | Architect | DMN design patterns doc |
| BPMN subprocess patterns | Architect | BPMN templates |
| Worker template (thin integration) | Dev Team | Reference implementation |
| Testing strategy | QA + Dev | Test framework for DMN + BPMN |

### 6.4 Pilot Phase (4-6 Weeks)

| Action | Owner | Deliverable |
|--------|-------|-------------|
| Refactor pilot domain (e.g., `discharge_planning`) | Dev Team | New BPMN + DMN + thin workers |
| A/B testing in production | DevOps | Comparison metrics |
| Retrospective and pattern refinement | Team | Updated patterns doc |

### 6.5 Scaled Rollout (Ongoing)

| Action | Owner | Deliverable |
|--------|-------|-------------|
| Prioritized backlog of remaining workers | Product | Ranked list |
| Sprint-by-sprint migration | Dev Team | Incremental delivery |
| Architectural guardrails (linting, templates) | Platform Team | CI/CD checks |
| Training for new team members | Tech Lead | Onboarding materials |

---

## 7. Consensus Checkpoint Questions

Before proceeding to any implementation, I suggest we reach consensus on:

1. **Scope Confirmation**
   - Are we refactoring ALL 100+ workers, or prioritizing high-value/high-risk?
   
2. **Timeline Expectations**
   - Is this a 3-month initiative or a 12-month journey?
   
3. **Behavioral Fidelity**
   - Must extracted rules produce 100% identical output, or is "semantically equivalent" acceptable?
   
4. **Discovery Tool Investment**
   - Should we build automated rule extraction, or manually analyze each worker?
   
5. **Governance Model**
   - Who has final say on canonical rule definitions?
   
6. **Parallel Development Policy**
   - What happens to workers being developed RIGHT NOW?

---

## 8. Summary Position

This is a **classic, well-documented problem** in BPM implementations. The good news:

- ✅ Patterns and solutions exist in literature
- ✅ Your existing BPMN/DMN infrastructure supports the correct architecture
- ✅ ADR-007 already anticipates tenant-specific rule needs
- ✅ The problem is organizational/architectural, not fundamental

The risk:

- ⚠️ O(N²) complexity in discovery due to rule interactions
- ⚠️ Organizational change management required
- ⚠️ Regression risk during migration

**My recommendation:** Invest heavily in **Discovery Phase** before any refactoring. The automated rule extraction and conflict detection will pay for itself many times over by preventing mid-migration surprises.


---

# CTO DECISIONS (2026-02-11)

## Status: APPROVED FOR EXECUTION

The following decisions are binding and close all open questions above.

---

## 9. Strategic Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Business Driver** | Technical debt + Multi-tenant scaling | Feature velocity blocked; new hospitals need different rules |
| **Behavioral Tolerance** | 5% intentional changes, 0% regression | Pre-production allows adjustments |
| **Domain Priority** | clinical_operations → revenue_cycle → patient_access → platform_services | Clinical is most complex, proves pattern |
| **DMN Ownership** | Developers with BA validation post-Phase 4 | Fast iteration, BA reviews final artifacts |
| **Conditional DMN Pattern** | Pattern A (BPMN-controlled routing) | Clean architecture; Pattern C hybrid only for latency > 200ms |
| **Cross-Worker Rules** | Unified via Byzantine consensus | Agents vote, majority wins, dissent logged |
| **Latency Budget** | 200ms async, 50ms critical path | Sepsis/cardiac stay as-is; billing/discharge refactored |
| **Release Strategy** | Shadow Mode + Assertion Testing | v1 and v2 run parallel, outputs compared |
| **Rollback Strategy** | Git branch per domain | Merge to main only after Phase 4 passes |
| **Automation** | claude-flow swarm (non-negotiable per ADR-013) | Byzantine consensus for design decisions |

---

## 10. Consensus Protocol

All design and unification decisions during migration are made by agents, not humans.

| Decision Type | Consensus Mode | Threshold | Fallback |
|---------------|----------------|-----------|----------|
| Rule unification (same domain) | Byzantine | 2/3 majority | Log + proceed with majority |
| Rule unification (cross-domain) | Unanimous | 100% | Defer to Phase 5 human review |
| DMN table design | Byzantine | 2/3 majority | Majority design wins |
| BPMN subprocess design | Byzantine | 2/3 majority | Majority design wins |
| Latency exemption | Unanimous | 100% | If any disagrees, refactor anyway |
| Behavioral change classification | Byzantine | 2/3 majority | Bug fix vs intentional vs regression |

---

## 11. Execution Pipeline

### Phase 0: Preparation

- Create git branch per domain
- Initialize claude-flow hive-mind
- Index codebase in RuVector
- Store scope in memory

### Phase 0.5: Pre-Discovery Triage (NEW)

- Vector-based classification using smell patterns
- Classify workers: HIGH / MEDIUM / LOW / EXEMPT priority
- Reduces Phase 1 analysis time by 60-70%

### Phase 1: Discovery (2-3 days)

- 10 agents, hierarchical-mesh topology
- Extract rules, map coverage, identify conflicts
- Focus on HIGH/MEDIUM priority workers first

### Phase 2: Consensus (1-2 days)

- 8 agents, Byzantine consensus
- Resolve conflicts, design canonical DMN/BPMN
- Identify latency exemptions

### Phase 3: Generation (3-5 days)

- 12 agents, hierarchical-mesh topology
- Create DMN files, BPMN files, thin workers, tests

### Phase 4: Validation (2-3 days)

- 8 agents, Byzantine consensus
- Execute tests, confirm parity, generate report

---

## 12. Timeline

| Domain | Start | Duration | End |
|--------|-------|----------|-----|
| clinical_operations | Feb 11 | 10 days | Feb 21 |
| revenue_cycle | Feb 22 | 8 days | Mar 2 |
| patient_access | Mar 3 | 6 days | Mar 9 |
| platform_services | Mar 10 | 5 days | Mar 15 |
| BA Review & Merge | Mar 16 | 3 days | Mar 19 |

**Total: 5.5 weeks**

---

## 13. Success Metrics

| Metric | Target |
|--------|--------|
| Workers refactored | 90%+ of non-critical |
| Behavioral parity | 100% (minus intentional changes) |
| DMN tables created | 1 per rule cluster |
| BPMN subprocesses created | 1 per orchestrating worker |
| Latency increase | < 200ms async, < 50ms critical |
| Conflicts resolved | 100% |

---

## 14. Memory Keys (claude-flow)

All state stored in claude-flow memory per ADR-013:

| Key | Purpose |
|-----|---------|
| `refactoring/strategy-document` | Strategy document reference |
| `refactoring/agent-handoff` | Agent handoff document reference |
| `refactoring/phase-0.5-triage` | Triage phase configuration |
| `triage/smell-patterns` | 7 anti-pattern definitions for vector search |
| `refactoring/scope` | Project scope and parameters |

---

## 15. Related Documents

- **Strategy Document:** `docs/Agents handoffs/WORKER_REFACTORING_STRATEGY_2026-02-11.md`
- **Agent Handoff:** `docs/Agents handoffs/AGENT_HANDOFF_REFACTOR_WORKERS_2026-02-11.md`
- **ADR-003:** Python External Task Workers
- **ADR-007:** DMN Federation with Tenant Overrides
- **ADR-013:** Claude-flow Swarm Intelligence

---

## 16. Approval

**Status:** ✅ APPROVED  
**Date:** 2026-02-11  
**Authority:** CTO Decision  
**Execution:** Immediate (Phase 0 preparation)

---

*Last updated: 2026-02-11*
