# RN-BaseKafkaProducer

## Identificação
- **ID**: RN-BaseKafkaProducer
- **Nome**: Producer Kafka Base
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Classe Abstrata / Infraestrutura

## Descrição
Classe base abstrata para todos os produtores de eventos Kafka, fornecendo funcionalidade comum de envio com logging e callbacks assíncronos.

## Funcionalidades Principais

### Envio de Eventos
```java
protected void sendEvent(String topic, String key, T event)
```
- Envio assíncrono via KafkaTemplate
- Callback para sucesso/erro
- Logging detalhado (topic, partition, offset)

### Template Method Pattern
```java
protected abstract String getTopicName();
```

## Comportamento Assíncrono
```java
CompletableFuture<SendResult<String, Object>> future = kafkaTemplate.send(topic, key, event);

future.whenComplete((result, ex) -> {
    if (ex == null) {
        logger.info("Event sent successfully");
    } else {
        logger.error("Failed to send event");
        throw new RuntimeException("Failed to send event to Kafka", ex);
    }
});
```

## Subclasses Implementadas
- ClaimEventProducer
- CodingEventProducer
- CollectionEventProducer
- EligibilityEventProducer
- GlosaEventProducer
- NotificationEventProducer
- PostingEventProducer

## Referências
- [RN-KafkaProducerConfig](RN-KafkaProducerConfig.md)
