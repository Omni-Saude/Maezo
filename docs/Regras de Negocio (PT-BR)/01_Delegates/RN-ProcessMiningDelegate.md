# RN-ProcessMiningDelegate - Mineração e Análise de Processos

## Identificação
- **ID**: RN-OPT-002
- **Nome**: ProcessMiningDelegate
- **Categoria**: Revenue Optimization
- **Subprocess**: SUB_10_Revenue_Cycle_Optimization
- **Versão**: 1.0.0
- **Bean BPMN**: `processMiningDelegate`
- **Prioridade**: CRÍTICA

## Visão Geral
Delegate responsável por analisar workflows do ciclo de receita usando técnicas de process mining, identificando caminhos de execução, gargalos, retrabalhos e utilização de recursos para otimização contínua.

## Responsabilidades

### 1. Análise de Caminhos de Execução
- Identifica todos os caminhos de execução do processo
- Determina "happy path" (caminho mais frequente)
- Calcula frequência de cada variante de processo
- Identifica desvios do fluxo padrão

### 2. Identificação de Gargalos
- Detecta atividades com maior tempo de espera
- Calcula duração média por atividade
- Identifica atividades críticas no caminho
- Prioriza gargalos por impacto

### 3. Análise de Retrabalho
- Identifica loops e atividades repetidas
- Calcula taxa de retrabalho por atividade
- Quantifica impacto do retrabalho no tempo total
- Sugere melhorias para reduzir retrabalho

### 4. Utilização de Recursos
- Analisa carga de trabalho por usuário/grupo
- Identifica recursos sub/sobreutilizados
- Calcula tempo médio de execução por recurso
- Sugere redistribuição de carga

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `process_key_to_analyze` | String | Não | Chave do processo a analisar (default: ORCH_Ciclo_Receita_Hospital_Futuro) |
| `analysis_period_days` | Integer | Não | Período de análise em dias (default: 30) |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `process_mining_completed` | Boolean | `true` se análise foi concluída |
| `process_mining_timestamp` | Long | Timestamp da análise (millis) |
| `total_instances_analyzed` | Integer | Número de instâncias analisadas |
| `avg_cycle_time_minutes` | Double | Tempo médio de ciclo (minutos) |
| `completion_rate` | Double | Taxa de conclusão (%) |
| `total_execution_paths` | Integer | Número de caminhos de execução identificados |
| `happy_path_frequency` | Integer | Frequência do caminho principal |
| `bottlenecks_identified` | Integer | Número de gargalos identificados |
| `top_bottleneck_activity` | String | ID da atividade com maior gargalo |
| `top_bottleneck_avg_duration_minutes` | Double | Duração média do maior gargalo (min) |
| `rework_patterns_found` | Integer | Número de padrões de retrabalho encontrados |
| `rework_rate_percentage` | Double | Taxa de retrabalho (%) |
| `active_resources` | Integer | Número de recursos ativos |
| `top_resource_user_id` | String | Usuário com maior carga |
| `top_resource_tasks_completed` | Integer | Tarefas completadas pelo top resource |
| `optimization_potential_savings` | Double | Potencial de economia estimado (R$) |
| `optimization_recommendations` | String | Recomendações de otimização |

## Algoritmo de Análise

```
1. Obter parâmetros:
   - process_key_to_analyze (default: "ORCH_Ciclo_Receita_Hospital_Futuro")
   - analysis_period_days (default: 30)

2. Executar ProcessMiningService:
   - result = processMiningService.analyzeProcess(processKey, analysisPeriodDays)

3. Extrair métricas gerais:
   - total_instances_analyzed
   - avg_cycle_time_minutes
   - completion_rate

4. Analisar caminhos de execução:
   - total_execution_paths = result.getExecutionPaths().size()
   - happy_path_frequency = result.getExecutionPaths().get(0).getFrequency()

5. Identificar gargalos:
   - bottlenecks_identified = result.getBottlenecks().size()
   - top_bottleneck_activity
   - top_bottleneck_avg_duration_minutes

6. Analisar retrabalho:
   - rework_patterns_found = result.getReworkPatterns().size()
   - Calcular rework_rate_percentage

7. Analisar recursos:
   - active_resources = result.getResourceUtilization().size()
   - top_resource_user_id
   - top_resource_tasks_completed

8. Calcular potencial de otimização:
   - optimization_potential_savings = calculateOptimizationPotential(result)

9. Gerar recomendações:
   - optimization_recommendations = generateRecommendations(result)

10. Persistir todas variáveis de saída
```

## Estrutura de ProcessMiningResult

```java
class ProcessMiningResult {
    int totalInstances;
    double averageCycleTimeMinutes;
    double completionRate;
    List<ExecutionPath> executionPaths;
    List<Bottleneck> bottlenecks;
    List<ReworkPattern> reworkPatterns;
    List<ResourceUtilization> resourceUtilization;
}

class ExecutionPath {
    String pathId;
    List<String> activities;
    int frequency;
    boolean isHappyPath;
}

class Bottleneck {
    String activityId;
    double averageDurationMinutes;
    int instanceCount;
}

class ReworkPattern {
    String activityId;
    int instancesWithRework;
    double avgReworkCount;
}

class ResourceUtilization {
    String userId;
    int tasksCompleted;
    double avgTaskDurationMinutes;
}
```

## Casos de Uso

### Caso 1: Análise de 30 Dias
**Entrada**:
```json
{
  "process_key_to_analyze": "ORCH_Ciclo_Receita_Hospital_Futuro",
  "analysis_period_days": 30
}
```

**Saída**:
```json
{
  "process_mining_completed": true,
  "total_instances_analyzed": 1250,
  "avg_cycle_time_minutes": 180.5,
  "completion_rate": 92.3,
  "total_execution_paths": 8,
  "happy_path_frequency": 850,
  "bottlenecks_identified": 3,
  "top_bottleneck_activity": "Activity_ApplyContractRules",
  "top_bottleneck_avg_duration_minutes": 45.2,
  "rework_patterns_found": 2,
  "rework_rate_percentage": 12.5,
  "active_resources": 25,
  "optimization_potential_savings": 125000.00,
  "optimization_recommendations": "BOTTLENECKS: Activity_ApplyContractRules (avg: 45.2 min), Activity_ValidateCodes (avg: 30.1 min), REWORK: Activity_SubmitClaim (50 instances), "
}
```

### Caso 2: Análise de Período Curto (7 dias)
**Entrada**:
```json
{
  "process_key_to_analyze": "SUB_05_Billing",
  "analysis_period_days": 7
}
```

**Saída**:
```json
{
  "process_mining_completed": true,
  "total_instances_analyzed": 320,
  "avg_cycle_time_minutes": 95.2,
  "completion_rate": 98.1,
  "total_execution_paths": 4,
  "happy_path_frequency": 280,
  "bottlenecks_identified": 1,
  "rework_patterns_found": 0,
  "rework_rate_percentage": 0.0,
  "optimization_potential_savings": 15000.00
}
```

## Cálculo de Potencial de Otimização

### Fórmula
```
optimization_potential = bottleneck_savings +
                         rework_elimination_savings +
                         cycle_time_improvement_savings

Componentes:
1. Bottleneck Savings (top 3 gargalos):
   - Assume 30% de redução no tempo de gargalo
   - bottleneck_savings = SUM(top 3: avg_duration * 0.3 * $100/min)

2. Rework Elimination Savings:
   - Assume eliminação completa de retrabalho
   - rework_savings = rework_instances * $500/instance

3. Cycle Time Improvement:
   - Assume 20% de redução no tempo total
   - cycle_time_savings = (avg_cycle_time * 0.2) * total_instances * $10/min
```

### Exemplo
```
Cenário:
- Top 3 gargalos: 45min, 30min, 20min
- Instâncias com retrabalho: 50
- Tempo médio de ciclo: 180min
- Total de instâncias: 1000

Cálculo:
1. Bottleneck Savings:
   = (45 + 30 + 20) * 0.3 * 100
   = 95 * 0.3 * 100
   = $2,850

2. Rework Elimination:
   = 50 * 500
   = $25,000

3. Cycle Time Improvement:
   = (180 * 0.2) * 1000 * 10
   = 36 * 1000 * 10
   = $360,000

Total: $387,850
```

## Geração de Recomendações

### Formato
```
"BOTTLENECKS: {activity} (avg: {duration} min), ...
 REWORK: {activity} ({instances} instances), ...
 DEVIATIONS: {deviations} instances deviated from happy path."
```

### Exemplo
```
"BOTTLENECKS: Activity_ApplyContractRules (avg: 45.2 min), Activity_ValidateCodes (avg: 30.1 min), Activity_CheckEligibility (avg: 25.5 min), REWORK: Activity_SubmitClaim (50 instances), Activity_GenerateClaim (30 instances), DEVIATIONS: 400 instances deviated from happy path."
```

## Regras de Negócio

### RN-OPT-002-001: Período Mínimo de Análise
- **Descrição**: Análise requer pelo menos 7 dias de dados
- **Prioridade**: MÉDIA
- **Validação**: `analysis_period_days >= 7`

### RN-OPT-002-002: Identificação de Happy Path
- **Descrição**: Happy path é o caminho de execução mais frequente
- **Prioridade**: ALTA
- **Implementação**: `executionPaths.stream().max(comparingInt(ExecutionPath::getFrequency))`

### RN-OPT-002-003: Threshold de Gargalo
- **Descrição**: Atividade é gargalo se duração > 20 minutos
- **Prioridade**: MÉDIA
- **Threshold**: 20 minutos

### RN-OPT-002-004: Taxa de Retrabalho Aceitável
- **Descrição**: Taxa de retrabalho < 10% é aceitável
- **Prioridade**: MÉDIA
- **Threshold**: 10%

## Integração com ProcessMiningService

### Método Principal
```java
ProcessMiningResult result =
    processMiningService.analyzeProcess(
        processKeyToAnalyze,
        analysisPeriodDays
    );
```

### Análise de Histórico Camunda
```java
// Usa Camunda History API para extrair event logs
List<HistoricActivityInstance> activities =
    historyService.createHistoricActivityInstanceQuery()
        .processDefinitionKey(processKey)
        .startedAfter(startDate)
        .finishedBefore(endDate)
        .orderByHistoricActivityInstanceStartTime().asc()
        .list();
```

## Idempotência

**Requer Idempotência**: Não

**Justificativa**: Análise de process mining é operação read-only e pode ser executada múltiplas vezes sem efeitos colaterais.

## Conformidade Regulatória

### Auditoria
- Registra todas as análises realizadas
- Mantém histórico de recomendações
- Rastreia implementação de melhorias

## Métricas e KPIs

### Indicadores de Otimização
- **Redução de Tempo de Ciclo**: `(tempo_anterior - tempo_atual) / tempo_anterior * 100%`
- **Eliminação de Gargalos**: `(gargalos_anteriores - gargalos_atuais) / gargalos_anteriores * 100%`
- **Redução de Retrabalho**: `(retrabalho_anterior - retrabalho_atual) / retrabalho_anterior * 100%`
- **ROI de Otimizações**: `(economia_realizada / custo_implementação) * 100%`

### Metas
- Redução de Tempo de Ciclo > 20%
- Eliminação de Gargalos > 50%
- Redução de Retrabalho > 30%
- ROI de Otimizações > 300%

## Dependências
- **ProcessMiningService**: Serviço de análise de processos
- **Camunda History API**: API de histórico do Camunda BPM
- **Historical Database**: Base de dados histórica

## Visualização de Resultados

### Dashboard Sugerido
- Gráfico de variantes de processo (Sankey diagram)
- Heatmap de gargalos
- Timeline de execução
- Resource utilization chart
- Rework patterns visualization

## Versionamento
- **v1.0.0**: Implementação inicial com análise básica

## Referências
- RN-IdentifyUpsell: Identificação de oportunidades de receita
- RN-DetectMissedCharges: Detecção de cobranças perdidas
- Process Mining Manifesto: https://www.win.tue.nl/ieeetfpm/
- Camunda History API: https://docs.camunda.org/manual/latest/user-guide/process-engine/history/
