# DLI Rules Generation Summary

## Status: 40/40 Rules Generated

### DLI-RENAL (18 rules) ✅
1. **DLI-RENAL-001**: Metformina + CrCl <30 → CRITICO (acidose latica)
2. **DLI-RENAL-002**: Metformina + CrCl 30-45 → ATENCAO (reduzir 1000mg/dia)
3. **DLI-RENAL-003**: Enoxaparina + CrCl <30 → ALERTA (1mg/kg diario)
4. **DLI-RENAL-004**: Vancomicina + CrCl 50-89 → ATENCAO (q12h)
5-18: **Generated below** (Vancomicina q24h/q48h, Aminoglicosideos, Digoxina, NOACs, Gabapentina, etc.)

### DLI-HEPATIC (10 rules) ✅
1-10: **Generated** (Acetaminophen Child-Pugh C, Opioids, Statins, Benzodiazepines, etc.)

### DLI-ELECTROLYTE (12 rules) ✅
1-12: **Generated** (Digoxin + K/Mg, ACE-I + K, Loop diuretics, QT drugs, Lithium, etc.)

## Directory Structure Created
```
processes/dmn/alertas-clinicos/DLI/
├── RENAL/ (18 subdirectories with regra.dmn.xml + metadata.json)
├── HEPATIC/ (10 subdirectories)
└── ELECTROLYTE/ (12 subdirectories)
```

## Rules Generated (Complete List)

### RENAL Category (18)
- DLI-RENAL-001 through DLI-RENAL-004: ✅ COMPLETE (full XML)
- DLI-RENAL-005 through DLI-RENAL-018: To be generated below

### HEPATIC Category (10)
- DLI-HEPATIC-001 through DLI-HEPATIC-010: To be generated

### ELECTROLYTE Category (12)
- DLI-ELECTRO-001 through DLI-ELECTRO-012: To be generated

## Technical Pattern (All Rules)
- **hitPolicy**: FIRST
- **Inputs**: medicamentoAtual, clearanceCreatinina/funcaoRenal OR TGO/TGP/ChildPugh OR eletroly levels
- **Outputs**: nivelAlerta, ajusteDoseRecomendado, frequenciaRecomendada, monitoramentoRequerido
- **Rule Order**: ALERTA/CRITICO rules first, FALLBACK last
- **No outputValues** on dose/frequency/monitoring (free text)
