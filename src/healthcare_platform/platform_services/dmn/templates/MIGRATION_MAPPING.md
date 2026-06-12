# DMN Template Migration Mapping
**Date:** 2026-02-11
**Total Files:** 778

## Mapping: Existing Schemas → New Templates

### CLINICAL_ALERT (3 outputs: nivelAlerta, acaoRequerida, justificativa)

| Current Location | Files | Current Schema | Migration Effort |
|---|---|---|---|
| clinical_safety/ddi | 32 | 3-out (nivelAlerta, acaoRequerida, justificativaCientifica) | **LOW** — rename justificativaCientifica→justificativa |
| clinical_safety/lab | 32 | 6-out (adds classificacao, tendencia) | **MEDIUM** — drop 2 outputs |
| clinical_safety/renal | 27 | 4-out (adds urgencia) | **LOW** — drop urgencia |
| clinical_safety/cardiac | 15 | 4-out (nivelAlerta, contraindicacao, medicamentoAlternativo, acaoRequerida) | **MEDIUM** — restructure |
| clinical_safety/electrolyte | 14 | 4-out | LOW |
| clinical_safety/hepatic | 13 | 4-out | LOW |
| clinical_safety/vit | 12 | 4-out | LOW |
| clinical_safety/bleed | 12 | 3-out | **TRIVIAL** |
| clinical_safety/vte | 9 | 4-out | LOW |
| clinical_safety/ews | 8 | 4-out (nivelAlerta, urgencia, acaoRequerida, justificativaCientifica) | LOW — drop urgencia |
| clinical_safety/ddx | 8 | 3-out | TRIVIAL |
| clinical_safety/respiratory | 7 | 4-out | LOW |
| clinical_safety/peds | 7 | 4-out | LOW |
| clinical_safety/neuro | 7 | 4-out | LOW |
| clinical_safety/heme | 7 | 4-out | LOW |
| clinical_safety/electro | 7 | 4-out | LOW |
| clinical_safety/dose | 7 | 4-out | LOW |
| clinical_safety/critical | 7 | 4-out | LOW |
| clinical_safety/contraind | 7 | 3-out | TRIVIAL |
| clinical_safety/allergy | 7 | 3-out | TRIVIAL |
| clinical_safety/trend | 6 | 4-out | LOW |
| clinical_safety/serotonin | 6 | 3-out | TRIVIAL |
| clinical_safety/qt | 6 | 3-out | TRIVIAL |
| clinical_safety/nephro | 6 | 3-out | TRIVIAL |
| clinical_safety/moderate | 6 | 3-out | TRIVIAL |
| clinical_safety/major | 6 | 3-out | TRIVIAL |
| clinical_safety/highrisk | 6 | 3-out | TRIVIAL |
| clinical_safety/hepato | 6 | 3-out | TRIVIAL |
| clinical_safety/frequency | 6 | 3-out | TRIVIAL |
| clinical_safety/duplicate | 6 | 3-out | TRIVIAL |
| clinical_safety/pressure | 5 | 4-out | LOW |
| clinical_safety/fall | 5 | 4-out | LOW |
| clinical_safety/dli | 5 | 4-out | LOW |
| clinical_safety/dka | 5 | 4-out | LOW |
| clinical_safety/aki | 5 | 4-out | LOW |
| clinical_safety/mews | 7 | 4-out | LOW |
| clinical_safety/news | 6 | 4-out | LOW |
| clinical_safety/pews | 6 | 4-out | LOW |
| clinical_safety/qsofa | 6 | 4-out | LOW |
| clinical_safety/sepsis | 4 | 5-out (admin schema!) | **HIGH** — wrong template in use |
| clinical_safety/mi | 4 | 4-out | LOW |
| clinical_safety/rsk | 3 | 4-out | LOW |
| clinical_safety/med | 3 | 4-out | LOW |
| **Subtotal** | **~289** | | |

### CLINICAL_SCORE (3 outputs: pontuacao, classificacao, conduta)

| Current Location | Files | Notes | Migration Effort |
|---|---|---|---|
| clinical_safety/ews (subset) | ~8 | NEWS, MEWS, PEWS, qSOFA — these are scoring, not alerting | **MEDIUM** — reclassify from ALERT to SCORE |
| clinical_safety/rsk | 3 | Risk assessment scores | MEDIUM |
| **Subtotal** | **~11** | | |

_Note: Many EWS files currently mix scoring + alerting. Should be decomposed into SCORE (C+ sum) + ALERT (FIRST threshold)._

### ADMIN_ADJUDICATION (3 outputs: resultado, acao, risco)

| Current Location | Files | Current Schema | Migration Effort |
|---|---|---|---|
| billing/opme | 10 | 5-out (resultado, observacao, acaoRecomendada, alertasConformidade, riscoDenial) | **MEDIUM** — consolidate to 3 |
| billing/material | 7 | 5-out | MEDIUM |
| billing/* (rest) | 30 | 5-out | MEDIUM |
| revenue_recovery/glosa | 11 | 5-out | MEDIUM |
| revenue_recovery/* (rest) | 29 | 5-out | MEDIUM |
| glosa_prevention/* | 53 | 5-out | MEDIUM |
| authorization/* | 29 | 5-out | MEDIUM |
| compliance/tiss | 8 | 5-out | MEDIUM |
| compliance/* (rest) | 35 | 5-out | MEDIUM |
| coding_audit/* | 21 | 5-out (different resultado values) | **MEDIUM** — remap Prosseguir/Bloquear/Alertar/Revisar → PROSSEGUIR/BLOQUEAR/REVISAR |
| pricing/* | 15 | 5-out | MEDIUM |
| credentialing/* | 15 | 5-out | MEDIUM |
| cash_operations/* | 9 | 5-out | MEDIUM |
| clinical_safety/sepsis | 4 | 5-out (misplaced!) | HIGH — should be CLINICAL_ALERT |
| **Subtotal** | **~276** | | |

### OPERATIONAL_ROUTING (3 outputs: destino, prioridade, restricao)

| Current Location | Files | Current Schema | Migration Effort |
|---|---|---|---|
| surgical/or_allocation | 1 | 4-out (recommendedRoom, alternativeRooms, schedulingPriority, conflictRisk) | **MEDIUM** — map to destino/prioridade/restricao |
| surgical/surgical_team_assignment | 1 | bespoke | MEDIUM |
| surgical/surgical_readiness | 1 | 3-out (readinessStatus, missingItems, canProceed) | **LOW** — natural fit |
| surgical/surgical_safety_checklist | 1 | bespoke | MEDIUM |
| communication/* | 4 | 3-out (sendNow, delayMinutes, channelPriority) | **MEDIUM** — map timing to routing |
| **Subtotal** | **~8** | | |

### Templates/Config/Standards (excluded from migration)

| Location | Files | Notes |
|---|---|---|
| infrastructure/config | 23 | JSON index files, not decision tables |
| compliance/standards | 1 | Schema definition (superseded by new templates) |
| clinical_safety/templates | 1 | Old template (superseded) |
| clinical_safety/safety | 1 | Meta-rule |
| */federated | ~6 | Federation routing configs |
| **Subtotal** | **~32** | |

---

## Summary

| Template | Files | % of Total | Avg Effort |
|---|---|---|---|
| CLINICAL_ALERT | 289 | 37% | LOW |
| CLINICAL_SCORE | 11 | 1% | MEDIUM |
| ADMIN_ADJUDICATION | 276 | 35% | MEDIUM |
| OPERATIONAL_ROUTING | 8 | 1% | MEDIUM |
| Excluded (config/meta) | 32 | 4% | N/A |
| **Unaccounted** | **162** | **21%** | Needs classification |

_The 162 unaccounted files are distributed across sub-domains that appear in multiple mappings. Exact classification requires per-file inspection during Phase 0.5 triage._

---

## Migration Priority

1. **clinical_safety/sepsis** (4 files) — WRONG TEMPLATE. Using admin schema for clinical safety. Fix immediately.
2. **clinical_safety/lab** (32 files) — 6 outputs → 3. Largest structural change.
3. **billing + revenue_recovery + glosa_prevention** (93 files) — Highest volume admin. Batch rename.
4. **authorization** (29 files) — High business impact.
5. **Everything else** — Incremental.
