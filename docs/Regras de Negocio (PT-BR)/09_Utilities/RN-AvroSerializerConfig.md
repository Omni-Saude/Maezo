# RN-AvroSerializerConfig

## Identificação
- **ID da Regra**: RN-AvroSerializerConfig
- **Nome**: Configuração do Serializador Avro
- **Versão**: 1.0
- **Data de Criação**: 2025-01-12
- **Autor**: Hive Mind Swarm - Coder Agent
- **Tipo**: Configuração Técnica / Infraestrutura de Mensageria

## Descrição
Classe de configuração Spring reservada para personalizações futuras relacionadas ao Apache Avro schema registry e serialização de mensagens Kafka. Serve como ponto de extensão para configurações avançadas de esquema Avro.

## Contexto de Negócio
No ciclo de receita hospitalar, a serialização consistente de eventos Kafka usando Avro garante:
- **Compatibilidade de Schema**: Evolução segura de estruturas de mensagens
- **Validação de Dados**: Garantia de integridade dos eventos entre microsserviços
- **Documentação Automática**: Schema registry como catálogo de eventos

## Implementação Técnica

### Arquivo
```
src/main/java/com/hospital/revenuecycle/kafka/config/AvroSerializerConfig.java
```

### Estrutura da Classe
```java
@Configuration
public class AvroSerializerConfig {
    // Configurações de schema registry delegadas para KafkaProducerConfig e KafkaConsumerConfig
}
```

### Extensões Futuras Planejadas
1. **Schema Resolution Strategy**: Estratégias customizadas de resolução de esquema
2. **Schema Compatibility Settings**: Configuração de níveis de compatibilidade (BACKWARD, FORWARD, FULL)
3. **Schema Registry Authentication**: Autenticação com schema registry externo
4. **Schema Caching**: Configuração de cache de esquemas para performance
5. **Custom Avro Converters**: Conversores Avro especializados para tipos complexos

## Integração com Sistema

### Componentes Relacionados
- **KafkaProducerConfig**: Configuração atual do schema registry para produtores
- **KafkaConsumerConfig**: Configuração atual do schema registry para consumidores
- **Avro Schema Files** (`src/main/avro/`): Definições de esquemas de eventos

### Tópicos Kafka com Avro
Todos os tópicos do revenue cycle usam serialização Avro:
- `revenue-cycle.eligibility.*`
- `revenue-cycle.coding.*`
- `revenue-cycle.claim.*`
- `revenue-cycle.glosa.*`
- `revenue-cycle.collection.*`
- `revenue-cycle.payment.*`
- `revenue-cycle.posting.*`

## Regras de Validação

### Pré-condições
- Schema registry deve estar acessível
- Schemas Avro devem estar registrados
- Dependências Confluent Kafka Avro no classpath

### Pós-condições
- Configurações Avro disponíveis para toda aplicação
- Serialização/deserialização consistente entre produtores e consumidores

## Parâmetros de Configuração

### Properties Relevantes (application.yml)
```yaml
spring:
  kafka:
    properties:
      schema.registry.url: http://localhost:8081
```

### Configurações de Compatibilidade (Futuro)
- `BACKWARD`: Consumidores novos podem ler dados antigos
- `FORWARD`: Consumidores antigos podem ler dados novos
- `FULL`: Compatibilidade bidirecional
- `NONE`: Sem verificação de compatibilidade

## Exemplos de Uso

### Uso Atual (Configuração Existente)
```java
// Configuração atual em KafkaProducerConfig e KafkaConsumerConfig
props.put("schema.registry.url", schemaRegistryUrl);
props.put(KafkaAvroDeserializerConfig.SPECIFIC_AVRO_READER_CONFIG, true);
```

### Uso Futuro (Extensões Planejadas)
```java
@Configuration
public class AvroSerializerConfig {

    @Bean
    public SchemaRegistryClient schemaRegistryClient() {
        return new CachedSchemaRegistryClient(
            schemaRegistryUrl,
            1000, // cache size
            securityConfig
        );
    }

    @Bean
    public CompatibilityLevel compatibilityLevel() {
        return CompatibilityLevel.FULL;
    }
}
```

## Tratamento de Erros

### Erros Potenciais (Quando Implementado)
1. **Schema Not Found**: Esquema não registrado no schema registry
2. **Schema Incompatible**: Violação de regras de compatibilidade
3. **Registry Unavailable**: Schema registry inacessível
4. **Serialization Error**: Erro ao serializar objeto em Avro

### Estratégia de Recuperação
- Retry automático para problemas de conectividade
- Cache local de esquemas para resiliência
- Fallback para esquemas padrão quando apropriado

## Métricas e Monitoramento

### KPIs Futuros
- **Schema Cache Hit Rate**: Taxa de acerto do cache de esquemas
- **Schema Validation Errors**: Erros de validação de esquema
- **Registry Latency**: Latência de consultas ao schema registry
- **Schema Evolution Events**: Eventos de evolução de esquema

## Dependências

### Maven Dependencies
```xml
<dependency>
    <groupId>io.confluent</groupId>
    <artifactId>kafka-avro-serializer</artifactId>
    <version>7.5.0</version>
</dependency>
<dependency>
    <groupId>org.apache.avro</groupId>
    <artifactId>avro</artifactId>
    <version>1.11.3</version>
</dependency>
```

## Conformidade e Auditoria

### Padrões de Conformidade
- **Event Sourcing**: Preservação de histórico de eventos
- **Schema Evolution**: Evolução controlada de contratos
- **Data Governance**: Governança de estruturas de dados

### Trilha de Auditoria
- Registro de versões de esquemas utilizadas
- Histórico de evolução de contratos de mensagens

## Referências

### Documentação Relacionada
- [RN-KafkaProducerConfig](RN-KafkaProducerConfig.md)
- [RN-KafkaConsumerConfig](RN-KafkaConsumerConfig.md)
- [RN-KafkaTopicConfig](RN-KafkaTopicConfig.md)

### Padrões de Integração
- **Schema Registry Pattern**: Catálogo centralizado de esquemas
- **Schema Evolution Pattern**: Evolução segura de contratos
- **Versioning Pattern**: Versionamento de mensagens

### Links Externos
- [Apache Avro Documentation](https://avro.apache.org/docs/)
- [Confluent Schema Registry](https://docs.confluent.io/platform/current/schema-registry/)
- [Schema Evolution Best Practices](https://docs.confluent.io/platform/current/schema-registry/avro.html)

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2025-01-12 | Hive Mind Swarm | Criação inicial da documentação |

## Status
- **Estado Atual**: Placeholder para extensões futuras
- **Prioridade**: Baixa (funcionalidade base coberta por KafkaProducerConfig/ConsumerConfig)
- **Próximos Passos**: Implementar quando necessário customizações avançadas de Avro

## Notas de Implementação
A configuração atual de Avro está distribuída entre `KafkaProducerConfig` e `KafkaConsumerConfig`. Esta classe serve como ponto de consolidação futuro para configurações Avro avançadas que não se enquadram especificamente em produtor ou consumidor.
