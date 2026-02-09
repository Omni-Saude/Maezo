# RN-PACSStudyDTO - Estudo de Imagem (FHIR ImagingStudy)

## Identificação
- **ID**: RN-PACSStudyDTO
- **Nome**: PACS Study Data Transfer Object
- **Categoria**: Integration/Data Model
- **Subcategoria**: HL7 FHIR DTO + DICOM
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/pacs/dto/PACSStudyDTO.java`

---

## Descrição

Objeto de transferência de dados que representa um estudo de imagem médica seguindo os padrões HL7 FHIR R4 ImagingStudy e DICOM. Um estudo agrupa todas as imagens adquiridas em um único procedimento radiológico (ex: TC de abdômen, RM de crânio).

**Recursos Utilizados**:
- **FHIR**: ImagingStudy
- **DICOM**: Study Instance UID
- **URL FHIR**: http://hl7.org/fhir/R4/imagingstudy.html

---

## Estrutura de Dados

### Atributos

```java
@Data
public class PACSStudyDTO {
    private String id;                          // ID único no PACS
    private String identifier;                  // Identificador de negócio
    private String status;                      // Status do estudo
    private String patientId;                   // Referência ao paciente
    private String encounterId;                 // Referência ao encontro
    private LocalDateTime started;              // Data/hora início do estudo
    private LocalDateTime ended;                // Data/hora fim do estudo
    private String modality;                    // Modalidade DICOM (CT, MR, XR, etc.)
    private String description;                 // Descrição do estudo
    private Integer numberOfSeries;             // Número de séries
    private Integer numberOfInstances;          // Número total de imagens
    private List<PACSSeriesDTO> series;         // Séries de imagens
    private String studyInstanceUID;            // DICOM Study Instance UID
    private String reportStatus;                // Status do laudo
    private String reportText;                  // Texto do laudo radiológico
    private String interpretingRadiologist;     // Médico radiologista laudante
    private String viewerUrl;                   // URL do visualizador DICOM
}
```

---

## Mapeamento FHIR ImagingStudy

### Exemplo JSON FHIR
```json
{
  "resourceType": "ImagingStudy",
  "id": "study-12345",
  "identifier": [
    {
      "system": "urn:dicom:uid",
      "value": "urn:oid:1.2.840.113619.2.55.3.1234567890.123"
    },
    {
      "system": "http://hospital.com/pacs/accession",
      "value": "ACC-2024-001234"
    }
  ],
  "status": "available",
  "subject": {
    "reference": "Patient/123456"
  },
  "encounter": {
    "reference": "Encounter/enc-789"
  },
  "started": "2024-01-15T10:00:00Z",
  "endpoint": [
    {
      "reference": "Endpoint/pacs-dicomweb"
    }
  ],
  "numberOfSeries": 3,
  "numberOfInstances": 250,
  "modality": [
    {
      "system": "http://dicom.nema.org/resources/ontology/DCM",
      "code": "CT",
      "display": "Computed Tomography"
    }
  ],
  "description": "CT Abdomen with contrast",
  "series": [
    {
      "uid": "1.2.840.113619.2.55.3.1234567890.123.1",
      "number": 1,
      "modality": {
        "system": "http://dicom.nema.org/resources/ontology/DCM",
        "code": "CT"
      },
      "description": "Axial pre-contrast",
      "numberOfInstances": 80
    }
  ]
}
```

---

## Atributos Detalhados

### 1. id
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Identificador único do estudo no PACS
- **Exemplo**: `"study-12345"`

### 2. identifier
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Identificador de negócio (número de acesso)
- **Exemplo**: `"ACC-2024-001234"`
- **Uso**: Rastreamento físico, comunicação com radiologia

### 3. status
- **Tipo**: String (Enum)
- **Obrigatório**: Sim
- **Valores**:
  - `available` - Estudo disponível no PACS
  - `unavailable` - Estudo não disponível (arquivado, excluído)
  - `cancelled` - Exame cancelado

**Impacto no Faturamento**:
```java
// RN-PACSSTUDY-01: Apenas estudos "available" devem ser faturados
if (!"available".equals(study.getStatus())) {
    log.info("Estudo {} não faturável: status={}", study.getId(), study.getStatus());
    return false;
}
```

---

### 4. patientId
- **Tipo**: String
- **Obrigatório**: Sim
- **Formato**: `"Patient/{id}"`
- **Exemplo**: `"Patient/123456"`

### 5. encounterId
- **Tipo**: String
- **Obrigatório**: Sim (crítico para faturamento)
- **Formato**: `"Encounter/{id}"`
- **Exemplo**: `"Encounter/enc-789"`

**Importância**:
- Vincula exame ao episódio de cuidado
- Necessário para incluir na guia TISS correta
- Valida que exame foi realizado durante internação/consulta

---

### 6. started
- **Tipo**: LocalDateTime
- **Obrigatório**: Sim
- **Descrição**: Data/hora de início da aquisição de imagens
- **Formato ISO**: `2024-01-15T10:00:00`

**Uso**:
- Data de realização para faturamento
- Validação de vigência de plano de saúde
- Cálculo de tempo de exame

### 7. ended
- **Tipo**: LocalDateTime
- **Obrigatório**: Não
- **Descrição**: Data/hora de término da aquisição

**Cálculo de Duração**:
```java
Duration examDuration = Duration.between(study.getStarted(), study.getEnded());
if (examDuration.toMinutes() > 60) {
    qualityAlert("Exame com duração prolongada: " + study.getId());
}
```

---

### 8. modality
- **Tipo**: String (DICOM Modality)
- **Obrigatório**: Sim
- **Sistema**: http://dicom.nema.org/resources/ontology/DCM

**Modalidades Comuns**:
| Código | Descrição | Uso Clínico |
|--------|-----------|-------------|
| CT | Computed Tomography | Tomografia computadorizada |
| MR | Magnetic Resonance | Ressonância magnética |
| XR | X-Ray | Radiografia convencional |
| US | Ultrasound | Ultrassonografia |
| CR | Computed Radiography | Radiografia computadorizada |
| DX | Digital Radiography | Radiografia digital |
| MG | Mammography | Mamografia |
| NM | Nuclear Medicine | Medicina nuclear |
| PT | PET Scan | Tomografia por emissão de pósitrons |
| RF | Radioflurescence | Fluoroscopia |

**Mapeamento para TUSS**:
```java
private static final Map<String, String> MODALITY_TO_TUSS_PREFIX = Map.of(
    "CT", "408",  // Tomografia
    "MR", "409",  // Ressonância
    "XR", "401",  // Radiografia
    "CR", "401",  // Radiografia computadorizada
    "DX", "401",  // Radiografia digital
    "US", "410",  // Ultrassonografia
    "MG", "411",  // Mamografia
    "NM", "412",  // Medicina nuclear
    "PT", "412"   // PET Scan
);

public String getTUSSCategory(String modality) {
    return MODALITY_TO_TUSS_PREFIX.getOrDefault(modality, "400");
}
```

---

### 9. description
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Descrição textual do estudo
- **Exemplos**:
  - `"CT Abdomen with contrast"`
  - `"MRI Brain without contrast"`
  - `"Chest X-ray 2 views"`

**Uso**:
- Mapeamento para códigos TUSS específicos
- Identificação de uso de contraste
- Validação de protocolo

**Parsing para Mapeamento**:
```java
public String mapDescriptionToTUSS(String description, String modality) {
    String desc = description.toLowerCase();

    if ("CT".equals(modality)) {
        if (desc.contains("abdomen")) {
            return desc.contains("contrast") ? "40801403" : "40801390";
        } else if (desc.contains("chest") || desc.contains("thorax")) {
            return desc.contains("contrast") ? "40801144" : "40801136";
        } else if (desc.contains("brain") || desc.contains("head")) {
            return desc.contains("contrast") ? "40801071" : "40801063";
        }
    }

    throw new CodeMappingException("Descrição não mapeada: " + description);
}
```

---

### 10. numberOfSeries
- **Tipo**: Integer
- **Obrigatório**: Sim
- **Descrição**: Número de séries de imagens no estudo

**Validação**:
```java
if (study.getNumberOfSeries() == null || study.getNumberOfSeries() == 0) {
    throw new ValidationException("Estudo sem séries: " + study.getId());
}
```

### 11. numberOfInstances
- **Tipo**: Integer
- **Obrigatório**: Sim
- **Descrição**: Número total de imagens DICOM no estudo

**Validação de Qualidade**:
```java
// CT de abdômen geralmente tem 80-150 imagens
if ("CT".equals(study.getModality()) && study.getNumberOfInstances() < 50) {
    qualityAlert("CT com poucas imagens: " + study.getNumberOfInstances());
}
```

---

### 12. series
- **Tipo**: List<PACSSeriesDTO>
- **Obrigatório**: Não (mas geralmente presente)
- **Descrição**: Lista de séries de imagens do estudo

**Uso**:
- Detalhamento técnico do estudo
- Identificação de séries com/sem contraste
- Faturamento de séries adicionais

---

### 13. studyInstanceUID
- **Tipo**: String (DICOM UID)
- **Obrigatório**: Sim
- **Descrição**: Identificador único global do estudo no padrão DICOM
- **Formato**: OID (Object Identifier)
- **Exemplo**: `"1.2.840.113619.2.55.3.1234567890.123"`

**Importância**:
- Identificação única global (independente de sistema)
- Usado em queries DICOM nativas
- Padrão para integração entre sistemas PACS

**Estrutura do UID**:
```
1.2.840.113619        - Root (organization)
.2.55.3               - Device/Application
.1234567890.123       - Study unique number
```

---

### 14. reportStatus
- **Tipo**: String (Enum)
- **Obrigatório**: Não (mas crítico para faturamento)
- **Valores**:
  - `preliminary` - Laudo preliminar
  - `final` - Laudo final liberado
  - `amended` - Laudo alterado
  - `corrected` - Laudo corrigido

**Regra de Faturamento**:
```java
// RN-PACSSTUDY-02: Apenas estudos com laudo final podem ser faturados
public boolean hasValidReport(PACSStudyDTO study) {
    return Set.of("final", "amended", "corrected")
        .contains(study.getReportStatus());
}
```

---

### 15. reportText
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Texto do laudo radiológico
- **Exemplo**:
```
TÉCNICA: Tomografia computadorizada do abdome com contraste endovenoso.

ACHADOS:
- Fígado de dimensões normais, contornos regulares, sem lesões focais.
- Vesícula biliar normodistendida, sem cálculos.
- Pâncreas de aspecto habitual.
- Baço tópico, tamanho e densidade normais.

CONCLUSÃO: Exame dentro dos limites da normalidade.
```

**Uso**:
- Anexo em guias TISS quando exigido
- Recurso de glosa (evidência clínica)
- Prontuário eletrônico

---

### 16. interpretingRadiologist
- **Tipo**: String
- **Obrigatório**: Sim (para faturamento)
- **Formato**: `"Practitioner/{id}"`
- **Exemplo**: `"Practitioner/dr-radiologista-123"`

**Validações Regulatórias**:
```java
public void validateRadiologist(String radiologistId) {
    Practitioner radiologist = practitionerService.getById(radiologistId);

    if (radiologist == null || !radiologist.isActive()) {
        throw new ValidationException("Radiologista inativo: " + radiologistId);
    }

    // Validar CRM com especialidade radiologia
    if (!radiologist.getSpecialty().equals("RADIOLOGY")) {
        throw new ValidationException("Profissional não é radiologista");
    }

    // Validar RQE (Registro de Qualificação de Especialista)
    if (radiologist.getRqe() == null) {
        throw new ValidationException("Radiologista sem RQE");
    }
}
```

---

### 17. viewerUrl
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: URL do visualizador DICOM web
- **Exemplo**: `"https://pacs-viewer.hospital.com/viewer?studyUID=1.2.840..."`

**Uso**:
- Acesso direto às imagens
- Integração com prontuário eletrônico
- Anexo em guias TISS (link para imagens)

---

## Regras de Negócio

### RN-PACSSTUDY-01: Validação de Status para Faturamento
**Descrição**: Apenas estudos com status "available" podem ser faturados.

**Implementação**:
```java
public boolean isStudyBillable(PACSStudyDTO study) {
    // Verificar status do estudo
    if (!"available".equals(study.getStatus())) {
        return false;
    }

    // Verificar laudo finalizado
    if (!hasValidReport(study)) {
        return false;
    }

    // Verificar radiologista
    if (study.getInterpretingRadiologist() == null) {
        return false;
    }

    return true;
}
```

---

### RN-PACSSTUDY-02: Exames com Contraste
**Descrição**: Identificar e codificar corretamente exames realizados com meio de contraste.

**Implementação**:
```java
public boolean isContrastEnhanced(PACSStudyDTO study) {
    String desc = study.getDescription().toLowerCase();
    return desc.contains("contrast") ||
           desc.contains("contraste") ||
           desc.contains("enhanced") ||
           desc.contains("with injection");
}

public String getTUSSCode(PACSStudyDTO study) {
    String baseCode = mapModalityAndRegion(study.getModality(), study.getDescription());

    if (isContrastEnhanced(study)) {
        return getContrastEnhancedCode(baseCode);
    }

    return baseCode;
}
```

---

### RN-PACSSTUDY-03: Séries Múltiplas
**Descrição**: Estudos com múltiplas séries podem gerar cobrança adicional.

**Implementação**:
```java
public List<GuiaItem> processMultipleSeries(PACSStudyDTO study) {
    List<GuiaItem> items = new ArrayList<>();

    // Item principal
    items.add(createMainStudyItem(study));

    // Verificar séries adicionais cobráveis
    if (study.getNumberOfSeries() > 1 && study.getSeries() != null) {
        for (PACSSeriesDTO series : study.getSeries()) {
            if (isAdditionalSeriesBillable(series, study.getModality())) {
                items.add(createAdditionalSeriesItem(series));
            }
        }
    }

    return items;
}

private boolean isAdditionalSeriesBillable(PACSSeriesDTO series, String modality) {
    // Exemplo: CT com séries pré e pós-contraste
    if ("CT".equals(modality)) {
        String desc = series.getDescription().toLowerCase();
        return desc.contains("post-contrast") ||
               desc.contains("delayed") ||
               desc.contains("arterial phase");
    }
    return false;
}
```

---

### RN-PACSSTUDY-04: Validação de Qualidade de Imagens
**Descrição**: Verificar se o estudo tem quantidade adequada de imagens.

**Implementação**:
```java
@Service
public class ImageQualityValidationService {

    // Número mínimo de imagens por modalidade
    private static final Map<String, Integer> MIN_INSTANCES = Map.of(
        "CT", 50,
        "MR", 30,
        "XR", 1,
        "US", 5,
        "MG", 2  // CC e MLO
    );

    public QualityReport validateImageQuality(PACSStudyDTO study) {
        QualityReport report = new QualityReport();

        Integer minInstances = MIN_INSTANCES.get(study.getModality());
        if (minInstances != null) {
            if (study.getNumberOfInstances() < minInstances) {
                report.addWarning(
                    String.format("Estudo %s com poucas imagens: %d (mínimo: %d)",
                        study.getModality(),
                        study.getNumberOfInstances(),
                        minInstances)
                );
            }
        }

        // Validar séries
        if (study.getNumberOfSeries() == 0) {
            report.addError("Estudo sem séries");
        }

        return report;
    }
}
```

---

## Exemplos de Uso

### Exemplo 1: Processar Estudos para Faturamento
```java
@Service
public class ImagingBillingService {

    public List<GuiaItem> processStudiesForBilling(String encounterId, String operadoraId) {
        List<GuiaItem> items = new ArrayList<>();

        // Obter estudos do encontro
        List<PACSStudyDTO> studies = pacsClient.getStudiesByEncounter(encounterId, apiKey);

        for (PACSStudyDTO study : studies) {
            // Validar se é faturável
            if (!isStudyBillable(study)) {
                log.info("Estudo {} não faturável", study.getId());
                continue;
            }

            // Mapear para código TUSS
            String tissCode = mapStudyToTUSS(study);

            // Criar item de guia
            GuiaItem item = new GuiaItem();
            item.setCodigoTUSS(tissCode);
            item.setDataRealizacao(study.getStarted().toLocalDate());
            item.setQuantidade(1);
            item.setValorUnitario(contratoService.getValor(tissCode, operadoraId));

            // Anexar visualizador se exigido
            if (contratoService.exigeAnexoImagem(operadoraId, tissCode)) {
                item.setAnexoImagem(study.getViewerUrl());
            }

            items.add(item);

            // Processar séries adicionais
            items.addAll(processMultipleSeries(study));
        }

        return items;
    }
}
```

---

### Exemplo 2: Validação de Completude
```java
@Service
public class StudyCompletenessService {

    public CompletenessReport checkStudyCompleteness(String encounterId) {
        CompletenessReport report = new CompletenessReport();

        List<PACSStudyDTO> studies = pacsClient.getStudiesByEncounter(encounterId, apiKey);

        for (PACSStudyDTO study : studies) {
            // Verificar status
            if (!"available".equals(study.getStatus())) {
                report.addPending(study.getId(), "Estudo não disponível: " + study.getStatus());
                continue;
            }

            // Verificar laudo
            if (study.getReportStatus() == null || "preliminary".equals(study.getReportStatus())) {
                report.addPending(study.getId(), "Laudo não finalizado");
                continue;
            }

            // Verificar qualidade de imagens
            QualityReport quality = imageQualityService.validateImageQuality(study);
            if (quality.hasErrors()) {
                report.addIssue(study.getId(), quality.getErrors());
            }

            report.addCompleted(study.getId());
        }

        return report;
    }
}
```

---

## Integração DICOM

### Query DICOM usando Study Instance UID
```java
public byte[] downloadStudyDICOM(String studyInstanceUID) {
    // URL WADO (Web Access to DICOM Objects)
    String wadoUrl = String.format(
        "%s/wado?requestType=WADO&studyUID=%s",
        pacsConfig.getWadoUri(),
        studyInstanceUID
    );

    return restTemplate.getForObject(wadoUrl, byte[].class);
}
```

---

## Conformidade Regulatória

### HL7 FHIR R4
- **ImagingStudy Resource**: http://hl7.org/fhir/R4/imagingstudy.html

### DICOM Standards
- **Study Module**: PS3.3 Section C.7.2
- **Study Instance UID**: Identificador único global

### TISS/ANS
- **Codificação**: Procedimentos radiológicos com códigos TUSS
- **Anexos**: Laudos e imagens podem ser exigidos

---

## Referências Técnicas

1. **FHIR ImagingStudy**: http://hl7.org/fhir/R4/imagingstudy.html
2. **DICOM Standard**: https://www.dicomstandard.org/
3. **DICOM Modalities**: http://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.3.html
4. **DICOMweb**: https://www.dicomstandard.org/dicomweb

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
