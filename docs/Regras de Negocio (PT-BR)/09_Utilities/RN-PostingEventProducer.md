# RN-PostingEventProducer

## Identificação
- **ID**: RN-PostingEventProducer
- **Nome**: Produtor de Eventos de Lançamento
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Producer

## Descrição
Publica eventos de lançamento contábil e reconciliação.

## Métodos Públicos

### publishPostingCompleted
Tópico: `revenue-cycle.posting.completed`

### publishPostingReconciled
Tópico: `revenue-cycle.posting.reconciled`

## Particionamento
Key: transactionId (garante ordem por transação)

## Referências
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-PostingEventConsumer](RN-PostingEventConsumer.md)
