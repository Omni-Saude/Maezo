# RN-KafkaConsumerConfig

## Identificação
- **ID da Regra**: RN-KafkaConsumerConfig
- **Nome**: Configuração de Consumidores Kafka
- **Versão**: 1.0
- **Data de Criação**: 2025-01-12
- **Autor**: Hive Mind Swarm - Coder Agent
- **Tipo**: Configuração Técnica / Infraestrutura de Mensageria

## Descrição
Configura consumidores Kafka para receber mensagens serializadas em Avro dos tópicos do ciclo de receita hospitalar. Define parâmetros de performance, confiabilidade e deserialização com schema registry.

## Contexto de Negócio
Os consumidores Kafka processam eventos críticos do ciclo de receita:
- **Elegibilidade**: Respostas de verificação de cobertura de seguradoras
- **Codificação**: Eventos de codificação médica completa
- **Cobrança**: Status de submissão e processamento de contas médicas
- **Glosa**: Identificação e análise de negativas
- **Cobrança/Recebimento**: Eventos de pagamento e cobrança

## Implementação Técnica

### Arquivo
```
src/main/java/com/hospital/revenuecycle/kafka/config/KafkaConsumerConfig.java
```

### Anotações Spring
```java
@EnableKafka
@Configuration
@ConditionalOnProperty(name = "kafka.enabled", havingValue = "true", matchIfMissing = true)
```

### Propriedades de Configuração
```java
@Value("${spring.kafka.bootstrap-servers}")
private String bootstrapServers;

@Value("${spring.kafka.properties.schema.registry.url}")
private String schemaRegistryUrl;

@Value("${spring.kafka.consumer.group-id}")
private String groupId;

@Value("${spring.kafka.consumer.auto-offset-reset:earliest}")
private String autoOffsetReset;

@Value("${spring.kafka.consumer.enable-auto-commit:false}")
private boolean enableAutoCommit;

@Value("${spring.kafka.consumer.max-poll-records:500}")
private int maxPollRecords;

@Value("${spring.kafka.consumer.max-poll-interval-ms:300000}")
private int maxPollIntervalMs;

@Value("${spring.kafka.consumer.session-timeout-ms:30000}")
private int sessionTimeoutMs;

@Value("${spring.kafka.consumer.concurrency:3}")
private int concurrency;
```

## Parâmetros de Configuração

### Configuração de Deserialização
```java
// Deserializadores
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class);

// Schema Registry
props.put("schema.registry.url", schemaRegistryUrl);
props.put(KafkaAvroDeserializerConfig.SPECIFIC_AVRO_READER_CONFIG, true);
```

### Configuração de Consumer Group
```java
props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, autoOffsetReset);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, enableAutoCommit);
```

### Configuração de Performance
```java
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, maxPollRecords);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, maxPollIntervalMs);
props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, sessionTimeoutMs);
```

## Regras de Processamento

### Manual Acknowledgment
```java
factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL);
```

**Razão**: Garante que mensagens sejam confirmadas apenas após processamento completo, evitando perda de dados em caso de falhas.

### Concurrency
```java
factory.setConcurrency(concurrency);
```

**Padrão**: 3 threads por consumidor para processamento paralelo dentro do mesmo consumer group.

## Beans Spring

### ConsumerFactory Bean
```java
@Bean
public ConsumerFactory<String, Object> consumerFactory()
```

**Responsabilidade**:
- Criar instâncias de consumidores Kafka
- Configurar deserialização Avro
- Definir parâmetros de confiabilidade

### KafkaListenerContainerFactory Bean
```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, Object> kafkaListenerContainerFactory()
```

**Responsabilidade**:
- Gerenciar containers de listeners Kafka
- Configurar concorrência
- Definir modo de confirmação manual

## Integração com Sistema

### Componentes Consumidores
- **EligibilityEventConsumer**: Processa verificações de elegibilidade
- **CodingEventConsumer**: Processa eventos de codificação
- **ClaimEventConsumer**: Processa status de contas médicas
- **GlosaEventConsumer**: Processa negativas e recursos
- **CollectionEventConsumer**: Processa pagamentos e cobranças
- **PostingEventConsumer**: Processa lançamentos contábeis

### Tópicos Consumidos
```
revenue-cycle.eligibility.{request,response,verified}
revenue-cycle.coding.{request,completed,validated}
revenue-cycle.claim.{submitted,acknowledged,approved,rejected}
revenue-cycle.glosa.{identified,analyzed,appeal-submitted}
revenue-cycle.collection.{initiated}
revenue-cycle.payment.{received,reminder-sent}
revenue-cycle.posting.{completed,reconciled}
```

## Parâmetros Técnicos Detalhados

### auto-offset-reset: earliest
- **earliest**: Inicia do início do tópico se não houver offset commitado
- **latest**: Inicia apenas de novas mensagens
- **none**: Lança exceção se não houver offset

**Escolha**: `earliest` garante processamento de todos eventos históricos.

### enable-auto-commit: false
**Razão**: Confirmação manual permite:
- Garantia de processamento at-least-once
- Controle explícito de confirmação
- Integração com padrão de DLQ (Dead Letter Queue)

### max-poll-records: 500
**Otimização**: Batch de 500 mensagens por poll reduz overhead de rede enquanto mantém latência aceitável.

### max-poll-interval-ms: 300000 (5 minutos)
**Proteção**: Tempo máximo entre polls antes que o consumidor seja considerado inativo e removido do grupo.

### session-timeout-ms: 30000 (30 segundos)
**Heartbeat**: Tempo máximo sem heartbeat antes de rebalanceamento.

### concurrency: 3
**Paralelismo**: 3 threads por consumidor para processamento paralelo de partições.

## Regras de Validação

### Pré-condições
- Kafka cluster acessível
- Schema registry disponível
- Grupo de consumidores configurado
- Esquemas Avro registrados

### Pós-condições
- Consumidores ativos e prontos para receber mensagens
- Confirmação manual habilitada
- Deserialização Avro operacional

## Tratamento de Erros

### Erros de Deserialização
```java
// KafkaAvroDeserializer lança SerializationException
// Roteado para DeadLetterQueueHandler via BaseKafkaConsumer
```

### Erros de Schema Registry
- Retry automático com backoff exponencial
- Fallback para esquema em cache local
- Alerta para time de operações

### Rebalanceamento de Partições
- Pausa automática durante rebalanceamento
- Retomada após conclusão
- Logs de auditoria de rebalanceamentos

## Monitoramento e Métricas

### KPIs de Consumer
- **Lag**: Diferença entre último offset e offset processado
- **Throughput**: Mensagens processadas por segundo
- **Error Rate**: Taxa de erros de deserialização
- **Rebalance Rate**: Frequência de rebalanceamentos

### Alertas Recomendados
- Lag > 10.000 mensagens
- Error rate > 5%
- Rebalance frequency > 1/hora

## Exemplo de Uso

### Consumer Listener
```java
@Component
public class ClaimEventConsumer extends BaseKafkaConsumer<Object> {

    @KafkaListener(
        topics = "revenue-cycle.claim.submitted",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void consumeClaimEvents(ConsumerRecord<String, Object> record,
                                   Acknowledgment acknowledgment) {
        handleMessage(record, acknowledgment);
    }
}
```

## Configuração de Ambiente

### application.yml
```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: revenue-cycle-consumer-group
      auto-offset-reset: earliest
      enable-auto-commit: false
      max-poll-records: 500
      max-poll-interval-ms: 300000
      session-timeout-ms: 30000
      concurrency: 3
    properties:
      schema.registry.url: http://localhost:8081

kafka:
  enabled: true
```

## Conformidade e Auditoria

### Padrões de Conformidade
- **At-Least-Once Delivery**: Confirmação manual garante processamento
- **Schema Validation**: Validação automática via Avro
- **Event Sourcing**: Preservação de histórico de eventos

### Trilha de Auditoria
- Logs de mensagens recebidas (topic, partition, offset)
- Logs de confirmações (acknowledgment)
- Logs de erros e roteamento para DLQ

## Referências

### Documentação Relacionada
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-DeadLetterQueueHandler](RN-DeadLetterQueueHandler.md)
- [RN-KafkaTopicConfig](RN-KafkaTopicConfig.md)
- [RN-AvroSerializerConfig](RN-AvroSerializerConfig.md)

### Consumers Implementados
- [RN-ClaimEventConsumer](RN-ClaimEventConsumer.md)
- [RN-CodingEventConsumer](RN-CodingEventConsumer.md)
- [RN-EligibilityEventConsumer](RN-EligibilityEventConsumer.md)
- [RN-GlosaEventConsumer](RN-GlosaEventConsumer.md)
- [RN-CollectionEventConsumer](RN-CollectionEventConsumer.md)
- [RN-PostingEventConsumer](RN-PostingEventConsumer.md)

### Links Externos
- [Spring Kafka Documentation](https://docs.spring.io/spring-kafka/reference/)
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Confluent Avro Deserializer](https://docs.confluent.io/platform/current/schema-registry/serdes-develop/serdes-avro.html)

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2025-01-12 | Hive Mind Swarm | Criação inicial da documentação |

## Status
- **Estado Atual**: Implementado e operacional
- **Prioridade**: Crítica (infraestrutura base de messaging)
- **Próximos Passos**: Monitoramento de métricas e ajuste fino de performance

## Notas de Implementação
A configuração privilegia confiabilidade sobre performance, com confirmação manual e deserialização validada. Ajustes de performance (max-poll-records, concurrency) devem ser feitos com base em métricas de produção.
