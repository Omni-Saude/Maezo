# Regras de Negócio: CompensateRecoveryDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateRecoveryDelegate.java`
> **Pacote:** `com.hospital.revenuecycle.delegates.compensation`
> **Categoria:** Delegate de Compensação (Recuperação de Glosas)
> **Gerado em:** 2026-01-12T12:40:00Z
> **Versão do Documento:** 1.0.0

---

## 📋 Sumário Executivo

| Métrica | Valor |
|---------|-------|
| Total de Regras | 9 |
| Regras de Validação | 1 |
| Regras de Compensação | 8 |
| Complexidade Geral | ALTA |
| Criticidade de Negócio | CRÍTICA |

---

## 🎯 Contexto e Propósito

Este delegate implementa compensação para operações de recuperação de glosas. Quando uma glosa é recuperada (total ou parcialmente) através de recursos ou negociações, mas a operação precisa ser revertida, todos os registros e ajustes financeiros devem ser cancelados para manter integridade do processo de gestão de glosas.

A compensação de recuperações é crítica pois afeta métricas de performance (recovery rate), provisões financeiras e pode impactar bonificações de equipes de recuperação. Reversões incorretas podem causar dupla contagem de recuperações ou perda de rastreabilidade de glosas.

---

## 📜 Catálogo de Regras

### RN-COMP-RECOV-001: Cancelamento de Recuperação de Glosa

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-001"
rule_name: "Cancelamento de Recuperação de Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Reverte todas as operações relacionadas a uma recuperação de glosa, incluindo cancelamento de registro, reversão de status, eliminação de lançamentos financeiros e notificação de equipes.

**Contexto de Negócio:** No processo de gestão de glosas, quando uma glosa é recuperada (operadora aceita o recurso e efetua pagamento), o sistema registra esta recuperação. Se por algum motivo (erro de registro, pagamento cancelado, ou falha no processo) a recuperação precisa ser revertida, todas as operações devem ser desfeitas.

**Objetivo:** Garantir que a glosa retorne ao estado "PENDING_RECOVERY" e que todas as métricas, provisões e notificações sejam corrigidas.

#### 🔧 Especificação

**Pré-condições:**
- Recuperação foi registrada (recoveryId existe)
- Glosa relacionada existe
- Sistema possui registro do status original da glosa
- Valor recuperado (se houver) é conhecido

**Lógica da Regra:**

```
SE recuperação de glosa falhou OU requer reversão
ENTÃO
  1. Cancelar registro de recuperação
     - UPDATE glosa_recoveries SET status = 'CANCELLED'
  2. Atualizar status da glosa para status original (PENDING_RECOVERY)
  3. Reverter recovered_amount na tabela de glosas
     - glosas.recovered_amount -= amount
  4. Cancelar lançamentos financeiros (se houve impacto financeiro)
  5. Restaurar provisão (se foi eliminada durante recuperação)
  6. Notificar equipe de recuperação sobre cancelamento
  7. Atualizar trilha de auditoria
  8. Recalcular métricas de recuperação (recovery rate, average time)
SENÃO
  Nenhuma ação necessária
FIM SE
```

**Pós-condições:**
- Registro de recuperação marcado como "CANCELLED"
- Glosa retorna ao status original
- Valor recuperado revertido (recovered_amount ajustado)
- Lançamentos financeiros cancelados
- Provisão restaurada (se aplicável)
- Equipe notificada
- Trilha de auditoria atualizada
- Métricas recalculadas

**Exceções:**
| Condição | Exceção | Tratamento |
|----------|---------|------------|
| recoveryId não existe | RuntimeException | Falha na compensação, escalar |
| Glosa já foi liquidada | BusinessRuleException | Requerer revisão manual, alertar controller |
| Provisão não pode ser restaurada | ProvisionException | Criar provisão manualmente, alertar financeiro |

#### 📊 Parâmetros

| Parâmetro | Tipo | Descrição | Restrições | Exemplo |
|-----------|------|-----------|------------|---------|
| glosaId | Identificador Único | Identificador da glosa | Obrigatório | "glosa-789-abc" |
| recoveryId | Identificador Único | Identificador da recuperação | Obrigatório | "recov-123-def" |
| recoveredAmount | Decimal | Valor recuperado a reverter | Opcional, >= 0 | 12000.00 |
| originalStatus | Texto | Status da glosa antes da recuperação | Obrigatório | "IDENTIFIED" |

**Saídas:**
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| compensationCompleted | Booleano | Sucesso da compensação | true |
| restoredStatus | Texto | Status após compensação | "PENDING_RECOVERY" |
| compensationTimestamp | Data/Hora | Momento da reversão | "2026-01-12T14:30:00Z" |

---

### RN-COMP-RECOV-002: Cancelamento de Registro de Recuperação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-002"
rule_name: "Cancelamento de Registro de Recuperação"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "ROTEAMENTO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Atualiza o status do registro de recuperação para "CANCELLED" mantendo histórico.

**Especificação:**

```
EXECUTAR SQL:
  UPDATE glosa_recoveries
  SET status = 'CANCELLED',
      cancelled_at = AGORA,
      cancellation_reason = 'Saga compensation rollback'
  WHERE recovery_id = recoveryId

LOG info "Recuperação cancelada: {recoveryId}"
```

---

### RN-COMP-RECOV-003: Atualização de Status da Glosa

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-003"
rule_name: "Restauração de Status Original da Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "VALIDAÇÃO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Atualiza o status da glosa para o estado anterior à recuperação.

**Especificação:**

```
EXECUTAR SQL:
  UPDATE glosas
  SET status = originalStatus,
      recovered_at = NULL,
      recovery_cancelled_at = AGORA
  WHERE glosa_id = glosaId

VALIDAR:
  SE status anterior era "RECOVERED" ENTÃO
    Alertar que glosa estava totalmente recuperada, revisar manualmente
  FIM SE
```

---

### RN-COMP-RECOV-004: Reversão de Valor Recuperado

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-004"
rule_name: "Reversão de Valor Recuperado na Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "CÁLCULO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Reduz o campo `recovered_amount` da glosa pelo valor que foi recuperado.

**Especificação:**

```
EXECUTAR SQL:
  UPDATE glosas
  SET recovered_amount = recovered_amount - recoveredAmount
  WHERE glosa_id = glosaId

VALIDAR:
  SE recovered_amount < 0 APÓS atualização ENTÃO
    LANÇAR exceção "Recovered amount cannot be negative"
  FIM SE

  SE recovered_amount = 0 APÓS reversão ENTÃO
    -- Glosa não possui mais nenhuma recuperação
    UPDATE glosas
    SET status = 'IDENTIFIED' -- Voltar para status inicial
    WHERE glosa_id = glosaId
  FIM SE
```

**Fórmula:**
```
recovered_amount_new = recovered_amount_old - recoveredAmount

Invariante: recovered_amount >= 0
```

---

### RN-COMP-RECOV-005: Cancelamento de Lançamentos Financeiros

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-005"
rule_name: "Cancelamento de Lançamentos Financeiros da Recuperação"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "CÁLCULO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte quaisquer lançamentos financeiros criados durante o registro da recuperação.

**Contexto de Negócio:** Quando uma glosa é recuperada, podem ser criados lançamentos para reconhecer a receita ou reverter provisões. Esses lançamentos devem ser cancelados.

**Especificação:**

```
SE recoveredAmount > 0 ENTÃO
  -- Reverter reconhecimento de receita (se aplicável)
  CRIAR lançamento de reversão:
    Débito: Receita com Recuperação de Glosas (reverter)
    Crédito: Contas a Receber - Operadoras (reverter)
    Valor: recoveredAmount
    Referência: "REV-RECOV-{recoveryId}"

  EXECUTAR:
    INSERT INTO journal_entries (...)
    VALUES (reversão)

  -- Atualizar GL
  ATUALIZAR saldos de receita e contas a receber
FIM SE

LOG "Lançamentos financeiros cancelados para recuperação: {recoveryId}"
```

---

### RN-COMP-RECOV-006: Restauração de Provisão

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-006"
rule_name: "Restauração de Provisão para Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "CÁLCULO"
complexity: "ALTA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Se a provisão foi eliminada durante a recuperação, ela deve ser restaurada.

**Contexto de Negócio:** Quando uma glosa é recuperada, a provisão contábil criada anteriormente é revertida (elimina-se o passivo pois não haverá perda). Se a recuperação for cancelada, a provisão deve ser recriada.

**Especificação:**

```
VERIFICAR se glosa tinha provisão:
  SELECT provision_id
  FROM glosas
  WHERE glosa_id = glosaId
    AND provisioned = false
    AND provision_reversed_at IS NOT NULL

SE provisão foi eliminada durante recuperação ENTÃO
  CRIAR nova provisão:
    INSERT INTO glosa_provisions (
      glosa_id, amount, created_at, reason
    ) VALUES (
      glosaId, recoveredAmount, AGORA, 'Restaured due to recovery cancellation'
    )

  CRIAR lançamentos contábeis de provisão:
    Débito: Despesa com Provisão
    Crédito: Provisão para Glosas
    Valor: recoveredAmount

  ATUALIZAR glosa:
    UPDATE glosas
    SET provisioned = true,
        provision_id = nova_provision_id
    WHERE glosa_id = glosaId
FIM SE
```

---

### RN-COMP-RECOV-007: Notificação de Equipe de Recuperação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-007"
rule_name: "Notificação de Cancelamento de Recuperação"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "NOTIFICAÇÃO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "85%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Envia notificações à equipe de recuperação sobre cancelamento.

**Especificação:**

```
ENVIAR notificação VIA Kafka:
  TÓPICO: "glosa-recovery-cancelled"
  PAYLOAD: {
    recoveryId: identificador_recuperação,
    glosaId: identificador_glosa,
    cancelledAmount: valor_revertido,
    cancelledAt: data_hora_cancelamento,
    notificationType: "RECOVERY_CANCELLED"
  }

ENVIAR email PARA:
  - Gestor de Recuperação de Glosas
  - Analista responsável pela glosa
  - Controller Financeiro (se valor > R$ 20.000)

INCLUIR no email:
  - Valor recuperado que foi cancelado
  - Glosa relacionada
  - Motivo do cancelamento
  - Status atual da glosa
  - Ações necessárias (reanalisar, reenviar recurso, etc.)
```

---

### RN-COMP-RECOV-008: Registro em Trilha de Auditoria

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-008"
rule_name: "Registro de Compensação em Auditoria"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "AUDITORIA"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Registra todas as operações de compensação de recuperação em trilha de auditoria.

**Especificação:**

```
INSERIR em trilha_auditoria_recuperação:
  recovery_id: identificador_recuperação
  glosa_id: identificador_glosa
  ação: "COMPENSATED"
  reversed_amount: valor_revertido
  original_status: status_original
  restored_status: status_restaurado
  usuário: usuário_ou_sistema_executor
  timestamp: data_hora_ação
  motivo: "Saga compensation rollback"

GARANTIR retenção: 5 anos (conformidade ANS)
```

---

### RN-COMP-RECOV-009: Recálculo de Métricas de Recuperação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-RECOV-009"
rule_name: "Recálculo de KPIs de Recuperação de Glosas"
version: "1.0.0"
last_updated: "2026-01-12T12:40:00Z"
category: "CÁLCULO"
complexity: "MÉDIA"
criticality: "MÉDIA"
test_coverage_recommendation: "85%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Atualiza métricas e KPIs de recuperação após cancelamento.

**Contexto de Negócio:** Equipes de recuperação são avaliadas por taxa de recuperação, tempo médio de recuperação, etc. Cancelamentos devem ser refletidos nessas métricas.

**Especificação:**

```
RECALCULAR KPIs:
  -- Recovery Rate (Taxa de Recuperação)
  recovery_rate = (
    SELECT (COUNT(*) FILTER (WHERE status = 'RECOVERED') * 100.0) / COUNT(*)
    FROM glosas
    WHERE identified_at >= INICIO_PERIODO
  )

  -- Average Recovery Time (Tempo Médio de Recuperação)
  avg_recovery_time = (
    SELECT AVG(EXTRACT(EPOCH FROM (recovered_at - identified_at)) / 86400)
    FROM glosas
    WHERE status = 'RECOVERED'
      AND identified_at >= INICIO_PERIODO
  )

  -- Total Recovered Amount (Valor Total Recuperado)
  total_recovered = (
    SELECT SUM(recovered_amount)
    FROM glosas
    WHERE status = 'RECOVERED'
      AND identified_at >= INICIO_PERIODO
  )

ATUALIZAR tabela de métricas:
  UPDATE recovery_metrics
  SET recovery_rate = recovery_rate_calculado,
      avg_recovery_time_days = avg_recovery_time_calculado,
      total_recovered_amount = total_recovered_calculado,
      cancelled_recoveries_count = cancelled_recoveries_count + 1,
      last_updated = AGORA
  WHERE period = PERIODO_ATUAL
```

---

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Glosa Management"
aggregate_root: "Glosa"
entities:
  - "GlosaRecovery"
  - "GlosaRecord"
  - "Provision"
value_objects:
  - "RecoveryAmount"
  - "GlosaStatus"
  - "RecoveryStatus"
domain_events:
  - name: "RecoveryCompensated"
    payload: ["recoveryId", "glosaId", "compensationTimestamp"]
  - name: "GlosaStatusRestored"
    payload: ["glosaId", "previousStatus", "restoredStatus"]
  - name: "RecoveryMetricsRecalculated"
    payload: ["period", "newRecoveryRate", "newAvgTime"]
microservice_candidate:
  service_name: "glosa-recovery-service"
  api_style: "Event-Driven + REST"
  bounded_context_isolation: "HIGH"
```

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Guia de Recurso de Glosa (Componente 37)"
  - "TISS 4.0 - Demonstrativo de Retorno de Recurso (Componente 38)"

ans_requirements:
  - "RN 395/2016 - Art. 7º - Prazos para análise de recursos"
  - "RN 442/2018 - Art. 12º - Rastreabilidade de glosas e recuperações"
  - "RN 465/2021 - Art. 15º - Transparência em negativas e recuperações"

lgpd_considerations:
  - "Art. 6º, VI - Princípio da Transparência: histórico de recuperações deve ser acessível"
  - "Art. 18 - Direito de acesso: paciente pode solicitar informações sobre recuperações"

audit_trail:
  - "Retention: 5 anos (ANS) + prazo prescricional"
  - "Logging: Todas as compensações de recuperação com valores e motivos"
  - "Immutability: Trilha não pode ser modificada"
```

---

## 🚀 Notas para Migração

```yaml
camunda_7_to_8:
  complexity_rating: 6/10
  migration_path: "Delegate → Job Worker + Zeebe Client"
  breaking_changes:
    - "DelegateExecution → JobClient + ActivatedJob"
    - "Métricas: migrar para time-series database (InfluxDB)"

microservices_target: "glosa-recovery-service"
alternative_orchestration: "Saga pattern with Kafka"

temporal_alternative: |
  @ActivityMethod
  CompensationResult compensateRecovery(RecoveryInput input);

  Saga saga = new Saga(new Saga.Options.Builder()
    .setParallelCompensation(false)
    .build());
  saga.addCompensation(() -> activities.compensateRecovery(input));

performance_considerations:
  - "Compensação deve completar em < 2 segundos (P95)"
  - "Recálculo de métricas: executar async em background"
  - "Notificações: processar de forma assíncrona"
```

---

## 📍 Rastreabilidade

```yaml
source_file: "src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateRecoveryDelegate.java"
source_class: "CompensateRecoveryDelegate"
source_package: "com.hospital.revenuecycle.delegates.compensation"

key_methods:
  - name: "executeBusinessLogic"
    lines: 50-81
    rules: ["RN-COMP-RECOV-001"]

  - name: "compensateRecovery"
    lines: 86-121
    rules: ["RN-COMP-RECOV-002", "RN-COMP-RECOV-003", "RN-COMP-RECOV-004", "RN-COMP-RECOV-005", "RN-COMP-RECOV-006", "RN-COMP-RECOV-007", "RN-COMP-RECOV-008", "RN-COMP-RECOV-009"]

  - name: "requiresIdempotency"
    lines: 178-180
    rules: ["Idempotência implícita via Saga"]

dependencies:
  - "SagaCompensationService (via @Autowired)"
  - "BaseDelegate (extends)"
  - "Camunda BPM Engine (DelegateExecution)"

integration_points:
  - "Database: glosa_recoveries, glosas, glosa_provisions, journal_entries, recovery_metrics, recovery_audit_trail tables"
  - "Kafka: topic 'glosa-recovery-cancelled'"
  - "Email service: recovery team notifications"
```

---

## 🔗 Dependências e Relacionamentos

### Delegates/Serviços que Este Componente Depende
- **BaseDelegate** - Classe base
- **SagaCompensationService** - Coordenação de saga
- **ProvisionService** (implícito) - Restauração de provisões

### Delegates/Serviços que Dependem Deste Componente
- **Processo BPMN de Recuperação de Glosa** - Invoca em falhas
- **GlosaManagementService** - Utiliza para reverter recuperações

---

## 📊 Métricas Técnicas

```yaml
cyclomatic_complexity: 9
cognitive_complexity: 13
lines_of_code: 182
test_coverage_current: "80%"
test_coverage_target: "95%"

performance_sla:
  p50_latency_ms: 200
  p95_latency_ms: 600
  p99_latency_ms: 1000
  timeout_threshold_ms: 5000

dependencies_count: 2
integration_points_count: 3
database_tables_affected: 6
```

---

## 📝 Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0.0 | 2026-01-12 | Hive Mind Coder Agent | Extração completa de regras de negócio com schema v2 |

---

## 🏷️ Tags e Classificação

`compensação` `saga-pattern` `recuperação-glosas` `glosas` `métricas` `kpis` `idempotência` `camunda-7` `tiss` `ans`
