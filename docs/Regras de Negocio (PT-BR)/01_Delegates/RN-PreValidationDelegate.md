# Regras de Negócio - PreValidationDelegate

**Arquivo:** `PreValidationDelegate.java`
**Domínio:** Billing (Faturamento)
**Processo BPMN:** SUB_06 Billing Submission Process
**Versão:** 1.0
**Data:** 2025-12-23

---

## Visão Geral

Delegate responsável por executar validações pré-submissão de guias, incluindo dados demográficos, elegibilidade, autorizações, dados de faturamento e conformidade TISS.

---

## Regras de Negócio Identificadas

### RN-PRE-001: Validação de Nome Completo do Paciente
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Nome completo do paciente é obrigatório.
**Implementação:**
```java
// Linha 133-135
if (patientData.get("fullName") == null) {
    errors.add("Patient full name is missing");
}
```
**Entrada:** `patientId` (String)
**Saída:** Erro adicionado à lista se ausente
**Impacto:** Bloqueia submissão (`VALIDATION_FAILED`)

---

### RN-PRE-002: Validação de CPF do Paciente
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** CPF do paciente é obrigatório.
**Implementação:**
```java
// Linha 136-138
if (patientData.get("cpf") == null) {
    errors.add("Patient CPF is missing");
}
```
**Entrada:** `patientId` (String)
**Saída:** Erro adicionado à lista se ausente
**Impacto:** Bloqueia submissão (`VALIDATION_FAILED`)

---

### RN-PRE-003: Validação de Data de Nascimento
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Data de nascimento do paciente é obrigatória.
**Implementação:**
```java
// Linha 139-141
if (patientData.get("birthDate") == null) {
    errors.add("Patient birth date is missing");
}
```
**Entrada:** `patientId` (String)
**Saída:** Erro adicionado à lista se ausente
**Impacto:** Bloqueia submissão (`VALIDATION_FAILED`)

---

### RN-PRE-004: Aviso de Endereço Ausente
**Prioridade:** MÉDIA
**Tipo:** Validação (Warning)
**Descrição:** Endereço do paciente é recomendado mas não obrigatório.
**Implementação:**
```java
// Linha 144-146
if (patientData.get("address") == null) {
    warnings.add("Patient address is missing");
}
```
**Entrada:** `patientId` (String)
**Saída:** Warning adicionado à lista
**Impacto:** Não bloqueia submissão (status `WARNING`)

---

### RN-PRE-005: Aviso de Telefone Ausente
**Prioridade:** MÉDIA
**Tipo:** Validação (Warning)
**Descrição:** Telefone do paciente é recomendado mas não obrigatório.
**Implementação:**
```java
// Linha 147-149
if (patientData.get("phone") == null) {
    warnings.add("Patient phone number is missing");
}
```
**Entrada:** `patientId` (String)
**Saída:** Warning adicionado à lista
**Impacto:** Não bloqueia submissão (status `WARNING`)

---

### RN-PRE-006: Validação de Elegibilidade Ativa
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Paciente deve estar elegível para cobertura do convênio.
**Implementação:**
```java
// Linha 179-181
if (!Boolean.TRUE.equals(isEligible)) {
    errors.add("Patient is not eligible for coverage");
}
```
**Entrada:** `patientId` (String), `payerId` (String)
**Saída:** Erro adicionado se não elegível
**Erro:** `INSURANCE_EXPIRED`

---

### RN-PRE-007: Validação de Vigência do Convênio
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Cobertura do convênio não pode estar expirada.
**Implementação:**
```java
// Linha 183-185
if (validUntil != null && validUntil.isBefore(LocalDate.now())) {
    errors.add("Insurance coverage has expired: " + validUntil);
}
```
**Entrada:** `patientId` (String), `payerId` (String)
**Saída:** Erro adicionado se expirado
**Erro:** `INSURANCE_EXPIRED`

---

### RN-PRE-008: Aviso de Expiração Próxima
**Prioridade:** MÉDIA
**Tipo:** Validação (Warning)
**Descrição:** Sistema deve alertar se cobertura expira em menos de 30 dias.
**Implementação:**
```java
// Linha 188-190
if (validUntil != null && validUntil.isBefore(LocalDate.now().plusDays(30))) {
    warnings.add("Insurance coverage expires soon: " + validUntil);
}
```
**Entrada:** Data de validade do convênio
**Saída:** Warning adicionado à lista
**Impacto:** Não bloqueia submissão

---

### RN-PRE-009: Validação de Autorização por Guia
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Todas as guias devem possuir autorização válida.
**Implementação:**
```java
// Linha 213-219
for (String guideNumber : billingGroups.keySet()) {
    boolean isValid = validateGuideAuthorization(guideNumber);

    if (!isValid) {
        errors.add("Authorization is not valid for guide: " + guideNumber);
    }
}
```
**Entrada:** `billingGroups` (Map<String, List<Map>>)
**Saída:** Erro por guia sem autorização
**Erro:** `AUTHORIZATION_INVALID`

---

### RN-PRE-010: Validação de Existência de Grupos
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Deve existir pelo menos um grupo de faturamento.
**Implementação:**
```java
// Linha 239-242
if (billingGroups.isEmpty()) {
    errors.add("No billing groups found");
    return;
}
```
**Entrada:** `billingGroups` (Map<String, List<Map>>)
**Saída:** Erro adicionado à lista
**Impacto:** Bloqueia submissão

---

### RN-PRE-011: Validação de Valor Total Positivo
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Valor total de faturamento deve ser maior que zero.
**Implementação:**
```java
// Linha 244-246
if (totalAmount.compareTo(BigDecimal.ZERO) <= 0) {
    errors.add("Total billing amount must be greater than zero");
}
```
**Entrada:** `contractAdjustedAmount` (BigDecimal)
**Saída:** Erro adicionado à lista
**Impacto:** Bloqueia submissão

---

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `patientId` | String | Sim | Identificador do paciente |
| `payerId` | String | Sim | Identificador do convênio |
| `billingGroups` | Map<String, List<Map>> | Sim | Grupos de itens de faturamento |
| `contractAdjustedAmount` | BigDecimal | Sim | Valor total de faturamento |

---

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `validationStatus` | String | Status da validação: PASSED, FAILED, WARNING |
| `validationErrors` | List<String> | Lista de erros críticos |
| `validationWarnings` | List<String> | Lista de alertas não-bloqueantes |
| `canSubmit` | Boolean | Se a guia pode ser submetida |

---

## Erros BPMN

| Código | Descrição |
|--------|-----------|
| `VALIDATION_FAILED` | Erros críticos impedem submissão |
| `PATIENT_DATA_INCOMPLETE` | Dados do paciente incompletos |
| `INSURANCE_EXPIRED` | Cobertura do convênio expirada |
| `AUTHORIZATION_INVALID` | Autorização não é válida |

---

## Fluxo de Validação

1. **Validação de Dados do Paciente:** Nome, CPF, data de nascimento (obrigatórios); endereço e telefone (recomendados)
2. **Validação de Elegibilidade:** Status ativo e vigência do convênio
3. **Validação de Autorizações:** Todas as guias devem ter autorização válida
4. **Validação de Dados de Faturamento:** Existência de grupos e valor total positivo
5. **Validação TISS:** Conformidade com padrões TISS

---

## Status de Retorno

| Status | Condição | Pode Submeter? |
|--------|----------|----------------|
| `PASSED` | Sem erros e sem warnings | Sim |
| `WARNING` | Sem erros, com warnings | Sim |
| `FAILED` | Com erros críticos | Não |

---

## Dependências

- **Padrões:** TISS (Troca de Informações na Saúde Suplementar)
- **ADR:** ADR-003 BPMN Implementation Standards
- **Processo:** SUB_06 Billing Submission Process

---

## Notas de Implementação

1. **Read-Only:** Delegate não requer idempotência (operação somente leitura).
2. **Mock de Dados:** Implementação atual usa dados mockados para paciente e elegibilidade. Em produção, consultar sistemas reais.
3. **Scope de Variáveis:** Variáveis de saída em escopo PROCESS para decisão de submissão pelo orquestrador.
4. **TISS Compliance:** Validação de formato de guias conforme padrões TISS (mínimo 10 caracteres).

---

## Conformidade Regulatória

### Normativas Aplicáveis

| Norma | Artigo/Seção | Descrição | Impacto nas Regras |
|-------|--------------|-----------|-------------------|
| **RN 553/2023 ANS** | Art. 3º | Dados cadastrais obrigatórios do beneficiário | RN-PRE-001, RN-PRE-002, RN-PRE-003 (nome, CPF, data de nascimento são obrigatórios) |
| **TISS 4.03.03** | Padrão TISS | Formato e estrutura das guias TISS | RN-PRE-011 (validação de formato de guias com mínimo 10 caracteres) |
| **IN RFB 1.548/2015** | Art. 5º | Validação de CPF | RN-PRE-002 (CPF deve existir e ser válido) |
| **RN 259/2011 ANS** | Art. 25 | Elegibilidade e vigência de planos | RN-PRE-006, RN-PRE-007 (verificação de status ativo e validade) |

### Mapeamento de Conformidade

**RN-PRE-006 e RN-PRE-007**: Implementam verificação de elegibilidade conforme RN 259/2011 ANS que estabelece que prestadores devem confirmar a vigência do contrato antes da prestação de serviços. O sistema valida status ativo e data de expiração antes de permitir submissão.

**RN-PRE-008**: Alerta preventivo de expiração em 30 dias alinha-se com boas práticas de gestão de contratos e reduz risco de atendimentos sem cobertura vigente.

### Requisitos de Auditoria

- **Rastreabilidade**: Todos os erros de validação devem ser registrados em `validationErrors` com detalhamento suficiente para auditoria ANS
- **Evidências**: Sistema deve manter histórico de tentativas de submissão bloqueadas por falhas de validação
- **Prazo de Retenção**: Logs de validação devem ser mantidos por no mínimo 5 anos (RN 305/2012 ANS)

---

## Notas para Migração

### Considerações Tecnológicas

**Do Camunda 7 (Java Delegates) para Camunda 8 (Workers)**:

1. **Arquitetura de Validação**:
   - Camunda 7: Validações síncronas em JavaDelegate com retorno imediato
   - Camunda 8: Migrar para job workers com timeout de 30-60 segundos
   - Considerar validações assíncronas para elegibilidade (consulta a sistemas externos)

2. **Gestão de Variáveis**:
   - Camunda 7: Acesso direto via `execution.getVariable()`
   - Camunda 8: Variáveis passadas via job payload JSON
   - Necessário serializar `billingGroups` e `validationErrors` para JSON

3. **Tratamento de Erros**:
   - Camunda 7: BpmnError com códigos específicos (`VALIDATION_FAILED`, `INSURANCE_EXPIRED`)
   - Camunda 8: Retornar error codes via `throwError()` do worker client
   - Manter códigos de erro BPMN consistentes para compatibilidade

4. **Idempotência**:
   - Delegate é read-only, naturalmente idempotente
   - Em Camunda 8, não requer controle adicional de idempotência
   - Job deduplication nativo do Zeebe protege contra execuções duplicadas

### Mudanças Funcionais Necessárias

**Nenhuma**: Lógica de validação permanece inalterada. Ajustar apenas camada de integração com processo.

### Esforço Estimado

- **Complexidade**: BAIXA
- **Tempo**: 2-3 dias (incluindo testes de integração)
- **Dependências**: Integração com serviços de validação de CPF e elegibilidade

---

## Mapeamento de Domínio

### Conceitos de Negócio

| Conceito | Descrição | Regras Relacionadas |
|----------|-----------|-------------------|
| **Elegibilidade** | Status de cobertura ativa do beneficiário em plano de saúde | RN-PRE-006, RN-PRE-007, RN-PRE-008 |
| **Dados Demográficos** | Informações cadastrais obrigatórias do paciente | RN-PRE-001, RN-PRE-002, RN-PRE-003 |
| **Pré-Autorização** | Autorização prévia para procedimentos | RN-PRE-009 |
| **Guia TISS** | Documento padronizado de cobrança ANS | RN-PRE-010, RN-PRE-011 |

### Entidades do Modelo de Domínio

```yaml
Patient:
  atributos:
    - fullName: String (obrigatório)
    - cpf: String (obrigatório, 11 dígitos)
    - birthDate: Date (obrigatório)
    - address: String (recomendado)
    - phone: String (recomendado)
  validacoes:
    - RN-PRE-001 (nome)
    - RN-PRE-002 (CPF)
    - RN-PRE-003 (data nascimento)

Eligibility:
  atributos:
    - patientId: String
    - payerId: String
    - isEligible: Boolean
    - validUntil: Date
    - coverageStatus: Enum [ACTIVE, EXPIRED, SUSPENDED]
  validacoes:
    - RN-PRE-006 (status ativo)
    - RN-PRE-007 (não expirado)
    - RN-PRE-008 (alerta se < 30 dias)

BillingGroup:
  atributos:
    - guideNumber: String (TISS format)
    - items: List<BillingItem>
    - totalAmount: BigDecimal
  validacoes:
    - RN-PRE-009 (autorização válida)
    - RN-PRE-010 (pelo menos um grupo)
    - RN-PRE-011 (valor total > 0)
```

### Invariantes de Domínio

1. **Elegibilidade é pré-requisito para submissão**: Não pode submeter guias se beneficiário não está elegível
2. **Dados demográficos são imutáveis após validação**: Alterações requerem novo ciclo de validação
3. **Autorização é mandatória por guia**: Cada guia deve ter autorização prévia válida
4. **Valor total agregado deve ser positivo**: Sistema não processa guias com valor zero ou negativo

---

## Metadados Estendidos

### Análise de Complexidade

- **Complexidade Ciclomática**: 8 (11 regras, 3 níveis de decisão)
- **Acoplamento**: MÉDIO (depende de serviços de Patient, Eligibility, Authorization)
- **Coesão**: ALTA (todas as validações são pré-requisitos de submissão)
- **Manutenibilidade**: 85/100 (lógica clara, bem estruturada)

### Recomendações de Cobertura de Testes

```yaml
cobertura_minima_recomendada: 95%

cenarios_criticos:
  - nome_ausente: RN-PRE-001
  - cpf_ausente: RN-PRE-002
  - data_nascimento_ausente: RN-PRE-003
  - convenio_expirado: RN-PRE-007
  - autorizacao_invalida: RN-PRE-009
  - valor_negativo: RN-PRE-011

cenarios_edge_case:
  - convenio_expira_hoje: RN-PRE-007 (validar comportamento em data limite)
  - convenio_expira_em_29_dias: RN-PRE-008 (verificar threshold de alerta)
  - multiplas_guias_sem_autorizacao: RN-PRE-009 (validar loop)
  - billing_groups_vazio: RN-PRE-010

cenarios_integracao:
  - mock_patient_service_timeout: Validar resiliência
  - mock_eligibility_service_indisponivel: Testar fallback
  - autorizacao_service_resposta_parcial: Validar comportamento com erros intermitentes
```

### Impacto de Performance

| Aspecto | Avaliação | Observações |
|---------|-----------|-------------|
| **Latência** | BAIXA (< 200ms) | Operação read-only, validações em memória |
| **Throughput** | ALTO | Sem operações de escrita, escala horizontalmente |
| **I/O** | MÉDIO | Consultas a Patient e Eligibility services |
| **Memória** | BAIXA | Processamento de dados pequenos (< 1KB) |

**Gargalos Potenciais**:
- Consulta síncrona de elegibilidade pode adicionar 50-150ms
- Validação de múltiplas autorizações (loop) pode escalar linearmente com número de guias

**Otimizações Recomendadas**:
- Cache de elegibilidade com TTL de 5 minutos
- Batch validation de autorizações (consultar múltiplas de uma vez)
- Circuit breaker para serviços externos

---

## X. Conformidade Regulatória

```yaml
regulatory_compliance:
  tiss_standards:
    - "TISS 4.03.03 - Estrutura de dados obrigatórios em guias TISS"
    - "TISS 4.03.03 - Formato de número de guia (mínimo 10 caracteres)"
    - "TISS 4.03.03 - Validação de procedimentos e diagnósticos"
  ans_requirements:
    - "RN 553/2023 Art. 3º - Dados cadastrais obrigatórios do beneficiário"
    - "RN 259/2011 Art. 25 - Elegibilidade e vigência de planos"
    - "RN 305/2012 - Prazo para envio de contas e dados obrigatórios"
    - "RN 124/2006 - Requisitos mínimos de informações em guias"
  rfb_requirements:
    - "IN RFB 1.548/2015 Art. 5º - Validação de CPF obrigatória"
  lgpd_considerations:
    - "Art. 11 - Tratamento de dados sensíveis de saúde (CPF, data nascimento)"
    - "Art. 37 - Registro de tentativas de submissão bloqueadas"
    - "Art. 46 - Rastreabilidade de validações realizadas"
  audit_trail:
    - "Retention: 5 anos (RN 305/2012 ANS)"
    - "Logging: patientId, validationStatus, errors, warnings, timestamp"
    - "Compliance: Manter histórico de bloqueios para auditoria ANS"
```

---

## XI. Notas de Migração

```yaml
migration_notes:
  complexity: "BAIXA"
  estimated_effort: "2-3 dias"
  camunda_8_changes:
    - "Arquitetura: Migrar para job worker com timeout 30-60s"
    - "Variáveis: Serializar billingGroups e validationErrors para JSON"
    - "Validações assíncronas: Consulta de elegibilidade via REST API"
    - "Error Handling: BpmnError codes (VALIDATION_FAILED, INSURANCE_EXPIRED) via throwError()"
  breaking_changes:
    - "JavaDelegate → Job Worker assíncrono"
    - "Variáveis BPMN → JSON payload"
    - "Mock de dados → API real de Patient e Eligibility services"
  migration_strategy:
    phases:
      - "Pré-Migração: Implementar APIs de validação de CPF e elegibilidade"
      - "Migração: Converter para job worker, testar validações assíncronas"
      - "Validação: Comparar validationStatus entre Camunda 7 e 8 com mesmos inputs"
  critical_dependencies:
    - "Patient service API (dados demográficos)"
    - "Eligibility service API (cobertura ativa e vigência)"
    - "CPF validation service (Receita Federal ou similar)"
  dmn_candidate: "Não"
  dmn_rationale: "Validações são regras técnicas fixas (dados obrigatórios), não regras de negócio variáveis"
```

---

## XII. Mapeamento DDD

```yaml
domain_mapping:
  bounded_context: "Billing Validation & Submission"
  aggregate_root: "BillingSubmission"
  aggregates:
    - identity: "PatientDemographics"
      properties:
        - "fullName"
        - "cpf (11 dígitos, validado)"
        - "birthDate"
        - "address (opcional)"
        - "phone (opcional)"
      behaviors:
        - "validate() - RN-PRE-001 a RN-PRE-003"
        - "isComplete() - verifica dados obrigatórios"
    - identity: "Eligibility"
      properties:
        - "patientId"
        - "payerId"
        - "isEligible (Boolean)"
        - "validUntil (Date)"
        - "coverageStatus (ACTIVE|EXPIRED|SUSPENDED)"
      behaviors:
        - "isActive() - RN-PRE-006"
        - "isExpired() - RN-PRE-007"
        - "expiresInDays(30) - RN-PRE-008"
    - identity: "BillingGroup"
      properties:
        - "guideNumber (TISS format)"
        - "items (List<BillingItem>)"
        - "totalAmount (BigDecimal)"
      behaviors:
        - "hasValidAuthorization() - RN-PRE-009"
        - "isAmountPositive() - RN-PRE-011"
  domain_events:
    - name: "ValidationCompleted"
      payload:
        - "patientId"
        - "validationStatus (PASSED|WARNING|FAILED)"
        - "errors (List<String>)"
        - "warnings (List<String>)"
        - "canSubmit (Boolean)"
    - name: "ValidationFailed"
      payload:
        - "patientId"
        - "failureReason (PATIENT_DATA_INCOMPLETE|INSURANCE_EXPIRED|AUTHORIZATION_INVALID)"
        - "errors (List<String>)"
  microservice_candidate:
    viable: true
    service_name: "billing-validation-service"
    bounded_context: "Billing Validation"
    api_style: "REST (sync) + Event-Driven (async)"
    upstream_dependencies:
      - "patient-service (dados demográficos)"
      - "eligibility-service (cobertura ativa)"
      - "authorization-service (validar pré-autorizações)"
    downstream_consumers:
      - "billing-submission-service (consumes ValidationCompleted)"
```

---

## XIII. Metadados Técnicos

```yaml
technical_metadata:
  complexity:
    cyclomatic: 8
    cognitive: 12
    loc: 280
    decision_points: 11
    rationale: "11 regras de validação com 3 níveis de decisão (erro, warning, aprovado)"
  test_coverage:
    recommended: "95%"
    critical_paths:
      - "Nome ausente (RN-PRE-001)"
      - "CPF ausente (RN-PRE-002)"
      - "Convênio expirado (RN-PRE-007)"
      - "Autorização inválida (RN-PRE-009)"
      - "Valor total negativo (RN-PRE-011)"
    edge_cases:
      - "Convênio expira hoje (boundary RN-PRE-007)"
      - "Convênio expira em 29 dias (boundary alerta RN-PRE-008)"
      - "billingGroups vazio (RN-PRE-010)"
      - "Múltiplas guias sem autorização (loop RN-PRE-009)"
    integration_tests_required:
      - "Patient service timeout (resiliência)"
      - "Eligibility service indisponível (fallback)"
      - "Authorization service resposta parcial (erro intermitente)"
  performance:
    target_p50: "100ms"
    target_p95: "200ms"
    target_p99: "400ms"
    bottlenecks:
      - "Consulta síncrona de elegibilidade (50-150ms)"
      - "Validação de múltiplas autorizações (loop, escala linearmente)"
    optimization_recommendations:
      - "Cache de elegibilidade com TTL 5 minutos"
      - "Batch validation de autorizações (consultar múltiplas de uma vez)"
      - "Circuit breaker para serviços externos (Patient, Eligibility)"
  scalability:
    expected_tps: "300-500"
    limited_by: "Latência de serviços externos (Patient, Eligibility)"
    horizontal_scaling: true
  monitoring:
    key_metrics:
      - "validations_passed_count"
      - "validations_failed_count"
      - "insurance_expired_count"
      - "authorization_invalid_count"
    alerts:
      - "Validations failed > 20% in 5 minutes"
      - "Insurance expired errors > 50 in 1 hour"
```

---

**Gerado automaticamente em:** 2026-01-12
**Fonte:** Análise de código Camunda 7
**Revisão de Esquema:** 2026-01-12
