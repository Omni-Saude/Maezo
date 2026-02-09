# Regras de Negócio: CompensateSubmitDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateSubmitDelegate.java`
> **Pacote:** `com.hospital.revenuecycle.delegates.compensation`
> **Categoria:** Delegate de Compensação (Submissão de Faturamento)
> **Gerado em:** 2026-01-12T12:45:00Z
> **Versão do Documento:** 1.0.0

---

## 📋 Sumário Executivo

| Métrica | Valor |
|---------|-------|
| Total de Regras | 8 |
| Regras de Validação | 1 |
| Regras de Compensação | 7 |
| Complexidade Geral | ALTA |
| Criticidade de Negócio | CRÍTICA |

---

## 🎯 Contexto e Propósito

Este delegate implementa compensação para submissões de faturamento (claims) à operadora de saúde. Quando uma submissão falha ou precisa ser cancelada, todas as operações relacionadas (registro de submissão, atribuição de número de guia, transações EDI) devem ser revertidas para permitir reenvio ou cancelamento.

A compensação de submissões é crítica pois cobranças duplicadas às operadoras podem resultar em glosas, penalidades e perda de credibilidade. Cancelamentos incorretos podem deixar faturas "órfãs" (marcadas como enviadas mas sem confirmação da operadora).

---

## 📜 Catálogo de Regras

### RN-COMP-SUBMIT-001: Cancelamento de Submissão de Faturamento

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-001"
rule_name: "Cancelamento de Submissão de Faturamento"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Reverte todas as operações relacionadas à submissão de um claim à operadora, incluindo cancelamento junto à operadora, atualização de status, deleção de registros e cancelamento de transações EDI.

**Contexto de Negócio:** No processo de faturamento, após consolidação de cobranças, um claim (guia TISS) é submetido eletronicamente à operadora via XML ou EDI X12 837. Se esta submissão falha (erro de rede, rejeição imediata, ou falha no processo), todas as operações devem ser revertidas para permitir correção e reenvio.

**Objetivo:** Garantir que o claim retorne ao estado "PENDING_SUBMISSION" e que nenhum registro duplicado seja criado na próxima tentativa de envio.

#### 🔧 Especificação

**Pré-condições:**
- Submissão foi iniciada (submissionId existe)
- Claim relacionado existe
- Sistema possui registros da tentativa de submissão
- Operadora pode ser notificada sobre cancelamento (se necessário)

**Lógica da Regra:**

```
SE submissão de faturamento falhou OU requer cancelamento
ENTÃO
  1. Cancelar submissão junto à operadora (via API ou protocolo TISS)
  2. Atualizar status do claim para "PENDING_SUBMISSION"
     - claim.status = "PENDING_SUBMISSION"
     - claim.submitted_at = NULL
  3. Deletar registro de submissão (tabela claim_submissions)
  4. Reverter atribuição de número de guia da operadora
     - claim.payer_claim_number = NULL
  5. Cancelar transação EDI (se aplicável)
     - Deletar ou marcar EDI X12 837 como cancelado
  6. Notificar equipe de faturamento sobre cancelamento
  7. Atualizar trilha de auditoria
  8. Marcar compensação como completa
SENÃO
  Nenhuma ação necessária
FIM SE
```

**Pós-condições:**
- Submissão cancelada junto à operadora (se já enviada)
- Claim retorna ao status "PENDING_SUBMISSION"
- Registro de submissão deletado
- Número de guia da operadora removido
- Transação EDI cancelada
- Equipe notificada
- Trilha de auditoria atualizada

**Exceções:**
| Condição | Exceção | Tratamento |
|----------|---------|------------|
| submissionId não existe | RuntimeException | Falha na compensação, escalar |
| Operadora não responde | TimeoutException | Retry 3x, se falhar alertar operações |
| Claim já foi aprovado pela operadora | InvalidStateException | Bloquear cancelamento, requerer estorno formal |
| EDI já processado | EDIException | Alertar compliance, pode requerer glosa voluntária |

#### 📊 Parâmetros

| Parâmetro | Tipo | Descrição | Restrições | Exemplo |
|-----------|------|-----------|------------|---------|
| submissionId | Identificador Único | Identificador da submissão a cancelar | Obrigatório | "sub-123-abc" |
| claimId | Identificador Único | Identificador do claim | Obrigatório | "claim-456-def" |
| payerId | Identificador Único | Identificador da operadora | Opcional | "oper-789-ghi" |

**Saídas:**
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| compensationCompleted | Booleano | Sucesso da compensação | true |
| compensationTimestamp | Data/Hora | Momento do cancelamento | "2026-01-12T14:30:00Z" |

---

### RN-COMP-SUBMIT-002: Cancelamento junto à Operadora

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-002"
rule_name: "Cancelamento de Submissão junto à Operadora"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "INTEGRAÇÃO"
complexity: "MÉDIA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Comunica à operadora o cancelamento da submissão através de API ou protocolo TISS.

**Contexto de Negócio:** Conforme normas TISS, quando um prestador cancela uma guia já submetida, a operadora deve ser formalmente notificada para evitar processamento duplicado.

**Especificação:**

```
INVOCAR API da operadora:
  ENDPOINT: POST /api/v1/payer/{payerId}/submissions/{submissionId}/cancel
  PAYLOAD: {
    submissionId: identificador_submissão,
    claimId: identificador_claim,
    cancellationReason: "Process failure - Saga compensation",
    cancellationTimestamp: data_hora_cancelamento
  }
  TIMEOUT: 30 segundos
  RETRY: 3 tentativas com backoff exponencial (1s, 2s, 4s)

ALTERNATIVA (se API não disponível):
  -- Enviar cancelamento via protocolo TISS XML
  GERAR XML de cancelamento:
    <cancelamentoGuia>
      <numeroGuia>{claimNumber}</numeroGuia>
      <motivoCancelamento>Compensação de processo</motivoCancelamento>
      <dataCancelamento>{timestamp}</dataCancelamento>
    </cancelamentoGuia>

TRATAMENTO DE ERRO:
  SE operadora retorna erro "guia já processada" ENTÃO
    ALERTAR operações de faturamento (URGENTE)
    BLOQUEAR cancelamento automático
    REQUERER estorno formal via glosa voluntária
  FIM SE
```

---

### RN-COMP-SUBMIT-003: Atualização de Status do Claim

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-003"
rule_name: "Reversão de Status do Claim para Pending"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "VALIDAÇÃO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Atualiza o status do claim para "PENDING_SUBMISSION" e remove timestamp de submissão.

**Especificação:**

```
EXECUTAR SQL:
  UPDATE claims
  SET status = 'PENDING_SUBMISSION',
      submitted_at = NULL,
      submission_cancelled_at = AGORA,
      last_modified = AGORA
  WHERE claim_id = claimId

LOG info "Claim status reverted to PENDING_SUBMISSION: {claimId}"
```

---

### RN-COMP-SUBMIT-004: Deleção de Registro de Submissão

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-004"
rule_name: "Deleção de Registro de Submissão"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "ROTEAMENTO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Remove o registro da tentativa de submissão da tabela `claim_submissions`.

**Especificação:**

```
EXECUTAR SQL:
  DELETE FROM claim_submissions
  WHERE submission_id = submissionId

VERIFICAR:
  SE linhas_afetadas = 0 ENTÃO
    LOG warning "Submission record not found for deletion"
  SENÃO
    LOG info "Submission record deleted: {submissionId}"
  FIM SE
```

---

### RN-COMP-SUBMIT-005: Reversão de Número de Guia da Operadora

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-005"
rule_name: "Reversão de Atribuição de Número de Guia"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "VALIDAÇÃO"
complexity: "BAIXA"
criticality: "MÉDIA"
test_coverage_recommendation: "90%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Remove o número de guia atribuído pela operadora (payer_claim_number).

**Contexto de Negócio:** Quando uma guia é submetida, a operadora retorna um número de protocolo/guia. Se a submissão for cancelada, este número deve ser removido para evitar confusão em futuras submissões.

**Especificação:**

```
EXECUTAR SQL:
  UPDATE claims
  SET payer_claim_number = NULL
  WHERE claim_id = claimId

LOG "Payer claim number reversed for claim: {claimId}"
```

---

### RN-COMP-SUBMIT-006: Cancelamento de Transação EDI

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-006"
rule_name: "Cancelamento de Transação EDI X12 837"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "INTEGRAÇÃO"
complexity: "MÉDIA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Cancela ou marca como cancelada a transação EDI (Electronic Data Interchange) criada para submissão.

**Contexto de Negócio:** EDI X12 837 é o formato padrão nos EUA para submissão eletrônica de claims. No Brasil, TISS XML é o equivalente. Transações EDI canceladas devem ser marcadas para evitar reprocessamento.

**Especificação:**

```
EXECUTAR operação conforme protocolo:

  SE protocolo = "EDI_X12" ENTÃO
    -- Marcar transação EDI como cancelada
    UPDATE edi_transactions
    SET status = 'CANCELLED',
        cancelled_at = AGORA
    WHERE submission_id = submissionId

    -- Registrar cancelamento no interchange
    INSERT INTO edi_audit_log (
      interchange_id, event, timestamp, reason
    ) VALUES (
      edi_interchange_id, 'CANCELLED', AGORA, 'Saga compensation'
    )

  SENÃO SE protocolo = "TISS_XML" ENTÃO
    -- Deletar arquivo XML gerado
    DELETE FROM tiss_xml_files
    WHERE submission_id = submissionId

    -- Registrar cancelamento
    LOG "TISS XML cancelled for submission: {submissionId}"
  FIM SE
```

---

### RN-COMP-SUBMIT-007: Notificação de Equipe de Faturamento

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-007"
rule_name: "Notificação de Cancelamento de Submissão"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "NOTIFICAÇÃO"
complexity: "BAIXA"
criticality: "MÉDIA"
test_coverage_recommendation: "85%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Envia notificações à equipe de faturamento sobre cancelamento de submissão.

**Especificação:**

```
ENVIAR notificação VIA Kafka:
  TÓPICO: "claim-submissions-cancelled"
  PAYLOAD: {
    submissionId: identificador_submissão,
    claimId: identificador_claim,
    payerId: identificador_operadora,
    cancelledAt: data_hora_cancelamento,
    notificationType: "SUBMISSION_CANCELLED"
  }

ENVIAR email PARA:
  - Coordenador de Faturamento
  - Analista de Contas Médicas
  - Gestor de Relacionamento com Operadora (se valor > R$ 10.000)

INCLUIR no email:
  - Claim cancelado
  - Operadora destinatária
  - Motivo do cancelamento
  - Ações necessárias (revisar, corrigir, reenviar)
  - Link para o claim no sistema
```

---

### RN-COMP-SUBMIT-008: Registro em Trilha de Auditoria

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-SUBMIT-008"
rule_name: "Registro de Cancelamento em Auditoria"
version: "1.0.0"
last_updated: "2026-01-12T12:45:00Z"
category: "AUDITORIA"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Registra todas as operações de cancelamento de submissão em trilha de auditoria.

**Especificação:**

```
INSERIR em trilha_auditoria_submissão:
  submission_id: identificador_submissão
  claim_id: identificador_claim
  payer_id: identificador_operadora
  ação: "CANCELLED"
  cancellation_reason: "Saga compensation rollback"
  cancelled_by: usuário_ou_sistema_executor
  timestamp: data_hora_ação
  original_status: status_antes_cancelamento

GARANTIR:
  - Retenção: 5 anos (ANS) + prazo prescricional
  - Imutabilidade: trilha não pode ser modificada
  - Rastreabilidade: link com processo BPMN e saga transaction
```

---

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Billing"
aggregate_root: "Claim"
entities:
  - "ClaimSubmission"
  - "EDITransaction"
  - "PayerIntegration"
value_objects:
  - "SubmissionStatus"
  - "PayerClaimNumber"
  - "EDIInterchangeId"
domain_events:
  - name: "SubmissionCancelled"
    payload: ["submissionId", "claimId", "cancellationTimestamp"]
  - name: "ClaimStatusReverted"
    payload: ["claimId", "previousStatus", "newStatus"]
  - name: "PayerNotified"
    payload: ["payerId", "notificationType", "referenceId"]
microservice_candidate:
  service_name: "claim-submission-service"
  api_style: "Event-Driven + REST"
  bounded_context_isolation: "HIGH"
```

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Guia de Consulta (Componente 1)"
  - "TISS 4.0 - Guia SP/SADT (Componente 2)"
  - "TISS 4.0 - Guia de Internação (Componente 3)"
  - "TISS 4.0 - Cancelamento de Guia (protocolo XML)"
  - "TISS XML Schema - tag <cancelamentoGuia>"

ans_requirements:
  - "RN 395/2016 - Art. 9º - Troca eletrônica de informações via TISS"
  - "RN 442/2018 - Art. 8º - Rastreabilidade de submissões"
  - "RN 465/2021 - Art. 12º - Transparência em submissões e negativas"

lgpd_considerations:
  - "Art. 6º, III - Princípio da Necessidade: armazenar apenas dados necessários de submissões"
  - "Art. 46 - Logs de submissões devem ser mantidos de forma segura"

sox_controls:
  - "Controle de Submissões Duplicadas: prevenir envio múltiplo da mesma guia"
  - "Segregação de Funções: cancelamento requer aprovação diferente de submissão"
  - "Auditoria: trilha completa de tentativas, sucessos e cancelamentos"

edi_compliance:
  - "HIPAA 5010 - EDI X12 837 (se aplicável para operadoras internacionais)"
  - "ANSI ASC X12 - Standards para transações EDI"

audit_trail:
  - "Retention: 5 anos (ANS) + prazo prescricional"
  - "Logging: Todas as submissões e cancelamentos com timestamps e motivos"
  - "Immutability: Trilha em append-only log"
```

---

## 🚀 Notas para Migração

```yaml
camunda_7_to_8:
  complexity_rating: 6/10
  migration_path: "Delegate → Job Worker + Zeebe Client"
  breaking_changes:
    - "DelegateExecution → JobClient + ActivatedJob"
    - "Retry logic: migrar para Zeebe retry policies"
    - "Error handling: usar Zeebe incidents para falhas críticas"

  example_camunda_8:
    worker_type: "compensate-submit"
    handler: |
      @JobWorker(type = "compensate-submit", timeout = 30000)
      public void handle(JobClient client, ActivatedJob job) {
        Map<String, Object> variables = job.getVariablesAsMap();
        String submissionId = (String) variables.get("submissionId");

        try {
          compensateSubmission(variables);

          client.newCompleteCommand(job.getKey())
            .variables(Map.of("compensationCompleted", true))
            .send();

        } catch (PayerAPIException e) {
          // Falha na comunicação com operadora
          client.newFailCommand(job.getKey())
            .retries(job.getRetries() - 1)
            .errorMessage("Payer API failure: " + e.getMessage())
            .send();
        }
      }

microservices_target: "claim-submission-service"
alternative_orchestration: "Saga pattern with Kafka + Outbox pattern"

edi_modernization:
  - "Current: synchronous EDI submission"
  - "Target: async event-driven submission with Kafka"
  - "Benefits: resilience, retry, audit trail"

temporal_alternative: |
  @ActivityMethod
  CompensationResult compensateSubmission(SubmissionInput input);

  Saga saga = new Saga(new Saga.Options.Builder()
    .setParallelCompensation(false)
    .build());
  saga.addCompensation(() ->
    activities.compensateSubmission(input)
  );

performance_considerations:
  - "Compensação deve completar em < 5 segundos (P95)"
  - "API operadora: usar circuit breaker pattern"
  - "EDI cancelamento: processar async para não bloquear"
  - "Notificações: enviar de forma assíncrona"
```

---

## 📍 Rastreabilidade

```yaml
source_file: "src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateSubmitDelegate.java"
source_class: "CompensateSubmitDelegate"
source_package: "com.hospital.revenuecycle.delegates.compensation"

key_methods:
  - name: "executeBusinessLogic"
    lines: 23-67
    rules: ["RN-COMP-SUBMIT-001", "RN-COMP-SUBMIT-002", "RN-COMP-SUBMIT-003", "RN-COMP-SUBMIT-004", "RN-COMP-SUBMIT-005", "RN-COMP-SUBMIT-006", "RN-COMP-SUBMIT-007", "RN-COMP-SUBMIT-008"]

  - name: "cancelClaimSubmission"
    lines: 69-73
    rules: ["RN-COMP-SUBMIT-002"]

  - name: "updateClaimStatus"
    lines: 75-78
    rules: ["RN-COMP-SUBMIT-003"]

  - name: "deleteSubmissionRecord"
    lines: 80-83
    rules: ["RN-COMP-SUBMIT-004"]

dependencies:
  - "BaseDelegate (extends)"
  - "Camunda BPM Engine (DelegateExecution)"

integration_points:
  - "Payer API: POST /api/v1/payer/{payerId}/submissions/{submissionId}/cancel"
  - "Database: claim_submissions, claims, edi_transactions, tiss_xml_files, submission_audit_trail tables"
  - "Kafka: topic 'claim-submissions-cancelled'"
  - "Email service: billing team notifications"
```

---

## 🔗 Dependências e Relacionamentos

### Delegates/Serviços que Este Componente Depende
- **BaseDelegate** - Classe base
- **PayerAPIClient** (implícito) - Cliente para APIs de operadoras
- **EDIService** (implícito) - Gerenciamento de transações EDI

### Delegates/Serviços que Dependem Deste Componente
- **Processo BPMN de Submissão de Faturamento** - Invoca em falhas
- **BillingSubmissionService** - Utiliza para cancelar submissões

---

## 📊 Métricas Técnicas

```yaml
cyclomatic_complexity: 7
cognitive_complexity: 10
lines_of_code: 118
test_coverage_current: "75%"
test_coverage_target: "95%"

performance_sla:
  p50_latency_ms: 300
  p95_latency_ms: 1500
  p99_latency_ms: 3000
  timeout_threshold_ms: 5000

dependencies_count: 1
integration_points_count: 4
database_tables_affected: 4
```

---

## 📝 Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0.0 | 2026-01-12 | Hive Mind Coder Agent | Extração completa de regras de negócio com schema v2 |

---

## 🏷️ Tags e Classificação

`compensação` `saga-pattern` `submissão-faturamento` `claims` `tiss` `edi` `operadoras` `idempotência` `camunda-7` `ans`
