# DMN Migration Manifest - Quick Reference Card

## File Location
```
docs/Migration/migration_manifest.json (537.8 KB, 667 entries)
```

## Quick Stats

| Metric | Value |
|--------|-------|
| **Total Rules** | 667 |
| **Admin Rules** | 369 (55.3%) |
| **Clinical Rules** | 267 (40.0%) |
| **Federated** | 6 (0.9%) |
| **Cross-Cutting** | 3 (0.4%) |
| **Infrastructure** | 22 (3.3%) |

## Priority Breakdown

```
CRITICAL: ████████████████████████████ 308 (46.2%)
HIGH:     ████████████████████████████ 295 (44.2%)
MEDIUM:   ███                           40 (6.0%)
LOW:      █                             24 (3.6%)
```

## Phase Distribution

| Phase | Rules | Duration | Focus |
|-------|-------|----------|-------|
| **Phase 8** | 397 | 4 weeks | Clinical Safety + Critical Auth |
| **Phase 9** | 206 | 4 weeks | Revenue Cycle Operations |
| **Phase 10** | 64 | 4 weeks | Support Services |

## Top Categories

```
1. clinical_safety     268  ████████████████████████████
2. authorization        68  ███████
3. revenue_recovery     67  ███████
4. billing             63  ██████
5. glosa_prevention    62  ██████
```

## Key jq Queries

### Get all CRITICAL rules
```bash
jq '.entries[] | select(.priority == "CRITICAL") | {rule_id, category, business_value}' migration_manifest.json
```

### Get Phase 8 rules
```bash
jq '.entries[] | select(.phase == 8)' migration_manifest.json
```

### Get clinical safety DDI rules
```bash
jq '.entries[] | select(.category == "clinical_safety" and (.subcategory | contains("ddi")))' migration_manifest.json
```

### Count by category
```bash
jq '.summary.by_category' migration_manifest.json
```

### Find specific rule
```bash
jq '.entries[] | select(.rule_id == "APPEAL-ELIG-001")' migration_manifest.json
```

### Get rules with revenue impact
```bash
jq '.entries[] | select(.business_value | contains("R$"))' migration_manifest.json
```

### List all ANS-regulated rules
```bash
jq '.entries[] | select(.regulatory_references[] | contains("ANS"))' migration_manifest.json
```

### Get Week 1 Phase 8 rules
```bash
jq '.entries[] | select(.phase == 8 and .week == 1)' migration_manifest.json
```

### Export to CSV (basic)
```bash
jq -r '.entries[] | [.rule_id, .category, .priority, .phase, .business_value] | @csv' migration_manifest.json > migration_plan.csv
```

### Get migration status summary
```bash
jq '.entries | group_by(.migration_status) | map({status: .[0].migration_status, count: length})' migration_manifest.json
```

## Business Value Summary

| Category | Annual Impact |
|----------|---------------|
| Denial Prevention | R$ 27M |
| Revenue Recovery | R$ 9.5M |
| Billing Accuracy | R$ 8M |
| Coding Accuracy | R$ 5M |
| Pricing Optimization | R$ 4M |
| Cash Flow | R$ 3M |
| **TOTAL** | **R$ 56.5M** |

## Clinical Safety Coverage

| Alert Type | Rules | Priority |
|-----------|-------|----------|
| Drug-Drug Interactions (DDI) | 50 | CRITICAL |
| Early Warning Scores (EWS) | 25 | CRITICAL |
| Critical Lab Values (LAB) | 29 | CRITICAL |
| Clinical Syndromes (SYN) | 22 | CRITICAL |
| Drug-Lab Interactions (DLI) | 40 | HIGH |
| Disease-Drug Contraindications (DDX) | 35 | CRITICAL |
| Medication Safety (MED) | 25 | HIGH |
| Risk Assessment (RSK) | 20 | HIGH |
| Vital Signs (VIT) | 21 | CRITICAL |

## Regulatory Coverage

| Regulation | Rules | Scope |
|-----------|-------|-------|
| ANS RN 465/2021 | 376 | Operations |
| ANVISA RDC 36/2013 | 324 | Clinical Safety |
| CFM 2.217/2018 | 267 | Medical Ethics |
| ANVISA RDC 63/2011 | 267 | Drug Safety |
| ANS RN 259/2011 | 130 | Authorization |
| LGPD Lei 13.709/2018 | 56 | Data Protection |

## Migration Workflow

1. **Query manifest** for next batch
2. **Read legacy DMN** file
3. **Convert to CIB7 worker** (Python/TypeScript)
4. **Implement business logic**
5. **Write tests** (unit + integration)
6. **Deploy to platform**
7. **Update manifest** status to "complete"
8. **Validate** in production

## Manifest Schema

```json
{
  "legacy_path": "Legacy processes/dmn/.../regra.dmn.xml",
  "new_path": "platform/dmn/{category}/{subcategory}/{rule_id}.dmn",
  "category": "clinical_safety|authorization|billing|...",
  "subcategory": "ddi/qt|auth/preauth|...",
  "priority": "CRITICAL|HIGH|MEDIUM|LOW",
  "business_value": "R$ amount or description",
  "medical_validation": "complete|pending|n/a",
  "regulatory_references": ["ANS RN X", "ANVISA RDC Y"],
  "phase": 8|9|10,
  "week": 1-4,
  "migration_status": "pending|in-progress|complete|blocked|deferred",
  "notes": "Additional context",
  "rule_id": "CATEGORY-SUBCAT-###",
  "rule_name": "Human-readable name",
  "hit_policy": "FIRST|COLLECT|...",
  "inputs": 0-10,
  "outputs": 5
}
```

## Update Migration Status

```bash
# Mark rule as in-progress
jq '(.entries[] | select(.rule_id == "DDI-QT-001") | .migration_status) = "in-progress"' migration_manifest.json > temp.json && mv temp.json migration_manifest.json

# Mark rule as complete
jq '(.entries[] | select(.rule_id == "DDI-QT-001") | .migration_status) = "complete"' migration_manifest.json > temp.json && mv temp.json migration_manifest.json
```

## Python Access

```python
import json

# Load manifest
with open('docs/Migration/migration_manifest.json') as f:
    manifest = json.load(f)

# Get Phase 8 Week 1 CRITICAL rules
phase8_week1_critical = [
    entry for entry in manifest['entries']
    if entry['phase'] == 8
    and entry['week'] == 1
    and entry['priority'] == 'CRITICAL'
]

# Get all DDI rules
ddi_rules = [
    entry for entry in manifest['entries']
    if 'ddi' in entry['subcategory'].lower()
]

# Get next pending rule
next_rule = next(
    (e for e in manifest['entries'] if e['migration_status'] == 'pending'),
    None
)
```

## Related Documentation

- **Full Summary:** `MANIFEST_SUMMARY.md`
- **Migration Strategy:** `LEGACY_DMN_MIGRATION_STRATEGY.md`
- **Category Mapping:** `DMN_CATEGORY_MAPPING.md`
- **Worker Template:** `CIB7_WORKER_TEMPLATE.md`
- **Quick Start:** `QUICK_START_GUIDE.md`

## Validation Status

✓ All 667 entries validated
✓ All required fields present
✓ All categories mapped correctly
✓ All priorities assigned
✓ All phases scheduled
✓ All regulatory references included
✓ Production ready

---

**Last Updated:** 2026-02-09
**Manifest Version:** 1.0.0
**Status:** PRODUCTION READY
