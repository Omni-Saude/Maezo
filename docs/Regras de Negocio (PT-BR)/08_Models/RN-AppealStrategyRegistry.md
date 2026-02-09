# RN-AppealStrategyRegistry - Registro de Estratégias de Recurso

**Categoria:** Modelo de Domínio - Registry Pattern
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.AppealStrategyRegistry`
**Tipo:** Component Registry

---

## Descrição
Componente responsável por gerenciar e fornecer acesso às diferentes estratégias de recurso de glosa. Implementa o padrão Registry para permitir seleção dinâmica de estratégias.

## Estrutura

```java
@Slf4j
@Component
public class AppealStrategyRegistry {
    private final Map<String, AppealStrategy> strategies = new HashMap<>();
    private final AppealStrategy defaultStrategy;

    @Autowired
    public AppealStrategyRegistry(List<AppealStrategy> strategyList,
                                 StandardAppealStrategy defaultStrategy) {
        this.defaultStrategy = defaultStrategy;
        // Registro automático via Spring DI
        for (AppealStrategy strategy : strategyList) {
            String key = strategy.getStrategyType();
            strategies.put(key, strategy);
            log.debug("Registered appeal strategy: {}", key);
        }
        mapStrategyAliases();
    }
}
```

## Responsabilidades

1. **Auto-registro:** Registra todas implementações de `AppealStrategy` via Spring DI
2. **Mapeamento de Aliases:** Mapeia nomes alternativos para estratégias
3. **Seleção de Estratégia:** Retorna estratégia apropriada ou fallback
4. **Extensibilidade:** Permite adicionar novas estratégias sem modificar código

## Métodos

### 1. getStrategy
```java
public AppealStrategy getStrategy(String appealStrategy)
```

**Descrição:** Retorna estratégia registrada ou estratégia padrão

**Parâmetros:**
- `appealStrategy` - Nome/código da estratégia desejada

**Retorno:**
- `AppealStrategy` - Implementação encontrada ou `StandardAppealStrategy` (default)

**Comportamento:**
```java
AppealStrategy strategy = strategies.get(appealStrategy);

if (strategy == null) {
    log.warn("No strategy found for: {}. Using default.", appealStrategy);
    return defaultStrategy;
}

return strategy;
```

**Exemplos:**
```java
// Estratégia existente
AppealStrategy strategy = registry.getStrategy("MEDICAL_NECESSITY");
// Retorna: MedicalNecessityAppealStrategy

// Estratégia não existente
AppealStrategy strategy = registry.getStrategy("UNKNOWN_STRATEGY");
// Retorna: StandardAppealStrategy (default)
// Log: WARN "No strategy found for: UNKNOWN_STRATEGY. Using default."
```

### 2. mapStrategyAliases (private)
```java
private void mapStrategyAliases()
```

**Descrição:** Configura mapeamentos de aliases para estratégias

**Aliases Padrão:**
- "MEDICAL_NECESSITY_APPEAL" → "MEDICAL_NECESSITY"
- "COMPREHENSIVE_APPEAL" → StandardAppealStrategy
- "QUICK_REVIEW_AND_RESUBMIT" → StandardAppealStrategy
- "AUTHORIZATION_APPEAL" → StandardAppealStrategy
- "ELIGIBILITY_VERIFICATION_APPEAL" → StandardAppealStrategy
- "CODING_REVIEW_APPEAL" → StandardAppealStrategy
- "MODIFIER_CORRECTION_APPEAL" → StandardAppealStrategy
- "TIMELY_FILING_APPEAL" → StandardAppealStrategy
- "DUPLICATE_CLAIM_RESOLUTION" → StandardAppealStrategy
- "STANDARD_APPEAL" → StandardAppealStrategy

## Regras de Negócio

### RN-STRATEGY-REG-001: Auto-registro via Spring DI
**Descrição:** Todas as implementações de AppealStrategy são automaticamente registradas
**Mecanismo:** Constructor injection de `List<AppealStrategy>`
**Vantagem:** Adicionar nova estratégia não requer modificação do registry

### RN-STRATEGY-REG-002: Chave de Registro
**Descrição:** Cada estratégia é indexada por seu `getStrategyType()`
**Formato:** String uppercase (ex: "STANDARD", "MEDICAL_NECESSITY")
**Unicidade:** Chave deve ser única; últimas registradas sobrescrevem

### RN-STRATEGY-REG-003: Estratégia Padrão (Fallback)
**Descrição:** Se estratégia não encontrada, usa `StandardAppealStrategy`
**Benefício:** Sistema nunca falha por estratégia ausente
**Log:** WARNING é registrado para auditoria

### RN-STRATEGY-REG-004: Aliases para Compatibilidade
**Descrição:** Múltiplos nomes podem mapear para mesma estratégia
**Uso:** Compatibilidade com sistemas legacy ou nomes de processo BPMN

### RN-STRATEGY-REG-005: Logging de Registro
**Descrição:** DEBUG log para cada estratégia registrada
**Formato:** "Registered appeal strategy: {strategyType}"
**Uso:** Troubleshooting e verificação de configuração

## Fluxo de Inicialização

```
┌─ Spring Container Startup ─────────────────────────┐
│                                                      │
│ 1. Spring identifica @Component AppealStrategy      │
│    - StandardAppealStrategy                          │
│    - MedicalNecessityAppealStrategy                  │
│    - (outras implementações)                         │
│    ↓                                                 │
│ 2. Injeta List<AppealStrategy> no construtor       │
│    ↓                                                 │
│ 3. AppealStrategyRegistry construtor executado      │
│    ↓                                                 │
│ 4. Loop: Para cada strategy na lista                │
│    key = strategy.getStrategyType()                 │
│    strategies.put(key, strategy)                    │
│    log.debug("Registered: {}", key)                 │
│    ↓                                                 │
│ 5. mapStrategyAliases() executado                   │
│    - Mapeia MEDICAL_NECESSITY_APPEAL → MEDICAL_NECESSITY│
│    - Mapeia aliases para defaultStrategy            │
│    ↓                                                 │
│ 6. Registry pronto para uso                         │
│                                                      │
└──────────────────────────────────────────────────────┘
```

## Integração com Spring

### Injeção de Dependências
```java
// Spring encontra todas as implementações
@Autowired
public AppealStrategyRegistry(
    List<AppealStrategy> strategyList,  // Todas as implementações
    StandardAppealStrategy defaultStrategy) { // Estratégia padrão específica
    // ...
}
```

### Declaração de Estratégias
```java
// Cada implementação deve ser um Spring Component
@Component("standardAppeal")
public class StandardAppealStrategy implements AppealStrategy { }

@Component("medicalNecessityAppeal")
public class MedicalNecessityAppealStrategy implements AppealStrategy { }
```

## Uso no Sistema

### No AppealDocumentService
```java
@Service
public class AppealDocumentService {
    private final AppealStrategyRegistry strategyRegistry;

    public AppealPackage prepareAppealPackage(AppealRequest request) {
        // Busca estratégia via registry
        AppealStrategy strategy = strategyRegistry.getStrategy(
            request.getAppealStrategy());

        // Usa estratégia para gerar documentos
        List<String> docs = strategy.generateDocuments(request);
        // ...
    }
}
```

### No BPMN Process
```java
// Processo define estratégia via variável
execution.setVariable("appealStrategy", "MEDICAL_NECESSITY");

// Delegate busca estratégia via registry
String strategyName = (String) execution.getVariable("appealStrategy");
AppealStrategy strategy = registry.getStrategy(strategyName);
```

## Extensibilidade

### Adicionar Nova Estratégia

**Passo 1:** Criar implementação
```java
@Component("urgentAppeal")
public class UrgentAppealStrategy implements AppealStrategy {
    @Override
    public String getStrategyType() {
        return "URGENT";
    }

    @Override
    public List<String> generateDocuments(AppealRequest request) {
        // Implementação específica
    }

    @Override
    public boolean requiresClinicalDocumentation() {
        return true;
    }

    @Override
    public int getMinimumDocumentCount() {
        return 5;
    }
}
```

**Passo 2:** Spring auto-registra (nenhuma modificação necessária no Registry)

**Passo 3:** Usar a estratégia
```java
AppealStrategy strategy = registry.getStrategy("URGENT");
```

### Adicionar Aliases Customizados
```java
private void mapStrategyAliases() {
    // ... aliases existentes

    // Adicionar novos aliases
    if (strategies.containsKey("URGENT")) {
        strategies.put("HIGH_PRIORITY_APPEAL", strategies.get("URGENT"));
        strategies.put("EMERGENCY_APPEAL", strategies.get("URGENT"));
    }
}
```

## Logging

### Durante Inicialização
```
DEBUG: Registered appeal strategy: STANDARD
DEBUG: Registered appeal strategy: MEDICAL_NECESSITY
DEBUG: Registered appeal strategy: URGENT
```

### Durante Uso
```
WARN: No strategy found for: UNKNOWN_TYPE. Using default.
```

## Testes

### Cenários de Teste
```java
@Test
void shouldReturnMedicalNecessityStrategy() {
    AppealStrategy strategy = registry.getStrategy("MEDICAL_NECESSITY");
    assertThat(strategy).isInstanceOf(MedicalNecessityAppealStrategy.class);
}

@Test
void shouldReturnDefaultStrategyForUnknown() {
    AppealStrategy strategy = registry.getStrategy("UNKNOWN");
    assertThat(strategy).isInstanceOf(StandardAppealStrategy.class);
}

@Test
void shouldResolveAlias() {
    AppealStrategy strategy = registry.getStrategy("MEDICAL_NECESSITY_APPEAL");
    assertThat(strategy).isInstanceOf(MedicalNecessityAppealStrategy.class);
}

@Test
void shouldLogWarningForUnknownStrategy() {
    // Capturar logs e verificar WARNING
    registry.getStrategy("INVALID_STRATEGY");
    // Assert: log contém "No strategy found for: INVALID_STRATEGY"
}
```

## Performance

- **Lookup:** O(1) - HashMap.get()
- **Inicialização:** O(n) - n = número de estratégias
- **Memória:** HashMap pequeno (~10 entries)
- **Thread-Safety:** Imutável após inicialização (thread-safe)

## Padrões de Design

### Registry Pattern
- Centraliza registro e busca de estratégias
- Desacopla cliente de implementações concretas

### Strategy Pattern
- Permite trocar algoritmos dinamicamente
- Implementações intercambiáveis

### Dependency Injection
- Spring gerencia ciclo de vida
- Auto-descoberta de implementações

## Melhores Práticas

### ✓ BOM
```java
// Verificar se estratégia existe antes de usar
AppealStrategy strategy = registry.getStrategy(appealStrategyName);
if (strategy instanceof StandardAppealStrategy &&
    !appealStrategyName.equals("STANDARD")) {
    log.warn("Fallback to default strategy for: {}", appealStrategyName);
}
```

### ✗ RUIM
```java
// Assumir que estratégia existe
AppealStrategy strategy = registry.getStrategy(appealStrategyName);
// Se não existir, pode não ser o comportamento esperado
```

## Configuração

### Application Properties (futuro)
```yaml
appeal:
  strategies:
    default: STANDARD
    aliases:
      URGENT_APPEAL: MEDICAL_NECESSITY
      FAST_TRACK: STANDARD
```

## Monitoramento

### Métricas Úteis
- Número de estratégias registradas
- Frequência de uso por estratégia
- Taxa de fallback para default
- Tempo médio de execução por estratégia

## Conformidade

- **Open/Closed Principle:** Aberto para extensão, fechado para modificação
- **Dependency Inversion:** Depende de abstração (AppealStrategy)
- **Single Responsibility:** Apenas gerencia registro de estratégias

## Referências
- `AppealStrategy.java` - Interface base
- `StandardAppealStrategy.java` - Implementação padrão
- `MedicalNecessityAppealStrategy.java` - Implementação específica
- `AppealDocumentService.java` - Principal consumidor
