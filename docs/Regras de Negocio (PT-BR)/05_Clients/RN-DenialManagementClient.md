# RN-DenialManagementClient - Cliente de Integração com Sistema de Gerenciamento de Glosas

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/denial/DenialManagementClient.java`
- **Tipo**: External Integration Client
- **Categoria**: 05_Clients - Denial Management Integration
- **Camunda DMN**: N/A (Feign HTTP Client)
- **Complexidade**: Baixa
- **Autor**: Revenue Cycle Development Team - Hive Mind Coder Agent
- **Data Criação**: 2026-01-11
- **Versão**: 1.0.0

## Descrição

### Objetivo
Cliente Feign para integração com sistema externo de gerenciamento de glosas (denials), responsável por gerenciar recursos de glosa e restauração de status de negações.

### Tecnologia
- **Framework**: Spring Cloud OpenFeign
- **Protocolo**: HTTP/REST
- **Base URL**: Configurável via `denial.management.base-url` (padrão: `http://localhost:8082`)

## Regras de Negócio

### RN-DMC-001: Cancelamento de Recurso
**Operação**: `POST /appeals/{appealId}/cancel`

**Entrada**:
- `appealId` (String, path): Identificador do recurso a cancelar

**Comportamento**:
1. Envia requisição HTTP POST ao sistema de gerenciamento de glosas
2. Cancela recurso de glosa ativo
3. Atualiza status do recurso para "CANCELLED"

**Uso Típico**:
- Cancelamento de recurso durante compensação saga (rollback)
- Cancelamento manual de recurso indevido
- Desistência de recurso por decisão médica/administrativa

**Integração Camunda**:
- Chamado durante compensação saga em `AppealOrchestrator`
- Parte do fluxo de reversão de operações de recurso

### RN-DMC-002: Restauração de Status de Glosa
**Operação**: `POST /denials/{denialId}/restore`

**Entrada**:
- `denialId` (String, path): Identificador da glosa
- `status` (String, query param): Status a restaurar (ex: "PENDING", "UNDER_REVIEW")

**Comportamento**:
1. Envia requisição HTTP POST ao sistema de glosas
2. Restaura glosa ao status anterior antes do recurso
3. Reverte mudanças de estado realizadas pelo recurso

**Uso Típico**:
- Restauração durante compensação saga
- Correção de status indevido
- Rollback de operações de recurso falhadas

**Status Comuns para Restauração**:
- `PENDING`: Glosa pendente de análise
- `UNDER_REVIEW`: Glosa em revisão
- `IDENTIFIED`: Glosa identificada mas não analisada
- `AWAITING_DOCUMENTATION`: Aguardando documentação adicional

## Relacionamentos

### Upstream (Chama este cliente)
- **AppealOrchestrator**: Coordena cancelamento de recursos durante compensação
- **DenialCompensationService**: Executa restauração de status
- **GlosaSagaOrchestrator**: Gerencia saga de recursos de glosa

### Downstream (Sistemas externos)
- **Denial Management System**: Sistema externo de gerenciamento de glosas
  - Base URL: `http://localhost:8082` (configurável)

### DTOs Relacionados
- **DenialResponseDTO**: DTO de resposta (não atualmente usado)

## Configurações

### application.yml
```yaml
denial:
  management:
    base-url: http://localhost:8082
    timeout:
      connect: 5000
      read: 10000
```

### Propriedades
| Propriedade | Tipo | Padrão | Descrição |
|-------------|------|--------|-----------|
| `denial.management.base-url` | String | `http://localhost:8082` | URL base do sistema de glosas |

## Tratamento de Erros

### Cenários de Falha
1. **Sistema indisponível**: FeignException com HTTP 503/504
2. **Recurso não encontrado**: HTTP 404 (appealId inválido)
3. **Glosa não encontrada**: HTTP 404 (denialId inválido)
4. **Status inválido**: HTTP 400 (status não permitido)
5. **Timeout de comunicação**: Timeout exception

### Estratégia de Recuperação
- **Retry**: Configurado via Feign Retryer (padrão Spring)
- **Circuit Breaker**: Pode ser configurado via Resilience4j
- **Fallback**: Não implementado (void methods)
- **Idempotência**: Cancelamento deve ser idempotente

## Padrões de Design

### Design Patterns Aplicados
1. **Remote Facade**: Abstrai complexidade da API remota
2. **Proxy Pattern**: Feign cria proxy dinâmico
3. **Interface Segregation**: Interface focada em operações específicas
4. **Idempotent Operations**: Operações seguras para retry

### Boas Práticas
- Interface declarativa (Feign client)
- Configuração externalizada
- Operações idempotentes
- Separação de concerns

## Exemplos de Uso

### Caso 1: Cancelar Recurso durante Compensação Saga
```java
@Autowired
private DenialManagementClient denialClient;

@Override
public void compensate(SagaContext context) {
    String appealId = context.getData("appealId");

    try {
        denialClient.cancelAppeal(appealId);
        log.info("Appeal cancelled successfully: {}", appealId);
        context.markStepCompensated("APPEAL_CREATION");
    } catch (FeignException.NotFound e) {
        log.warn("Appeal not found (may have been already cancelled): {}",
                 appealId);
        // Idempotente: considera sucesso se já foi cancelado
        context.markStepCompensated("APPEAL_CREATION");
    } catch (FeignException e) {
        log.error("Failed to cancel appeal: {}", appealId, e);
        throw new CompensationFailedException("Appeal cancellation failed", e);
    }
}
```

### Caso 2: Restaurar Status de Glosa
```java
public void restoreDenialToPreviousStatus(String denialId,
                                            String previousStatus) {
    try {
        denialClient.restoreDenial(denialId, previousStatus);
        log.info("Denial {} restored to status: {}", denialId, previousStatus);
    } catch (FeignException e) {
        log.error("Failed to restore denial {}: {}", denialId, e.getMessage());
        throw new DenialRestorationException("Denial restoration failed", e);
    }
}
```

### Caso 3: Compensação Completa de Recurso de Glosa
```java
public void compensateAppealCreation(AppealContext appealContext) {
    // 1. Cancelar recurso
    denialClient.cancelAppeal(appealContext.getAppealId());

    // 2. Restaurar status original da glosa
    denialClient.restoreDenial(
        appealContext.getDenialId(),
        appealContext.getOriginalStatus()
    );

    // 3. Atualizar entidades locais
    Appeal appeal = appealRepository.findById(appealContext.getAppealId())
        .orElseThrow();
    appeal.setStatus(AppealStatus.CANCELLED);
    appeal.setCancellationReason("Saga compensation");
    appealRepository.save(appeal);

    log.info("Appeal compensation completed: {}", appealContext.getAppealId());
}
```

## Testes

### Cenários de Teste
1. **Cancelamento bem-sucedido**: Verifica chamada HTTP POST correta
2. **Recurso inexistente**: Valida tratamento de HTTP 404
3. **Restauração de status**: Testa restauração para diferentes status
4. **Sistema indisponível**: Testa retry e circuit breaker
5. **Idempotência**: Verifica que múltiplos cancelamentos não causam erro

### Exemplo de Teste Unitário
```java
@Test
void testCancelAppeal() {
    String appealId = "APPEAL-001";

    denialClient.cancelAppeal(appealId);

    verify(mockServer).post(eq("/appeals/APPEAL-001/cancel"));
}

@Test
void testCancelAppeal_NotFound_IsIdempotent() {
    String appealId = "APPEAL-999";

    when(mockServer.cancelAppeal(appealId))
        .thenThrow(new FeignException.NotFound("Not found",
                                                request,
                                                null));

    // Should not throw exception (idempotent)
    assertDoesNotThrow(() -> denialClient.cancelAppeal(appealId));
}
```

### Teste de Integração
```java
@Test
@Transactional
void testCompensateAppeal_CancelsAndRestores() {
    // Arrange
    Appeal appeal = createTestAppeal();
    String originalStatus = "PENDING";

    // Act
    compensationService.compensateAppeal(appeal.getId(), originalStatus);

    // Assert
    verify(denialClient).cancelAppeal(appeal.getId());
    verify(denialClient).restoreDenial(appeal.getDenialId(),
                                        originalStatus);

    Appeal updated = appealRepository.findById(appeal.getId()).orElseThrow();
    assertThat(updated.getStatus()).isEqualTo(AppealStatus.CANCELLED);
}
```

## Integrações ANS/TISS

### Padrão TISS
- **Relacionado**: Operações de recurso seguem processo TISS para contestação de glosas
- **Códigos de Glosa**: Restauração deve manter rastreabilidade de códigos TISS

### Compliance
- **Auditoria**: Todas operações de cancelamento/restauração devem ser auditadas
- **Rastreabilidade**: Manter histórico completo de mudanças de status

## Fluxo BPMN/Camunda

### Processo Principal: Recurso de Glosa
```
[Criar Recurso] → [Enviar Documentação] → [Aguardar Decisão]
                                               ↓
                                      [Compensação Saga]
                                               ↓
                            [Cancelar Recurso + Restaurar Status]
```

### Service Tasks
- **"Cancelar Recurso"**: Executa `cancelAppeal()`
- **"Restaurar Status Glosa"**: Executa `restoreDenial()`

## Logs e Observabilidade

### Eventos Logados
- Cancelamentos de recurso (sucesso/falha)
- Restaurações de status de glosa
- Falhas de comunicação com sistema externo
- Timeouts e retries

### Métricas Importantes
- Taxa de sucesso de cancelamentos
- Taxa de sucesso de restaurações
- Latência de chamadas HTTP
- Taxa de erro por tipo (4xx, 5xx)
- Tempo médio de compensação

### Dashboard Sugerido
```
- Cancelamentos de Recurso (último hora)
- Restaurações de Status (último hora)
- Taxa de Erro de Integração (%)
- Latência P95 de Chamadas (ms)
- Compensações Falhadas (alertar se > 0)
```

## Segurança
- **Autenticação**: Não implementada no cliente (pode ser via interceptor)
- **HTTPS**: Recomendado para produção
- **API Key/OAuth2**: Pode ser configurada via Feign RequestInterceptor
- **Autorização**: Sistema externo deve validar permissões

## Compliance e Auditoria
- **Rastreabilidade**: Logs de todas requisições via Feign
- **Audit Trail**: Registros de cancelamento/restauração no sistema externo
- **LGPD**: Dados de glosas podem conter informações de pacientes

## Melhorias Futuras
1. Implementar retry automático com backoff exponencial
2. Adicionar circuit breaker (Resilience4j)
3. Implementar autenticação via OAuth2
4. Criar DTOs de response para validação
5. Adicionar métricas detalhadas (Micrometer)
6. Implementar batch operations (cancelar múltiplos recursos)
7. Criar API para consultar status de recurso
8. Implementar webhooks para notificações assíncronas

## Dependências
```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-spring-boot2</artifactId>
</dependency>
```

## Referências
- Spring Cloud OpenFeign Documentation
- [Saga Pattern Compensation](https://microservices.io/patterns/data/saga.html)
- [Idempotent REST APIs](https://restfulapi.net/idempotent-rest-apis/)
- TISS - Padrão ANS para Glosas e Recursos

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
