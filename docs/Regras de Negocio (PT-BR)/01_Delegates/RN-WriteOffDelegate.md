# Regras de Negócio - WriteOffDelegate

**Arquivo:** `WriteOffDelegate.java`
**Domínio:** Collection (Cobrança)
**Processo BPMN:** Write-Off Management
**Versão:** 2.0.0
**Data:** Análise de Código

---

## Visão Geral

Delegate responsável por processar baixas contábeis (write-offs) de valores incobráveis com fluxo de aprovação escalonado e atualização de contas contábeis.

---

## Regras de Negócio Identificadas

### RN-WRO-001: Validação de Valor Positivo
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Valor de write-off deve ser maior que zero.
**Implementação:**
```java
// Linha 58-62
if (writeOffAmount == null || writeOffAmount.compareTo(BigDecimal.ZERO) <= 0) {
    log.warn("Invalid write-off amount: {}", writeOffAmount);
    execution.setVariable("writeOffApproved", false);
    return;
}
```
**Entrada:** `writeOffAmount` (BigDecimal)
**Saída:** `writeOffApproved` = false se inválido
**Impacto:** Processo não continua

---

### RN-WRO-002: Geração de ID Único
**Prioridade:** MÉDIA
**Tipo:** Processamento
**Descrição:** ID de write-off deve seguir formato WO-{UUID-8-chars}.
**Implementação:**
```java
// Linha 68
String writeOffId = "WO-" + UUID.randomUUID().toString().substring(0, 8);
```
**Saída:** `writeOffId` (String)
**Formato:** "WO-12ab34cd"

---

### RN-WRO-003: Auto-Aprovação para Valores Baixos
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Write-offs até R$ 100,00 são aprovados automaticamente.
**Implementação:**
```java
// Linha 39 (constante)
private static final BigDecimal AUTO_APPROVE_THRESHOLD = new BigDecimal("100.0");

// Linha 105-106
if (amount.compareTo(AUTO_APPROVE_THRESHOLD) <= 0) {
    return "auto";
```
**Entrada:** `writeOffAmount` <= R$ 100,00
**Saída:**
- `approvalLevel` = "auto"
- `requiresApproval` = false
- `writeOffApproved` = true

---

### RN-WRO-004: Aprovação de Gerente para Valores Médios
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Write-offs entre R$ 100,01 e R$ 1.000,00 requerem aprovação de gerente.
**Implementação:**
```java
// Linha 40 (constante)
private static final BigDecimal MANAGER_APPROVE_THRESHOLD = new BigDecimal("1000.0");

// Linha 107-108
} else if (amount.compareTo(MANAGER_APPROVE_THRESHOLD) <= 0) {
    return "manager";
```
**Entrada:** R$ 100,01 <= `writeOffAmount` <= R$ 1.000,00
**Saída:**
- `approvalLevel` = "manager"
- `requiresApproval` = true
- `writeOffApproved` = false (aguardando aprovação)

---

### RN-WRO-005: Aprovação de Diretor para Valores Altos
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Write-offs acima de R$ 1.000,00 requerem aprovação de diretor.
**Implementação:**
```java
// Linha 109-110
} else {
    return "director";
```
**Entrada:** `writeOffAmount` > R$ 1.000,00
**Saída:**
- `approvalLevel` = "director"
- `requiresApproval` = true
- `writeOffApproved` = false (aguardando aprovação)

---

### RN-WRO-006: Criação de Solicitação de Aprovação
**Prioridade:** MÉDIA
**Tipo:** Processamento
**Descrição:** Para write-offs que requerem aprovação, criar registro de solicitação.
**Implementação:**
```java
// Linha 117-136
private void createApprovalRequest(DelegateExecution execution,
                                  String writeOffId,
                                  BigDecimal writeOffAmount,
                                  String approvalLevel,
                                  String writeOffReason) {
    Map<String, Object> approvalRequest = new HashMap<>();
    approvalRequest.put("writeOffId", writeOffId);
    approvalRequest.put("writeOffAmount", writeOffAmount);
    approvalRequest.put("approvalLevel", approvalLevel);
    approvalRequest.put("writeOffReason", writeOffReason);
    approvalRequest.put("requestedAt", LocalDateTime.now().toString());
    approvalRequest.put("requestedBy", "write_off_system");
    approvalRequest.put("status", "pending");

    ObjectValue approvalRequestValue = Variables.objectValue(approvalRequest)
        .serializationDataFormat(Variables.SerializationDataFormats.JSON)
        .create();
    execution.setVariable("writeOffApprovalRequest", approvalRequestValue);
}
```
**Saída:** `writeOffApprovalRequest` (ObjectValue JSON)

---

### RN-WRO-007: Lançamento Contábil - Débito em Despesa
**Prioridade:** ALTA
**Tipo:** Contabilidade
**Descrição:** Write-off aprovado deve debitar conta 6100 (Bad Debt Expense).
**Implementação:**
```java
// Linha 44 (constante)
private static final String GL_BAD_DEBT_EXPENSE = "6100"; // Bad Debt Expense

// Linha 178-190 (comentário)
// Debit:  Bad Debt Expense (6100)     $amount
// Credit: Accounts Receivable (1200)  $amount
//
// SQL example:
// INSERT INTO gl_journal_entries (entry_id, entry_date, description, created_by)
// VALUES (?, NOW(), ?, ?)
//
// INSERT INTO gl_journal_lines (entry_id, account_number, debit, credit, description)
// VALUES
//   (?, '6100', ?, 0, 'Bad debt write-off'),
//   (?, '1200', 0, ?, 'Accounts receivable reduction')
```
**Conta:** 6100 - Bad Debt Expense (Despesa com Dívidas Incobráveis)
**Tipo:** Débito
**Valor:** `writeOffAmount`

---

### RN-WRO-008: Lançamento Contábil - Crédito em Contas a Receber
**Prioridade:** ALTA
**Tipo:** Contabilidade
**Descrição:** Write-off aprovado deve creditar conta 1200 (Accounts Receivable).
**Implementação:**
```java
// Linha 45 (constante)
private static final String GL_ACCOUNTS_RECEIVABLE = "1200"; // Accounts Receivable

// (ver SQL na RN-WRO-007)
```
**Conta:** 1200 - Accounts Receivable (Contas a Receber)
**Tipo:** Crédito
**Valor:** `writeOffAmount`

---

## Limiares de Aprovação

| Nível | Valor Mínimo | Valor Máximo | Aprovador | Auto-Aprovação |
|-------|-------------|--------------|-----------|----------------|
| Auto | R$ 0,01 | R$ 100,00 | Sistema | Sim |
| Gerente | R$ 100,01 | R$ 1.000,00 | Manager | Não |
| Diretor | R$ 1.000,01 | Ilimitado | Director | Não |

---

## Contas Contábeis (GL Accounts)

| Código | Nome | Tipo | Uso |
|--------|------|------|-----|
| 6100 | Bad Debt Expense | Despesa | Débito no write-off |
| 1200 | Accounts Receivable | Ativo | Crédito no write-off |

---

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `writeOffAmount` | BigDecimal | Sim | Valor a dar baixa |
| `invoiceId` | String | Não | ID da fatura relacionada |
| `patientId` | String | Não | ID do paciente |
| `writeOffReason` | String | Não (default: "uncollectable") | Motivo da baixa |

---

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `writeOffApproved` | Boolean | Se write-off foi aprovado |
| `writeOffId` | String | ID único do write-off |
| `requiresApproval` | Boolean | Se necessita aprovação manual |
| `glAccountUpdated` | Boolean | Se conta contábil foi atualizada |
| `approvalLevel` | String | Nível de aprovação: auto, manager, director |
| `writeOffApprovalRequest` | ObjectValue | Solicitação de aprovação (se aplicável) |
| `writeOffRecord` | ObjectValue | Registro completo do write-off |

---

## Fluxo de Decisão

```
writeOffAmount <= R$ 100,00
    → Auto-aprovado
    → Processar write-off imediatamente
    → Atualizar GL

writeOffAmount R$ 100,01 - R$ 1.000,00
    → Criar solicitação para gerente
    → Aguardar aprovação
    → [Após aprovação] Processar write-off
    → Atualizar GL

writeOffAmount > R$ 1.000,00
    → Criar solicitação para diretor
    → Aguardar aprovação
    → [Após aprovação] Processar write-off
    → Atualizar GL
```

---

## Motivos de Write-Off (Exemplos)

- `uncollectable` - Valor incobrável (padrão)
- `deceased` - Paciente falecido
- `bankruptcy` - Falência
- `statute_of_limitations` - Prescrição
- `small_balance` - Saldo pequeno (custo > benefício)

---

## Dependências

- **ADR:** ADR-003 BPMN Implementation Standards
- **Processo:** Write-Off Management Process

---

## Notas de Implementação

1. **GL Integration:** Implementação atual registra logs. Em produção, deve inserir registros em `gl_journal_entries` e `gl_journal_lines`.
2. **Approval Workflow:** Solicitações de aprovação devem disparar tarefas de usuário (user tasks) no BPMN.
3. **Audit Trail:** Todos os write-offs devem ser auditáveis com histórico de quem aprovou e quando.
4. **Idempotência:** Implementação deve prevenir write-offs duplicados para mesma fatura.

---

## Conformidade Regulatória

### Normativas Aplicáveis

| Norma | Artigo/Seção | Descrição | Impacto nas Regras |
|-------|--------------|-----------|-------------------|
| **Lei 11.638/2007** | Art. 3º | Práticas contábeis brasileiras | RN-WRO-007, RN-WRO-008 (lançamentos contábeis de bad debt) |
| **CPC 12** | Seção 4.2 | Ajuste a valor recuperável de ativos | RN-WRO-003 a RN-WRO-005 (aprovação escalonada por valor) |
| **Resolução CFC 1.282/2010** | Art. 5º | Princípios de prudência e competência | RN-WRO-006 (registro de solicitação de aprovação) |
| **SOX (Lei Sarbanes-Oxley)** | Seção 302 | Controles internos financeiros | RN-WRO-004, RN-WRO-005 (aprovação de gerente/diretor obrigatória) |

### Mapeamento de Conformidade

**RN-WRO-003 a RN-WRO-005**: Níveis de aprovação escalonados implementam segregação de funções conforme SOX. Auto-aprovação até R$ 100 permite eficiência operacional, enquanto valores ≥ R$ 1.000 requerem aprovação de diretoria para mitigar risco financeiro.

**RN-WRO-007, RN-WRO-008**: Lançamentos contábeis duplos (débito/crédito) seguem método de partidas dobradas conforme Lei 11.638/2007 e CPC 12 para ajuste de ativos de difícil recuperação.

### Requisitos de Auditoria

- **Trilha de Aprovação**: Registro obrigatório de aprovador, data/hora e justificativa para todos os write-offs
- **Segregação de Funções**: Quem solicita não pode aprovar (implementar em user tasks)
- **Retenção**: Documentos de write-off devem ser mantidos por 7 anos (prazo legal fiscal)

---

## Notas para Migração

### Considerações Tecnológicas

**Do Camunda 7 (Java Delegates) para Camunda 8 (Workers)**:

1. **Workflow de Aprovação**:
   - Camunda 7: Criar `writeOffApprovalRequest` e disparar user task via message
   - Camunda 8: Usar job variables para criar task assignment baseado em `approvalLevel`
   - Considerar Camunda Forms para interface de aprovação

2. **Integração GL (General Ledger)**:
   - Atualmente mockado (logs apenas)
   - Em produção: Integrar com ERP via REST API ou mensageria
   - Camunda 8: Usar outbound connector para ERP (SAP, TOTVS, etc.)

3. **Idempotência**:
   - **CRÍTICO**: Write-off duplicado gera inconsistência contábil severa
   - Camunda 8: Usar deduplication ID baseado em `invoiceId + writeOffReason`
   - Implementar check no worker: verificar se write-off já existe para invoice

4. **Tratamento de Erros**:
   - Camunda 7: BpmnError para valores inválidos
   - Camunda 8: Usar incident handling com retries para falhas de integração GL

### Mudanças Funcionais Necessárias

**Recomendadas**:
- Adicionar motivo obrigatório para write-offs > R$ 100 (compliance)
- Implementar notificação por e-mail ao aprovador quando solicitude é criada
- Dashboard de write-offs pendentes para gestores

### Esforço Estimado

- **Complexidade**: ALTA (integração GL + workflow aprovação)
- **Tempo**: 8-10 dias (incluindo integração ERP e testes contábeis)
- **Dependências**: API do ERP, user management, notificações

---

## Mapeamento de Domínio

### Conceitos de Negócio

| Conceito | Descrição | Regras Relacionadas |
|----------|-----------|-------------------|
| **Write-Off** | Baixa contábil de valores incobráveis | RN-WRO-001 a RN-WRO-003 |
| **Bad Debt** | Dívida classificada como incobrável | RN-WRO-007 (débito em conta de despesa) |
| **Aprovação Escalonada** | Níveis hierárquicos de aprovação por valor | RN-WRO-003 a RN-WRO-005 |
| **Lançamento Contábil** | Registro duplo em GL (débito/crédito) | RN-WRO-007, RN-WRO-008 |

### Entidades do Modelo de Domínio

```yaml
WriteOff:
  atributos:
    - writeOffId: String (formato WO-{UUID-8})
    - writeOffAmount: BigDecimal (> 0)
    - invoiceId: String
    - patientId: String
    - writeOffReason: Enum [uncollectable, deceased, bankruptcy, statute_of_limitations, small_balance]
    - approvalLevel: Enum [auto, manager, director]
    - requiresApproval: Boolean
    - approvedBy: String (nullable)
    - approvedAt: DateTime (nullable)
  validacoes:
    - RN-WRO-001 (valor > 0)
    - RN-WRO-003 a RN-WRO-005 (nível de aprovação por valor)

GLJournalEntry:
  atributos:
    - entryId: String
    - entryDate: Date
    - description: String
    - createdBy: String
    - lines: List<GLJournalLine>
  linhas_write_off:
    - Linha 1: Débito 6100 (Bad Debt Expense) = writeOffAmount
    - Linha 2: Crédito 1200 (Accounts Receivable) = writeOffAmount
  validacoes:
    - RN-WRO-007 (débito em despesa)
    - RN-WRO-008 (crédito em contas a receber)
```

### Invariantes de Domínio

1. **Valor positivo obrigatório**: Write-off com valor ≤ 0 é rejeitado (RN-WRO-001)
2. **Lançamento contábil balanceado**: Soma de débitos = Soma de créditos (princípio contábil)
3. **Aprovação por autoridade competente**: Valores acima de threshold requerem aprovação de nível hierárquico adequado
4. **Unicidade por fatura**: Não permitir múltiplos write-offs para mesma fatura sem estorno prévio

---

## Metadados Estendidos

### Análise de Complexidade

- **Complexidade Ciclomática**: 6 (3 níveis de aprovação, validações, lançamentos GL)
- **Acoplamento**: MÉDIO (depende de GL system, approval workflow, audit trail)
- **Coesão**: ALTA (todas as regras relacionadas a write-off e aprovação)
- **Manutenibilidade**: 80/100 (bem estruturado, mas requer integração GL real)

### Recomendações de Cobertura de Testes

```yaml
cobertura_minima_recomendada: 95%

cenarios_criticos:
  - valor_nulo_ou_zero: RN-WRO-001
  - auto_aprovacao_100: RN-WRO-003 (valor = R$ 100,00)
  - auto_aprovacao_100_01: RN-WRO-003 (valor = R$ 100,01 requer manager)
  - aprovacao_manager_1000: RN-WRO-004 (valor = R$ 1.000,00)
  - aprovacao_diretor_1000_01: RN-WRO-005 (valor = R$ 1.000,01)
  - gl_entry_balanceado: RN-WRO-007, RN-WRO-008 (débito = crédito)

cenarios_edge_case:
  - write_off_duplicado: Validar idempotência
  - invoice_inexistente: Validar referential integrity
  - aprovacao_pendente_timeout: Testar escalação após X dias

cenarios_integracao:
  - gl_system_indisponivel: Testar retry logic
  - gl_api_erro_400: Validar tratamento de erro
  - aprovacao_workflow_concorrente: Testar race conditions
```

### Impacto de Performance

| Aspecto | Avaliação | Observações |
|---------|-----------|-------------|
| **Latência** | BAIXA (< 300ms) | Depende de latência do GL system (50-200ms) |
| **Throughput** | MÉDIO | Limitado por API do ERP (tipicamente 50-100 TPS) |
| **I/O** | MÉDIO | Insert em GL + audit log |
| **Memória** | BAIXA | Processamento de poucos campos |

**Gargalos Potenciais**:
- Integração síncrona com GL system pode adicionar 100-300ms
- Volume alto de auto-aprovações (< R$ 100) pode sobrecarregar GL

**Otimizações Recomendadas**:
- Batch de write-offs auto-aprovados (processar múltiplos em lote)
- Integração assíncrona com GL via mensageria (Kafka/RabbitMQ)
- Circuit breaker para falhas do GL system

---

## X. Conformidade Regulatória

```yaml
regulatory_compliance:
  tiss_standards:
    - "TISS 4.01 - Não aplicável diretamente (write-off é processo interno contábil)"
  ans_requirements:
    - "RN 395/2016 - Registro de valores não recebidos para fins de auditoria"
    - "RN 442/2018 - Provisionamento de perdas em contas a receber"
  lgpd_considerations:
    - "Art. 11 - Dados de pacientes em registros de write-off devem ter finalidade de gestão financeira"
    - "Art. 46 - Manter rastreabilidade de quem aprovou write-offs com dados pessoais"
  sox_compliance:
    - "Seção 302 - Controles internos sobre write-offs com segregação de funções"
    - "Seção 404 - Aprovação escalonada por valor implementa controles adequados"
  contabilidade_brasileira:
    - "Lei 11.638/2007 Art. 3º - Lançamentos contábeis de bad debt expense"
    - "CPC 12 - Ajuste a valor recuperável de ativos financeiros"
    - "Resolução CFC 1.282/2010 Art. 5º - Princípios de prudência e competência"
  audit_trail:
    - "Retention: 7 anos (prazo legal fiscal brasileiro)"
    - "Logging: writeOffId, approvalLevel, approvedBy, glAccountUpdated, timestamp"
    - "Segregação: Solicitante ≠ Aprovador (implementar em user tasks)"
```

---

## XI. Notas de Migração

```yaml
migration_notes:
  complexity: "ALTA"
  estimated_effort: "8-10 dias"
  camunda_8_changes:
    - "Workflow de Aprovação: Substituir message-based approval por Camunda Forms e task assignment"
    - "Integração GL: Implementar outbound connector para ERP (SAP, TOTVS, Oracle Financials)"
    - "Idempotência: Usar deduplication ID baseado em invoiceId + writeOffReason"
    - "Error Handling: BpmnError → Zeebe incident handling com retry policies configuráveis"
  breaking_changes:
    - "JavaDelegate → Job Worker assíncrono com timeout 60s"
    - "writeOffApprovalRequest ObjectValue → JSON payload simples"
    - "GL integration mockada → API real do ERP com circuit breaker"
    - "Transações ACID → Eventual consistency com compensações"
  migration_strategy:
    phases:
      - "Pré-Migração: Implementar API do ERP e validar lançamentos GL em staging"
      - "Migração: Converter delegate para worker, testar workflow de aprovação"
      - "Validação: Comparar lançamentos GL entre Camunda 7 e 8 por 1 semana"
  critical_dependencies:
    - "ERP API para lançamentos contábeis (GL journal entries)"
    - "User management system para aprovadores (manager, director)"
    - "Email/SMS notification service para aprovações pendentes"
  dmn_candidate: "Não"
  dmn_rationale: "Limiares de aprovação são configurações fixas, não regras de negócio complexas"
```

---

## XII. Mapeamento DDD

```yaml
domain_mapping:
  bounded_context: "Collection & Accounts Receivable"
  aggregate_root: "WriteOff"
  aggregates:
    - identity: "WriteOff"
      properties:
        - "writeOffId (WO-{UUID-8})"
        - "writeOffAmount (BigDecimal)"
        - "invoiceId"
        - "patientId"
        - "writeOffReason (Enum)"
        - "approvalLevel (auto|manager|director)"
        - "approvedBy"
        - "approvedAt"
      behaviors:
        - "validate() - RN-WRO-001"
        - "determineApprovalLevel() - RN-WRO-003 a RN-WRO-005"
        - "requiresApproval() - baseado em valor"
        - "approve(approver) - registra aprovador e timestamp"
    - identity: "GLJournalEntry"
      properties:
        - "entryId"
        - "entryDate"
        - "lines (débito 6100, crédito 1200)"
      behaviors:
        - "validate() - soma débitos = soma créditos"
        - "post() - inserir em GL system"
  domain_events:
    - name: "WriteOffRequested"
      payload: ["writeOffId", "amount", "invoiceId", "reason", "requestedBy"]
    - name: "WriteOffApproved"
      payload: ["writeOffId", "approvedBy", "approvedAt", "approvalLevel"]
    - name: "WriteOffRejected"
      payload: ["writeOffId", "rejectedBy", "rejectionReason"]
    - name: "GLEntryPosted"
      payload: ["entryId", "writeOffId", "debitAccount", "creditAccount", "amount"]
  microservice_candidate:
    viable: true
    service_name: "write-off-service"
    bounded_context: "Collection Management"
    api_style: "Event-Driven + REST"
    upstream_dependencies:
      - "invoice-service (validar invoiceId)"
      - "gl-service (post journal entries)"
      - "user-service (validar aprovadores)"
    downstream_consumers:
      - "accounting-service (consumes GLEntryPosted)"
      - "reporting-service (consumes WriteOffApproved)"
```

---

## XIII. Metadados Técnicos

```yaml
technical_metadata:
  complexity:
    cyclomatic: 8
    cognitive: 12
    loc: 200
    decision_points: 6
    rationale: "Múltiplos branches de aprovação e lógica GL"
  test_coverage:
    recommended: "95%"
    critical_paths:
      - "Valores limites: R$ 100,00 / R$ 1.000,00"
      - "Lançamentos GL balanceados"
      - "Idempotência (write-off duplicado)"
      - "Approval workflow com timeout"
    integration_tests_required:
      - "ERP API indisponível (circuit breaker)"
      - "Aprovação concorrente (race conditions)"
      - "GL transaction rollback"
  performance:
    target_p50: "100ms"
    target_p95: "300ms"
    target_p99: "800ms"
    bottlenecks:
      - "Integração síncrona com GL system (100-300ms)"
      - "Criação de approval request (50ms)"
    optimization_recommendations:
      - "Batch de write-offs auto-aprovados"
      - "Integração assíncrona com GL via mensageria"
      - "Circuit breaker para ERP failures"
  scalability:
    expected_tps: "50-100"
    limited_by: "ERP API throughput"
    horizontal_scaling: true
  monitoring:
    key_metrics:
      - "write_offs_auto_approved_count"
      - "write_offs_pending_approval_count"
      - "gl_integration_latency_ms"
      - "approval_timeout_count"
    alerts:
      - "GL integration failures > 5% in 5 minutes"
      - "Pending approvals > 100 for > 1 hour"
```

---

**Gerado automaticamente em:** 2026-01-12
**Fonte:** Análise de código Camunda 7
**Revisão de Esquema:** 2026-01-12
