# RN-CollectionEventConsumer

## Identificação
- **ID**: RN-CollectionEventConsumer
- **Nome**: Consumidor de Eventos de Cobrança/Pagamento
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Consumer

## Descrição
Consome eventos de cobrança e recebimento de pagamentos do Kafka.

## Tópicos Consumidos
1. `revenue-cycle.collection.initiated` - Cobrança iniciada
2. `revenue-cycle.payment.received` - Pagamento recebido
3. `revenue-cycle.payment.reminder-sent` - Lembrete enviado

## TODO - Integrações Pendentes
- [ ] Integrar com subprocesso Camunda de cobrança
- [ ] Atualizar status de pagamento
- [ ] Gerar lembretes de pagamento

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-CollectionEventProducer](RN-CollectionEventProducer.md)
