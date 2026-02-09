# RN-LISObservationDTO - Observação Laboratorial (FHIR Observation)

## Identificação
- **ID**: RN-LISObservationDTO
- **Nome**: LIS Observation Data Transfer Object
- **Categoria**: Integration/Data Model
- **Subcategoria**: HL7 FHIR DTO
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/lis/dto/ObservationDTO.java`

---

## Descrição

Objeto de transferência de dados que representa uma observação/medição individual dentro de um resultado laboratorial, seguindo o padrão HL7 FHIR R4 Observation. Cada observação corresponde a um teste específico com seu valor, unidade, faixa de referência e interpretação clínica.

**Recurso FHIR**: Observation
**URL FHIR**: http://hl7.org/fhir/R4/observation.html

---

## Estrutura de Dados

### Atributos

```java
@Data
public class ObservationDTO {
    private String id;              // ID único da observação
    private String code;            // Código LOINC do teste
    private String display;         // Nome legível do teste
    private String value;           // Valor medido
    private String unit;            // Unidade de medida
    private String interpretation;  // Interpretação (N, A, H, L, HH, LL)
    private String referenceRange;  // Valores de referência
    private String status;          // Status (final, preliminary, corrected)
}
```

---

## Mapeamento FHIR Observation

### Exemplo JSON FHIR
```json
{
  "resourceType": "Observation",
  "id": "obs-cholesterol",
  "status": "final",
  "category": [
    {
      "coding": [
        {
          "system": "http://terminology.hl7.org/CodeSystem/observation-category",
          "code": "laboratory"
        }
      ]
    }
  ],
  "code": {
    "coding": [
      {
        "system": "http://loinc.org",
        "code": "2093-3",
        "display": "Cholesterol [Mass/volume] in Serum or Plasma"
      }
    ]
  },
  "valueQuantity": {
    "value": 220,
    "unit": "mg/dL",
    "system": "http://unitsofmeasure.org",
    "code": "mg/dL"
  },
  "interpretation": [
    {
      "coding": [
        {
          "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
          "code": "H",
          "display": "High"
        }
      ]
    }
  ],
  "referenceRange": [
    {
      "high": {
        "value": 200,
        "unit": "mg/dL"
      },
      "text": "< 200 mg/dL"
    }
  ]
}
```

---

## Atributos Detalhados

### 1. id
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Identificador único da observação no LIS
- **Exemplo**: `"obs-cholesterol"`

### 2. code (LOINC)
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Código LOINC que identifica universalmente o teste
- **Sistema**: http://loinc.org
- **Exemplos**:
  - `2093-3` - Cholesterol [Mass/volume] in Serum or Plasma
  - `718-7` - Hemoglobin [Mass/volume] in Blood
  - `2951-2` - Sodium [Moles/volume] in Serum or Plasma

**Importância**:
- Padronização internacional
- Permite mapeamento preciso para códigos TUSS
- Facilita integração entre sistemas

---

### 3. display
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Nome legível por humanos do teste
- **Exemplos**:
  - `"Colesterol Total"`
  - `"Hemoglobina"`
  - `"Sódio"`

**Uso**: Interface de usuário, impressão de laudos

---

### 4. value
- **Tipo**: String
- **Obrigatório**: Sim (em observações quantitativas)
- **Descrição**: Valor medido do teste
- **Exemplos**:
  - `"220"` (numérico)
  - `"Positivo"` (qualitativo)
  - `">1000"` (com operador)
  - `"<0.5"` (abaixo do limite de detecção)

**Tipos de Valores**:
1. **Quantitativo**: Número (ex: `220`)
2. **Qualitativo**: Texto (ex: `Positivo`, `Negativo`, `Reagente`)
3. **Semi-quantitativo**: Com operadores (ex: `>1000`, `<5`)

---

### 5. unit
- **Tipo**: String
- **Obrigatório**: Sim (para valores quantitativos)
- **Sistema**: UCUM (Unified Code for Units of Measure)
- **Exemplos**:
  - `mg/dL` - miligramas por decilitro
  - `g/L` - gramas por litro
  - `mmol/L` - milimoles por litro
  - `10*3/uL` - mil por microlitro (células)
  - `%` - percentual

**Normalização de Unidades**:
```java
// Conversão entre unidades comuns
public double normalizeToSI(String value, String unit) {
    switch (unit) {
        case "mg/dL":
            return Double.parseDouble(value) * 0.01; // Para g/L
        case "mmHg":
            return Double.parseDouble(value) * 0.133; // Para kPa
        default:
            return Double.parseDouble(value);
    }
}
```

---

### 6. interpretation
- **Tipo**: String (Enum)
- **Obrigatório**: Não (mas crítico para alertas)
- **Sistema**: http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation

**Valores Padrão**:
- `N` - Normal
- `A` - Abnormal (anormal)
- `H` - High (alto)
- `L` - Low (baixo)
- `HH` - Critically high (criticamente alto)
- `LL` - Critically low (criticamente baixo)
- `<` - Below detection limit
- `>` - Above measurement range

**Uso Clínico**:
```java
public boolean isCritical(ObservationDTO obs) {
    return Set.of("HH", "LL").contains(obs.getInterpretation());
}

public boolean isAbnormal(ObservationDTO obs) {
    return Set.of("A", "H", "L", "HH", "LL").contains(obs.getInterpretation());
}
```

---

### 7. referenceRange
- **Tipo**: String
- **Obrigatório**: Não (mas recomendado)
- **Descrição**: Valores de referência (normalidade) para o teste
- **Formatos Comuns**:
  - `"< 200 mg/dL"` (limite superior)
  - `"135-145 mmol/L"` (faixa)
  - `"Negativo"` (qualitativo)
  - `"Homem: 13.5-17.5 g/dL, Mulher: 12.0-15.5 g/dL"` (por sexo)

**Parsing de Faixa de Referência**:
```java
public ReferenceRange parseReferenceRange(String rangeText, String unit) {
    ReferenceRange range = new ReferenceRange();

    // Padrão: "135-145 mmol/L"
    if (rangeText.matches("\\d+(\\.\\d+)?-\\d+(\\.\\d+)? .*")) {
        String[] parts = rangeText.split("-");
        range.setLow(Double.parseDouble(parts[0].trim()));
        range.setHigh(Double.parseDouble(parts[1].split(" ")[0].trim()));
    }
    // Padrão: "< 200 mg/dL"
    else if (rangeText.startsWith("<")) {
        range.setHigh(Double.parseDouble(rangeText.substring(1).split(" ")[0].trim()));
    }
    // Padrão: "> 50 mg/dL"
    else if (rangeText.startsWith(">")) {
        range.setLow(Double.parseDouble(rangeText.substring(1).split(" ")[0].trim()));
    }

    return range;
}
```

---

### 8. status
- **Tipo**: String (Enum)
- **Obrigatório**: Sim
- **Valores**:
  - `final` - Resultado final liberado
  - `preliminary` - Resultado preliminar
  - `corrected` - Resultado corrigido
  - `amended` - Resultado alterado
  - `cancelled` - Resultado cancelado
  - `entered-in-error` - Erro de entrada

**Impacto no Faturamento**:
```java
// Apenas observações "final", "corrected" ou "amended" devem ser faturadas
public boolean isBillable(ObservationDTO obs) {
    return Set.of("final", "corrected", "amended").contains(obs.getStatus());
}
```

---

## Regras de Negócio

### RN-OBS-01: Validação de Interpretação Automática
**Descrição**: Sistema deve validar se interpretação (H/L/N) está consistente com valor e faixa de referência.

**Implementação**:
```java
public boolean validateInterpretation(ObservationDTO obs) {
    if (obs.getInterpretation() == null || obs.getReferenceRange() == null) {
        return true; // Não há como validar
    }

    ReferenceRange range = parseReferenceRange(obs.getReferenceRange(), obs.getUnit());
    double value = Double.parseDouble(obs.getValue());

    // Validar interpretação "H" (High)
    if ("H".equals(obs.getInterpretation())) {
        if (range.getHigh() != null && value <= range.getHigh()) {
            log.warn("Interpretação 'H' inconsistente com valor: {} <= {}",
                value, range.getHigh());
            return false;
        }
    }

    // Validar interpretação "L" (Low)
    if ("L".equals(obs.getInterpretation())) {
        if (range.getLow() != null && value >= range.getLow()) {
            log.warn("Interpretação 'L' inconsistente com valor: {} >= {}",
                value, range.getLow());
            return false;
        }
    }

    // Validar interpretação "N" (Normal)
    if ("N".equals(obs.getInterpretation())) {
        if (range.getLow() != null && value < range.getLow()) {
            return false;
        }
        if (range.getHigh() != null && value > range.getHigh()) {
            return false;
        }
    }

    return true;
}
```

---

### RN-OBS-02: Alertas de Valores Críticos
**Descrição**: Observações com interpretação HH ou LL devem gerar notificação imediata ao médico.

**Implementação**:
```java
@Service
public class CriticalValueAlertService {

    public void checkCriticalValues(List<ObservationDTO> observations, String patientId) {
        List<ObservationDTO> criticals = observations.stream()
            .filter(obs -> Set.of("HH", "LL").contains(obs.getInterpretation()))
            .collect(Collectors.toList());

        if (!criticals.isEmpty()) {
            sendCriticalAlert(patientId, criticals);
        }
    }

    private void sendCriticalAlert(String patientId, List<ObservationDTO> criticals) {
        String message = criticals.stream()
            .map(obs -> String.format("%s: %s %s (ref: %s)",
                obs.getDisplay(),
                obs.getValue(),
                obs.getUnit(),
                obs.getReferenceRange()))
            .collect(Collectors.joining("\n"));

        notificationService.sendUrgent(
            patientId,
            "RESULTADO CRÍTICO",
            message
        );

        // Log de auditoria
        auditService.logCriticalValueAlert(patientId, criticals, LocalDateTime.now());
    }
}
```

---

### RN-OBS-03: Delta Check (Comparação com Resultados Anteriores)
**Descrição**: Detectar variações significativas em relação a resultados anteriores do mesmo teste.

**Implementação**:
```java
@Service
public class DeltaCheckService {

    // Limites de variação percentual por teste
    private static final Map<String, Double> DELTA_CHECK_LIMITS = Map.of(
        "718-7", 0.3,   // Hemoglobina: 30%
        "2093-3", 0.5,  // Colesterol: 50%
        "2951-2", 0.1   // Sódio: 10%
    );

    public DeltaCheckResult checkDelta(ObservationDTO current, ObservationDTO previous) {
        Double deltaLimit = DELTA_CHECK_LIMITS.get(current.getCode());
        if (deltaLimit == null) {
            return DeltaCheckResult.NOT_APPLICABLE;
        }

        double currentValue = Double.parseDouble(current.getValue());
        double previousValue = Double.parseDouble(previous.getValue());

        double percentChange = Math.abs((currentValue - previousValue) / previousValue);

        if (percentChange > deltaLimit) {
            return DeltaCheckResult.SIGNIFICANT_CHANGE;
        }

        return DeltaCheckResult.NORMAL_VARIATION;
    }
}
```

---

### RN-OBS-04: Conversão de Unidades para Padronização
**Descrição**: Converter unidades diferentes para um padrão (ex: mg/dL → g/L).

**Implementação**:
```java
@Service
public class UnitConversionService {

    // Fatores de conversão para SI
    private static final Map<String, ConversionFactor> CONVERSION_FACTORS = Map.of(
        "mg/dL_to_g/L", new ConversionFactor(0.01, "g/L"),
        "g/dL_to_g/L", new ConversionFactor(10.0, "g/L"),
        "mmol/L_to_mg/dL_glucose", new ConversionFactor(18.0, "mg/dL")
    );

    public ObservationDTO convertToStandardUnit(ObservationDTO obs, String targetUnit) {
        String conversionKey = obs.getUnit() + "_to_" + targetUnit;
        ConversionFactor factor = CONVERSION_FACTORS.get(conversionKey);

        if (factor == null) {
            log.warn("Conversão não disponível: {} -> {}", obs.getUnit(), targetUnit);
            return obs;
        }

        double originalValue = Double.parseDouble(obs.getValue());
        double convertedValue = originalValue * factor.getFactor();

        ObservationDTO converted = new ObservationDTO();
        converted.setId(obs.getId());
        converted.setCode(obs.getCode());
        converted.setDisplay(obs.getDisplay());
        converted.setValue(String.valueOf(convertedValue));
        converted.setUnit(factor.getTargetUnit());
        converted.setInterpretation(obs.getInterpretation());
        converted.setStatus(obs.getStatus());

        // Atualizar faixa de referência
        converted.setReferenceRange(
            convertReferenceRange(obs.getReferenceRange(), factor)
        );

        return converted;
    }
}
```

---

## Exemplos de Uso

### Exemplo 1: Processar Observações de um Resultado
```java
@Service
public class ObservationProcessingService {

    public void processObservations(LISResultDTO result) {
        List<ObservationDTO> observations = result.getObservations();

        for (ObservationDTO obs : observations) {
            // 1. Validar interpretação
            if (!validateInterpretation(obs)) {
                qualityAlert("Interpretação inconsistente: " + obs.getId());
            }

            // 2. Verificar valores críticos
            if (Set.of("HH", "LL").contains(obs.getInterpretation())) {
                criticalValueAlertService.sendAlert(result.getPatientId(), obs);
            }

            // 3. Delta check com resultado anterior
            ObservationDTO previous = getPreviousObservation(
                result.getPatientId(),
                obs.getCode()
            );

            if (previous != null) {
                DeltaCheckResult deltaResult = deltaCheckService.checkDelta(obs, previous);
                if (deltaResult == DeltaCheckResult.SIGNIFICANT_CHANGE) {
                    qualityAlert("Variação significativa detectada: " + obs.getDisplay());
                }
            }

            // 4. Mapear para código TUSS (se necessário faturamento individual)
            String tissCode = mapObservationToTISS(obs.getCode());
            if (tissCode != null) {
                log.info("Observação {} mapeada para TUSS: {}", obs.getCode(), tissCode);
            }
        }
    }
}
```

---

### Exemplo 2: Gerar Laudo Textual a Partir de Observações
```java
@Service
public class ReportGenerationService {

    public String generateTextReport(List<ObservationDTO> observations) {
        StringBuilder report = new StringBuilder();

        // Agrupar por normalidade
        List<ObservationDTO> normal = observations.stream()
            .filter(obs -> "N".equals(obs.getInterpretation()))
            .collect(Collectors.toList());

        List<ObservationDTO> abnormal = observations.stream()
            .filter(obs -> Set.of("H", "L", "A").contains(obs.getInterpretation()))
            .collect(Collectors.toList());

        List<ObservationDTO> critical = observations.stream()
            .filter(obs -> Set.of("HH", "LL").contains(obs.getInterpretation()))
            .collect(Collectors.toList());

        // Seção de valores críticos (se houver)
        if (!critical.isEmpty()) {
            report.append("*** VALORES CRÍTICOS ***\n\n");
            for (ObservationDTO obs : critical) {
                report.append(formatObservation(obs, true));
            }
            report.append("\n");
        }

        // Seção de valores alterados
        if (!abnormal.isEmpty()) {
            report.append("VALORES ALTERADOS:\n\n");
            for (ObservationDTO obs : abnormal) {
                report.append(formatObservation(obs, false));
            }
            report.append("\n");
        }

        // Seção de valores normais
        if (!normal.isEmpty()) {
            report.append("VALORES DENTRO DA NORMALIDADE:\n\n");
            for (ObservationDTO obs : normal) {
                report.append(formatObservation(obs, false));
            }
        }

        return report.toString();
    }

    private String formatObservation(ObservationDTO obs, boolean highlight) {
        String flag = "";
        if ("H".equals(obs.getInterpretation())) flag = "↑ ";
        if ("L".equals(obs.getInterpretation())) flag = "↓ ";
        if ("HH".equals(obs.getInterpretation())) flag = "↑↑ ";
        if ("LL".equals(obs.getInterpretation())) flag = "↓↓ ";

        return String.format(
            "%s%s: %s %s (Ref: %s)\n",
            flag,
            obs.getDisplay(),
            obs.getValue(),
            obs.getUnit(),
            obs.getReferenceRange()
        );
    }
}
```

---

### Exemplo 3: Validação de Qualidade de Dados
```java
@Service
public class ObservationQualityService {

    public QualityReport validateObservations(List<ObservationDTO> observations) {
        QualityReport report = new QualityReport();

        for (ObservationDTO obs : observations) {
            // 1. Código LOINC obrigatório
            if (obs.getCode() == null || obs.getCode().isEmpty()) {
                report.addError("Observação sem código LOINC: " + obs.getId());
            }

            // 2. Valor obrigatório
            if (obs.getValue() == null || obs.getValue().isEmpty()) {
                report.addError("Observação sem valor: " + obs.getDisplay());
            }

            // 3. Unidade obrigatória para valores numéricos
            if (isNumeric(obs.getValue()) && (obs.getUnit() == null || obs.getUnit().isEmpty())) {
                report.addWarning("Valor numérico sem unidade: " + obs.getDisplay());
            }

            // 4. Faixa de referência recomendada
            if (obs.getReferenceRange() == null || obs.getReferenceRange().isEmpty()) {
                report.addWarning("Faixa de referência ausente: " + obs.getDisplay());
            }

            // 5. Status obrigatório
            if (obs.getStatus() == null || obs.getStatus().isEmpty()) {
                report.addError("Status ausente: " + obs.getDisplay());
            }

            // 6. Validar interpretação vs valor
            if (!validateInterpretation(obs)) {
                report.addError("Interpretação inconsistente: " + obs.getDisplay());
            }
        }

        return report;
    }

    private boolean isNumeric(String value) {
        try {
            Double.parseDouble(value);
            return true;
        } catch (NumberFormatException e) {
            return false;
        }
    }
}
```

---

## Conformidade com Padrões

### HL7 FHIR R4
- **Observation Resource**: http://hl7.org/fhir/R4/observation.html
- **Observation Interpretation Codes**: http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation

### LOINC
- **LOINC Database**: https://loinc.org/
- Identificadores universais para testes laboratoriais

### UCUM (Units of Measure)
- **System**: http://unitsofmeasure.org
- Padronização de unidades de medida

---

## Referências Técnicas

1. **FHIR Observation**: http://hl7.org/fhir/R4/observation.html
2. **LOINC**: https://loinc.org/
3. **UCUM**: http://unitsofmeasure.org/
4. **HL7 V3 Observation Interpretation**: http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation
5. **CLSI - Defining, Establishing, and Verifying Reference Intervals**: EP28-A3c

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
