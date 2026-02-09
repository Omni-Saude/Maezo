# RN-ValidationResult - Value Object para Resultado de Validação

**Identificador**: RN-ValidationResult
**Módulo**: Domain Models - Compensation
**Tipo de Regra**: Value Object (DDD)
**Status**: Ativo ✅
**Versão**: 2.0
**Última Atualização**: 2025-12-25

---

## 1. DESCRIÇÃO GERAL

Value Object que representa o resultado de uma validação de contexto de compensação. Encapsula o status de sucesso/falha e mensagens de erro de forma imutável e tipo-segura.

### Padrão de Projeto
**Value Object + Result Pattern** - Retorna resultado de operação com sucesso ou erros, sem usar exceções para fluxo de controle.

---

## 2. ESTRUTURA DO MODELO

### 2.1. Atributos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `valid` | boolean | Indica se a validação foi bem-sucedida |
| `errors` | List<String> | Lista de mensagens de erro (vazia se válido) |

### 2.2. Métodos Factory

#### `success()`
```java
public static ValidationResult success()
```
- Cria resultado de validação bem-sucedida
- `valid = true`
- `errors = []`

#### `failure(List<String> errors)`
```java
public static ValidationResult failure(List<String> errors)
```
- Cria resultado com múltiplos erros
- `valid = false`
- `errors = cópia da lista fornecida`

#### `failure(String error)`
```java
public static ValidationResult failure(String error)
```
- Cria resultado com erro único
- `valid = false`
- `errors = [error]`

### 2.3. Métodos de Acesso

#### `getErrors()`
```java
public List<String> getErrors()
```
- Retorna lista imutável de erros
- **Nunca retorna `null`** - retorna lista vazia se não houver erros

---

## 3. EXEMPLOS DE USO

### 3.1. Validação Bem-Sucedida
```java
@Override
public ValidationResult validate(CompensationContext context) {
    String claimId = context.getVariable("claimId", String.class);

    if (claimId != null && !claimId.isEmpty()) {
        return ValidationResult.success();
    }

    return ValidationResult.failure("claimId is required");
}
```

### 3.2. Múltiplos Erros
```java
@Override
public ValidationResult validate(CompensationContext context) {
    List<String> errors = new ArrayList<>();

    if (context.getVariable("claimId") == null) {
        errors.add("claimId is required");
    }

    if (context.getVariable("payerId") == null) {
        errors.add("payerId is required");
    }

    Double amount = context.getVariable("amount", Double.class);
    if (amount == null || amount <= 0) {
        errors.add("amount must be greater than zero");
    }

    return errors.isEmpty()
        ? ValidationResult.success()
        : ValidationResult.failure(errors);
}
```

### 3.3. Uso em Adapter
```java
@Override
protected void executeBusinessLogic(DelegateExecution execution) {
    CompensationContext context = mapper.toCompensationContext(execution);
    CompensationStrategy strategy = registry.getStrategy(compensationType);

    // Valida antes de executar
    ValidationResult validation = strategy.validate(context);

    if (!validation.isValid()) {
        String errorMessage = "Validation failed: " +
            String.join(", ", validation.getErrors());

        log.error("Compensation validation failed: {}", errorMessage);
        throw new BpmnError("COMPENSATION_VALIDATION_FAILED", errorMessage);
    }

    // Executa compensação
    strategy.execute(context);
}
```

---

## 4. VALIDAÇÕES COMUNS

### 4.1. Campos Obrigatórios
```java
private ValidationResult validateRequiredFields(CompensationContext context) {
    List<String> errors = new ArrayList<>();

    for (String field : REQUIRED_FIELDS) {
        if (context.getVariable(field) == null) {
            errors.add(field + " is required");
        }
    }

    return errors.isEmpty()
        ? ValidationResult.success()
        : ValidationResult.failure(errors);
}
```

### 4.2. Validações de Negócio
```java
private ValidationResult validateBusinessRules(CompensationContext context) {
    String claimStatus = context.getVariable("claimStatus", String.class);

    if ("PAID".equals(claimStatus)) {
        return ValidationResult.failure(
            "Cannot compensate paid claim. Use refund process instead."
        );
    }

    if ("CANCELLED".equals(claimStatus)) {
        return ValidationResult.failure(
            "Claim already cancelled. No compensation needed."
        );
    }

    return ValidationResult.success();
}
```

### 4.3. Validações Compostas
```java
@Override
public ValidationResult validate(CompensationContext context) {
    ValidationResult requiredFields = validateRequiredFields(context);
    if (!requiredFields.isValid()) {
        return requiredFields;
    }

    ValidationResult businessRules = validateBusinessRules(context);
    if (!businessRules.isValid()) {
        return businessRules;
    }

    return ValidationResult.success();
}
```

---

## 5. INTEGRAÇÃO COM CAMUNDA

### 5.1. Tratamento de Erros BPMN
```java
if (!validation.isValid()) {
    String errors = String.join("; ", validation.getErrors());

    // Lança erro BPMN para ativar boundary event
    throw new BpmnError(
        "COMPENSATION_VALIDATION_FAILED",
        "Validation errors: " + errors
    );
}
```

### 5.2. Armazenamento em Variáveis
```java
if (!validation.isValid()) {
    execution.setVariable("validationErrors", validation.getErrors());
    execution.setVariable("validationFailed", true);

    // Log para auditoria
    log.error("Compensation validation failed for process {}: {}",
        execution.getProcessInstanceId(),
        validation.getErrors());
}
```

---

## 6. PADRÕES DE MENSAGEM DE ERRO

### 6.1. Mensagens Claras
```java
// ✅ BOM - Específico e acionável
"claimId is required for claim compensation"
"amount must be greater than zero"
"claimStatus must be SUBMITTED or PENDING, found: PAID"

// ❌ RUIM - Vago e não acionável
"Invalid input"
"Error"
"Validation failed"
```

### 6.2. Mensagens Internacionalizadas
```java
private static final String REQUIRED_FIELD = "field.required";
private static final String INVALID_AMOUNT = "amount.invalid";

return ValidationResult.failure(
    messageSource.getMessage(REQUIRED_FIELD,
        new Object[]{"claimId"},
        LocaleContextHolder.getLocale())
);
```

---

## 7. REFERÊNCIAS TÉCNICAS

### 7.1. Documentação
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/domain/compensation/ValidationResult.java`
- **Pattern**: Value Object + Result Pattern
- **Annotations**: `@Data`, `@NoArgsConstructor`, `@AllArgsConstructor`

### 7.2. Referências Relacionadas
- `RN-CompensationStrategy.md` - Interface que usa ValidationResult
- `RN-CompensationContext.md` - Contexto sendo validado
- `RN-CompensationDelegateAdapter.md` - Uso em produção

### 7.3. Literatura
- Martin, R. C. (2008). "Clean Code: A Handbook of Agile Software Craftsmanship"
- Result Pattern: Railway Oriented Programming (Scott Wlaschin)

---

## 8. NOTAS DE IMPLEMENTAÇÃO

### 8.1. Boas Práticas
- ✅ Sempre retornar lista imutável
- ✅ Mensagens de erro claras e acionáveis
- ✅ Validar early, fail fast
- ✅ Logar erros de validação para auditoria

### 8.2. Evitar
- ❌ Retornar `null` ao invés de lista vazia
- ❌ Mensagens genéricas de erro
- ❌ Misturar validação com lógica de negócio
- ❌ Usar exceções para validações esperadas

---

**Autor**: Revenue Cycle Development Team
**Revisado por**: Hive Mind Architecture Agent
**Próxima Revisão**: 2026-03-25
