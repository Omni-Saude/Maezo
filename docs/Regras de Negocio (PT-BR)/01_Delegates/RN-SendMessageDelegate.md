# RN-SendMessageDelegate - Envio Genérico de Mensagens Kafka

## Identificação
- **ID**: RN-MSG-003
- **Nome**: SendMessageDelegate
- **Categoria**: Messaging/Kafka
- **Versão**: 1.0.0
- **Bean BPMN**: `sendMessageDelegate`
- **Autor**: AI Swarm - Forensics Delegate Generation

## Visão Geral
Delegate genérico responsável por enviar mensagens para tópicos Kafka configuráveis, suportando qualquer tipo de payload serializável.

## Responsabilidades

### 1. Envio de Mensagens
- Envia mensagem para tópico Kafka especificado
- Suporta qualquer payload no formato Map<String, Object>
- Gera chave de mensagem para particionamento
- Adiciona metadados (headers)

### 2. Rastreabilidade
- Registra offset da mensagem publicada
- Persiste timestamp de envio
- Marca mensagem como enviada
- Habilita auditoria de eventos

### 3. Tratamento de Erros
- Retries automáticos em caso de falha
- Timeout configurável (5 segundos)
- Lança erro BPMN em falha permanente

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `kafkaTopic` | String | Sim | Nome do tópico Kafka de destino |
| `kafkaMessage` | Map&lt;String, Object&gt; | Sim | Payload da mensagem a enviar |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `messageSent` | Boolean | `true` se mensagem foi enviada com sucesso |
| `sendDate` | LocalDateTime | Timestamp do envio |
| `messageQueued` | Boolean | `true` se mensagem foi enfileirada (modo mock) |

## Algoritmo

```
1. Validar entrada:
   - kafkaTopic não pode ser nulo/vazio
   - kafkaMessage não pode ser nulo

2. Extrair chave de mensagem:
   - messageKey = message.getOrDefault("key", UUID.randomUUID().toString())

3. Criar ProducerRecord:
   - record = new ProducerRecord<>(topic, messageKey, message)

4. Adicionar headers:
   - "source": "revenue-cycle"
   - "timestamp": LocalDateTime.now()

5. Publicar em Kafka (com timeout 5s):
   - result = kafkaTemplate.send(record).get(5, TimeUnit.SECONDS)
   - kafkaOffset = result.getRecordMetadata().offset()

6. Persistir resultados:
   - setVariable("messageSent", true)
   - setVariable("kafkaOffset", offset)
   - setVariable("sendDate", LocalDateTime.now())

7. Em caso de erro:
   - throw BpmnError("KAFKA_SEND_FAILED", "Failed to send message to topic " + topic)
```

## Estrutura de Mensagem Kafka

### Payload Mínimo
```json
{
  "key": "optional-message-key",
  "data": "any serializable data"
}
```

### Headers Adicionados
```
source: revenue-cycle
timestamp: 2025-01-12T10:30:00
processInstanceId: abc-123-xyz (se disponível)
```

## Integração com Kafka

### Configuração KafkaTemplate
```java
@Autowired
private KafkaTemplate<String, Object> kafkaTemplate;
```

### Publicação com Timeout
```java
try {
    ProducerRecord<String, Object> record =
        new ProducerRecord<>(topic, messageKey, message);

    // Headers
    record.headers().add("source", "revenue-cycle".getBytes());
    record.headers().add("timestamp", LocalDateTime.now().toString().getBytes());

    // Send with timeout
    SendResult<String, Object> result =
        kafkaTemplate.send(record).get(5, TimeUnit.SECONDS);

    Long offset = result.getRecordMetadata().offset();
    log.info("Message sent to Kafka: topic={}, offset={}", topic, offset);

} catch (Exception e) {
    log.error("Failed to send Kafka message: topic={}", topic, e);
    throw new BpmnError("KAFKA_SEND_FAILED",
        "Failed to send message to topic " + topic);
}
```

## Casos de Uso

### Caso 1: Envio de Evento de Faturamento
**Entrada**:
```json
{
  "kafkaTopic": "billing-events",
  "kafkaMessage": {
    "claimId": "GUIA-2025-001",
    "event": "BILLING_COMPLETE",
    "amount": 1500.00
  }
}
```

**Saída**:
```json
{
  "messageSent": true,
  "sendDate": "2025-01-12T10:30:00",
  "messageQueued": true
}
```

### Caso 2: Envio de Evento de Glosa
**Entrada**:
```json
{
  "kafkaTopic": "denials-events",
  "kafkaMessage": {
    "glosaId": "GLOSA-2025-001",
    "event": "DENIAL_PROCESSED",
    "status": "RECOVERED"
  }
}
```

**Saída**:
```json
{
  "messageSent": true,
  "sendDate": "2025-01-12T10:35:00",
  "messageQueued": true
}
```

### Caso 3: Envio para Tópico Customizado
**Entrada**:
```json
{
  "kafkaTopic": "custom-analytics-events",
  "kafkaMessage": {
    "eventType": "PATIENT_DISCHARGE",
    "patientId": "PAT-12345",
    "dischargeDate": "2025-01-12",
    "los": 3,
    "totalCost": 5000.00
  }
}
```

**Saída**:
```json
{
  "messageSent": true,
  "sendDate": "2025-01-12T10:40:00",
  "messageQueued": true
}
```

## Erros BPMN

| Código | Mensagem | Causa | Ação |
|--------|----------|-------|------|
| `KAFKA_SEND_FAILED` | Failed to send message to topic {topic} | Falha na publicação Kafka | Verificar conectividade Kafka, retry |

## Regras de Negócio

### RN-MSG-003-001: Tópico Obrigatório
- **Descrição**: Nome do tópico Kafka deve ser fornecido
- **Prioridade**: CRÍTICA
- **Validação**: `kafkaTopic != null && !kafkaTopic.isEmpty()`

### RN-MSG-003-002: Mensagem Obrigatória
- **Descrição**: Payload da mensagem deve ser fornecido
- **Prioridade**: CRÍTICA
- **Validação**: `kafkaMessage != null`

### RN-MSG-003-003: Timeout de Envio
- **Descrição**: Envio deve completar em 5 segundos
- **Prioridade**: ALTA
- **Timeout**: 5000ms

### RN-MSG-003-004: Chave de Particionamento
- **Descrição**: Se chave não fornecida, gerar UUID
- **Prioridade**: MÉDIA
- **Implementação**: `message.getOrDefault("key", UUID.randomUUID().toString())`

## Tópicos Kafka Sugeridos

### Tópicos do Ciclo de Receita
| Tópico | Descrição | Partições | Retenção |
|--------|-----------|-----------|----------|
| `billing-events` | Eventos de faturamento | 3 | 7 dias |
| `denials-events` | Eventos de glosas | 3 | 30 dias |
| `eligibility-events` | Eventos de elegibilidade | 2 | 7 dias |
| `collection-events` | Eventos de cobrança | 2 | 30 dias |
| `analytics-events` | Eventos de analytics | 5 | 90 dias |
| `audit-events` | Eventos de auditoria | 1 | 365 dias |

## Idempotência

**Requer Idempotência**: Não

**Parâmetros de Idempotência**:
```java
Map<String, Object> params = {
    "kafkaTopic": topic
}
```

**Justificativa**: Publicação em Kafka pode gerar mensagens duplicadas, mas isso é aceitável para eventos (at-least-once delivery). Consumidores devem implementar deduplicação se necessário.

## Configuração Kafka

### application.yml
```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      retries: 3
      properties:
        max.in.flight.requests.per.connection: 1
        enable.idempotence: true
```

## Relacionamento com Outros Delegates

### Delegates que Usam SendMessageDelegate
- **SendBillingCompleteDelegate**: Envia eventos de faturamento
- **SendDenialsCompleteDelegate**: Envia eventos de glosa
- Qualquer processo que precise publicar eventos customizados

### Fluxo BPMN Típico
```
[Preparação de Mensagem]
    ↓
[SendMessageDelegate] (envia para Kafka)
    ↓
[Kafka Broker]
    ↓
[Consumidores Downstream]
```

## Dependências
- **KafkaTemplate<String, Object>**: Template Spring Kafka
- **Kafka Cluster**: Infraestrutura Kafka

## Monitoramento

### Métricas
- Taxa de sucesso de envio
- Latência de publicação (p50, p95, p99)
- Taxa de erro por tópico
- Volume de mensagens por tópico

### Alertas
- Taxa de erro > 5%
- Latência p95 > 1 segundo
- Kafka cluster indisponível

## Versionamento
- **v1.0.0**: Implementação inicial genérica

## Referências
- RN-SendBillingCompleteDelegate: Uso específico para billing
- RN-SendDenialsCompleteDelegate: Uso específico para denials
- Kafka Documentation: https://kafka.apache.org/documentation/
- Spring Kafka: https://docs.spring.io/spring-kafka/reference/html/
