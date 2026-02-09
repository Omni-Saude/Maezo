# RN-CollectExternalDelegate - Submissão para Agência de Cobrança Externa

## Metadados
- **ID**: RN-CollectExternalDelegate
- **Categoria**: Cobrança (SUB_09_Collections)
- **Prioridade**: HIGH
- **Versão**: 2.0
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Última Atualização**: 2026-01-12
- **Status**: Ativo

## Referência de Implementação
- **Arquivo**: `/src/main/java/com/hospital/revenuecycle/delegates/collection/CollectExternalDelegate.java`
- **Bean BPMN**: `collectExternalDelegate`
- **Integration**: `CollectionAgencyClient`

---

## Descrição Geral

O **CollectExternalDelegate** gerencia a submissão de contas inadimplentes para agências de cobrança externas quando os esforços internos de cobrança foram esgotados. Este delegate implementa integração com APIs de agências de cobrança, incluindo circuit breaker para resiliência.

**Contexto de Negócio:**
- Contas com mais de 90 dias de atraso geralmente requerem cobrança externa
- Submissão para cobrança externa tem implicações legais e regulatórias
- Integração com agências deve ser resiliente e rastreável para compliance

---

## Regras de Negócio

### RN-CEX-001: Critério de Elegibilidade - Dias de Atraso
**Descrição:** Contas devem estar no mínimo 90 dias em atraso para submissão à cobrança externa.

**Condições:**
- `days_past_due >= 90` (recomendado)
- `days_past_due < 90` gera warning mas não impede submissão

**Implementação:**
```java
if (daysPastDue < 90) {
    log.warn("Account not yet eligible for external collection (< 90 days) - AccountNumber: {}, Days: {}",
            accountNumber, daysPastDue);
    setVariable(execution, "collection_warning",
        "Account not yet eligible (minimum 90 days past due)");
}
```

**Justificativa:** Políticas de cobrança e boas práticas da indústria recomendam esgotar tentativas internas antes de submissão externa.

---

### RN-CEX-002: Validação de Saldo Devedor
**Descrição:** O saldo devedor deve ser positivo para submissão à cobrança.

**Condições:**
- `balance_owed > 0`

**BPMN Error:** `INVALID_BALANCE` - "Cannot submit zero or negative balance to collection"

**Implementação:**
```java
if (balanceOwed.compareTo(BigDecimal.ZERO) <= 0) {
    throw new BpmnError("INVALID_BALANCE",
        "Cannot submit zero or negative balance to collection");
}
```

---

### RN-CEX-003: Construção de Requisição de Cobrança
**Descrição:** A requisição para a agência de cobrança deve conter todos os dados necessários para contato e cobrança.

**Campos Obrigatórios:**
- `accountNumber`: Número da conta/fatura
- `patientId`: Identificador do paciente
- `patientName`: Nome completo do paciente
- `balanceOwed`: Valor devido
- `daysPastDue`: Dias de atraso

**Campos Opcionais:**
- `lastPaymentDate`: Data do último pagamento
- `contactPhone`: Telefone de contato
- `contactEmail`: Email de contato

**Estrutura:**
```java
CollectionRequest request = CollectionRequest.builder()
    .accountNumber(accountNumber)
    .patientId(patientId)
    .patientName(patientName)
    .balanceOwed(balanceOwed)
    .lastPaymentDate(lastPaymentDate)
    .daysPastDue(daysPastDue)
    .contactPhone(contactPhone)
    .contactEmail(contactEmail)
    .build();
```

---

### RN-CEX-004: Tratamento de Respostas da Agência
**Descrição:** A resposta da agência de cobrança deve ser processada e armazenada.

**Campos da Resposta:**
- `isAccepted()`: Boolean indicando se agência aceitou a conta
- `getCollectionCaseId()`: ID do caso na agência
- `getStatus()`: Status da submissão
- `getMessage()`: Mensagem adicional

**Cenários:**

**Cenário A: Aceito**
```java
if (response.isAccepted()) {
    setVariable(execution, "collection_submitted", true);
    setVariable(execution, "collection_case_id", response.getCollectionCaseId());
    // Prosseguir com notificações
}
```

**Cenário B: Rejeitado**
```java
if (!response.isAccepted()) {
    throw new BpmnError("COLLECTION_REJECTED",
        "Collection agency rejected account: " + response.getMessage());
}
```

---

### RN-CEX-005: Circuit Breaker e Retry
**Descrição:** Integração com agência de cobrança implementa circuit breaker para resiliência.

**Comportamento:**
- Abre após 5 falhas consecutivas
- Fallback para fila de submissão manual
- Retry automático conforme configuração do cliente

**Implementação:** Circuit breaker é gerenciado pelo `CollectionAgencyClient` (anotação @CircuitBreaker ou Resilience4j).

---

### RN-CEX-006: Notificações Pós-Submissão
**Descrição:** Após submissão bem-sucedida, notificar paciente e equipe de compliance.

**Notificações Requeridas:**
- **Paciente**: Notificação formal de submissão para cobrança externa
- **Compliance**: Registro para auditoria regulatória

**Variáveis Definidas:**
```java
setVariable(execution, "notification_type", "COLLECTION_NOTICE");
setVariable(execution, "notify_patient", true);
setVariable(execution, "notify_compliance", true);
```

---

### RN-CEX-007: Idempotência de Submissão
**Descrição:** Múltiplas execuções com a mesma conta não devem criar duplicatas na agência.

**Implementação:**
```java
@Override
public boolean requiresIdempotency() {
    return true;
}
```

**Mecanismo:** `CollectionAgencyClient` deve verificar se conta já foi submetida antes de criar novo caso.

---

## Variáveis do Processo BPMN

### Variáveis de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `account_number` | String | Sim | Número da conta/fatura |
| `patient_id` | String | Sim | Identificador do paciente |
| `patient_name` | String | Sim | Nome completo do paciente |
| `balance_owed` | BigDecimal | Sim | Saldo devedor |
| `days_past_due` | Integer | Sim | Dias de atraso |
| `last_payment_date` | LocalDate | Não | Data do último pagamento |
| `contact_phone` | String | Não | Telefone de contato |
| `contact_email` | String | Não | Email de contato |

### Variáveis de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `collection_submitted` | Boolean | Indica se submissão foi bem-sucedida |
| `collection_case_id` | String | ID do caso na agência de cobrança |
| `collection_status` | String | Status retornado pela agência |
| `submitted_to_collection_date` | LocalDate | Data de submissão |
| `collection_agency_response` | String | Mensagem completa da resposta |
| `notification_type` | String | "COLLECTION_NOTICE" |
| `notify_patient` | Boolean | `true` para notificar paciente |
| `notify_compliance` | Boolean | `true` para notificar compliance |

**Em caso de warning:**
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `collection_warning` | String | Warning sobre elegibilidade (< 90 dias) |

**Em caso de erro:**
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `collection_submitted` | Boolean | `false` |
| `collection_error` | String | Mensagem de erro técnico |

---

## Eventos de Erro BPMN

### INVALID_BALANCE
- **Quando:** Saldo devedor é zero ou negativo
- **Mensagem:** "Cannot submit zero or negative balance to collection"
- **Ação Recomendada:** Verificar cálculos de saldo antes de submissão

### COLLECTION_REJECTED
- **Quando:** Agência de cobrança rejeita a conta
- **Mensagem:** "Collection agency rejected account: {motivo}"
- **Motivos Comuns:**
  - Informações de contato insuficientes
  - Valor muito baixo (abaixo do mínimo da agência)
  - Conta já em cobrança
  - Paciente falecido ou em falência
- **Ação Recomendada:** Revisar dados e reclassificar conta

### SUBMISSION_FAILED
- **Quando:** Falha técnica na integração com agência
- **Mensagem:** "Technical failure in collection submission: {detalhes}"
- **Ação Recomendada:** Verificar conectividade, tentar novamente ou usar fallback manual

---

## Integrações

### CollectionAgencyClient
**Método:** `submitToCollection(CollectionRequest request)`

**Funcionalidades:**
- Integração via REST API com agência de cobrança
- Circuit breaker para resiliência (5 falhas consecutivas)
- Retry automático (exponential backoff)
- Fallback para fila de submissão manual

**Request:**
```json
{
  "accountNumber": "ACC-12345",
  "patientId": "PAT-67890",
  "patientName": "João Silva",
  "balanceOwed": 5000.00,
  "lastPaymentDate": "2025-08-15",
  "daysPastDue": 120,
  "contactPhone": "+55119876543210",
  "contactEmail": "joao.silva@email.com"
}
```

**Response:**
```json
{
  "accepted": true,
  "collectionCaseId": "COLL-20260112-0001",
  "status": "ACCEPTED",
  "message": "Account submitted successfully for collection"
}
```

---

## Cenários de Teste

### CT-CEX-001: Submissão Bem-Sucedida
**Dado:**
- Conta com $2500 de saldo devedor
- 120 dias em atraso
- Informações de contato completas

**Quando:** Submeter para cobrança externa

**Então:**
- `collection_submitted` = true
- `collection_case_id` retornado
- `collection_status` = "ACCEPTED"
- Notificações configuradas (paciente e compliance)

---

### CT-CEX-002: Warning - Menos de 90 Dias
**Dado:**
- Conta com $1000 de saldo devedor
- 60 dias em atraso

**Quando:** Submeter para cobrança externa

**Então:**
- Warning gerado: "Account not yet eligible (minimum 90 days past due)"
- Submissão prossegue normalmente
- `collection_warning` contém mensagem

---

### CT-CEX-003: Erro - Saldo Inválido
**Dado:**
- Conta com saldo $0
- 150 dias em atraso

**Quando:** Submeter para cobrança externa

**Então:**
- BPMN Error `INVALID_BALANCE` lançado
- `collection_submitted` = false

---

### CT-CEX-004: Erro - Agência Rejeita
**Dado:**
- Conta com $50 de saldo devedor (abaixo do mínimo)
- 100 dias em atraso

**Quando:** Submeter para cobrança externa

**Então:**
- BPMN Error `COLLECTION_REJECTED` lançado
- `collection_agency_response` contém motivo da rejeição
- `collection_submitted` = false

---

### CT-CEX-005: Erro - Falha de Integração
**Dado:**
- Agência de cobrança offline (API indisponível)

**Quando:** Submeter para cobrança externa

**Então:**
- Circuit breaker ativa após 5 tentativas
- BPMN Error `SUBMISSION_FAILED` lançado
- Fallback para fila manual

---

## Métricas e KPIs

### Operacionais
- **Taxa de Aceitação**: % de contas aceitas pela agência
- **Taxa de Rejeição por Motivo**: % de rejeições categorizadas
- **Valor Médio Submetido**: Média dos valores enviados para cobrança

### Performance
- **Tempo Médio de Submissão**: < 2 segundos
- **Taxa de Falha de Integração**: < 1%
- **Circuit Breaker Open Rate**: Frequência de ativação

### Compliance
- **Total de Contas em Cobrança Externa**: Contagem ativa
- **Valor Total em Cobrança**: Soma dos valores submetidos
- **Aging de Contas antes de Submissão**: Distribuição em dias

---

## Considerações de Segurança

### Proteção de Dados (LGPD/HIPAA)
- Dados sensíveis do paciente devem ser transmitidos via HTTPS
- Minimizar dados pessoais compartilhados com agência
- Obter consentimento do paciente quando requerido por lei

### Auditoria
- Toda submissão deve gerar entrada em log de auditoria
- Armazenar resposta completa da agência
- Rastrear histórico de tentativas

### Compliance Regulatório
- Seguir Fair Debt Collection Practices Act (FDCPA) nos EUA
- Respeitar Código de Defesa do Consumidor no Brasil
- Notificar paciente conforme legislação local

---

## Observações de Implementação

### Configuração de Agência
Configurações via variáveis de ambiente ou application.yml:
```yaml
collection:
  agency:
    api-url: https://api.collectionagency.com
    api-key: ${COLLECTION_AGENCY_API_KEY}
    timeout: 5000
    retry:
      max-attempts: 3
      backoff-period: 2000
    circuit-breaker:
      failure-threshold: 5
      timeout: 60000
```

### Fallback Manual
Quando circuit breaker está aberto:
```java
// Adicionar à fila de processamento manual
manualQueueService.addToQueue(CollectionTask.builder()
    .accountNumber(accountNumber)
    .patientId(patientId)
    .balanceOwed(balanceOwed)
    .reason("API_UNAVAILABLE")
    .build());
```

---

## Referências
- Fair Debt Collection Practices Act (FDCPA)
- Código de Defesa do Consumidor (Brasil)
- BPMN Process: SUB_09_Collections
- Integration: CollectionAgencyClient
- Circuit Breaker Pattern (Resilience4j)

---

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 2.0 | 2026-01-09 | Revenue Cycle Team | Adição de circuit breaker e notificações |
| 1.0 | 2025-10-15 | Revenue Cycle Team | Versão inicial com integração básica |
