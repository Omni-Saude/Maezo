# RN-PrepareDenialsMessageDelegate - Preparação de Mensagem de Glosas

## Identificação
- **ID**: RN-MSG-002
- **Nome**: PrepareDenialsMessageDelegate
- **Categoria**: Messaging/Kafka
- **Versão**: 1.0.0
- **Bean BPMN**: `prepareDenialsMessageDelegate`
- **Autor**: AI Swarm - Forensics Delegate Generation

## Visão Geral
Delegate responsável por preparar mensagem de glosas (denials) para publicação em Kafka, serializando dados de glosa processada em formato compatível com schema.

## Responsabilidades

### 1. Preparação de Mensagem
- Extrai dados essenciais da glosa (glosaId)
- Cria estrutura de mensagem Kafka
- Define tipo de evento (DENIAL_PROCESSED)
- Serializa para formato compatível com schema

### 2. Integração com Kafka
- Prepara payload para tópico Kafka
- Mantém compatibilidade com schema Avro/JSON
- Habilita processamento assíncrono downstream

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaId` | String | Sim | Identificador único da glosa |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `kafkaMessage` | Map&lt;String, Object&gt; | Mensagem serializada pronta para Kafka |

## Estrutura da Mensagem Kafka

```json
{
  "glosaId": "GLOSA-2025-001",
  "event": "DENIAL_PROCESSED"
}
```

**Campos**:
- `glosaId`: Identificador da glosa
- `event`: Tipo de evento (sempre "DENIAL_PROCESSED")

## Algoritmo

```
1. Validar entrada:
   - glosaId não pode ser nulo/vazio

2. Criar estrutura de mensagem:
   - Map<String, Object> message = new HashMap<>()
   - message.put("glosaId", glosaId)
   - message.put("event", "DENIAL_PROCESSED")

3. Persistir mensagem:
   - setVariable("kafkaMessage", message)

4. Registrar log:
   - log.info("prepareDenialsMessageDelegate completed for glosa {}", glosaId)
```

## Integração com Kafka

### Tópico Kafka
- **Tópico**: `denials-events` (configurável)
- **Formato**: Avro ou JSON Schema
- **Particionamento**: Por `glosaId` (garante ordem)

### Schema Avro Sugerido
```json
{
  "type": "record",
  "name": "DenialProcessedEvent",
  "namespace": "com.hospital.revenuecycle.events",
  "fields": [
    {"name": "glosaId", "type": "string"},
    {"name": "event", "type": "string", "default": "DENIAL_PROCESSED"},
    {"name": "timestamp", "type": "long", "logicalType": "timestamp-millis"},
    {"name": "glosaStatus", "type": ["null", "string"], "default": null},
    {"name": "glosaAmount", "type": ["null", "double"], "default": null}
  ]
}
```

## Casos de Uso

### Caso 1: Preparação Bem-Sucedida
**Entrada**:
```json
{
  "glosaId": "GLOSA-2025-00123"
}
```

**Saída**:
```json
{
  "kafkaMessage": {
    "glosaId": "GLOSA-2025-00123",
    "event": "DENIAL_PROCESSED"
  }
}
```

**Log**:
```
INFO: prepareDenialsMessageDelegate completed for glosa GLOSA-2025-00123
```

### Caso 2: Múltiplas Glosas
**Execução sequencial** para cada glosa:
```
glosaId: GLOSA-001 → kafkaMessage: {"glosaId": "GLOSA-001", "event": "DENIAL_PROCESSED"}
glosaId: GLOSA-002 → kafkaMessage: {"glosaId": "GLOSA-002", "event": "DENIAL_PROCESSED"}
glosaId: GLOSA-003 → kafkaMessage: {"glosaId": "GLOSA-003", "event": "DENIAL_PROCESSED"}
```

## Regras de Negócio

### RN-MSG-002-001: Glosa ID Obrigatório
- **Descrição**: Glosa ID deve ser fornecido
- **Prioridade**: CRÍTICA
- **Validação**: `glosaId != null && !glosaId.isEmpty()`

### RN-MSG-002-002: Formato de Evento Fixo
- **Descrição**: Evento deve ser sempre "DENIAL_PROCESSED"
- **Prioridade**: ALTA
- **Validação**: `event == "DENIAL_PROCESSED"`

### RN-MSG-002-003: Serialização Kafka
- **Descrição**: Mensagem deve ser serializável em JSON/Avro
- **Prioridade**: ALTA
- **Validação**: `message instanceof Map<String, Object>`

## Fluxo de Publicação Kafka

```
1. PrepareDenialsMessageDelegate
   ↓ (cria kafkaMessage)
2. SendDenialsCompleteDelegate
   ↓ (publica em Kafka)
3. KafkaProducer
   ↓ (serializa Avro/JSON)
4. Kafka Broker (tópico: denials-events)
   ↓
5. Consumidores Downstream:
   - Sistema de Gestão de Glosas
   - Sistema de BI/Analytics
   - Sistema de Auditoria
   - Sistema de Notificações
```

## Extensões Futuras

### Campos Adicionais Sugeridos
```java
message.put("glosaId", glosaId);
message.put("event", "DENIAL_PROCESSED");
message.put("timestamp", System.currentTimeMillis());
message.put("processInstanceId", execution.getProcessInstanceId());
message.put("glosaStatus", execution.getVariable("glosaStatus"));
message.put("glosaAmount", execution.getVariable("glosaAmount"));
message.put("glosaCode", execution.getVariable("glosaCode"));
message.put("claimId", execution.getVariable("claimId"));
message.put("payerId", execution.getVariable("payerId"));
message.put("processingDate", LocalDateTime.now().toString());
```

### Validação de Schema
```java
// Validar conformidade com Avro Schema antes de publicar
SchemaValidator validator = new SchemaValidator(avroSchema);
if (!validator.validate(message)) {
    throw new BpmnError("SCHEMA_VALIDATION_FAILED",
        "Message does not conform to denial event schema");
}
```

## Dependências
- Nenhuma dependência externa (operação simples de preparação)
- Coordenação com `SendDenialsCompleteDelegate` para publicação

## Relacionamento com Outros Delegates

### Delegates Relacionados
- **SendDenialsCompleteDelegate**: Consome `kafkaMessage` e publica em Kafka
- **SendMessageDelegate**: Delegate genérico que também publica mensagens
- **PrepareBillingMessageDelegate**: Delegate similar para eventos de faturamento

### Fluxo BPMN Típico
```
[Glosa Process]
    ↓
[PrepareDenialsMessageDelegate] (prepara mensagem)
    ↓
[SendDenialsCompleteDelegate] (publica em Kafka)
    ↓
[End Event]
```

## Tipos de Eventos de Glosa

### Eventos Relacionados
1. **DENIAL_IDENTIFIED**: Glosa identificada
2. **DENIAL_ANALYZED**: Glosa analisada
3. **DENIAL_PROCESSED**: Glosa processada (este delegate)
4. **DENIAL_RECOVERED**: Glosa recuperada
5. **DENIAL_PROVISIONED**: Glosa provisionada
6. **DENIAL_ESCALATED**: Glosa escalada

## Idempotência

**Requer Idempotência**: Não

**Justificativa**: Preparação de mensagem é operação stateless e pode ser executada múltiplas vezes sem efeitos colaterais.

## Versionamento
- **v1.0.0**: Implementação inicial com estrutura básica de mensagem

## Referências
- RN-SendDenialsCompleteDelegate: Documentação de publicação de eventos
- RN-SendMessageDelegate: Documentação de mensagens genéricas
- RN-PrepareBillingMessageDelegate: Documentação de eventos de faturamento
- Kafka Documentation: https://kafka.apache.org/documentation/
- Avro Specification: https://avro.apache.org/docs/current/spec.html
