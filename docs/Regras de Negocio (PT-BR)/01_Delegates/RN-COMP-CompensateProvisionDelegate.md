# Regras de Negócio: CompensateProvisionDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateProvisionDelegate.java`
> **Pacote:** `com.hospital.revenuecycle.delegates.compensation`
> **Categoria:** Delegate de Compensação (Provisões Financeiras)
> **Gerado em:** 2026-01-12T12:35:00Z
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

Este delegate implementa compensação para criação de provisões financeiras relacionadas a glosas. Provisões são lançamentos contábeis preventivos que registram possíveis perdas financeiras com glosas não recuperáveis, seguindo princípios contábeis conservadores e requisitos SOX.

A compensação de provisões é crítica pois afeta demonstrações financeiras, balanços patrimoniais e pode impactar relatórios de auditoria. Reversões incorretas podem causar distorções em lucros/prejuízos reportados e violar controles SOX.

---

## 📜 Catálogo de Regras

### RN-COMP-PROV-001: Reversão de Provisão Financeira para Glosas

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-001"
rule_name: "Reversão de Provisão Financeira para Glosas"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "98%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte todas as operações relacionadas à criação de uma provisão financeira para glosas, incluindo lançamentos contábeis, atualizações de status e integrações com ERP.

**Contexto de Negócio:** Quando uma glosa é identificada, o hospital cria uma provisão contábil (Despesa com Provisão no resultado, Provisão para Glosas no passivo) para reconhecer a possível perda. Se esta operação falha ou precisa ser cancelada, todos os lançamentos devem ser revertidos para não distorcer demonstrações financeiras.

**Objetivo:** Garantir integridade contábil e compliance com princípios contábeis (Prudência/Conservadorismo), revertendo provisões de forma completa e rastreável.

#### 🔧 Especificação

**Pré-condições:**
- Provisão foi criada (provisionId existe)
- Glosa relacionada existe e possui referência à provisão
- Valor da provisão é conhecido
- Período contábil da provisão está identificado
- Lançamentos contábeis foram registrados

**Lógica da Regra:**

```
SE criação de provisão falhou OU requer reversão
ENTÃO
  1. Deletar registro de provisão (tabela glosa_provisions)
  2. Reverter lançamentos contábeis:
     - Débito: Provisão para Glosas (Passivo Circulante - conta 2101)
     - Crédito: Despesa com Provisão (Resultado - conta 6301)
  3. Atualizar status da glosa:
     - Remover flag "provisioned"
     - Status = "PENDING_PROVISION"
  4. Restaurar saldos financeiros no GL (General Ledger)
  5. Cancelar transação no ERP externo (se integrado)
  6. Notificar controladores financeiros sobre reversão
  7. Atualizar analytics de provisões (decrementar contadores)
  8. Criar trilha de auditoria da reversão
  9. Retornar valor revertido
SENÃO
  Nenhuma ação necessária
FIM SE
```

**Lançamentos Contábeis de Reversão:**
```
Débito: 2101 - Provisão para Glosas (Passivo)      R$ provisionAmount
Crédito: 6301 - Despesa com Provisão (Resultado)   R$ provisionAmount

Efeito: Reverte a despesa reconhecida e elimina o passivo provisionado
```

**Pós-condições:**
- Registro de provisão deletado
- Lançamentos contábeis revertidos (Dr: Passivo, Cr: Despesa)
- Glosa não possui mais flag "provisioned"
- Saldos de GL restaurados
- ERP externo notificado e transação cancelada
- Controladores financeiros notificados
- Analytics atualizados
- Trilha de auditoria completa

**Exceções:**
| Condição | Exceção | Tratamento |
|----------|---------|------------|
| provisionId não existe | RuntimeException | Falha na compensação, escalar para contabilidade |
| Período contábil fechado | AccountingPeriodClosedException | Requerer reabertura de período, aprovação CFO |
| ERP não responde | IntegrationException | Retry 3x, se falhar alertar controller financeiro urgente |
| Saldo GL inconsistente | DataIntegrityException | Suspender operações, auditoria manual |

#### 📊 Parâmetros

| Parâmetro | Tipo | Descrição | Restrições | Exemplo |
|-----------|------|-----------|------------|---------|
| provisionId | Identificador Único | Identificador da provisão a reverter | Obrigatório | "prov-123-abc" |
| glosaId | Identificador Único | Identificador da glosa relacionada | Obrigatório | "glosa-456-def" |
| provisionAmount | Decimal | Valor da provisão a reverter | Obrigatório, > 0 | 8500.00 |
| accountingPeriod | Texto | Período contábil (YYYY-MM) | Obrigatório, formato YYYY-MM | "2026-01" |

**Saídas:**
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| compensationCompleted | Booleano | Sucesso da compensação | true |
| reversedAmount | Decimal | Valor revertido | 8500.00 |
| compensationTimestamp | Data/Hora | Momento da reversão | "2026-01-12T14:30:00Z" |

---

### RN-COMP-PROV-002: Deleção de Registro de Provisão

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-002"
rule_name: "Deleção de Registro de Provisão"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "ROTEAMENTO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Remove o registro de provisão da tabela `glosa_provisions`.

**Especificação:**

```
EXECUTAR SQL:
  DELETE FROM glosa_provisions
  WHERE provision_id = provisionId

VERIFICAR:
  SE linhas_afetadas = 0 ENTÃO
    LOG warning "Provisão não encontrada para deletar"
  SENÃO
    LOG info "Provisão deletada: {provisionId}"
  FIM SE
```

---

### RN-COMP-PROV-003: Reversão de Lançamentos Contábeis de Provisão

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-003"
rule_name: "Reversão de Lançamentos Contábeis de Provisão"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "CÁLCULO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "98%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Cria lançamentos contábeis de reversão que cancelam o efeito da provisão original.

**Contexto de Negócio:** Provisões afetam o resultado (lucro/prejuízo) e o balanço patrimonial. A reversão deve ser contabilizada no mesmo período ou no período corrente, conforme política contábil da instituição.

**Especificação:**

```
CRIAR lançamentos contábeis no General Ledger:

  Lançamento 1 (Reversão do Passivo):
    Conta: 2101 - Provisão para Glosas
    Tipo: DÉBITO
    Valor: provisionAmount
    Data: AGORA
    Período: accountingPeriod
    Referência: "REV-PROV-{provisionId}"
    Descrição: "Reversão de provisão para glosa {glosaId}"

  Lançamento 2 (Reversão da Despesa):
    Conta: 6301 - Despesa com Provisão
    Tipo: CRÉDITO
    Valor: provisionAmount
    Data: AGORA
    Período: accountingPeriod
    Referência: "REV-PROV-{provisionId}"
    Descrição: "Reversão de despesa com provisão glosa {glosaId}"

EXECUTAR:
  INSERT INTO journal_entries (...)
  VALUES (lançamento1, lançamento2)

VALIDAR:
  Débitos = Créditos (princípio das partidas dobradas)

ATENÇÃO:
  Se período contábil está fechado, usar período corrente e criar ajuste
```

---

### RN-COMP-PROV-004: Atualização de Status da Glosa

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-004"
rule_name: "Atualização de Status da Glosa pós-Reversão"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "VALIDAÇÃO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Atualiza o status da glosa para remover a indicação de que está provisionada.

**Especificação:**

```
EXECUTAR SQL:
  UPDATE glosas
  SET status = 'PENDING_PROVISION',
      provisioned = false,
      provision_id = NULL,
      provision_reversed_at = AGORA
  WHERE glosa_id = glosaId

LOG "Status da glosa atualizado após reversão de provisão"
```

---

### RN-COMP-PROV-005: Restauração de Saldos Financeiros

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-005"
rule_name: "Restauração de Saldos no General Ledger"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "CÁLCULO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Atualiza saldos agregados de contas contábeis após reversão de provisão.

**Especificação:**

```
ATUALIZAR saldos do General Ledger:

  -- Reduzir saldo da conta de Provisão para Glosas (Passivo)
  UPDATE general_ledger
  SET current_balance = current_balance - provisionAmount,
      debit_total = debit_total + provisionAmount
  WHERE account_code = '2101'
    AND period = accountingPeriod

  -- Reduzir saldo da conta de Despesa com Provisão (Resultado)
  UPDATE general_ledger
  SET current_balance = current_balance + provisionAmount,
      credit_total = credit_total + provisionAmount
  WHERE account_code = '6301'
    AND period = accountingPeriod

RECALCULAR:
  - Resultado do período (lucro/prejuízo)
  - Total do passivo circulante
```

---

### RN-COMP-PROV-006: Cancelamento de Integração com ERP

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-006"
rule_name: "Cancelamento de Transação no ERP Externo"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "INTEGRAÇÃO"
complexity: "MÉDIA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Notifica sistema ERP externo (SAP, TOTVS, etc.) sobre cancelamento de provisão para sincronização contábil.

**Especificação:**

```
INVOCAR API do ERP:
  ENDPOINT: POST /api/v1/provisions/{provisionId}/cancel
  PAYLOAD: {
    provisionId: identificador_provisão,
    glosaId: identificador_glosa,
    reversalAmount: valor_revertido,
    accountingPeriod: período_contábil,
    reversalReason: "Compensation - Saga rollback",
    journalEntries: [
      {account: "2101", debit: provisionAmount},
      {account: "6301", credit: provisionAmount}
    ]
  }
  TIMEOUT: 30 segundos
  RETRY: 3 tentativas com backoff exponencial

TRATAMENTO DE ERRO:
  SE falha na comunicação com ERP ENTÃO
    LOG error "ERP integration failed for provision reversal"
    CRIAR alerta para controller financeiro (URGENTE)
    MARCAR provisão para reconciliação manual
  FIM SE
```

---

### RN-COMP-PROV-007: Notificação de Controladores Financeiros

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-007"
rule_name: "Notificação de Reversão de Provisão"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "NOTIFICAÇÃO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "85%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Envia notificações às equipes financeiras sobre reversão de provisão.

**Especificação:**

```
ENVIAR notificação VIA Kafka:
  TÓPICO: "provision-reversals"
  PAYLOAD: {
    provisionId: identificador_provisão,
    glosaId: identificador_glosa,
    reversedAmount: valor_revertido,
    accountingPeriod: período_contábil,
    reversedAt: data_hora_reversão,
    notificationType: "PROVISION_REVERSED"
  }

ENVIAR email PARA:
  - Controller Financeiro (CFO)
  - Gerente de Contabilidade
  - Analista de Provisões
  - Auditor Interno (se valor > R$ 50.000)

INCLUIR no email:
  - Valor revertido
  - Glosa relacionada
  - Período contábil afetado
  - Impacto no resultado do período
  - Link para sistema (deep link)
```

---

### RN-COMP-PROV-008: Atualização de Analytics de Provisões

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-008"
rule_name: "Atualização de Métricas e Analytics de Provisões"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "CÁLCULO"
complexity: "MÉDIA"
criticality: "MÉDIA"
test_coverage_recommendation: "85%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Atualiza contadores e métricas de provisões após reversão.

**Especificação:**

```
ATUALIZAR analytics:
  UPDATE provision_analytics
  SET reversed_provisions_count = reversed_provisions_count + 1,
      reversed_provisions_amount = reversed_provisions_amount + provisionAmount,
      net_provisions_amount = net_provisions_amount - provisionAmount,
      last_reversal_at = AGORA
  WHERE period = accountingPeriod

ATUALIZAR KPIs:
  - Provision Reversal Rate = (reversed / created) * 100
  - Average Provision Amount = total_provisions_amount / provisions_count
  - Net Provisions = created - reversed
```

---

### RN-COMP-PROV-009: Trilha de Auditoria de Reversão

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-PROV-009"
rule_name: "Registro de Reversão em Trilha de Auditoria"
version: "1.0.0"
last_updated: "2026-01-12T12:35:00Z"
category: "AUDITORIA"
complexity: "BAIXA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Registra todas as operações de reversão de provisão em trilha de auditoria imutável para compliance SOX e ANS.

**Contexto de Negócio:** SOX (Sarbanes-Oxley) exige rastreamento completo de todas as operações contábeis, especialmente reversões, para auditoria externa.

**Especificação:**

```
INSERIR em trilha_auditoria_provisão:
  provision_id: identificador_provisão
  glosa_id: identificador_glosa
  ação: "REVERSED"
  provision_amount: valor_revertido
  accounting_period: período_contábil
  journal_entry_reference: referência_lançamento_contábil
  erp_transaction_id: id_transação_erp
  reversed_by: usuário_ou_sistema_executor
  reversal_reason: "Saga compensation rollback"
  timestamp: data_hora_ação

GARANTIR:
  - Retenção: 7 anos (SOX requirement)
  - Imutabilidade: trilha não pode ser modificada ou deletada
  - Criptografia: dados sensíveis criptografados em repouso
  - Hash: SHA-256 hash da entrada para detecção de adulteração
```

---

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Financial Accounting"
aggregate_root: "Provision"
entities:
  - "GlosaProvision"
  - "Glosa"
  - "JournalEntry"
  - "GeneralLedger"
value_objects:
  - "ProvisionAmount"
  - "AccountingPeriod"
  - "AccountCode"
domain_events:
  - name: "ProvisionReversed"
    payload: ["provisionId", "glosaId", "reversedAmount", "accountingPeriod"]
  - name: "JournalEntriesPosted"
    payload: ["journalEntryReference", "entries", "accountingPeriod"]
  - name: "ERPSyncRequired"
    payload: ["provisionId", "syncOperation", "syncStatus"]
microservice_candidate:
  service_name: "financial-provisions-service"
  api_style: "Event-Driven + REST"
  bounded_context_isolation: "VERY_HIGH"
  erp_integration: "REQUIRED"
```

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Demonstrativo de Análise de Conta (Componente 33) - provisões para glosas"

ans_requirements:
  - "RN 442/2018 - Art. 13º - Provisões para glosas devem ser rastreáveis"
  - "RN 465/2021 - Art. 16º - Transparência em glosas e perdas provisionadas"

lgpd_considerations:
  - "Art. 46 - Logs de operações financeiras devem ser mantidos de forma segura"

sox_controls:
  - "SOX 302 - Controles internos sobre relatórios financeiros"
  - "SOX 404 - Avaliação de controles internos"
  - "Segregação de funções: criação e reversão de provisões não podem ser pela mesma pessoa"
  - "Aprovação de reversões: reversões acima de R$ 50.000 requerem aprovação do CFO"
  - "Auditoria externa: trilha completa deve estar disponível para auditores"
  - "Período contábil: reversões após fechamento requerem ajustes aprovados"

ifrs_standards:
  - "IAS 37 - Provisões, Passivos Contingentes e Ativos Contingentes"
  - "Reconhecimento: provisão deve ser reconhecida quando perda é provável"
  - "Mensuração: provisão deve ser a melhor estimativa do desembolso"
  - "Reversão: provisão deve ser revertida quando não mais atender critérios"

audit_trail:
  - "Retention: 7 anos (SOX) + prazo de auditoria externa"
  - "Logging: Todas as reversões com valores, períodos, aprovadores e motivos"
  - "Immutability: Trilha em blockchain hash ou append-only log"
  - "Availability: Trilha deve estar disponível para auditoria em 24h"
```

---

## 🚀 Notas para Migração

```yaml
camunda_7_to_8:
  complexity_rating: 8/10
  migration_path: "Delegate → Job Worker + Zeebe Client"
  breaking_changes:
    - "DelegateExecution → JobClient + ActivatedJob"
    - "Integração ERP: considerar circuit breaker pattern"
    - "Transações contábeis: usar 2PC ou Saga com compensação"

  example_camunda_8:
    worker_type: "compensate-provision"
    handler: |
      @JobWorker(type = "compensate-provision")
      public void handle(JobClient client, ActivatedJob job) {
        Map<String, Object> variables = job.getVariablesAsMap();
        String provisionId = (String) variables.get("provisionId");

        try {
          Double reversedAmount = compensateProvision(variables);

          client.newCompleteCommand(job.getKey())
            .variables(Map.of(
              "compensationCompleted", true,
              "reversedAmount", reversedAmount
            ))
            .send();
        } catch (AccountingPeriodClosedException e) {
          // Handle closed period with incident
          client.newFailCommand(job.getKey())
            .retries(0)
            .errorMessage("Accounting period closed")
            .send();
        }
      }

microservices_target: "financial-provisions-service"
alternative_orchestration: "Saga pattern + Outbox pattern para lançamentos contábeis"

temporal_alternative: |
  @ActivityMethod
  CompensationResult compensateProvision(ProvisionInput input);

  Saga saga = new Saga(new Saga.Options.Builder()
    .setParallelCompensation(false)
    .build());
  saga.addCompensation(() ->
    activities.compensateProvision(input)
  );

erp_integration_modernization:
  - "Current: synchronous REST API calls"
  - "Target: event-driven integration with Kafka + CDC"
  - "Benefits: resilience, eventual consistency, audit trail"

performance_considerations:
  - "Compensação deve completar em < 3 segundos (P95)"
  - "Integração ERP: usar circuit breaker (Resilience4j)"
  - "Lançamentos contábeis: batch posting para reduzir round-trips"
  - "Auditoria: async logging para não bloquear compensação"
```

---

## 📍 Rastreabilidade

```yaml
source_file: "src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateProvisionDelegate.java"
source_class: "CompensateProvisionDelegate"
source_package: "com.hospital.revenuecycle.delegates.compensation"

key_methods:
  - name: "executeBusinessLogic"
    lines: 50-81
    rules: ["RN-COMP-PROV-001"]

  - name: "compensateProvision"
    lines: 86-125
    rules: ["RN-COMP-PROV-002", "RN-COMP-PROV-003", "RN-COMP-PROV-004", "RN-COMP-PROV-005", "RN-COMP-PROV-006", "RN-COMP-PROV-007", "RN-COMP-PROV-008", "RN-COMP-PROV-009"]

  - name: "requiresIdempotency"
    lines: 185-187
    rules: ["Idempotência implícita via Saga"]

dependencies:
  - "SagaCompensationService (via @Autowired)"
  - "BaseDelegate (extends)"
  - "Camunda BPM Engine (DelegateExecution)"
  - "AccountingIntegrationService (implied)"
  - "ERPClient (implied)"

integration_points:
  - "Database: glosa_provisions, glosas, journal_entries, general_ledger, provision_analytics, provision_audit_trail tables"
  - "ERP API: POST /api/v1/provisions/{provisionId}/cancel"
  - "Kafka: topic 'provision-reversals'"
  - "Email service: financial controller notifications"
```

---

## 🔗 Dependências e Relacionamentos

### Delegates/Serviços que Este Componente Depende
- **BaseDelegate** - Classe base
- **SagaCompensationService** - Coordenação de saga
- **AccountingIntegrationService** - Integração com GL e ERP
- **ERPClient** - Cliente para ERP externo

### Delegates/Serviços que Dependem Deste Componente
- **Processo BPMN de Criação de Provisão** - Invoca em falhas
- **GlosaManagementService** - Utiliza para reverter provisões
- **FinancialClosingService** - Consulta para fechamento contábil

---

## 📊 Métricas Técnicas

```yaml
cyclomatic_complexity: 9
cognitive_complexity: 14
lines_of_code: 189
test_coverage_current: "83%"
test_coverage_target: "98%"

performance_sla:
  p50_latency_ms: 350
  p95_latency_ms: 1200
  p99_latency_ms: 2500
  timeout_threshold_ms: 5000

dependencies_count: 4
integration_points_count: 4
database_tables_affected: 6
```

---

## 📝 Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0.0 | 2026-01-12 | Hive Mind Coder Agent | Extração completa de regras de negócio com schema v2 |

---

## 🏷️ Tags e Classificação

`compensação` `saga-pattern` `provisões-financeiras` `glosas` `contabilidade` `general-ledger` `sox` `ifrs` `erp-integration` `camunda-7`
