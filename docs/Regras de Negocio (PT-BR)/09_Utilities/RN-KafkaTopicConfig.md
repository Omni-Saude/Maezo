# RN-KafkaTopicConfig

## Identificação
- **ID**: RN-KafkaTopicConfig
- **Nome**: Configuração de Tópicos Kafka
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm - Coder Agent
- **Tipo**: Configuração Técnica

## Descrição
Auto-cria todos os tópicos Kafka necessários para o ciclo de receita com particionamento, replicação e políticas de retenção apropriadas.

## Tópicos Criados

### Elegibilidade (3 tópicos)
- `revenue-cycle.eligibility.request`
- `revenue-cycle.eligibility.response`
- `revenue-cycle.eligibility.verified`

### Codificação (3 tópicos)
- `revenue-cycle.coding.request`
- `revenue-cycle.coding.completed`
- `revenue-cycle.coding.validated`

### Cobrança (4 tópicos)
- `revenue-cycle.claim.submitted`
- `revenue-cycle.claim.acknowledged`
- `revenue-cycle.claim.approved`
- `revenue-cycle.claim.rejected`

### Glosa (3 tópicos)
- `revenue-cycle.glosa.identified`
- `revenue-cycle.glosa.analyzed`
- `revenue-cycle.glosa.appeal-submitted`

### Cobrança/Pagamento (3 tópicos)
- `revenue-cycle.collection.initiated`
- `revenue-cycle.payment.received`
- `revenue-cycle.payment.reminder-sent`

### Lançamento (2 tópicos)
- `revenue-cycle.posting.completed`
- `revenue-cycle.posting.reconciled`

### Dead Letter Queue (1 tópico)
- `revenue-cycle.dlq` (retenção de 30 dias)

## Configuração Padrão

```java
@Value("${spring.kafka.topic.partitions:3}")
private int defaultPartitions;

@Value("${spring.kafka.topic.replication-factor:3}")
private short defaultReplicationFactor;

@Value("${spring.kafka.topic.retention-ms:604800000}") // 7 dias
private String retentionMs;
```

### Políticas Aplicadas
- **Partições**: 3 (paralelismo)
- **Replicação**: 3 (alta disponibilidade)
- **Retenção**: 7 dias (dados regulares), 30 dias (DLQ)
- **Compressão**: snappy
- **Limpeza**: delete (não compaction)

## Regras de Particionamento
- Key-based partitioning (por ID de entidade)
- Garante ordem por entidade (paciente, conta, pagamento)
- Permite consumo paralelo

## Referências
- [RN-KafkaProducerConfig](RN-KafkaProducerConfig.md)
- [RN-KafkaConsumerConfig](RN-KafkaConsumerConfig.md)
- [RN-DeadLetterQueueHandler](RN-DeadLetterQueueHandler.md)
