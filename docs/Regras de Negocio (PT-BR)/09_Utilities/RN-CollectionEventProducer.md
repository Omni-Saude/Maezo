# RN-CollectionEventProducer

## Identificação
- **ID**: RN-CollectionEventProducer
- **Nome**: Produtor de Eventos de Cobrança/Pagamento
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Producer

## Descrição
Publica eventos de cobrança e recebimento de pagamentos.

## Métodos Públicos

### publishCollectionInitiated
Tópico: `revenue-cycle.collection.initiated`

### publishPaymentReceived
Tópico: `revenue-cycle.payment.received`

### publishReminderSent
Tópico: `revenue-cycle.payment.reminder-sent`

## Particionamento
Key: accountId (garante ordem por conta de paciente)

## Referências
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-CollectionEventConsumer](RN-CollectionEventConsumer.md)
