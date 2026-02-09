# RN-CodingEventProducer

## Identificação
- **ID**: RN-CodingEventProducer
- **Nome**: Produtor de Eventos de Codificação
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Producer

## Descrição
Publica eventos de codificação médica (ICD-10, TUSS).

## Métodos Públicos

### publishCodingRequest
Tópico: `revenue-cycle.coding.request`

### publishCodingCompleted
Tópico: `revenue-cycle.coding.completed`

### publishCodingValidated
Tópico: `revenue-cycle.coding.validated`

## Particionamento
Key: encounterId (garante ordem por atendimento)

## Referências
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-CodingEventConsumer](RN-CodingEventConsumer.md)
