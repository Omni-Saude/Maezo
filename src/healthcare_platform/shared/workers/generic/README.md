# Generic Worker Framework

## 1. Overview and Rationale

The generic worker framework eliminates the anti-pattern of creating one Python class per BPMN service task. Before this framework, 223 orphan topics (BPMN tasks with no corresponding worker) would have required approximately 17,840 lines of repetitive boilerplate code.

**Zero-code philosophy:** Adding a new topic requires only a YAML entry in `config/topic_registry.yaml`. No Python code is written or modified. The framework reads the registry at startup, selects the correct archetype class, and executes the full DMN evaluation pipeline.

**Key problems solved:**
- 97 existing workers shared 7 structural patterns with no formal contracts
- Inconsistent error handling (some blocked on failure, others silently passed)
- No standard for chaining multiple DMN tables in sequence
- New developers had no canonical pattern to follow

## 2. Architecture

### Inheritance Chain

```
BaseExternalTaskWorker          (healthcare_platform/shared/workers/base.py)
        │
        └── GenericWorkerBase   (base_generic.py)
                │               - Registry loading
                │               - Input/output mapping
                │               - DMN pipeline execution
                │               - Merge strategy application
                │               - Error strategy dispatch
                │
                ├── GenericAdminAdjudicationWorker   (admin_adjudication.py)
                ├── GenericClinicalAlertWorker        (clinical_alert.py)
                ├── GenericClinicalScoreWorker        (clinical_score.py)
                ├── GenericOperationalRoutingWorker   (operational_routing.py)
                ├── GenericComplianceValidationWorker (compliance_validation.py)
                ├── GenericFinancialCalculationWorker (financial_calculation.py)
                └── GenericDataEnrichmentWorker       (data_enrichment.py)
```

### FederatedDMNService Integration

All DMN evaluation routes through `FederatedDMNService` (ADR-007). The service provides:
- 11 domain DMN path mappings (`revenue_cycle`, `clinical_operations`, `governance`, etc.)
- Tenant-specific decision table override resolution
- Result caching across pipeline stages
- Federation across DMN domains

The `dmn_category` field in the registry entry maps directly to the `FederatedDMNService` category parameter.

### Template-Method Pipeline Pattern

`GenericWorkerBase.execute()` drives a fixed lifecycle:

```python
def execute(self, context: TaskContext) -> TaskResult:
    variables = self._map_inputs(context)      # 1. Rename context keys per input_map
    decisions = self._build_decisions()         # 2. Resolve dmn_pipeline / dmn_key / decisions
    dmn_results = self._execute_dmn_pipeline(context, decisions)  # 3. Call DMN(s) in sequence
    raw_result = self._merge_results(dmn_results, decisions)      # 4. Merge per merge_strategy
    output = self._map_outputs(raw_result, context)               # 5. Rename output keys
    # 6. Check resultado and return TaskResult.success or TaskResult.bpmn_error
```

Archetype subclasses may override `execute()` to add archetype-specific validation while still calling the helper methods above.

### Registry Loading

`registry_loader.load_registry()` reads `config/topic_registry.yaml` at startup, validates every entry, and returns a `Dict[str, Dict]` keyed by topic name. `get_topic_config(topic)` provides cached single-topic lookup.

## 3. Seven Archetypes

| Archetype | Class | Purpose | Default Error Strategy | Error Behavior |
|---|---|---|---|---|
| `ADMIN_ADJUDICATION` | `GenericAdminAdjudicationWorker` | Authorization, eligibility, claims adjudication | `fail_closed` | BLOQUEAR — surfaces as BPMN error boundary; blocks process |
| `CLINICAL_ALERT` | `GenericClinicalAlertWorker` | Sepsis detection, drug interaction, critical threshold escalation | `fail_safe` | REVISAR — logs warning, returns sentinel; process continues |
| `CLINICAL_SCORE` | `GenericClinicalScoreWorker` | Risk scores, SOFA/qSOFA, comorbidity indices | `fail_safe` | REVISAR — returns default score; process continues with flag |
| `OPERATIONAL_ROUTING` | `GenericOperationalRoutingWorker` | Triage, bed allocation, staff assignment | `fail_closed` | BLOQUEAR — escalates to supervisor; no routing on error |
| `COMPLIANCE_VALIDATION` | `GenericComplianceValidationWorker` | LGPD audit trail, ANS compliance, documentation integrity | `fail_closed` | BLOQUEAR — escalates to compliance officer on error |
| `FINANCIAL_CALCULATION` | `GenericFinancialCalculationWorker` | Pricing, denial analysis, TISS generation, revenue impact | `fail_closed` | BLOQUEAR — prevents incorrect billing; escalates |
| `DATA_ENRICHMENT` | `GenericDataEnrichmentWorker` | FHIR normalization, demographic enrichment, data quality | `fail_safe` | REVISAR — preserves existing data if enrichment fails |

**Error strategy logic:**
- `fail_closed` (BLOQUEAR): Re-raises or converts to `TaskResult.bpmn_error` with `error_code="DMN_ERROR_BLOCKED"`. Triggers Camunda error boundary event. Used when proceeding without a valid decision is unsafe.
- `fail_safe` (REVISAR): Logs a warning and returns `TaskResult.success` with `{"resultado": "REVISAR", "acao": "Revisão manual necessária"}`. Process continues; item queued for async human review.

**Note on `ADMIN_ADJUDICATION`:** The constructor enforces `fail_closed` by default — if `error_strategy` is not present in `registry_config`, it is injected before `super().__init__()` is called. It also validates that DMN output always contains an explicit `action`; if absent, defaults to `REVISAR` to prevent silent approvals.

## 4. Registry Schema Reference

Location: `config/topic_registry.yaml`

```yaml
topics:
  <topic.name>:           # dot.snake_case — matches Camunda External Task topic
    # --- Required fields ---
    archetype: ADMIN_ADJUDICATION   # One of 7 valid values (see table above)
    dmn_category: revenue_cycle     # FederatedDMNService category

    # --- DMN source (exactly one of the following) ---
    dmn_key: DMN-RC-001             # Single DMN decision table ID
    # OR
    dmn_pipeline:                   # Ordered list of DMN calls
      - key: DMN-RC-001
        category: eligibility_rules # Overrides dmn_category for this step
        merge_strategy: worst_case  # How to merge this step's output
      - key: DMN-RC-004
        category: tiss_validation
        merge_strategy: worst_case

    # --- Optional fields ---
    input_map:                      # Rename context variables before DMN evaluation
      contextKey: dmn_input_name    # context "contextKey" becomes DMN input "dmn_input_name"

    output_map:                     # Rename DMN outputs before writing to process variables
      dmn_output_name: process_var  # DMN "dmn_output_name" becomes process variable "process_var"

    error_strategy: fail_closed     # 'fail_closed' (BLOQUEAR) or 'fail_safe' (REVISAR)
                                    # Defaults to archetype default if omitted

    timeout_ms: 15000               # Camunda task lock duration in ms (default: 300000)

    merge_strategy: override        # Global merge strategy for single-DMN topics
                                    # Per-step merge_strategy in dmn_pipeline overrides this

    description: >                  # Human-readable description (not used at runtime)
      Validates claim across eligibility and TISS rules.
```

**Required fields summary:**
- `archetype` — must be one of the 7 valid values
- `dmn_category` — must be a valid `FederatedDMNService` category
- At least one of: `dmn_key`, `dmn_pipeline`, or `decisions` (legacy)

**Validation rules enforced by `registry_loader._validate_entry()`:**
- `archetype` not in `_VALID_ARCHETYPES` → `RegistryValidationError`
- No DMN source defined → `RegistryValidationError`
- `dmn_category` absent → `RegistryValidationError`
- `error_strategy` not in `{'fail_closed', 'fail_safe'}` → `RegistryValidationError`
- `dmn_pipeline` stage missing `key` or `dmn_key` → `RegistryValidationError`
- `timeout_ms` not a positive integer → `RegistryValidationError`

## 5. Pipeline Pattern Guide

Use `dmn_pipeline` when a topic requires sequential evaluation across multiple DMN tables where each stage may depend on the output of the previous one.

### How the pipeline executes

Each stage's output is merged into `running_vars` before the next stage runs:

```python
running_vars = dict(context.variables)
for decision_config in decisions:
    stage_inputs = {**running_vars, **decision_config.get("inputs", {})}
    result = evaluate_dmn(decision_key, stage_inputs, category)
    running_vars.update(result)   # Stage output feeds next stage's input
```

This means stage 2 receives the original context variables plus everything stage 1 returned.

### Four Merge Strategies

| Strategy | Behavior | `resultado`/`action` handling | Use when |
|---|---|---|---|
| `worst_case` | Most restrictive action wins | Keeps BLOQUEAR > REVISAR > PROSSEGUIR | Clinical safety, compliance — any failure should block |
| `best_case` | Least restrictive action wins | Keeps PROSSEGUIR > REVISAR > BLOQUEAR | Eligibility — any approval is sufficient |
| `append` | All values collected into lists | Action values appended to list | Collecting multiple recommendations or flags |
| `override` | Last result wins for every key | Last stage's action replaces earlier ones | Simple sequential enrichment |

`ACTION_PRIORITY` constants govern `worst_case`/`best_case` comparisons:

```python
ACTION_PRIORITY = {
    "BLOQUEAR":   3,   # Most restrictive
    "REVISAR":    2,
    "PROSSEGUIR": 1,   # Least restrictive
}
```

For `worst_case`: if new priority > accumulated priority, new value wins.
For `best_case`: if new priority < accumulated priority, new value wins.
Non-action fields always use `override` semantics regardless of strategy.

### Example pipeline entry

```yaml
billing.validate_claim:
  archetype: ADMIN_ADJUDICATION
  dmn_pipeline:
    - key: DMN-RC-001
      category: eligibility_rules
      merge_strategy: worst_case    # BLOQUEAR on eligibility failure propagates forward
    - key: DMN-RC-004
      category: tiss_validation
      merge_strategy: worst_case    # BLOQUEAR on TISS failure overrides PROSSEGUIR from stage 1
    - key: DMN-RC-005
      category: coding_optimization
      merge_strategy: best_case     # PROSSEGUIR on coding optimization keeps approval
  dmn_category: revenue_cycle
  error_strategy: fail_closed
```

Per-step `merge_strategy` overrides the global `merge_strategy` field. When no `merge_strategy` is specified at any level, `override` is the default.

## 6. Adding New Topics (Zero-Code Workflow)

No Python code is required. The entire workflow is:

**Step 1: Add the entry to `config/topic_registry.yaml`**

```yaml
topics:
  # ... existing entries ...

  surgical.equipment_check:
    archetype: COMPLIANCE_VALIDATION
    dmn_key: DMN-CO-007
    dmn_category: clinical_operations
    input_map:
      equipmentId: equipment_id
      procedureCode: procedure_code
      sterileStatus: sterilization_status
    output_map:
      complianceResult: equipment_status
      recommendedAction: action
    error_strategy: fail_closed
    timeout_ms: 5000
    description: >
      Validates surgical equipment sterility and readiness for procedure.
```

**Step 2: Register the topic in your BPMN process**

In Camunda Modeler, set the service task implementation to External Task with topic `surgical.equipment_check`. No worker class name is referenced.

**Step 3: Verify**

```bash
# Confirm registry loads without validation errors
python -c "from healthcare_platform.shared.workers.generic import load_registry; r = load_registry(); print(list(r.keys()))"

# Run the integration test suite to confirm topic connectivity
pytest tests/integration/bpmn/ -k "surgical"
```

That is the complete workflow. The framework's registry loader discovers the new topic, instantiates `GenericComplianceValidationWorker` with the config dict, and handles execution.

### Topic naming convention

Topics must follow `domain.action_name` format (dot.snake_case per ADR-019):

```
billing.validate_claim          # correct
emergency.triage_status         # correct
clinical.drug_interaction_check # correct
billing-validate-claim          # WRONG — kebab case rejected by integration tests
BillingValidateClaim            # WRONG — PascalCase rejected
```

## 7. Migration Guide

To convert an existing hardcoded worker to a registry entry:

**Before — typical hardcoded worker (~80 lines):**

```python
class DrugInteractionCheckWorker(BaseExternalTaskWorker):
    TOPIC = "clinical.drug_interaction_check"

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            inputs = {
                "patient_id": context.variables["patientFhirId"],
                "active_meds_list": context.variables["currentMedications"],
                "new_drug_code": context.variables["proposedMedication"],
            }
            result = self.evaluate_dmn(
                context,
                decision_key="DMN-CA-003",
                variables=inputs,
                category="clinical_operations",
            )
            return TaskResult.success({
                "severity_level": result["interactionLevel"],
                "action": result["recommendedAction"],
            })
        except Exception as e:
            self.logger.warning("Drug check failed: %s", e)
            return TaskResult.success({"resultado": "REVISAR"})
```

**After — registry entry (15 lines of YAML):**

```yaml
clinical.drug_interaction_check:
  archetype: CLINICAL_ALERT
  dmn_key: DMN-CA-003
  dmn_category: clinical_operations
  input_map:
    patientFhirId: patient_id
    currentMedications: active_meds_list
    proposedMedication: new_drug_code
  output_map:
    interactionLevel: severity_level
    recommendedAction: action
  error_strategy: fail_safe
```

**Migration steps:**

1. Identify the existing worker's `TOPIC`, `decision_key`, and `category` values.
2. Determine the archetype from the table in section 3 (match on error strategy and purpose).
3. Extract `input_map` by comparing `context.variables` key names to DMN input parameter names.
4. Extract `output_map` by comparing DMN output field names to the variables written to `TaskResult`.
5. Add the YAML entry to `config/topic_registry.yaml`.
6. Delete the Python worker class file.
7. Remove the worker's import from any worker registration module.
8. Run existing tests — they should pass against the generic worker.

**Handling archetype-specific behavior:** If the existing worker has custom logic beyond input mapping and DMN evaluation (e.g., external API calls, database writes), it cannot be migrated to the generic framework. Keep it as a concrete subclass of `BaseExternalTaskWorker`.

## 8. Testing Guide

### Test structure

Tests live in `tests/unit/workers/generic/`. Each archetype has a dedicated test module:

```
tests/unit/workers/generic/
    conftest.py                          # Shared fixtures
    test_base_generic.py                 # GenericWorkerBase, merge strategies, error handling
    test_registry_loader.py              # load_registry, validation errors
    test_pipeline_patterns.py            # All 4 merge strategies, multi-stage pipelines
    test_admin_adjudication_worker.py    # fail_closed enforcement, _validate_admin_result
    test_clinical_alert_worker.py        # fail_safe behavior, REVISAR sentinel
    test_clinical_score_worker.py        # Score calculation patterns
    test_operational_routing_worker.py   # Routing patterns
    test_compliance_validation_worker.py # LGPD / compliance patterns
    test_financial_calculation_worker.py # Financial calculation patterns
    test_data_enrichment_worker.py       # Enrichment patterns
```

### Shared fixtures (conftest.py)

```python
# TaskContext with realistic variables
@pytest.fixture
def mock_context():
    return TaskContext(
        task_id="task-001",
        process_instance_id="proc-999",
        tenant_id="hospital-a",
        variables={"claimId": "CLM-123", "payerId": "payer-001", "amount": 1500.00},
        worker_id="billing.validate_claim",
        retries=3,
    )

# FederatedDMNService mock returning a default PROSSEGUIR result
@pytest.fixture
def mock_dmn_service():
    service = MagicMock()
    service.evaluate.return_value = {"action": "PROSSEGUIR", "reason": "OK"}
    return service
```

### Writing tests for a new archetype

Use `unittest.mock.patch.object` on `evaluate_dmn` to avoid real DMN calls:

```python
from unittest.mock import MagicMock, patch
from healthcare_platform.shared.workers.generic.compliance_validation import GenericComplianceValidationWorker
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


def _make_worker(registry_config):
    return GenericComplianceValidationWorker(
        topic="compliance.validate_audit_trail",
        registry_config=registry_config,
        logger=MagicMock(),
    )


class TestComplianceValidationWorker:
    def test_fail_closed_blocks_on_dmn_error(self):
        config = {
            "archetype": "COMPLIANCE_VALIDATION",
            "decisions": [{"key": "DMN-CMP-001", "category": "governance", "inputs": {}}],
            "error_strategy": "fail_closed",
            "dmn_category": "governance",
        }
        worker = _make_worker(config)
        ctx = TaskContext(
            task_id="t-001", process_instance_id="p-001", tenant_id="hospital-a",
            variables={"processInstanceId": "p-001"}, worker_id="compliance.validate_audit_trail",
        )
        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("db timeout")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.variables["resultado"] == "BLOQUEAR"

    def test_success_path_maps_outputs(self):
        config = {
            "archetype": "COMPLIANCE_VALIDATION",
            "decisions": [{"key": "DMN-CMP-001", "category": "governance", "inputs": {}}],
            "error_strategy": "fail_closed",
            "dmn_category": "governance",
            "output_map": {"complianceStatus": "audit_status"},
        }
        worker = _make_worker(config)
        ctx = TaskContext(
            task_id="t-001", process_instance_id="p-001", tenant_id="hospital-a",
            variables={}, worker_id="compliance.validate_audit_trail",
        )
        with patch.object(worker, "evaluate_dmn", return_value={"complianceStatus": "CONFORME"}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["audit_status"] == "CONFORME"
```

### Test checklist for any archetype worker

- Default `error_strategy` matches archetype's documented default
- `fail_closed` path: DMN exception produces `TaskStatus.BPMN_ERROR` with `resultado=BLOQUEAR`
- `fail_safe` path: DMN exception produces `TaskStatus.SUCCESS` with `resultado=REVISAR`
- `input_map` correctly renames context variables
- `output_map` correctly renames DMN output fields
- Empty `decisions` list returns `BPMN_ERROR` with `NO_DECISIONS_CONFIGURED`
- Pipeline with `worst_case` merge returns most restrictive action across all stages
- Pipeline with `best_case` merge returns least restrictive action across all stages

### Running tests

```bash
# All generic worker tests
pytest tests/unit/workers/generic/ -v

# Single module
pytest tests/unit/workers/generic/test_admin_adjudication_worker.py -v

# Coverage report
pytest tests/unit/workers/generic/ --cov=healthcare_platform.shared.workers.generic --cov-report=term-missing
```

Coverage target is 95%+.
