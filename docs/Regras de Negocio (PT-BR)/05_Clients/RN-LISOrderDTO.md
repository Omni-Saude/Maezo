# RN-LISOrderDTO - Pedido Laboratorial (FHIR ServiceRequest)

## Identificação
- **ID**: RN-LISOrderDTO
- **Nome**: LIS Order Data Transfer Object
- **Categoria**: Integration/Data Model
- **Subcategoria**: HL7 FHIR DTO
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/lis/dto/LISOrderDTO.java`

---

## Descrição

Objeto de transferência de dados que representa um pedido de exame laboratorial seguindo o padrão HL7 FHIR R4 ServiceRequest. Este DTO mapeia os dados recebidos do LIS (Laboratory Information System) para o domínio do sistema de faturamento hospitalar.

**Recurso FHIR**: ServiceRequest
**URL FHIR**: http://hl7.org/fhir/R4/servicerequest.html

---

## Estrutura de Dados

### Atributos

```java
@Data
public class LISOrderDTO {
    private String id;                      // ID único do pedido no LIS
    private String identifier;              // Identificador de negócio
    private String status;                  // Status do pedido
    private String intent;                  // Intenção clínica
    private String priority;                // Prioridade do exame
    private String patientId;               // Referência ao paciente
    private String encounterId;             // Referência ao encontro
    private String orderingProviderId;      // Médico solicitante
    private LocalDateTime authoredOn;       // Data/hora da solicitação
    private LocalDateTime occurrenceDateTime; // Data/hora da realização
    private List<String> testCodes;         // Códigos LOINC dos testes
    private List<String> specimenIds;       // IDs das amostras
    private String category;                // Categoria do serviço
    private String reasonCode;              // Código da justificativa
    private String reasonReference;         // Referência à condição/diagnóstico
    private Boolean requisitionSigned;      // Requisição assinada?
}
```

---

## Mapeamento FHIR ServiceRequest

### Exemplo JSON FHIR
```json
{
  "resourceType": "ServiceRequest",
  "id": "order-12345",
  "identifier": [
    {
      "system": "http://hospital.com/lis/orders",
      "value": "REQ-2024-001234"
    }
  ],
  "status": "active",
  "intent": "order",
  "priority": "routine",
  "code": {
    "coding": [
      {
        "system": "http://loinc.org",
        "code": "24331-1",
        "display": "Lipid panel"
      }
    ]
  },
  "subject": {
    "reference": "Patient/123456"
  },
  "encounter": {
    "reference": "Encounter/enc-789"
  },
  "authoredOn": "2024-01-15T08:30:00Z",
  "occurrenceDateTime": "2024-01-15T09:00:00Z",
  "requester": {
    "reference": "Practitioner/dr-silva"
  },
  "reasonCode": [
    {
      "coding": [
        {
          "system": "http://snomed.info/sct",
          "code": "267036007",
          "display": "Dyslipidemia"
        }
      ]
    }
  ],
  "specimen": [
    {
      "reference": "Specimen/spec-001"
    }
  ]
}
```

---

## Atributos Detalhados

### 1. id
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Identificador único do pedido no sistema LIS
- **Exemplo**: `"order-12345"`
- **Uso**: Rastreamento e referência cruzada

### 2. identifier
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Identificador de negócio (número da requisição)
- **Exemplo**: `"REQ-2024-001234"`
- **Uso**: Identificação humanizada, impressão em laudos

### 3. status
- **Tipo**: String (Enum)
- **Obrigatório**: Sim
- **Valores Possíveis**:
  - `draft` - Rascunho, não enviado ao laboratório
  - `active` - Pedido ativo, em processamento
  - `completed` - Exame realizado, resultados disponíveis
  - `cancelled` - Pedido cancelado
  - `on-hold` - Suspenso temporariamente
  - `revoked` - Revogado após aprovação
  - `entered-in-error` - Entrada errônea

**Impacto no Faturamento**:
- Apenas `completed` deve ser faturado
- `cancelled` não deve gerar cobrança
- `active` indica serviço em andamento

---

### 4. intent
- **Tipo**: String (Enum)
- **Obrigatório**: Sim
- **Valores**:
  - `order` - Pedido original
  - `reflex-order` - Pedido reflexo (automático baseado em resultado)
  - `original-order` - Pedido original que gerou reflexos
  - `instance-order` - Instância específica de pedido recorrente

**Regra de Negócio**:
```java
if ("reflex-order".equals(order.getIntent())) {
    // Pedido reflexo: verificar se está coberto pelo pedido original
    // Pode não gerar cobrança adicional conforme contrato
}
```

---

### 5. priority
- **Tipo**: String (Enum)
- **Obrigatório**: Não
- **Valores**:
  - `routine` - Rotina (prazo normal)
  - `urgent` - Urgente (prazo reduzido)
  - `stat` - Emergência (imediato)
  - `asap` - Assim que possível

**Impacto no Faturamento**:
- Exames STAT/urgentes podem ter acréscimo no valor
- SLA diferenciado para liberação de resultados

---

### 6. patientId
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Referência FHIR ao paciente
- **Formato**: `"Patient/{id}"`
- **Exemplo**: `"Patient/123456"`

**Uso**: Vinculação do exame ao paciente para faturamento

---

### 7. encounterId
- **Tipo**: String
- **Obrigatório**: Sim (para faturamento)
- **Descrição**: Referência ao encontro hospitalar
- **Formato**: `"Encounter/{id}"`
- **Exemplo**: `"Encounter/enc-789"`

**Importância Crítica**:
- **Faturamento**: Exames devem ser cobrados no contexto do encontro
- **Auditoria**: Valida que exame foi solicitado durante internação/consulta
- **Rastreabilidade**: Liga exame ao episódio de cuidado

---

### 8. orderingProviderId
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: ID do médico solicitante
- **Formato**: `"Practitioner/{id}"`
- **Exemplo**: `"Practitioner/dr-silva"`

**Validações**:
- Médico deve estar ativo no corpo clínico
- Deve ter CRM válido
- Necessário para auditoria regulatória (ANS, conselhos)

---

### 9. authoredOn
- **Tipo**: LocalDateTime
- **Obrigatório**: Sim
- **Descrição**: Data/hora da solicitação do exame
- **Formato ISO**: `2024-01-15T08:30:00`

**Regras de Negócio**:
```java
// RN-LIS-ORDER-01: Pedido deve ser dentro do período do encontro
if (order.getAuthoredOn().isBefore(encounter.getPeriod().getStart()) ||
    order.getAuthoredOn().isAfter(encounter.getPeriod().getEnd())) {
    throw new ValidationException("Pedido fora do período do encontro");
}
```

---

### 10. occurrenceDateTime
- **Tipo**: LocalDateTime
- **Obrigatório**: Não (mas crítico para faturamento)
- **Descrição**: Data/hora planejada/realizada da coleta

**Uso**:
- Data de realização para faturamento
- Cálculo de SLA (tempo até resultado)
- Validação de cobertura (vigência do plano)

---

### 11. testCodes (LOINC)
- **Tipo**: List<String>
- **Obrigatório**: Sim
- **Descrição**: Códigos LOINC dos testes solicitados
- **Sistema**: http://loinc.org

**Exemplos**:
```java
testCodes = ["718-7", "4544-3", "787-2"]
// 718-7: Hemoglobin
// 4544-3: Hematocrit
// 787-2: Erythrocyte MCV
```

**Mapeamento para Faturamento**:
```java
for (String loincCode : order.getTestCodes()) {
    String tissCode = codeMapper.loincToTiss(loincCode);
    BigDecimal valor = contratoService.getValor(tissCode, operadoraId);
    guiaItem.add(new GuiaItem(tissCode, valor, order.getOccurrenceDateTime()));
}
```

---

### 12. specimenIds
- **Tipo**: List<String>
- **Obrigatório**: Não
- **Descrição**: Referências às amostras biológicas coletadas
- **Formato**: `["Specimen/spec-001", "Specimen/spec-002"]`

**Uso**:
- Rastreamento de coleta de material
- Validação de procedimentos de coleta cobrados
- Auditoria de manuseio de amostras

---

### 13. category
- **Tipo**: String (CodeableConcept)
- **Obrigatório**: Sim
- **Valores Comuns**:
  - `laboratory` - Laboratório clínico
  - `radiology` - Radiologia (não deveria estar em LIS)
  - `pathology` - Anatomia patológica
  - `genetics` - Genética/Biologia molecular

**Validação**:
```java
if (!"laboratory".equals(order.getCategory())) {
    log.warn("Categoria inesperada no LIS: {}", order.getCategory());
}
```

---

### 14. reasonCode
- **Tipo**: String (SNOMED CT)
- **Obrigatório**: Não (recomendado para auditoria)
- **Descrição**: Código da justificativa clínica
- **Sistema**: http://snomed.info/sct

**Exemplos**:
- `267036007` - Dyslipidemia
- `73211009` - Diabetes mellitus
- `38341003` - Hypertensive disorder

**Uso em Auditoria**:
```java
// RN-LIS-ORDER-02: Validar coerência entre diagnóstico e exame
if (!isExamApplicableForDiagnosis(order.getTestCodes(), order.getReasonCode())) {
    auditAlert("Exame pode não ser coberto: incompatível com diagnóstico");
}
```

---

### 15. reasonReference
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Referência a uma Condition (diagnóstico) no EMR
- **Formato**: `"Condition/cond-123"`

**Uso**:
- Link direto ao diagnóstico que justifica o exame
- Mais completo que reasonCode (pode ter histórico, severidade, etc.)

---

### 16. requisitionSigned
- **Tipo**: Boolean
- **Obrigatório**: Não
- **Descrição**: Indica se requisição foi assinada digitalmente

**Importância Regulatória**:
- ANS exige assinatura digital em requisições
- Crítico para auditoria
- Pode bloquear faturamento se false

**Validação**:
```java
if (order.getRequisitionSigned() == null || !order.getRequisitionSigned()) {
    throw new ValidationException("Requisição não assinada - não pode faturar");
}
```

---

## Regras de Negócio

### RN-LISORDER-01: Validação de Status para Faturamento
**Descrição**: Apenas pedidos com status "completed" podem ser incluídos em guias TISS.

**Implementação**:
```java
public boolean isBillable(LISOrderDTO order) {
    return "completed".equals(order.getStatus()) &&
           order.getOccurrenceDateTime() != null &&
           order.getRequisitionSigned() != null &&
           order.getRequisitionSigned();
}
```

---

### RN-LISORDER-02: Pedidos Reflexos
**Descrição**: Pedidos reflexos (intent=reflex-order) devem verificar cobertura do pedido original.

**Fluxo**:
1. Identificar pedido original via reasonReference
2. Verificar se contrato cobre exames reflexos
3. Se não coberto, não faturar separadamente

```java
if ("reflex-order".equals(order.getIntent())) {
    if (!contratoService.coberturaExamesReflexos(operadoraId)) {
        log.info("Exame reflexo não cobrado separadamente: {}", order.getId());
        return; // Não adiciona à guia
    }
}
```

---

### RN-LISORDER-03: Validação de Médico Solicitante
**Descrição**: Médico solicitante deve estar cadastrado e com CRM ativo.

**Validação**:
```java
Practitioner medico = practitionerService.getById(order.getOrderingProviderId());
if (medico == null || !medico.isActive()) {
    throw new ValidationException("Médico solicitante inativo ou não cadastrado");
}

if (medico.getCrm() == null || !crmService.isValid(medico.getCrm())) {
    throw new ValidationException("CRM inválido: " + medico.getCrm());
}
```

---

### RN-LISORDER-04: Prazo de Solicitação
**Descrição**: Pedidos devem ser solicitados dentro do período do encontro (ou até 24h após alta).

**Implementação**:
```java
LocalDateTime limiteMax = encounter.getPeriod().getEnd().plusHours(24);

if (order.getAuthoredOn().isAfter(limiteMax)) {
    throw new ValidationException(
        "Pedido solicitado após prazo permitido (24h pós-alta)"
    );
}
```

---

## Mapeamento LOINC → TUSS

### Serviço de Mapeamento
```java
@Service
public class LISCodeMappingService {

    @Autowired
    private CodeMappingRepository mappingRepo;

    public String loincToTiss(String loincCode) {
        return mappingRepo.findTissByLoinc(loincCode)
            .orElseThrow(() -> new CodeMappingException(
                "Código LOINC não mapeado: " + loincCode
            ));
    }

    public List<GuiaItem> mapOrderToGuiaItems(LISOrderDTO order, String operadoraId) {
        List<GuiaItem> items = new ArrayList<>();

        for (String loincCode : order.getTestCodes()) {
            String tissCode = loincToTiss(loincCode);
            BigDecimal valor = contratoService.getValor(tissCode, operadoraId);

            GuiaItem item = new GuiaItem();
            item.setCodigoTUSS(tissCode);
            item.setQuantidade(1);
            item.setValorUnitario(valor);
            item.setDataRealizacao(order.getOccurrenceDateTime());

            items.add(item);
        }

        return items;
    }
}
```

---

## Exemplos de Uso

### Exemplo 1: Converter Pedido LIS para Itens de Guia
```java
@Service
public class BillingService {

    public List<GuiaItem> processLabOrders(String encounterId) {
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(encounterId, apiKey);
        List<GuiaItem> guiaItems = new ArrayList<>();

        for (LISOrderDTO order : orders) {
            // Validar se é faturável
            if (!isBillable(order)) {
                log.info("Pedido {} não faturável: status={}, signed={}",
                    order.getId(), order.getStatus(), order.getRequisitionSigned());
                continue;
            }

            // Mapear cada teste LOINC para item TISS
            for (String loincCode : order.getTestCodes()) {
                GuiaItem item = mapToGuiaItem(order, loincCode);
                guiaItems.add(item);
            }
        }

        return guiaItems;
    }

    private GuiaItem mapToGuiaItem(LISOrderDTO order, String loincCode) {
        GuiaItem item = new GuiaItem();
        item.setCodigoTUSS(codeMapper.loincToTiss(loincCode));
        item.setDataRealizacao(order.getOccurrenceDateTime());
        item.setQuantidade(1);

        // Acréscimo para exames urgentes
        if ("stat".equals(order.getPriority()) || "urgent".equals(order.getPriority())) {
            item.setAcrescimoUrgencia(BigDecimal.valueOf(1.5)); // 50% de acréscimo
        }

        return item;
    }
}
```

---

### Exemplo 2: Validação Pré-Faturamento
```java
@Service
public class PreBillingValidationService {

    public ValidationResult validateLabOrders(String encounterId) {
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(encounterId, apiKey);
        ValidationResult result = new ValidationResult();

        for (LISOrderDTO order : orders) {
            // Verificar status
            if (!"completed".equals(order.getStatus())) {
                result.addWarning(
                    "Pedido " + order.getIdentifier() + " ainda não completado"
                );
            }

            // Verificar assinatura
            if (order.getRequisitionSigned() == null || !order.getRequisitionSigned()) {
                result.addError(
                    "Requisição " + order.getIdentifier() + " não assinada"
                );
            }

            // Verificar médico solicitante
            if (!practitionerService.isActive(order.getOrderingProviderId())) {
                result.addError(
                    "Médico solicitante inativo: " + order.getOrderingProviderId()
                );
            }

            // Verificar mapeamento de códigos
            for (String loincCode : order.getTestCodes()) {
                try {
                    codeMapper.loincToTiss(loincCode);
                } catch (CodeMappingException e) {
                    result.addError(
                        "Código LOINC não mapeado: " + loincCode + " no pedido " + order.getIdentifier()
                    );
                }
            }
        }

        return result;
    }
}
```

---

## Referências Técnicas

1. **FHIR ServiceRequest**: http://hl7.org/fhir/R4/servicerequest.html
2. **LOINC Database**: https://loinc.org/
3. **SNOMED CT**: https://www.snomed.org/
4. **TISS/ANS**: Padrão brasileiro de troca de informações

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
