# RN-AccountingClient - Cliente de Integração com Sistema Contábil

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/accounting/AccountingClient.java`
- **Tipo**: External Integration Client
- **Categoria**: 05_Clients - Accounting Integration
- **Camunda DMN**: N/A (Feign HTTP Client)
- **Complexidade**: Baixa
- **Autor**: Revenue Cycle Development Team - Hive Mind Coder Agent
- **Data Criação**: 2026-01-11
- **Versão**: 1.0.0

## Descrição

### Objetivo
Cliente Feign para integração com sistema contábil externo, responsável por gerenciar lançamentos de provisão contábil e seus estornos.

### Tecnologia
- **Framework**: Spring Cloud OpenFeign
- **Protocolo**: HTTP/REST
- **Base URL**: Configurável via `accounting.base-url` (padrão: `http://localhost:8084`)

## Regras de Negócio

### RN-AC-001: Estorno de Provisão Contábil
**Operação**: `POST /provisions/{provisionId}/reverse`

**Entrada**:
- `provisionId` (String, path): Identificador da provisão a estornar
- `amount` (BigDecimal, query param): Valor a ser estornado

**Comportamento**:
1. Envia requisição HTTP POST ao sistema contábil
2. Executa estorno do lançamento contábil da provisão
3. Atualiza registros contábeis com operação de reversão

**Uso Típico**:
- Estorno de provisões para glosas
- Ajustes contábeis após recurso de glosa aprovado
- Correção de lançamentos contábeis indevidos

**Integração Camunda**:
- Chamado por `FinancialProvisionService` durante compensação saga
- Parte do fluxo de reversão de provisões financeiras

## Relacionamentos

### Upstream (Chama este cliente)
- **FinancialProvisionService**: Executa estornos durante compensação saga
- **GlosaCompensationOrchestrator**: Coordena reversão de provisões

### Downstream (Sistemas externos)
- **Sistema Contábil**: Recebe requisições de estorno (`http://localhost:8084`)

### DTOs Relacionados
- **AccountingResponseDTO**: DTO de resposta (não atualmente usado)

## Configurações

### application.yml
```yaml
accounting:
  base-url: http://localhost:8084
```

### Propriedades
| Propriedade | Tipo | Padrão | Descrição |
|-------------|------|--------|-----------|
| `accounting.base-url` | String | `http://localhost:8084` | URL base do sistema contábil |

## Tratamento de Erros

### Cenários de Falha
1. **Sistema contábil indisponível**: FeignException com HTTP 503/504
2. **Provisão não encontrada**: HTTP 404
3. **Valor inválido**: HTTP 400
4. **Timeout de comunicação**: Timeout exception

### Estratégia de Recuperação
- **Retry**: Configurado via Feign Retryer (padrão Spring)
- **Circuit Breaker**: Pode ser configurado via Resilience4j
- **Fallback**: Não implementado (void method)

## Padrões de Design

### Design Patterns Aplicados
1. **Remote Facade**: Abstrai complexidade da API remota
2. **Proxy Pattern**: Feign cria proxy dinâmico
3. **Interface Segregation**: Interface focada em operação específica

### Boas Práticas
- Interface declarativa (Feign client)
- Configuração externalizada
- Separação de concerns (client vs. service logic)

## Exemplos de Uso

### Caso 1: Estorno de Provisão para Glosa
```java
@Autowired
private AccountingClient accountingClient;

public void reverseGlosaProvision(String provisionId, BigDecimal amount) {
    try {
        accountingClient.reverseProvisionEntry(provisionId, amount);
        log.info("Provision reversed successfully: {}", provisionId);
    } catch (FeignException e) {
        log.error("Failed to reverse provision: {}", provisionId, e);
        throw new AccountingIntegrationException("Accounting reversal failed", e);
    }
}
```

### Caso 2: Compensação Saga (Usado por FinancialProvisionService)
```java
@Override
public void compensate(SagaContext context) {
    String provisionId = context.getData("provisionId");
    BigDecimal amount = context.getData("amount");

    accountingClient.reverseProvisionEntry(provisionId, amount);
    log.info("Compensated: reversed provision {}", provisionId);
}
```

## Testes

### Cenários de Teste
1. **Estorno bem-sucedido**: Verifica chamada HTTP POST correta
2. **Provisão inexistente**: Valida tratamento de HTTP 404
3. **Sistema contábil indisponível**: Testa retry e circuit breaker
4. **Timeout de comunicação**: Verifica comportamento em timeout

### Exemplo de Teste Unitário
```java
@Test
void testReverseProvisionEntry() {
    String provisionId = "PROV-001";
    BigDecimal amount = new BigDecimal("500.00");

    accountingClient.reverseProvisionEntry(provisionId, amount);

    verify(mockServer).post(eq("/provisions/PROV-001/reverse"),
                            contains("amount=500.00"));
}
```

## Integrações ANS/TISS
- **N/A**: Não lida diretamente com padrões TISS
- **Impacto Indireto**: Registros contábeis devem refletir glosas TISS

## Fluxo BPMN/Camunda
- **Processo**: Saga de Compensação de Glosa
- **Tarefa**: Service Task "Estornar Provisão Contábil"
- **Execução**: Síncrona via Feign HTTP call

## Logs e Observabilidade

### Eventos Logados
- Chamadas ao sistema contábil (via Feign logger)
- Falhas de comunicação
- Timeouts e retries

### Métricas
- Taxa de sucesso de estornos contábeis
- Latência de chamadas HTTP
- Taxa de erro por tipo (4xx, 5xx)

## Segurança
- **Autenticação**: Não implementada no cliente (pode ser via interceptor)
- **HTTPS**: Recomendado para produção
- **API Key**: Pode ser configurada via Feign RequestInterceptor

## Compliance e Auditoria
- **Rastreabilidade**: Logs de todas requisições via Feign
- **Audit Trail**: Registros contábeis mantidos no sistema externo

## Melhorias Futuras
1. Implementar retry automático com backoff exponencial
2. Adicionar circuit breaker (Resilience4j)
3. Implementar autenticação via OAuth2
4. Criar DTO de response para validação
5. Adicionar métricas detalhadas (Micrometer)

## Dependências
```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
```

## Referências
- Spring Cloud OpenFeign Documentation
- [Padrões de Integração Enterprise](https://www.enterpriseintegrationpatterns.com/)
- [Saga Pattern Best Practices](https://microservices.io/patterns/data/saga.html)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
