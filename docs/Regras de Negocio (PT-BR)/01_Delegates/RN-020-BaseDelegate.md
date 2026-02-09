# RN-020: BaseDelegate - Template para Delegates do Camunda

**Classe**: `BaseDelegate.java`
**Tipo**: Classe Base Abstrata
**Prioridade**: CRÍTICA (Infraestrutura)
**Versão**: 1.0
**Última Atualização**: 2026-01-12

---

## 1. Visão Geral

### 1.1 Objetivo
Fornecer classe base abstrata para todos os JavaDelegates do Camunda, implementando funcionalidades comuns de idempotência, validação, tratamento de erros e manipulação de variáveis.

### 1.2 Escopo
- Template Method Pattern para execução de delegates
- Gerenciamento automático de idempotência
- Validação de contexto de execução
- Métodos auxiliares para variáveis de processo
- Tratamento padronizado de erros
- Avaliação de decisões DMN

### 1.3 Stakeholders
- **Primários**: Desenvolvedores de delegates, arquitetos de software
- **Secundários**: Administradores Camunda, QA

---

## 2. Regras de Negócio

### RN-020.1: Template Method Pattern
**Criticidade**: CRÍTICA
**Categoria**: Arquitetura de Código

**Descrição**:
BaseDelegate implementa Template Method Pattern para padronizar execução:

**Fluxo de Execução**:
```
1. Logging inicial
2. Validação de contexto
3. Verificação de idempotência (se habilitado)
4. Execução da lógica de negócio (abstrato)
5. Tratamento de erros
6. Logging final
```

**Implementação**:
```java
@Override
public final void execute(DelegateExecution execution) throws Exception {
    String processInstanceId = execution.getProcessInstanceId();
    String activityId = execution.getCurrentActivityId();
    String operationName = getOperationName();

    log.info("Starting delegate execution: processInstance={}, activity={}, operation={}",
             processInstanceId, activityId, operationName);

    try {
        validateExecutionContext(execution);

        if (requiresIdempotency()) {
            executeWithIdempotency(execution);
        } else {
            executeBusinessLogic(execution);
        }

        log.info("Delegate execution completed successfully");

    } catch (BpmnError e) {
        log.warn("BPMN error in delegate: error={}, message={}",
                e.getErrorCode(), e.getMessage());
        throw e;

    } catch (Exception e) {
        log.error("Technical error in delegate", e);
        handleTechnicalError(execution, e);
    }
}
```

**Método `final`**: Subclasses NÃO podem sobrescrever `execute()`

---

### RN-020.2: Métodos Abstratos Obrigatórios
**Criticidade**: CRÍTICA
**Categoria**: Contrato de Interface

**Descrição**:
Toda subclasse DEVE implementar:

**1. executeBusinessLogic()**:
```java
protected abstract void executeBusinessLogic(DelegateExecution execution)
    throws Exception;
```
- Contém a lógica de negócio específica do delegate
- Chamado pelo template method após validações

**2. getOperationName()**:
```java
public abstract String getOperationName();
```
- Retorna nome único da operação (ex: "submit_claim", "validate_insurance")
- Usado para logging e chave de idempotência

**Exemplo de Implementação**:
```java
@Component("myDelegate")
public class MyDelegate extends BaseDelegate {
    @Override
    protected void executeBusinessLogic(DelegateExecution execution) {
        // Lógica de negócio aqui
        String data = getRequiredVariable(execution, "myData", String.class);
        processData(data);
        setVariable(execution, "result", "success");
    }

    @Override
    public String getOperationName() {
        return "my_operation";
    }
}
```

---

### RN-020.3: Gerenciamento de Idempotência
**Criticidade**: CRÍTICA
**Categoria**: Confiabilidade

**Descrição**:
Idempotência garante que operação executada múltiplas vezes produza mesmo resultado:

**Habilitação de Idempotência**:
```java
public boolean requiresIdempotency() {
    return true; // DEFAULT
}
```

**Quando Desabilitar Idempotência**:
Override para `false` quando:
- Operação já é naturalmente idempotente
- Read-only queries (sem side effects)
- Performance crítica e duplicações improváveis

**Implementação de Idempotência**:
```java
private void executeWithIdempotency(DelegateExecution execution) throws Exception {
    Map<String, Object> inputParams = extractInputParameters(execution);

    idempotencyService.executeIdempotent(
        execution.getProcessInstanceId(),
        execution.getCurrentActivityId(),
        getOperationName(),
        inputParams,
        () -> {
            executeBusinessLogic(execution);
            return null;
        }
    );
}
```

**Chave de Idempotência**:
```
Hash(processInstanceId + activityId + operationName + inputParams)
```

---

### RN-020.4: Extração de Parâmetros para Idempotência
**Criticidade**: ALTA
**Categoria**: Configuração de Idempotência

**Descrição**:
Método `extractInputParameters()` define quais variáveis compõem a chave de idempotência:

**Implementação Padrão**:
```java
protected Map<String, Object> extractInputParameters(DelegateExecution execution) {
    return new HashMap<>(execution.getVariables()); // TODAS as variáveis
}
```

**Override Recomendado** (performance):
```java
@Override
protected Map<String, Object> extractInputParameters(DelegateExecution execution) {
    Map<String, Object> params = new HashMap<>();
    params.put("claimId", execution.getVariable("claimId"));
    params.put("patientId", execution.getVariable("patientId"));
    // Apenas variáveis relevantes
    return params;
}
```

**Benefícios do Override**:
- Chave de idempotência mais precisa
- Melhor performance (menos dados para hash)
- Evita falsos positivos

---

### RN-020.5: Validação de Contexto de Execução
**Criticidade**: CRÍTICA
**Categoria**: Validação de Entrada

**Descrição**:
Valida contexto antes de executar lógica de negócio:

**Validações Obrigatórias**:
```java
protected void validateExecutionContext(DelegateExecution execution) {
    Objects.requireNonNull(execution,
        "Execution context cannot be null");
    Objects.requireNonNull(execution.getProcessInstanceId(),
        "Process instance ID cannot be null");
    Objects.requireNonNull(execution.getCurrentActivityId(),
        "Activity ID cannot be null");
}
```

**Pode ser Sobrescrito**:
```java
@Override
protected void validateExecutionContext(DelegateExecution execution) {
    super.validateExecutionContext(execution); // Validações base

    // Validações adicionais
    if (execution.getVariable("criticalData") == null) {
        throw new IllegalArgumentException("criticalData is required");
    }
}
```

---

### RN-020.6: Tratamento de Erros BPMN
**Criticidade**: CRÍTICA
**Categoria**: Error Handling

**Descrição**:
Diferencia erros de negócio (BPMN) de erros técnicos:

**BPMN Errors** (esperados):
- São re-lançados para tratamento no processo
- Não geram logs de erro (apenas warning)
- Processados por Boundary Events no BPMN

**Technical Errors** (não esperados):
- Logados como ERROR
- Convertidos para RuntimeException por padrão
- Podem ser customizados via `handleTechnicalError()`

**Implementação**:
```java
try {
    executeBusinessLogic(execution);
} catch (BpmnError e) {
    // Re-throw BPMN errors
    log.warn("BPMN error: code={}, message={}",
            e.getErrorCode(), e.getMessage());
    throw e;

} catch (Exception e) {
    // Log e trata erros técnicos
    log.error("Technical error in " + getOperationName(), e);
    handleTechnicalError(execution, e);
}
```

**Customização de Tratamento**:
```java
@Override
protected void handleTechnicalError(DelegateExecution execution, Exception error) {
    // Enviar notificação de erro
    notificationService.sendErrorAlert(error);

    // Lançar como BPMN error se apropriado
    throw new BpmnError("TECHNICAL_ERROR", "System error: " + error.getMessage());
}
```

---

## 3. Manipulação de Variáveis

### RN-020.7: getRequiredVariable() - Variável Obrigatória
**Criticidade**: ALTA
**Categoria**: Validação de Variáveis

**Descrição**:
Obtém variável obrigatória com validação de tipo:

**Assinatura**:
```java
protected <T> T getRequiredVariable(DelegateExecution execution,
                                     String name, Class<T> type)
```

**Validações**:
1. Variável não pode ser null
2. Tipo deve corresponder ao esperado

**Erros BPMN**:
- `MISSING_VARIABLE`: Variável não encontrada
- `INVALID_VARIABLE_TYPE`: Tipo incorreto

**Implementação**:
```java
@SuppressWarnings("unchecked")
protected <T> T getRequiredVariable(DelegateExecution execution,
                                     String name, Class<T> type) {
    Object value = execution.getVariable(name);

    if (value == null) {
        throw new BpmnError("MISSING_VARIABLE",
            "Required variable not found: " + name);
    }

    if (!type.isInstance(value)) {
        throw new BpmnError("INVALID_VARIABLE_TYPE",
            String.format("Variable '%s' has incorrect type. Expected: %s, Actual: %s",
                name, type.getSimpleName(), value.getClass().getSimpleName()));
    }

    return (T) value;
}
```

**Exemplo de Uso**:
```java
String claimId = getRequiredVariable(execution, "claimId", String.class);
Integer amount = getRequiredVariable(execution, "claimAmount", Integer.class);
```

---

### RN-020.8: getVariable() - Variável Opcional
**Criticidade**: MÉDIA
**Categoria**: Obtenção de Variável

**Descrição**:
Obtém variável opcional com validação de tipo:

**Assinatura**:
```java
protected <T> T getVariable(DelegateExecution execution,
                            String name, Class<T> type)
```

**Comportamento**:
- Retorna `null` se variável não existir
- Retorna `null` se tipo incorreto (com warning no log)
- Não lança exceções

**Implementação**:
```java
@SuppressWarnings("unchecked")
protected <T> T getVariable(DelegateExecution execution,
                            String name, Class<T> type) {
    Object value = execution.getVariable(name);

    if (value == null) {
        return null;
    }

    if (!type.isInstance(value)) {
        log.warn("Variable '{}' has incorrect type. Expected: {}, Actual: {}",
                name, type.getSimpleName(), value.getClass().getSimpleName());
        return null;
    }

    return (T) value;
}
```

**Exemplo de Uso**:
```java
String notes = getVariable(execution, "additionalNotes", String.class);
if (notes != null) {
    processNotes(notes);
}
```

---

### RN-020.9: getVariable() com Default - Variável com Fallback
**Criticidade**: MÉDIA
**Categoria**: Obtenção de Variável

**Descrição**:
Obtém variável com valor padrão se ausente:

**Assinatura**:
```java
protected <T> T getVariable(DelegateExecution execution,
                            String name, Class<T> type, T defaultValue)
```

**Implementação**:
```java
protected <T> T getVariable(DelegateExecution execution,
                            String name, Class<T> type, T defaultValue) {
    T value = getVariable(execution, name, type);
    return value != null ? value : defaultValue;
}
```

**Alias**:
```java
protected <T> T getVariableOrDefault(DelegateExecution execution,
                                      String name, Class<T> type, T defaultValue) {
    return getVariable(execution, name, type, defaultValue);
}
```

**Exemplo de Uso**:
```java
Integer maxRetries = getVariable(execution, "maxRetries", Integer.class, 3);
Boolean autoApprove = getVariable(execution, "autoApprove", Boolean.class, false);
```

---

### RN-020.10: setVariable() - Escopo de Processo
**Criticidade**: ALTA
**Categoria**: Definição de Variável

**Descrição**:
Define variável no escopo de processo (visível para todo o processo):

**Assinatura**:
```java
protected void setVariable(DelegateExecution execution,
                           String name, Object value)
```

**Implementação**:
```java
protected void setVariable(DelegateExecution execution,
                           String name, Object value) {
    execution.setVariable(name, value);
    log.debug("Set variable: name={}, value={}, processInstance={}",
            name, value, execution.getProcessInstanceId());
}
```

**Escopo**: PROCESS (visível em todo processo, incluindo subprocessos)

**Exemplo de Uso**:
```java
setVariable(execution, "claimApproved", true);
setVariable(execution, "approvalDate", LocalDateTime.now());
```

---

### RN-020.11: setLocalVariable() - Escopo Local
**Criticidade**: MÉDIA
**Categoria**: Definição de Variável

**Descrição**:
Define variável no escopo local (apenas task/subprocess atual):

**Assinatura**:
```java
protected void setLocalVariable(DelegateExecution execution,
                                String name, Object value)
```

**Implementação**:
```java
protected void setLocalVariable(DelegateExecution execution,
                                String name, Object value) {
    execution.setVariableLocal(name, value);
    log.debug("Set local variable: name={}, value={}, activity={}",
            name, value, execution.getCurrentActivityId());
}
```

**Escopo**: LOCAL (não sobe para processo pai)

**Quando Usar**:
- Variáveis temporárias de subprocesso
- Dados que não devem poluir escopo global
- Informações específicas de uma atividade

**Exemplo de Uso**:
```java
setLocalVariable(execution, "tempCalculation", intermediateResult);
setLocalVariable(execution, "loopCounter", 5);
```

---

## 4. Integração com DMN

### RN-020.12: Avaliação de Decisões DMN
**Criticidade**: MÉDIA
**Categoria**: Decision Management

**Descrição**:
Método auxiliar para avaliar tabelas de decisão DMN:

**Assinatura**:
```java
protected Map<String, Object> evaluateDMN(DelegateExecution execution,
                                           String decisionKey,
                                           Map<String, Object> variables)
```

**Implementação**:
```java
protected Map<String, Object> evaluateDMN(DelegateExecution execution,
                                           String decisionKey,
                                           Map<String, Object> variables) throws Exception {
    log.debug("Evaluating DMN decision: key={}, variables={}", decisionKey, variables);

    try {
        DecisionService decisionService =
            execution.getProcessEngineServices().getDecisionService();

        DmnDecisionResult result = decisionService
            .evaluateDecisionByKey(decisionKey)
            .variables(variables)
            .evaluate();

        if (result == null || result.isEmpty()) {
            log.warn("DMN evaluation returned no results for decision: {}", decisionKey);
            return new HashMap<>();
        }

        Map<String, Object> dmnResult = result.getSingleResult().getEntryMap();
        log.debug("DMN evaluation successful: key={}, result={}", decisionKey, dmnResult);
        return dmnResult;

    } catch (Exception e) {
        log.error("DMN evaluation failed: key={}, variables={}", decisionKey, variables, e);
        throw new RuntimeException("Failed to evaluate DMN decision: " + decisionKey, e);
    }
}
```

**Exemplo de Uso**:
```java
Map<String, Object> inputs = new HashMap<>();
inputs.put("claimAmount", 5000);
inputs.put("patientAge", 45);
inputs.put("serviceType", "SURGERY");

Map<String, Object> decision = evaluateDMN(execution, "claim_approval", inputs);
Boolean approved = (Boolean) decision.get("approved");
String reason = (String) decision.get("reason");
```

**Política de Hit**: Retorna single result (primeira regra que bate)

---

### RN-020.13: Tratamento de Resultados DMN Vazios
**Criticidade**: MÉDIA
**Categoria**: Resilience

**Descrição**:
Se DMN não retornar resultados, retorna Map vazio (não null):

**Comportamento**:
- Loga warning se resultado vazio
- Retorna `new HashMap<>()` (nunca null)
- Permite código chamador continuar sem NPE

**Justificativa**:
- Algumas tabelas DMN podem não ter hits válidos
- Default values podem ser aplicados pelo chamador
- Evita propagação de null

---

## 5. Dependências

### RN-020.14: Injeção de IdempotencyService
**Criticidade**: CRÍTICA
**Categoria**: Service Dependency

**Descrição**:
IdempotencyService é injetado via Spring:

**Declaração**:
```java
@Autowired
protected IdempotencyService idempotencyService;
```

**Visibilidade**: `protected` (subclasses podem acessar se necessário)

**Uso Automático**: BaseDelegate gerencia automaticamente quando `requiresIdempotency() == true`

---

## 6. Casos de Uso

### 6.1 Delegate Simples sem Idempotência
```java
@Component("readOnlyQueryDelegate")
public class ReadOnlyQueryDelegate extends BaseDelegate {

    @Override
    protected void executeBusinessLogic(DelegateExecution execution) {
        String patientId = getRequiredVariable(execution, "patientId", String.class);
        Patient patient = patientRepository.findById(patientId);
        setVariable(execution, "patientData", patient);
    }

    @Override
    public String getOperationName() {
        return "query_patient";
    }

    @Override
    public boolean requiresIdempotency() {
        return false; // Read-only, sem side effects
    }
}
```

---

### 6.2 Delegate com Idempotência e Parâmetros Customizados
```java
@Component("submitClaimDelegate")
public class SubmitClaimDelegate extends BaseDelegate {

    @Autowired
    private ClaimSubmissionService claimService;

    @Override
    protected void executeBusinessLogic(DelegateExecution execution) {
        String claimId = getRequiredVariable(execution, "claimId", String.class);
        Integer amount = getRequiredVariable(execution, "claimAmount", Integer.class);
        Boolean expedited = getVariable(execution, "expedited", Boolean.class, false);

        ClaimSubmissionResult result = claimService.submit(claimId, amount, expedited);

        setVariable(execution, "submissionId", result.getSubmissionId());
        setVariable(execution, "submittedAt", result.getTimestamp());
    }

    @Override
    protected Map<String, Object> extractInputParameters(DelegateExecution execution) {
        Map<String, Object> params = new HashMap<>();
        params.put("claimId", execution.getVariable("claimId"));
        params.put("claimAmount", execution.getVariable("claimAmount"));
        // NÃO inclui 'expedited' - não afeta idempotência
        return params;
    }

    @Override
    public String getOperationName() {
        return "submit_claim";
    }

    @Override
    public boolean requiresIdempotency() {
        return true; // Submissão é crítica - evitar duplicatas
    }
}
```

---

### 6.3 Delegate com DMN e Error Handling
```java
@Component("approveClaimDelegate")
public class ApproveClaimDelegate extends BaseDelegate {

    @Override
    protected void executeBusinessLogic(DelegateExecution execution) throws Exception {
        String claimId = getRequiredVariable(execution, "claimId", String.class);
        Integer amount = getRequiredVariable(execution, "claimAmount", Integer.class);

        // Avalia DMN para determinar aprovação
        Map<String, Object> inputs = Map.of(
            "amount", amount,
            "serviceType", execution.getVariable("serviceType")
        );

        Map<String, Object> decision = evaluateDMN(execution, "claim_approval", inputs);
        Boolean approved = (Boolean) decision.get("approved");
        String reason = (String) decision.get("reason");

        if (!approved) {
            throw new BpmnError("CLAIM_DENIED", "Claim denied: " + reason);
        }

        setVariable(execution, "approvalReason", reason);
        setVariable(execution, "approved", true);
    }

    @Override
    protected void handleTechnicalError(DelegateExecution execution, Exception error) {
        // Notifica equipe de suporte
        supportService.notifyError(execution.getProcessInstanceId(), error);
        // Re-lança erro
        throw new RuntimeException("Failed to approve claim", error);
    }

    @Override
    public String getOperationName() {
        return "approve_claim";
    }
}
```

---

## 7. Logging Estruturado

### RN-020.15: Padrões de Logging
**Criticidade**: MÉDIA
**Categoria**: Observability

**Descrição**:
BaseDelegate implementa logging estruturado:

**Início de Execução** (INFO):
```
Starting delegate execution: processInstance=abc-123, activity=Task_Submit, operation=submit_claim, businessKey=CLM-001
```

**Sucesso** (INFO):
```
Delegate execution completed successfully: processInstance=abc-123, activity=Task_Submit, operation=submit_claim
```

**BPMN Error** (WARN):
```
BPMN error in delegate: processInstance=abc-123, activity=Task_Submit, error=CLAIM_DENIED, message=Amount exceeds limit
```

**Technical Error** (ERROR):
```
Technical error in delegate: processInstance=abc-123, activity=Task_Submit, operation=submit_claim
[Stack trace]
```

**Set Variable** (DEBUG):
```
Set variable: name=claimApproved, value=true, processInstance=abc-123
```

---

## 8. Referências

- **Código Fonte**: `src/main/java/com/hospital/revenuecycle/delegates/BaseDelegate.java`
- **Service**: `IdempotencyService.java`
- **ADR**: ADR-003 (BPMN Implementation Standards)
- **Design Pattern**: Template Method Pattern (Gang of Four)
- **Camunda Docs**: https://docs.camunda.org/manual/latest/user-guide/process-engine/delegation-code/

---

## X. Conformidade Regulatória

### 10.1 Requisitos ANS
- **RN 395/2016**: Rastreabilidade de execução de delegates - todas as operações logadas
- **RN 442/2018**: Auditoria de qualidade - trilha completa de processamento BPMN
- **Retenção de logs**: 5 anos para conformidade ANS/SOX

### 10.2 LGPD
- **Art. 48 LGPD**: Comunicação de incidentes - error handling padronizado
- **Art. 49 LGPD**: Auditoria de segurança - rastreamento de todas as execuções
- **Minimização**: Template method garante logging estruturado sem dados excessivos

### 10.3 SOX Compliance
- **Seção 404**: Controles internos sobre processamento de dados financeiros
- **Idempotência**: Previne execuções duplicadas que afetam relatórios financeiros
- **Audit trail**: Logging obrigatório com timestamp, processInstanceId e activityId

---

## XI. Notas de Migração - Camunda 7 para Camunda 8

### 11.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: Job Worker base class para External Tasks
- **Implementação**: Template similar mas com Zeebe Client
- **Vantagens**: Escalabilidade horizontal, backpressure, retry policies nativos

### 11.2 Nível de Complexidade
- **Complexidade de Migração**: BAIXA (1-2 dias)
- **Justificativa**: Pattern reutilizável, sem dependências de banco, stateless

### 11.3 Breaking Changes
- **DelegateExecution → JobClient**: Mudança de interface de contexto de execução
- **BPMN Error → Zeebe Incident**: Modelo de erro diferente (incident throwing)
- **Variáveis**: Zeebe usa JSON serialization ao invés de ObjectValue
- **Idempotência**: Requer implementação externa (Redis/DB) ao invés de in-memory

### 11.4 Implementação Camunda 8
```java
@JobWorker(type = "my-operation")
public abstract class BaseJobWorker {
    protected abstract void executeBusinessLogic(
        ActivatedJob job, JobClient client);

    @Override
    public void handle(JobClient client, ActivatedJob job) {
        // Template method similar
        log.info("Starting job: processInstanceKey={}",
            job.getProcessInstanceKey());
        try {
            validateJobContext(job);
            if (requiresIdempotency()) {
                executeWithIdempotency(client, job);
            } else {
                executeBusinessLogic(job, client);
            }
            client.newCompleteCommand(job.getKey()).send().join();
        } catch (Exception e) {
            client.newThrowErrorCommand(job.getKey())
                .errorCode("TECHNICAL_ERROR")
                .send().join();
        }
    }
}
```

---

## XII. Mapeamento DDD

### 12.1 Bounded Context
- **Contexto Delimitado**: `Shared Kernel / Infrastructure`
- **Linguagem Ubíqua**: Template method, idempotency, execution context, business logic

### 12.2 Aggregate Root
- **N/A**: BaseDelegate é infraestrutura técnica, não modelo de domínio

### 12.3 Domain Events
- **N/A**: BaseDelegate não emite eventos de domínio (apenas logging técnico)

### 12.4 Padrões Aplicados
- **Template Method Pattern**: Padronização de execução de delegates
- **Dependency Injection**: Spring autowiring para services
- **Strategy Pattern**: Subclasses definem estratégias específicas via `executeBusinessLogic()`

### 12.5 Candidato a Biblioteca Compartilhada
- **Tipo**: Shared Library (não microserviço)
- **Uso**: Todos os microserviços que executam workflows Camunda
- **Distribuição**: Maven/Gradle dependency comum

---

## XIII. Metadados Técnicos

### 13.1 Características
- **Tipo**: Abstract Base Class (Template Method Pattern)
- **Execução**: Definida por subclasse (síncrona por padrão)
- **Idempotência**: Configurável via `requiresIdempotency()`
- **Transacional**: Dependente da implementação da subclasse

### 13.2 Métricas de Qualidade
- **Complexidade Ciclomática**: BAIXA (lógica simples de orquestração)
- **Cobertura de Testes Recomendada**: 95% (infraestrutura crítica)
- **Reusabilidade**: ALTA (base para todos os delegates do sistema)

### 13.3 Impacto de Performance
- **I/O**: LOW (apenas logging)
- **CPU**: LOW (orchestration overhead mínimo)
- **Memória**: LOW (poucos objetos criados)

### 13.4 Dependências de Runtime
- Spring Framework (DI, @Autowired)
- Camunda BPM Engine 7.x (DelegateExecution, BpmnError)
- IdempotencyService (custom, opcional se `requiresIdempotency() == false`)
- SLF4J (logging)

---

**Documento gerado por**: AI Swarm - Hive Mind Documentation Generator
**Total de Regras**: 14 regras de negócio (padrões arquiteturais)
**Revisão**: Necessária por arquitetos de software
**Próxima revisão**: Quando houver mudanças nos padrões de desenvolvimento Camunda
