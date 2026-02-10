# DMN Migration Manifest - Summary Report

**Generated:** 2026-02-09T21:07:54Z
**Version:** 1.0.0
**Total Entries:** 667
**Status:** ✓ COMPLETE

## Overview

This manifest provides a comprehensive mapping of all 667 legacy DMN (Decision Model and Notation) files to the new platform structure for the CIB7 Healthcare Orchestrator. It includes administrative rules, clinical safety alerts, federated services, cross-cutting concerns, templates, and infrastructure files.

## Source Breakdown

| Source Category | Count | Description |
|----------------|-------|-------------|
| **Administrative Rules** | 369 | Revenue cycle, authorization, billing, compliance |
| **Clinical Safety Rules** | 267 | Drug interactions, vital signs, early warning scores |
| **Federated DMN Files** | 6 | Cross-system orchestration rules |
| **Cross-Cutting Files** | 3 | Shared rules (contraindications, documentation, standards) |
| **Template Files** | 1 | Enhanced clinical rule template |
| **Infrastructure Files** | 21 | Configuration, indexes, metadata |
| **TOTAL** | **667** | |

## Category Distribution

| Category | Count | Phase | Priority Mix |
|----------|-------|-------|--------------|
| **clinical_safety** | 268 | 8 | 193 CRITICAL, 75 HIGH |
| **authorization** | 68 | 8 | 53 CRITICAL, 15 HIGH |
| **revenue_recovery** | 67 | 9 | HIGH |
| **billing** | 63 | 9 | HIGH |
| **glosa_prevention** | 62 | 8 | 62 CRITICAL |
| **compliance** | 56 | 9 | HIGH |
| **infrastructure** | 23 | 10 | LOW |
| **coding_audit** | 21 | 9 | HIGH |
| **credentialing** | 15 | 10 | MEDIUM |
| **pricing** | 15 | 10 | MEDIUM |
| **cash_operations** | 9 | 10 | MEDIUM |

## Migration Phases

### Phase 8: Clinical Safety & Critical Auth (397 rules)
- **Focus:** Patient safety, critical authorizations, glosa prevention
- **Duration:** 4 weeks
- **Priority:** 308 CRITICAL, 89 HIGH
- **Key Categories:** clinical_safety (268), glosa_prevention (62), authorization (53)
- **Business Value:** Patient safety + R$ 27M/year denial prevention

### Phase 9: Revenue Cycle Operations (206 rules)
- **Focus:** Billing, appeals, coding, compliance
- **Duration:** 4 weeks
- **Priority:** 206 HIGH
- **Key Categories:** revenue_recovery (67), billing (63), compliance (56), coding_audit (21)
- **Business Value:** R$ 20M/year revenue optimization

### Phase 10: Support Services (64 rules)
- **Focus:** Infrastructure, pricing, credentialing, cash operations
- **Duration:** 4 weeks
- **Priority:** 40 MEDIUM, 24 LOW
- **Key Categories:** infrastructure (23), credentialing (15), pricing (15), cash_operations (9)
- **Business Value:** Operational efficiency + R$ 7M/year

## Priority Levels

| Priority | Count | % of Total | Key Focus Areas |
|----------|-------|------------|-----------------|
| **CRITICAL** | 308 | 46.2% | Patient safety, authorization, glosa prevention |
| **HIGH** | 295 | 44.2% | Revenue cycle, billing accuracy, compliance |
| **MEDIUM** | 40 | 6.0% | Support services, pricing, credentialing |
| **LOW** | 24 | 3.6% | Infrastructure, configuration, templates |

## Business Value Summary

### Quantified Revenue Impact: R$ 56.5M/year

- **Denial Prevention (AUTH + DENY):** R$ 27M/year
- **Revenue Recovery (APPEAL + RECV):** R$ 9.5M/year
- **Billing Accuracy (BILL):** R$ 8M/year
- **Coding Accuracy (EDIT):** R$ 5M/year
- **Pricing Optimization (PRICE):** R$ 4M/year
- **Cash Flow Optimization (CASH):** R$ 3M/year

### Patient Safety Impact

- **267 Clinical Safety Rules** covering:
  - Drug-Drug Interactions (DDI): 50 rules
  - Disease-Drug Contraindications (DDX): 35 rules
  - Drug-Lab Interactions (DLI): 40 rules
  - Early Warning Scores (EWS): 25 rules
  - Critical Lab Values (LAB): 29 rules
  - Medication Safety (MED): 25 rules
  - Risk Assessment (RSK): 20 rules
  - Clinical Syndromes (SYN): 22 rules
  - Vital Signs (VIT): 21 rules

## Regulatory Compliance

### Key Regulations Referenced

| Regulation | Scope | Rules Affected |
|-----------|--------|----------------|
| **ANS RN 465/2021** | Operational standards | 376 rules |
| **ANVISA RDC 36/2013** | Clinical safety | 324 rules |
| **CFM 2.217/2018** | Medical ethics | 267 rules |
| **ANVISA RDC 63/2011** | Drug safety | 267 rules |
| **ANS RN 259/2011** | Authorization | 130 rules |
| **ANS IN DIDES 56/2018** | Billing/compliance | 130 rules |
| **LGPD Lei 13.709/2018** | Data protection | 56 rules |
| **ANS IN 68/2020** | Authorization | 68 rules |
| **CBHPM 2021** | Coding standards | 21 rules |
| **TISS 4.01.00** | Data exchange | 84 rules |

## Administrative Rules Categories

### APPEAL - Appeals and Resources (15 rules → revenue_recovery)
- **ELIG** (5): Eligibility for appeals
- **STRATEGY** (5): Appeal strategy optimization
- **TRACK** (5): Appeal tracking and follow-up

### AUTH - Authorization (102 rules → authorization)
- **PREAUTH** (10): Prior authorization (CRITICAL)
- **URGENCY** (8): Urgent authorization (CRITICAL)
- **STANDARD** (5): Standard authorization
- **FOLLOW** (5): Authorization follow-up
- ... (19 subcategories total)

### BILL - Billing (63 rules → billing)
- **ACCURACY** (5): Billing accuracy validation
- **AUDIT** (5): Billing audit rules
- **COPAY** (5): Co-payment calculation
- **PROCEDURE** (5): Procedure code validation
- ... (11 subcategories total)

### DENY - Denial Management (62 rules → glosa_prevention)
- All rules marked CRITICAL priority
- Focus on real-time denial prevention
- Integration with authorization workflows

### Other Administrative Categories
- **CASH** (9 rules): Cash operations
- **COMP** (56 rules): Compliance validation
- **CRED** (15 rules): Credentialing
- **EDIT** (21 rules): Coding audit
- **PRICE** (15 rules): Pricing
- **PRIOR** (15 rules): Prior authorization
- **RECV** (52 rules): Revenue recovery

## Clinical Safety Categories

### DDI - Drug-Drug Interactions (50 rules)
**Priority:** CRITICAL
**Subcategories:**
- BLEED: Bleeding risk interactions
- CONTRAIND: Absolute contraindications
- HEPATO: Hepatotoxicity risk
- MAJOR: Major interactions
- MODERATE: Moderate interactions
- NEPHRO: Nephrotoxicity risk
- QT: QT prolongation risk (CRITICAL)
- SEROTONIN: Serotonin syndrome risk (CRITICAL)

### EWS - Early Warning Scores (25 rules)
**Priority:** CRITICAL
**Subcategories:**
- NEWS: National Early Warning Score 2
- qSOFA: Quick SOFA (sepsis screening)
- MEWS: Modified Early Warning Score
- PEWS: Pediatric Early Warning Score

### SYN - Clinical Syndromes (22 rules)
**Priority:** CRITICAL
**Subcategories:**
- SEPSIS: Sepsis detection (qSOFA/SOFA)
- AKI: Acute Kidney Injury (KDIGO)
- MI: Myocardial Infarction
- DKA: Diabetic Ketoacidosis
- VTE: Venous Thromboembolism

### LAB - Critical Lab Values (29 rules)
**Priority:** CRITICAL
**Subcategories:**
- CARDIAC: Cardiac markers (Troponin, BNP)
- ELECTRO: Electrolyte abnormalities
- HEME: Hematologic values (CBC)
- RENAL: Renal function markers

## Special Files

### Federated DMN Files (6)
1. **FED-BILL-001**: Federated Billing Calculation
2. **FED-RECV-001**: Federated Collection Workflow
3. **FED-AUTH-001**: Federated Eligibility Verification
4. **FED-EDIT-001**: Federated Coding Validation
5. **FED-AUTH-002**: Federated Authorization Approval
6. **FED-DENY-001**: Federated Glosa Classification

### Cross-Cutting Rules (3)
1. **CROSS-SAFETY-001**: Universal Contraindications (CRITICAL)
2. **CROSS-COMP-001**: Documentation Gate (HIGH)
3. **CROSS-COMP-002**: Standard Outputs (MEDIUM)

### Template Files (1)
1. **TEMPLATE-CLINICAL-001**: Enhanced Clinical Rule Template

## Migration Status Tracking

All 667 entries are currently marked as **"pending"** migration. As migration progresses, update status to:
- `"in-progress"` - Migration work underway
- `"complete"` - Migration and validation complete
- `"blocked"` - Migration blocked (with notes)
- `"deferred"` - Deferred to later phase

## Medical Validation

- **Complete:** 643 rules (96.4%)
- **N/A:** 24 rules (3.6% - infrastructure)

All clinical safety and administrative rules have completed medical validation by qualified healthcare professionals.

## Usage

### Query by Category
```bash
jq '.entries[] | select(.category == "clinical_safety") | .rule_id' migration_manifest.json
```

### Query by Priority
```bash
jq '.entries[] | select(.priority == "CRITICAL") | {rule_id, category, business_value}' migration_manifest.json
```

### Query by Phase
```bash
jq '.entries[] | select(.phase == 8) | {rule_id, category, priority}' migration_manifest.json
```

### Get Summary Statistics
```bash
jq '.summary' migration_manifest.json
```

### Find Specific Rule
```bash
jq '.entries[] | select(.rule_id == "DDI-QT-001")' migration_manifest.json
```

## Next Steps

1. **Phase 8 (Weeks 1-4):** Migrate 397 CRITICAL clinical safety and authorization rules
2. **Phase 9 (Weeks 5-8):** Migrate 206 HIGH priority revenue cycle rules
3. **Phase 10 (Weeks 9-12):** Migrate 64 MEDIUM/LOW priority support and infrastructure files

4. **Continuous Activities:**
   - Update migration_status as work progresses
   - Track blockers and dependencies
   - Validate each rule post-migration
   - Update regulatory references as needed
   - Document any rule changes or enhancements

## File Locations

- **Manifest:** `docs/Migration/migration_manifest.json` (537.8 KB)
- **Generator Script:** `scripts/generate_migration_manifest.py`
- **Legacy Admin Rules:** `Legacy processes/dmn/Regras-Adm-Hospitais/`
- **Legacy Clinical Rules:** `Legacy processes/dmn/Regras-Clinicas-Hospitais/`
- **Target Platform:** `platform/dmn/` (to be created during migration)

## Verification

✓ Total entries verified: 667
✓ All required fields present
✓ Category mapping validated
✓ Phase assignments complete
✓ Priority levels assigned
✓ Regulatory references included
✓ Business value quantified (96.4%)
✓ Medical validation complete (96.4%)

---

**Document Version:** 1.0.0
**Last Updated:** 2026-02-09
**Maintained By:** CIB7 Healthcare Orchestrator Migration Team
