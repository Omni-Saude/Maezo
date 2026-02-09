# RN-KafkaProducerConfig

## Identificação
- **ID da Regra**: RN-KafkaProducerConfig
- **Nome**: Configuração de Produtores Kafka
- **Versão**: 1.0
- **Data de Criação**: 2025-01-12
- **Autor**: Hive Mind Swarm - Coder Agent
- **Tipo**: Configuração Técnica / Infraestrutura de Mensageria

## Descrição
Configura produtores Kafka para enviar mensagens serializadas em Avro aos tópicos do ciclo de receita hospitalar. Define parâmetros de confiabilidade, performance e idempotência para garantir entrega garantida de eventos críticos.

## Contexto de Negócio
Os produtores Kafka publicam eventos críticos do ciclo de receita que acionam processos downstream:
- **Elegibilidade**: Requisições de verificação de cobertura
- **Codificação**: Solicitações de codificação médica
- **Cobrança**: Eventos de submissão de contas
- **Glosa**: Notificações de negativas identificadas
- **Notificações**: Alertas e lembretes de pagamento
- **Lançamentos**: Eventos de reconciliação contábil

## Implementação Técnica

### Arquivo
```
src/main/java/com/hospital/revenuecycle/kafka/config/KafkaProducerConfig.java
```

### Anotações Spring
```java
@Configuration
@ConditionalOnProperty(name = "kafka.enabled", havingValue = "true", matchIfMissing = true)
```

### Propriedades de Configuração
```java
@Value("${spring.kafka.bootstrap-servers}")
private String bootstrapServers;

@Value("${spring.kafka.properties.schema.registry.url}")
private String schemaRegistryUrl;

@Value("${spring.kafka.producer.acks:all}")
private String acks;

@Value("${spring.kafka.producer.retries:3}")
private int retries;

@Value("${spring.kafka.producer.compression-type:snappy}")
private String compressionType;

@Value("${spring.kafka.producer.batch-size:16384}")
private int batchSize;

@Value("${spring.kafka.producer.linger-ms:10}")
private int lingerMs;

@Value("${spring.kafka.producer.buffer-memory:33554432}")
private long bufferMemory;

@Value("${spring.kafka.producer.max-in-flight-requests:5}")
private int maxInFlightRequests;

@Value("${spring.kafka.producer.enable-idempotence:true}")
private boolean enableIdempotence;
```

## Parâmetros de Configuração

### Configuração de Serialização
```java
// Serializers
configProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
configProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class);

// Schema Registry
configProps.put("schema.registry.url", schemaRegistryUrl);
```

### Configuração de Confiabilidade
```java
// Garantias de entrega
configProps.put(ProducerConfig.ACKS_CONFIG, acks);
configProps.put(ProducerConfig.RETRIES_CONFIG, retries);
configProps.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, enableIdempotence);
configProps.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, maxInFlightRequests);
```

### Configuração de Performance
```java
// Otimizações de throughput
configProps.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, compressionType);
configProps.put(ProducerConfig.BATCH_SIZE_CONFIG, batchSize);
configProps.put(ProducerConfig.LINGER_MS_CONFIG, lingerMs);
configProps.put(ProducerConfig.BUFFER_MEMORY_CONFIG, bufferMemory);
```

## Regras de Confiabilidade

### acks: "all"
**Significado**: Aguarda confirmação de todas as réplicas in-sync antes de considerar escrita bem-sucedida.

**Garantias**:
- Durabilidade máxima
- Proteção contra perda de dados
- Latência ligeiramente maior

**Trade-offs**:
- ✅ Confiabilidade crítica para eventos financeiros
- ⚠️ Latência adicional de ~5-10ms

### enable-idempotence: true
**Significado**: Produtor garante que cada mensagem seja escrita exatamente uma vez, mesmo com retries.

**Benefícios**:
- Elimina mensagens duplicadas
- Garante ordem de mensagens por partição
- Integra com transações Kafka

**Implicações**:
- Requer `acks=all`
- Requer `max.in.flight.requests <= 5`
- Requer `retries > 0`

### retries: 3
**Estratégia**: Até 3 tentativas automáticas em caso de falhas transientes.

**Cenários de Retry**:
- Network timeout
- Broker temporariamente indisponível
- Líder de partição em eleição

## Regras de Performance

### compression-type: snappy
**Algoritmo**: Snappy - compressão rápida com boa taxa de compressão.

**Comparação**:
| Algoritmo | CPU | Compressão | Velocidade |
|-----------|-----|------------|------------|
| none | Baixo | 0% | Máxima |
| gzip | Alto | ~70% | Lenta |
| snappy | Médio | ~50% | Rápida |
| lz4 | Baixo | ~40% | Muito Rápida |

**Escolha**: Snappy oferece melhor equilíbrio para eventos médicos.

### batch-size: 16384 (16KB)
**Otimização**: Agrupa múltiplas mensagens em um único request de rede.

**Trade-off**:
- ✅ Reduz overhead de rede
- ✅ Aumenta throughput
- ⚠️ Pode aumentar latência até atingir batch size

### linger-ms: 10
**Delay**: Aguarda até 10ms para preencher batch antes de enviar.

**Comportamento**:
- Se batch encher primeiro: envia imediatamente
- Se 10ms passar: envia batch parcial
- Otimiza throughput sem afetar latência significativamente

### buffer-memory: 33554432 (32MB)
**Buffer**: Memória total disponível para bufferização de mensagens aguardando envio.

**Proteção**: Se buffer encher, send() bloqueia (backpressure).

### max-in-flight-requests: 5
**Paralelismo**: Até 5 requests simultâneos por conexão.

**Restrição**: Deve ser ≤ 5 quando idempotência está habilitada para garantir ordem.

## Beans Spring

### ProducerFactory Bean
```java
@Bean
public ProducerFactory<String, Object> producerFactory()
```

**Responsabilidade**:
- Criar instâncias de produtores Kafka
- Configurar serialização Avro
- Definir parâmetros de confiabilidade e performance

### KafkaTemplate Bean
```java
@Bean
public KafkaTemplate<String, Object> kafkaTemplate()
```

**Responsabilidade**:
- Interface simplificada para envio de mensagens
- Integração com Spring
- Suporte a callbacks assíncronos

## Integração com Sistema

### Componentes Produtores
- **EligibilityEventProducer**: Publica requisições de elegibilidade
- **CodingEventProducer**: Publica eventos de codificação
- **ClaimEventProducer**: Publica eventos de contas médicas
- **GlosaEventProducer**: Publica eventos de negativas
- **CollectionEventProducer**: Publica eventos de cobrança
- **NotificationEventProducer**: Publica notificações
- **PostingEventProducer**: Publica eventos de lançamento

### Tópicos Publicados
```
revenue-cycle.eligibility.{request,response,verified}
revenue-cycle.coding.{request,completed,validated}
revenue-cycle.claim.{submitted,acknowledged,approved,rejected}
revenue-cycle.glosa.{identified,analyzed,appeal-submitted}
revenue-cycle.collection.{initiated}
revenue-cycle.payment.{received,reminder-sent}
revenue-cycle.posting.{completed,reconciled}
```

## Regras de Validação

### Pré-condições
- Kafka cluster acessível
- Schema registry disponível
- Esquemas Avro registrados
- Buffers de memória suficientes

### Pós-condições
- Produtores prontos para envio
- Idempotência habilitada
- Serialização Avro operacional
- Compressão ativa

## Tratamento de Erros

### Erros de Serialização Avro
```java
// KafkaAvroSerializer lança SerializationException
// Propagado para aplicação via CompletableFuture.whenComplete()
```

### Erros de Schema Registry
- Retry automático com backoff
- Cache local de esquemas
- Alerta para time de operações

### Erros de Envio
```java
future.whenComplete((result, ex) -> {
    if (ex != null) {
        logger.error("Failed to send event - Topic: {}, Error: {}", topic, ex.getMessage());
        // Logging, alertas, métricas
    }
});
```

## Monitoramento e Métricas

### KPIs de Producer
- **Send Rate**: Mensagens enviadas por segundo
- **Error Rate**: Taxa de falhas de envio
- **Latency**: Tempo de confirmação de envio
- **Batch Size Avg**: Tamanho médio de batches
- **Compression Ratio**: Taxa de compressão

### Alertas Recomendados
- Error rate > 1%
- Latency p99 > 100ms
- Buffer memory usage > 80%

## Exemplo de Uso

### Envio de Evento
```java
@Component
public class ClaimEventProducer extends BaseKafkaProducer<Object> {

    public void publishClaimSubmitted(String claimId, Object event) {
        sendEvent("revenue-cycle.claim.submitted", claimId, event);
    }
}

// BaseKafkaProducer
protected void sendEvent(String topic, String key, T event) {
    CompletableFuture<SendResult<String, Object>> future =
        kafkaTemplate.send(topic, key, event);

    future.whenComplete((result, ex) -> {
        if (ex == null) {
            logger.info("Event sent - Topic: {}, Partition: {}, Offset: {}",
                topic, result.getRecordMetadata().partition(),
                result.getRecordMetadata().offset());
        } else {
            logger.error("Failed to send - Topic: {}, Error: {}", topic, ex);
        }
    });
}
```

## Configuração de Ambiente

### application.yml
```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      retries: 3
      compression-type: snappy
      batch-size: 16384
      linger-ms: 10
      buffer-memory: 33554432
      max-in-flight-requests: 5
      enable-idempotence: true
    properties:
      schema.registry.url: http://localhost:8081

kafka:
  enabled: true
```

## Conformidade e Auditoria

### Padrões de Conformidade
- **Exactly-Once Semantics**: Idempotência garante unicidade
- **Schema Validation**: Validação automática via Avro
- **Durability**: acks=all garante persistência em réplicas

### Trilha de Auditoria
- Logs de mensagens enviadas (topic, partition, offset)
- Logs de falhas de envio
- Métricas de throughput e latência

## Segurança

### Proteções Implementadas
- **Buffer Overflow Protection**: Backpressure automático
- **Network Failure Resilience**: Retry automático
- **Data Validation**: Schema validation via Avro

### Proteções Futuras
- TLS/SSL para comunicação criptografada
- SASL para autenticação
- ACLs para autorização de tópicos

## Referências

### Documentação Relacionada
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-KafkaTopicConfig](RN-KafkaTopicConfig.md)
- [RN-AvroSerializerConfig](RN-AvroSerializerConfig.md)

### Producers Implementados
- [RN-ClaimEventProducer](RN-ClaimEventProducer.md)
- [RN-CodingEventProducer](RN-CodingEventProducer.md)
- [RN-EligibilityEventProducer](RN-EligibilityEventProducer.md)
- [RN-GlosaEventProducer](RN-GlosaEventProducer.md)
- [RN-CollectionEventProducer](RN-CollectionEventProducer.md)
- [RN-NotificationEventProducer](RN-NotificationEventProducer.md)
- [RN-PostingEventProducer](RN-PostingEventProducer.md)

### Links Externos
- [Spring Kafka Documentation](https://docs.spring.io/spring-kafka/reference/)
- [Apache Kafka Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Confluent Avro Serializer](https://docs.confluent.io/platform/current/schema-registry/serdes-develop/serdes-avro.html)
- [Kafka Idempotence](https://kafka.apache.org/documentation/#producerconfigs_enable.idempotence)

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2025-01-12 | Hive Mind Swarm | Criação inicial da documentação |

## Status
- **Estado Atual**: Implementado e operacional
- **Prioridade**: Crítica (infraestrutura base de messaging)
- **Próximos Passos**: Monitoramento de métricas e ajuste fino de performance

## Notas de Implementação
A configuração privilegia confiabilidade máxima (acks=all, idempotência) com otimizações de performance (batching, compressão). Para eventos críticos financeiros, confiabilidade é prioridade sobre latência mínima.
