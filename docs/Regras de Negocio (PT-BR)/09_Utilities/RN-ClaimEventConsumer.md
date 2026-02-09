# RN-ClaimEventConsumer

## Identificação
- **ID**: RN-ClaimEventConsumer
- **Nome**: Consumidor de Eventos de Cobrança
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Consumer

## Descrição
Consome eventos de submissão e status de contas médicas (claims) do Kafka e integra com processos Camunda.

## Tópicos Consumidos
1. `revenue-cycle.claim.submitted` - Conta enviada para operadora
2. `revenue-cycle.claim.acknowledged` - Conta recebida por operadora
3. `revenue-cycle.claim.approved` - Conta aprovada
4. `revenue-cycle.claim.rejected` - Conta rejeitada

## Processamento
```java
@KafkaListener(
    topics = {
        "revenue-cycle.claim.submitted",
        "revenue-cycle.claim.acknowledged",
        "revenue-cycle.claim.approved",
        "revenue-cycle.claim.rejected"
    },
    groupId = "${spring.kafka.consumer.group-id}"
)
```

## TODO - Integrações Pendentes
- [ ] Integrar com instância de processo Camunda
- [ ] Atualizar status de conta médica
- [ ] Rotear para subprocesso apropriado (aprovação/rejeição/glosa)

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-ClaimEventProducer](RN-ClaimEventProducer.md)
