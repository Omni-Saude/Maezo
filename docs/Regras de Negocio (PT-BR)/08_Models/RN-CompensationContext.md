# RN-CompensationContext - Value Object para Contexto de Compensação

**Identificador**: RN-CompensationContext
**Módulo**: Domain Models - Compensation
**Tipo de Regra**: Value Object (DDD)
**Status**: Ativo ✅
**Versão**: 2.0
**Última Atualização**: 2025-12-25

---

## 1. DESCRIÇÃO GERAL

Value Object que encapsula todos os dados necessários para execução de estratégias de compensação. Fornece acesso tipo-seguro às variáveis de processo e metadados do contexto de compensação.

### Padrão de Projeto
**Value Object** - Objeto imutável que representa dados contextuais sem identidade própria.

---

## 2. ESTRUTURA DO MODELO

### 2.1. Atributos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `processInstanceId` | String | Sim | Identificador da instância do processo |
| `compensationType` | String | Sim | Tipo de compensação sendo executada |
| `processVariables` | Map<String, Object> | Sim | Todas as variáveis do processo |
| `businessKey` | String | Não | Chave de negócio da instância |
| `tenantId` | String | Não | Identificador do tenant (multi-tenancy) |

### 2.2. Métodos de Acesso

#### Acesso Genérico
```java
Object getVariable(String variableName)
```
- Retorna variável sem tipagem
- Retorna `null` se não encontrada

#### Acesso Tipado
```java
<T> T getVariable(String variableName, Class<T> type)
```
- Retorna variável com cast automático
- Type-safe com generics
- Retorna `null` se não encontrada

---

## 3. EXEMPLOS DE USO

### 3.1. Criação via Builder
```java
CompensationContext context = CompensationContext.builder()
    .processInstanceId("proc-123")
    .compensationType("ELIGIBILITY")
    .processVariables(Map.of(
        "eligibilityCheckId", "elig-456",
        "patientId", "pat-789"
    ))
    .businessKey("atd-001")
    .tenantId("hospital-A")
    .build();
```

### 3.2. Acesso a Variáveis
```java
// Acesso genérico
Object rawValue = context.getVariable("eligibilityCheckId");

// Acesso tipado
String eligibilityId = context.getVariable("eligibilityCheckId", String.class);
Double amount = context.getVariable("amount", Double.class);
List<String> codes = context.getVariable("codes", List.class);
```

### 3.3. Uso em Estratégia
```java
@Override
public void execute(CompensationContext context) throws Exception {
    String claimId = context.getVariable("claimId", String.class);
    String payerId = context.getVariable("payerId", String.class);
    Double amount = context.getVariable("amount", Double.class);

    log.info("Compensating claim: {}, payer: {}, amount: {}",
        claimId, payerId, amount);

    // Lógica de compensação
    reverseClaimSubmission(claimId, payerId, amount);
}
```

---

## 4. MAPEAMENTO CAMUNDA → DOMAIN

### 4.1. Conversão via Mapper
```java
@Component
public class ExecutionContextMapper {

    public CompensationContext toCompensationContext(
            DelegateExecution execution,
            String compensationType) {

        return CompensationContext.builder()
            .processInstanceId(execution.getProcessInstanceId())
            .compensationType(compensationType)
            .processVariables(execution.getVariables())
            .businessKey(execution.getBusinessKey())
            .tenantId(execution.getTenantId())
            .build();
    }
}
```

### 4.2. Uso no Adapter
```java
@Override
protected void executeBusinessLogic(DelegateExecution execution) {
    String compensationType = getVariable("compensationType");

    // Mapeia Camunda → Domain
    CompensationContext context = contextMapper
        .toCompensationContext(execution, compensationType);

    // Executa estratégia
    CompensationStrategy strategy = registry.getStrategy(compensationType);
    strategy.execute(context);
}
```

---

## 5. MULTI-TENANCY

### 5.1. Suporte a Múltiplos Tenants
```java
public class CompensationContext {
    private String tenantId;  // Hospital/Unidade identifier
}
```

### 5.2. Uso
```java
String tenantId = context.getTenantId();
if ("hospital-A".equals(tenantId)) {
    // Lógica específica do Hospital A
} else {
    // Lógica padrão
}
```

---

## 6. SEGURANÇA E VALIDAÇÃO

### 6.1. Validação de Contexto
```java
public ValidationResult validate(CompensationContext context) {
    List<String> errors = new ArrayList<>();

    if (context.getProcessInstanceId() == null) {
        errors.add("processInstanceId is required");
    }

    if (context.getCompensationType() == null) {
        errors.add("compensationType is required");
    }

    String entityId = context.getVariable("entityId", String.class);
    if (entityId == null) {
        errors.add("entityId is required for this compensation");
    }

    return errors.isEmpty()
        ? ValidationResult.success()
        : ValidationResult.failure(errors);
}
```

### 6.2. Sanitização de Dados
```java
String sanitizedInput = context.getVariable("userInput", String.class);
if (sanitizedInput != null) {
    sanitizedInput = HtmlUtils.htmlEscape(sanitizedInput);
}
```

---

## 7. REFERÊNCIAS TÉCNICAS

### 7.1. Documentação
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/domain/compensation/CompensationContext.java`
- **Pattern**: Value Object (Domain-Driven Design)
- **Annotations**: `@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`

### 7.2. Referências Relacionadas
- `RN-CompensationStrategy.md` - Interface de estratégia
- `RN-CompensationDelegateAdapter.md` - Adaptador Camunda
- `RN-ValidationResult.md` - Resultado de validação

### 7.3. Literatura
- Evans, E. (2003). "Domain-Driven Design: Tackling Complexity in the Heart of Software"
- Vernon, V. (2013). "Implementing Domain-Driven Design"

---

## 8. NOTAS DE IMPLEMENTAÇÃO

### 8.1. Boas Práticas
- ✅ Usar acesso tipado sempre que possível
- ✅ Validar variáveis obrigatórias antes de usar
- ✅ Tratar `null` values apropriadamente
- ✅ Logar variáveis para debug (sem dados sensíveis)

### 8.2. Evitar
- ❌ Modificar `processVariables` map diretamente
- ❌ Armazenar dados sensíveis sem criptografia
- ❌ Fazer cast sem try-catch
- ❌ Assumir que variáveis sempre existem

---

**Autor**: Revenue Cycle Development Team
**Revisado por**: Hive Mind Architecture Agent
**Próxima Revisão**: 2026-03-25
