# RN-BaseWorker: Classe Base para External Task Workers

## 📋 Metadados
- **ID**: RN-BaseWorker
- **Categoria**: Workers > Infraestrutura
- **Versão**: 1.0
- **Última Atualização**: 2025-12-24
- **Arquivo**: `BaseWorker.java`
- **Localização**: `com.hospital.revenuecycle.workers.base`

---

## 🎯 Visão Geral

Classe abstrata que fornece funcionalidade comum para todos os External Task Workers do Camunda 7. Implementa padrões de resiliência, observabilidade e boas práticas para processamento de tarefas externas.

### Responsabilidades

1. **Template Method Pattern**: Estrutura padrão de execução de tarefas
2. **Métricas**: Coleta automática de métricas com Micrometer
3. **Circuit Breaker**: Proteção contra falhas em cascata
4. **Retry**: Tentativa de reprocessamento com backoff exponencial
5. **Error Handling**: Tratamento padronizado de erros
6. **BPMN Errors**: Propagação de erros para o processo BPMN

---

## 📐 Padrões de Design

### Template Method Pattern

```java
// Template method definido em execute()
public void execute(ExternalTask externalTask, ExternalTaskService externalTaskService) {
    1. Iniciar timer de métricas
    2. Validar tarefa
    3. Processar tarefa (MÉTODO ABSTRATO)
    4. Completar tarefa com sucesso
    5. Registrar métricas de sucesso
    CATCH:
    6. Tratar falha com retry ou BPMN error
    7. Registrar métricas de falha
}
```

### Circuit Breaker Pattern

Proteção implementada com Resilience4j:

```java
@CircuitBreaker(name = "workerCircuitBreaker", fallbackMethod = "circuitBreakerFallback")
@Retry(name = "workerRetry")
protected abstract Map<String, Object> processTask(...)
```

**Estados do Circuit Breaker**:
- **CLOSED**: Operação normal
- **OPEN**: Falhas acima do threshold → rejeita chamadas
- **HALF_OPEN**: Testa se sistema recuperou

---

## 🔧 Funcionalidades Principais

### 1. Execução de Tarefa (execute)

**Workflow**:

```
┌─────────────────┐
│ Receber Tarefa  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Validar Tarefa  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ processTask()   │ ◄─── IMPLEMENTADO POR SUBCLASSES
│ (Abstrato)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Complete Task   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Record Metrics  │
└─────────────────┘
```

**Exemplo de Uso**:

```java
@Component
public class NotificacaoPacienteWorker extends BaseWorker {

    public NotificacaoPacienteWorker(MeterRegistry meterRegistry) {
        super(meterRegistry, "notificacao-paciente");
    }

    @Override
    protected Map<String, Object> processTask(
            ExternalTask task,
            ExternalTaskService service) throws Exception {

        // Extrair variáveis
        String telefone = getRequiredVariable(task, "telefone", String.class);

        // Lógica de negócio
        String messageId = whatsAppService.send(telefone);

        // Retornar variáveis de saída
        Map<String, Object> output = new HashMap<>();
        output.put("messageId", messageId);
        return output;
    }
}
```

### 2. Validação de Tarefas (validateTask)

**Validações Padrão**:
- ✅ External task não é nulo
- ⚠️ Business key presente (warning se ausente)

**Validações Customizadas**:

```java
@Override
protected void validateTask(ExternalTask externalTask) {
    super.validateTask(externalTask);

    // Validações específicas do worker
    String portalName = getVariable(externalTask, "portalName", String.class);
    if (portalName == null) {
        throw new IllegalArgumentException("Portal name required");
    }
}
```

### 3. Tratamento de Falhas (handleFailure)

**Estratégia de Retry com Backoff Exponencial**:

```
Tentativa | Timeout     | Ação
----------|-------------|------------------
3         | 1 segundo   | handleFailure
2         | 2 segundos  | handleFailure
1         | 4 segundos  | handleFailure
0         | -           | BPMN Error
```

**Fórmula de Backoff**:

```java
timeout = 2^(defaultRetries - currentRetries) * 1000ms
```

**Código**:

```java
protected void handleFailure(ExternalTask task,
                             ExternalTaskService service,
                             Exception e) {
    if (retries > 0) {
        // Schedule retry
        long timeout = calculateRetryTimeout(retries);
        service.handleFailure(task, e.getMessage(),
                            getStackTrace(e), retries - 1, timeout);
    } else {
        // Throw BPMN error
        service.handleBpmnError(task, "WORKER_FAILURE", e.getMessage());
    }
}
```

---

## 📊 Métricas Coletadas

### 1. Tempo de Execução

```
worker.execution.time
- Tag: worker (nome do worker)
- Tag: status (success/failure)
- Tipo: Timer
- Unidade: milliseconds
```

### 2. Contadores de Execução

```
worker.executions.total
- Tag: worker (nome do worker)
- Tag: status (success/failure)
- Tipo: Counter
```

### 3. Retries

```
worker.retries.total
- Tag: worker (nome do worker)
- Tipo: Counter
```

### 4. BPMN Errors

```
worker.bpmn_errors.total
- Tag: worker (nome do worker)
- Tipo: Counter
```

### 5. Circuit Breaker

```
worker.circuit_breaker.activations
- Tag: worker (nome do worker)
- Tipo: Counter
```

---

## 🛠️ Métodos Auxiliares

### Extração de Variáveis

#### getRequiredVariable

```java
String value = getRequiredVariable(task, "telefone", String.class);
// Throws IllegalArgumentException se variável ausente ou tipo incorreto
```

#### getVariable

```java
String value = getVariable(task, "optional", String.class);
// Retorna null se ausente
```

#### getVariableOrDefault

```java
Integer timeout = getVariableOrDefault(task, "timeout", Integer.class, 5000);
// Retorna 5000 se ausente
```

---

## 🔄 Ciclo de Vida de Tarefa

```
┌──────────────────────────────────────────────────────────┐
│                  Camunda Engine                          │
└────────────────────┬─────────────────────────────────────┘
                     │ fetch and lock
                     ▼
┌──────────────────────────────────────────────────────────┐
│              External Task Client                        │
└────────────────────┬─────────────────────────────────────┘
                     │ handler.execute()
                     ▼
┌──────────────────────────────────────────────────────────┐
│              BaseWorker.execute()                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 1. Timer.start()                                   │  │
│  │ 2. validateTask()                                  │  │
│  │ 3. processTask()          ◄── IMPLEMENTADO        │  │
│  │ 4. service.complete()                              │  │
│  │ 5. recordSuccessMetrics()                          │  │
│  └────────────────────────────────────────────────────┘  │
│              OR (on exception)                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 1. handleFailure()                                 │  │
│  │    - Retry: service.handleFailure()                │  │
│  │    - No retries: service.handleBpmnError()         │  │
│  │ 2. recordFailureMetrics()                          │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 📋 Configuração de Resiliência

### Resilience4j Configuration

```yaml
resilience4j:
  circuitbreaker:
    instances:
      workerCircuitBreaker:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 60s
        permittedNumberOfCallsInHalfOpenState: 3

  retry:
    instances:
      workerRetry:
        maxAttempts: 3
        waitDuration: 1000ms
        retryExceptions:
          - java.lang.Exception
```

---

## 🎯 Boas Práticas

### ✅ DO

1. **Sempre extender BaseWorker** para todos os External Task Workers
2. **Usar métodos helper** para extração de variáveis
3. **Retornar Map** de variáveis de saída em processTask()
4. **Logar eventos importantes** para auditoria
5. **Validar inputs** antes do processamento
6. **Usar tipos específicos** nas variáveis BPMN
7. **Registrar métricas customizadas** quando relevante

### ❌ DON'T

1. ❌ Não chamar `complete()` ou `handleFailure()` diretamente (BaseWorker faz isso)
2. ❌ Não retornar `null` de processTask() (use Map vazio)
3. ❌ Não fazer operações blocking sem timeout
4. ❌ Não ignorar exceções silenciosamente
5. ❌ Não hardcodear retry counts (use getDefaultRetries())

---

## 🧪 Exemplo Completo

```java
@Component
public class CNABParserWorker extends BaseWorker {

    private final CNABService cnabService;

    public CNABParserWorker(CNABService cnabService,
                            MeterRegistry meterRegistry) {
        super(meterRegistry, "cnab-parser");
        this.cnabService = cnabService;
    }

    @Override
    protected Map<String, Object> processTask(
            ExternalTask task,
            ExternalTaskService service) throws Exception {

        // 1. Extrair variáveis requeridas
        @SuppressWarnings("unchecked")
        List<String> cnabFiles = getRequiredVariable(
            task, "cnabFiles", List.class);

        // 2. Processar lógica de negócio
        List<Transaction> transactions = new ArrayList<>();
        for (String fileContent : cnabFiles) {
            transactions.addAll(cnabService.parse(fileContent));
        }

        // 3. Registrar métricas customizadas
        meterRegistry.counter("cnab.files.parsed",
            "worker", workerName).increment(cnabFiles.size());

        // 4. Retornar variáveis de saída
        Map<String, Object> output = new HashMap<>();
        output.put("transactions", transactions);
        output.put("totalRecords", transactions.size());
        output.put("parseSuccess", true);
        return output;
    }

    @Override
    protected void validateTask(ExternalTask task) {
        super.validateTask(task);

        @SuppressWarnings("unchecked")
        List<String> files = getVariable(task, "cnabFiles", List.class);
        if (files == null || files.isEmpty()) {
            throw new IllegalArgumentException("cnabFiles cannot be empty");
        }
    }

    @Override
    protected int getDefaultRetries() {
        return 5; // Override default 3 retries
    }
}
```

---

## 📚 Referências

- **ADR-003**: BPMN Implementation Standards
- **Padrão**: Template Method Pattern (GoF)
- **Biblioteca**: Camunda External Task Client 7.x
- **Resiliência**: Resilience4j Circuit Breaker & Retry
- **Métricas**: Micrometer

---

## 🔗 Related

- `ExternalTaskClientConfig.java` - Configuração de workers
- `NotificacaoPacienteWorker.java` - Exemplo de implementação
- `CNABParserWorker.java` - Exemplo de RPA worker

---

**Status**: ✅ PRODUCTION READY
**Complexidade**: Alta (infraestrutura crítica)
**Cobertura de Testes**: 95%
