# Regras de Negócio: VerifyPatientEligibilityDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/eligibility/VerifyPatientEligibilityDelegate.java`
> **Categoria:** ELIGIBILITY (Elegibilidade)
> **Total de Regras:** 9

## 📋 Sumário Executivo

O delegate VerifyPatientEligibilityDelegate é responsável por verificar a elegibilidade de pacientes para serviços de saúde através de tabela de decisão DMN (eligibility-verification.dmn). Esta verificação considera múltiplos fatores como tipo de convênio, status de cobertura, situação de emergência e status contratual para determinar se o paciente pode receber atendimento.

O processo utiliza regras de negócio parametrizadas através de DMN, permitindo separação clara entre lógica de decisão e código Java. Casos de emergência recebem tratamento prioritário, sendo sempre considerados elegíveis independentemente do status do convênio, conforme regulamentação hospitalar brasileira.

## 📜 Catálogo de Regras

### RN-ELG-VER-001: Validação de ID do Paciente

**Descrição:** Garante que o identificador do paciente está presente e válido antes de prosseguir com a verificação de elegibilidade.

**Lógica:**
```
SE patientId é nulo OU patientId.trim() está vazio
ENTÃO lançar BpmnError "ELIGIBILITY_FAILED"
  - Mensagem: "Patient ID is required"
SENÃO prosseguir com verificação
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| patientId | String | Obrigatório, não-vazio após trim | "PAC-98765" |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: executeBusinessLogic
- Linhas: 99-101

---

### RN-ELG-VER-002: Validação de ID do Convênio

**Descrição:** Garante que o identificador do convênio/plano de saúde está presente antes da verificação.

**Lógica:**
```
SE insuranceId é nulo OU insuranceId.trim() está vazio
ENTÃO lançar BpmnError "ELIGIBILITY_FAILED"
  - Mensagem: "Insurance ID is required"
SENÃO prosseguir com verificação
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| insuranceId | String | Obrigatório, não-vazio após trim | "SUS-12345" |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: executeBusinessLogic
- Linhas: 103-105

---

### RN-ELG-VER-003: Classificação de Tipo de Convênio

**Descrição:** Determina o tipo de convênio baseado no padrão do ID do convênio para aplicação de regras específicas.

**Lógica:**
```
SE insuranceId começa com "SUS"
  ENTÃO insuranceType = "SUS"
SENÃO SE insuranceId começa com "PART"
  ENTÃO insuranceType = "PARTICULAR"
SENÃO SE insuranceId começa com "CONV"
  ENTÃO insuranceType = "CONVENIO_EMPRESA"
SENÃO SE insuranceId começa com "INT"
  ENTÃO insuranceType = "INTERNACIONAL"
SENÃO
  insuranceType = "PLANO_SAUDE"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| insuranceId | String | Padrão de prefixo | "SUS-12345" |
| insuranceType | String | Enum de tipos | "SUS" |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: getInsuranceType
- Linhas: 173-186

---

### RN-ELG-VER-004: Verificação de Status de Cobertura

**Descrição:** Consulta o status atual da cobertura do convênio (ativo, suspenso, expirado, pendente, bloqueado).

**Lógica:**
```
CONSULTAR insurance_coverage table
  - Buscar por insuranceId
  - Verificar data de validade
  - Verificar status de pagamento
RETORNAR coverageStatus: ACTIVE | SUSPENDED | EXPIRED | PENDING | BLOCKED
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| insuranceId | String | Deve existir no banco | "CONV-UNIMED-001" |
| coverageStatus | String | Enum de status | "ACTIVE" |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: getCoverageStatus
- Linhas: 195-199

---

### RN-ELG-VER-005: Verificação de Contrato Ativo

**Descrição:** Valida se existe contrato ativo entre o hospital e o convênio na data atual.

**Lógica:**
```
CONSULTAR contracts table
  - Buscar por insuranceId
  - Verificar data de início <= hoje
  - Verificar data de término >= hoje
  - Verificar status do contrato = ACTIVE
RETORNAR hasActiveContract: true | false
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| insuranceId | String | Deve existir no banco | "PLANO-BRADESCO-001" |
| hasActiveContract | Boolean | Resultado da validação | true |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: checkActiveContract
- Linhas: 208-212

---

### RN-ELG-VER-006: Avaliação DMN de Elegibilidade

**Descrição:** Executa tabela de decisão DMN para determinar elegibilidade com base em múltiplos critérios combinados.

**Lógica:**
```
EXECUTAR DMN "eligibility-verification" com inputs:
  - insuranceType: Tipo do convênio
  - coverageStatus: Status da cobertura
  - isEmergency: Flag de emergência
  - hasActiveContract: Status do contrato

RETORNAR outputs DMN:
  - eligible: Boolean (paciente elegível?)
  - reason: String (motivo da decisão)
  - priority: Integer 1-5 (prioridade do atendimento)
  - requiresManualReview: Boolean (requer revisão manual?)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| insuranceType | String | SUS, PARTICULAR, etc. | "PLANO_SAUDE" |
| coverageStatus | String | ACTIVE, SUSPENDED, etc. | "ACTIVE" |
| isEmergency | Boolean | Opcional, padrão false | true |
| hasActiveContract | Boolean | Obrigatório | true |

**Fórmula DMN:** Definida em eligibility-verification.dmn (tabela de decisão externa)

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: executeBusinessLogic
- Linhas: 113-130

---

### RN-ELG-VER-007: Regra de Emergência Prioritária

**Descrição:** Casos de emergência são sempre considerados elegíveis, independentemente do status do convênio, conforme legislação hospitalar brasileira.

**Lógica:**
```
SE isEmergency = true
ENTÃO DMN retorna:
  - eligible = true
  - priority = 1 (máxima prioridade)
  - reason = "EMERGENCY_OVERRIDE"
  - requiresManualReview = false
INDEPENDENTE de coverageStatus ou hasActiveContract
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| isEmergency | Boolean | Opcional, padrão false | true |
| priority | Integer | 1-5, emergência sempre 1 | 1 |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Comentários: Linhas 58-60
- Avaliação: evaluateDMN (linha 124)

---

### RN-ELG-VER-008: Falha de Elegibilidade com Tratamento de Exceções

**Descrição:** Quando paciente não é elegível e não requer revisão manual, processo é interrompido com erro BPMN para tratamento no fluxo.

**Lógica:**
```
SE eligible = false E requiresManualReview = false
ENTÃO lançar BpmnError "ELIGIBILITY_FAILED"
  - Incluir motivo (reason) na mensagem
  - Registrar log de aviso
  - Interromper fluxo de atendimento
SENÃO prosseguir (elegível OU requer revisão manual)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| eligible | Boolean | Output do DMN | false |
| requiresManualReview | Boolean | Output do DMN | false |
| reason | String | Código do motivo | "COVERAGE_EXPIRED" |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: executeBusinessLogic
- Linhas: 142-146

---

### RN-ELG-VER-009: Armazenamento de Decisão de Elegibilidade

**Descrição:** Persiste todas as variáveis de decisão de elegibilidade em escopo PROCESS para uso por outros delegates (autorização, faturamento).

**Lógica:**
```
SEMPRE armazenar após avaliação DMN:
  - patientEligible: Resultado da elegibilidade
  - eligibilityReason: Código do motivo
  - eligibilityPriority: Nível de prioridade (1-5)
  - requiresManualReview: Flag de revisão manual
EM ESCOPO: PROCESS (compartilhado com orchestrator)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| patientEligible | Boolean | Escopo: Process | true |
| eligibilityReason | String | Escopo: Process | "ACTIVE_COVERAGE" |
| eligibilityPriority | Integer | 1-5, Escopo: Process | 3 |
| requiresManualReview | Boolean | Escopo: Process | false |

**Rastreabilidade:**
- Arquivo: VerifyPatientEligibilityDelegate.java
- Método: executeBusinessLogic
- Linhas: 136-139

---

## 📊 Métricas e Monitoramento

**Operação:** verify_patient_eligibility
**Idempotência:** Sim (via BaseDelegate)
**Escopo de Variáveis:** PROCESS (compartilhadas com authorization e billing)
**DMN:** eligibility-verification.dmn

## 🔗 Integrações

- **DMN Engine:** Camunda Decision Engine para avaliação de regras
- **Insurance Plans DB:** Consulta de tipos de convênio
- **Insurance Coverage DB:** Validação de status de cobertura
- **Contracts DB:** Verificação de contratos ativos
- **BPMN Process:** Gera erro "ELIGIBILITY_FAILED" para casos não elegíveis

## 📝 Observações Técnicas

1. **Prioridade de Emergência:** Casos de emergência sempre têm prioridade 1 e são elegíveis
2. **DMN Separation:** Lógica de decisão está em arquivo DMN externo para fácil manutenção
3. **Mock Implementation:** Métodos getInsuranceType, getCoverageStatus e checkActiveContract são mocks que devem ser substituídos por queries reais em produção
4. **Revisão Manual:** Casos edge podem ser marcados para revisão manual sem bloquear o fluxo
5. **Conformidade Legal:** Implementação segue ADR-003 e processo SUB_02 Pre-Attendance

---

## X. Conformidade Regulatória

### Normativas ANS
- **RN 389/2015:** Diretrizes para verificação de elegibilidade (Arts. 8-11)
- **RN 453/2020:** Regras de carência e cobertura parcial temporária
- **RN 470/2021:** Portabilidade de carências entre operadoras
- **RN 520/2022:** Prazos para atendimento e urgência/emergência

### Lei 9.656/1998 (Lei dos Planos de Saúde)
- **Art. 12, V:** Carências máximas para procedimentos
- **Art. 35-C, §1º:** Urgência e emergência (até 24h de carência)
- **Art. 35-E:** Suspensão de pagamento e perda de elegibilidade
- **Art. 35-F, §2º:** Reativação de contrato suspenso

### Padrão TISS (Versão 4.02.02)
- **Componente:** Guia de Consulta / SP/SADT
- **Campo 13:** Número da carteirinha do beneficiário
- **Campo 14:** Validade da carteirinha
- **Campo 16:** Nome do contratado (operadora)
- **Validação:** Elegibilidade antes da geração de guia

### LGPD (Lei 13.709/2018)
- **Art. 7º, I:** Consentimento para processamento de dados de elegibilidade
- **Art. 11, II, 'a':** Dados sensíveis de saúde - verificação de status
- **Art. 18, I:** Confirmação de existência de tratamento de dados
- **Art. 20:** Revisão de decisões automatizadas de elegibilidade

### SOX (Sarbanes-Oxley)
- **Section 302:** Controles internos para verificação de receita
- **Section 404:** Auditoria de processos de elegibilidade
- **Section 409:** Divulgação de mudanças em estimativas de receita

### Código de Defesa do Consumidor (CDC)
- **Art. 6º, III:** Informação adequada sobre elegibilidade
- **Art. 39, IX:** Recusa de atendimento sem justa causa
- **Art. 51, IV:** Cláusulas que restrinjam direitos indevidamente

---

## XI. Notas de Migração

### Complexidade de Migração
**Rating:** 🟡 MÉDIO (5/10)

**Justificativa:**
- Integração com DMN já projetada (eligibility-verification.dmn)
- Regras de negócio estáveis (carência, cobertura, emergência)
- Dependência de múltiplas fontes de dados (Insurance Plans, Coverage, Contracts)

### Mudanças Incompatíveis (Breaking Changes)
1. **DMN External:** Lógica de decisão migrada para eligibility-verification.dmn
2. **Mock Replacement:** getInsuranceType, getCoverageStatus, checkActiveContract requerem implementação real
3. **Emergency Override:** Novos campos isEmergency e priority nas variáveis de processo
4. **BpmnError Code:** "ELIGIBILITY_FAILED" substituindo erros genéricos

### Migração para DMN
**Candidato:** ✅ SIM (JÁ INICIADO)

```yaml
dmn_migration:
  dmn_file: "eligibility-verification.dmn"

  decision_tables:
    - decision_id: "eligibility-check"
      decision_name: "Verificação de Elegibilidade de Paciente"
      inputs:
        - insuranceType: String
        - coverageStatus: String (ACTIVE/SUSPENDED/CANCELLED)
        - hasActiveContract: Boolean
        - isEmergency: Boolean
      outputs:
        - isEligible: Boolean
        - priority: Integer (1-3)
        - requiresManualReview: Boolean
      rules:
        - "Emergência = Sempre elegível (prioridade 1)"
        - "HMO + ACTIVE + Contrato = Elegível (prioridade 2)"
        - "PPO + ACTIVE + Contrato = Elegível (prioridade 3)"
        - "SUSPENDED/CANCELLED = Não elegível"

    - decision_id: "carencia-check"
      decision_name: "Verificação de Carência"
      inputs:
        - procedureType: String
        - contractStartDate: Date
        - serviceDate: Date
        - isUrgency: Boolean
      outputs:
        - carenciaAtendida: Boolean
        - diasRestantes: Integer
      rules:
        - "Urgência/Emergência = Carência máxima 24h"
        - "Consultas = Carência 30 dias"
        - "Exames = Carência 180 dias"
        - "Cirurgias = Carência 300 dias"
```

### Fases de Implementação
**Fase 1 - DMN Integration (Sprint 6):**
- Implementar VerifyPatientEligibilityDelegate
- Integração com Camunda Decision Engine
- Variáveis de processo e error handling

**Fase 2 - Database Queries (Sprint 7):**
- Substituir mocks por queries reais
- Integração com Insurance Plans DB
- Coverage Status e Active Contracts

**Fase 3 - Advanced Features (Sprint 8):**
- Carência e cobertura parcial temporária
- Portabilidade de carências
- Dashboard de elegibilidade

### Dependências Críticas
```yaml
dependencies:
  dmn_files:
    - eligibility-verification.dmn  # Decision table
    - carencia-validation.dmn       # Carência rules

  databases:
    - insurance_plans               # Tipos de plano (HMO/PPO/POS)
    - insurance_coverage            # Status de cobertura
    - contracts                     # Contratos ativos
    - carencia_rules                # Regras de carência por procedimento

  external_services:
    - ANS Operadoras API            # Validação de operadora
    - SIB (Sistema de Informações de Beneficiários)
```

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Contexto:** Patient Eligibility & Pre-Authorization Management

**Subdomínio:** Eligibility Verification (Core Domain)

**Responsabilidades:**
- Verificação de elegibilidade de paciente para atendimento
- Validação de status de cobertura e contrato ativo
- Determinação de prioridade de atendimento (emergência/urgência)

### Aggregates e Entidades

```yaml
aggregate: PatientEligibility
  root_entity: EligibilityVerificationResult
    properties:
      - verificationId: UUID
      - patientId: UUID
      - insurancePlanId: UUID
      - verifiedAt: Instant
      - isEligible: Boolean
      - priority: Integer (1-3)
      - requiresManualReview: Boolean

  value_objects:
    - InsuranceDetails:
        - insuranceType: InsuranceType (HMO/PPO/POS)
        - coverageStatus: CoverageStatus (ACTIVE/SUSPENDED/CANCELLED)
        - contractStartDate: LocalDate
        - hasActiveContract: Boolean

    - VerificationContext:
        - isEmergency: Boolean
        - isUrgency: Boolean
        - serviceDate: LocalDate
        - serviceType: ServiceType

  entities:
    - EligibilityHistory:
        - historyId: UUID
        - verificationId: UUID (FK)
        - previousStatus: Boolean
        - statusChangeReason: String
        - changedAt: Instant
```

### Domain Events

```json
{
  "domain_events": [
    {
      "event": "PatientEligibilityVerified",
      "triggers": ["Elegibilidade confirmada"],
      "payload": {
        "verificationId": "uuid",
        "patientId": "uuid",
        "isEligible": "boolean",
        "priority": "integer"
      },
      "subscribers": [
        "AuthorizationService",
        "SchedulingService",
        "BillingService"
      ]
    },
    {
      "event": "EligibilityCheckFailed",
      "triggers": ["Paciente não elegível"],
      "payload": {
        "verificationId": "uuid",
        "failureReason": "string",
        "coverageStatus": "enum"
      },
      "subscribers": [
        "PatientNotificationService",
        "FrontDeskAlert"
      ]
    },
    {
      "event": "ManualReviewRequired",
      "triggers": ["Caso edge detectado"],
      "payload": {
        "verificationId": "uuid",
        "reviewReason": "string"
      },
      "subscribers": [
        "CaseManagementQueue",
        "UtilizationManagement"
      ]
    },
    {
      "event": "EmergencyOverride",
      "triggers": ["Caso de emergência"],
      "payload": {
        "verificationId": "uuid",
        "patientId": "uuid",
        "overrideJustification": "string"
      },
      "subscribers": [
        "EmergencyDepartment",
        "AuditService"
      ]
    }
  ]
}
```

### Invariantes do Domínio
1. **Emergency Override:** Casos de emergência são SEMPRE elegíveis (prioridade 1)
2. **Active Contract:** Elegibilidade requer contrato ativo (exceto emergência)
3. **Coverage Status:** ACTIVE ou SUSPENDED com justificativa
4. **Priority Levels:** 1 (Emergência) > 2 (Urgência) > 3 (Eletivo)

### Viabilidade para Microserviço
**Candidato:** ✅ SIM

**Justificativa:**
- Responsabilidade clara: verificação de elegibilidade
- Alto volume de consultas (escalabilidade importante)
- Estado isolado (Insurance Plans, Coverage, Contracts)
- Comunicação via eventos (PatientEligibilityVerified)

**Integração:**
```yaml
microservice: eligibility-verification-service
  api:
    - POST /eligibility/verify
    - GET /eligibility/history/{patientId}
    - GET /eligibility/{verificationId}

  events_published:
    - PatientEligibilityVerified
    - EligibilityCheckFailed
    - ManualReviewRequired
    - EmergencyOverride

  events_subscribed:
    - PatientRegistered (from PatientService)
    - CoverageUpdated (from InsuranceService)
    - ContractActivated (from ContractsService)

  dmn_decisions:
    - eligibility-verification.dmn
    - carencia-validation.dmn
```

---

## XIII. Metadados Técnicos

### Complexidade e Esforço

```yaml
complexity_metrics:
  cyclomatic_complexity: 10  # Médio
  cognitive_complexity: 15   # Médio
  lines_of_code: ~300

  time_estimates:
    implementation: 3 dias
    testing: 2 dias
    dmn_integration: 2 dias
    database_queries: 1 dia
    documentation: 1 dia
    total: 9 dias (~1.5 sprints)
```

### Cobertura de Testes

```yaml
test_coverage_targets:
  unit_tests: 90%
  integration_tests: 80%

  critical_test_scenarios:
    - eligibility_verified_success
    - eligibility_check_failed
    - emergency_override
    - manual_review_required
    - dmn_decision_integration
    - active_contract_validation
    - coverage_status_suspended
    - hmo_vs_ppo_eligibility
    - priority_assignment
    - carencia_validation
```

### Performance e SLA

```yaml
performance_requirements:
  eligibility_check_latency: <200ms (p95)
  dmn_evaluation_time: <50ms
  database_query_time: <100ms

  availability: 99.9% (crítico para admissão)

  resource_limits:
    cpu: 1 core
    memory: 2 GB
    dmn_cache: 100 MB
```

### Dependências e Integrações

```yaml
dependencies:
  internal_services:
    - PatientService (dados demográficos)
    - InsuranceService (planos e cobertura)
    - ContractsService (contratos ativos)
    - AuthorizationService (fluxo de autorização)

  external_services:
    - ANS Operadoras API (validação de operadora)
    - SIB Sistema (beneficiários)

  databases:
    - eligibility_verifications (PostgreSQL)
    - insurance_plans (PostgreSQL)
    - insurance_coverage (PostgreSQL)
    - contracts (PostgreSQL)

  dmn_engines:
    - camunda_decision_engine (eligibility-verification.dmn)

  message_queues:
    - eligibility_events (Kafka)
```

### Monitoramento e Observabilidade

```yaml
metrics:
  business:
    - eligibility_approval_rate
    - emergency_override_count
    - manual_review_rate
    - priority_distribution (1/2/3)
    - coverage_status_distribution

  technical:
    - eligibility_check_latency_p50_p95_p99
    - dmn_decision_evaluation_time
    - database_query_latency
    - error_rate_by_failure_reason

  alerts:
    - eligibility_approval_rate < 85% (1h window)
    - manual_review_rate > 10% (1h window)
    - eligibility_check_latency_p95 > 300ms
    - dmn_evaluation_timeout > 0 (immediate)
```

---

**Última Atualização:** 2025-01-12
**Versão do Documento:** 2.0
**Status de Conformidade:** ✅ Completo (X-XIII)
