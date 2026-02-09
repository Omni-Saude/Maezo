# RN-CheckIdempotencyDelegate - Verificação de Idempotência

## Identificação
- **ID**: RN-INFRA-001
- **Nome**: CheckIdempotencyDelegate
- **Categoria**: Infrastructure/Idempotency
- **Versão**: 1.0.0
- **Bean BPMN**: `checkIdempotencyDelegate`
- **Autor**: Hospital Revenue Cycle Team

## Visão Geral
Delegate responsável por verificar idempotência no início do processo orquestrador, prevenindo execução duplicada de processos baseada no `atendimentoId`.

## Responsabilidades

### 1. Verificação de Duplicidade
- Verifica se processo já foi executado anteriormente
- Baseia-se no `atendimentoId` como chave de idempotência
- Consulta serviço de idempotência para histórico
- Marca processo como duplicado ou novo

### 2. Geração de Chave de Idempotência
- Gera chave única baseada em:
  - `processInstanceId`
  - `activityId`
  - Operação ("check_duplicate")
  - `atendimentoId`

### 3. Prevenção de Reprocessamento
- Se duplicado: Define `is_duplicate = true`
- Habilita gateway BPMN para desviar processo duplicado
- Evita reexecução de operações críticas

### 4. Fail-Open em Caso de Erro
- Se verificação falhar: Permite prosseguir (fail-open)
- Registra erro mas não bloqueia processo
- Prioriza disponibilidade sobre consistência absoluta

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `atendimentoId` | String | Sim | Identificador único do atendimento |

**Nota**: Também usa `processInstanceId`, `businessKey` e `activityId` do contexto de execução.

## Variáveis de Saída

| Variável | Tipo | Escopo | Descrição |
|----------|------|--------|-----------|
| `is_duplicate` | Boolean | PROCESS | `true` se processo é duplicado |
| `idempotency_key` | String | PROCESS | Chave de idempotência gerada |
| `duplicate_detection_time` | String | PROCESS | Timestamp da detecção (ISO-8601) |
| `idempotency_check_error` | String | PROCESS | Mensagem de erro (se houver) |

**IMPORTANT**: Todas as variáveis usam escopo PROCESS para serem acessíveis por gateways do processo orquestrador.

## Algoritmo

```
1. Obter contexto de execução:
   - processInstanceId = execution.getProcessInstanceId()
   - businessKey = execution.getBusinessKey()
   - atendimentoId = execution.getVariable("atendimentoId")

2. Validar atendimentoId:
   - if (atendimentoId == null || atendimentoId.trim().isEmpty())
     → throw IllegalArgumentException("atendimentoId é obrigatório")

3. Gerar chave de idempotência:
   - activityId = execution.getCurrentActivityId()
   - idempotencyKey = idempotencyService.generateIdempotencyKey(
       processInstanceId,
       activityId,
       "check_duplicate",
       atendimentoId
     )

4. Verificar se foi executado anteriormente:
   - isDuplicate = idempotencyService.wasExecuted(idempotencyKey)

5. Se duplicado:
   - execution.setVariable("is_duplicate", true)
   - execution.setVariable("idempotency_key", idempotencyKey)
   - execution.setVariable("duplicate_detection_time", Instant.now().toString())
   - log.warn("Processo duplicado detectado")

6. Se novo:
   - execution.setVariable("is_duplicate", false)
   - execution.setVariable("idempotency_key", idempotencyKey)
   - log.info("Processo novo")

7. Em caso de erro (fail-open):
   - execution.setVariable("is_duplicate", false)
   - execution.setVariable("idempotency_check_error", e.getMessage())
   - log.error("Erro na verificação - permitindo prosseguir")
```

## Geração de Chave de Idempotência

### Formato da Chave
```
idempotency_key = SHA-256(
    processInstanceId + ":" +
    activityId + ":" +
    operation + ":" +
    atendimentoId
)

Exemplo:
processInstanceId: "proc-123-abc"
activityId: "Activity_CheckIdempotency"
operation: "check_duplicate"
atendimentoId: "ATD-2025-001"

→ idempotency_key = SHA-256("proc-123-abc:Activity_CheckIdempotency:check_duplicate:ATD-2025-001")
→ "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

## Casos de Uso

### Caso 1: Processo Novo (Primeira Execução)
**Entrada**:
```json
{
  "atendimentoId": "ATD-2025-001"
}
```

**Contexto**:
```
processInstanceId: "proc-123"
businessKey: "ATD-2025-001"
activityId: "Activity_CheckIdempotency"
```

**Saída**:
```json
{
  "is_duplicate": false,
  "idempotency_key": "e3b0c442...52b855"
}
```

**Log**:
```
INFO: Processo novo - AtendimentoId: ATD-2025-001
```

**Fluxo BPMN**: Prossegue normalmente com execução completa.

### Caso 2: Processo Duplicado
**Entrada**:
```json
{
  "atendimentoId": "ATD-2025-001"
}
```

**Contexto**: Mesmo `atendimentoId` já foi processado anteriormente.

**Saída**:
```json
{
  "is_duplicate": true,
  "idempotency_key": "e3b0c442...52b855",
  "duplicate_detection_time": "2025-01-12T10:30:00Z"
}
```

**Log**:
```
WARN: Processo duplicado detectado - AtendimentoId: ATD-2025-001, IdempotencyKey: e3b0c442...52b855
```

**Fluxo BPMN**: Gateway desvia para caminho de "processo duplicado" (ex: retornar resultado anterior).

### Caso 3: Erro na Verificação (Fail-Open)
**Entrada**:
```json
{
  "atendimentoId": "ATD-2025-002"
}
```

**Erro**: Serviço de idempotência indisponível.

**Saída**:
```json
{
  "is_duplicate": false,
  "idempotency_check_error": "Timeout connecting to idempotency service"
}
```

**Log**:
```
ERROR: Erro inesperado ao verificar idempotência: Timeout connecting to idempotency service
INFO: Permitindo prosseguir (fail-open)
```

**Fluxo BPMN**: Prossegue como se fosse novo processo (fail-open strategy).

## Regras de Negócio

### RN-INFRA-001-001: AtendimentoId Obrigatório
- **Descrição**: atendimentoId é obrigatório para verificação
- **Prioridade**: CRÍTICA
- **Validação**: `atendimentoId != null && !atendimentoId.trim().isEmpty()`
- **Erro**: `IllegalArgumentException`

### RN-INFRA-001-002: Escopo de Variáveis
- **Descrição**: Variáveis devem usar escopo PROCESS
- **Prioridade**: CRÍTICA
- **Razão**: Gateway orquestrador precisa acessar `is_duplicate`

### RN-INFRA-001-003: Fail-Open Strategy
- **Descrição**: Em caso de erro, permitir prosseguir
- **Prioridade**: ALTA
- **Razão**: Disponibilidade > Consistência absoluta
- **Implementação**: `is_duplicate = false` em catch block

### RN-INFRA-001-004: Chave de Idempotência Única
- **Descrição**: Chave deve ser determinística e única
- **Prioridade**: CRÍTICA
- **Algoritmo**: SHA-256 de componentes concatenados

## Integração com IdempotencyService

### Geração de Chave
```java
String idempotencyKey =
    idempotencyService.generateIdempotencyKey(
        processInstanceId,
        activityId,
        operation,
        atendimentoId
    );
```

### Verificação de Execução
```java
boolean isDuplicate =
    idempotencyService.wasExecuted(idempotencyKey);
```

### Registro de Execução
```java
// Executado por BaseDelegate após execução bem-sucedida
idempotencyService.recordExecution(idempotencyKey);
```

## Gateway BPMN de Roteamento

### Configuração do Gateway
```xml
<bpmn:exclusiveGateway id="Gateway_CheckDuplicate">
  <bpmn:incoming>Flow_FromIdempotencyCheck</bpmn:incoming>
  <bpmn:outgoing>Flow_Duplicate</bpmn:outgoing>
  <bpmn:outgoing>Flow_NewProcess</bpmn:outgoing>
</bpmn:exclusiveGateway>

<bpmn:sequenceFlow id="Flow_Duplicate"
                   sourceRef="Gateway_CheckDuplicate"
                   targetRef="Task_ReturnCachedResult">
  <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">
    ${is_duplicate == true}
  </bpmn:conditionExpression>
</bpmn:sequenceFlow>

<bpmn:sequenceFlow id="Flow_NewProcess"
                   sourceRef="Gateway_CheckDuplicate"
                   targetRef="Task_ProcessNormally">
  <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">
    ${is_duplicate == false}
  </bpmn:conditionExpression>
</bpmn:sequenceFlow>
```

## Estratégia Fail-Open vs Fail-Closed

### Fail-Open (Implementação Atual)
- **Comportamento**: Em caso de erro, permitir prosseguir
- **Vantagem**: Maior disponibilidade
- **Desvantagem**: Risco de reprocessamento em falhas
- **Uso**: Recomendado para processos não-críticos

### Fail-Closed (Alternativa)
- **Comportamento**: Em caso de erro, bloquear execução
- **Vantagem**: Maior consistência
- **Desvantagem**: Menor disponibilidade
- **Uso**: Recomendado para processos financeiros críticos

## Armazenamento de Idempotência

### Tabela idempotency_records
```sql
CREATE TABLE idempotency_records (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    process_instance_id VARCHAR(255) NOT NULL,
    atendimento_id VARCHAR(255) NOT NULL,
    executed_at TIMESTAMP NOT NULL,
    ttl_expires_at TIMESTAMP,
    INDEX idx_atendimento_id (atendimento_id),
    INDEX idx_executed_at (executed_at)
);
```

### TTL (Time-To-Live)
- **Padrão**: 90 dias
- **Configurável**: Via application.properties
- **Cleanup**: Job automático remove registros expirados

## Métricas

### Indicadores
- **Taxa de Duplicação**: `(processos duplicados / total) * 100%`
- **Taxa de Erro de Verificação**: `(erros / total) * 100%`
- **Latência de Verificação**: `AVG(verificacao_duration_ms)`

### Alertas
- Taxa de Duplicação > 5%: Investigar origem de duplicatas
- Taxa de Erro > 1%: Verificar saúde do serviço de idempotência
- Latência > 100ms: Otimizar consultas ou adicionar cache

## Dependências
- **IdempotencyService**: Serviço de gerenciamento de idempotência
- **Database**: Armazenamento persistente de registros

## Versionamento
- **v1.0.0**: Implementação inicial com fail-open strategy

## Referências
- BaseDelegate: Documentação do delegate base com suporte a idempotência
- Idempotency Patterns: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- Camunda Best Practices: https://docs.camunda.org/manual/latest/user-guide/process-engine/transactions-in-processes/
