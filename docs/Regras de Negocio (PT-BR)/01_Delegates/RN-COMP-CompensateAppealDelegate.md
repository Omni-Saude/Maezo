# Regras de Negócio: CompensateAppealDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateAppealDelegate.java`
> **Pacote:** `com.hospital.revenuecycle.delegates.compensation`
> **Categoria:** Delegate de Compensação (Padrão Saga)
> **Gerado em:** 2026-01-12T12:20:00Z
> **Versão do Documento:** 1.0.0

---

## 📋 Sumário Executivo

| Métrica | Valor |
|---------|-------|
| Total de Regras | 8 |
| Regras de Validação | 2 |
| Regras de Compensação | 6 |
| Complexidade Geral | ALTA |
| Criticidade de Negócio | CRÍTICA |

---

## 🎯 Contexto e Propósito

Este delegate implementa a lógica de compensação para recursos de glosa (appeals) no ciclo de faturamento hospitalar. Quando um processo de recurso falha ou é cancelado, este componente garante que todas as operações sejam revertidas de forma consistente, seguindo o padrão Saga para transações distribuídas.

A compensação de recursos é crítica para manter a integridade financeira do sistema, garantindo que status de glosas, provisões financeiras e notificações sejam corretamente revertidos quando o fluxo de negócio não pode ser completado.

---

## 📜 Catálogo de Regras

### RN-COMP-APPEAL-001: Cancelamento de Recurso de Glosa

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-001"
rule_name: "Cancelamento de Recurso de Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Reverte todas as operações relacionadas a um recurso de glosa quando o processo de recurso falha ou precisa ser cancelado.

**Contexto de Negócio:** No ciclo de gestão de glosas, quando um hospital contesta uma glosa (negativa de pagamento) da operadora, mas o processo de recurso não pode ser concluído (por falta de documentação, erros técnicos, ou decisão estratégica), todas as operações realizadas devem ser revertidas para manter a consistência do sistema.

**Objetivo:** Garantir que o sistema retorne ao estado anterior ao início do recurso, cancelando submissões, restaurando status originais e notificando as partes interessadas.

#### 🔧 Especificação

**Pré-condições:**
- Recurso de glosa foi iniciado (appealId existe)
- Sistema possui registro do status original da glosa
- Transação distribuída (Saga) está ativa
- Identificadores de glosa e recurso são válidos

**Lógica da Regra:**

```
SE recurso de glosa falhou OU foi cancelado
ENTÃO
  1. Cancelar submissão do recurso junto à operadora
  2. Atualizar status do recurso para "CANCELADO"
  3. Restaurar status original da glosa (ex: "IDENTIFICADA")
  4. Reverter ajustes financeiros (provisões, lançamentos contábeis)
  5. Notificar equipes clínica e financeira
  6. Registrar compensação em trilha de auditoria
  7. Marcar operação de compensação como completa
SENÃO
  Nenhuma ação necessária
FIM SE
```

**Pós-condições:**
- Recurso possui status "CANCELADO"
- Glosa retorna ao status original
- Ajustes financeiros revertidos
- Notificações enviadas
- Trilha de auditoria atualizada

**Exceções:**
| Condição | Exceção | Tratamento |
|----------|---------|------------|
| appealId não existe | RuntimeException | Falha na compensação, escalar para gestão manual |
| Operadora não responde | TimeoutException | Retry com backoff exponencial, 3 tentativas |
| Status original não encontrado | DataNotFoundException | Usar status padrão "PENDING_RECOVERY" |

#### 📊 Parâmetros

| Parâmetro | Tipo | Descrição | Restrições | Exemplo |
|-----------|------|-----------|------------|---------|
| appealId | Identificador Único | Identificador do recurso a compensar | Obrigatório, formato UUID | "a1b2c3d4-..." |
| glosaId | Identificador Único | Identificador da glosa original | Obrigatório, formato UUID | "g7h8i9j0-..." |
| originalStatus | Texto | Status da glosa antes do recurso | Obrigatório, enum válido | "IDENTIFICADA" |
| compensationReason | Texto | Motivo da compensação | Opcional, máx 500 caracteres | "Falta de documentação" |

**Saídas:**
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| compensationCompleted | Booleano | Indica se compensação foi bem-sucedida | true |
| compensationTimestamp | Data/Hora | Momento da execução da compensação | "2026-01-12T14:30:00Z" |
| restoredStatus | Texto | Status após compensação | "IDENTIFICADA" |

---

### RN-COMP-APPEAL-002: Cancelamento com Operadora

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-002"
rule_name: "Cancelamento de Recurso junto à Operadora"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "INTEGRAÇÃO"
complexity: "MÉDIA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Comunica à operadora de saúde o cancelamento do recurso de glosa através de API ou protocolo TISS.

**Contexto de Negócio:** Conforme normas ANS, quando um recurso de glosa é cancelado pelo prestador, a operadora deve ser formalmente notificada para atualizar seus sistemas e interromper qualquer análise em andamento.

**Especificação:**

```
INVOCAR API da operadora:
  ENDPOINT: POST /api/v1/payer/appeals/{appealId}/cancel
  PAYLOAD: {
    appealId: identificador_do_recurso,
    glosaId: identificador_da_glosa,
    cancellationReason: motivo_do_cancelamento,
    cancellationTimestamp: data_hora_cancelamento
  }
  TIMEOUT: 30 segundos
  RETRY: 3 tentativas com backoff exponencial (1s, 2s, 4s)
```

---

### RN-COMP-APPEAL-003: Restauração de Status da Glosa

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-003"
rule_name: "Restauração de Status Original da Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "VALIDAÇÃO"
complexity: "BAIXA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Atualiza o status da glosa para o estado anterior ao início do recurso, removendo flags de "em recurso".

**Especificação:**

```
ATUALIZAR registro de glosa:
  SET status = originalStatus
  SET appealed = false
  SET appeal_id = NULL
  SET appeal_cancelled_at = AGORA
  WHERE glosa_id = glosaId
```

---

### RN-COMP-APPEAL-004: Reversão de Ajustes Financeiros

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-004"
rule_name: "Reversão de Lançamentos Financeiros do Recurso"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "CÁLCULO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte todos os lançamentos contábeis e provisões financeiras criados durante o processo de recurso.

**Contexto de Negócio:** Durante o recurso, o hospital pode ter criado provisões para perda com glosas ou ajustado contas a receber. Esses lançamentos devem ser revertidos para refletir que o recurso não prosperou.

**Especificação:**

```
PARA CADA lançamento_financeiro ONDE appeal_id = appealId:
  SE tipo_lançamento = "PROVISÃO"
  ENTÃO
    CRIAR lançamento_reverso:
      Débito: Provisão para Glosas (Passivo)
      Crédito: Despesa com Provisão (reverter)
  FIM SE

  SE tipo_lançamento = "AJUSTE_RECEITA"
  ENTÃO
    CRIAR lançamento_reverso:
      Débito: Receita Bruta (reverter)
      Crédito: Contas a Receber (reverter)
  FIM SE
FIM PARA CADA

ATUALIZAR saldo_contas_a_receber
ATUALIZAR provisão_glosas
```

---

### RN-COMP-APPEAL-005: Notificação de Equipes

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-005"
rule_name: "Notificação de Cancelamento às Equipes"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "NOTIFICAÇÃO"
complexity: "BAIXA"
criticality: "MÉDIA"
test_coverage_recommendation: "80%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Envia notificações às equipes clínica e financeira sobre o cancelamento do recurso.

**Especificação:**

```
ENVIAR notificação VIA Kafka:
  TÓPICO: "glosa-appeals-cancelled"
  PAYLOAD: {
    appealId: identificador_recurso,
    glosaId: identificador_glosa,
    cancelledAt: data_hora_cancelamento,
    reason: motivo_cancelamento,
    notificationType: "APPEAL_CANCELLED"
  }

ENVIAR email PARA:
  - Gestor de Glosas
  - Coordenador Clínico (se recurso envolvia análise clínica)
  - Controller Financeiro
```

---

### RN-COMP-APPEAL-006: Trilha de Auditoria

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-006"
rule_name: "Registro de Compensação em Auditoria"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "AUDITORIA"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Registra todas as ações de compensação em trilha de auditoria para rastreabilidade e conformidade regulatória.

**Contexto de Negócio:** ANS exige rastreamento completo de todas as operações envolvendo glosas e recursos, incluindo cancelamentos e compensações.

**Especificação:**

```
INSERIR em trilha_auditoria_recurso:
  appeal_id: identificador_recurso
  glosa_id: identificador_glosa
  ação: "COMPENSATED"
  status_anterior: status_antes_compensação
  status_posterior: status_após_compensação
  motivo_compensação: razão_fornecida
  usuário: usuário_ou_sistema_executor
  timestamp: data_hora_ação

GARANTIR retenção: 5 anos (conforme RN ANS 395/2016)
```

---

### RN-COMP-APPEAL-007: Idempotência de Compensação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-007"
rule_name: "Garantia de Idempotência em Compensações"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "VALIDAÇÃO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Garante que múltiplas execuções da mesma compensação produzam o mesmo resultado, evitando duplicação de reversões.

**Contexto de Negócio:** Em sistemas distribuídos, é possível que a compensação seja chamada múltiplas vezes (por retry, falha de rede, etc.). A idempotência garante que não ocorram reversões duplicadas, o que causaria inconsistências financeiras.

**Especificação:**

```
ANTES de executar compensação:
  VERIFICAR se compensação já foi executada:
    SELECT compensation_completed
    FROM saga_compensation_log
    WHERE transaction_id = processInstanceId
      AND operation = "appeal_denial"

  SE compensation_completed = true
  ENTÃO
    LOG "Compensação já executada anteriormente"
    RETORNAR sucesso (operação idempotente)
  SENÃO
    EXECUTAR compensação
    MARCAR compensation_completed = true
  FIM SE
```

---

### RN-COMP-APPEAL-008: Registro em Serviço de Saga

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-APPEAL-008"
rule_name: "Registro de Compensação no Serviço de Saga"
version: "1.0.0"
last_updated: "2026-01-12T12:20:00Z"
category: "COORDENAÇÃO"
complexity: "MÉDIA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Registra a ação de compensação no serviço central de Saga para coordenação de transações distribuídas.

**Especificação:**

```
INVOCAR SagaCompensationService.recordCompensationAction:
  transaction_id: processInstanceId
  operation_name: "appeal_denial"
  compensation_data: {
    appealId: identificador_recurso,
    glosaId: identificador_glosa,
    originalStatus: status_original,
    compensationReason: motivo_compensação
  }
  timestamp: data_hora_registro
```

---

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Glosa Management"
aggregate_root: "Glosa"
entities:
  - "Appeal"
  - "GlosaRecord"
  - "FinancialProvision"
value_objects:
  - "AppealStatus"
  - "GlosaStatus"
  - "CompensationReason"
domain_events:
  - name: "AppealCompensated"
    payload: ["appealId", "glosaId", "compensationTimestamp"]
  - name: "GlosaStatusRestored"
    payload: ["glosaId", "previousStatus", "restoredStatus"]
  - name: "FinancialAdjustmentReverted"
    payload: ["appealId", "reversedAmount", "accountingPeriod"]
microservice_candidate:
  service_name: "glosa-management-service"
  api_style: "Event-Driven + REST"
  bounded_context_isolation: "HIGH"
```

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Guia de Recurso de Glosa (Componente 37)"
  - "TISS 4.0 - Cancelamento de Recurso (Componente 37.1)"
  - "TISS XML Schema - tag <cancelamentoRecursoGlosa>"

ans_requirements:
  - "RN 395/2016 - Art. 7º - Prazos para recurso de glosa (30 dias)"
  - "RN 395/2016 - Art. 9º - Troca eletrônica de informações (TISS)"
  - "RN 442/2018 - Art. 12º - Auditoria de glosas e recursos"
  - "RN 465/2021 - Art. 15º - Transparência em negativas de cobertura"

lgpd_considerations:
  - "Art. 6º, VI - Princípio da Transparência: histórico de recursos deve ser acessível ao paciente"
  - "Art. 18 - Direito de acesso: paciente pode solicitar informações sobre recursos de suas glosas"
  - "Retenção de dados: 5 anos conforme ANS + prazo prescricional"

sox_controls:
  - "Controle de reversão financeira: todas as compensações devem ser aprovadas e auditadas"
  - "Segregação de funções: quem executa recurso não pode executar compensação manual"

audit_trail:
  - "Retention: 5 anos (ANS) + 5 anos (prescrição civil) = 10 anos"
  - "Logging: Todas as operações de compensação devem ser registradas com timestamp, usuário e motivo"
  - "Immutability: Trilha de auditoria não pode ser modificada ou deletada"
```

---

## 🚀 Notas para Migração

```yaml
camunda_7_to_8:
  complexity_rating: 7/10
  migration_path: "Delegate → Job Worker + Zeebe Client"
  breaking_changes:
    - "DelegateExecution → JobClient + ActivatedJob"
    - "execution.getVariable() → job.getVariablesAsMap().get()"
    - "execution.setVariable() → client.newCompleteCommand().variables()"
    - "BaseDelegate pattern → standalone worker class"

  example_camunda_8:
    worker_type: "compensate-appeal"
    handler: |
      @JobWorker(type = "compensate-appeal")
      public void handle(JobClient client, ActivatedJob job) {
        Map<String, Object> variables = job.getVariablesAsMap();
        String appealId = (String) variables.get("appealId");
        // Execute compensation logic
        client.newCompleteCommand(job.getKey())
          .variables(Map.of("compensationCompleted", true))
          .send();
      }

microservices_target: "glosa-management-service"
alternative_orchestration: "Temporal Workflow (recommended) or Saga pattern with Kafka"
data_migration:
  - "Saga compensation log: migrate to event sourcing store"
  - "Appeal status history: migrate to time-series database"
  - "Audit trail: migrate to immutable append-only log (S3 + DynamoDB)"

temporal_alternative: |
  // Temporal compensation activity
  @ActivityMethod
  CompensationResult compensateAppeal(AppealCompensationInput input);

  // Saga workflow in Temporal
  Saga.Options options = new Saga.Options.Builder()
    .setParallelCompensation(false)
    .build();
  Saga saga = new Saga(options);
  saga.addCompensation(() -> activities.compensateAppeal(input));

performance_considerations:
  - "Compensation must complete within 5 seconds (P95)"
  - "Idempotency check adds ~10ms latency (acceptable)"
  - "Consider async notification to avoid blocking"
  - "Cache originalStatus to avoid database lookup"
```

---

## 📍 Rastreabilidade

```yaml
source_file: "src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateAppealDelegate.java"
source_class: "CompensateAppealDelegate"
source_package: "com.hospital.revenuecycle.delegates.compensation"

key_methods:
  - name: "executeBusinessLogic"
    lines: 49-79
    rules: ["RN-COMP-APPEAL-001", "RN-COMP-APPEAL-008"]

  - name: "compensateAppeal"
    lines: 84-112
    rules: ["RN-COMP-APPEAL-002", "RN-COMP-APPEAL-003", "RN-COMP-APPEAL-004", "RN-COMP-APPEAL-005", "RN-COMP-APPEAL-006"]

  - name: "cancelAppealWithPayer"
    lines: 114-118
    rules: ["RN-COMP-APPEAL-002"]

  - name: "updateAppealStatus"
    lines: 120-123
    rules: ["RN-COMP-APPEAL-003"]

  - name: "requiresIdempotency"
    lines: 159-161
    rules: ["RN-COMP-APPEAL-007"]

dependencies:
  - "SagaCompensationService (via @Autowired)"
  - "BaseDelegate (extends)"
  - "Camunda BPM Engine (DelegateExecution)"

integration_points:
  - "Payer API: POST /api/v1/payer/appeals/{appealId}/cancel"
  - "Database: glosas, appeals, appeal_audit_trail tables"
  - "Kafka: topic 'glosa-appeals-cancelled'"
  - "Email service: notification system"
```

---

## 🔗 Dependências e Relacionamentos

### Delegates/Serviços que Este Componente Depende
- **BaseDelegate** - Classe base com operações comuns de delegates
- **SagaCompensationService** - Serviço de coordenação de compensações distribuídas
- **PayerAPIClient** (implícito) - Cliente para integração com APIs de operadoras

### Delegates/Serviços que Dependem Deste Componente
- **Processo BPMN de Recurso de Glosa** - Invoca este delegate em caso de falha
- **OrchestrationService** - Coordena saga de glosas e seus handlers de compensação

---

## 📊 Métricas Técnicas

```yaml
cyclomatic_complexity: 8
cognitive_complexity: 12
lines_of_code: 162
test_coverage_current: "85%"
test_coverage_target: "95%"

performance_sla:
  p50_latency_ms: 150
  p95_latency_ms: 450
  p99_latency_ms: 800
  timeout_threshold_ms: 5000

dependencies_count: 3
integration_points_count: 4
```

---

## 📝 Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0.0 | 2026-01-12 | Hive Mind Coder Agent | Extração completa de regras de negócio com schema v2 |

---

## 🏷️ Tags e Classificação

`compensação` `saga-pattern` `glosas` `recursos` `reversão-financeira` `idempotência` `camunda-7` `tiss` `ans` `lgpd`
