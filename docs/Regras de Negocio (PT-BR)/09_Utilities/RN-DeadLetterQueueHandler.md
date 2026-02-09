# RN-DeadLetterQueueHandler

## Identificação
- **ID**: RN-DeadLetterQueueHandler
- **Nome**: Handler de Dead Letter Queue
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Error Handler

## Descrição
Roteia mensagens com falha de processamento para Dead Letter Queue (DLQ) com metadados de erro completos para análise posterior.

## Funcionalidades Principais

### Roteamento para DLQ
```java
public void sendToDLQ(String originalTopic, String key, Object value, Exception error)
public void sendToDLQ(String originalTopic, String key, Object value, Exception error, String processingStage)
```

## Metadados Anexados
Headers adicionados à mensagem DLQ:
- `original_topic`: Tópico original da mensagem
- `processing_stage`: Estágio onde falhou (ex: "claim-processing")
- `error_message`: Mensagem de erro
- `error_class`: Classe da exceção
- `error_timestamp`: Timestamp ISO-8601 do erro
- `error_stacktrace`: Stack trace completo (opcional)

## Tópico DLQ
```
revenue-cycle.dlq
```

### Configuração DLQ
- **Retenção**: 30 dias (vs 7 dias para tópicos regulares)
- **Partições**: 3
- **Replicação**: 3

## Estratégia de Tratamento

### Acknowledge Always
Mensagens com erro permanente são:
1. Enviadas para DLQ com contexto completo
2. Confirmadas no tópico original (evita reprocessamento infinito)

### Análise Posterior
Equipe de operações pode:
- Consultar mensagens no DLQ
- Analisar erros recorrentes
- Corrigir dados e reprocessar manualmente
- Implementar correções e reenviar

## Uso por Consumers
```java
try {
    processMessage(value, key);
    acknowledgment.acknowledge();
} catch (Exception e) {
    dlqHandler.sendToDLQ(topic, key, value, e, getProcessingStage());
    acknowledgment.acknowledge(); // Still acknowledge to avoid infinite loop
}
```

## Monitoramento

### Alertas Recomendados
- Taxa de mensagens no DLQ > 1%
- Spike repentino no DLQ
- Mesma mensagem recorrente no DLQ

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-KafkaTopicConfig](RN-KafkaTopicConfig.md)
