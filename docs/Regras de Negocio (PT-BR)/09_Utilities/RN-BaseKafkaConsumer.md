# RN-BaseKafkaConsumer

## Identificação
- **ID**: RN-BaseKafkaConsumer
- **Nome**: Consumer Kafka Base
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Classe Abstrata / Infraestrutura

## Descrição
Classe base abstrata que fornece funcionalidade comum para todos os consumidores de eventos Kafka com suporte a Dead Letter Queue (DLQ) e confirmação manual.

## Funcionalidades Principais

### 1. Processamento com Error Handling
```java
protected void handleMessage(ConsumerRecord<String, T> record, Acknowledgment acknowledgment)
```
- Logging de mensagens recebidas (topic, partition, offset)
- Try-catch para processamento seguro
- Roteamento automático para DLQ em caso de erro
- Confirmação manual após sucesso ou erro

### 2. Template Method Pattern
```java
protected abstract void processMessage(T message, String key) throws Exception;
protected abstract String getProcessingStage();
protected abstract String getTopicName();
```

## Estratégia de Erro

### Confirmação Sempre (Acknowledge Always)
```java
// Sucesso: confirma
acknowledgment.acknowledge();

// Erro: envia para DLQ e confirma
dlqHandler.sendToDLQ(topic, key, value, e, getProcessingStage());
acknowledgment.acknowledge();
```

**Razão**: Evita reprocessamento infinito de mensagens com erro permanente.

## Subclasses Implementadas
- ClaimEventConsumer
- CodingEventConsumer
- CollectionEventConsumer
- EligibilityEventConsumer
- GlosaEventConsumer
- PostingEventConsumer

## Referências
- [RN-DeadLetterQueueHandler](RN-DeadLetterQueueHandler.md)
- [RN-KafkaConsumerConfig](RN-KafkaConsumerConfig.md)
