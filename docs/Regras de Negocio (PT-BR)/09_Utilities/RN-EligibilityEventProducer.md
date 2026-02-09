# RN-EligibilityEventProducer

## Identificação
- **ID**: RN-EligibilityEventProducer
- **Nome**: Produtor de Eventos de Elegibilidade
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Producer

## Descrição
Publica eventos de verificação de elegibilidade de pacientes.

## Métodos Públicos

### publishEligibilityRequest
Tópico: `revenue-cycle.eligibility.request`

### publishEligibilityResponse
Tópico: `revenue-cycle.eligibility.response`

### publishEligibilityVerified
Tópico: `revenue-cycle.eligibility.verified`

## Particionamento
Key: patientId (garante ordem por paciente)

## Referências
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-EligibilityEventConsumer](RN-EligibilityEventConsumer.md)
