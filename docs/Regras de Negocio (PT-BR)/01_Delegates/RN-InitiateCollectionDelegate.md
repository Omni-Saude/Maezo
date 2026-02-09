# RN-InitiateCollectionDelegate - Iniciação de Workflow de Cobrança

## Metadados
- **ID**: RN-InitiateCollectionDelegate
- **Categoria**: Cobrança (SUB_09_Collections)
- **Prioridade**: HIGH
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Última Atualização**: 2026-01-12
- **Status**: Ativo

## Referência de Implementação
- **Arquivo**: `/src/main/java/com/hospital/revenuecycle/delegates/collection/InitiateCollectionDelegate.java`
- **Bean BPMN**: `initiateCollection`
- **DMN Table**: `collection-workflow.dmn`

---

## Descrição Geral

O **InitiateCollectionDelegate** é o ponto de entrada do processo de cobrança. Este delegate avalia a situação financeira do paciente e determina a estratégia de cobrança, canal de contato e nível de escalação através de regras DMN (Decision Model and Notation).

**Contexto de Negócio:**
- A estratégia de cobrança deve ser proporcional ao tempo de atraso e valor devido
- Diferentes canais de contato têm diferentes taxas de sucesso e custos
- A escalação apropriada otimiza recursos e melhora recovery rate

---

## Regras de Negócio

### RN-ICO-001: Avaliação DMN de Estratégia
**Descrição:** Utilizar tabela DMN `collection-workflow.dmn` para determinar estratégia, canal de contato e nível de escalação.

**Inputs DMN:**
- `amountDue`: Valor devido (BigDecimal)
- `daysPastDue`: Dias de atraso (Integer)

**Outputs DMN:**
- `strategy`: Estratégia de cobrança (String: "friendly", "formal", "legal")
- `contactMethod`: Canal de contato (String: "whatsapp", "sms", "email", "phone")
- `escalationLevel`: Nível de urgência (Integer: 1-3)

**Implementação:**
```java
Map<String, Object> dmnResult = evaluateDMN(
    execution,
    "collection-workflow",
    dmnVariables
);

collectionStrategy = (String) dmnResult.getOrDefault("strategy", "friendly");
contactMethod = (String) dmnResult.getOrDefault("contactMethod", "whatsapp");
escalationLevel = (Integer) dmnResult.getOrDefault("escalationLevel", 1);
```

---

### RN-ICO-002: Estratégias de Cobrança (Fallback)
**Descrição:** Quando DMN não está disponível, aplicar lógica de fallback baseada em dias de atraso.

**Regras de Fallback:**

| Dias de Atraso | Estratégia | Justificativa |
|----------------|------------|---------------|
| 0-15 dias | `friendly` | Abordagem amigável, pode ser esquecimento |
| 16-45 dias | `formal` | Abordagem formal, mais assertiva |
| 46+ dias | `legal` | Abordagem legal, preparação para ações judiciais |

**Implementação:**
```java
private String determineDefaultStrategy(Integer daysPastDue) {
    if (daysPastDue <= 15) {
        return "friendly";
    } else if (daysPastDue <= 45) {
        return "formal";
    } else {
        return "legal";
    }
}
```

---

### RN-ICO-003: Método de Contato (Fallback)
**Descrição:** Quando DMN não está disponível, selecionar canal baseado no valor devido.

**Regras de Fallback:**

| Valor Devido | Método | Justificativa |
|--------------|--------|---------------|
| > $1000 | `phone` | Valores altos requerem contato direto |
| $500 - $1000 | `sms` | Balanceamento entre custo e efetividade |
| < $500 | `whatsapp` | Custo mais baixo para valores menores |

**Implementação:**
```java
private String determineContactMethod(BigDecimal amountDue) {
    if (amountDue.compareTo(new BigDecimal("1000")) > 0) {
        return "phone";
    } else if (amountDue.compareTo(new BigDecimal("500")) > 0) {
        return "sms";
    } else {
        return "whatsapp";
    }
}
```

---

### RN-ICO-004: Nível de Escalação (Fallback)
**Descrição:** Quando DMN não está disponível, determinar prioridade baseada em dias de atraso.

**Regras de Fallback:**

| Dias de Atraso | Nível | Descrição |
|----------------|-------|-----------|
| 0-15 dias | 1 | Baixa prioridade - reminder suave |
| 16-45 dias | 2 | Média prioridade - follow-up ativo |
| 46+ dias | 3 | Alta prioridade - ação legal iminente |

**Implementação:**
```java
private Integer determineEscalationLevel(Integer daysPastDue) {
    if (daysPastDue <= 15) {
        return 1;
    } else if (daysPastDue <= 45) {
        return 2;
    } else {
        return 3;
    }
}
```

---

### RN-ICO-005: Armazenamento de Detalhes de Cobrança
**Descrição:** Armazenar todos os parâmetros e decisões em objeto serializado para rastreamento e auditoria.

**Campos Armazenados:**
- `patientId`: Identificador do paciente
- `amountDue`: Valor devido
- `daysPastDue`: Dias de atraso
- `strategy`: Estratégia determinada
- `contactMethod`: Canal de contato selecionado
- `escalationLevel`: Nível de escalação
- `initiatedAt`: Timestamp de início

**Implementação:**
```java
Map<String, Object> collectionDetails = new HashMap<>();
collectionDetails.put("patientId", patientId);
collectionDetails.put("amountDue", amountDue);
collectionDetails.put("daysPastDue", daysPastDue);
collectionDetails.put("strategy", collectionStrategy);
collectionDetails.put("contactMethod", contactMethod);
collectionDetails.put("escalationLevel", escalationLevel);
collectionDetails.put("initiatedAt", java.time.LocalDateTime.now().toString());

ObjectValue collectionDetailsValue = Variables.objectValue(collectionDetails)
    .serializationDataFormat(Variables.SerializationDataFormats.JSON)
    .create();
execution.setVariable("collectionDetails", collectionDetailsValue);
```

---

## Variáveis do Processo BPMN

### Variáveis de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `patientId` | String | Sim | Identificador do paciente |
| `amountDue` | BigDecimal | Sim | Valor devido pelo paciente |
| `daysPastDue` | Integer | Sim | Número de dias que pagamento está atrasado |

### Variáveis de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `collectionStrategy` | String | Estratégia determinada ("friendly", "formal", "legal") |
| `contactMethod` | String | Método de contato ("whatsapp", "sms", "email", "phone") |
| `escalationLevel` | Integer | Nível de urgência (1-3) |
| `collectionInitiated` | Boolean | Sempre `true` após execução bem-sucedida |
| `collectionDetails` | ObjectValue | Objeto JSON com todos os detalhes da cobrança |

---

## Tabela DMN - collection-workflow.dmn

### Estrutura da Decisão

**Decision ID**: `determine_collection_strategy`

**Input Columns:**
1. `amountDue` (number)
2. `daysPastDue` (number)

**Output Columns:**
1. `strategy` (string)
2. `contactMethod` (string)
3. `escalationLevel` (number)

### Regras DMN Exemplo

| # | amountDue | daysPastDue | → strategy | → contactMethod | → escalationLevel |
|---|-----------|-------------|-----------|-----------------|-------------------|
| 1 | < 500 | ≤ 15 | friendly | whatsapp | 1 |
| 2 | < 500 | 16-45 | formal | sms | 2 |
| 3 | < 500 | > 45 | legal | email | 3 |
| 4 | 500-1000 | ≤ 15 | friendly | sms | 1 |
| 5 | 500-1000 | 16-45 | formal | sms | 2 |
| 6 | 500-1000 | > 45 | legal | phone | 3 |
| 7 | > 1000 | ≤ 15 | friendly | phone | 1 |
| 8 | > 1000 | 16-45 | formal | phone | 2 |
| 9 | > 1000 | > 45 | legal | phone | 3 |

**Hit Policy:** FIRST (primeira regra que satisfaz condições)

---

## Cenários de Teste

### CT-ICO-001: DMN - Valor Baixo, Atraso Curto
**Dado:**
- `amountDue` = $300
- `daysPastDue` = 10

**Quando:** Avaliar via DMN

**Então:**
- `collectionStrategy` = "friendly"
- `contactMethod` = "whatsapp"
- `escalationLevel` = 1

---

### CT-ICO-002: DMN - Valor Alto, Atraso Longo
**Dado:**
- `amountDue` = $2000
- `daysPastDue` = 60

**Quando:** Avaliar via DMN

**Então:**
- `collectionStrategy` = "legal"
- `contactMethod` = "phone"
- `escalationLevel` = 3

---

### CT-ICO-003: Fallback - DMN Indisponível
**Dado:**
- `amountDue` = $800
- `daysPastDue` = 30
- DMN evaluation lança exceção

**Quando:** Aplicar lógica de fallback

**Então:**
- `collectionStrategy` = "formal" (16-45 dias)
- `contactMethod` = "sms" ($500-$1000)
- `escalationLevel` = 2
- Warning log gerado

---

### CT-ICO-004: Armazenamento de Detalhes
**Dado:**
- Qualquer combinação válida de inputs

**Quando:** Processo executa

**Então:**
- `collectionDetails` contém JSON serializado com todos os campos
- `collectionInitiated` = true
- Timestamp de início registrado

---

## Métricas e KPIs

### Distribuição de Estratégias
- **% Friendly**: Porcentagem de cobranças amigáveis
- **% Formal**: Porcentagem de cobranças formais
- **% Legal**: Porcentagem de cobranças legais

### Distribuição de Canais
- **% WhatsApp**: Uso de WhatsApp
- **% SMS**: Uso de SMS
- **% Email**: Uso de Email
- **% Phone**: Uso de ligação telefônica

### Escalação
- **Nível 1 (Baixo)**: Contagem
- **Nível 2 (Médio)**: Contagem
- **Nível 3 (Alto)**: Contagem

### Efetividade DMN
- **DMN Success Rate**: % de avaliações DMN bem-sucedidas
- **Fallback Rate**: % de uso de lógica de fallback

---

## Considerações de Segurança

### Validação de Inputs
- Validar que `amountDue` é positivo
- Validar que `daysPastDue` é não-negativo
- Sanitizar `patientId` para prevenir injection

### Proteção de Dados
- `collectionDetails` contém dados sensíveis - criptografar em repouso
- Aplicar LGPD/HIPAA ao armazenar informações de pacientes

### Auditoria
- Toda iniciação de cobrança deve ser auditada
- Registrar estratégia determinada e justificativa
- Manter histórico para análise de efetividade

---

## Observações de Implementação

### Tratamento de Exceção DMN
```java
try {
    Map<String, Object> dmnResult = evaluateDMN(
        execution,
        "collection-workflow",
        dmnVariables
    );
    // Process DMN result
} catch (Exception e) {
    logger.warn("DMN evaluation failed, using default strategy", e);
    // Fallback logic
    collectionStrategy = determineDefaultStrategy(daysPastDue);
    contactMethod = determineContactMethod(amountDue);
    escalationLevel = determineEscalationLevel(daysPastDue);
}
```

### Formato de Serialização
Utilizar JSON para compatibilidade com front-end e APIs externas:
```java
ObjectValue collectionDetailsValue = Variables.objectValue(collectionDetails)
    .serializationDataFormat(Variables.SerializationDataFormats.JSON)
    .create();
```

### Logging Estruturado
```java
logger.info("Initiating collection for patient: {}, Amount due: {}, Days past due: {}",
            patientId, amountDue, daysPastDue);

logger.info("DMN determined strategy: {}, Contact: {}, Escalation: {}",
            collectionStrategy, contactMethod, escalationLevel);
```

---

## Referências
- DMN (Decision Model and Notation) Specification 1.3
- Camunda DMN Engine Documentation
- BPMN Process: SUB_09_Collections
- Collection Best Practices Guide

---

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Versão inicial com DMN e fallback logic |
