# RN-016: Detecção de Cobranças Perdidas

**Delegate**: `DetectMissedChargesDelegate.java`
**Subprocesso BPMN**: SUB_10_Revenue_Maximization
**Prioridade**: CRÍTICA
**Versão**: 1.0
**Última Atualização**: 2026-01-12

---

## 1. Visão Geral

### 1.1 Objetivo
Detectar procedimentos realizados, medicamentos utilizados e exames solicitados que não foram faturados, identificando oportunidades de recuperação de receita perdida.

### 1.2 Escopo
- Cruzamento de documentação clínica com registros de faturamento
- Identificação de procedimentos realizados mas não cobrados
- Análise de suprimentos utilizados sem cobrança
- Detecção de exames/imagens sem charges correspondentes
- Cálculo de perda de receita estimada
- Geração de recomendações de recuperação

### 1.3 Stakeholders
- **Primários**: Gestão financeira, faturamento, controladoria
- **Secundários**: Auditoria de receita, CDI (Clinical Documentation Improvement)

---

## 2. Regras de Negócio

### RN-016.1: Definição de Período de Análise Padrão
**Criticidade**: MÉDIA
**Categoria**: Configuração de Análise

**Descrição**:
Se não especificado, o sistema analisa os últimos 30 dias do encontro:
- `analysisStartDate` (opcional): Data inicial da análise
- `analysisEndDate` (opcional): Data final da análise
- **Default**: Últimos 30 dias a partir da data atual

**Implementação**:
```java
if (analysisStartDate == null) {
    analysisStartDate = LocalDateTime.now().minusDays(30);
}
if (analysisEndDate == null) {
    analysisEndDate = LocalDateTime.now();
}
```

**Justificativa**: Cobranças podem ser lançadas até 30 dias após o atendimento

---

### RN-016.2: Validação de Período de Análise
**Criticidade**: ALTA
**Categoria**: Validação de Entrada

**Descrição**:
O período de análise deve atender aos seguintes critérios:

**Regras Obrigatórias**:
1. Data inicial e final não podem ser null
2. Data inicial deve ser anterior ou igual à data final
3. Data final não pode ser no futuro

**Regras de Alerta**:
- Período > 90 dias: warning de performance (consulta pesada)

**Implementação**:
```java
private void validateAnalysisPeriod(LocalDateTime startDate, LocalDateTime endDate) {
    if (startDate == null || endDate == null) {
        throw new BpmnError("ANALYSIS_PERIOD_INVALID",
            "Analysis period start and end dates cannot be null");
    }

    if (startDate.isAfter(endDate)) {
        throw new BpmnError("ANALYSIS_PERIOD_INVALID",
            "Analysis start date must be before end date");
    }

    if (endDate.isAfter(LocalDateTime.now())) {
        throw new BpmnError("ANALYSIS_PERIOD_INVALID",
            "Analysis end date cannot be in the future");
    }

    if (startDate.isBefore(LocalDateTime.now().minusDays(90))) {
        log.warn("Analysis period exceeds 90 days - may impact performance");
    }
}
```

**Erros BPMN**: `ANALYSIS_PERIOD_INVALID`

---

### RN-016.3: Detecção de Procedimentos Não Faturados
**Criticidade**: CRÍTICA
**Categoria**: Cruzamento de Dados

**Descrição**:
Compara registros de procedimentos realizados (EMR) com cobranças submetidas:

**Fontes de Dados**:
- **Documentação Clínica**: Procedimentos documentados por médicos/enfermeiros
- **Billing Records**: Procedimentos efetivamente faturados

**Algoritmo de Detecção**:
```
FOR EACH procedimento in EMR.procedures:
    IF NOT EXISTS(billing.procedures WHERE code = procedimento.code):
        missedCharges.add({
            category: "PROCEDURE",
            code: procedimento.code,
            description: procedimento.description,
            estimatedCharge: getProcedurePrice(procedimento.code),
            serviceDate: procedimento.date,
            provider: procedimento.provider
        })
```

**Categorias de Procedimentos**:
- Cirurgias (CPT 10000-69999)
- Radiologia (CPT 70000-79999)
- Laboratório (CPT 80000-89999)
- Medicina (CPT 90000-99999)

---

### RN-016.4: Detecção de Suprimentos Não Cobrados
**Criticidade**: ALTA
**Categoria**: Análise de Inventário

**Descrição**:
Identifica materiais e medicamentos utilizados mas não cobrados:

**Fontes de Dados**:
- **Sistema de Inventário**: Materiais dispensados para o paciente
- **Billing Records**: Suprimentos faturados (revenue code 270-279)

**Algoritmo de Detecção**:
```
FOR EACH item in Inventory.dispensedItems:
    IF item.billable == true:
        IF NOT EXISTS(billing.supplies WHERE item_code = item.code):
            missedCharges.add({
                category: "SUPPLY",
                code: item.code,
                description: item.name,
                quantity: item.quantity,
                unitPrice: item.unitCost,
                estimatedCharge: item.quantity * item.unitCost,
                dispensedDate: item.dispensedDate
            })
```

**Exemplos de Suprimentos**:
- Implantes ortopédicos (alto valor)
- Medicamentos de alto custo (quimioterapia, biológicos)
- Próteses e órteses
- Materiais cirúrgicos descartáveis

---

### RN-016.5: Detecção de Exames/Imagens Sem Cobrança
**Criticidade**: ALTA
**Categoria**: Cruzamento de Sistemas Ancilares

**Descrição**:
Identifica ordens de exames laboratoriais e imagens que não geraram cobrança:

**Fontes de Dados**:
- **Sistema de Laboratório**: Exames coletados e processados
- **Sistema de Radiologia (RIS/PACS)**: Imagens realizadas
- **Billing Records**: Exames faturados

**Algoritmo de Detecção**:
```
FOR EACH order in Lab.completedOrders:
    IF NOT EXISTS(billing.lab WHERE order_id = order.id):
        missedCharges.add({
            category: "LAB",
            code: order.testCode,
            description: order.testName,
            estimatedCharge: getLabPrice(order.testCode),
            collectionDate: order.collectionDate,
            resultDate: order.resultDate
        })

FOR EACH imaging in Radiology.completedStudies:
    IF NOT EXISTS(billing.radiology WHERE study_id = imaging.id):
        missedCharges.add({
            category: "IMAGING",
            code: imaging.cptCode,
            description: imaging.studyDescription,
            estimatedCharge: getImagingPrice(imaging.cptCode),
            studyDate: imaging.studyDate,
            modality: imaging.modality
        })
```

---

### RN-016.6: Cálculo de Perda de Receita Estimada
**Criticidade**: CRÍTICA
**Categoria**: Cálculo Financeiro

**Descrição**:
Calcula o valor total de receita perdida com base nos itens não cobrados:

**Fórmula**:
```
Estimated Revenue Loss = Σ(item.quantity × item.unitPrice)
```

**Considerações**:
- Preços baseados na tabela de preços vigente no momento do serviço
- Considera contratos e descontos aplicáveis
- Não considera write-offs ou ajustes contratuais

**Implementação**:
```java
BigDecimal estimatedRevenueLoss = missedCharges.stream()
    .map(charge -> (BigDecimal) charge.get("estimatedCharge"))
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

**Output**: `estimated_revenue_loss` (BigDecimal)

---

### RN-016.7: Classificação de Prioridade de Recuperação
**Criticidade**: ALTA
**Categoria**: Priorização de Trabalho

**Descrição**:
Classifica a urgência de recuperação com base no valor da perda:

**Thresholds**:
| Prioridade | Valor Mínimo | Ação Recomendada |
|------------|--------------|------------------|
| **HIGH** | ≥ R$ 5.000,00 | Recuperação imediata (24h) |
| **MEDIUM** | R$ 1.000,00 - R$ 4.999,99 | Recuperação em 72h |
| **LOW** | < R$ 1.000,00 | Recuperação em 7 dias |

**Implementação**:
```java
private String determineRecoveryPriority(BigDecimal estimatedRevenueLoss) {
    if (estimatedRevenueLoss.compareTo(HIGH_PRIORITY_THRESHOLD) >= 0) {
        return "HIGH";
    } else if (estimatedRevenueLoss.compareTo(MEDIUM_PRIORITY_THRESHOLD) >= 0) {
        return "MEDIUM";
    } else {
        return "LOW";
    }
}
```

**Constants**:
- `HIGH_PRIORITY_THRESHOLD = R$ 5.000,00`
- `MEDIUM_PRIORITY_THRESHOLD = R$ 1.000,00`

---

### RN-016.8: Geração de Recomendações de Recuperação
**Criticidade**: ALTA
**Categoria**: Plano de Ação

**Descrição**:
Gera lista de ações recomendadas para recuperar as cobranças perdidas:

**Tipos de Recomendações**:
1. **Late Charge Submission**: Submeter cobrança tardia (dentro do prazo payer)
2. **Billing Correction**: Corrigir sinistro já submetido adicionando itens
3. **Documentation Request**: Solicitar documentação adicional do provedor
4. **System Integration Fix**: Corrigir falha de integração entre sistemas
5. **Training Need**: Treinar equipe para prevenir recorrência

**Implementação**:
```java
List<String> recoveryRecommendations = new ArrayList<>();

if (canSubmitLateCharge(missedCharge)) {
    recommendations.add("Submit late charge for " + missedCharge.code);
}

if (requiresDocumentation(missedCharge)) {
    recommendations.add("Request documentation from provider");
}

if (isIntegrationIssue(missedCharge)) {
    recommendations.add("Investigate EMR-billing interface failure");
}
```

**Output**: `recovery_recommendations` (List<String>)

---

### RN-016.9: Breakdown por Categoria
**Criticidade**: MÉDIA
**Categoria**: Análise Detalhada

**Descrição**:
Agrupa cobranças perdidas por categoria para análise de padrões:

**Categorias Rastreadas**:
- PROCEDURE: Procedimentos médicos
- SUPPLY: Materiais e medicamentos
- LAB: Exames laboratoriais
- IMAGING: Exames de imagem
- OTHER: Outros serviços

**Implementação**:
```java
private void logMissedChargesBreakdown(List<Map<String, Object>> missedCharges) {
    Map<String, Integer> categoryBreakdown = new HashMap<>();
    Map<String, BigDecimal> categoryRevenueLoss = new HashMap<>();

    for (Map<String, Object> charge : missedCharges) {
        String category = (String) charge.get("category");
        BigDecimal amount = (BigDecimal) charge.get("estimatedCharge");

        categoryBreakdown.merge(category, 1, Integer::sum);
        categoryRevenueLoss.merge(category, amount, BigDecimal::add);
    }

    log.info("Missed charges breakdown by category:");
    categoryBreakdown.forEach((category, count) -> {
        BigDecimal loss = categoryRevenueLoss.get(category);
        log.info("  {} - Count: {}, Revenue Loss: ${}", category, count, loss);
    });
}
```

---

### RN-016.10: Auditoria e Rastreabilidade
**Criticidade**: ALTA
**Categoria**: Compliance

**Descrição**:
Todos os resultados devem ser auditáveis e rastreáveis:

**Dados Registrados**:
- Data/hora da análise: `detectionCompletedDate`
- Período analisado: `analysisStartDate` - `analysisEndDate`
- Quantidade de cobranças perdidas: `missedChargesCount`
- Perda total de receita: `estimated_revenue_loss`
- Prioridade de recuperação: `recoveryPriority`
- Lista detalhada de itens: `missed_charges`

**Implementação**:
```java
setVariable(execution, "detectionCompletedDate", LocalDateTime.now());
setVariable(execution, "missedChargesCount", missedCharges.size());
setVariable(execution, "estimated_revenue_loss", estimatedRevenueLoss);
```

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `encounterId` | String | Sim | ID único do encontro |
| `analysisStartDate` | LocalDateTime | Não | Data inicial (default: -30 dias) |
| `analysisEndDate` | LocalDateTime | Não | Data final (default: hoje) |

### 3.2 Variáveis de Saída (PROCESS Scope)
| Nome | Tipo | Descrição |
|------|------|-----------|
| `missed_charges` | List<Map> | Lista de cobranças perdidas |
| `estimated_revenue_loss` | BigDecimal | Perda total de receita |
| `recovery_recommendations` | List<String> | Ações recomendadas |
| `missedChargesCount` | Integer | Quantidade de itens detectados |
| `recoveryPriority` | String | HIGH, MEDIUM, LOW |
| `detectionCompletedDate` | LocalDateTime | Timestamp da análise |

### 3.3 Estrutura de `missed_charges`
```json
[
  {
    "category": "PROCEDURE",
    "code": "93000",
    "description": "Electrocardiogram, routine ECG",
    "estimatedCharge": 85.00,
    "serviceDate": "2026-01-10T14:30:00",
    "provider": "Dr. Silva"
  },
  {
    "category": "SUPPLY",
    "code": "J1745",
    "description": "Infliximab, injection",
    "quantity": 100,
    "unitPrice": 12.50,
    "estimatedCharge": 1250.00,
    "dispensedDate": "2026-01-10T15:00:00"
  },
  {
    "category": "LAB",
    "code": "80053",
    "description": "Comprehensive metabolic panel",
    "estimatedCharge": 45.00,
    "collectionDate": "2026-01-10T08:00:00"
  }
]
```

---

## 4. Códigos de Erro BPMN

| Código | Descrição | Ação Recomendada |
|--------|-----------|------------------|
| `ENCOUNTER_NOT_FOUND` | Encontro não existe | Verificar ID do encontro |
| `ANALYSIS_PERIOD_INVALID` | Período de análise inválido | Corrigir datas de início/fim |
| `DETECTION_SERVICE_ERROR` | Erro no serviço de detecção | Verificar logs e conectividade |

---

## 5. Dependências de Serviços

### 5.1 MissedChargesDetectionService
```java
@Autowired
private MissedChargesDetectionService detectionService;

Map<String, Object> detectMissedCharges(
    String encounterId,
    LocalDateTime analysisStartDate,
    LocalDateTime analysisEndDate
);
```

**Retorno**:
```java
{
  "missedCharges": List<Map<String, Object>>,
  "estimatedRevenueLoss": BigDecimal,
  "recoveryRecommendations": List<String>
}
```

---

## 6. Casos de Uso

### 6.1 Detecção com Período Padrão
**Entrada**:
```json
{
  "encounterId": "ENC-2026-001234"
}
```

**Processamento**:
- analysisStartDate = 30 dias atrás
- analysisEndDate = hoje
- Análise completa de procedimentos, suprimentos e exames

**Saída**:
```json
{
  "missedChargesCount": 12,
  "estimated_revenue_loss": 8450.00,
  "recoveryPriority": "HIGH",
  "recovery_recommendations": [
    "Submit late charge for CPT 93000 - Electrocardiogram",
    "Submit late charge for J1745 - Infliximab injection",
    "Request documentation from Dr. Silva for procedure validation"
  ]
}
```

### 6.2 Detecção com Período Customizado
**Entrada**:
```json
{
  "encounterId": "ENC-2026-001234",
  "analysisStartDate": "2026-01-01T00:00:00",
  "analysisEndDate": "2026-01-15T23:59:59"
}
```

**Saída**:
```json
{
  "missedChargesCount": 5,
  "estimated_revenue_loss": 2300.00,
  "recoveryPriority": "MEDIUM"
}
```

---

## 7. Performance e Otimização

### 7.1 Considerações de Performance
- Consultas cruzadas entre múltiplos sistemas (EMR, Billing, Lab, Radiology)
- Volume de dados proporcional ao período analisado
- Períodos > 90 dias podem impactar performance

### 7.2 Recomendações
- Executar em horários de baixa carga
- Considerar processamento assíncrono para grandes períodos
- Implementar cache de preços (tabela de preços)

---

## 8. Logging e Auditoria

### 8.1 Exemplo de Logs
```
INFO: Detecting missed charges: encounterId=ENC-001234, period=2025-12-12 to 2026-01-12
DEBUG: Analysis period validated: 2025-12-12 to 2026-01-12
INFO: Missed charges breakdown by category:
INFO:   PROCEDURE - Count: 5, Revenue Loss: $3250.00
INFO:   SUPPLY - Count: 4, Revenue Loss: $4200.00
INFO:   LAB - Count: 3, Revenue Loss: $1000.00
INFO: Missed charges detection completed: encounterId=ENC-001234, count=12, revenueLoss=8450.00, priority=HIGH
```

---

## 9. Referências

- **Código Fonte**: `src/main/java/com/hospital/revenuecycle/delegates/optimization/DetectMissedChargesDelegate.java`
- **Service**: `MissedChargesDetectionService.java`
- **Subprocesso BPMN**: `SUB_10_Revenue_Maximization.bpmn`
- **Sprint**: Sprint 2 - Target 6 (SWARM_SPRINTS_2_4_EXECUTION_PROTOCOL.md)
- **ADR**: ADR-003 (BPMN Implementation Standards)

---

## X. Conformidade Regulatória

### X.1 Regulamentações Aplicáveis

**ANS (Agência Nacional de Saúde Suplementar)**:
- **RN nº 424/2017**: Padrões de qualidade assistencial e auditoria médica - cobrança completa de procedimentos realizados
- **RN nº 453/2020**: Padrões de integração de sistemas - detecção automatizada de inconsistências entre EMR e billing
- **TISS (Troca de Informações de Saúde Suplementar)**: Rastreamento de procedimentos não faturados

**LGPD (Lei Geral de Proteção de Dados)**:
- **Art. 9º**: Acesso a registros médicos apenas para fins de faturamento legítimo
- **Art. 11º**: Processamento de dados de saúde requer controles rigorosos de auditoria

**SOX (Sarbanes-Oxley)**:
- **Section 302**: Controles internos para detecção de receita não reconhecida
- **Section 404**: Auditoria de processos de reconciliação de receita

### X.2 Obrigações de Conformidade

**Auditoria e Rastreabilidade**:
- Registrar todas as detecções de cobranças perdidas com timestamp e usuário responsável
- Manter log de análises por no mínimo 5 anos (RN ANS 424/2017)
- Documentar razão de cada cobrança perdida identificada

**Privacidade de Dados**:
- Anonimizar dados de pacientes em relatórios agregados de cobranças perdidas
- Acesso restrito aos dados de encontro apenas para usuários autorizados
- Criptografia de dados de saúde em trânsito e repouso

**Controles Financeiros**:
- Separação de funções: equipe que identifica ≠ equipe que submete cobrança
- Aprovação de supervisão para cobranças tardias acima de threshold (R$ 5.000)
- Relatório mensal de receita recuperada vs. receita perdida não recuperável

---

## XI. Notas de Migração

### XI.1 Camunda 7 → Camunda 8

**Impacto**: **BAIXO**

**Mudanças Requeridas**:

1. **Variáveis de Processo**:
   - Camunda 7: `execution.setVariable()` para todas as variáveis
   - Camunda 8: Usar `VariableMap` para variáveis de saída
   ```java
   // Camunda 8
   return Variables.createVariables()
       .putValue("missed_charges", missedCharges)
       .putValue("estimated_revenue_loss", estimatedRevenueLoss);
   ```

2. **Serviços Externos**:
   - Camunda 7: `@Autowired MissedChargesDetectionService`
   - Camunda 8: Considerar job workers para chamadas assíncronas a EMR/Billing

3. **Tratamento de Erros**:
   - Camunda 7: `throw new BpmnError("ENCOUNTER_NOT_FOUND")`
   - Camunda 8: Usar `JobClient.throwBpmnError()` em workers

**Complexidade de Migração**: 2/10 (delegate simples, poucas dependências)

**Breaking Changes**:
- Mudança de API de variáveis (simples refactoring)
- Possível necessidade de worker assíncrono se integrações EMR forem lentas

---

## XII. Mapeamento DDD

### XII.1 Bounded Context

**Revenue Cycle Maximization Context**

### XII.2 Aggregates

**Aggregate Root**: `MissedChargeAnalysis`
- **Entities**:
  - `Encounter` (referência externa)
  - `MissedCharge` (value object)
  - `RecoveryRecommendation` (value object)

**Invariantes**:
- `estimated_revenue_loss` = Σ(`missedCharge.estimatedCharge`)
- `recoveryPriority` deve ser consistente com `estimated_revenue_loss` threshold
- `missedCharges` não pode conter duplicatas de mesmo código

### XII.3 Domain Events

1. **MissedChargesDetected**:
   ```json
   {
     "eventType": "MissedChargesDetected",
     "encounterId": "ENC-001",
     "missedChargesCount": 12,
     "estimatedRevenueLoss": 8450.00,
     "priority": "HIGH",
     "timestamp": "2026-01-12T10:45:00Z"
   }
   ```

2. **HighValueOpportunityIdentified** (quando > R$ 5.000):
   ```json
   {
     "eventType": "HighValueOpportunityIdentified",
     "encounterId": "ENC-001",
     "estimatedRevenueLoss": 12500.00,
     "timestamp": "2026-01-12T10:45:00Z"
   }
   ```

### XII.4 Value Objects

- `MissedCharge`: Imutável, contém categoria, código, valor, data
- `RecoveryRecommendation`: Imutável, contém ação recomendada e prazo
- `RevenueOpportunity`: Imutável, contém estimativa e prioridade

### XII.5 Microservice Candidate

**Viabilidade**: **ALTA**

**Justificativa**:
- Contexto bem delimitado (maximização de receita)
- Baixo acoplamento com outros domínios (apenas leitura de EMR/Billing)
- Operação read-only (não modifica estado de outros sistemas)
- Execução assíncrona aceitável

**API Proposta**:
```
POST /revenue-maximization/detect-missed-charges
GET  /revenue-maximization/analysis/{encounterId}
GET  /revenue-maximization/opportunities (lista de oportunidades pendentes)
```

---

## XIII. Metadados Técnicos

### XIII.1 Complexidade

**Complexidade Ciclomática**: **MÉDIA** (6-8)
- Múltiplas fontes de dados (EMR, Billing, Lab, Radiology)
- Lógica de cruzamento de dados entre sistemas
- Classificação de prioridade com múltiplos thresholds

**Complexidade de Integração**: **ALTA**
- 4+ sistemas externos (EMR, Billing, Lab, Radiology, Inventory)
- Consultas cross-database
- Potencial impacto de performance

### XIII.2 Cobertura de Testes

**Target**: ≥ 85%

**Casos de Teste Obrigatórios**:
1. Detecção de procedimentos não faturados
2. Detecção de suprimentos não cobrados
3. Detecção de exames sem cobrança
4. Cálculo correto de perda de receita
5. Classificação de prioridade (HIGH/MEDIUM/LOW)
6. Validação de período de análise inválido
7. Tratamento de encontro inexistente
8. Período > 90 dias (warning de performance)

### XIII.3 Impacto de Performance

**Criticidade**: **ALTA**

**Gargalos**:
- Consultas JOIN entre EMR.procedures e billing.procedures
- Volume de dados proporcional ao período analisado
- Consultas a múltiplos sistemas ancilares

**Otimizações**:
- Índices em `procedure_code` e `encounter_id`
- Cache de tabela de preços
- Execução em horários de baixa carga
- Processamento assíncrono para períodos > 30 dias

**SLA**: < 30 segundos para período padrão (30 dias)

### XIII.4 Dependências

**Serviços Internos**:
- `MissedChargesDetectionService` (service layer)

**Sistemas Externos**:
- EMR (Electronic Medical Record) - procedimentos documentados
- Billing System - procedimentos faturados
- Laboratory System - exames realizados
- Radiology System (RIS/PACS) - imagens realizadas
- Inventory System - materiais dispensados

**Infraestrutura**:
- Database: PostgreSQL 12+ (suporte a queries complexas)
- Cache: Redis (opcional, para tabela de preços)

---

**Documento gerado por**: AI Swarm - Hive Mind Documentation Generator
**Revisão**: Necessária por faturamento e gestão financeira
**Próxima revisão**: Trimestral ou quando houver mudanças nos thresholds de prioridade
