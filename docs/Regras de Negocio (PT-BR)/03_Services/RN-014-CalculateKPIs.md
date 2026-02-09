# RN-014: Cálculo de Indicadores de Desempenho (KPIs)

**Delegate**: `CalculateKPIsDelegate.java`
**Subprocesso BPMN**: SUB_09_Analytics_Reporting
**Prioridade**: CRÍTICA
**Versão**: 1.0
**Última Atualização**: 2026-01-12

---

## 1. Visão Geral

### 1.1 Objetivo
Calcular indicadores-chave de desempenho (KPIs) do ciclo de receita hospitalar para um período específico, fornecendo métricas essenciais para análise gerencial e tomada de decisão.

### 1.2 Escopo
- Cálculo de 7 KPIs críticos do ciclo de receita
- Suporte a filtros de KPIs específicos
- Validação de período de análise
- Geração de métricas agregadas

### 1.3 Stakeholders
- **Primários**: Gestores financeiros, controllers, diretoria executiva
- **Secundários**: Analistas de BI, auditoria interna, compliance

---

## 2. Regras de Negócio

### RN-014.1: Validação de Período de Análise
**Criticidade**: ALTA
**Categoria**: Validação de Entrada

**Descrição**:
O período de análise deve atender aos seguintes critérios:
- Data inicial (startDate) e final (endDate) são obrigatórias
- Data final deve ser igual ou posterior à data inicial
- Ambas as datas devem estar no formato ISO-8601 (YYYY-MM-DD)

**Implementação**:
```java
LocalDate start = LocalDate.parse(startDate);
LocalDate end = LocalDate.parse(endDate);
if (end.isBefore(start)) {
    throw new BpmnError("INVALID_DATE_RANGE",
        "End date must be after or equal to start date");
}
```

**Erro BPMN**: `INVALID_DATE_RANGE`

---

### RN-014.2: Cálculo de Days in A/R (Dias em Contas a Receber)
**Criticidade**: CRÍTICA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula o número médio de dias que as contas levam para serem recebidas após a prestação do serviço.

**Fórmula**:
```
Days in A/R = Contas a Receber Totais / (Receita Bruta / Dias no Período)
```

**Benchmark Indústria**:
- Excelente: < 30 dias
- Bom: 30-45 dias
- Médio: 45-60 dias
- Ruim: > 60 dias

**Implementação**:
```java
if (shouldCalculateKPI("days_in_ar", includeKPIs)) {
    double daysInAR = kpiService.calculateDaysInAR(start, end);
    kpiValues.put("days_in_ar", daysInAR);
}
```

---

### RN-014.3: Cálculo de Collection Rate (Taxa de Cobrança)
**Criticidade**: CRÍTICA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula a taxa de valores efetivamente recebidos em relação ao total faturado.

**Fórmula**:
```
Collection Rate = Pagamentos Recebidos / Cobranças Totais
```

**Benchmark Indústria**:
- Excelente: > 95%
- Bom: 85-95%
- Médio: 75-85%
- Ruim: < 75%

**Implementação**:
```java
if (shouldCalculateKPI("collection_rate", includeKPIs)) {
    double collectionRate = kpiService.calculateCollectionRate(start, end);
    kpiValues.put("collection_rate", collectionRate);
}
```

---

### RN-014.4: Cálculo de Denial Rate (Taxa de Glosa)
**Criticidade**: CRÍTICA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula a porcentagem de sinistros negados ou glosados pelas operadoras.

**Fórmula**:
```
Denial Rate = Sinistros Glosados / Total de Sinistros Submetidos
```

**Benchmark Indústria**:
- Excelente: < 5%
- Bom: 5-10%
- Médio: 10-15%
- Ruim: > 15%

**Implementação**:
```java
if (shouldCalculateKPI("denial_rate", includeKPIs)) {
    double denialRate = kpiService.calculateDenialRate(start, end);
    kpiValues.put("denial_rate", denialRate);
}
```

---

### RN-014.5: Cálculo de Clean Claim Rate (Taxa de Sinistro Limpo)
**Criticidade**: ALTA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula a porcentagem de sinistros aprovados na primeira submissão, sem necessidade de correção ou reenvio.

**Fórmula**:
```
Clean Claim Rate = Sinistros Aprovados na 1ª Submissão / Total de Sinistros
```

**Benchmark Indústria**:
- Excelente: > 90%
- Bom: 80-90%
- Médio: 70-80%
- Ruim: < 70%

**Implementação**:
```java
if (shouldCalculateKPI("clean_claim_rate", includeKPIs)) {
    double cleanClaimRate = kpiService.calculateCleanClaimRate(start, end);
    kpiValues.put("clean_claim_rate", cleanClaimRate);
}
```

---

### RN-014.6: Cálculo de Net Collection Rate (Taxa de Cobrança Líquida)
**Criticidade**: CRÍTICA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula a efetividade de cobrança considerando ajustes contratuais e write-offs.

**Fórmula**:
```
Net Collection Rate = Pagamentos Recebidos / (Cobranças - Ajustes Contratuais)
```

**Benchmark Indústria**:
- Excelente: > 98%
- Bom: 95-98%
- Médio: 90-95%
- Ruim: < 90%

**Implementação**:
```java
if (shouldCalculateKPI("net_collection_rate", includeKPIs)) {
    double netCollectionRate = kpiService.calculateNetCollectionRate(start, end);
    kpiValues.put("net_collection_rate", netCollectionRate);
}
```

---

### RN-014.7: Cálculo de Cost to Collect (Custo para Cobrar)
**Criticidade**: MÉDIA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula o custo operacional como percentual da receita para realizar cobranças.

**Fórmula**:
```
Cost to Collect = Custos Operacionais de Cobrança / Receita Bruta Total
```

**Benchmark Indústria**:
- Excelente: < 2%
- Bom: 2-3%
- Médio: 3-4%
- Ruim: > 4%

**Implementação**:
```java
if (shouldCalculateKPI("cost_to_collect", includeKPIs)) {
    double costToCollect = kpiService.calculateCostToCollect(start, end);
    kpiValues.put("cost_to_collect", costToCollect);
}
```

---

### RN-014.8: Cálculo de Charge Lag Days (Dias de Atraso de Faturamento)
**Criticidade**: ALTA
**Categoria**: Cálculo de KPI

**Descrição**:
Calcula o tempo médio entre a prestação do serviço e a submissão do faturamento.

**Fórmula**:
```
Charge Lag Days = Média(Data de Faturamento - Data de Atendimento)
```

**Benchmark Indústria**:
- Excelente: < 1 dia
- Bom: 1-3 dias
- Médio: 3-5 dias
- Ruim: > 5 dias

**Implementação**:
```java
if (shouldCalculateKPI("charge_lag_days", includeKPIs)) {
    double chargeLagDays = kpiService.calculateChargeLagDays(start, end);
    kpiValues.put("charge_lag_days", chargeLagDays);
}
```

---

### RN-014.9: Filtro de KPIs Específicos
**Criticidade**: MÉDIA
**Categoria**: Controle de Execução

**Descrição**:
O sistema permite calcular apenas KPIs específicos através do parâmetro `includeKPIs`:
- Se `includeKPIs` for null ou vazio: calcula TODOS os 7 KPIs
- Se `includeKPIs` contiver lista: calcula apenas os KPIs especificados

**KPIs Disponíveis**:
- `days_in_ar`
- `collection_rate`
- `denial_rate`
- `clean_claim_rate`
- `net_collection_rate`
- `cost_to_collect`
- `charge_lag_days`

**Implementação**:
```java
private boolean shouldCalculateKPI(String kpiName, List<String> includeKPIs) {
    return includeKPIs == null || includeKPIs.isEmpty() ||
           includeKPIs.contains(kpiName);
}
```

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `startDate` | String | Sim | Data inicial (ISO-8601: "2026-01-01") |
| `endDate` | String | Sim | Data final (ISO-8601: "2026-01-31") |
| `includeKPIs` | List<String> | Não | Lista de KPIs específicos a calcular |

### 3.2 Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| `kpi_calculated` | Boolean | Indica sucesso do cálculo |
| `kpi_values` | Map<String, Object> | Mapa com valores dos KPIs |
| `calculation_timestamp` | String | Timestamp ISO-8601 do cálculo |
| `kpi_error` | String | Mensagem de erro (se falha) |

### 3.3 Estrutura de `kpi_values`
```json
{
  "days_in_ar": 45.2,
  "collection_rate": 0.87,
  "denial_rate": 0.12,
  "clean_claim_rate": 0.78,
  "net_collection_rate": 0.92,
  "cost_to_collect": 3.5,
  "charge_lag_days": 2.1
}
```

---

## 4. Códigos de Erro BPMN

| Código | Descrição | Ação Recomendada |
|--------|-----------|------------------|
| `INVALID_DATE_RANGE` | Data final anterior à inicial | Corrigir intervalo de datas |
| `MISSING_VARIABLE` | Variável obrigatória ausente | Fornecer variável requerida |

---

## 5. Dependências de Serviços

### 5.1 KPICalculationService
Serviço responsável pelos cálculos dos KPIs:
- `calculateDaysInAR(LocalDate start, LocalDate end): double`
- `calculateCollectionRate(LocalDate start, LocalDate end): double`
- `calculateDenialRate(LocalDate start, LocalDate end): double`
- `calculateCleanClaimRate(LocalDate start, LocalDate end): double`
- `calculateNetCollectionRate(LocalDate start, LocalDate end): double`
- `calculateCostToCollect(LocalDate start, LocalDate end): double`
- `calculateChargeLagDays(LocalDate start, LocalDate end): double`

---

## 6. Casos de Uso

### 6.1 Cálculo Completo de KPIs Mensais
**Entrada**:
```json
{
  "startDate": "2026-01-01",
  "endDate": "2026-01-31",
  "includeKPIs": null
}
```

**Saída**:
```json
{
  "kpi_calculated": true,
  "kpi_values": {
    "days_in_ar": 42.5,
    "collection_rate": 0.89,
    "denial_rate": 0.08,
    "clean_claim_rate": 0.85,
    "net_collection_rate": 0.95,
    "cost_to_collect": 2.8,
    "charge_lag_days": 1.5
  },
  "calculation_timestamp": "2026-02-01T10:30:00"
}
```

### 6.2 Cálculo de KPIs Específicos
**Entrada**:
```json
{
  "startDate": "2026-01-01",
  "endDate": "2026-01-31",
  "includeKPIs": ["denial_rate", "clean_claim_rate"]
}
```

**Saída**:
```json
{
  "kpi_calculated": true,
  "kpi_values": {
    "denial_rate": 0.08,
    "clean_claim_rate": 0.85
  },
  "calculation_timestamp": "2026-02-01T10:35:00"
}
```

---

## 7. Conformidade e Auditoria

### 7.1 Regulamentações
- **TISS**: Padrões ANS para indicadores de qualidade
- **CMS Guidelines**: Benchmarks de performance do Medicare
- **ANS Resolução 259/2011**: Indicadores de qualidade setorial

### 7.2 Requisitos de Auditoria
- Todos os cálculos devem ser registrados com timestamp
- Dados fonte devem ser rastreáveis
- Fórmulas devem seguir padrões HFMA (Healthcare Financial Management Association)

---

## 8. Notas de Implementação

### 8.1 Performance
- Cálculos são intensivos em I/O (consultas ao banco)
- Considerar cache para períodos já calculados
- Execução assíncrona recomendada para grandes períodos

### 8.2 Serialização JSON
Os resultados são serializados em JSON para armazenamento no Camunda:
```java
execution.setVariable("kpi_values",
    Variables.objectValue(kpiValues)
        .serializationDataFormat(Variables.SerializationDataFormats.JSON)
        .create());
```

### 8.3 Logging
```
INFO: Calculating KPIs for date range 2026-01-01 to 2026-01-31 (includeKPIs: null)
DEBUG: Days in A/R: 42.5
DEBUG: Collection Rate: 0.89
INFO: KPIs calculated successfully for period 2026-01-01 to 2026-01-31: 7 KPIs computed
```

---

## 9. Referências

- **Código Fonte**: `src/main/java/com/hospital/revenuecycle/delegates/analytics/CalculateKPIsDelegate.java`
- **Service**: `KPICalculationService.java`
- **Subprocesso BPMN**: `SUB_09_Analytics_Reporting.bpmn`
- **ADR**: ADR-003 (BPMN Implementation Standards)
- **HFMA**: Healthcare Financial Management Association - KPI Guidelines

---

## X. Conformidade Regulatória

### 10.1 Requisitos ANS
- **RN 553/2023**: Indicadores de qualidade setorial - cálculo obrigatório de KPIs
- **RN 259/2011**: Programa de Qualificação de Operadoras - métricas de desempenho
- **RN 395/2016**: Submissão eletrônica - rastreabilidade dos cálculos

### 10.2 Conformidade TISS
- **TISS Componente Organizacional**: Padrões de indicadores de qualidade
- **Terminologia**: Nomenclatura padronizada de KPIs conforme ANS

### 10.3 LGPD
- **Art. 13 LGPD**: Anonimização obrigatória - KPIs agregados sem identificação individual
- **Art. 11 LGPD**: Processamento de dados de saúde - finalidade legítima para gestão
- **Retenção**: 5 anos para documentação de indicadores de qualidade

### 10.4 SOX Compliance
- **Seção 302**: Certificação de controles de relatórios financeiros
- **Documentação**: Fórmulas e metodologias de cálculo devem estar documentadas
- **Auditoria**: Rastreabilidade completa da fonte de dados até o relatório final

### 10.5 Trilha de Auditoria
- **Registro obrigatório**: Todos os cálculos com timestamp e período
- **Campos auditáveis**: Fórmulas aplicadas, volumes de dados, resultados
- **Rastreabilidade**: Hash dos dados fonte para validação posterior
- **Período de retenção**: 7 anos (requisitos fiscais e ANS)

---

## X. Notas de Migração - Camunda 7 para Camunda 8

### 10.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: Microserviço Standalone com API REST
- **Implementação**: Analytics Service desacoplado do workflow engine
- **Vantagens**: Escalabilidade independente, caching agressivo, processamento assíncrono

### 10.2 Nível de Complexidade
- **Complexidade de Migração**: MÉDIA-ALTA (5-10 dias)
- **Justificativa**: Lógica complexa de agregação, múltiplas fontes de dados, cálculos intensivos

### 10.3 Breaking Changes
- **Delegate → REST API**: Mudança de padrão sync para API HTTP assíncrona
- **Variáveis**: De Camunda variables para request/response JSON
- **Caching**: Necessidade de implementar cache distribuído (Redis)
- **Batch Processing**: Requer arquitetura de processamento em lote

### 10.4 Arquitetura Camunda 8
```
Zeebe Process → HTTP Service Task → Analytics API
                                   ↓
                         KPI Calculation Service
                                   ↓
                         [Redis Cache] ← [PostgreSQL OLAP]
```

---

## XI. Mapeamento DDD

### 11.1 Bounded Context
- **Contexto Delimitado**: `Analytics & Reporting`
- **Linguagem Ubíqua**: KPI, days in A/R, collection rate, denial rate, benchmark

### 11.2 Aggregate Root
- **Aggregate**: `KPIReport`
- **Entidades relacionadas**:
  - `KPIValue` (valor de um indicador específico)
  - `CalculationPeriod` (período de análise)
  - `BenchmarkThreshold` (limites de performance)

### 11.3 Domain Events
- **KPIsCalculated**: KPIs calculados com sucesso para o período
- **BenchmarkThresholdExceeded**: KPI ultrapassou limite crítico
- **CalculationFailed**: Falha no cálculo (dados insuficientes, erro de sistema)

### 11.4 Value Objects
- `Period` (startDate, endDate)
- `KPIValue` (name, value, unit, benchmark_status)
- `BenchmarkRange` (excellent, good, average, poor)

### 11.5 Candidato a Microserviço
- **Serviço**: `analytics-service`
- **Responsabilidades**: Cálculo de KPIs, geração de relatórios, benchmarking
- **Integrações**: Data Warehouse, Claims Service, Payment Service, External BI Tools

---

## XII. Metadados Técnicos

### 12.1 Características
- **Tipo**: Service Delegate (Camunda 7 JavaDelegate)
- **Execução**: Síncrona (blocking) - pode ser lenta para grandes volumes
- **Idempotência**: Habilitada (evitar recálculo desnecessário)
- **Transacional**: Não (read-only, sem side effects)

### 12.2 Métricas de Qualidade
- **Complexidade Ciclomática**: ALTA (7 KPIs + validações + filtros)
- **Cobertura de Testes Recomendada**: 85% (lógica complexa mas determinística)
- **Tempo de Execução Esperado**: 5-15s (dependente do volume de dados e período)

### 12.3 Impacto de Performance
- **I/O**: HIGH (múltiplas queries agregadas ao banco de dados)
- **CPU**: MEDIUM (cálculos matemáticos moderados)
- **Memória**: MEDIUM (agregação de grandes volumes em memória)

### 12.4 Dependências de Runtime
- Spring Framework (DI)
- Camunda BPM Engine 7.x
- KPICalculationService (custom, com acesso ao banco OLAP)
- SLF4J (logging)

### 12.5 Otimizações Recomendadas
- **Caching**: Redis para períodos já calculados (TTL: 24h)
- **Materialized Views**: Pré-agregar dados em banco para queries rápidas
- **Async Processing**: Para períodos longos (>3 meses), executar em background
- **Batch API**: Calcular múltiplos períodos em uma chamada

---

## X. Conformidade Regulatória

### 10.1 Requisitos ANS
- **RN 553/2023**: Indicadores de qualidade setorial - cálculo obrigatório de KPIs
- **RN 259/2011**: Programa de Qualificação de Operadoras - métricas de desempenho
- **RN 395/2016**: Submissão eletrônica - rastreabilidade dos cálculos

### 10.2 Conformidade TISS
- **TISS Componente Organizacional**: Padrões de indicadores de qualidade
- **Terminologia**: Nomenclatura padronizada de KPIs conforme ANS

### 10.3 LGPD
- **Art. 13 LGPD**: Anonimização obrigatória - KPIs agregados sem identificação individual
- **Art. 11 LGPD**: Processamento de dados de saúde - finalidade legítima para gestão
- **Retenção**: 5 anos para documentação de indicadores de qualidade

### 10.4 SOX Compliance
- **Seção 302**: Certificação de controles de relatórios financeiros
- **Documentação**: Fórmulas e metodologias de cálculo devem estar documentadas
- **Auditoria**: Rastreabilidade completa da fonte de dados até o relatório final

### 10.5 Trilha de Auditoria
- **Registro obrigatório**: Todos os cálculos com timestamp e período
- **Campos auditáveis**: Fórmulas aplicadas, volumes de dados, resultados
- **Rastreabilidade**: Hash dos dados fonte para validação posterior
- **Período de retenção**: 7 anos (requisitos fiscais e ANS)

---

## XI. Notas de Migração - Camunda 7 para Camunda 8

### 11.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: Microserviço Standalone com API REST
- **Implementação**: Analytics Service desacoplado do workflow engine
- **Vantagens**: Escalabilidade independente, caching agressivo, processamento assíncrono

### 11.2 Nível de Complexidade
- **Complexidade de Migração**: MÉDIA-ALTA (5-10 dias)
- **Justificativa**: Lógica complexa de agregação, múltiplas fontes de dados, cálculos intensivos

### 11.3 Breaking Changes
- **Delegate → REST API**: Mudança de padrão sync para API HTTP assíncrona
- **Variáveis**: De Camunda variables para request/response JSON
- **Caching**: Necessidade de implementar cache distribuído (Redis)
- **Batch Processing**: Requer arquitetura de processamento em lote

### 11.4 Arquitetura Camunda 8
```
Zeebe Process → HTTP Service Task → Analytics API
                                   ↓
                         KPI Calculation Service
                                   ↓
                         [Redis Cache] ← [PostgreSQL OLAP]
```

---

## XII. Mapeamento DDD

### 12.1 Bounded Context
- **Contexto Delimitado**: `Analytics & Reporting`
- **Linguagem Ubíqua**: KPI, days in A/R, collection rate, denial rate, benchmark

### 12.2 Aggregate Root
- **Aggregate**: `KPIReport`
- **Entidades relacionadas**:
  - `KPIValue` (valor de um indicador específico)
  - `CalculationPeriod` (período de análise)
  - `BenchmarkThreshold` (limites de performance)

### 12.3 Domain Events
- **KPIsCalculated**: KPIs calculados com sucesso para o período
- **BenchmarkThresholdExceeded**: KPI ultrapassou limite crítico
- **CalculationFailed**: Falha no cálculo (dados insuficientes, erro de sistema)

### 12.4 Value Objects
- `Period` (startDate, endDate)
- `KPIValue` (name, value, unit, benchmark_status)
- `BenchmarkRange` (excellent, good, average, poor)

### 12.5 Candidato a Microserviço
- **Serviço**: `analytics-service`
- **Responsabilidades**: Cálculo de KPIs, geração de relatórios, benchmarking
- **Integrações**: Data Warehouse, Claims Service, Payment Service, External BI Tools

---

## XIII. Metadados Técnicos

### 13.1 Características
- **Tipo**: Service Delegate (Camunda 7 JavaDelegate)
- **Execução**: Síncrona (blocking) - pode ser lenta para grandes volumes
- **Idempotência**: Habilitada (evitar recálculo desnecessário)
- **Transacional**: Não (read-only, sem side effects)

### 13.2 Métricas de Qualidade
- **Complexidade Ciclomática**: ALTA (7 KPIs + validações + filtros)
- **Cobertura de Testes Recomendada**: 85% (lógica complexa mas determinística)
- **Tempo de Execução Esperado**: 5-15s (dependente do volume de dados e período)

### 13.3 Impacto de Performance
- **I/O**: HIGH (múltiplas queries agregadas ao banco de dados)
- **CPU**: MEDIUM (cálculos matemáticos moderados)
- **Memória**: MEDIUM (agregação de grandes volumes em memória)

### 13.4 Dependências de Runtime
- Spring Framework (DI)
- Camunda BPM Engine 7.x
- KPICalculationService (custom, com acesso ao banco OLAP)
- SLF4J (logging)

### 13.5 Otimizações Recomendadas
- **Caching**: Redis para períodos já calculados (TTL: 24h)
- **Materialized Views**: Pré-agregar dados em banco para queries rápidas
- **Async Processing**: Para períodos longos (>3 meses), executar em background
- **Batch API**: Calcular múltiplos períodos em uma chamada

---

**Documento gerado por**: AI Swarm - Hive Mind Documentation Generator
**Revisão**: Necessária por gestor financeiro
**Próxima revisão**: Trimestral ou quando houver mudanças nos benchmarks
**Schema Compliance Fix:** 2026-01-12
