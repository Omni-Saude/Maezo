# RN-EligibilityEventConsumer

## Identificação
- **ID**: RN-EligibilityEventConsumer
- **Nome**: Consumidor de Eventos de Elegibilidade
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Consumer

## Descrição
Consome eventos de verificação de elegibilidade de pacientes (cobertura de plano de saúde).

## Tópicos Consumidos
1. `revenue-cycle.eligibility.request` - Requisição de verificação
2. `revenue-cycle.eligibility.response` - Resposta da operadora

## Processamento
Dois listeners separados para request e response.

## TODO - Integrações Pendentes
- [ ] Integrar com instância de processo Camunda
- [ ] Atualizar variáveis de processo
- [ ] Acionar próximo passo no workflow

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-EligibilityEventProducer](RN-EligibilityEventProducer.md)
