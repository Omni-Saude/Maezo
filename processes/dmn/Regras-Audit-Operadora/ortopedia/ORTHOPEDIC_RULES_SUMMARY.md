# Orthopedic DMN Rules - Priority 10 Generated

## Overview
Generated 10 high-priority orthopedic DMN rules focusing on:
1. **Conservative Treatment First** (3 rules)
2. **Device Selection - OPME** (3 rules)
3. **Spine Surgery** (4 rules)

---

## CONSERVATIVE TREATMENT FIRST

### ORT-CONS-001: Fisioterapia Antes de Artroscopia de Joelho (TUSS 30727014)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30727014/regra.dmn.xml`

**Clinical Logic**:
- **APPROVED**: Joelho bloqueado (emergência) OR Ruptura meniscal aguda traumática em paciente <40 anos
- **APPROVED**: Tratamento conservador ≥6 semanas com falha terapêutica
- **REJECTED**: Lesão degenerativa em paciente ≥50 anos sem <6 semanas de fisioterapia
- **PENDING**: 3-6 semanas de fisioterapia (completar protocolo)

**Waste Prevention**: R$8.000-R$15.000 per premature surgery avoided

**References**: AAOS 2013, SBO Guidelines on Meniscal Tears

---

### ORT-CONS-002: Conservador Antes de Artroplastia Total de Joelho (TUSS 30727030)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30727030/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: K-L Grade 0-1 (no significant OA)
- **REJECTED**: K-L Grade 2 without ≥6 months conservative treatment OR without multimodal therapy
- **APPROVED**: K-L Grade 3-4 with failed conservative treatment (≥3 months, PT + analgesia)
- **APPROVED**: K-L Grade 2 with complete multimodal failure (≥6 months, PT + NSAIDs + injection)

**Waste Prevention**: R$40.000-R$60.000 per inappropriate TKA avoided

**References**: AAOS Knee OA Guidelines, OARSI Recommendations

---

### ORT-CONS-003: Conservador Antes de Artroplastia Total de Quadril (TUSS 30711045)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30711045/regra.dmn.xml`

**Clinical Logic**:
- **APPROVED (Emergency)**: Necrose avascular com colapso OR Fratura colo de fêmur em idade >60 anos
- **REJECTED**: Osteoartrite sem <3 meses tratamento conservador
- **REJECTED**: Conservador incompleto (missing PT, analgesia, or activity modification)
- **APPROVED**: Osteoartrite with ≥3 months complete multimodal conservative failure

**Waste Prevention**: R$40.000-R$60.000 per premature THA avoided

**References**: AAOS Hip OA Guidelines

---

## DEVICE SELECTION - OPME

### ORT-DEV-001: Seleção de Prótese - Cerâmica vs Metal ATQ (TUSS 30711037)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30711037/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: Cerâmica-cerâmica em paciente ≥75 anos sedentário (expectativa <15 anos)
- **APPROVED**: Cerâmica-cerâmica em paciente <60 anos, ativo/muito_ativo, expectativa ≥20 anos
- **REJECTED**: Metal-metal em insuficiência renal crônica (liberação de íons metálicos)
- **APPROVED**: Cerâmica em paciente 60-70 anos, ativo, expectativa ≥15 anos
- **REJECTED**: Idade 70-75 anos sedentário/moderado com custo adicional >R$15.000

**Waste Prevention**: R$10.000-R$25.000 per inappropriate premium implant avoided

**References**: AAOS Hip Implant Guidelines, FDA Safety Communication

---

### ORT-DEV-002: Fixação Cimentada vs Não-Cimentada ATQ (TUSS 30727022)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30727022/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: Não-cimentada em idade ≥75 anos + osteoporose severa (T-score <-2.5)
- **APPROVED**: Cimentada em idade ≥75 anos + osteoporose (T-score <-1.5) - fixação imediata
- **APPROVED**: Não-cimentada em idade <65 anos + boa qualidade óssea (T-score ≥-1.0) + expectativa ≥15 anos
- **REJECTED**: Não-cimentada em idade ≥75 anos sem justificativa com custo adicional >R$10.000
- **APPROVED**: Híbrida em idade 65-75 anos (acetábulo não-cimentado + femoral cimentado)

**Waste Prevention**: R$8.000-R$15.000 per inappropriate fixation method + reduced complications

**References**: AAOS Hip Arthroplasty Guidelines

---

### ORT-DEV-003: Implante Padrão vs Revisão ATQ/ATJ (TUSS 30711029)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30711029/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: Implante de revisão em cirurgia primária (perda óssea mínima)
- **APPROVED**: Implante de revisão em revisão com perda óssea severa/massiva (Paprosky Tipo 3/4)
- **APPROVED**: Revisão séptica com espaçador + implante revisão no segundo tempo
- **REJECTED**: Revisão com perda óssea mínima usando implante premium (custo >R$20.000)
- **APPROVED**: Revisão moderada com enxerto ósseo (Paprosky Tipo 2)

**Waste Prevention**: R$15.000-R$35.000 per inappropriate revision implant avoided

**References**: AAOS Revision Guidelines, AAOS Periprosthetic Infection Guidelines

---

## SPINE SURGERY

### ORT-SPI-001: Conservador Antes de Fusão Lombar (TUSS 30716241)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30716241/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: Espondilolistese sem ≥6 meses tratamento conservador
- **REJECTED**: Doença degenerativa discal sem protocolo multimodal completo
- **APPROVED**: ≥6 meses conservador falho + instabilidade documentada + deficit neurológico
- **APPROVED (Emergency)**: Síndrome de cauda equina OR deficit neurológico progressivo
- **PENDING**: 3-6 meses conservador (completar protocolo)

**Waste Prevention**: R$25.000-R$40.000 per premature fusion avoided

**References**: SBO Spine Guidelines, North American Spine Society, AAOS

---

### ORT-SPI-002: Discectomia vs Conservador (TUSS 30716250)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30716250/regra.dmn.xml`

**Clinical Logic**:
- **APPROVED (Emergency)**: Síndrome de cauda equina OR deficit motor progressivo
- **APPROVED**: Correlação clínico-radiológica + sintomas radiculares + falha conservadora ≥6 semanas
- **REJECTED**: Hérnia discal sem correlação clínico-radiológica
- **REJECTED**: <6 semanas tratamento conservador em hérnia não-emergencial
- **PENDING**: 4-6 semanas conservador (completar tentativa)

**Waste Prevention**: R$12.000-R$20.000 per premature discectomy avoided

**References**: SBO, North American Spine Society Guidelines

---

### ORT-SPI-003: Laminectomia para Estenose Lombar (TUSS 30716268)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30716268/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: Estenose assintomática ou sintomas leves sem tratamento conservador
- **REJECTED**: <3 meses tratamento conservador em estenose moderada/severa
- **APPROVED**: Claudicação neurogênica documentada + estenose confirmada + ≥3 meses conservador falho
- **APPROVED (Emergency)**: Deficit neurológico progressivo OR síndrome de cauda equina
- **PENDING**: Estenose sem documentação funcional (solicitar teste de caminhada, WOMAC)

**Waste Prevention**: R$18.000-R$30.000 per premature laminectomy avoided

**References**: SBO, AAOS, North American Spine Society

---

### ORT-SPI-004: Seleção de Cage de Fusão - Padrão vs Premium (TUSS 30716276)
**File**: `processes/dmn/regras-clinicas-operadora/ortopedia/30716276/regra.dmn.xml`

**Clinical Logic**:
- **REJECTED**: Cage premium (PEEK expandível, titânio poroso) em fusão 1-2 níveis sem fatores de risco
- **APPROVED**: Cage premium em fusão ≥3 níveis OR osteoporose severa OR revisão
- **APPROVED**: Cage padrão PEEK em fusão 1-2 níveis com boa qualidade óssea
- **REJECTED**: Custo adicional >R$20.000 sem justificativa biomecânica
- **PENDING**: Fusão complexa requer avaliação caso-a-caso

**Waste Prevention**: R$15.000-R$30.000 per inappropriate premium cage avoided

**References**: North American Spine Society, SBO Interbody Fusion Guidelines

---

## Summary Statistics

| Category | Rules | Total Waste Prevention |
|----------|-------|------------------------|
| Conservative First | 3 | R$88.000-R$135.000 per case avoided |
| Device Selection | 3 | R$33.000-R$75.000 per inappropriate device |
| Spine Surgery | 4 | R$70.000-R$120.000 per premature surgery |

**Total Economic Impact**: R$191.000-R$330.000 per full suite of inappropriate procedures prevented

## Key Clinical Principles Applied

1. **Conservative First**: All non-emergency cases require documented conservative treatment failure
2. **Age-Appropriate Device Selection**: Premium devices justified only for young, active patients with long life expectancy
3. **Bone Quality Matters**: Osteoporosis requires cemented fixation for immediate stability
4. **Emergency Exceptions**: Locked knee, cauda equina, progressive neurological deficit bypass conservative treatment
5. **Multimodal Requirement**: PT + pharmacologic + activity modification required before surgery
6. **Cost-Benefit Analysis**: Premium devices require clear clinical justification with measurable benefit

## Implementation Notes

- All rules use `hitPolicy="FIRST"` with order: REJECTED → APPROVED → PENDING → DEFAULT
- Minimum 3-5 clinical inputs with camelCase naming
- Three standard outputs: `resultado`, `observacao`, `fundamentacao`
- Economic impact quantified for all waste prevention rules
- Evidence-based references from AAOS, SBO, OARSI, North American Spine Society

## Next Steps

Continue generating remaining 60 rules across:
- Arthroplasty Criteria (5 rules)
- Additional Conservative First (17 rules)
- Additional Device Selection (22 rules)
- Additional Spine Surgery (16 rules)

