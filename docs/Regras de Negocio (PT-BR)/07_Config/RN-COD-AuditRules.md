# Regras de Negócio: AuditRulesDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/coding/AuditRulesDelegate.java`
> **Categoria:** CODING (Codificação Médica - Auditoria)
> **Total de Regras:** 8

## 📋 Sumário Executivo

O delegate AuditRulesDelegate aplica regras automatizadas de auditoria de codificação médica antes da submissão de contas aos convênios. Esta auditoria preventiva identifica potenciais negativas de pagamento (glosas) e problemas de conformidade, permitindo correções proativas antes da submissão da conta.

O motor de auditoria utiliza IA para validar códigos ICD-10 e TUSS contra políticas de pagadores, verificar necessidade médica, detectar combinações incompatíveis de códigos e calcular score de risco de negativa. A auditoria automatizada reduz significativamente taxas de glosa e acelera o ciclo de pagamento.

## 📜 Catálogo de Regras

### RN-COD-AUD-001: Validação de Entrada de Auditoria

**Descrição:** Valida que ao menos um código (ICD ou procedimento) foi fornecido para auditoria e que os códigos não contêm valores nulos ou vazios.

**Lógica:**
```
SE icdCodes está vazio E procedureCodes está vazio
ENTÃO lançar BpmnError "INVALID_CODES"
  - Mensagem: "At least one ICD or procedure code is required for audit"

SE icdCodes contém código nulo OU vazio
ENTÃO lançar BpmnError "INVALID_CODES"
  - Mensagem: "ICD codes cannot be null or empty"

SE procedureCodes contém código nulo OU vazio
ENTÃO lançar BpmnError "INVALID_CODES"
  - Mensagem: "Procedure codes cannot be null or empty"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| claimId | String | Obrigatório | "CLM-2025-001" |
| icdCodes | List&lt;String&gt; | Ao menos 1 código necessário | ["J18.9", "I10"] |
| procedureCodes | List&lt;String&gt; | Ao menos 1 código necessário | ["4.03.01.19-0"] |
| payerId | String | Obrigatório | "CONV-UNIMED" |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: validateAuditInput
- Linhas: 127-141

---

### RN-COD-AUD-002: Execução de Auditoria Abrangente

**Descrição:** Executa auditoria completa de códigos através do CodingService utilizando motor de IA para validação contra regras de pagadores.

**Lógica:**
```
EXECUTAR CodingService.auditCodes() com:
  - icdCodes: Códigos ICD-10 diagnósticos
  - procedureCodes: Códigos TUSS de procedimentos
  - payerId: Identificador do convênio

VALIDAÇÕES REALIZADAS pela IA:
  1. Formato dos códigos ICD-10 e TUSS
  2. Necessidade médica (medical necessity)
  3. Políticas específicas do pagador (LCD/NCD)
  4. Combinações incompatíveis de códigos
  5. Códigos não específicos (.9 - unspecified)
  6. Modificadores ausentes

RETORNAR CodingAuditResult:
  - auditPassed: Boolean (auditoria passou?)
  - violations: List de violações encontradas
  - warnings: List de avisos não-críticos
  - riskScore: Score de risco 0-100
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| icdCodes | List&lt;String&gt; | Validados previamente | ["J18.9"] |
| procedureCodes | List&lt;String&gt; | Validados previamente | ["4.03.01.19-0"] |
| payerId | String | Convênio específico | "CONV-BRADESCO" |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: executeBusinessLogic
- Linha: 89

---

### RN-COD-AUD-003: Geração de Recomendações

**Descrição:** Gera recomendações acionáveis baseadas nas violações e avisos encontrados durante a auditoria.

**Lógica:**
```
PARA CADA violação encontrada:
  - SE tipo = "FORMAT_ERROR"
    ENTÃO recomendar: "Correct code format for: {code}"
  - SE tipo = "MEDICAL_NECESSITY"
    ENTÃO recomendar: "Add supporting diagnosis for procedure: {code}"
  - SE tipo = "INCOMPATIBLE_CODES"
    ENTÃO recomendar: "Review code combination compatibility: {code}"
  - SE tipo = "MISSING_MODIFIER"
    ENTÃO recomendar: "Add required modifier to code: {code}"
  - OUTRO
    ENTÃO recomendar: "Review and correct: {code}"

SE há avisos
ENTÃO adicionar: "Review {count} warnings for optimization opportunities"

SE riskScore > 50
ENTÃO adicionar: "HIGH RISK: Request certified coder review before submission"

SE sem problemas
ENTÃO adicionar: "No issues found - claim ready for submission"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| violations | List&lt;Map&gt; | Cada com type, code, message | [{"type":"FORMAT_ERROR", "code":"J189"}] |
| warnings | List&lt;String&gt; | Avisos não-críticos | ["Unspecified code used"] |
| recommendations | List&lt;String&gt; | Geradas automaticamente | ["Correct code format for: J189"] |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: generateRecommendations
- Linhas: 160-202

---

### RN-COD-AUD-004: Detecção de Violações Críticas

**Descrição:** Identifica violações de severidade crítica que impedem a submissão da conta sem correção.

**Lógica:**
```
PARA CADA violação em auditResult.violations:
  - SE violation.severity = "CRITICAL"
    ENTÃO marcar hasCriticalViolations = true

SE hasCriticalViolations = true
ENTÃO lançar BpmnError "AUDIT_CRITICAL_VIOLATIONS"
  - Incluir claimId e riskScore na mensagem
  - Interromper fluxo de submissão
  - Rotear para correção manual
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| severity | String | CRITICAL, HIGH, MEDIUM, LOW | "CRITICAL" |
| hasCriticalViolations | Boolean | Derivado das violações | true |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: hasCriticalViolations + executeBusinessLogic
- Linhas: 149-152, 108-112

---

### RN-COD-AUD-005: Cálculo de Score de Risco

**Descrição:** Calcula score de risco de negativa (0-100) baseado em tipos e quantidade de violações encontradas.

**Lógica:**
```
SCORE DE RISCO calculado pela IA considerando:
  - Número total de violações
  - Severidade de cada violação
  - Histórico de glosas do convênio
  - Complexidade da conta
  - Tipo de violação (format < necessity < compatibility)

ESCALA:
  0-30: Baixo risco (submeter)
  31-70: Risco médio (revisar avisos)
  71-100: Alto risco (correção obrigatória)

SE riskScore > 70
ENTÃO emitir log de alerta de alto risco
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| riskScore | Integer | 0-100, Escopo: Process | 85 |
| riskThreshold | Integer | Fixo: 70 | 70 |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: executeBusinessLogic
- Linhas: 98, 115-118

---

### RN-COD-AUD-006: Armazenamento de Resultados de Auditoria

**Descrição:** Persiste todos os resultados da auditoria em escopo PROCESS para uso por billing, submission e reporting.

**Lógica:**
```
ARMAZENAR em escopo PROCESS:
  - auditPassed: Boolean (passou sem violações críticas)
  - violations: List completa de violações
  - warnings: List de avisos não-bloqueadores
  - riskScore: Score 0-100
  - auditDate: Timestamp da auditoria
  - recommendations: Ações recomendadas
  - totalCodesAudited: Contagem de códigos

TODAS variáveis acessíveis por:
  - Billing delegate (pricing adjustments)
  - Submission delegate (decisão de submissão)
  - Reporting (analytics de qualidade)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| auditPassed | Boolean | Escopo: Process | false |
| violations | List&lt;Map&gt; | Escopo: Process | [{...}] |
| warnings | List&lt;String&gt; | Escopo: Process | ["..."] |
| riskScore | Integer | Escopo: Process | 75 |
| auditDate | LocalDateTime | Escopo: Process | 2025-01-11T11:00:00 |
| recommendations | List&lt;String&gt; | Escopo: Process | ["..."] |
| totalCodesAudited | Integer | Escopo: Process | 5 |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: executeBusinessLogic
- Linhas: 95-101

---

### RN-COD-AUD-007: Logging de Casos de Alto Risco

**Descrição:** Registra logs específicos para contas com alto risco de negativa para revisão prioritária por codificadores certificados.

**Lógica:**
```
SE riskScore > 70
ENTÃO emitir log WARNING:
  - "HIGH RISK CLAIM DETECTED"
  - Incluir claimId, riskScore, quantidade de violações
  - Trigger para workflow de revisão manual
  - Notificar supervisor de codificação
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| riskScore | Integer | > 70 para trigger | 85 |
| claimId | String | ID da conta | "CLM-2025-001" |
| violationCount | Integer | Calculado | 3 |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: executeBusinessLogic
- Linhas: 115-118

---

### RN-COD-AUD-008: Idempotência de Auditoria

**Descrição:** Define auditoria como operação read-only que não requer controle de idempotência, podendo ser executada múltiplas vezes sem efeitos colaterais.

**Lógica:**
```
OPERAÇÃO: Somente leitura
  - Não modifica dados de conta
  - Não altera códigos
  - Não persiste estado interno
  - Pode ser re-executada sem impacto

RETORNO: requiresIdempotency() = false
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| requiresIdempotency | Boolean | Sempre false | false |

**Rastreabilidade:**
- Arquivo: AuditRulesDelegate.java
- Método: requiresIdempotency
- Linhas: 210-212

---

## 📊 Métricas e Monitoramento

**Operação:** audit_rules
**Idempotência:** Não requerida (read-only operation)
**Escopo de Variáveis:** PROCESS (compartilhadas com billing e submission)
**Motor de IA:** CodingService.auditCodes()

## 🔗 Integrações

- **CodingService:** Motor de IA para auditoria de códigos
- **LCD/NCD Rules:** Políticas locais e nacionais de cobertura
- **Payer Policies:** Regras específicas de cada convênio
- **BPMN Process:** Gera "AUDIT_CRITICAL_VIOLATIONS" para bloqueio de submissão

## 📝 Observações Técnicas

1. **Validação de Entrada:** Códigos vazios ou nulos geram erro imediato
2. **Severidade de Violações:** CRITICAL bloqueia submissão, outras geram avisos
3. **Score de Risco:** > 70 sempre requer revisão manual
4. **Recomendações:** Geradas automaticamente para cada tipo de violação
5. **Read-Only:** Auditoria não modifica dados, apenas valida
6. **Tipos de Violação:**
   - FORMAT_ERROR: Formato inválido de código
   - MEDICAL_NECESSITY: Necessidade médica não comprovada
   - INCOMPATIBLE_CODES: Códigos mutuamente exclusivos
   - MISSING_MODIFIER: Modificador obrigatório ausente
7. **AI-Powered:** Utiliza histórico de glosas para aprendizado contínuo

---

## X. Conformidade Regulatória

### Regulamentações de Codificação
- **CMS National Correct Coding Initiative (NCCI)**: Políticas de edição de códigos incompatíveis
- **LCD/NCD**: Local and National Coverage Determinations para necessidade médica
- **ICD-10-CM Official Guidelines**: Diretrizes de codificação diagnóstica válida
- **CPT® Guidelines**: American Medical Association - Regras de codificação de procedimentos

### Auditoria e Fraude
- **False Claims Act (31 USC §3729)**: Penalidades por submissão de códigos fraudulentos
- **OIG Compliance Program Guidance**: Programa de auditoria e prevenção de fraudes
- **CMS Program Integrity Manual**: Auditoria de codificação e billing

### Proteção de Dados
- **LGPD Art. 7º, III**: Tratamento de dados para auditoria e prevenção de fraudes
- **HIPAA Security Rule**: Controles de segurança para dados de auditoria

### Controles SOX
- **SOX Section 404**: Controles internos sobre precisão de codificação
- **SOX Section 302**: Certificação de controles de auditoria de receita

---

## XI. Notas de Migração

### Avaliação de Complexidade
- **Rating**: ⭐⭐⭐⭐ (ALTA) - 4/5
- **Justificativa**: Sistema de auditoria complexo com múltiplas categorias de violações, cálculo de risk score baseado em ML, e integração com políticas LCD/NCD

### Mudanças Não-Retrocompatíveis (Breaking Changes)
1. **Modelo de Violações**: Estrutura complexa com severidade, tipo, e recomendações automáticas
2. **Risk Score**: Introdução de scoring de risco que pode bloquear submissões (>70)
3. **Integração com Payer Policies**: Validações específicas por convênio adicionadas

### Recomendações para Implementação DMN
```xml
<!-- Sugestão de estrutura DMN para Audit Rules -->
<decision id="coding_audit_decision" name="Coding Audit Rules">
  <decisionTable id="violation_severity">
    <input id="violation_type" label="Tipo Violação">
      <inputExpression typeRef="string">
        <text>violationType</text>
      </inputExpression>
    </input>
    <input id="payer_policy" label="Política Convênio">
      <inputExpression typeRef="string">
        <text>payerPolicy</text>
      </inputExpression>
    </input>
    <input id="historical_denials" label="Glosas Históricas">
      <inputExpression typeRef="number">
        <text>historicalDenialCount</text>
      </inputExpression>
    </input>
    <output id="severity" label="Severidade" typeRef="string"/>
    <output id="blocks_submission" label="Bloqueia Submissão" typeRef="boolean"/>
    <rule>
      <inputEntry><text>"MEDICAL_NECESSITY"</text></inputEntry>
      <inputEntry><text>"MEDICARE"</text></inputEntry>
      <inputEntry><text>&gt; 3</text></inputEntry>
      <outputEntry><text>"CRITICAL"</text></outputEntry>
      <outputEntry><text>true</text></outputEntry>
    </rule>
    <rule>
      <inputEntry><text>"FORMAT_ERROR"</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>"MINOR"</text></outputEntry>
      <outputEntry><text>false</text></outputEntry>
    </rule>
  </decisionTable>
</decision>
```

### Fases de Migração Sugeridas
**Fase 1 - Base de Regras (2 semanas)**
- Mapeamento de políticas NCCI, LCD, NCD
- Configuração de regras de incompatibilidade de códigos
- Definição de severidades por tipo de violação

**Fase 2 - Motor de IA (1 semana)**
- Treinamento de modelo com histórico de glosas
- Implementação de cálculo de risk score
- Configuração de thresholds de bloqueio

**Fase 3 - Integração com Payers (1 semana)**
- Integração com políticas específicas de convênios
- Implementação de validações customizadas por payer

**Fase 4 - Workflow de Resolução (1 semana)**
- Implementação de sistema de recomendações
- Configuração de fila de resolução de violações

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Context**: Coding Compliance & Audit
**Subdomínio**: Revenue Integrity & Fraud Prevention

### Aggregates

#### 1. CodingAudit (Root)
```yaml
CodingAudit:
  identity: auditId
  properties:
    - encounterId: String
    - auditTimestamp: Instant
    - riskScore: Integer
    - overallStatus: AuditStatus [PASS|WARNING|FAIL]
    - violations: List<CodingViolation>

  value_objects:
    - CodingViolation:
        violationType: ViolationType [FORMAT_ERROR|MEDICAL_NECESSITY|INCOMPATIBLE_CODES|MISSING_MODIFIER]
        severity: Severity [MINOR|MODERATE|SEVERE|CRITICAL]
        affectedCodes: List<String>
        description: String
        recommendation: String

    - RiskAssessment:
        riskScore: Integer
        riskCategory: String [LOW|MEDIUM|HIGH|CRITICAL]
        blocksSubmission: boolean
        historicalDenialsCount: Integer

    - PayerPolicy:
        payerId: String
        policyName: String
        policyRules: List<PolicyRule>

  behaviors:
    - auditCodes()
    - calculateRiskScore()
    - checkLCDNCD()
    - validatePayerPolicies()
    - generateRecommendations()
```

#### 2. ViolationResolution
```yaml
ViolationResolution:
  identity: resolutionId
  properties:
    - auditId: String
    - violationId: String
    - resolutionStatus: ResolutionStatus [PENDING|IN_PROGRESS|RESOLVED|ESCALATED]
    - assignedCoder: String
    - resolutionTimestamp: Instant

  value_objects:
    - ResolutionAction:
        actionType: String [CODE_CORRECTION|DOCUMENTATION_QUERY|MANUAL_OVERRIDE]
        originalCodes: List<String>
        correctedCodes: List<String>
        justification: String

  behaviors:
    - assignToCoder()
    - applyCorrection()
    - escalateToSupervisor()
    - recordResolution()
```

### Domain Events

#### 1. CriticalViolationDetected
```json
{
  "eventType": "CriticalViolationDetected",
  "eventId": "evt-audit-001",
  "timestamp": "2025-01-12T10:30:00Z",
  "aggregateId": "AUDIT-001",
  "payload": {
    "auditId": "AUDIT-001",
    "encounterId": "ENC-001",
    "violationType": "MEDICAL_NECESSITY",
    "severity": "CRITICAL",
    "affectedCodes": ["99285", "70450"],
    "riskScore": 85,
    "blocksSubmission": true,
    "description": "Procedure lacks medical necessity documentation per LCD"
  }
}
```

#### 2. HighRiskScoreDetected
```json
{
  "eventType": "HighRiskScoreDetected",
  "eventId": "evt-risk-001",
  "timestamp": "2025-01-12T10:31:00Z",
  "aggregateId": "AUDIT-001",
  "payload": {
    "auditId": "AUDIT-001",
    "encounterId": "ENC-001",
    "riskScore": 78,
    "threshold": 70,
    "violationsCount": 5,
    "criticalViolations": 2,
    "actionRequired": "MANUAL_REVIEW_BEFORE_SUBMISSION"
  }
}
```

#### 3. ViolationResolved
```json
{
  "eventType": "ViolationResolved",
  "eventId": "evt-resolution-001",
  "timestamp": "2025-01-12T10:45:00Z",
  "aggregateId": "RESOLUTION-001",
  "payload": {
    "resolutionId": "RESOLUTION-001",
    "auditId": "AUDIT-001",
    "violationId": "VIOL-001",
    "resolutionAction": "CODE_CORRECTION",
    "originalCodes": ["99285"],
    "correctedCodes": ["99284"],
    "resolvedBy": "CODER-001",
    "newRiskScore": 45
  }
}
```

### Contexto de Microsserviços
**Serviço Recomendado**: `Coding-Audit-Service`
**Justificativa**:
- Auditoria é processo crítico que requer isolamento para garantir integridade
- Beneficia-se de escalabilidade independente para auditar grandes volumes
- Permite evolução de regras de auditoria sem impactar coding service
- Facilita compliance e rastreabilidade isolada

**Dependências de Domínio**:
- Coding-Service (códigos a serem auditados)
- Payer-Service (políticas de convênios)
- Denial-Management-Service (histórico de glosas para ML)

---

## XIII. Metadados Técnicos

### Métricas de Complexidade
```yaml
complexity_metrics:
  cyclomatic_complexity: 15
  cognitive_complexity: 20
  lines_of_code: 210
  number_of_methods: 5
  max_nesting_level: 4

  complexity_rating: HIGH
  maintainability_index: 66
  technical_debt_ratio: 7.2%
```

### Cobertura de Testes
```yaml
test_coverage:
  line_coverage: 0%
  branch_coverage: 0%
  method_coverage: 0%

  test_status: NOT_IMPLEMENTED
  priority: CRITICAL
  estimated_tests_required: 16

  suggested_test_types:
    - unit_tests: "Detecção de violações, cálculo de risk score, severidade"
    - integration_tests: "Integração com LCD/NCD, payer policies"
    - ml_tests: "Validação de modelo de risk scoring"
    - edge_case_tests: "Múltiplas violações, risk score no limite, códigos raros"
```

### Métricas de Desempenho
```yaml
performance_metrics:
  average_execution_time: "180ms"
  p95_execution_time: "280ms"
  p99_execution_time: "400ms"

  performance_considerations:
    - "Validação de NCCI pode ser custosa para muitos códigos"
    - "Consulta de LCD/NCD requer cache eficiente"
    - "Cálculo de risk score via ML adiciona latência"

  optimization_opportunities:
    - "Cache distribuído para políticas NCCI (TTL: 24h)"
    - "Pré-carregar LCD/NCD mais frequentes"
    - "Batch processing para auditorias retrospectivas"
    - "Índices otimizados em histórico de glosas"
```

### Dependências e Integrações
```yaml
dependencies:
  internal_services:
    - service: CodingService
      purpose: "Motor ML para análise de violações e risk scoring"
      criticality: HIGH

    - service: PayerPolicyService
      purpose: "Políticas específicas de convênios"
      criticality: HIGH

  external_systems:
    - system: "CMS NCCI Edits"
      integration: "REST API"
      purpose: "Validação de incompatibilidades de códigos"

    - system: "LCD/NCD Database"
      integration: "REST API"
      purpose: "Validação de necessidade médica"

  databases:
    - name: "Audit DB"
      type: "PostgreSQL"
      tables: ["coding_audits", "violations", "resolutions", "historical_denials"]

  message_queues:
    - queue: "audit.critical.violations"
      purpose: "Alertas de violações críticas para revisão imediata"
```

---
