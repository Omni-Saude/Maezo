# RN-AnaliseIndicadoresCompensationStrategy - Estratégia de Compensação para Análise de Indicadores

**Arquivo:** `src/main/java/com/hospital/revenuecycle/domain/compensation/strategies/AnaliseIndicadoresCompensationStrategy.java`

**Tipo:** Estratégia de Compensação SAGA

**Versão:** 2.0

**Última Atualização:** 2025-12-25

---

## 1. VISÃO GERAL

### 1.1 Descrição
Implementa estratégia de compensação para reverter registros de analytics, relatórios gerados, e dados de métricas em processos de análise de indicadores quando ocorrem falhas no fluxo SAGA.

### 1.2 Propósito
- Remover registros de analytics criados
- Deletar relatórios gerados temporariamente
- Limpar cache de métricas
- Resetar dados de dashboard

### 1.3 Tipo de Compensação
```java
@Override
public String getCompensationType() {
    return "ANALISE_INDICADORES";
}
```

---

## 2. REGRAS DE NEGÓCIO

### RN-ANALIND-001: Remoção de Registros Analíticos
**Descrição:** O sistema deve remover registros analíticos criados durante processo falhado.

**Critérios:**
- Identificar registros pelo analyticsId
- Remover apenas registros temporários
- Preservar dados históricos consolidados
- Manter log de remoção para auditoria

**Implementação:**
```java
private void removeAnalyticsRecords(String analyticsId) {
    log.debug("Removing analytics records: {}", analyticsId);
    // TODO: Integration with analytics database
}
```

### RN-ANALIND-002: Deleção de Relatórios Gerados
**Descrição:** O sistema deve deletar relatórios temporários gerados durante processamento.

**Critérios:**
- Verificar se reportId existe
- Deletar arquivos de relatório do storage
- Remover referências no banco de dados
- Não deletar relatórios já publicados

**Implementação:**
```java
private void deleteGeneratedReports(String reportId) {
    log.debug("Deleting generated reports: {}", reportId);
    // TODO: Integration with report storage
}
```

### RN-ANALIND-003: Limpeza de Cache de Métricas
**Descrição:** O sistema deve limpar métricas em cache relacionadas ao processo falhado.

**Critérios:**
- Identificar chaves de cache pelo analyticsId
- Invalidar cache de métricas calculadas
- Limpar cache distribuído (Redis)
- Permitir recálculo em nova execução

**Implementação:**
```java
private void clearCachedMetrics(String analyticsId) {
    log.debug("Clearing cached metrics for analytics: {}", analyticsId);
    // TODO: Integration with cache service
}
```

### RN-ANALIND-004: Reset de Dados de Dashboard
**Descrição:** O sistema deve resetar dados de dashboard afetados pelo processo.

**Critérios:**
- Identificar widgets afetados
- Remover dados temporários de visualização
- Restaurar estado anterior do dashboard
- Manter configurações de dashboard intactas

**Implementação:**
```java
private void resetDashboardData(String analyticsId) {
    log.debug("Resetting dashboard data for analytics: {}", analyticsId);
    // TODO: Integration with dashboard service
}
```

---

## 3. ESTRUTURA DE DADOS

### 3.1 Variáveis de Contexto
```java
CompensationContext {
    String analyticsId;        // ID do processo analítico
    String reportId;           // ID do relatório gerado
    String processInstanceId;  // ID da instância SAGA
}
```

---

## 4. FLUXO DE EXECUÇÃO

### 4.1 Sequência de Compensação
```
1. Remover Registros Analíticos (analyticsId)
   ↓
2. Deletar Relatórios Gerados (reportId)
   ↓
3. Limpar Cache de Métricas
   ↓
4. Resetar Dados de Dashboard
   ↓
5. Log de Conclusão
```

### 4.2 Código de Execução
```java
@Override
public void execute(CompensationContext context) throws Exception {
    String analyticsId = context.getVariable("analyticsId", String.class);
    String reportId = context.getVariable("reportId", String.class);

    log.info("[COMPENSATION] Executing analise indicadores rollback - AnalyticsId: {}, ReportId: {}",
             analyticsId, reportId);

    // Step 1: Remove analytics records
    if (analyticsId != null) {
        removeAnalyticsRecords(analyticsId);
    }

    // Step 2: Delete generated reports
    if (reportId != null) {
        deleteGeneratedReports(reportId);
    }

    // Step 3: Clear cached metrics
    clearCachedMetrics(analyticsId);

    // Step 4: Reset dashboard data
    resetDashboardData(analyticsId);

    log.info("[COMPENSATION] Analise indicadores rollback completed - AnalyticsId: {}", analyticsId);
}
```

---

## 5. INTEGRAÇÕES

### 5.1 Analytics Database
- **Operação:** Remoção de registros
- **Tipo:** SQL DELETE
- **Tabelas:** analytics_records, metrics_temp

### 5.2 Report Storage Service
- **Operação:** Deleção de arquivos
- **Método:** API REST ou S3
- **Endpoint:** `/api/reports/{id}/delete`

### 5.3 Cache Service (Redis)
- **Operação:** Invalidação de cache
- **Comando:** DEL analytics:{analyticsId}:*
- **Pattern:** Wildcard key deletion

### 5.4 Dashboard Service
- **Operação:** Reset de dados
- **Método:** API REST
- **Endpoint:** `/api/dashboard/reset`

---

## 6. CENÁRIOS DE COMPENSAÇÃO

### 6.1 Cenário: Falha no Cálculo de KPIs
**Situação:** Processo de cálculo de KPIs falha após gerar registros parciais

**Ações:**
1. Remover KPIs calculados parcialmente
2. Deletar relatórios preliminares
3. Limpar cache de cálculos intermediários
4. Resetar widgets do dashboard

### 6.2 Cenário: Timeout em Geração de Relatório
**Situação:** Timeout na geração de relatório complexo

**Ações:**
1. Remover registros de progresso
2. Deletar arquivo parcial de relatório
3. Limpar cache de dados agregados
4. Restaurar estado do dashboard

---

## 7. AUDITORIA E MONITORAMENTO

### 7.1 Logs de Compensação
```
[COMPENSATION] Executing analise indicadores rollback - AnalyticsId: {analyticsId}, ReportId: {reportId}, ProcessInstance: {processInstanceId}
[COMPENSATION] Analise indicadores rollback completed - AnalyticsId: {analyticsId}, ProcessInstance: {processInstanceId}
```

### 7.2 Métricas
- Número de compensações executadas
- Tempo médio de compensação
- Taxa de sucesso de limpeza de cache
- Volume de dados removidos

---

## 8. TRATAMENTO DE ERROS

### 8.1 Exceções
- `AnalyticsRecordNotFoundException`: Registro não encontrado
- `ReportDeletionException`: Falha ao deletar relatório
- `CacheClearException`: Erro na limpeza de cache

### 8.2 Retry Policy
- Tentativas: 3x
- Backoff: Exponential (2s, 4s, 8s)
- Circuit breaker ativado após 5 falhas consecutivas

---

## 9. CONFORMIDADE

### 9.1 LGPD/GDPR
- Dados analíticos devem ser removidos completamente
- Cache deve ser limpo sem deixar vestígios
- Logs de compensação devem ser anonimizados

### 9.2 Retenção de Dados
- Relatórios deletados: Log mantido por 90 dias
- Registros removidos: Backup mantido por 30 dias
- Cache limpo: Sem retenção

---

## 10. TESTES

### 10.1 Casos de Teste
```java
@Test
void shouldRemoveAnalyticsRecordsSuccessfully() {
    // Given: analyticsId exists
    // When: compensation executed
    // Then: records removed from database
}

@Test
void shouldDeleteGeneratedReportsFromStorage() {
    // Given: reportId with generated file
    // When: compensation executed
    // Then: file deleted from storage
}

@Test
void shouldClearCacheCompletely() {
    // Given: cached metrics exist
    // When: compensation executed
    // Then: cache keys deleted
}
```

---

## 11. IMPLEMENTAÇÃO FUTURA

### 11.1 Melhorias
- [ ] Backup automático antes de deleção
- [ ] Compensação assíncrona para grandes volumes
- [ ] Notificação aos usuários afetados
- [ ] Dashboard de monitoramento de compensações

### 11.2 Dependências Externas
- Sistema de analytics (Power BI, Tableau)
- Storage de relatórios (S3, Azure Blob)
- Cache distribuído (Redis Cluster)
- Dashboard service (Grafana, Custom)

---

**Data de Criação:** 2026-01-12
**Autor:** Hive Mind Swarm - Coder Agent
**Revisão:** v1.0
