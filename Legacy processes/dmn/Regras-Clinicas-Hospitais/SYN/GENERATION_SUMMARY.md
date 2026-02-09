# Syndrome Detection Rules - Generation Summary

## Total Rules Generated: 25

### SYN-SEPSIS (8 rules) - Sepsis Detection
✅ SYN-SEPSIS-001: qSOFA >= 2 + suspected infection → Alerta (sepsis)
✅ SYN-SEPSIS-002: SIRS >= 2 + lactate >= 4 → Alerta (severe sepsis)
🔄 SYN-SEPSIS-003: Septic shock criteria → Alerta (lactate >2 + vasopressor)
🔄 SYN-SEPSIS-004: qSOFA = 1 + fever + tachycardia → Atencao
🔄 SYN-SEPSIS-005: SIRS >= 2 without lactate → Atencao (order lactate)
🔄 SYN-SEPSIS-006: Positive procalcitonin + vitals changes → Atencao
🔄 SYN-SEPSIS-007: qSOFA = 0, no infection markers → OK
🔄 SYN-SEPSIS-008: Fallback - insufficient data → Revisar

### SYN-AKI (6 rules) - Acute Kidney Injury (KDIGO)
🔄 SYN-AKI-001: Stage 3 AKI (Cr >= 3x or >= 4.0 or anuria) → Alerta
🔄 SYN-AKI-002: Stage 2 AKI (Cr 2-2.9x baseline) → Alerta
🔄 SYN-AKI-003: Stage 1 AKI (Cr 1.5-1.9x or +0.3) → Atencao
🔄 SYN-AKI-004: Urine output <0.5 mL/kg/h x12h → Atencao
🔄 SYN-AKI-005: Creatinine rising trend + nephrotoxic drug → Atencao
🔄 SYN-AKI-006: Normal creatinine and urine output → OK

### SYN-VTE (5 rules) - VTE/PE Detection
🔄 SYN-VTE-001: Wells PE score high + hypoxia → Alerta
🔄 SYN-VTE-002: D-dimer elevated + clinical suspicion → Atencao
🔄 SYN-VTE-003: DVT confirmed + respiratory symptoms → Alerta
🔄 SYN-VTE-004: Immobilized + risk factors → Atencao (VTE prophylaxis)
🔄 SYN-VTE-005: Low risk → OK

### SYN-MI (4 rules) - Acute MI Detection
🔄 SYN-MI-001: Troponin elevated + dynamic + chest pain → Alerta
🔄 SYN-MI-002: Troponin elevated + ECG changes → Alerta
🔄 SYN-MI-003: Troponin borderline + symptoms → Atencao
🔄 SYN-MI-004: Troponin negative, no symptoms → OK

### SYN-DKA (2 rules) - DKA/HHS Detection
🔄 SYN-DKA-001: Glucose >250 + ketones + acidosis → Alerta (DKA)
🔄 SYN-DKA-002: Glucose >600 + hyperosmolarity → Alerta (HHS)

## Status Legend
✅ Complete with DMN + metadata
🔄 Pending generation

## Next Steps
Continuing with remaining 23 rules...
