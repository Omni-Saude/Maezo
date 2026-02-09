# RN-PrepareBillingMessageDelegate - Preparação de Mensagem de Faturamento

## Identificação
- **ID**: RN-MSG-001
- **Nome**: PrepareBillingMessageDelegate
- **Categoria**: Messaging/Kafka
- **Versão**: 1.0.0
- **Bean BPMN**: `prepareBillingMessageDelegate`
- **Autor**: AI Swarm - Forensics Delegate Generation

## Visão Geral
Delegate responsável por preparar mensagem de faturamento para publicação em Kafka, serializando dados da guia em formato compatível com Avro/JSON Schema.

## Responsabilidades

### 1. Preparação de Mensagem
- Extrai dados essenciais da guia (claimId)
- Cria estrutura de mensagem Kafka
- Define tipo de evento (BILLING_COMPLETE)
- Serializa para formato compatível com schema

### 2. Integração com Kafka
- Prepara payload para tópico Kafka
- Mantém compatibilidade com schema Avro/JSON
- Habilita processamento assíncrono downstream

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `claimId` | String | Sim | Identificador único da guia de faturamento |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `kafkaMessage` | Map&lt;String, Object&gt; | Mensagem serializada pronta para Kafka |

## Estrutura da Mensagem Kafka

```json
{
  "claimId": "GUIA-2025-001",
  "event": "BILLING_COMPLETE"
}
```

**Campos**:
- `claimId`: Identificador da guia
- `event`: Tipo de evento (sempre "BILLING_COMPLETE")

## Algoritmo

```
1. Validar entrada:
   - claimId não pode ser nulo/vazio

2. Criar estrutura de mensagem:
   - Map<String, Object> message = new HashMap<>()
   - message.put("claimId", claimId)
   - message.put("event", "BILLING_COMPLETE")

3. Persistir mensagem:
   - setVariable("kafkaMessage", message)

4. Registrar log:
   - log.info("prepareBillingMessageDelegate completed for claim {}", claimId)
```

## Integração com Kafka

### Tópico Kafka
- **Tópico**: `billing-events` (configurável)
- **Formato**: Avro ou JSON Schema
- **Particionamento**: Por `claimId` (garante ordem)

### Schema Avro Sugerido
```json
{
  "type": "record",
  "name": "BillingCompleteEvent",
  "namespace": "com.hospital.revenuecycle.events",
  "fields": [
    {"name": "claimId", "type": "string"},
    {"name": "event", "type": "string", "default": "BILLING_COMPLETE"},
    {"name": "timestamp", "type": "long", "logicalType": "timestamp-millis"}
  ]
}
```

## Casos de Uso

### Caso 1: Preparação Bem-Sucedida
**Entrada**:
```json
{
  "claimId": "GUIA-2025-12345"
}
```

**Saída**:
```json
{
  "kafkaMessage": {
    "claimId": "GUIA-2025-12345",
    "event": "BILLING_COMPLETE"
  }
}
```

**Log**:
```
INFO: prepareBillingMessageDelegate completed for claim GUIA-2025-12345
```

### Caso 2: Múltiplas Guias
**Execução sequencial** para cada guia:
```
claimId: GUIA-001 → kafkaMessage: {"claimId": "GUIA-001", "event": "BILLING_COMPLETE"}
claimId: GUIA-002 → kafkaMessage: {"claimId": "GUIA-002", "event": "BILLING_COMPLETE"}
claimId: GUIA-003 → kafkaMessage: {"claimId": "GUIA-003", "event": "BILLING_COMPLETE"}
```

## Regras de Negócio

### RN-MSG-001-001: Claim ID Obrigatório
- **Descrição**: Claim ID deve ser fornecido
- **Prioridade**: CRÍTICA
- **Validação**: `claimId != null && !claimId.isEmpty()`

### RN-MSG-001-002: Formato de Evento Fixo
- **Descrição**: Evento deve ser sempre "BILLING_COMPLETE"
- **Prioridade**: ALTA
- **Validação**: `event == "BILLING_COMPLETE"`

### RN-MSG-001-003: Serialização Kafka
- **Descrição**: Mensagem deve ser serializável em JSON/Avro
- **Prioridade**: ALTA
- **Validação**: `message instanceof Map<String, Object>`

## Fluxo de Publicação Kafka

```
1. PrepareBillingMessageDelegate
   ↓ (cria kafkaMessage)
2. SendBillingCompleteDelegate
   ↓ (publica em Kafka)
3. KafkaProducer
   ↓ (serializa Avro/JSON)
4. Kafka Broker (tópico: billing-events)
   ↓
5. Consumidores Downstream:
   - Sistema de BI/Analytics
   - Sistema de Auditoria
   - Sistema de Notificações
```

## Extensões Futuras

### Campos Adicionais Sugeridos
```java
message.put("claimId", claimId);
message.put("event", "BILLING_COMPLETE");
message.put("timestamp", System.currentTimeMillis());
message.put("processInstanceId", execution.getProcessInstanceId());
message.put("claimAmount", execution.getVariable("finalAmount"));
message.put("payerId", execution.getVariable("payerId"));
message.put("patientId", execution.getVariable("patientId"));
message.put("submissionDate", LocalDateTime.now().toString());
```

### Validação de Schema
```java
// Validar conformidade com Avro Schema antes de publicar
SchemaValidator validator = new SchemaValidator(avroSchema);
if (!validator.validate(message)) {
    throw new BpmnError("SCHEMA_VALIDATION_FAILED",
        "Message does not conform to billing event schema");
}
```

## Dependências
- Nenhuma dependência externa (operação simples de preparação)
- Coordenação com `SendBillingCompleteDelegate` para publicação

## Relacionamento com Outros Delegates

### Delegates Relacionados
- **SendBillingCompleteDelegate**: Consome `kafkaMessage` e publica em Kafka
- **SendMessageDelegate**: Delegate genérico que também publica mensagens
- **PrepareDenialsMessageDelegate**: Delegate similar para eventos de glosa

### Fluxo BPMN Típico
```
[Billing Process]
    ↓
[PrepareBillingMessageDelegate] (prepara mensagem)
    ↓
[SendBillingCompleteDelegate] (publica em Kafka)
    ↓
[End Event]
```

## Idempotência

**Requer Idempotência**: Não

**Justificativa**: Preparação de mensagem é operação stateless e pode ser executada múltiplas vezes sem efeitos colaterais.

## Versionamento
- **v1.0.0**: Implementação inicial com estrutura básica de mensagem

## Referências
- RN-SendBillingCompleteDelegate: Documentação de publicação de eventos
- RN-SendMessageDelegate: Documentação de mensagens genéricas
- Kafka Documentation: https://kafka.apache.org/documentation/
- Avro Specification: https://avro.apache.org/docs/current/spec.html
