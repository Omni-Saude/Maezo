# RN-PACSSeriesDTO - Série de Imagens (FHIR ImagingSeries)

## Identificação
- **ID**: RN-PACSSeriesDTO
- **Nome**: PACS Series Data Transfer Object
- **Categoria**: Integration/Data Model
- **Subcategoria**: HL7 FHIR DTO + DICOM
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/pacs/dto/PACSSeriesDTO.java`

---

## Descrição

Objeto de transferência de dados que representa uma série de imagens dentro de um estudo DICOM. Uma série é um conjunto de imagens adquiridas com os mesmos parâmetros técnicos em uma única sequência de aquisição (ex: série axial pré-contraste, série coronal pós-contraste).

**Padrão**: DICOM + HL7 FHIR R4 ImagingStudy.series

---

## Estrutura de Dados

### Atributos

```java
@Data
public class PACSSeriesDTO {
    private String uid;                  // Series Instance UID (DICOM)
    private Integer number;              // Número sequencial da série
    private String modality;             // Modalidade DICOM (CT, MR, XR, etc.)
    private String description;          // Descrição da série
    private LocalDateTime started;       // Data/hora início da aquisição
    private Integer numberOfInstances;   // Número de imagens na série
    private String bodysite;             // Local anatômico (SNOMED CT)
    private String laterality;           // Lateralidade (LEFT, RIGHT, BILATERAL)
}
```

---

## Mapeamento FHIR ImagingStudy.series

### Exemplo JSON FHIR
```json
{
  "series": [
    {
      "uid": "1.2.840.113619.2.55.3.1234567890.123.1",
      "number": 1,
      "modality": {
        "system": "http://dicom.nema.org/resources/ontology/DCM",
        "code": "CT"
      },
      "description": "Axial pre-contrast",
      "started": "2024-01-15T10:05:00Z",
      "numberOfInstances": 80,
      "bodySite": {
        "system": "http://snomed.info/sct",
        "code": "818983003",
        "display": "Abdomen"
      },
      "laterality": {
        "system": "http://snomed.info/sct",
        "code": "51440002",
        "display": "Right and left"
      }
    },
    {
      "uid": "1.2.840.113619.2.55.3.1234567890.123.2",
      "number": 2,
      "modality": {
        "system": "http://dicom.nema.org/resources/ontology/DCM",
        "code": "CT"
      },
      "description": "Axial post-contrast arterial phase",
      "started": "2024-01-15T10:10:00Z",
      "numberOfInstances": 85,
      "bodySite": {
        "system": "http://snomed.info/sct",
        "code": "818983003",
        "display": "Abdomen"
      }
    }
  ]
}
```

---

## Atributos Detalhados

### 1. uid (Series Instance UID)
- **Tipo**: String (DICOM UID)
- **Obrigatório**: Sim
- **Descrição**: Identificador único global da série no padrão DICOM
- **Formato**: OID (Object Identifier)
- **Exemplo**: `"1.2.840.113619.2.55.3.1234567890.123.1"`

**Estrutura**:
```
1.2.840.113619.2.55.3.1234567890.123    - Study UID
                                    .1   - Series number
```

**Uso**:
- Identificação única global da série
- Query DICOM para recuperar imagens específicas
- Rastreamento entre sistemas PACS

---

### 2. number
- **Tipo**: Integer
- **Obrigatório**: Sim
- **Descrição**: Número sequencial da série dentro do estudo
- **Exemplo**: `1, 2, 3, ...`

**Uso**:
- Ordenação das séries
- Identificação humanizada (ex: "Série 1", "Série 2")

---

### 3. modality
- **Tipo**: String (DICOM Modality)
- **Obrigatório**: Sim
- **Sistema**: http://dicom.nema.org/resources/ontology/DCM

**Valores Comuns**:
- `CT` - Computed Tomography
- `MR` - Magnetic Resonance
- `XR` - X-Ray
- `US` - Ultrasound
- `CR` - Computed Radiography
- `DX` - Digital Radiography

**Uso**:
- Validação de protocolo
- Mapeamento para códigos TUSS

---

### 4. description
- **Tipo**: String
- **Obrigatório**: Não (mas recomendado)
- **Descrição**: Descrição técnica da série
- **Exemplos**:
  - `"Axial pre-contrast"`
  - `"Axial post-contrast arterial phase"`
  - `"Coronal reformation"`
  - `"Sagittal T1"`
  - `"Axial T2 FLAIR"`

**Padrões de Descrição**:
```java
// CT
"Axial pre-contrast"
"Axial post-contrast arterial phase"
"Axial post-contrast venous phase"
"Axial post-contrast delayed phase"
"Coronal reformation"
"Sagittal reformation"

// MR
"Axial T1"
"Axial T2"
"Axial T2 FLAIR"
"Sagittal T1"
"Coronal T2"
"Axial DWI (Diffusion Weighted Imaging)"
```

**Uso**:
- Identificação de fases de contraste
- Faturamento de séries adicionais
- Validação de protocolo

---

### 5. started
- **Tipo**: LocalDateTime
- **Obrigatório**: Não
- **Descrição**: Data/hora de início da aquisição da série
- **Formato ISO**: `2024-01-15T10:05:00`

**Uso**:
- Ordenação temporal das séries
- Cálculo de tempo de exame
- Validação de protocolo (intervalo entre fases)

---

### 6. numberOfInstances
- **Tipo**: Integer
- **Obrigatório**: Sim
- **Descrição**: Número de imagens (instâncias DICOM) na série
- **Exemplo**: `80, 85, 100, ...`

**Validação**:
```java
// Séries axiais de CT geralmente têm 50-150 imagens
if ("CT".equals(series.getModality()) && series.getNumberOfInstances() < 30) {
    qualityAlert("Série CT com poucas imagens: " + series.getNumberOfInstances());
}

// Radiografias geralmente têm 1-2 imagens
if ("XR".equals(series.getModality()) && series.getNumberOfInstances() > 4) {
    qualityAlert("Série XR com muitas imagens: " + series.getNumberOfInstances());
}
```

---

### 7. bodysite
- **Tipo**: String (SNOMED CT)
- **Obrigatório**: Não
- **Sistema**: http://snomed.info/sct

**Exemplos**:
| Código | Descrição |
|--------|-----------|
| 818983003 | Abdomen |
| 51185008 | Thorax |
| 69536005 | Head |
| 416550000 | Anterior chest wall |
| 244007 | Knee |
| 734000 | Hand |

**Uso**:
- Mapeamento para códigos TUSS por região anatômica
- Validação de protocolo

---

### 8. laterality
- **Tipo**: String (Enum)
- **Obrigatório**: Não (mas crítico para alguns exames)
- **Sistema**: http://snomed.info/sct

**Valores**:
| Código | Descrição | Uso |
|--------|-----------|-----|
| 7771000 | LEFT | Lado esquerdo |
| 24028007 | RIGHT | Lado direito |
| 51440002 | Right and left | Bilateral |

**Importância Crítica**:
```java
// RN-PACSSERIES-01: Lateralidade obrigatória para membros
private static final Set<String> REQUIRES_LATERALITY = Set.of(
    "244007",  // Knee
    "734000",  // Hand
    "40983000", // Arm
    "61685007", // Leg
    "85562004"  // Hip
);

public void validateLaterality(PACSSeriesDTO series) {
    if (REQUIRES_LATERALITY.contains(series.getBodysite())) {
        if (series.getLaterality() == null || series.getLaterality().isEmpty()) {
            throw new ValidationException(
                "Lateralidade obrigatória para " + series.getBodysite()
            );
        }
    }
}
```

---

## Regras de Negócio

### RN-PACSSERIES-01: Identificação de Fases de Contraste
**Descrição**: Identificar séries realizadas em diferentes fases após administração de contraste.

**Implementação**:
```java
public enum ContrastPhase {
    PRE_CONTRAST("pre-contrast", "sem contraste"),
    ARTERIAL("arterial", "fase arterial"),
    VENOUS("venous", "portal", "venosa", "fase venosa"),
    DELAYED("delayed", "tardia", "fase tardia"),
    EQUILIBRIUM("equilibrium", "equilíbrio");

    private final String[] keywords;

    ContrastPhase(String... keywords) {
        this.keywords = keywords;
    }

    public static Optional<ContrastPhase> detectPhase(String description) {
        String desc = description.toLowerCase();

        for (ContrastPhase phase : values()) {
            for (String keyword : phase.keywords) {
                if (desc.contains(keyword)) {
                    return Optional.of(phase);
                }
            }
        }

        return Optional.empty();
    }
}
```

---

### RN-PACSSERIES-02: Séries Adicionais Cobráveis
**Descrição**: Determinar se séries adicionais geram cobrança extra.

**Implementação**:
```java
@Service
public class AdditionalSeriesBillingService {

    public boolean isAdditionalSeriesBillable(PACSSeriesDTO series, List<PACSSeriesDTO> allSeries) {
        // Séries de reformatação não são cobradas separadamente
        if (isReformattedSeries(series)) {
            return false;
        }

        // Séries em diferentes fases de contraste podem ser cobráveis
        Optional<ContrastPhase> phase = ContrastPhase.detectPhase(series.getDescription());
        if (phase.isPresent()) {
            // Verificar se é fase adicional além da básica
            boolean hasBasicPhase = allSeries.stream()
                .anyMatch(s -> ContrastPhase.detectPhase(s.getDescription())
                    .map(p -> p == ContrastPhase.VENOUS)
                    .orElse(false));

            // Se já tem fase venosa (padrão), outras fases podem ser cobráveis
            return hasBasicPhase && phase.get() != ContrastPhase.VENOUS;
        }

        return false;
    }

    private boolean isReformattedSeries(PACSSeriesDTO series) {
        String desc = series.getDescription().toLowerCase();
        return desc.contains("reformation") ||
               desc.contains("reformat") ||
               desc.contains("mip") ||        // Maximum Intensity Projection
               desc.contains("mpr") ||        // Multiplanar Reformation
               desc.contains("3d");
    }
}
```

---

### RN-PACSSERIES-03: Validação de Protocolo
**Descrição**: Validar que as séries seguem o protocolo padrão para o tipo de exame.

**Implementação**:
```java
@Service
public class ProtocolValidationService {

    // Protocolos padrão por tipo de exame
    private static final Map<String, List<String>> STANDARD_PROTOCOLS = Map.of(
        "CT_ABDOMEN", List.of(
            "pre-contrast",
            "arterial phase",
            "venous phase"
        ),
        "MRI_BRAIN", List.of(
            "T1 sagittal",
            "T2 axial",
            "T2 FLAIR",
            "DWI"
        )
    );

    public ProtocolComplianceReport validateProtocol(
        String examType,
        List<PACSSeriesDTO> series
    ) {
        ProtocolComplianceReport report = new ProtocolComplianceReport();

        List<String> expectedSeries = STANDARD_PROTOCOLS.get(examType);
        if (expectedSeries == null) {
            report.addWarning("Protocolo não definido para: " + examType);
            return report;
        }

        // Verificar séries esperadas
        for (String expected : expectedSeries) {
            boolean found = series.stream()
                .anyMatch(s -> s.getDescription().toLowerCase().contains(expected));

            if (!found) {
                report.addMissingSeries(expected);
            }
        }

        // Verificar séries extras não esperadas
        for (PACSSeriesDTO serie : series) {
            boolean isExpected = expectedSeries.stream()
                .anyMatch(exp -> serie.getDescription().toLowerCase().contains(exp));

            if (!isExpected && !isReformattedSeries(serie)) {
                report.addUnexpectedSeries(serie.getDescription());
            }
        }

        return report;
    }
}
```

---

### RN-PACSSERIES-04: Lateralidade Obrigatória
**Descrição**: Exames de membros devem ter lateralidade especificada.

**Validação**:
```java
public void validateLateralityRequirement(PACSSeriesDTO series) {
    // Regiões que exigem lateralidade
    Set<String> requiresLaterality = Set.of(
        "upper extremity", "lower extremity",
        "arm", "forearm", "hand",
        "leg", "thigh", "foot",
        "shoulder", "elbow", "wrist",
        "hip", "knee", "ankle"
    );

    String bodysite = series.getBodysite().toLowerCase();
    boolean needsLaterality = requiresLaterality.stream()
        .anyMatch(bodysite::contains);

    if (needsLaterality) {
        if (series.getLaterality() == null || series.getLaterality().isEmpty()) {
            throw new ValidationException(
                "Lateralidade obrigatória para exame de " + series.getBodysite()
            );
        }
    }
}
```

---

## Exemplos de Uso

### Exemplo 1: Processar Séries para Faturamento
```java
@Service
public class SeriesBillingService {

    public List<GuiaItem> processSeriesForBilling(
        PACSStudyDTO study,
        String operadoraId
    ) {
        List<GuiaItem> items = new ArrayList<>();

        List<PACSSeriesDTO> series = study.getSeries();
        if (series == null || series.isEmpty()) {
            return items;
        }

        // Item principal (primeira série/série básica)
        GuiaItem mainItem = createMainStudyItem(study);
        items.add(mainItem);

        // Verificar séries adicionais
        for (PACSSeriesDTO serie : series) {
            if (isAdditionalSeriesBillable(serie, series)) {
                GuiaItem additionalItem = new GuiaItem();
                additionalItem.setCodigoTUSS(getAdditionalSeriesCode(serie));
                additionalItem.setQuantidade(1);
                additionalItem.setValorUnitario(
                    contratoService.getValor(
                        additionalItem.getCodigoTUSS(),
                        operadoraId
                    )
                );

                items.add(additionalItem);

                log.info("Série adicional faturada: {} - {}",
                    serie.getNumber(), serie.getDescription());
            }
        }

        return items;
    }

    private String getAdditionalSeriesCode(PACSSeriesDTO series) {
        // Exemplo: CT com fase adicional
        Optional<ContrastPhase> phase = ContrastPhase.detectPhase(series.getDescription());

        if (phase.isPresent()) {
            switch (phase.get()) {
                case ARTERIAL:
                    return "40801XXX"; // Código para fase arterial
                case DELAYED:
                    return "40801YYY"; // Código para fase tardia
                default:
                    return "40801ZZZ"; // Código genérico
            }
        }

        return "40801ZZZ";
    }
}
```

---

### Exemplo 2: Análise de Qualidade de Protocolo
```java
@Service
public class SeriesQualityAnalysisService {

    public QualityReport analyzeSeriesQuality(List<PACSSeriesDTO> series, String modality) {
        QualityReport report = new QualityReport();

        for (PACSSeriesDTO serie : series) {
            // Validar número de imagens
            if ("CT".equals(modality) && serie.getNumberOfInstances() < 30) {
                report.addWarning(
                    String.format("Série %d com poucas imagens: %d",
                        serie.getNumber(), serie.getNumberOfInstances())
                );
            }

            // Validar descrição presente
            if (serie.getDescription() == null || serie.getDescription().isEmpty()) {
                report.addError("Série " + serie.getNumber() + " sem descrição");
            }

            // Validar lateralidade se necessário
            try {
                validateLateralityRequirement(serie);
            } catch (ValidationException e) {
                report.addError(e.getMessage());
            }

            // Validar UID
            if (serie.getUid() == null || serie.getUid().isEmpty()) {
                report.addError("Série " + serie.getNumber() + " sem UID");
            }
        }

        return report;
    }
}
```

---

### Exemplo 3: Detecção de Fases de Contraste
```java
@Service
public class ContrastPhaseAnalysisService {

    public ContrastPhaseReport analyzeContrastPhases(List<PACSSeriesDTO> series) {
        ContrastPhaseReport report = new ContrastPhaseReport();

        for (PACSSeriesDTO serie : series) {
            Optional<ContrastPhase> phase = ContrastPhase.detectPhase(serie.getDescription());

            if (phase.isPresent()) {
                report.addPhase(phase.get(), serie);
            } else {
                report.addUnclassifiedSeries(serie);
            }
        }

        // Validar protocolo padrão
        if (report.hasPhase(ContrastPhase.PRE_CONTRAST) &&
            report.hasPhase(ContrastPhase.VENOUS)) {
            report.setProtocolCompliant(true);
        } else {
            report.addWarning("Protocolo incompleto: faltam fases padrão");
        }

        return report;
    }
}
```

---

## Integração DICOM

### Query de Séries Específicas
```java
public List<String> getSeriesInstanceUIDs(String studyInstanceUID) {
    List<PACSSeriesDTO> series = pacsClient.getStudySeries(studyInstanceUID, apiKey);

    return series.stream()
        .map(PACSSeriesDTO::getUid)
        .collect(Collectors.toList());
}

public byte[] downloadSeriesDICOM(String seriesInstanceUID) {
    String wadoUrl = String.format(
        "%s/wado?requestType=WADO&seriesUID=%s",
        pacsConfig.getWadoUri(),
        seriesInstanceUID
    );

    return restTemplate.getForObject(wadoUrl, byte[].class);
}
```

---

## Conformidade com Padrões

### DICOM Series Module
- **Series Instance UID**: Identificador único global
- **Series Number**: Número sequencial
- **Modality**: Modalidade de aquisição
- **Body Part Examined**: Região anatômica

### HL7 FHIR R4
- **ImagingStudy.series**: http://hl7.org/fhir/R4/imagingstudy-definitions.html#ImagingStudy.series

---

## Referências Técnicas

1. **DICOM Series Module**: PS3.3 Section C.7.3
2. **FHIR ImagingStudy**: http://hl7.org/fhir/R4/imagingstudy.html
3. **SNOMED CT Body Structures**: https://browser.ihtsdotools.org/?perspective=full&conceptId1=123037004

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
