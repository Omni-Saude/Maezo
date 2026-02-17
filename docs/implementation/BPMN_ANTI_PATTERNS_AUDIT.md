# BPMN Anti-Patterns Audit Report

**Date**: 2026-02-14  
**Auditor**: Claude Agent  
**Engine**: CIB Seven 2.1.3 (Camunda 7 compatible)  

---

## 🚨 CRITICAL ANTI-PATTERNS DISCOVERED

### Anti-Pattern #1: Wrong Namespace (Zeebe/Camunda 8)

**Problem:**
```xml
<!-- WRONG - This is Camunda 8/Zeebe namespace -->
xmlns:camunda="http://camunda.org/schema/zeebe/1.0"
```

**Correct:**
```xml
<!-- CORRECT - This is Camunda 7 namespace -->
xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
```

**Impact:** Camunda Modeler shows `ns0 namespace` errors. Process WILL NOT deploy to CIB7 engine.

**Files Affected (11):**
- `platform_services/bpmn/integration_analytics.bpmn`
- `platform_services/bpmn/revenue_optimization.bpmn`
- `revenue_cycle/bpmn/SP-RC-002_Pre_Service.bpmn`
- `revenue_cycle/bpmn/SP-RC-003_Clinical_Service.bpmn`
- `revenue_cycle/bpmn/SP-RC-004_Clinical_Production.bpmn`
- `revenue_cycle/bpmn/SP-RC-005_Coding_Audit.bpmn`
- `revenue_cycle/bpmn/SP-RC-006_Billing_Submission.bpmn`
- `revenue_cycle/bpmn/SP-RC-007_Denial_Management.bpmn`
- `revenue_cycle/bpmn/SP-RC-008_Revenue_Collection.bpmn`
- `revenue_cycle/bpmn/SP-RC-009_Analytics_Intelligence.bpmn`
- `revenue_cycle/bpmn/SP-RC-010_Maximization.bpmn`

---

### Anti-Pattern #2: Nested Extension Elements

**Problem:**
```xml
<!-- WRONG - Nested <camunda:topic> inside extensionElements -->
<bpmn:serviceTask id="task_verify" name="Verify">
  <bpmn:extensionElements>
    <camunda:topic>verify-insurance</camunda:topic>
    <camunda:inputOutput>
      <camunda:inputParameter name="patientId">${patientId}</camunda:inputParameter>
    </camunda:inputOutput>
  </bpmn:extensionElements>
</bpmn:serviceTask>
```

**Correct:**
```xml
<!-- CORRECT - Attributes on service task element -->
<bpmn:serviceTask id="task_verify" name="Verify"
                  camunda:type="external" 
                  camunda:topic="revenue.verify_insurance">
  <bpmn:incoming>flow_in</bpmn:incoming>
  <bpmn:outgoing>flow_out</bpmn:outgoing>
</bpmn:serviceTask>
```

**Impact:** Parser doesn't recognize `<camunda:topic>` as valid extension. External task workers won't receive tasks.

**Files Affected (13):**
- `clinical_operations/bpmn/SP-CO-001_Adverse_Event_Detection.bpmn`
- `platform_services/bpmn/integration_analytics.bpmn`
- `platform_services/bpmn/revenue_optimization.bpmn`
- `revenue_cycle/bpmn/SP-RC-002_Pre_Service.bpmn` through `SP-RC-010_Maximization.bpmn`

---

### Anti-Pattern #3: FEEL Expression Syntax

**Problem:**
```xml
<!-- WRONG - FEEL syntax (Camunda 8) -->
<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">=eligibilityStatus = true</bpmn:conditionExpression>
```

**Correct:**
```xml
<!-- CORRECT - JUEL syntax (Camunda 7) -->
<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">${eligibilityStatus == true}</bpmn:conditionExpression>
```

**Impact:** Expression evaluation fails at runtime. Gateway always takes default path.

**Files Affected (9):**
- All SP-RC-002 through SP-RC-010 files

---

### Anti-Pattern #4: Orphan Flow References

**Problem:**
```xml
<!-- Reference to non-existent flow -->
<bpmn:incoming>flow_retry_after_escalation</bpmn:incoming>
```

**Impact:** Camunda Modeler shows "unresolved reference" warning. May cause deployment validation failures.

---

## 📊 AUDIT SUMMARY

| Category | Files Affected | Severity |
|----------|---------------|----------|
| Wrong Namespace | 11 | 🔴 CRITICAL |
| Nested Extensions | 13 | 🔴 CRITICAL |
| FEEL Expressions | 9 | 🟠 HIGH |
| Orphan References | Unknown | 🟡 MEDIUM |

### Files Status

| File | Namespace | Extensions | Expressions | Status |
|------|-----------|------------|-------------|--------|
| SP-RC-001 | ✅ Fixed | ✅ Fixed | ✅ Fixed | ✅ CLEAN |
| SP-RC-002 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-003 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-004 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-005 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-006 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-007 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-008 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-009 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| SP-RC-010 | ❌ Zeebe | ❌ Nested | ❌ FEEL | 🔴 NEEDS FIX |
| integration_analytics | ❌ Zeebe | ❌ Nested | ✅ OK | 🟠 PARTIAL |
| revenue_optimization | ❌ Zeebe | ❌ Nested | ✅ OK | 🟠 PARTIAL |
| SP-CO-001 | ✅ OK | ❌ Nested | ✅ OK | 🟠 PARTIAL |

### Files with CORRECT Patterns (21 files)
Files in `clinical_operations/bpmn/` (except SP-CO-001) use correct patterns and can be used as reference.

---

## 🔧 FIX PROCEDURE

### Step 1: Fix Namespace
```bash
# Find and replace zeebe namespace
sed -i '' 's|camunda.org/schema/zeebe/1.0|camunda.org/schema/1.0/bpmn|g' file.bpmn
```

### Step 2: Fix Extension Elements
Transform nested elements to attributes:
```xml
<!-- FROM -->
<bpmn:serviceTask id="X" name="Y">
  <bpmn:extensionElements>
    <camunda:topic>my-topic</camunda:topic>
  </bpmn:extensionElements>
</bpmn:serviceTask>

<!-- TO -->
<bpmn:serviceTask id="X" name="Y"
                  camunda:type="external" camunda:topic="domain.my_topic">
</bpmn:serviceTask>
```

### Step 3: Fix Expressions
```xml
<!-- FROM (FEEL) -->
<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">=var = value</bpmn:conditionExpression>

<!-- TO (JUEL) -->
<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">${var == value}</bpmn:conditionExpression>
```

### Step 4: Validate
```bash
xmllint --noout file.bpmn
# Open in Camunda Modeler - no ns0 errors
```

---

## 📝 TOPIC NAMING CONVENTION

Follow the established pattern from clean files:

| Domain | Topic Pattern | Example |
|--------|---------------|---------|
| Revenue Cycle | `revenue.{action}` | `revenue.verify_insurance` |
| Clinical Operations | `clinical.{action}` | `clinical.vital_signs` |
| Patient Access | `patient.{action}` | `patient.register` |
| Platform Services | `platform.{action}` | `platform.notify_supervisor` |

---

## 🎯 PRIORITY FOR REMEDIATION

1. **IMMEDIATE**: SP-RC-002 through SP-RC-010 (revenue cycle - production processes)
2. **HIGH**: integration_analytics.bpmn, revenue_optimization.bpmn
3. **MEDIUM**: SP-CO-001 (only needs extension format fix)

**Estimated Effort**: 2-3 hours for all 13 files

---

## ✅ VALIDATION CHECKLIST

Before committing any BPMN file, verify:

- [ ] Namespace is `http://camunda.org/schema/1.0/bpmn`
- [ ] Service tasks use `camunda:type="external" camunda:topic="..."` as attributes
- [ ] User tasks use `camunda:formKey="..."` as attribute
- [ ] Expressions use JUEL syntax `${...}` not FEEL `=...`
- [ ] All sequence flow references exist
- [ ] File validates with `xmllint --noout`
- [ ] Opens in Camunda Modeler without namespace errors

---

## 📚 REFERENCE: Good vs Bad Examples

### Good (from SP-CA-001_Sepsis_Detection.bpmn):
```xml
<bpmn:serviceTask id="Task_CollectVitals" name="Collect Vital Signs"
                  camunda:type="external" camunda:topic="clinical.vital_signs">
  <bpmn:incoming>Flow_ToCollectVitals</bpmn:incoming>
  <bpmn:outgoing>Flow_ToQSOFA</bpmn:outgoing>
</bpmn:serviceTask>
```

### Bad (from SP-RC-002_Pre_Service.bpmn before fix):
```xml
<bpmn:serviceTask id="task_verify" name="Verificar">
  <bpmn:extensionElements>
    <camunda:topic>verify-insurance</camunda:topic>
  </bpmn:extensionElements>
</bpmn:serviceTask>
```

---

*This audit was generated after discovering anti-patterns in SP-RC-001 during BPMNDI pilot phase.*
