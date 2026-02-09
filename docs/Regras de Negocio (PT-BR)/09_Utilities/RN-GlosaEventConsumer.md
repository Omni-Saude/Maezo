# RN-GlosaEventConsumer

## Identificação
- **ID**: RN-GlosaEventConsumer
- **Nome**: Consumidor de Eventos de Glosa
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Consumer

## Descrição
Consome eventos de negativas (glosas) e recursos administrativos do Kafka.

## Tópicos Consumidos
1. `revenue-cycle.glosa.identified` - Glosa identificada
2. `revenue-cycle.glosa.analyzed` - Análise de motivo concluída
3. `revenue-cycle.glosa.appeal-submitted` - Recurso enviado

## Integrações Camunda Existentes
- **AnalyzeGlosaDelegate**: Análise de motivo da negativa
- **PrepareGlosaAppealDelegate**: Preparação de documentação de recurso
- **PdfAppealLetterGenerator**: Geração de carta de recurso

## Referências
- [RN-BaseKafkaConsumer](RN-BaseKafkaConsumer.md)
- [RN-GlosaEventProducer](RN-GlosaEventProducer.md)
- [RN-AnalyzeGlosaDelegate](../03_Servicos/RN-AnalyzeGlosaDelegate.md)
