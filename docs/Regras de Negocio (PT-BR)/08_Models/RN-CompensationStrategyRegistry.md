# RN-CompensationStrategyRegistry - Registro de Estratégias de Compensação

**Identificador**: RN-CompensationStrategyRegistry
**Módulo**: Domain Models - Compensation
**Tipo de Regra**: Service (Registry Pattern)
**Status**: Ativo ✅
**Versão**: 2.0
**Última Atualização**: 2025-12-25

---

## 1. DESCRIÇÃO GERAL

Serviço de registro que gerencia todas as implementações de `CompensationStrategy` e fornece lookup de estratégias por tipo de compensação. Utiliza injeção de dependência do Spring para auto-descoberta de estratégias.

### Padrão de Projeto
**Registry Pattern** - Mantém mapa de objetos registrados acessíveis por chave.

---

## 2. FUNCIONALIDADES

### 2.1. Auto-Descoberta de Estratégias

```java
@Autowired
public CompensationStrategyRegistry(List<CompensationStrategy> strategyBeans) {
    this.strategies = strategyBeans.stream()
            .collect(Collectors.toMap(
                    CompensationStrategy::getCompensationType,
                    Function.identity()
            ));

    log.info("Initialized registry with {} strategies: {}",
            strategies.size(), strategies.keySet());
}
```

**Spring auto-wire**:
- Injeta todas as implementações de `CompensationStrategy`
- Cria mapa usando `getCompensationType()` como chave
- Log de inicialização para diagnóstico

---

## 3. API PÚBLICA

### 3.1. `getStrategy(String compensationType)`

```java
public CompensationStrategy getStrategy(String compensationType)
```

**Parâmetros**:
- `compensationType`: Identificador do tipo (ex: "ELIGIBILITY", "CLAIM")

**Retorna**:
- `CompensationStrategy` correspondente

**Exceção**:
- `IllegalArgumentException` se estratégia não existe
- Mensagem inclui tipos disponíveis

**Exemplo**:
```java
try {
    CompensationStrategy strategy = registry.getStrategy("ELIGIBILITY");
    strategy.execute(context);
} catch (IllegalArgumentException e) {
    log.error("Strategy not found: {}", e.getMessage());
    // Mensagem: "No compensation strategy found for type: ELIGIBILITY.
    //            Available types: [CLAIM, CODING, AGENDAMENTO, ...]"
}
```

### 3.2. `hasStrategy(String compensationType)`

```java
public boolean hasStrategy(String compensationType)
```

**Uso**:
```java
if (registry.hasStrategy("CUSTOM_TYPE")) {
    CompensationStrategy strategy = registry.getStrategy("CUSTOM_TYPE");
    strategy.execute(context);
} else {
    log.warn("No strategy found for type: CUSTOM_TYPE");
    // Fallback logic
}
```

### 3.3. `getRegisteredTypes()`

```java
public java.util.Set<String> getRegisteredTypes()
```

**Retorna**: Conjunto de todos os tipos registrados

**Uso**:
```java
Set<String> availableTypes = registry.getRegisteredTypes();
log.info("Available compensation types: {}", availableTypes);
// Output: [ELIGIBILITY, CLAIM, CODING, GLOSAS, ...]
```

---

## 4. ESTRATÉGIAS REGISTRADAS (13 Total)

### 4.1. Ciclo Completo do Paciente

| Tipo | Descrição | Módulo BPMN |
|------|-----------|-------------|
| `AGENDAMENTO` | Rollback de agendamento | 01-Agendamento |
| `PRE_ATENDIMENTO` | Rollback de pré-atendimento | 02-Pre-Atendimento |
| `ELIGIBILITY` | Rollback de elegibilidade | 02-Pre-Atendimento |
| `ATENDIMENTO_CLINICO` | Rollback de atendimento | 03-Atendimento-Clinico |
| `CODING` | Rollback de codificação | 04-Codificacao |
| `AUDITORIA_MEDICA` | Rollback de auditoria | 04-Codificacao |

### 4.2. Faturamento e Cobrança

| Tipo | Descrição | Módulo BPMN |
|------|-----------|-------------|
| `CLAIM` | Rollback de submissão de guia | 05-Faturamento |
| `FATURAMENTO` | Rollback de faturamento | 05-Faturamento |
| `GLOSAS` | Rollback de gestão de glosas | 06-Glosas |
| `COBRANCA` | Rollback de cobrança | 07-Cobranca |
| `RECEBIMENTO_PAGAMENTO` | Rollback de recebimento | 08-Recebimento |

### 4.3. Gestão e Análise

| Tipo | Descrição | Módulo BPMN |
|------|-----------|-------------|
| `ANALISE_INDICADORES` | Rollback de análise | 09-Analise-Indicadores |
| `MELHORIA_CONTINUA` | Rollback de melhoria contínua | 10-Melhoria-Continua |

---

## 5. INICIALIZAÇÃO E LIFECYCLE

### 5.1. Startup Log
```
INFO  CompensationStrategyRegistry - Initialized CompensationStrategyRegistry with 13 strategies:
    [AGENDAMENTO, PRE_ATENDIMENTO, ELIGIBILITY, ATENDIMENTO_CLINICO, CODING,
     AUDITORIA_MEDICA, CLAIM, FATURAMENTO, GLOSAS, COBRANCA,
     RECEBIMENTO_PAGAMENTO, ANALISE_INDICADORES, MELHORIA_CONTINUA]
```

### 5.2. Health Check
```java
@Component
public class CompensationRegistryHealthIndicator implements HealthIndicator {

    @Autowired
    private CompensationStrategyRegistry registry;

    @Override
    public Health health() {
        Set<String> types = registry.getRegisteredTypes();

        if (types.isEmpty()) {
            return Health.down()
                .withDetail("reason", "No compensation strategies registered")
                .build();
        }

        return Health.up()
            .withDetail("strategies", types.size())
            .withDetail("types", types)
            .build();
    }
}
```

---

## 6. EXTENSIBILIDADE

### 6.1. Adicionando Nova Estratégia

**Passo 1**: Implementar interface
```java
@Slf4j
@Component
public class CustomCompensationStrategy implements CompensationStrategy {

    @Override
    public void execute(CompensationContext context) throws Exception {
        // Lógica de compensação
    }

    @Override
    public String getCompensationType() {
        return "CUSTOM";  // Identificador único
    }
}
```

**Passo 2**: Spring auto-registration
- Anotar com `@Component`
- Spring automaticamente injeta no registry
- Disponível imediatamente após startup

**Passo 3**: Usar no BPMN
```xml
<camunda:inputParameter name="compensationType">CUSTOM</camunda:inputParameter>
```

### 6.2. Estratégias Condicionais
```java
@Component
@Profile("production")  // Só em produção
public class ProductionOnlyStrategy implements CompensationStrategy {
    // ...
}

@Component
@ConditionalOnProperty(name = "features.custom-compensation", havingValue = "true")
public class FeatureFlagStrategy implements CompensationStrategy {
    // ...
}
```

---

## 7. TRATAMENTO DE ERROS

### 7.1. Estratégia Não Encontrada
```java
try {
    CompensationStrategy strategy = registry.getStrategy("UNKNOWN");
} catch (IllegalArgumentException e) {
    // Log completo do erro
    log.error("Strategy lookup failed: {}", e.getMessage());

    // Mensagem inclui tipos disponíveis
    // "No compensation strategy found for type: UNKNOWN.
    //  Available types: [ELIGIBILITY, CLAIM, ...]"

    // Notificar monitoramento
    metricsService.incrementCounter("compensation.strategy.not_found");

    // Re-lançar ou fallback
    throw new BpmnError("COMPENSATION_STRATEGY_NOT_FOUND", e.getMessage());
}
```

### 7.2. Duplicação de Tipos
```java
// Spring detecta automaticamente em startup
// Se dois beans retornam mesmo getCompensationType():

// Estratégia 1
@Component
public class Strategy1 implements CompensationStrategy {
    public String getCompensationType() { return "DUPLICATE"; }
}

// Estratégia 2
@Component
public class Strategy2 implements CompensationStrategy {
    public String getCompensationType() { return "DUPLICATE"; }
}

// Resultado: IllegalStateException durante startup
// "Duplicate key DUPLICATE (attempted merging values Strategy1 and Strategy2)"
```

---

## 8. MONITORAMENTO E MÉTRICAS

### 8.1. Métricas Recomendadas
```java
// Contador de lookups por tipo
registry.getStrategy(type);
metrics.counter("compensation.strategy.lookup", "type", type).increment();

// Gauge de estratégias registradas
metrics.gauge("compensation.strategy.count", registry.getRegisteredTypes().size());

// Alerta se tipos faltando
int expectedCount = 13;
int actualCount = registry.getRegisteredTypes().size();
if (actualCount < expectedCount) {
    alerts.warning("Missing compensation strategies", actualCount, expectedCount);
}
```

### 8.2. Logging
```java
// Startup
log.info("Registered strategies: {}", registry.getRegisteredTypes());

// Runtime lookup
log.debug("Looking up strategy for type: {}", compensationType);

// Erro
log.error("Strategy not found: {}. Available: {}",
    compensationType, registry.getRegisteredTypes());
```

---

## 9. REFERÊNCIAS TÉCNICAS

### 9.1. Documentação
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/domain/compensation/CompensationStrategyRegistry.java`
- **Protocol**: `AI_SWARM_EXECUTION_PROTOCOL.txt` (linhas 182-197)
- **Pattern**: Registry Pattern + Dependency Injection

### 9.2. Referências Relacionadas
- `RN-CompensationStrategy.md` - Interface registrada
- `RN-CompensationDelegateAdapter.md` - Uso do registry
- Todas as 13 estratégias concretas

### 9.3. Literatura
- Fowler, M. (2002). "Patterns of Enterprise Application Architecture" - Registry Pattern
- Spring Framework Documentation - Bean Discovery

---

## 10. NOTAS DE IMPLEMENTAÇÃO

### 10.1. Boas Práticas
- ✅ Garantir tipos únicos (sem duplicação)
- ✅ Logar todas as estratégias no startup
- ✅ Validar presença de estratégias críticas
- ✅ Usar `hasStrategy()` antes de `getStrategy()` para fluxos condicionais

### 10.2. Evitar
- ❌ Hard-coding de tipos (usar constantes)
- ❌ Assumir que estratégia existe
- ❌ Ignorar exceção `IllegalArgumentException`
- ❌ Criar múltiplos registries (singleton implícito via Spring)

---

**Autor**: Revenue Cycle Development Team
**Revisado por**: Hive Mind Architecture Agent
**Próxima Revisão**: 2026-03-25
