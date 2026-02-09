# RN-CodingEventConsumer

## Identificação
- **ID**: RN-CodingEventConsumer
- **Nome**: Consumidor de Eventos de Codificação
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Consumer

## Descrição
Consome eventos de codificação médica (ICD-10, TUSS) do Kafka e atualiza processos Camunda.

## Tópicos Consumidos
1. `revenue-cycle.coding.request` - Solicitação de codificação
2. `revenue-cycle.coding.completed` - Codificação concluída

## Processamento
Dois listeners separados para request e completed.

## TODO - Integrações Pendentes
- [ ] Integrar com instância de processo Camunda
- [ ] Atualizar variáveis de codificação
- [ ] Validar códigos médicos (ICD-10, TUSS)

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-CodingEventProducer](RN-CodingEventProducer.md)
