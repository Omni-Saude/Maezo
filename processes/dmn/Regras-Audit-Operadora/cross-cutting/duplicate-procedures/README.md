# Cross-Cutting Duplicate Procedure Prevention Rules

## Overview
This category contains 10 high-value DMN rules designed to prevent unnecessary duplicate procedures, tests, and exams across all medical specialties. These rules enforce evidence-based intervals between procedures, reducing healthcare waste while maintaining clinical quality.

## Rules Generated

| Rule ID | Name | Focus Area | Potential Savings |
|---------|------|------------|-------------------|
| **DUP-001** | Repeat Imaging Interval Control | TC, RM, PET-CT, Densitometria, Mamografia | R$500-5000/exam |
| **DUP-002** | Same-Day Laboratory Test Control | Hemograma, Glicemia, Eletrólitos, Função Renal/Hepática | R$5-50/test |
| **DUP-003** | Consultation Frequency Control | Consultas repetidas mesma especialidade | R$100-500/consultation |
| **DUP-004** | Duplicate Endoscopy Control | EDA, Colonoscopia, Broncoscopia, Artroscopia | R$400-3000/procedure |
| **DUP-005** | Duplicate Ultrasound Control | US Abdome, Transvaginal, Próstata, Tireoide, Mama | R$80-250/exam |
| **DUP-006** | Duplicate Radiography Control | RX Tórax, Coluna, Ossos Longos, Crânio | R$30-100/exam |
| **DUP-007** | Duplicate Cardiac Test Control | ECG, Ecocardiograma, Holter, MAPA, Teste Ergométrico | R$15-500/test |
| **DUP-008** | Duplicate Laboratory Panel Control | Perfis Lipídico, Tireoidiano, Hormonal, Vitamínico | R$30-400/panel |
| **DUP-009** | Duplicate Specialty Imaging Control | Angiotomografia, Angiorressonância, Cintilografia | R$500-5000/exam |
| **DUP-010** | Duplicate Procedure Same-Day Control | Curativo, Nebulização, Medicação Injetável, Glicemia Capilar | R$2-500/procedure |

## Clinical Rationale

### Evidence-Based Intervals

Each rule enforces minimum intervals based on clinical evidence:

**Imaging**:
- TC: 90 days (lesions change over months, not weeks)
- RM: 180 days (soft tissue evolution requires time)
- PET-CT: 180 days (metabolic changes in oncology follow-up)
- Densitometria: 730 days (bone density changes annually)

**Laboratory**:
- Hemograma: 24h (hematological parameters stable short-term)
- Eletrólitos: 24h (electrolyte balance stable in non-ICU)
- Perfil Lipídico: 90 days (lipid changes require 3+ months)
- Perfil Tireoidiano: 60 days (TSH stabilization takes 6-8 weeks)

**Endoscopy**:
- EDA: 180 days (mucosal healing 6+ months)
- Colonoscopia: 365 days (polyp surveillance intervals)
- Broncoscopia: 90 days (pulmonary findings stability)

**Consultations**:
- General limit: 3 consultations/30 days (prevents over-utilization)
- Specialty-specific: Cardiologia 4/30d, Psiquiatria 5/30d
- Chronic disease follow-up: Appropriate intervals per condition

## Exception Handling

All rules include approval pathways for legitimate clinical needs:

1. **Clinical Change**: New symptoms, worsening condition
2. **Critical Values**: Laboratory/imaging findings requiring urgent follow-up
3. **ICU Patients**: Frequent monitoring justified for critical patients
4. **Post-Intervention**: Procedures after surgery/intervention
5. **Emergency**: Trauma, acute illness overrides elective intervals
6. **Medical Prescription**: Documented physician order for repeat

## Financial Impact

### Estimated Annual Savings per 100,000 Beneficiaries

| Category | Duplicates Prevented | Annual Savings |
|----------|---------------------|----------------|
| Advanced Imaging (TC/RM/PET) | 500-1000/year | R$750k-2.5M |
| Laboratory Tests | 5000-10000/year | R$150k-400k |
| Endoscopy | 200-400/year | R$200k-800k |
| Ultrasound | 1000-2000/year | R$150k-400k |
| Radiography | 2000-4000/year | R$120k-300k |
| Consultations | 1000-2000/year | R$150k-400k |
| **TOTAL** | **9700-19400/year** | **R$1.52M-4.8M** |

### Cost-Benefit Analysis

- **Implementation Cost**: Minimal (rules run automatically)
- **ROI**: 1500%-3000% (automated detection vs. manual review)
- **Clinical Safety**: Maintained through exception rules
- **Patient Satisfaction**: Reduced unnecessary procedures

## Rule Structure

All rules follow the standard pattern:

```xml
<decisionTable hitPolicy="FIRST">
  <!-- Clinical inputs (3-4 variables) -->
  <input tipoExame />
  <input intervaloDesdeUltimo />
  <input mudancaClinica />
  <input urgenciaEmergencia />

  <!-- Standard outputs -->
  <output resultado />  <!-- Aprovado/Reprovado/Pendente -->
  <output observacao />
  <output fundamentacao />

  <!-- Rule order: Reprovado → Aprovado → Pendente → Fallback -->
</decisionTable>
```

## Integration Points

### Pre-Authorization System
```
Request → DUP Rules → Resultado:
├── Reprovado: Alert staff, request justification
├── Aprovado: Auto-approve based on clinical criteria
└── Pendente: Route to manual review
```

### Alert System
Reprovado triggers generate:
- Real-time alert to requesting physician
- Cost impact notification (R$ saved if avoided)
- Alternative timeline suggestion
- Evidence-based justification

### Reporting Metrics
Track quarterly:
- Duplicate procedures prevented by category
- Cost savings realized
- Override rate (clinical necessity)
- False positive rate (inappropriately flagged)

## Clinical Guidelines Referenced

All rules cite authoritative sources:

- **Choosing Wisely** (American Board of Internal Medicine)
- **ACR Appropriateness Criteria** (American College of Radiology)
- **SBC** (Sociedade Brasileira de Cardiologia)
- **SBPC-ML** (Sociedade Brasileira de Patologia Clínica)
- **SOBED** (Sociedade Brasileira de Endoscopia Digestiva)
- **NCCN Guidelines** (National Comprehensive Cancer Network)
- **ASCO** (American Society of Clinical Oncology)
- **Brazilian Medical Societies** (SBEM, SBD, SBU, etc.)

## Quality Assurance

### Monthly Review
- Analyze overridden cases for appropriateness
- Adjust interval thresholds if clinical practice evolves
- Monitor patient outcomes (no harm from delayed procedures)

### Annual Update
- Review new clinical guidelines
- Update interval recommendations
- Expand rule coverage based on utilization data

## Compliance

These rules support:
- **ANS RN 465/2021**: Appropriate resource utilization
- **CDC Consumer Protection**: Prevent unnecessary procedures
- **Medical Society Guidelines**: Evidence-based practice
- **Choosing Wisely**: High-value, low-waste healthcare

## Success Metrics

**Target Performance** (Year 1):
- 80% duplicate detection rate
- 90% clinical appropriateness (low false positives)
- 60% cost savings realization (40% clinical overrides expected)
- <1% adverse events from delayed procedures

## Notes

- Rules are **advisory**, not absolute blocks
- Physicians can override with documented justification
- Focus is waste reduction, not access restriction
- Continuous monitoring ensures clinical safety
- Patient outcomes are primary measure of success

---

**Version**: 1.0
**Created**: 2026-02-07
**Rules**: DUP-001 through DUP-010
**Total Waste Prevention Potential**: R$1.5M-4.8M annually per 100k beneficiaries
