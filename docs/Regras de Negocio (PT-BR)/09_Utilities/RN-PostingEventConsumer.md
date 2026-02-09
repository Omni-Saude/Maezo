# RN-PostingEventConsumer

## Identificação
- **ID**: RN-PostingEventConsumer
- **Nome**: Consumidor de Eventos de Lançamento
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Consumer

## Descrição
Consome eventos de lançamento contábil e reconciliação de pagamentos.

## Tópicos Consumidos
1. `revenue-cycle.posting.completed` - Lançamento concluído
2. `revenue-cycle.posting.reconciled` - Reconciliação concluída

## TODO - Integrações Pendentes
- [ ] Integrar com subprocesso Camunda de lançamento
- [ ] Atualizar registros financeiros
- [ ] Reconciliar pagamentos

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-PostingEventProducer](RN-PostingEventProducer.md)
