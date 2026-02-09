# RN-GlosaEventProducer

## Identificação
- **ID**: RN-GlosaEventProducer
- **Nome**: Produtor de Eventos de Glosa
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Producer

## Descrição
Publica eventos de negativas (glosas) e recursos administrativos.

## Métodos Públicos

### publishGlosaIdentified
Tópico: `revenue-cycle.glosa.identified`

### publishGlosaAnalyzed
Tópico: `revenue-cycle.glosa.analyzed`

### publishAppealSubmitted
Tópico: `revenue-cycle.glosa.appeal-submitted`

## Particionamento
Key: claimId (garante ordem por conta médica)

## Referências
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-GlosaEventConsumer](RN-GlosaEventConsumer.md)
