# DMN Template Standard — Healthcare Orchestration Platform

**Version:** 1.0.0
**Date:** 2026-02-11
**Status:** Normative
**Governs:** All `.dmn` files in `healthcare_platform/`

---

## Design Principles

1. **One decision archetype = one template.** Don't mix clinical alerting with revenue adjudication.
2. **Minimum viable outputs.** Every output must answer a question the downstream consumer _will_ act on. If nobody reads it, delete it.
3. **Inputs are domain-specific. Outputs are archetype-specific.** Templates standardize outputs. Inputs are defined by the rule author per use case.
4. **FIRST hit policy by default.** Rules ordered by severity (deny/block first, allow last, fallback at bottom). Use UNIQUE only when input space is fully partitioned. Use COLLECT only for scoring.
5. **No prose in output cells.** Use codes and enums. Free-text rationale goes in exactly one `string` column — never duplicated across multiple verbose columns.
6. **Tenant-override aware.** All templates comply with ADR-007 federated DMN. Global deploys without `tenantId`, overrides deploy with.

---

## Template Selection Guide

| Decision Archetype | Template | Outputs | Use When |
|---|---|---|---|
| **Clinical Alert** | `CLINICAL_ALERT` | 3 | Patient safety, drug interaction, vitals, lab values, early warning |
| **Clinical Scoring** | `CLINICAL_SCORE` | 3 | Risk scores, severity indices, acuity (NEWS, qSOFA, MEWS, Braden) |
| **Administrative Adjudication** | `ADMIN_ADJUDICATION` | 3 | Authorization, billing validation, glosa prevention, coding audit, compliance |
| **Operational Routing** | `OPERATIONAL_ROUTING` | 3 | Scheduling, allocation, assignment, queue prioritization |

### Why only 4 templates?

Every hospital DMN decision falls into one of four archetypes:

- **ALERT**: "Is this dangerous?" → severity + action + evidence
- **SCORE**: "How bad is this?" → numeric score + risk tier + factors
- **ADJUDICATE**: "Should we proceed?" → verdict + action + risk
- **ROUTE**: "Where/when/who?" → target + priority + constraint

If a proposed rule doesn't fit any archetype, it's likely mixing concerns and should be decomposed.

---

## Output Contracts

### CLINICAL_ALERT (3 outputs)

Answers: _"Is this clinically dangerous, and what should be done?"_

| # | Name | Type | Values | Semantics |
|---|---|---|---|---|
| 1 | `nivelAlerta` | string | `CRITICO`, `ALTO`, `MEDIO`, `BAIXO`, `OK` | Severity. Maps to CDS Hooks `indicator`: critical→urgent, alto→warning, medio→info |
| 2 | `acaoRequerida` | string | free text | Single imperative sentence. What the clinician must do. Evidence-referenced. |
| 3 | `justificativa` | string | free text | Citation: trial name, guideline, or pharmacological mechanism. Machine-parseable when prefixed with `[REF]`. |

**Removed from legacy:** `urgencia` (redundant with `nivelAlerta`), `classificacao`, `tendencia` (derived downstream, not DMN's job).

**Hit policy:** `FIRST` (most severe match wins).

---

### CLINICAL_SCORE (3 outputs)

Answers: _"What is the patient's calculated risk score and tier?"_

| # | Name | Type | Values | Semantics |
|---|---|---|---|---|
| 1 | `pontuacao` | number | 0–N | Raw numeric score (NEWS2, qSOFA, Braden, MEWS, etc.) |
| 2 | `classificacao` | string | `CRITICO`, `ALTO`, `MEDIO`, `BAIXO` | Risk tier derived from score thresholds |
| 3 | `conduta` | string | free text | Protocol-defined response for this tier |

**Hit policy:** `COLLECT SUM` (C+) for additive scoring, `FIRST` for threshold classification.

**Note:** Scoring tables often use a two-table DRD: Table 1 (C+ sum) calculates raw score → Table 2 (F first) classifies tier + action.

---

### ADMIN_ADJUDICATION (3 outputs)

Answers: _"Should this administrative/financial request proceed?"_

| # | Name | Type | Values | Semantics |
|---|---|---|---|---|
| 1 | `resultado` | string | `PROSSEGUIR`, `BLOQUEAR`, `REVISAR` | Verdict. Three-state only. No ambiguity. |
| 2 | `acao` | string | free text | What must happen next: specific document to attach, deadline, escalation path |
| 3 | `risco` | string | `CRITICO`, `ALTO`, `MEDIO`, `BAIXO` | Financial/compliance risk if rule is ignored |

**Removed from legacy:**
- `observacao` (merged into `acao` — observation without action is waste)
- `alertasConformidade` (redundant — the rule _is_ the conformity check; its ID is the alert code)
- `alertasDesperdicio` (same: waste detection is inherent in the rule match, not a separate output)
- `riscoDenial` renamed to `risco` (denial is one type; risk is universal)
- `resultado` values simplified: `Aprovado/Reprovado/Pendente` → `PROSSEGUIR/BLOQUEAR/REVISAR` (unambiguous imperative verbs, not judgment adjectives)

**Hit policy:** `FIRST` (blocking rules evaluated before approval).

---

### OPERATIONAL_ROUTING (3 outputs)

Answers: _"Where should this go, with what priority?"_

| # | Name | Type | Values | Semantics |
|---|---|---|---|---|
| 1 | `destino` | string | context-dependent | Target: room, queue, team, channel, provider |
| 2 | `prioridade` | number | 1–5 | 1 = highest. Used by scheduler/dispatcher |
| 3 | `restricao` | string | free text | Constraint or reason: equipment needed, time window, exclusion |

**Hit policy:** `FIRST` or `COLLECT` (when multiple destinations apply).

---

## Naming Convention

```
{DOMAIN}-{CATEGORY}-{SEQ}
```

- DOMAIN: 3-letter domain code (DDI, EWS, LAB, BIL, AUT, GLS, etc.)
- CATEGORY: subcategory (BLEED, NEPHRO, OPME, PREAUTH, etc.)
- SEQ: 3-digit zero-padded sequence

Examples: `DDI-NEPHRO-010`, `BIL-OPME-003`, `AUT-PREAUTH-007`, `EWS-NEWS-001`

---

## Anti-Patterns (Do Not)

| Anti-Pattern | Why It's Wrong | Fix |
|---|---|---|
| Output column nobody reads | Waste. Violates lean principle. | Delete it. |
| Free-text in all 5 outputs | Unstructured data can't drive automation. | Use enums. One free-text max. |
| `resultado` = "Pendente" with no `acao` | Caller doesn't know what to do next. | Always pair verdict with action. |
| Same rule logic in worker AND DMN | Separation of concerns violation (ADR-003). | DMN is source of truth for rules. |
| Mixing clinical + financial outputs | Archetype confusion. | Decompose into two tables. |
| `urgencia` + `nivelAlerta` + `severidade` | Redundant severity axes. | One severity enum. Period. |
| Comments longer than the rule | Template bloat. | Cite reference. Don't explain science. |

---

## Migration Path from Legacy

| Legacy Schema | Target Template | Key Changes |
|---|---|---|
| 4-output clinical (nivelAlerta, urgencia, acaoRequerida, justificativaCientifica) | `CLINICAL_ALERT` | Drop `urgencia` (redundant) |
| 6-output lab (adds classificacao, tendencia) | `CLINICAL_ALERT` | Drop `classificacao` + `tendencia` (derived downstream) |
| 5-output admin (resultado, observacao, acaoRecomendada, alertasConformidade, riscoDenial) | `ADMIN_ADJUDICATION` | Merge observacao→acao, drop alertas, rename riscoDenial→risco, remap resultado values |
| 5-output LEAN TIER-2 (resultado, observacao, fundamentacao, alertasDesperdicio, acaoRecomendada) | `ADMIN_ADJUDICATION` | Merge fundamentacao→acao, drop alertas, remap resultado |
| Bespoke surgical/communication | `OPERATIONAL_ROUTING` | Map to destino/prioridade/restricao |
| Scoring (C+ sum) | `CLINICAL_SCORE` | Standardize output names |
