# LAB Clinical Alert Rules - Generation Status

## Completed Rules (6/30)

### Potassium Rules (4/4 complete)
- ✅ LAB-ELECTRO-K-001: Critical hypokalemia (<2.5 mEq/L)
- ✅ LAB-ELECTRO-K-002: Critical hyperkalemia (>6.5 mEq/L)
- ✅ LAB-ELECTRO-K-003: Moderate K+ abnormality (2.5-3.4 or 5.6-6.4)
- ✅ LAB-ELECTRO-K-004: Normal K+ (3.5-5.0 mEq/L)

### Sodium Rules (1/4 complete)
- ✅ LAB-ELECTRO-NA-001: Critical hyponatremia (<120 mEq/L)
- ⏳ LAB-ELECTRO-NA-002: Critical hypernatremia (>160 mEq/L)
- ⏳ LAB-ELECTRO-NA-003: Moderate Na+ abnormality (120-134 or 146-159)

### Remaining Rules (24/30)

#### Electrolytes (4 remaining)
- ⏳ LAB-ELECTRO-CA-001: Critical ionized calcium low (<0.8 mmol/L)
- ⏳ LAB-ELECTRO-CA-002: Critical ionized calcium high (>1.5 mmol/L)
- ⏳ LAB-ELECTRO-MG-001: Critical magnesium low (<1.0 mg/dL)
- ⏳ LAB-ELECTRO-MG-002: Critical magnesium high (>4.0 mg/dL)
- ⏳ LAB-ELECTRO-PHOS-001: Critical phosphorus values

#### Renal (5 remaining)
- ⏳ LAB-RENAL-001: Creatinine increase >=0.3 from baseline (AKI Stage 1)
- ⏳ LAB-RENAL-002: Creatinine 2x baseline (AKI Stage 2)
- ⏳ LAB-RENAL-003: Creatinine 3x baseline or >4.0 (AKI Stage 3)
- ⏳ LAB-RENAL-004: BUN >100 mg/dL (uremia)
- ⏳ LAB-RENAL-005: Creatinine trending up pattern

#### Hematology (6 remaining)
- ⏳ LAB-HEME-HGB-001: Hemoglobin <7.0 g/dL (transfusion trigger)
- ⏳ LAB-HEME-HGB-002: Hemoglobin 7.0-9.9 g/dL (moderate anemia)
- ⏳ LAB-HEME-PLT-001: Platelets <20,000/µL (critical)
- ⏳ LAB-HEME-PLT-002: Platelets <50,000/µL (procedure risk)
- ⏳ LAB-HEME-WBC-001: WBC <1,000/µL (severe neutropenia)
- ⏳ LAB-HEME-ANC-001: ANC <500 + fever (neutropenic fever)

#### Coagulation (4 remaining)
- ⏳ LAB-COAG-INR-001: INR >5.0 (major bleeding risk)
- ⏳ LAB-COAG-INR-002: INR 4.0-5.0 (moderate bleeding risk)
- ⏳ LAB-COAG-APTT-001: aPTT >100 seconds
- ⏳ LAB-COAG-FIB-001: Fibrinogen <100 mg/dL (DIC)

#### Cardiac (3 remaining)
- ⏳ LAB-CARDIAC-TROP-001: Troponin elevated + dynamic change (acute MI)
- ⏳ LAB-CARDIAC-BNP-001: BNP >400 pg/mL (heart failure)
- ⏳ LAB-CARDIAC-LAC-001: Lactate >4.0 mmol/L (shock/hypoperfusion)

## Critical Value Thresholds Summary

| Parameter | Critical Low | Critical High | Normal Range |
|-----------|--------------|---------------|--------------|
| Potassium | <2.5 mEq/L | >6.5 mEq/L | 3.5-5.0 mEq/L |
| Sodium | <120 mEq/L | >160 mEq/L | 135-145 mEq/L |
| Ionized Ca | <0.8 mmol/L | >1.5 mmol/L | 1.12-1.32 mmol/L |
| Magnesium | <1.0 mg/dL | >4.0 mg/dL | 1.7-2.4 mg/dL |
| Hemoglobin | <7.0 g/dL | - | 12-16 g/dL (F), 13.5-17.5 g/dL (M) |
| Platelets | <20,000/µL | - | 150,000-400,000/µL |
| INR | - | >5.0 | 0.8-1.2 |
| Lactate | - | >4.0 mmol/L | 0.5-2.2 mmol/L |

## Next Steps

To complete the remaining 24 rules, continue with the same pattern:
1. Create regra.dmn.xml with FIRST hitPolicy
2. Create metadata.json with clinical rationale
3. Include immediate action guidance for critical values
4. Reference evidence-based guidelines

All rules must include:
- Input variables with normal ranges
- Output: nivelAlerta, urgencia, classificacao, tendencia, acaoRequerida, justificativaCientifica
- Critical values trigger IMEDIATA urgency
- Scientific justification for each threshold
