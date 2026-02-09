# RN-IdentifyUpsellDelegate - Identificação de Oportunidades de Upsell

## Identificação
- **ID**: RN-OPT-001
- **Nome**: IdentifyUpsellDelegate
- **Categoria**: Revenue Optimization
- **Subprocess**: SUB_10_Revenue_Cycle_Optimization
- **Versão**: 2.0.0
- **Bean BPMN**: `identifyUpsellDelegate`
- **Prioridade**: CRÍTICA
- **Autor**: AI Swarm - Sprint 2 Implementation

## Visão Geral
Delegate responsável por identificar oportunidades de upsell durante o atendimento, analisando procedimentos realizados e sugerindo procedimentos adicionais baseados em padrões históricos, compatibilidade com plano de saúde e algoritmos de machine learning.

## Responsabilidades

### 1. Análise de Procedimentos
- Analisa códigos de procedimentos do atendimento atual
- Identifica procedimentos frequentemente realizados em conjunto
- Considera especialidade médica e contexto clínico
- Avalia histórico de atendimentos similares

### 2. Verificação de Cobertura
- Valida cobertura do plano de saúde para upsells
- Considera co-participação e limites de reembolso
- Verifica autorização prévia necessária
- Calcula impacto financeiro para hospital e paciente

### 3. Cálculo de Receita Potencial
- Estima receita adicional de cada oportunidade
- Considera tabela de preços do plano
- Calcula ROI esperado
- Prioriza oportunidades por valor

### 4. Pontuação de Confiança
- Gera score de confiança (0.0-1.0) para cada sugestão
- Baseia-se em:
  - Frequência histórica de combinação
  - Similaridade clínica
  - Taxa de aprovação do plano
  - Satisfação do paciente em casos similares

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `encounterId` | String | Sim | Identificador único do atendimento |
| `procedureCodes` | List&lt;String&gt; | Sim | Códigos TUSS dos procedimentos já realizados |
| `patientId` | String | Sim | Identificador do paciente |
| `insurancePlan` | String | Sim | Plano de saúde do paciente |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `upsell_opportunities` | List&lt;Map&lt;String, Object&gt;&gt; | Lista de oportunidades identificadas |
| `estimated_additional_revenue` | BigDecimal | Receita adicional total estimada |
| `confidence_score` | Double | Score de confiança médio 0.0-1.0 |
| `upsell_opportunities_found` | Boolean | `true` se encontrou oportunidades |
| `upsell_check_timestamp` | Long | Timestamp da análise (millis) |
| `upsell_count` | Integer | Número de oportunidades identificadas |
| `upsellAnalysisRecord` | ObjectValue | Registro completo da análise (JSON) |

## Estrutura de Oportunidade de Upsell

```java
{
    "procedureCode": "40301010",
    "procedureName": "Ressonância Magnética de Crânio",
    "estimatedRevenue": 1500.00,
    "confidenceScore": 0.85,
    "coveredByPlan": true,
    "requiresPriorAuth": false,
    "clinicalJustification": "Complementar diagnóstico de ...",
    "historicalFrequency": 78,
    "averageApprovalTime": 24
}
```

## Algoritmo de Identificação

```
1. Validar entrada:
   - encounterId, procedureCodes, patientId, insurancePlan não nulos

2. Executar UpsellAnalysisService:
   - analyzeUpsellOpportunities(encounterId, procedureCodes, patientId, insurancePlan)

3. Extrair resultados:
   - List<Map> opportunities = analysisResult.get("opportunities")
   - BigDecimal estimatedRevenue = analysisResult.get("estimated_revenue")
   - Double confidenceScore = analysisResult.get("confidence_score")

4. Persistir variáveis de saída:
   - upsell_opportunities
   - estimated_additional_revenue
   - confidence_score
   - upsell_opportunities_found = !opportunities.isEmpty()

5. Criar registro de análise:
   - analysis_id: UUID
   - encounter_id
   - process_instance_id
   - opportunities_count
   - opportunities (lista completa)
   - estimated_revenue
   - confidence_score
   - analyzed_at: LocalDateTime
   - analyzed_by: "upsell_analysis_system"

6. Registrar log com resumo
```

## Integração com UpsellAnalysisService

### Método Principal
```java
Map<String, Object> analysisResult =
    upsellAnalysisService.analyzeUpsellOpportunities(
        encounterId,
        procedureCodes,
        patientId,
        insurancePlan
    );
```

### Retorno do Serviço
```java
{
    "opportunities": [
        {
            "procedureCode": "...",
            "procedureName": "...",
            "estimatedRevenue": ...,
            "confidenceScore": ...,
            ...
        }
    ],
    "estimated_revenue": BigDecimal,
    "confidence_score": Double
}
```

## Casos de Uso

### Caso 1: Alta Oportunidade de Upsell
**Entrada**:
```json
{
  "encounterId": "ATD-2025-001",
  "procedureCodes": ["40301010", "40301020"],
  "patientId": "PAT-12345",
  "insurancePlan": "UNIMED-PREMIUM"
}
```

**Saída**:
```json
{
  "upsell_opportunities": [
    {
      "procedureCode": "40301030",
      "procedureName": "Ressonância Magnética de Abdômen",
      "estimatedRevenue": 2000.00,
      "confidenceScore": 0.92,
      "coveredByPlan": true,
      "requiresPriorAuth": false
    },
    {
      "procedureCode": "40301040",
      "procedureName": "Ultrassonografia Doppler",
      "estimatedRevenue": 800.00,
      "confidenceScore": 0.78,
      "coveredByPlan": true,
      "requiresPriorAuth": false
    }
  ],
  "estimated_additional_revenue": 2800.00,
  "confidence_score": 0.85,
  "upsell_opportunities_found": true,
  "upsell_count": 2
}
```

### Caso 2: Nenhuma Oportunidade Identificada
**Entrada**:
```json
{
  "encounterId": "ATD-2025-002",
  "procedureCodes": ["10101012"],
  "patientId": "PAT-67890",
  "insurancePlan": "BASICO"
}
```

**Saída**:
```json
{
  "upsell_opportunities": [],
  "estimated_additional_revenue": 0.00,
  "confidence_score": 0.0,
  "upsell_opportunities_found": false,
  "upsell_count": 0
}
```

### Caso 3: Oportunidade com Autorização Prévia
**Entrada**:
```json
{
  "encounterId": "ATD-2025-003",
  "procedureCodes": ["40301010"],
  "patientId": "PAT-11111",
  "insurancePlan": "AMIL"
}
```

**Saída**:
```json
{
  "upsell_opportunities": [
    {
      "procedureCode": "40301050",
      "procedureName": "PET-CT Oncológico",
      "estimatedRevenue": 5000.00,
      "confidenceScore": 0.65,
      "coveredByPlan": true,
      "requiresPriorAuth": true,
      "averageApprovalTime": 72
    }
  ],
  "estimated_additional_revenue": 5000.00,
  "confidence_score": 0.65,
  "upsell_opportunities_found": true,
  "upsell_count": 1
}
```

## Regras de Negócio

### RN-OPT-001-001: Validação de Parâmetros
- **Descrição**: Parâmetros obrigatórios devem ser fornecidos
- **Prioridade**: CRÍTICA
- **Validação**: `encounterId, procedureCodes, patientId, insurancePlan != null`

### RN-OPT-001-002: Threshold de Confiança
- **Descrição**: Apenas sugestões com confidence >= 0.6 são retornadas
- **Prioridade**: ALTA
- **Threshold**: 0.6 (60%)

### RN-OPT-001-003: Cobertura do Plano
- **Descrição**: Validar cobertura do plano antes de sugerir
- **Prioridade**: CRÍTICA
- **Validação**: `coveredByPlan == true`

### RN-OPT-001-004: ROI Mínimo
- **Descrição**: Receita estimada deve ser >= R$ 500,00
- **Prioridade**: MÉDIA
- **Validação**: `estimatedRevenue >= 500.00`

## Cálculo de Receita Potencial

### Fórmula
```
estimated_revenue = procedure_price * approval_rate * reimbursement_rate

Onde:
- procedure_price: Preço do procedimento na tabela do plano
- approval_rate: Taxa histórica de aprovação (0.0-1.0)
- reimbursement_rate: Taxa de reembolso do plano (0.0-1.0)
```

### Exemplo
```
Procedimento: Ressonância Magnética
- procedure_price: R$ 2.500,00
- approval_rate: 0.90 (90% aprovado historicamente)
- reimbursement_rate: 0.80 (plano reembolsa 80%)

estimated_revenue = 2500 * 0.90 * 0.80 = R$ 1.800,00
```

## Cálculo de Score de Confiança

### Fórmula
```
confidence_score = weighted_average([
    historical_frequency_score * 0.40,
    clinical_similarity_score * 0.30,
    plan_approval_rate * 0.20,
    patient_satisfaction_score * 0.10
])
```

### Componentes
1. **Historical Frequency Score**: Frequência de combinação em histórico
2. **Clinical Similarity Score**: Similaridade clínica entre procedimentos
3. **Plan Approval Rate**: Taxa de aprovação do plano
4. **Patient Satisfaction Score**: Satisfação em casos similares

## Análise de Registro (UpsellAnalysisRecord)

### Estrutura JSON
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "ATD-2025-001",
  "process_instance_id": "proc-123-abc",
  "opportunities_count": 2,
  "opportunities": [ ... ],
  "estimated_revenue": 2800.00,
  "confidence_score": 0.85,
  "analyzed_at": "2025-01-12T10:30:00",
  "analyzed_by": "upsell_analysis_system"
}
```

## Idempotência

**Requer Idempotência**: Não

**Justificativa**: Análise de upsell é operação read-only e pode ser executada múltiplas vezes sem efeitos colaterais. Resultados podem variar baseado em dados atualizados.

## Conformidade Regulatória

### CFM (Conselho Federal de Medicina)
- Sugestões devem ter justificativa clínica
- Decisão final é sempre do médico assistente

### ANS (Agência Nacional de Saúde)
- Validar cobertura conforme rol da ANS
- Respeitar prazos de autorização prévia

## Métricas e KPIs

### Indicadores de Performance
- **Taxa de Conversão de Upsell**: `(upsells aceitos / total sugerido) * 100%`
- **Receita Adicional Média**: `AVG(estimated_additional_revenue | upsell_accepted)`
- **Score Médio de Confiança**: `AVG(confidence_score)`
- **Taxa de Aprovação por Plano**: `(aprovados / sugeridos) * 100%` por insurancePlan

### Metas
- Taxa de Conversão > 30%
- Receita Adicional Média > R$ 1.000,00
- Score Médio de Confiança > 0.75

## Dependências
- **UpsellAnalysisService**: Serviço de análise de upsell com ML
- **Historical Data**: Base de dados histórica de atendimentos
- **Plan Coverage Data**: Dados de cobertura de planos de saúde

## Versionamento
- **v1.0.0**: Implementação inicial com análise básica
- **v2.0.0**: Adicionado ML e confidence score avançado

## Referências
- RN-DetectMissedCharges: Detecta procedimentos não cobrados
- RN-ProcessMining: Análise de padrões de processos
- Machine Learning Models: Modelos de predição de upsell
