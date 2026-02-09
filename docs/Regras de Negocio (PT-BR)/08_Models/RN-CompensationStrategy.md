# RN-CompensationStrategy - Interface de Estratégia de Compensação SAGA

**Identificador**: RN-CompensationStrategy
**Módulo**: Domain Models - Compensation
**Tipo de Regra**: Interface Pattern (Strategy)
**Status**: Ativo ✅
**Versão**: 2.0
**Última Atualização**: 2025-12-25

---

## 1. DESCRIÇÃO GERAL

Interface que define o contrato para estratégias de compensação no padrão SAGA. Cada tipo de compensação implementa esta interface para fornecer lógica específica de rollback seguindo o Strategy Pattern.

### Padrão de Projeto
**Strategy Pattern** - Permite definir família de algoritmos de compensação, encapsular cada um deles e torná-los intercambiáveis.

---

## 2. ESTRUTURA DA INTERFACE

### 2.1. Métodos Principais

#### `execute(CompensationContext context)`
```java
void execute(CompensationContext context) throws Exception
```
- **Propósito**: Executa a lógica de compensação para esta estratégia
- **Parâmetros**:
  - `context`: Contexto de execução da compensação
- **Throws**: `Exception` se a compensação falhar
- **Obrigatório**: Sim

#### `getCompensationType()`
```java
String getCompensationType()
```
- **Retorna**: Identificador único do tipo de compensação
- **Exemplos**: "ELIGIBILITY", "CLAIM", "CODING", "GLOSAS"
- **Obrigatório**: Sim

#### `validate(CompensationContext context)`
```java
default ValidationResult validate(CompensationContext context)
```
- **Propósito**: Valida o contexto antes da execução
- **Retorna**: `ValidationResult` indicando sucesso ou falha
- **Default**: Retorna `ValidationResult.success()`
- **Obrigatório**: Não (método default)

---

## 3. IMPLEMENTAÇÕES CONCRETAS

### 3.1. Estratégias do Ciclo de Receita (13 Estratégias)

| Tipo | Classe | Descrição |
|------|--------|-----------|
| ELIGIBILITY | `EligibilityCompensationStrategy` | Rollback de verificação de elegibilidade |
| CLAIM | `ClaimCompensationStrategy` | Rollback de submissão de guia |
| CODING | `CodingCompensationStrategy` | Rollback de codificação médica |
| AGENDAMENTO | `AgendamentoCompensationStrategy` | Rollback de agendamento |
| PRE_ATENDIMENTO | `PreAtendimentoCompensationStrategy` | Rollback de pré-atendimento |
| ATENDIMENTO_CLINICO | `AtendimentoClinicoCompensationStrategy` | Rollback de atendimento clínico |
| FATURAMENTO | `FaturamentoCompensationStrategy` | Rollback de faturamento |
| AUDITORIA_MEDICA | `AuditoriaMedicaCompensationStrategy` | Rollback de auditoria médica |
| GLOSAS | `GlosasCompensationStrategy` | Rollback de gestão de glosas |
| COBRANCA | `CobrancaCompensationStrategy` | Rollback de cobrança |
| RECEBIMENTO_PAGAMENTO | `RecebimentoPagamentoCompensationStrategy` | Rollback de recebimento |
| ANALISE_INDICADORES | `AnaliseIndicadoresCompensationStrategy` | Rollback de análise |
| MELHORIA_CONTINUA | `MelhoriaContinuaCompensationStrategy` | Rollback de melhoria contínua |

---

## 4. INTEGRAÇÃO COM CAMUNDA

### 4.1. Uso via Adapter
```java
@Component("compensation")
public class CompensationDelegateAdapter {
    @Autowired
    private CompensationStrategyRegistry strategyRegistry;

    protected void executeBusinessLogic(DelegateExecution execution) {
        String compensationType = getVariable("compensationType");
        CompensationStrategy strategy = strategyRegistry.getStrategy(compensationType);
        strategy.execute(context);
    }
}
```

### 4.2. Configuração BPMN
```xml
<serviceTask id="compensateTask"
             name="Execute Compensation"
             camunda:delegateExpression="${compensation}">
  <extensionElements>
    <camunda:inputOutput>
      <camunda:inputParameter name="compensationType">ELIGIBILITY</camunda:inputParameter>
    </camunda:inputOutput>
  </extensionElements>
</serviceTask>
```

---

## 5. PADRÃO SAGA

### 5.1. Ordem de Execução
- **Normal**: Estratégias são executadas conforme necessário
- **Compensação**: Executadas em **ordem reversa (LIFO)**

### 5.2. Garantias
- ✅ **Idempotência**: Mesma compensação pode ser executada múltiplas vezes
- ✅ **Atomicidade**: Cada compensação é atômica
- ✅ **Isolamento**: Compensações não interferem entre si
- ⚠️ **Consistência**: Eventual (não ACID)

---

## 6. REFERÊNCIAS TÉCNICAS

### 6.1. Documentação
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/domain/compensation/CompensationStrategy.java`
- **Protocol**: `AI_SWARM_EXECUTION_PROTOCOL.txt` (linhas 150-155)
- **Pattern**: Strategy Pattern (GoF Design Patterns)

### 6.2. Referências Relacionadas
- `RN-CompensationContext.md` - Contexto de compensação
- `RN-ValidationResult.md` - Resultado de validação
- `RN-CompensationStrategyRegistry.md` - Registro de estratégias
- `RN-CompensationDelegateAdapter.md` - Adaptador Camunda

### 6.3. Literatura
- Garcia-Molina, H., & Salem, K. (1987). "Sagas" - Distributed Transactions Pattern
- Gamma et al. (1994). "Design Patterns: Elements of Reusable Object-Oriented Software"

---

## 7. EXEMPLOS DE USO

### 7.1. Implementação Simples
```java
@Component
public class CustomCompensationStrategy implements CompensationStrategy {

    @Override
    public void execute(CompensationContext context) throws Exception {
        String entityId = context.getVariable("entityId", String.class);
        // Lógica de compensação específica
        rollbackOperation(entityId);
    }

    @Override
    public String getCompensationType() {
        return "CUSTOM";
    }
}
```

### 7.2. Com Validação
```java
@Override
public ValidationResult validate(CompensationContext context) {
    String requiredField = context.getVariable("requiredField", String.class);
    if (requiredField == null) {
        return ValidationResult.failure("requiredField is mandatory");
    }
    return ValidationResult.success();
}
```

---

## 8. NOTAS DE IMPLEMENTAÇÃO

### 8.1. Boas Práticas
- ✅ Implementar validação para contextos complexos
- ✅ Logar todas as ações de compensação
- ✅ Garantir idempotência
- ✅ Tratar exceções específicas
- ✅ Notificar stakeholders relevantes

### 8.2. Considerações
- Compensações devem ser **sempre seguras** (não pioram o estado)
- Preferir **soft deletes** ao invés de exclusões físicas
- Manter **audit trail** completo
- Implementar **circuit breakers** para sistemas externos

---

**Autor**: Revenue Cycle Development Team
**Revisado por**: Hive Mind Architecture Agent
**Próxima Revisão**: 2026-03-25
