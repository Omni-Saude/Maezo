# Legacy Revenue Cycle BPMN Deduplication Audit

**Date:** 2026-02-14
**Auditor:** Research Agent
**Scope:** READ-ONLY comparative analysis of legacy vs SP-RC BPMN files

---

## Executive Summary

| Legacy File | SP-RC File | Overlap % | Unique in Legacy | Recommendation |
|---|---|---|---|---|
| billing/bpmn/billing_submission.bpmn | SP-RC-006 | 75% | Retry subprocess with exponential backoff, ACK/NACK protocol handling, protocol tracking | **merge** - Keep retry logic from legacy |
| coding/bpmn/coding_audit.bpmn | SP-RC-005 | 85% | Parallel gateway (CID-10/Complexity paths), audit revision loop (max 3x), manual coding subprocess | **merge** - Keep parallel execution pattern |
| glosa/bpmn/glosa_management.bpmn | SP-RC-007 | 65% | Parallel analysis (impact + reason), supervisor review with 48h timer, 5-day polling loop, ANS RN 424/2017 30-day timeout | **keep** - Significantly different approach |
| production/bpmn/production_capture.bpmn | SP-RC-004 | 70% | 8-step sequential validation, ERP capture, authorization check, multi-tenant variables | **merge** - Keep validation chain |

---

## Detailed Pair Analysis

### 1. Billing Submission Comparison

**Legacy:** `billing/bpmn/billing_submission.bpmn`
**SP-RC:** `SP-RC-006_Billing_Submission.bpmn`

#### Process Structure

**Common Elements (75% overlap):**
- Group procedures by guide type
- Apply contract rules
- Calculate charges
- Generate TISS XML
- Validate TISS schema
- Submit to payer
- Handle validation errors

**Unique in Legacy:**
1. **Apply Discounts** task (line 42) - not in SP-RC-006
2. **Consolidate Charges** task (line 48) - not in SP-RC-006
3. **Track Protocol** task (line 103) - not in SP-RC-006
4. **Handle Acknowledgment** task (line 109) - ACK/NACK processing not in SP-RC-006
5. **Retry Sub-Process** (lines 147-178):
   - Embedded retry subprocess with exponential backoff (PT5M timer)
   - Gateway to check retry success vs max attempts
   - Loop back to Submit task on success
6. **Error Events:**
   - Error_CLAIM_VALIDATION_FAILED (line 236)
   - Error_TISS_SCHEMA_ERROR (line 237)
   - Error_TISS_VALIDATION_FAILED (line 238)
   - Error_CLAIM_SUBMISSION_FAILED (line 239)

**Unique in SP-RC-006:**
1. **DMN Integration** (5 decision tables):
   - `billing_quantity_validation` (line 42)
   - `billing_modifier_rules` (line 65)
   - `billing_bundle_rules` (line 74)
   - `billing_tax_calculation` (line 100)
   - `billing_opme_rules` (line 109)
2. **User Tasks:**
   - Correct validation errors (line 184)
   - Fix schema errors (line 190)
   - Manual TISS generation (line 196)
   - Escalate submission (line 202)
3. **Timer Boundary Event:**
   - 24h SLA timer on submission (line 176)

#### Analysis

The legacy file has a more robust **retry mechanism** and **acknowledgment handling**, while SP-RC-006 has better **business rule separation via DMN** and **manual intervention paths**.

**Key Difference:** Legacy treats submission as fully automated with retry, SP-RC-006 assumes manual escalation for failures.

**Recommendation:** **MERGE** - Combine retry logic from legacy with DMN rules from SP-RC-006.

---

### 2. Coding Audit Comparison

**Legacy:** `coding/bpmn/coding_audit.bpmn`
**SP-RC:** `SP-RC-005_Coding_Audit.bpmn`

#### Process Structure

**Common Elements (85% overlap):**
- Extract clinical data
- Suggest CID-10 codes
- Suggest TUSS codes
- Validate codes
- Check compatibility
- Detect fraud
- Audit coding
- Finalize coding

**Unique in Legacy:**
1. **Parallel Gateway** (lines 41-122):
   - Fork: Path A (coding) + Path B (complexity calculation)
   - Join: Consolidate before audit
   - Complexity calculation runs in parallel with coding validation
2. **Apply Coding Rules** task (line 102) - explicit rule application
3. **Audit Decision Gateway with Revision Loop** (lines 132-136):
   - "Aprovado" → proceed to fraud detection
   - "Revisão" → loop back to Suggest CID-10 (max 3 iterations)
   - Loop counter: `${loopCounter < 3}` (line 216)
4. **Manual Coding Subprocess** (line 86):
   - Called subprocess `SUB_ManualCoding`
   - Triggered by validation errors (CID-10 or TUSS invalid)
5. **Fraud Review Subprocess** (line 153):
   - Called subprocess `SUB_FraudReview`
   - Triggered by fraud boundary event

**Unique in SP-RC-006:**
1. **DMN Integration** (4 decision tables):
   - `coding_audit_compatibility` (line 61)
   - `coding_audit_duplicate` (line 85)
   - `coding_audit_frequency` (line 94)
   - `coding_audit_unbundle` (line 103)
2. **Simpler Linear Flow:**
   - No parallel gateway
   - No revision loop
   - Fraud detection → user task if high risk

#### Analysis

The legacy file has **parallel execution for efficiency** (coding + complexity calculation simultaneously) and a **quality feedback loop** (revision max 3x). SP-RC-005 is simpler but relies on DMN for audit rules.

**Key Difference:** Legacy emphasizes iterative improvement via revision loop; SP-RC-005 is one-pass with DMN rules.

**Recommendation:** **MERGE** - Keep parallel gateway and revision loop from legacy, integrate DMN rules from SP-RC-005.

---

### 3. Glosa Management Comparison

**Legacy:** `glosa/bpmn/glosa_management.bpmn`
**SP-RC:** `SP-RC-007_Denial_Management.bpmn`

#### Process Structure

**Common Elements (65% overlap):**
- Identify glosas
- Classify glosa type
- Analyze glosa reason
- Check appeal eligibility
- Generate appeal documentation
- Submit appeal
- Track appeal status

**Unique in Legacy:**
1. **Parallel Gateway for Analysis** (lines 61-100):
   - Fork: Calculate financial impact + Analyze reason
   - Join: Consolidate before eligibility check
2. **Supervisor Review with Timer** (lines 170-202):
   - User task: Supervisor review
   - 48h timer boundary event (line 184)
   - Auto-approve on timeout (line 192)
   - Gateway loops back if supervisor rejects (line 164)
3. **5-Day Polling Loop** (lines 247-304):
   - Intermediate timer event: Wait 5 business days (line 247)
   - Track appeal status (line 257)
   - Gateway: Resolved? → loop back if not resolved (line 367)
   - Loop counter: `${loopCounter < 6}` (line 368)
4. **ANS RN 424/2017 Compliance** (lines 273-297):
   - 30-day boundary timer on Track Appeal Status (line 273)
   - Escalate to ANS on timeout (line 282)
   - Specific regulatory reference in name attribute
5. **TISS Error Handling** (lines 222-244):
   - Boundary event on Submit Appeal (line 222)
   - Error handling task (line 228)
   - Dedicated error end event (line 241)

**Unique in SP-RC-007:**
1. **DMN Integration** (4 decision tables):
   - `glosa_prevention_predict` (line 62)
   - `glosa_prevention_prevent` (line 70)
   - `revenue_recovery_strategy` (line 110)
   - `revenue_recovery_eligibility` (line 119)
2. **Preventive Focus:**
   - DMN predicts glosa risk before it happens
   - Prevention strategy as a separate step
3. **Simpler Appeal Flow:**
   - Single timer: 30-day deadline on eligibility check (line 95)
   - No supervisor review
   - No polling loop
   - Single-shot track appeal status

#### Analysis

The legacy file has **operational sophistication** (supervisor approval, 5-day polling, ANS compliance) while SP-RC-007 has **preventive analytics** (risk prediction, prevention strategy).

**Key Difference:** Legacy is reactive (handle existing glosas), SP-RC-007 is proactive (predict and prevent).

**Recommendation:** **KEEP BOTH** - They serve different purposes. Consider renaming:
- Legacy → `SP-RC-007A_Glosa_Operational_Management.bpmn`
- SP-RC-007 → `SP-RC-007B_Glosa_Prevention_Strategy.bpmn`

Or **MERGE** if resources allow - combine prevention (SP-RC-007) with operational handling (legacy).

---

### 4. Clinical Production Comparison

**Legacy:** `production/bpmn/production_capture.bpmn`
**SP-RC:** `SP-RC-004_Clinical_Production.bpmn`

#### Process Structure

**Common Elements (70% overlap):**
- Validate procedures
- Assign prices
- Validate compatibility
- Persist production (record/capture)

**Unique in Legacy:**
1. **8-Step Sequential Validation Chain** (lines 44-239):
   - Validate Procedures (TUSS/CBHPM)
   - Capture Procedures (ERP)
   - Enrich Procedures (CID-10/Executante)
   - Check Authorization
   - Calculate Quantity
   - Assign Prices
   - Validate Compatibility
   - Persist Production (FHIR)
2. **Multi-Tenant Architecture** (lines 20-36):
   - `tenant_id` variable (required)
   - FHIR references (encounter, patient, coverage)
   - Contract and price table IDs
3. **ERP Integration** (line 70):
   - External topic: `production.capture_procedure`
   - ERP system output variable
4. **Authorization Check** (lines 119-143):
   - External call to check authorization
   - Boundary event for auth denial (line 139)
5. **Quantity Calculation** (lines 146-162):
   - Billable quantity calculation based on encounter duration
6. **7 Error Boundary Events:**
   - Invalid procedure code (line 63)
   - External service error (lines 87, 241)
   - Missing diagnosis (line 112)
   - Auth denied (line 139)
   - Contract violation (line 184)
   - Incompatible codes (line 210)
7. **FHIR Persistence** (line 218):
   - Outputs: `claim_reference`, `charge_item_references`

**Unique in SP-RC-004:**
1. **DMN Integration** (4 decision tables):
   - `pricing_contract_rules` (line 33)
   - `pricing_package_rules` (line 42)
   - `pricing_outlier_detection` (line 95)
2. **Outlier Detection Gateway** (lines 104-129):
   - Exclusive gateway: Is outlier?
   - User task: Review outlier if detected
3. **Simpler 6-Step Flow:**
   - Assign prices
   - DMN contract rules
   - DMN package rules
   - Validate compatibility
   - Calculate production value
   - DMN outlier detection
4. **No Authorization Check**
5. **No ERP Integration**
6. **No Multi-Tenant Support**

#### Analysis

The legacy file is **enterprise-grade** with multi-tenant support, ERP integration, authorization checks, and FHIR compliance. SP-RC-004 is simpler with focus on pricing rules via DMN.

**Key Difference:** Legacy handles full production lifecycle with external integrations; SP-RC-004 focuses on pricing and outlier detection.

**Recommendation:** **MERGE** - Use legacy as base, integrate DMN outlier detection from SP-RC-004. The authorization check, ERP capture, and FHIR persistence are critical for production environments.

---

## Overall Recommendations

### Deprecation Strategy

1. **SP-RC-006 (Billing):** Deprecate SP-RC-006, enhance with DMN rules from it
2. **SP-RC-005 (Coding):** Deprecate SP-RC-005, enhance with DMN rules from it
3. **SP-RC-007 (Glosa):** **DO NOT DEPRECATE** - Keep both or merge (different purposes)
4. **SP-RC-004 (Production):** Deprecate SP-RC-004, enhance with outlier DMN from it

### Migration Plan

| Action | Files | Timeline | Complexity |
|--------|-------|----------|------------|
| Merge DMN rules into legacy billing | billing_submission.bpmn + SP-RC-006 DMN | Week 1 | Medium |
| Merge parallel gateway into coding | coding_audit.bpmn + SP-RC-005 DMN | Week 2 | Low |
| Decision: Keep both glosa or merge | glosa_management.bpmn + SP-RC-007 | Week 3 | High |
| Merge outlier detection into production | production_capture.bpmn + SP-RC-004 DMN | Week 4 | Medium |

### Risk Analysis

**High Risk:**
- **Glosa Management:** Two different philosophies (reactive vs proactive). Merging requires careful design.

**Medium Risk:**
- **Billing Submission:** Retry logic is complex. Must preserve ACK/NACK handling during merge.
- **Production Capture:** Multi-tenant and FHIR persistence are critical. Cannot lose during merge.

**Low Risk:**
- **Coding Audit:** Parallel gateway is straightforward to integrate with DMN rules.

---

## Appendix: Detailed Element Counts

### Billing Submission (billing_submission.bpmn)

- **Service Tasks:** 12
- **Gateways:** 2 (exclusive)
- **Boundary Events:** 5 (4 error, 1 timer)
- **Subprocesses:** 1 (retry)
- **End Events:** 1
- **Error Definitions:** 4

### SP-RC-006 Billing Submission

- **Service Tasks:** 7
- **Business Rule Tasks (DMN):** 5
- **User Tasks:** 4
- **Gateways:** 2 (exclusive)
- **Boundary Events:** 2 (1 error, 1 timer)
- **End Events:** 5
- **Error Definitions:** 1

### Coding Audit (coding_audit.bpmn)

- **Service Tasks:** 10
- **Gateways:** 3 (1 parallel split, 1 parallel join, 2 exclusive)
- **Boundary Events:** 4 (error)
- **Call Activities:** 2 (manual coding, fraud review)
- **End Events:** 3
- **Error Definitions:** 4

### SP-RC-005 Coding Audit

- **Service Tasks:** 6
- **Business Rule Tasks (DMN):** 4
- **User Tasks:** 1
- **Gateways:** 1 (exclusive)
- **End Events:** 2

### Glosa Management (glosa_management.bpmn)

- **Service Tasks:** 11
- **User Tasks:** 1
- **Gateways:** 4 (1 parallel split, 1 parallel join, 4 exclusive)
- **Boundary Events:** 3 (1 error, 2 timer)
- **Intermediate Events:** 1 (timer catch - 5 days)
- **End Events:** 6
- **Error Definitions:** 1

### SP-RC-007 Denial Management

- **Service Tasks:** 8
- **Business Rule Tasks (DMN):** 4
- **User Tasks:** 2
- **Gateways:** 2 (exclusive)
- **Boundary Events:** 1 (timer - 30 days)
- **End Events:** 3

### Production Capture (production_capture.bpmn)

- **Service Tasks:** 8
- **Gateways:** 0
- **Boundary Events:** 7 (error)
- **End Events:** 8 (1 success, 7 error)
- **Error Definitions:** 7
- **Process Variables:** 16 (multi-tenant)

### SP-RC-004 Clinical Production

- **Service Tasks:** 4
- **Business Rule Tasks (DMN):** 3
- **User Tasks:** 3
- **Gateways:** 2 (exclusive)
- **Boundary Events:** 1 (error)
- **End Events:** 4
- **Error Definitions:** 1

---

**End of Audit Report**
