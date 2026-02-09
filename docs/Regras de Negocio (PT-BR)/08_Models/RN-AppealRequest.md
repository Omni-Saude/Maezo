# RN-AppealRequest - Solicitação de Recurso

**Categoria:** Modelo de Domínio - Entrada de Dados
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.AppealRequest`
**Tipo:** DTO (Data Transfer Object)

---

## Descrição
Objeto de requisição que encapsula todos os dados necessários para preparar um recurso de glosa. Usado como entrada para `AppealDocumentService` e estratégias de recurso.

## Estrutura

```java
@Data
@Builder
public class AppealRequest {
    private String glosaId;
    private String glosaType;
    private String appealStrategy;
    private String encounterId;
    private String providerId;
    private GlosaDetails glosaDetails;
}
```

## Atributos

### glosaId
- **Tipo:** String
- **Obrigatório:** Sim
- **Descrição:** Identificador único da glosa sendo recorrida
- **Formato:** UUID ou código sequencial
- **Exemplo:** "GLOSA-2024-001234"

### glosaType
- **Tipo:** String
- **Obrigatório:** Sim
- **Descrição:** Tipo/categoria da glosa
- **Valores Possíveis:**
  - "MEDICAL_NECESSITY" - Necessidade médica
  - "ADMINISTRATIVE" - Erro administrativo
  - "CODING" - Erro de codificação
  - "AUTHORIZATION" - Falta de autorização
  - "ELIGIBILITY" - Elegibilidade do paciente
  - "DUPLICATE" - Cobrança duplicada
- **Exemplo:** "MEDICAL_NECESSITY"

### appealStrategy
- **Tipo:** String
- **Obrigatório:** Sim
- **Descrição:** Estratégia a ser usada para o recurso
- **Valores Possíveis:**
  - "STANDARD" - Estratégia padrão
  - "MEDICAL_NECESSITY" - Necessidade médica
  - "COMPREHENSIVE_APPEAL" - Recurso abrangente
  - "QUICK_REVIEW_AND_RESUBMIT" - Revisão rápida
  - Outros definidos em `AppealStrategyRegistry`
- **Exemplo:** "MEDICAL_NECESSITY"

### encounterId
- **Tipo:** String
- **Obrigatório:** Condicional (obrigatório para estratégias clínicas)
- **Descrição:** Identificador do atendimento relacionado
- **Uso:** Buscar documentação clínica do prontuário
- **Exemplo:** "ENC-2024-789012"

### providerId
- **Tipo:** String
- **Obrigatório:** Sim
- **Descrição:** Identificador do prestador/médico responsável
- **Formato:** CRM ou código interno
- **Exemplo:** "CRM-SP-123456" ou "PROV-00789"

### glosaDetails
- **Tipo:** GlosaDetails
- **Obrigatório:** Sim
- **Descrição:** Objeto aninhado com detalhes específicos da glosa
- **Conteúdo:** Valores, códigos, motivos da negativa

## Regras de Negócio

### RN-APPEAL-REQ-001: Validação de Campos Obrigatórios
**Descrição:** Todos os campos obrigatórios devem estar preenchidos
**Validação:**
```java
if (glosaId == null || appealStrategy == null) {
    throw new IllegalArgumentException("Campos obrigatórios ausentes");
}
```

### RN-APPEAL-REQ-002: Encounter ID para Estratégias Clínicas
**Descrição:** encounterId é obrigatório quando estratégia requer documentação clínica
**Critério:**
```java
if (strategy.requiresClinicalDocumentation() && encounterId == null) {
    throw new IllegalArgumentException("encounterId obrigatório para estratégia clínica");
}
```

### RN-APPEAL-REQ-003: Validação de Estratégia
**Descrição:** appealStrategy deve ser uma estratégia registrada
**Implementação:** `AppealStrategyRegistry.getStrategy(appealStrategy)`

### RN-APPEAL-REQ-004: Consistência de Dados
**Descrição:** glosaType deve ser consistente com appealStrategy escolhida
**Exemplo:**
- glosaType="MEDICAL_NECESSITY" → appealStrategy="MEDICAL_NECESSITY" ou "COMPREHENSIVE_APPEAL"
- glosaType="ADMINISTRATIVE" → appealStrategy="STANDARD" ou "QUICK_REVIEW_AND_RESUBMIT"

## Uso no Sistema

### Construção via Builder
```java
AppealRequest request = AppealRequest.builder()
    .glosaId("GLOSA-2024-001234")
    .glosaType("MEDICAL_NECESSITY")
    .appealStrategy("MEDICAL_NECESSITY")
    .encounterId("ENC-2024-789012")
    .providerId("CRM-SP-123456")
    .glosaDetails(glosaDetails)
    .build();
```

### Fluxo de Processamento
```
1. PrepareGlosaAppealDelegate cria AppealRequest
   ↓
2. Popula com dados do processo BPMN
   ↓
3. Passa para AppealDocumentService.prepareAppealPackage(request)
   ↓
4. AppealDocumentService extrai:
   - appealStrategy → seleciona estratégia
   - encounterId → busca documentos clínicos
   - glosaDetails → gera conteúdo da carta
   ↓
5. Estratégia usa request para gerar documentos específicos
```

## Integração

### Criado Por
- `PrepareGlosaAppealDelegate` - Delegate BPMN
- Processos de workflow Camunda

### Usado Por
- `AppealDocumentService.prepareAppealPackage()` - Serviço principal
- `AppealStrategy.generateDocuments()` - Estratégias específicas
- `ClinicalDocumentCollector` - Coleta de documentos clínicos

### Dados de Origem
- **BPMN Variables:** glosaId, glosaType, appealStrategy
- **Database:** GlosaDetails, provider info
- **External Systems:** encounter data

## Modelo de Dados Relacionado

### GlosaDetails (nested)
```java
public class GlosaDetails {
    private String denialCode;
    private String denialReason;
    private BigDecimal glosaAmount;
    private String payerName;
    private LocalDateTime glosaDate;
    // outros campos
}
```

## Exemplos de Uso

### Exemplo 1: Recurso de Necessidade Médica
```java
AppealRequest request = AppealRequest.builder()
    .glosaId("GLO-2024-0001")
    .glosaType("MEDICAL_NECESSITY")
    .appealStrategy("MEDICAL_NECESSITY")
    .encounterId("ENC-2024-1234")
    .providerId("CRM-SP-98765")
    .glosaDetails(GlosaDetails.builder()
        .denialCode("NOT_MEDICALLY_NECESSARY")
        .denialReason("Procedimento considerado não necessário")
        .glosaAmount(new BigDecimal("15000.00"))
        .build())
    .build();
```

### Exemplo 2: Recurso Administrativo
```java
AppealRequest request = AppealRequest.builder()
    .glosaId("GLO-2024-0002")
    .glosaType("ADMINISTRATIVE")
    .appealStrategy("STANDARD")
    .providerId("PROV-456")
    .glosaDetails(GlosaDetails.builder()
        .denialCode("MISSING_AUTH")
        .denialReason("Autorização prévia não localizada")
        .glosaAmount(new BigDecimal("2500.00"))
        .build())
    .build();
// encounterId não é obrigatório para estratégia STANDARD
```

## Validação e Tratamento de Erros

### Validação na Criação
```java
public void validate() {
    if (glosaId == null || glosaId.isEmpty()) {
        throw new IllegalArgumentException("glosaId é obrigatório");
    }
    if (appealStrategy == null || appealStrategy.isEmpty()) {
        throw new IllegalArgumentException("appealStrategy é obrigatória");
    }
    if (glosaDetails == null) {
        throw new IllegalArgumentException("glosaDetails é obrigatório");
    }
}
```

### Tratamento de Erros
- **Campos ausentes:** `IllegalArgumentException`
- **Estratégia inválida:** Usa estratégia padrão (log warning)
- **encounterId ausente:** Documentação clínica não coletada

## Serialização

### JSON Example
```json
{
  "glosaId": "GLOSA-2024-001234",
  "glosaType": "MEDICAL_NECESSITY",
  "appealStrategy": "MEDICAL_NECESSITY",
  "encounterId": "ENC-2024-789012",
  "providerId": "CRM-SP-123456",
  "glosaDetails": {
    "denialCode": "NOT_MEDICALLY_NECESSARY",
    "denialReason": "Procedimento considerado não necessário",
    "glosaAmount": 15000.00
  }
}
```

## Performance

- **Imutabilidade:** Usar `@Builder` para construção segura
- **Validação Lazy:** Validar apenas quando necessário
- **Memória:** Objeto leve, apenas strings e referências

## Testes

**Arquivo:** `PrepareGlosaAppealDelegateTest.java`

Cenários testados:
- Criação via Builder
- Validação de campos obrigatórios
- Integração com AppealDocumentService
- Estratégias diferentes (STANDARD vs MEDICAL_NECESSITY)

## Conformidade

- **TISS 3.06.00:** Campos compatíveis com dados TISS
- **ANS RN 443/2019:** Suporta tipos de recurso regulamentados
- **LGPD:** Não contém dados sensíveis do paciente diretamente

## Referências
- `AppealDocumentService.java` - Serviço consumidor
- `AppealStrategy.java` - Interface de estratégias
- `GlosaDetails.java` - Objeto aninhado
- `PrepareGlosaAppealDelegate.java` - Criador do objeto
