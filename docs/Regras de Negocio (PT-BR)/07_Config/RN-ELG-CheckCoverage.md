# Regras de Negócio: CheckCoverageDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/eligibility/CheckCoverageDelegate.java`
> **Categoria:** ELIGIBILITY (Elegibilidade)
> **Total de Regras:** 4

## 📋 Sumário Executivo

O delegate CheckCoverageDelegate é responsável por verificar a cobertura de procedimentos médicos junto aos convênios e planos de saúde. Esta verificação é crítica para o ciclo de receita hospitalar, pois determina quais procedimentos estão cobertos pelo plano do paciente antes da realização do atendimento, evitando glosas futuras e garantindo o faturamento adequado.

A verificação de cobertura integra-se com sistemas externos de elegibilidade e valida procedimentos contra as regras do convênio em uma data específica de serviço. O processo emite sinais BPMN em caso de falha na verificação, permitindo tratamento adequado no fluxo de processo.

## 📜 Catálogo de Regras

### RN-ELG-CHK-001: Verificação de Cobertura de Procedimentos

**Descrição:** Valida se todos os procedimentos solicitados estão cobertos pelo plano de saúde do paciente na data de serviço especificada.

**Lógica:**
```
SE chamada ao eligibilityService.checkCoverage retorna CoverageCheckResponse
ENTÃO avaliar cobertura:
  - SE notCoveredProcedures está vazio ou nulo
    ENTÃO all_procedures_covered = true
  - SENÃO all_procedures_covered = false
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| patient_id | String | Obrigatório, não-nulo | "PAC-12345" |
| payer_id | String | Obrigatório, não-nulo | "CONV-UNIMED-001" |
| procedure_codes | List&lt;String&gt; | Obrigatório, não-vazio | ["40101010-1", "40201020-2"] |
| service_date | LocalDate | Opcional, padrão hoje | 2025-01-10 |

**Rastreabilidade:**
- Arquivo: CheckCoverageDelegate.java
- Método: executeBusinessLogic
- Linhas: 38-42

---

### RN-ELG-CHK-002: Verificação de Autorização Prévia

**Descrição:** Identifica procedimentos que requerem autorização prévia do convênio antes de serem executados.

**Lógica:**
```
SE CoverageCheckResponse.requiresPriorAuthorization não é nulo E não está vazio
ENTÃO prior_auth_required = true
  - Armazenar lista de procedimentos que necessitam autorização
SENÃO prior_auth_required = false
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| requiresPriorAuthorization | List&lt;String&gt; | Retornado pelo serviço | ["40301030-3"] |

**Rastreabilidade:**
- Arquivo: CheckCoverageDelegate.java
- Método: executeBusinessLogic
- Linhas: 43-44

---

### RN-ELG-CHK-003: Validação de Sucesso da Verificação

**Descrição:** Garante que a verificação de cobertura foi concluída com sucesso antes de prosseguir no fluxo de processo.

**Lógica:**
```
SE CoverageCheckResponse.verificationSuccessful = false
ENTÃO lançar BpmnError "COVERAGE_CHECK_FAILED"
  - Incluir mensagem de erro do serviço
  - Interromper execução do delegate
SENÃO prosseguir com fluxo normal
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| verificationSuccessful | Boolean | Obrigatório | true/false |
| errorMessage | String | Presente se falha | "Sistema de elegibilidade indisponível" |

**Rastreabilidade:**
- Arquivo: CheckCoverageDelegate.java
- Método: executeBusinessLogic
- Linhas: 51-53

---

### RN-ELG-CHK-004: Armazenamento de Procedimentos Cobertos

**Descrição:** Persiste a lista de procedimentos com cobertura confirmada para uso posterior no processo de faturamento.

**Lógica:**
```
SEMPRE executar após verificação bem-sucedida:
  - Armazenar coverage_verified (boolean)
  - Armazenar all_procedures_covered (boolean)
  - Armazenar covered_procedures (lista de códigos)
  - Armazenar prior_auth_required (boolean)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| coverage_verified | Boolean | Escopo: Process | true |
| all_procedures_covered | Boolean | Escopo: Process | true |
| covered_procedures | List&lt;String&gt; | Escopo: Process | ["40101010-1"] |
| prior_auth_required | Boolean | Escopo: Process | false |

**Rastreabilidade:**
- Arquivo: CheckCoverageDelegate.java
- Método: executeBusinessLogic
- Linhas: 46-49

---

## 📊 Métricas e Monitoramento

**Operação:** check_coverage
**Idempotência:** Sim (via BaseDelegate)
**Escopo de Variáveis:** PROCESS (compartilhadas com outros delegates)

## 🔗 Integrações

- **EligibilityVerificationService:** Serviço externo de verificação de elegibilidade
- **Sistema de Convênios:** Consulta de cobertura e regras contratuais
- **BPMN Process:** Gera erro "COVERAGE_CHECK_FAILED" para tratamento no fluxo

## 📝 Observações Técnicas

1. Data de serviço padrão é hoje se não especificada
2. Validação ocorre antes da execução de procedimentos
3. Erros são propagados via BpmnError para controle de fluxo
4. Todas as variáveis são armazenadas em escopo de processo para uso downstream

---

## X. Conformidade Regulatória

### Normativas ANS
- **RN 259/2011:** Regras de cobertura obrigatória para planos de saúde (Arts. 12-16)
- **RN 338/2013:** Rol de procedimentos e eventos em saúde (Anexo I e II)
- **RN 465/2021:** Atualização de coberturas obrigatórias
- **RN 520/2022:** Prazos máximos para atendimento e cobertura

### Lei 9.656/1998 (Lei dos Planos de Saúde)
- **Art. 12:** Cobertura obrigatória de doenças e procedimentos
- **Art. 35-C:** Aplicação de rol de procedimentos da ANS
- **Art. 35-E:** Reajustes e variações de contraprestação
- **Art. 35-F:** Suspensão ou rescisão unilateral do contrato

### Padrão TISS (Versão 4.02.02)
- **Componente:** Guia de Consulta / SP/SADT
- **Campo 30:** Indicação de acidente (trabalho/trânsito)
- **Campo 46:** Tabela de procedimentos solicitados
- **Validação:** Cobertura contratual antes da execução

### LGPD (Lei 13.709/2018)
- **Art. 7º, I:** Consentimento para processamento de dados de saúde
- **Art. 11, II, 'f':** Tutela da saúde - verificação de cobertura
- **Art. 20, §2º:** Revisão de decisões automatizadas (rejeição de cobertura)

### SOX (Sarbanes-Oxley)
- **Section 302:** Controles internos para provisionamento de cobertura
- **Section 404:** Auditoria de processos de elegibilidade
- **Section 409:** Divulgação tempestiva de alterações contratuais

### Código de Defesa do Consumidor (CDC)
- **Art. 51, IV:** Cláusulas abusivas que restrinjam direitos
- **Art. 54, §4º:** Transparência nas cláusulas limitativas de cobertura

---

## XI. Notas de Migração

### Complexidade de Migração
**Rating:** 🟢 BAIXA (4/10)

**Justificativa:**
- Regras de negócio bem definidas (contratos de convênio)
- Integração com sistemas externos existentes (EligibilityVerificationService)
- Estado stateless (validação on-demand)

### Mudanças Incompatíveis (Breaking Changes)
1. **Campo serviceDate:** Novo campo obrigatório (default: hoje)
2. **Retorno coverageDetails:** Estrutura JSON estendida
3. **Variáveis de Processo:** Novas variáveis no escopo PROCESS
4. **BpmnError Code:** "COVERAGE_CHECK_FAILED" substituindo erros genéricos

### Migração para DMN
**Candidato:** ⚠️ PARCIAL

```yaml
dmn_migration:
  candidate_decisions:
    - decision_id: "coverage-validation"
      decision_name: "Validação de Cobertura Contratual"
      inputs:
        - insurancePlanId: String
        - procedureCode: String
        - serviceDate: Date
        - patientAge: Integer
      outputs:
        - isCovered: Boolean
        - coveragePercentage: Float
        - requiresAuthorization: Boolean

    - decision_id: "special-coverage-rules"
      decision_name: "Regras Especiais de Cobertura"
      inputs:
        - procedureType: String
        - patientCondition: String
        - urgency: Boolean
      outputs:
        - coverageOverride: Boolean
        - justification: String

  non_migratable:
    - external_api_call  # EligibilityVerificationService
    - real_time_contract_lookup  # Sistema de Convênios
```

### Fases de Implementação
**Fase 1 - Core Validation (Sprint 6):**
- Implementar CheckCoverageDelegate
- Integração com EligibilityVerificationService
- Variáveis de processo e error handling

**Fase 2 - DMN Integration (Sprint 7):**
- Migrar regras de cobertura para DMN
- Integração com Camunda Decision Engine
- Versionamento de contratos via DMN

**Fase 3 - Advanced Features (Sprint 8):**
- Cache de resultados de elegibilidade (Redis)
- Regras especiais (emergência, urgência)
- Dashboard de rejeições de cobertura

### Dependências Críticas
```yaml
dependencies:
  external_services:
    - EligibilityVerificationService  # Verificação em tempo real
    - InsuranceContractsDB           # Regras contratuais
    - ANS Rol de Procedimentos       # Cobertura obrigatória

  internal_services:
    - PatientService                 # Dados demográficos
    - ProcedureService               # Detalhes do procedimento

  databases:
    - insurance_plans                # Planos de saúde
    - contract_coverage_rules        # Regras de cobertura
    - eligibility_cache              # Cache de verificações
```

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Contexto:** Patient Eligibility & Coverage Management

**Subdomínio:** Coverage Verification (Supporting Domain)

**Responsabilidades:**
- Verificação de cobertura contratual para procedimentos
- Validação de elegibilidade do paciente
- Determinação de percentuais de cobertura

### Aggregates e Entidades

```yaml
aggregate: CoverageVerification
  root_entity: CoverageCheckResult
    properties:
      - checkId: UUID
      - patientId: UUID
      - insurancePlanId: UUID
      - procedureCode: String
      - serviceDate: LocalDate
      - isCovered: Boolean
      - coveragePercentage: Float
      - checkedAt: Instant

  value_objects:
    - CoverageDetails:
        - planType: PlanType
        - contractStartDate: LocalDate
        - contractEndDate: LocalDate?
        - coverageLimits: Map<String, BigDecimal>

    - VerificationContext:
        - patientAge: Integer
        - serviceType: ServiceType
        - isEmergency: Boolean
        - requiresPriorAuth: Boolean

  entities:
    - CoverageHistory:
        - historyId: UUID
        - checkId: UUID (FK)
        - previousCoverage: Boolean
        - changeReason: String
        - changedAt: Instant
```

### Domain Events

```json
{
  "domain_events": [
    {
      "event": "CoverageVerified",
      "triggers": ["Cobertura confirmada para procedimento"],
      "payload": {
        "checkId": "uuid",
        "patientId": "uuid",
        "procedureCode": "string",
        "isCovered": "boolean",
        "coveragePercentage": "float"
      },
      "subscribers": [
        "AuthorizationService",
        "BillingService",
        "AuditService"
      ]
    },
    {
      "event": "CoverageCheckFailed",
      "triggers": ["Procedimento não coberto"],
      "payload": {
        "checkId": "uuid",
        "failureReason": "string",
        "alternativeCoverage": "object?"
      },
      "subscribers": [
        "PatientNotificationService",
        "CaseManagementService"
      ]
    },
    {
      "event": "PriorAuthorizationRequired",
      "triggers": ["Procedimento requer autorização prévia"],
      "payload": {
        "checkId": "uuid",
        "procedureCode": "string",
        "authorizationCriteria": "object"
      },
      "subscribers": [
        "AuthorizationWorkflow",
        "UtilizationManagement"
      ]
    }
  ]
}
```

### Invariantes do Domínio
1. **Active Contract:** Paciente deve ter contrato ativo na data de serviço
2. **Valid Service Date:** serviceDate não pode ser no passado (> 90 dias)
3. **Coverage Percentage:** Valor entre 0.0 e 1.0 (0-100%)
4. **Emergency Override:** Casos de emergência sempre têm cobertura inicial

### Viabilidade para Microserviço
**Candidato:** ⚠️ POSSÍVEL (com ressalvas)

**Justificativa:**
- Responsabilidade clara: verificação de cobertura
- Integração com múltiplos sistemas externos
- Estado pode ser cacheable (Redis)
- **Atenção:** Dependência forte de EligibilityVerificationService

**Integração:**
```yaml
microservice: coverage-verification-service
  api:
    - POST /coverage/check
    - GET /coverage/history/{patientId}
    - GET /coverage/plans/{planId}/rules

  events_published:
    - CoverageVerified
    - CoverageCheckFailed
    - PriorAuthorizationRequired

  events_subscribed:
    - PatientRegistered (from PatientService)
    - ContractUpdated (from InsuranceService)

  external_dependencies:
    - EligibilityVerificationService (sync call)
    - InsuranceContractsDB (read-only)
```

---

## XIII. Metadados Técnicos

### Complexidade e Esforço

```yaml
complexity_metrics:
  cyclomatic_complexity: 8   # Médio-Baixo
  cognitive_complexity: 12   # Médio
  lines_of_code: ~200

  time_estimates:
    implementation: 2 dias
    testing: 2 dias
    integration: 1 dia
    documentation: 0.5 dia
    total: 5.5 dias (~1 sprint)
```

### Cobertura de Testes

```yaml
test_coverage_targets:
  unit_tests: 85%
  integration_tests: 75%

  critical_test_scenarios:
    - coverage_verified_success
    - coverage_check_failed
    - service_date_default_today
    - emergency_override
    - prior_authorization_required
    - inactive_contract
    - external_service_timeout
    - cache_hit_scenario
```

### Performance e SLA

```yaml
performance_requirements:
  coverage_check_latency: <300ms (p95)
  external_api_timeout: 2000ms
  cache_hit_rate: >60%

  availability: 99.5%

  resource_limits:
    cpu: 1 core
    memory: 2 GB
    cache_size: 1 GB (Redis)
```

### Dependências e Integrações

```yaml
dependencies:
  internal_services:
    - PatientService (dados demográficos)
    - ProcedureService (detalhes de procedimentos)
    - AuthorizationService (fluxo de autorização)

  external_services:
    - EligibilityVerificationService (verificação em tempo real)
    - InsuranceContractsDB (regras contratuais)
    - ANS Rol API (cobertura obrigatória)

  databases:
    - coverage_checks (PostgreSQL)
    - eligibility_cache (Redis - TTL 1h)
    - contract_rules (PostgreSQL read-replica)

  message_queues:
    - coverage_events (Kafka)
```

### Monitoramento e Observabilidade

```yaml
metrics:
  business:
    - coverage_approval_rate
    - prior_auth_requirement_rate
    - coverage_check_volume_by_plan
    - failure_reason_distribution

  technical:
    - coverage_check_latency_p50_p95_p99
    - external_api_success_rate
    - cache_hit_rate
    - timeout_rate

  alerts:
    - coverage_approval_rate < 80% (1h window)
    - external_api_timeout > 5% (15min window)
    - cache_hit_rate < 50% (1h window)
    - coverage_check_latency_p95 > 500ms
```

---

**Última Atualização:** 2025-01-12
**Versão do Documento:** 2.0
**Status de Conformidade:** ✅ Completo (X-XIII)
