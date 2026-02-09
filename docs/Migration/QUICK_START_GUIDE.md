# CIB7 Worker Migration - Quick Start Guide

**🚀 START HERE** - Your 15-minute guide to migrating your first worker

---

## 📁 What You Have Now

```
docs/Technical specification/
├── CIB7_WORKER_TEMPLATE.md                    ← Generic template (copy this)
├── EXAMPLE_MIGRATION_validate_eligibility_worker.py  ← Real example (study this)
├── MIGRATION_COMPARISON_Camunda8_to_CIB7.md  ← Reference guide (use this)
└── MIGRATION_SUMMARY.md                       ← Overview (read this first)

Legacy processes/workers/camunda8-implementation/
└── (185 Camunda8 workers ready to migrate)
```

---

## ⚡ Quick Start: Migrate Your First Worker in 15 Minutes

### Step 1: Pick a Simple Worker (2 minutes)

Start with a simple worker to learn the patterns:

**Recommended First Worker:**
- `create_alert_worker.py` (simple, minimal dependencies)

**Alternative:**
- `send_message_worker.py` (straightforward logic)

**Avoid for First Migration:**
- Complex workers with many dependencies
- Workers with heavy business logic
- Workers requiring external API integration

---

### Step 2: Copy the Template (1 minute)

```bash
# Create your worker file from template
cp "docs/Technical specification/CIB7_WORKER_TEMPLATE.md" \
   "workers/revenue-cycle/my_first_worker.py"

# Open in editor
code "workers/revenue-cycle/my_first_worker.py"
```

---

### Step 3: Find the Original Worker (1 minute)

```bash
# Find the Camunda8 worker
find "Legacy processes/workers/camunda8-implementation" \
     -name "create_alert_worker.py"

# Open side-by-side with template
code --reuse-window \
     "Legacy processes/workers/camunda8-implementation/clinical/alerts/create_alert_worker.py"
```

---

### Step 4: Apply the Migration Pattern (8 minutes)

Open the comparison guide:
```bash
code "docs/Technical specification/MIGRATION_COMPARISON_Camunda8_to_CIB7.md"
```

#### 4.1 Update Imports

**Before (Camunda8):**
```python
from pyzeebe import worker, WorkerResult, BpmnErrorException
```

**After (CIB7):**
```python
from camunda.external_task.external_task import ExternalTask, TaskResult
from camunda.external_task.external_task_worker import ExternalTaskWorker
```

#### 4.2 Update Class Definition

**Before (Camunda8):**
```python
@worker(topic="create-alert", lock_duration=30000)
class CreateAlertWorker(BaseWorker):
    async def process_task(self, job, variables) -> WorkerResult:
        # ...
```

**After (CIB7):**
```python
class CreateAlertWorker:
    async def execute(self, task: ExternalTask) -> TaskResult:
        # ...
```

#### 4.3 Update Variable Access

**Before (Camunda8):**
```python
patient_id = variables.get("patientId")
alert_type = variables.get("alertType")
```

**After (CIB7):**
```python
patient_id = task.get_variable("patientId")
alert_type = task.get_variable("alertType")
```

#### 4.4 Update Task Completion

**Before (Camunda8):**
```python
return WorkerResult.ok({"alertId": alert_id, "status": "created"})
```

**After (CIB7):**
```python
return task.complete({"alertId": alert_id, "status": "created"})
```

#### 4.5 Add Worker Registration

**Add at end of file:**
```python
def register_worker(worker_client: ExternalTaskWorker) -> None:
    """Register worker with CIB7 client."""
    worker = CreateAlertWorker()
    
    worker_client.subscribe(
        topic="create-alert",
        action=worker.execute,
        lock_duration=30000,
        variables=["patientId", "alertType", "tenantId"],
    )
```

---

### Step 5: Test Locally (3 minutes)

```bash
# Install dependencies (if not done)
pip install camunda-external-task-client-python3 pydantic structlog

# Run worker standalone
cd workers/revenue-cycle
python my_first_worker.py

# Should see:
# Worker started: create-alert-local
# CIB7 REST API: http://localhost:8080/engine-rest
# Topic: create-alert
# Press Ctrl+C to stop.
```

---

## 📋 Migration Checklist

Use this checklist for every worker:

```markdown
- [ ] Copied template or opened existing Camunda8 worker
- [ ] Updated imports (pyzeebe → camunda.external_task)
- [ ] Removed @worker decorator
- [ ] Changed process_task() → execute()
- [ ] Updated parameter: (job, variables) → (task)
- [ ] Changed variable access: variables.get() → task.get_variable()
- [ ] Updated task completion: WorkerResult.ok() → task.complete()
- [ ] Updated BPMN errors: raise → return task.bpmn_error()
- [ ] Updated failures: raise → return task.failure()
- [ ] Added register_worker() function
- [ ] Added worker_client.subscribe() call
- [ ] Updated tests (mock ExternalTask)
- [ ] Tested locally with CIB7 instance
- [ ] Code review passed
- [ ] Documentation updated
```

---

## 🎯 Common Patterns - Quick Reference

### Pattern: Get Variables

```python
# Single variable
patient_id = task.get_variable("patientId")

# With default
procedure_codes = task.get_variable("procedureCodes", default=[])

# All variables
all_vars = task.get_variables()
```

### Pattern: Complete Task

```python
return task.complete({
    "resultStatus": "SUCCESS",
    "alertId": alert_id,
    "createdAt": datetime.now().isoformat(),
})
```

### Pattern: BPMN Error (Business Error)

```python
# Coverage expired - process should handle this
return task.bpmn_error(
    error_code="COVERAGE_EXPIRED",
    error_message="Patient insurance expired",
    variables={"expirationDate": "2025-12-31"}
)
```

### Pattern: Task Failure (Retry)

```python
# API unavailable - retry 3 times
return task.failure(
    error_message="Insurance API unavailable",
    error_details={"status_code": 503},
    max_retries=3,
    retry_timeout=5000,  # 5 seconds
)
```

### Pattern: Multi-Tenancy

```python
# Get tenant context
tenant_id = task.get_variable("tenantId")

if tenant_id:
    self.tenant_context.set_current_tenant(tenant_id)
    
try:
    # Business logic with tenant context
    db = self.tenant_context.get_database(tenant_id)
    credentials = self.tenant_context.get_credentials("api", tenant_id)
finally:
    if tenant_id:
        self.tenant_context.clear_current_tenant()
```

---

## 🔥 Most Common Mistakes

### Mistake 1: Forgetting to Return TaskResult

**❌ Wrong:**
```python
async def execute(self, task: ExternalTask):
    result = {"status": "success"}
    task.complete(result)  # No return!
```

**✅ Correct:**
```python
async def execute(self, task: ExternalTask) -> TaskResult:
    result = {"status": "success"}
    return task.complete(result)  # Must return!
```

---

### Mistake 2: Using Wrong Variable Access

**❌ Wrong:**
```python
patient_id = task.variables["patientId"]  # AttributeError!
```

**✅ Correct:**
```python
patient_id = task.get_variable("patientId")
```

---

### Mistake 3: Raising Instead of Returning BPMN Error

**❌ Wrong:**
```python
raise BpmnErrorException(error_code="EXPIRED", message="...")
# Error won't be caught by CIB7!
```

**✅ Correct:**
```python
return task.bpmn_error(error_code="EXPIRED", error_message="...")
```

---

### Mistake 4: Not Specifying max_retries

**❌ Wrong:**
```python
return task.failure(error_message="API failed")
# Will retry indefinitely!
```

**✅ Correct:**
```python
return task.failure(
    error_message="API failed",
    max_retries=3,  # Retry up to 3 times
    retry_timeout=5000,
)
```

---

## 📞 When You Get Stuck

### Problem: Worker Not Processing Tasks

**Check:**
1. Is CIB7 running? `curl http://localhost:8080/engine-rest/version`
2. Is worker registered? Check `worker_client.subscribe()` call
3. Does topic name match BPMN? Check BPMN task `<camunda:topic>`

### Problem: Variables Not Found

**Check:**
1. Variable name matches BPMN (case-sensitive!)
2. Variable is being set by previous task
3. Using `task.get_variable()` not `task.variables`

### Problem: BPMN Error Not Caught

**Check:**
1. Error code matches BPMN error event
2. Using `return task.bpmn_error()` not `raise`
3. Error boundary event attached to task in BPMN

---

## 🎓 Learning Resources

### Read in This Order

1. **MIGRATION_SUMMARY.md** (5 min)
   - Overview of what's been done
   - Migration strategy
   - Success criteria

2. **EXAMPLE_MIGRATION_validate_eligibility_worker.py** (15 min)
   - Complete real-world example
   - Study the patterns used
   - See how business logic is preserved

3. **CIB7_WORKER_TEMPLATE.md** (20 min)
   - Complete template structure
   - All patterns documented
   - Testing strategies

4. **MIGRATION_COMPARISON_Camunda8_to_CIB7.md** (30 min)
   - Side-by-side comparisons
   - Detailed pattern explanations
   - Migration checklist

**Total Time:** ~70 minutes to master CIB7 migration

---

## 🚀 Next Steps After First Worker

### After Successfully Migrating One Worker:

1. **Migrate 2-3 similar workers** using the same pattern
2. **Create internal template** for your team (customize from CIB7_WORKER_TEMPLATE.md)
3. **Document team-specific patterns** (your APIs, your databases)
4. **Train other team members** (pair programming)
5. **Set up CI/CD** for automated testing

### Scale Up Migration:

**Week 1:** 5 billing workers
**Week 2:** 10 denials workers  
**Week 3:** 10 coding workers
**Week 4:** 15 clinical workers
**Week 5-6:** Remaining 144 workers

**Target:** 2-3 workers per person per day (after learning curve)

---

## ✅ Completion Criteria

Your worker is ready for production when:

1. ✅ Code compiles without errors
2. ✅ Worker registers with CIB7
3. ✅ Worker processes test tasks successfully
4. ✅ All tests pass (unit + integration)
5. ✅ Logging shows tenant context
6. ✅ BPMN errors trigger boundary events
7. ✅ Failures retry correctly
8. ✅ Variables pass to next task
9. ✅ Code review approved
10. ✅ Documentation updated

---

## 💡 Pro Tips

### Tip 1: Start Simple
Don't try to optimize or refactor during migration. First make it work, then make it better.

### Tip 2: Use AI Assistant
Your claude-flow system is trained on your codebase. Ask questions like:
- "Generate CIB7 worker for creating alerts"
- "Review this migration for completeness"
- "What's wrong with this BPMN error?"

### Tip 3: Test with Stubs
Use stub implementations for external services (like StubInsuranceAPIClient in example).

### Tip 4: Migrate in Groups
Group similar workers together:
- All billing workers
- All coding workers
- All denials workers

### Tip 5: Keep Original Code
Don't delete Camunda8 workers until CIB7 workers are production-proven (keep in `Legacy processes/`).

---

## 🎉 You're Ready!

You now have everything needed to migrate your workers:

- ✅ Complete template
- ✅ Real-world example
- ✅ Comprehensive comparison guide
- ✅ Quick-start checklist
- ✅ Common mistakes guide

**Time to migrate your first worker!** 🚀

Start with `create_alert_worker.py` and follow this guide. You'll be done in 15 minutes!

---

**Need Help?**
- Review: `MIGRATION_COMPARISON_Camunda8_to_CIB7.md`
- Example: `EXAMPLE_MIGRATION_validate_eligibility_worker.py`
- Ask AI: Your claude-flow system knows all patterns

**Good luck!** 🎯
