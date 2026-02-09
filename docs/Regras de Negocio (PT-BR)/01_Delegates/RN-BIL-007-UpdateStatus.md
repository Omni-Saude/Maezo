# RN-BIL-007: Atualização de Status de Conta

**ID Técnico**: `UpdateStatusDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança, SUB_08 - Gestão de Receita
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Gerenciar transições de status de contas médicas ao longo do ciclo de vida de faturamento, registrando histórico completo, acionando notificações e atualizando entidades relacionadas (atendimento, conta do paciente).

### 1.2. Contexto de Negócio
Uma conta médica passa por múltiplos estados desde sua criação até o encerramento final:

**Ciclo de Vida de uma Conta**:
1. **DRAFT**: Conta sendo preparada
2. **VALIDATED**: Pré-validação aprovada
3. **SUBMITTED**: Enviada à operadora
4. **ACCEPTED**: Aceita pela operadora
5. **UNDER_REVIEW**: Em análise
6. **PAID**: Pagamento recebido (terminal)
7. **DENIED**: Negada pela operadora
8. **APPEALED**: Em recurso
9. **REJECTED**: Rejeitada na submissão
10. **CANCELLED**: Cancelada (terminal)

A gestão correta de status é crítica para:
- **Rastreabilidade**: Histórico completo do ciclo de vida
- **Conformidade**: Auditoria de mudanças de status
- **Eficiência**: Automação de fluxos baseados em status
- **Comunicação**: Notificações automáticas a equipes
- **Análise**: Métricas de tempo em cada status

### 1.3. Benefícios Esperados
- **Visibilidade**: Status em tempo real de todas as contas
- **Auditoria**: Histórico completo de mudanças
- **Automação**: Notificações e ações automáticas
- **Controle**: Transições validadas conforme regras
- **Análise**: Métricas de tempo de ciclo por status

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve validar o novo status solicitado, recuperar o status atual da conta, verificar se a transição é permitida, atualizar o registro com novo status, registrar histórico da mudança, enviar notificações apropriadas e atualizar entidades relacionadas.

**Lógica de Execução**:

1. **Validação de Status Válido**
   ```
   status_validos ← {
     "DRAFT", "VALIDATED", "SUBMITTED", "ACCEPTED",
     "REJECTED", "UNDER_REVIEW", "PAID", "DENIED",
     "APPEALED", "CANCELLED"
   }

   SE newStatus NÃO ESTÁ EM status_validos:
     LANÇAR ERRO "INVALID_STATUS" COM lista_validos
   ```

2. **Recuperação de Status Atual**
   ```
   conta ← BUSCAR_CONTA(claimId)

   SE conta É NULO:
     LANÇAR ERRO "CLAIM_NOT_FOUND"

   currentStatus ← conta.status
   ```

3. **Validação de Transição de Status**
   ```
   transicoes_validas ← MAPA_TRANSICOES[currentStatus]

   SE currentStatus = newStatus:
     LOG AVISO "Transição para mesmo status (idempotente)"
     RETORNAR  // Permite atualização idempotente

   SE newStatus NÃO ESTÁ EM transicoes_validas:
     LANÇAR ERRO "INVALID_STATUS_TRANSITION"
   ```

4. **Matriz de Transições Válidas**
   ```
   MAPA_TRANSICOES:
     DRAFT → {VALIDATED, CANCELLED}
     VALIDATED → {SUBMITTED, DRAFT, CANCELLED}
     SUBMITTED → {ACCEPTED, REJECTED, UNDER_REVIEW}
     ACCEPTED → {PAID, UNDER_REVIEW}
     REJECTED → {APPEALED, CANCELLED}
     UNDER_REVIEW → {ACCEPTED, DENIED, PAID}
     DENIED → {APPEALED, CANCELLED}
     APPEALED → {ACCEPTED, DENIED, PAID}
     PAID → {}  // Estado terminal
     CANCELLED → {}  // Estado terminal
   ```

5. **Atualização de Status**
   ```
   update_time ← AGORA()

   ATUALIZAR conta SET
     status = newStatus,
     status_reason = statusReason,
     updated_by = updatedBy,
     updated_at = update_time

   LOG INFO "Status atualizado: " + currentStatus + " → " + newStatus
   ```

6. **Registro de Histórico**
   ```
   historico_entrada ← {
     "claimId": claimId,
     "previousStatus": currentStatus,
     "newStatus": newStatus,
     "reason": statusReason,
     "updatedBy": updatedBy,
     "updateTime": update_time
   }

   INSERIR_EM status_history_table(historico_entrada)
   ```

7. **Envio de Notificações**
   ```
   notificacoes ← []

   SWITCH newStatus:
     CASO "SUBMITTED":
       notificacoes ← ["PAYER_NOTIFICATION", "BILLING_TEAM_NOTIFICATION"]

     CASO "ACCEPTED" OU "PAID":
       notificacoes ← ["BILLING_TEAM_NOTIFICATION", "FINANCE_NOTIFICATION"]

     CASO "REJECTED" OU "DENIED":
       notificacoes ← ["BILLING_TEAM_ALERT", "DENIAL_MANAGEMENT_NOTIFICATION"]

     CASO "APPEALED":
       notificacoes ← ["APPEAL_TEAM_NOTIFICATION", "PAYER_NOTIFICATION"]

   PARA CADA notificacao EM notificacoes:
     ENVIAR_NOTIFICACAO(notificacao, claimId, newStatus)
   ```

8. **Atualização de Entidades Relacionadas**
   ```
   SE newStatus = "PAID":
     SE encounterId NÃO É NULO:
       ATUALIZAR_STATUS_ATENDIMENTO(encounterId, "PAID")

     SE patientId NÃO É NULO:
       ATUALIZAR_CONTA_PACIENTE(patientId, claimId, "PAID")

   SE newStatus EM ["PAID", "DENIED"]:
     SE patientId NÃO É NULO:
       ATUALIZAR_SALDO_PACIENTE(patientId)
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-007-V1 | Status deve estar na lista de valores válidos | CRÍTICA | Rejeitar com INVALID_STATUS |
| BIL-007-V2 | Conta deve existir no sistema | CRÍTICA | Rejeitar com CLAIM_NOT_FOUND |
| BIL-007-V3 | Transição deve ser permitida pela matriz | CRÍTICA | Rejeitar com INVALID_STATUS_TRANSITION |
| BIL-007-V4 | Estados terminais não podem mudar | CRÍTICA | Rejeitar com INVALID_STATUS_TRANSITION |
| BIL-007-V5 | Razão da mudança deve ser informada | AVISO | Usar razão padrão "Status update" |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador de conta (claimId) válido
- Novo status (newStatus) definido
- Razão da mudança (statusReason) opcional
- Usuário responsável (updatedBy) opcional

**Exceções de Negócio**:

1. **Conta Não Encontrada**
   - **Código**: CLAIM_NOT_FOUND
   - **Causa**: claimId inválido ou conta inexistente
   - **Ação**: Rejeitar atualização
   - **Próximo Passo**: Validar ID da conta

2. **Status Inválido**
   - **Código**: INVALID_STATUS
   - **Causa**: newStatus não está na lista de valores válidos
   - **Ação**: Rejeitar atualização
   - **Próximo Passo**: Corrigir valor do status

3. **Transição Inválida**
   - **Código**: INVALID_STATUS_TRANSITION
   - **Causa**: Mudança de status não permitida pela matriz
   - **Ação**: Rejeitar atualização
   - **Próximo Passo**: Revisar fluxo do processo

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador único da conta | Formato: CLM-.*-\d+ |
| `newStatus` | String | Sim | Novo status a ser definido | Deve estar em lista válida |
| `statusReason` | String | Não | Motivo da mudança de status | Default: "Status update" |
| `updatedBy` | String | Não | Usuário ou sistema que atualizou | Default: "SYSTEM" |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `previousStatus` | String | Status anterior da conta | Auditoria e análise |
| `statusUpdateTime` | LocalDateTime | Data/hora da atualização | Métricas de SLA |
| `statusHistory` | Lista<Objeto> | Histórico completo de status | Auditoria |
| `notificationsSent` | Lista<String> | Notificações enviadas | Rastreamento |

**Estrutura de Status History**:
```json
{
  "statusHistory": [
    {
      "previousStatus": "SUBMITTED",
      "newStatus": "ACCEPTED",
      "reason": "Claim accepted by payer",
      "updatedBy": "TISS_INTEGRATION",
      "updateTime": "2025-01-12T10:50:00Z"
    },
    {
      "previousStatus": "ACCEPTED",
      "newStatus": "PAID",
      "reason": "Payment received",
      "updatedBy": "PAYMENT_PROCESSOR",
      "updateTime": "2025-01-14T14:30:00Z"
    }
  ]
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Tempo Médio por Status

```
Entrada:
  status_history = Lista de mudanças de status
  status_alvo = Status para calcular tempo

Cálculo:
  tempo_total = 0
  contagem = 0

  PARA CADA entrada EM status_history:
    SE entrada.newStatus = status_alvo:
      próxima_entrada ← PRÓXIMA(entrada)
      SE próxima_entrada EXISTE:
        tempo = próxima_entrada.updateTime - entrada.updateTime
        tempo_total ← tempo_total + tempo
        contagem ← contagem + 1

  SE contagem > 0:
    tempo_médio = tempo_total / contagem
  SENÃO:
    tempo_médio = 0

Saída:
  tempo_médio (Duration)
```

**Exemplo**:
```
Conta CLM-001:
  SUBMITTED: 2025-01-10 10:00 → ACCEPTED: 2025-01-11 15:00
  Tempo em SUBMITTED = 29 horas

Média de 100 contas em SUBMITTED = 32 horas
```

### 4.2. Taxa de Transição

```
Para análise de fluxo:

Taxa_Transição(Status_A → Status_B) =
  (Contas que foram de A para B / Total de contas em A) × 100

Exemplo:
  Total em SUBMITTED: 1000 contas
  Transições para ACCEPTED: 850
  Transições para REJECTED: 150

  Taxa(SUBMITTED → ACCEPTED) = (850 / 1000) × 100 = 85%
  Taxa(SUBMITTED → REJECTED) = (150 / 1000) × 100 = 15%
```

### 4.3. Tempo Total de Ciclo

```
Tempo_Ciclo_Completo = tempo(PAID ou CANCELLED) - tempo(DRAFT)

Componentes:
  - Tempo em preparação (DRAFT → VALIDATED)
  - Tempo em submissão (SUBMITTED → ACCEPTED)
  - Tempo em processamento (ACCEPTED → PAID)

Exemplo:
  DRAFT: 2025-01-08 09:00
  PAID: 2025-01-14 14:30
  Ciclo Total = 6 dias, 5h30min
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Sistema de Contas | Atualização | Novo status, razão | Database |
| Sistema de Notificações | Envio | Alertas por tipo de status | Message Queue |
| Sistema de Atendimento | Atualização | Status de faturamento | API REST |
| Sistema de Conta do Paciente | Atualização | Saldos e status | API REST |
| Sistema de Auditoria | Escrita | Histórico de mudanças | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Cadastro de contas médicas
- Matriz de transições válidas
- Configuração de notificações por status
- Relacionamento conta-atendimento-paciente

**Frequência de Atualização**:
- Status de contas: Tempo real
- Matriz de transições: Sob demanda (raramente muda)
- Configuração de notificações: Semanal

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Tempo Médio até Pagamento | Tempo de DRAFT a PAID | ≤ 30 dias | Média de ciclos completos | Mensal |
| Taxa de Aceitação | % de contas que vão de SUBMITTED a ACCEPTED | ≥ 90% | (ACCEPTED / SUBMITTED) × 100 | Mensal |
| Taxa de Negação | % de contas que chegam a DENIED | < 5% | (DENIED / Total) × 100 | Mensal |
| Tempo em UNDER_REVIEW | Tempo médio em análise | ≤ 5 dias | Média de tempo no status | Semanal |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Tempo de Processamento | Duração da atualização | > 2 segundos | Otimizar queries |
| Erros INVALID_STATUS_TRANSITION | Transições inválidas tentadas | > 1% | Revisar lógica de fluxo |
| Erros CLAIM_NOT_FOUND | Contas não encontradas | > 0.5% | Validar IDs |
| Taxa de Notificações Enviadas | % de notificações com sucesso | ≥ 99% | Verificar serviço de notificações |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Solicitação de mudança de status
2. Validação de novo status
3. Recuperação de status atual
4. Validação de transição
5. Atualização no banco de dados
6. Registro no histórico
7. Envio de notificações
8. Atualização de entidades relacionadas

**Informações Capturadas**:
```json
{
  "timestamp": "2025-01-12T10:50:00Z",
  "claimId": "CLM-001-1234567890",
  "previousStatus": "SUBMITTED",
  "newStatus": "ACCEPTED",
  "statusReason": "Claim accepted by payer",
  "updatedBy": "TISS_INTEGRATION",
  "statusUpdateTime": "2025-01-12T10:50:00Z",
  "notificationsSent": [
    "BILLING_TEAM_NOTIFICATION",
    "FINANCE_NOTIFICATION"
  ],
  "relatedEntitiesUpdated": ["encounter-001"],
  "executionTimeMs": 187
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Transições | Preventivo | Por transação | Sistema automático |
| Auditoria de Histórico | Detectivo | Semanal | Auditoria Interna |
| Análise de Tempo por Status | Detectivo | Mensal | Gestão de Processos |
| Revisão de Transições Inválidas | Corretivo | Diária | Equipe de TI |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| CLAIM_NOT_FOUND | Conta não existe no sistema | CRÍTICA | Validar ID da conta |
| INVALID_STATUS | Status não está na lista de valores válidos | CRÍTICA | Corrigir valor do status |
| INVALID_STATUS_TRANSITION | Transição não permitida | CRÍTICA | Revisar fluxo do processo |
| UPDATE_FAILED | Erro ao atualizar no banco | CRÍTICA | Retry ou escalar |

### 8.2. Estratégia de Retry

**Erros Transientes (retry automático)**:
- Timeout em atualização de banco
- Erro de conexão
- Deadlock

**Configuração**:
- Máximo de tentativas: 3
- Intervalo entre tentativas: 1s, 2s, 4s
- Timeout por tentativa: 5 segundos

**Erros Permanentes (sem retry)**:
- CLAIM_NOT_FOUND
- INVALID_STATUS
- INVALID_STATUS_TRANSITION

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Transição Bem-Sucedida

**Cenário**: Atualizar conta de SUBMITTED para ACCEPTED

**Pré-condições**:
- Conta CLM-001-123 existe
- Status atual: SUBMITTED
- Novo status: ACCEPTED

**Fluxo**:
1. Sistema recebe newStatus = "ACCEPTED"
2. Valida status: "ACCEPTED" está na lista válida
3. Recupera conta: status atual = "SUBMITTED"
4. Valida transição: SUBMITTED → ACCEPTED (VÁLIDA)
5. Atualiza banco:
   - status = "ACCEPTED"
   - status_reason = "Claim accepted by payer"
   - updated_by = "TISS_INTEGRATION"
   - updated_at = "2025-01-12T10:50:00Z"
6. Insere no histórico
7. Envia notificações:
   - BILLING_TEAM_NOTIFICATION
   - FINANCE_NOTIFICATION
8. Nenhuma entidade relacionada a atualizar
9. Retorna sucesso

**Pós-condições**:
- `previousStatus` = "SUBMITTED"
- `statusUpdateTime` = "2025-01-12T10:50:00Z"
- `notificationsSent` = ["BILLING_TEAM_NOTIFICATION", "FINANCE_NOTIFICATION"]
- Histórico atualizado

**Resultado**: Transição bem-sucedida

### 9.2. Fluxo Alternativo - Atualização Idempotente

**Cenário**: Tentar atualizar para mesmo status

**Fluxo**:
1. Sistema recebe newStatus = "SUBMITTED"
2. Recupera conta: status atual = "SUBMITTED"
3. Detecta que currentStatus = newStatus
4. Log de aviso: "Transição idempotente"
5. Permite atualização (atualiza timestamp)
6. Não envia notificações (status não mudou)
7. Retorna sucesso

**Resultado**: Atualização permitida (idempotência)

### 9.3. Fluxo de Exceção - Transição Inválida

**Cenário**: Tentar mudar de PAID para DRAFT (inválido)

**Fluxo**:
1. Sistema recebe newStatus = "DRAFT"
2. Recupera conta: status atual = "PAID"
3. Valida transição:
   - PAID é estado terminal
   - Transições permitidas: {} (vazio)
4. Transição inválida detectada
5. Lança erro INVALID_STATUS_TRANSITION
6. Registra em auditoria
7. Notifica equipe de TI

**Ações Corretivas**:
- Revisar lógica do processo
- Verificar se há bug no código
- Corrigir fluxo se necessário

**Resultado**: Erro com transição bloqueada

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 395/2016 | Art. 10º | Rastreabilidade de status | Histórico completo de mudanças |
| ANS IN 41/2018 | Art. 6º | Transparência de processamento | Notificações automáticas |
| CFM Res. 1.821/2007 | Art. 3º | Auditoria de processos | Log de todas as transições |
| LGPD Art. 6º | Inciso II | Transparência | Acesso ao histórico de status |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Mudança de status: Sistema automático ou usuário autorizado
- Validação: Sistema automático
- Auditoria: Equipe de compliance

**Retenção de Dados**:
- Histórico de status: 5 anos (ANS)
- Logs de mudanças: 5 anos
- Notificações enviadas: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker pattern |
| Atualizações | Síncronas | Assíncronas com workers | Garantir idempotência |
| Transações | ACID | Eventual consistency | Implementar compensação |
| Matriz de Estados | Em código | Externalizar | Configuração externa |

### 11.2. Estratégia de Migração

**Fase 1 - Worker de Status**:
```java
@JobWorker(
    type = "update-claim-status",
    timeout = 10_000,
    maxJobsActive = 50
)
public StatusUpdateResponse updateStatus(
    @Variable String claimId,
    @Variable String newStatus,
    @Variable String statusReason
) {
    // Validar status
    // Validar transição
    // Atualizar conta
    // Registrar histórico
    // Enviar notificações
    return updateResponse;
}
```

**Fase 2 - Event-Driven**:
```
Emitir Eventos de Mudança:
  - ClaimStatusChangedEvent
  - Consumidores:
    - NotificationService (enviar notificações)
    - AuditService (registrar histórico)
    - RelatedEntitiesService (atualizar relacionados)
```

### 11.3. Oportunidades de Melhoria

**Estado como Stream**:
- Implementar event sourcing para status
- Reconstruir estado a partir de eventos
- Facilitar auditoria temporal

**Máquina de Estados**:
- Implementar state machine formal
- Visualizar transições possíveis
- Validação automática de transições

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing Management (Gestão de Faturamento)

**Sub-domínio**: Core Domain - Status Management

**Responsabilidade**: Gerenciamento de ciclo de vida e transições de status de contas médicas

### 12.2. Agregados e Entidades

**Agregado Raiz**: `ClaimStatusLifecycle`

```
ClaimStatusLifecycle (Aggregate Root)
├── ClaimId (Value Object)
├── CurrentStatus (ClaimStatus Enum)
├── StatusHistory (Collection)
│   └── StatusChange
│       ├── PreviousStatus (ClaimStatus)
│       ├── NewStatus (ClaimStatus)
│       ├── Reason (String)
│       ├── UpdatedBy (UserId)
│       └── UpdatedAt (Instant)
├── NotificationsSent (Collection of Notification)
├── LastUpdated (Instant)
└── Version (Long)
```

**Value Objects**:
- `ClaimStatus`: Enum de status de conta
- `StatusTransition`: Par de status (de → para)

**Enums**:
```java
enum ClaimStatus {
    DRAFT,
    VALIDATED,
    SUBMITTED,
    ACCEPTED,
    REJECTED,
    UNDER_REVIEW,
    PAID,         // Terminal
    DENIED,
    APPEALED,
    CANCELLED     // Terminal
}
```

### 12.3. Domain Events

```
ClaimStatusChangedEvent
├── claimId: ClaimId
├── previousStatus: ClaimStatus
├── newStatus: ClaimStatus
├── reason: String
├── updatedBy: UserId
├── changedAt: Instant
└── version: Long

InvalidStatusTransitionAttemptedEvent
├── claimId: ClaimId
├── attemptedFrom: ClaimStatus
├── attemptedTo: ClaimStatus
├── attemptedBy: UserId
├── attemptedAt: Instant
└── severity: Severity.MEDIUM

TerminalStatusReachedEvent
├── claimId: ClaimId
├── finalStatus: ClaimStatus (PAID ou CANCELLED)
├── totalCycleDuration: Duration
├── reachedAt: Instant
└── version: Long
```

### 12.4. Serviços de Domínio

**StatusTransitionService**:
```
Responsabilidades:
- Validar transições de status
- Aplicar regras de negócio de transição
- Registrar histórico
- Emitir eventos de mudança

Métodos:
- validateTransition(from, to): ValidationResult
- applyTransition(claim, newStatus, reason): StatusChange
- getValidTransitions(currentStatus): Set<ClaimStatus>
- canTransitionTo(from, to): Boolean
```

### 12.5. Repositories

```
ClaimStatusRepository
├── findByClaimId(claimId): ClaimStatusLifecycle
├── save(lifecycle): ClaimStatusLifecycle
└── findByStatus(status): List<ClaimStatusLifecycle>

StatusHistoryRepository
├── findHistoryByClaimId(claimId): List<StatusChange>
├── saveStatusChange(change): StatusChange
└── findRecentChanges(limit): List<StatusChange>
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Status da Conta | Claim Status | Estado atual no ciclo de vida |
| Transição | Status Transition | Mudança de um status para outro |
| Estado Terminal | Terminal State | Status final (PAID, CANCELLED) |
| Histórico | Status History | Sequência de mudanças de status |
| Ciclo de Vida | Lifecycle | Jornada completa de DRAFT a terminal |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `UpdateStatusDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `updateStatus` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | State Pattern, Observer |
| **Complexidade Ciclomática** | 12 (Alta) |
| **Linhas de Código** | 294 |
| **Cobertura de Testes** | 93% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x

**Serviços Integrados** (futuro):
- ClaimRepository
- StatusHistoryRepository
- NotificationService
- EncounterService
- PatientAccountService

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 10s | Múltiplas atualizações |
| Pool de Threads | 30 | Alto volume de mudanças |
| Cache TTL (Status) | 5 minutos | Evitar reads desnecessários |
| Batch Size (Notificações) | 50 | Envio eficiente |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "claim_status_changed",
  "claimId": "CLM-001-1234567890",
  "previousStatus": "SUBMITTED",
  "newStatus": "ACCEPTED",
  "statusReason": "Claim accepted by payer",
  "updatedBy": "TISS_INTEGRATION",
  "statusUpdateTime": "2025-01-12T10:50:00Z",
  "notificationsSent": 2,
  "relatedEntitiesUpdated": 1,
  "executionTimeMs": 187,
  "timestamp": "2025-01-12T10:50:00Z"
}
```

**Métricas Prometheus**:
- `status_update_duration_seconds` (Histogram)
- `status_updates_total` (Counter por status)
- `status_transition_total` (Counter por transição)
- `invalid_transitions_total` (Counter)
- `notification_delivery_total` (Counter por tipo)
- `time_in_status_seconds` (Histogram por status)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Transição válida bem-sucedida
2. ✅ Transição inválida bloqueada
3. ✅ Atualização idempotente permitida
4. ✅ Estado terminal não pode mudar
5. ✅ Conta não encontrada
6. ✅ Status inválido rejeitado
7. ✅ Histórico registrado corretamente
8. ✅ Notificações enviadas por status
9. ✅ Entidades relacionadas atualizadas
10. ✅ Performance com múltiplas atualizações

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
