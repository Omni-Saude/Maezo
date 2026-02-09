# RN-LISSpecimenDTO - Amostra Biológica (FHIR Specimen)

## Identificação
- **ID**: RN-LISSpecimenDTO
- **Nome**: LIS Specimen Data Transfer Object
- **Categoria**: Integration/Data Model
- **Subcategoria**: HL7 FHIR DTO
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/lis/dto/LISSpecimenDTO.java`

---

## Descrição

Objeto de transferência de dados que representa uma amostra biológica (espécime) coletada para realização de exames laboratoriais, seguindo o padrão HL7 FHIR R4 Specimen. Este DTO contém informações sobre coleta, tipo de material, condições de armazenamento e rastreabilidade da amostra.

**Recurso FHIR**: Specimen
**URL FHIR**: http://hl7.org/fhir/R4/specimen.html

---

## Estrutura de Dados

### Atributos

```java
@Data
public class LISSpecimenDTO {
    private String id;                       // ID único da amostra
    private String identifier;               // Código de barras/etiqueta
    private String accessionIdentifier;      // Número de acesso laboratorial
    private String status;                   // Status da amostra
    private String type;                     // Tipo de material biológico
    private String patientId;                // Referência ao paciente
    private String orderId;                  // Referência ao pedido
    private LocalDateTime collectedDateTime; // Data/hora da coleta
    private LocalDateTime receivedDateTime;  // Data/hora de recebimento no lab
    private String collectionMethod;         // Método de coleta
    private String container;                // Tipo de recipiente
    private String bodysite;                 // Local anatômico da coleta
}
```

---

## Mapeamento FHIR Specimen

### Exemplo JSON FHIR
```json
{
  "resourceType": "Specimen",
  "id": "spec-001",
  "identifier": [
    {
      "system": "http://hospital.com/lis/specimens",
      "value": "SPEC-2024-001234"
    }
  ],
  "accessionIdentifier": {
    "system": "http://hospital.com/lis/accession",
    "value": "LAB-2024-56789"
  },
  "status": "available",
  "type": {
    "coding": [
      {
        "system": "http://snomed.info/sct",
        "code": "119297000",
        "display": "Blood specimen"
      }
    ]
  },
  "subject": {
    "reference": "Patient/123456"
  },
  "request": [
    {
      "reference": "ServiceRequest/order-12345"
    }
  ],
  "collection": {
    "collectedDateTime": "2024-01-15T09:00:00Z",
    "method": {
      "coding": [
        {
          "system": "http://snomed.info/sct",
          "code": "278450005",
          "display": "Venipuncture"
        }
      ]
    },
    "bodySite": {
      "coding": [
        {
          "system": "http://snomed.info/sct",
          "code": "368208006",
          "display": "Left antecubital fossa"
        }
      ]
    }
  },
  "receivedTime": "2024-01-15T09:30:00Z",
  "container": [
    {
      "type": {
        "text": "Tubo EDTA"
      }
    }
  ]
}
```

---

## Atributos Detalhados

### 1. id
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Identificador único da amostra no LIS
- **Exemplo**: `"spec-001"`

### 2. identifier
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Código de barras ou etiqueta da amostra
- **Exemplo**: `"SPEC-2024-001234"`
- **Uso**: Rastreamento físico da amostra no laboratório

### 3. accessionIdentifier
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Número de acesso/entrada do laboratório
- **Exemplo**: `"LAB-2024-56789"`
- **Uso**: Agrupamento de múltiplas amostras de um mesmo pedido

### 4. status
- **Tipo**: String (Enum)
- **Obrigatório**: Sim
- **Valores**:
  - `available` - Amostra disponível para análise
  - `unavailable` - Amostra não disponível (insuficiente, hemolisada)
  - `unsatisfactory` - Amostra inadequada para análise
  - `entered-in-error` - Erro no registro

**Impacto no Faturamento**:
```java
// RN-SPECIMEN-01: Apenas amostras "available" geram cobrança
if (!"available".equals(specimen.getStatus())) {
    log.info("Amostra {} não disponível: {}", specimen.getId(), specimen.getStatus());
    return false; // Não faturar
}
```

---

### 5. type
- **Tipo**: String (SNOMED CT)
- **Obrigatório**: Sim
- **Sistema**: http://snomed.info/sct
- **Exemplos**:
  - `119297000` - Blood specimen (sangue)
  - `122575003` - Urine specimen (urina)
  - `119376003` - Tissue specimen (tecido)
  - `258580003` - Whole blood (sangue total)
  - `119339001` - Stool specimen (fezes)

**Validação de Tipo vs Exame**:
```java
// RN-SPECIMEN-02: Tipo de amostra deve ser compatível com exame solicitado
if (!isSpecimenTypeValid(specimen.getType(), order.getTestCodes())) {
    throw new ValidationException(
        "Tipo de amostra incompatível com exame: " + specimen.getType()
    );
}
```

---

### 6. patientId
- **Tipo**: String
- **Obrigatório**: Sim
- **Formato**: `"Patient/{id}"`
- **Validação**: Deve corresponder ao paciente do pedido

### 7. orderId
- **Tipo**: String
- **Obrigatório**: Sim
- **Formato**: `"ServiceRequest/{id}"`
- **Descrição**: Referência ao pedido que originou a coleta

---

### 8. collectedDateTime
- **Tipo**: LocalDateTime
- **Obrigatório**: Sim
- **Descrição**: Data/hora da coleta da amostra
- **Formato ISO**: `2024-01-15T09:00:00`

**Uso**:
- Data de realização do procedimento de coleta (se faturado separadamente)
- Cálculo de turnaround time (TAT)
- Validação de estabilidade da amostra

---

### 9. receivedDateTime
- **Tipo**: LocalDateTime
- **Obrigatório**: Não (recomendado)
- **Descrição**: Data/hora de recebimento no laboratório

**Cálculo de TAT Pré-Analítico**:
```java
Duration preAnalyticTAT = Duration.between(
    specimen.getCollectedDateTime(),
    specimen.getReceivedDateTime()
);

if (preAnalyticTAT.toHours() > 4) {
    qualityAlert("TAT pré-analítico elevado: " + specimen.getId());
}
```

---

### 10. collectionMethod
- **Tipo**: String (SNOMED CT)
- **Obrigatório**: Não
- **Exemplos**:
  - `278450005` - Venipuncture (venopunção)
  - `129316008` - Arterial puncture (punção arterial)
  - `225158009` - Catheter specimen collection (coleta por cateter)

**Impacto no Faturamento**:
```java
// Alguns métodos de coleta são cobrados separadamente
if ("129316008".equals(specimen.getCollectionMethod())) { // Punção arterial
    GuiaItem coleta = new GuiaItem();
    coleta.setCodigoTUSS("40301079"); // Punção arterial para gasometria
    coleta.setValorUnitario(contratoService.getValor("40301079", operadoraId));
    guia.addItem(coleta);
}
```

---

### 11. container
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Tipo de recipiente/tubo utilizado
- **Exemplos**:
  - `"Tubo EDTA"` (roxo - hemograma)
  - `"Tubo citrato"` (azul - coagulação)
  - `"Tubo soro"` (amarelo - bioquímica)
  - `"Frasco estéril"` (culturas)

---

### 12. bodysite
- **Tipo**: String (SNOMED CT)
- **Obrigatório**: Não
- **Descrição**: Local anatômico da coleta
- **Exemplos**:
  - `368208006` - Left antecubital fossa (fossa cubital esquerda)
  - `368209003` - Right antecubital fossa
  - `7569003` - Finger (dedo - glicemia capilar)

---

## Regras de Negócio

### RN-SPECIMEN-01: Status para Faturamento
**Descrição**: Apenas amostras com status "available" devem gerar cobrança.

**Implementação**:
```java
public boolean isSpecimenBillable(LISSpecimenDTO specimen) {
    if (!"available".equals(specimen.getStatus())) {
        log.info("Amostra {} não faturável: status={}",
            specimen.getId(), specimen.getStatus());
        return false;
    }
    return true;
}
```

**Cenários**:
- `unavailable`: Amostra insuficiente → nova coleta necessária → não cobrar original
- `unsatisfactory`: Amostra hemolisada/coagulada → repetir coleta → não cobrar
- `entered-in-error`: Erro de registro → corrigir e não faturar

---

### RN-SPECIMEN-02: Compatibilidade Tipo de Amostra vs Exame
**Descrição**: O tipo de amostra coletada deve ser compatível com os exames solicitados.

**Tabela de Compatibilidade**:
| Tipo de Amostra | Exames Compatíveis | Incompatível |
|-----------------|-------------------|--------------|
| Blood specimen | Hemograma, bioquímica, sorologia | Uriná lise |
| Urine specimen | EAS, urinocultura | Hemograma |
| Stool specimen | Parasitológico, coprocultura | Hemograma |

**Validação**:
```java
public void validateSpecimenType(LISSpecimenDTO specimen, List<String> testCodes) {
    for (String testCode : testCodes) {
        String requiredSpecimenType = getRequiredSpecimenType(testCode);

        if (!specimen.getType().equals(requiredSpecimenType)) {
            throw new ValidationException(
                String.format(
                    "Tipo de amostra incompatível: exame %s requer %s, mas foi coletado %s",
                    testCode, requiredSpecimenType, specimen.getType()
                )
            );
        }
    }
}
```

---

### RN-SPECIMEN-03: Cobrança de Procedimentos de Coleta
**Descrição**: Alguns métodos de coleta são procedimentos cobráveis separadamente.

**Procedimentos Cobráveis**:
```java
private static final Map<String, String> BILLABLE_COLLECTION_METHODS = Map.of(
    "129316008", "40301079",  // Punção arterial
    "14766002", "40304256",    // Punção lombar
    "91602002", "40304230"     // Paracentese
);

public Optional<GuiaItem> getCollectionProcedureItem(LISSpecimenDTO specimen) {
    String collectionMethod = specimen.getCollectionMethod();
    String tissCode = BILLABLE_COLLECTION_METHODS.get(collectionMethod);

    if (tissCode != null) {
        GuiaItem item = new GuiaItem();
        item.setCodigoTUSS(tissCode);
        item.setDataRealizacao(specimen.getCollectedDateTime().toLocalDate());
        item.setQuantidade(1);
        item.setValorUnitario(contratoService.getValor(tissCode, operadoraId));
        return Optional.of(item);
    }

    return Optional.empty();
}
```

---

### RN-SPECIMEN-04: Rastreabilidade e Cadeia de Custódia
**Descrição**: Todas as amostras devem ter rastreabilidade completa (coleta → recebimento → análise).

**Validação**:
```java
public ChainOfCustodyReport validateChainOfCustody(LISSpecimenDTO specimen) {
    ChainOfCustodyReport report = new ChainOfCustodyReport();

    // Validar timestamps
    if (specimen.getCollectedDateTime() == null) {
        report.addIssue("Data/hora de coleta ausente");
    }

    if (specimen.getReceivedDateTime() == null) {
        report.addWarning("Data/hora de recebimento não registrada");
    }

    if (specimen.getReceivedDateTime() != null &&
        specimen.getReceivedDateTime().isBefore(specimen.getCollectedDateTime())) {
        report.addError("Data de recebimento anterior à coleta - erro lógico");
    }

    // Validar identificadores
    if (specimen.getIdentifier() == null || specimen.getIdentifier().isEmpty()) {
        report.addError("Identificador da amostra ausente");
    }

    return report;
}
```

---

### RN-SPECIMEN-05: Prazo de Estabilidade
**Descrição**: Amostras têm prazo máximo de estabilidade entre coleta e análise.

**Prazos de Estabilidade**:
```java
private static final Map<String, Duration> SPECIMEN_STABILITY = Map.of(
    "119297000", Duration.ofHours(24),  // Sangue: 24h
    "122575003", Duration.ofHours(2),   // Urina: 2h (sem conservante)
    "258580003", Duration.ofHours(6),   // Sangue total: 6h
    "119376003", Duration.ofHours(72)   // Tecido (fixado): 72h
);

public boolean isSpecimenStable(LISSpecimenDTO specimen, LocalDateTime analysisTime) {
    Duration maxStability = SPECIMEN_STABILITY.get(specimen.getType());
    if (maxStability == null) {
        maxStability = Duration.ofHours(24); // Default
    }

    Duration elapsed = Duration.between(specimen.getCollectedDateTime(), analysisTime);

    if (elapsed.compareTo(maxStability) > 0) {
        log.warn("Amostra {} pode estar instável: coletada há {}, máximo {}",
            specimen.getId(), elapsed, maxStability);
        return false;
    }

    return true;
}
```

---

## Exemplos de Uso

### Exemplo 1: Validar Amostras para Faturamento
```java
@Service
public class SpecimenBillingValidationService {

    public ValidationResult validateSpecimens(String orderId) {
        ValidationResult result = new ValidationResult();

        // Obter pedido
        LISOrderDTO order = lisClient.getOrderById(orderId, apiKey);

        // Obter amostras do pedido
        List<LISSpecimenDTO> specimens = lisClient.getSpecimensByOrder(orderId, apiKey);

        if (specimens.isEmpty()) {
            result.addError("Nenhuma amostra coletada para pedido " + order.getIdentifier());
            return result;
        }

        for (LISSpecimenDTO specimen : specimens) {
            // Validar status
            if (!"available".equals(specimen.getStatus())) {
                result.addWarning(
                    "Amostra " + specimen.getIdentifier() + " não disponível: " + specimen.getStatus()
                );
            }

            // Validar tipo vs exames
            try {
                validateSpecimenType(specimen, order.getTestCodes());
            } catch (ValidationException e) {
                result.addError(e.getMessage());
            }

            // Validar cadeia de custódia
            ChainOfCustodyReport custody = validateChainOfCustody(specimen);
            result.merge(custody);
        }

        return result;
    }
}
```

---

### Exemplo 2: Faturar Procedimentos de Coleta
```java
@Service
public class CollectionProcedureBillingService {

    public List<GuiaItem> billCollectionProcedures(String orderId) {
        List<GuiaItem> items = new ArrayList<>();

        // Obter amostras do pedido
        List<LISSpecimenDTO> specimens = lisClient.getSpecimensByOrder(orderId, apiKey);

        for (LISSpecimenDTO specimen : specimens) {
            // Verificar se método de coleta é cobrável
            Optional<GuiaItem> collectionItem = getCollectionProcedureItem(specimen);

            if (collectionItem.isPresent()) {
                items.add(collectionItem.get());
                log.info("Cobrando procedimento de coleta: {} para amostra {}",
                    collectionItem.get().getCodigoTUSS(), specimen.getId());
            }
        }

        return items;
    }
}
```

---

### Exemplo 3: Monitoramento de Qualidade (TAT Pré-Analítico)
```java
@Service
public class PreAnalyticQualityService {

    public PreAnalyticMetrics analyzePreAnalyticPhase(String orderId) {
        PreAnalyticMetrics metrics = new PreAnalyticMetrics();

        List<LISSpecimenDTO> specimens = lisClient.getSpecimensByOrder(orderId, apiKey);

        for (LISSpecimenDTO specimen : specimens) {
            if (specimen.getReceivedDateTime() == null) {
                metrics.addMissingData(specimen.getId(), "receivedDateTime");
                continue;
            }

            // Calcular TAT pré-analítico
            Duration tat = Duration.between(
                specimen.getCollectedDateTime(),
                specimen.getReceivedDateTime()
            );

            metrics.addTAT(specimen.getId(), tat);

            // Alertar se TAT > 4 horas (pode comprometer qualidade)
            if (tat.toHours() > 4) {
                metrics.addQualityAlert(
                    specimen.getId(),
                    "TAT pré-analítico elevado: " + tat.toHours() + "h"
                );
            }
        }

        return metrics;
    }
}
```

---

## Integração com Outros Sistemas

### 1. Sistema de Rastreamento por RFID/Código de Barras
```java
@Service
public class SpecimenTrackingService {

    public void trackSpecimen(String barcode) {
        // Buscar amostra por código de barras
        LISSpecimenDTO specimen = lisClient.getSpecimenByIdentifier(barcode, apiKey);

        if (specimen == null) {
            throw new NotFoundException("Amostra não encontrada: " + barcode);
        }

        // Registrar checkpoint
        trackingRepo.save(new TrackingEvent(
            specimen.getId(),
            LocalDateTime.now(),
            "SCANNED",
            getCurrentLocation()
        ));
    }
}
```

---

### 2. Interface com Robótica Laboratorial
```java
@Service
public class LaboratoryAutomationService {

    public void loadSpecimenToAnalyzer(String specimenId, String analyzerId) {
        LISSpecimenDTO specimen = lisClient.getSpecimenById(specimenId, apiKey);

        // Validar que amostra está disponível
        if (!"available".equals(specimen.getStatus())) {
            throw new IllegalStateException("Amostra não disponível para análise");
        }

        // Validar estabilidade
        if (!isSpecimenStable(specimen, LocalDateTime.now())) {
            qualityAlert("Amostra potencialmente instável carregada em analisador: " + specimenId);
        }

        // Enviar para analisador
        analyzerInterface.loadSample(analyzerId, specimen.getIdentifier());
    }
}
```

---

## Conformidade Regulatória

### ANVISA - RDC 302/2005 (Laboratórios Clínicos)
- **Rastreabilidade**: Toda amostra deve ter identificação única inequívoca
- **Cadeia de custódia**: Registro de coleta, transporte e recebimento
- **Prazo de estabilidade**: Respeitar limites de estabilidade de amostras

### LGPD
- **Minimização**: Coletar apenas dados necessários sobre amostras
- **Segurança**: Proteger identificadores de amostras vinculadas a pacientes

---

## Referências Técnicas

1. **FHIR Specimen**: http://hl7.org/fhir/R4/specimen.html
2. **SNOMED CT Specimen Types**: https://browser.ihtsdotools.org/?perspective=full&conceptId1=123038009
3. **CLSI - Procedures for Collection of Diagnostic Blood Specimens**: GP41-A6
4. **ANVISA RDC 302/2005**: Regulamento Técnico para Laboratórios Clínicos

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
