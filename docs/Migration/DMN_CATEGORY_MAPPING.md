# DMN Category Mapping - Legacy → Platform

**Version:** 1.0.0 | **Date:** 2026-02-09 | **Total DMN Rules:** 667 | **Medical Validation:** Complete

---

## 1. Directory Tree: Legacy → New Structure

```
Legacy processes/dmn/
├── Regras-Adm-Hospitais/ (368 rules)
│   ├── APPEAL/ (15)     → platform/dmn/revenue_recovery/
│   ├── AUTH/ (51)        → platform/dmn/authorization/
│   ├── BILL/ (62)        → platform/dmn/billing/
│   ├── CASH/ (9)         → platform/dmn/cash_operations/
│   ├── COMP/ (54)        → platform/dmn/compliance/
│   ├── CRED/ (15)        → platform/dmn/credentialing/
│   ├── DENY/ (61)        → platform/dmn/glosa_prevention/
│   ├── EDIT/ (20)        → platform/dmn/coding_audit/
│   ├── PRICE/ (15)       → platform/dmn/pricing/
│   ├── PRIOR/ (15)       → platform/dmn/authorization/
│   └── RECV/ (51)        → platform/dmn/revenue_recovery/
├── Regras-Clinicas-Hospitais/ (266 rules)
│   ├── DDI/ (50)         → platform/dmn/clinical_safety/ddi/
│   ├── DDX/ (35)         → platform/dmn/clinical_safety/ddx/
│   ├── DLI/ (40)         → platform/dmn/clinical_safety/dli/
│   ├── EWS/ (25)         → platform/dmn/clinical_safety/ews/
│   ├── LAB/ (29)         → platform/dmn/clinical_safety/lab/
│   ├── MED/ (25)         → platform/dmn/clinical_safety/med/
│   ├── RSK/ (20)         → platform/dmn/clinical_safety/rsk/
│   ├── SYN/ (22)         → platform/dmn/clinical_safety/syn/
│   └── VIT/ (20)         → platform/dmn/clinical_safety/vit/
├── Main-Federated/ (6)   → Various categories (federated/)
├── cross-cutting/ (3)    → clinical_safety/, compliance/
└── templates/ (1)        → clinical_safety/templates/
```

## 2. Count per Category

| # | Category | DMN Count | Source | Phase | Priority |
|---|----------|-----------|--------|-------|----------|
| 1 | **clinical_safety** | 268 | DDI(50)+DDX(35)+DLI(40)+EWS(25)+LAB(29)+MED(25)+RSK(20)+SYN(22)+VIT(20)+cross(1)+template(1) | 8 | CRITICAL |
| 2 | **authorization** | 68 | AUTH(51)+PRIOR(15)+FED(2) | 8 | CRITICAL |
| 3 | **glosa_prevention** | 62 | DENY(61)+FED(1) | 8 | CRITICAL |
| 4 | **billing** | 63 | BILL(62)+FED(1) | 9 | HIGH |
| 5 | **revenue_recovery** | 67 | APPEAL(15)+RECV(51)+FED(1) | 9 | HIGH |
| 6 | **compliance** | 56 | COMP(54)+cross(2) | 9 | HIGH |
| 7 | **coding_audit** | 21 | EDIT(20)+FED(1) | 9 | HIGH |
| 8 | **pricing** | 15 | PRICE(15) | 10 | MEDIUM |
| 9 | **credentialing** | 15 | CRED(15) | 10 | MEDIUM |
| 10 | **cash_operations** | 9 | CASH(9) | 10 | MEDIUM |
| 11 | **infrastructure** | 23 | Index files, configs | 10 | LOW |
| | **TOTAL** | **667** | | | |

## 3. Priority Matrix

### Clinical × Priority

| Priority | Clinical Safety | Authorization | Glosa Prevention | Subtotal |
|----------|----------------|---------------|-----------------|----------|
| **CRITICAL** | ~180 (DDI-MAJOR, EWS, LAB, SYN, VIT) | ~25 (PREAUTH, URGENCY) | ~20 (PREDICT, PREVENT) | ~225 |
| **HIGH** | ~88 (DDX, DLI, MED, RSK) | ~43 | ~42 | ~173 |
| Subtotal | 268 | 68 | 62 | 398 |

### Administrative × Priority

| Priority | Billing | Revenue Recovery | Compliance | Coding | Pricing | Cred | Cash | Infra | Subtotal |
|----------|---------|-----------------|------------|--------|---------|------|------|-------|----------|
| **HIGH** | 63 | 67 | 56 | 21 | - | - | - | - | 207 |
| **MEDIUM** | - | - | - | - | 15 | 15 | 9 | - | 39 |
| **LOW** | - | - | - | - | - | - | - | 23 | 23 |
| Subtotal | 63 | 67 | 56 | 21 | 15 | 15 | 9 | 23 | 269 |

### Grand Total: 667 DMN rules (398 Phase 8 + 207 Phase 9 + 62 Phase 10)

## 4. Phase 8 - Clinical Safety Priority (Week-by-Week)

### Week 1: Critical Lab Values & Sepsis (5 DMN)
| # | Rule ID | Name | Scoring System | Evidence |
|---|---------|------|----------------|----------|
| 1 | LAB-ELECTRO-001 | Lab_Critical_Potassium | Panic Values | AHA ACLS 2020 |
| 2 | LAB-ELECTRO-002 | Lab_Critical_Glucose | Panic Values | ADA Standards 2024 |
| 3 | LAB-RENAL-001 | Lab_Critical_Creatinine | KDIGO Stage 3 | KDIGO AKI 2012 |
| 4 | LAB-HEME-001 | Lab_Critical_INR | Bleeding Risk | CHEST Guidelines |
| 5 | SYN-SEPSIS-001 | SYN_Sepsis_qSOFA | qSOFA ≥2 | Surviving Sepsis 2021 |

### Week 2: Drug-Drug Interactions (DDI) - CYP450 Mapping
| CYP Enzyme | DDI Rules | Examples |
|------------|-----------|----------|
| CYP2C9 | DDI-BLEED-* | Warfarin + NSAIDs, Warfarin + Fluconazole |
| CYP2D6 | DDI-SEROTONIN-* | SSRIs + Tramadol, SSRIs + MAOIs |
| CYP3A4 | DDI-MAJOR-*, DDI-QT-* | Statins + Macrolides, QT drugs + Azoles |
| Multiple | DDI-HEPATO-*, DDI-NEPHRO-* | Hepatotoxic combos, Nephrotoxic combos |

### Week 3: Early Warning Scores (EWS) - Scoring Systems
| Score | Rules | Parameters | Escalation |
|-------|-------|------------|------------|
| NEWS2 | EWS-NEWS-* (7) | RR, SpO2, Temp, BP, HR, Consciousness | 0-4: Ward, 5-6: Urgent, 7+: Emergency |
| PEWS | EWS-PEWS-* (6) | HR, RR, SpO2, CRT, Behavior, Temp | Age-adjusted thresholds |
| qSOFA | EWS-qSOFA-* (6) | RR≥22, SBP≤100, GCS<15 | ≥2: Sepsis evaluation |
| MEWS | EWS-MEWS-* (6) | HR, RR, SBP, Temp, Consciousness | 0-4: Low, 5-6: Medium, 7+: High |

### Week 4: Risk Assessment & Vital Signs
| Tool | Rules | Application |
|------|-------|-------------|
| Caprini VTE | RSK-VTE-* | Venous thromboembolism risk |
| HAS-BLED | RSK-BLEED-* | Bleeding risk on anticoagulation |
| Morse Fall | RSK-FALL-* | Fall risk assessment |
| Braden | RSK-PRESSURE-* | Pressure ulcer risk |
| VIT-CRITICAL | VIT-CRITICAL-* | Panic vital sign thresholds |

## 5. Regulatory Compliance Matrix

| Category | ANVISA | ANS | LGPD | CFM | HL7 FHIR |
|----------|--------|-----|------|-----|----------|
| clinical_safety | RDC 36/2013, RDC 63/2011, RDC 7/2010 | RN 465/2021 | - | 2.217/2018 | R4 MedicationRequest, CDS Hooks |
| authorization | - | RN 465/2021, RN 259/2011, IN 68/2020 | - | - | R4 Claim |
| billing | - | RN 465/2021, TISS 4.01.00 | - | - | R4 Claim |
| compliance | RDC 36/2013 | RN 465/2021 | Lei 13.709/2018 | 1.638/2002 | - |
| glosa_prevention | - | RN 465/2021, RN 259/2011 | - | - | R4 ClaimResponse |
| revenue_recovery | - | RN 465/2021, IN DIDES 56/2018 | - | - | - |
| coding_audit | - | RN 465/2021, CBHPM 2021 | - | - | R4 Procedure |
| pricing | - | RN 465/2021, Brasindice, Simpro | - | - | - |
| credentialing | - | RN 465/2021 | - | 1.638/2002 | R4 Practitioner |
| cash_operations | - | RN 465/2021, Lei 9.656/1998 | - | - | - |

## 6. Evidence-Based Medicine Citations

| Citation | Category | Rules Affected |
|----------|----------|---------------|
| AHA ACLS 2020 | LAB, VIT, SYN | Critical thresholds, cardiac arrest criteria |
| Surviving Sepsis Campaign 2021 (JAMA) | SYN, EWS | qSOFA/SOFA scoring, sepsis bundle |
| KDIGO AKI 2012 | SYN, LAB, DLI | AKI staging, creatinine thresholds |
| NEWS2 2017 (Royal College of Physicians) | EWS | Adult early warning scoring |
| ISMP High-Alert Medications | MED | High-risk medication protocols |
| CredibleMeds QT Drug Lists | DDI | QT prolongation risk |
| Lexicomp DDI Severity (UpToDate) | DDI | Interaction severity grading |
| Cockcroft-Gault/CKD-EPI | DLI | Renal dosing adjustments |
| Child-Pugh Classification | DLI | Hepatic dosing adjustments |
| Caprini VTE Score (CHEST 2012) | RSK | VTE risk assessment |
| HAS-BLED Score (CHEST 2010) | RSK | Bleeding risk on anticoagulants |
| Morse Fall Scale | RSK | Fall risk assessment |
| Braden Scale | RSK | Pressure injury risk |

## 7. Migration Timeline

| Phase | Weeks | Categories | DMN Count | Focus |
|-------|-------|------------|-----------|-------|
| **8** | 4 weeks | clinical_safety, authorization, glosa_prevention | 398 | Patient safety + critical admin |
| **9** | 4 weeks | billing, revenue_recovery, compliance, coding_audit | 207 | Revenue cycle optimization |
| **10** | 4 weeks | pricing, credentialing, cash_operations, infrastructure | 62 | Remaining + infrastructure |

---

*Generated by Hive-Mind Migration Swarm | 2026-02-09 | Medical validation: Complete (2026-02-08)*
