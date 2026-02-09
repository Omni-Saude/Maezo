# RN-ClaimEventProducer

## Identificação
- **ID**: RN-ClaimEventProducer
- **Nome**: Produtor de Eventos de Cobrança
- **Versão**: 1.0
- **Autor**: Hive Mind Swarm
- **Tipo**: Component / Event Producer

## Descrição
Publica eventos de submissão e status de contas médicas para tópicos Kafka.

## Métodos Públicos

### publishClaimSubmitted
```java
public void publishClaimSubmitted(String claimId, Object event)
```
Tópico: `revenue-cycle.claim.submitted`

### publishClaimAcknowledged
```java
public void publishClaimAcknowledged(String claimId, Object event)
```
Tópico: `revenue-cycle.claim.acknowledged`

### publishClaimApproved
```java
public void publishClaimApproved(String claimId, Object event)
```
Tópico: `revenue-cycle.claim.approved`

### publishClaimRejected
```java
public void publishClaimRejected(String claimId, Object event)
```
Tópico: `revenue-cycle.claim.rejected`

## Particionamento
Key: claimId (garante ordem de eventos por conta médica)

## Referências
- [RN-BaseKafkaProducer](RN-BaseKafkaProducer.md)
- [RN-ClaimEventConsumer](RN-ClaimEventConsumer.md)
