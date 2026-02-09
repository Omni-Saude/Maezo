# RN-BIL-005: Tentativa de Reenvio de Submissão

**ID Técnico**: `RetrySubmissionDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Implementar lógica inteligente de retry para submissões de contas médicas que falharam, utilizando backoff exponencial e análise de erros para determinar se a resubmissão é apropriada.

### 1.2. Contexto de Negócio
A submissão de contas médicas a operadoras de saúde via TISS pode falhar por diversos motivos:

**Erros Transientes (podem ser resolvidos com retry)**:
- Timeout de rede
- Indisponibilidade temporária do sistema TISS
- Erro de conexão
- Sobrecarga momentânea (rate limit)

**Erros Permanentes (não devem ter retry)**:
- Dados de paciente inválidos
- Código de procedimento inexistente
- Autorização expirada ou negada
- Conta duplicada

Implementar uma estratégia inteligente de retry:
- Evita perda de receita por falhas temporárias
- Reduz trabalho manual da equipe de faturamento
- Respeita limites de tentativas para não sobrecarregar sistemas
- Identifica rapidamente erros que requerem intervenção humana

### 1.3. Benefícios Esperados
- **Resiliência**: Submissões bem-sucedidas mesmo com instabilidade de rede
- **Eficiência**: Automação de retentativas reduz trabalho manual
- **Inteligência**: Análise de erros evita tentativas desnecessárias
- **Controle**: Backoff exponencial previne sobrecarga de sistemas
- **Rastreabilidade**: Histórico completo de tentativas para auditoria

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve analisar o erro de submissão, verificar o contador de tentativas, classificar o erro como transiente ou permanente, calcular tempo de backoff exponencial, e decidir se deve reagendar uma nova tentativa ou rejeitar definitivamente.

**Lógica de Execução**:

1. **Verificação de Limite de Tentativas**
   ```
   MAX_RETRIES ← 5
   retryCount ← OBTER_CONTADOR(claimId)

   SE retryCount ≥ MAX_RETRIES:
     LOG ERRO "Máximo de tentativas excedido"
     LANÇAR ERRO "MAX_RETRIES_EXCEEDED"
   ```

2. **Análise de Tipo de Erro**
   ```
   erros_permanentes ← {
     "INVALID_PATIENT_DATA",
     "INSURANCE_EXPIRED",
     "AUTHORIZATION_DENIED",
     "DUPLICATE_CLAIM",
     "INVALID_PROCEDURE_CODE"
   }

   erros_transientes ← {
     "TIMEOUT",
     "CONNECTION_ERROR",
     "SERVICE_UNAVAILABLE",
     "NETWORK_ERROR",
     "RATE_LIMIT",
     "SERVER_ERROR",
     "503", "504"
   }

   erro_upper ← submissionError.PARA_MAIUSCULA()

   SE erro_upper CONTÉM QUALQUER erro_permanente:
     shouldRetry ← FALSO
     LANÇAR ERRO "PERMANENT_ERROR"

   SE erro_upper CONTÉM QUALQUER erro_transiente:
     shouldRetry ← VERDADEIRO

   SENÃO:
     // Erro desconhecido - retry por segurança
     shouldRetry ← VERDADEIRO
     LOG AVISO "Tipo de erro desconhecido, tentando retry"
   ```

3. **Cálculo de Backoff Exponencial**
   ```
   BASE_BACKOFF ← 5 minutos
   MAX_BACKOFF ← 240 minutos (4 horas)

   backoff ← BASE_BACKOFF × 2^retryCount
   backoff ← MIN(backoff, MAX_BACKOFF)

   // Adicionar jitter aleatório (±20%)
   jitter ← backoff × 0.2 × (RANDOM() - 0.5)
   backoff ← backoff + jitter

   // Garantir mínimo
   backoff ← MAX(backoff, BASE_BACKOFF)
   ```

4. **Agendamento de Próxima Tentativa**
   ```
   nextRetryTime ← HORA_ATUAL + backoff_minutos
   newRetryCount ← retryCount + 1

   retryReason ← FORMATAR(
     "Erro transiente, tentativa %d de %d",
     newRetryCount,
     MAX_RETRIES
   )
   ```

5. **Registro de Tentativa**
   ```
   retry_log ← {
     "claimId": claimId,
     "error": submissionError,
     "retryCount": newRetryCount,
     "backoffMinutes": backoff,
     "nextRetryTime": nextRetryTime,
     "timestamp": HORA_ATUAL
   }

   REGISTRAR_AUDITORIA(retry_log)
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-005-V1 | Máximo de 5 tentativas permitido | CRÍTICA | Rejeitar com MAX_RETRIES_EXCEEDED |
| BIL-005-V2 | Erro permanente não deve ter retry | CRÍTICA | Rejeitar com PERMANENT_ERROR |
| BIL-005-V3 | Backoff deve respeitar mínimo e máximo | AVISO | Ajustar para limites |
| BIL-005-V4 | Mensagem de erro obrigatória | CRÍTICA | Rejeitar se erro vazio |
| BIL-005-V5 | Próxima tentativa deve ser futura | CRÍTICA | nextRetryTime > now |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador de conta (claimId) válido
- Mensagem de erro de submissão (submissionError)
- Contador de tentativas atual (retryCount, default 0)
- Timestamp da última tentativa (opcional)

**Exceções de Negócio**:

1. **Máximo de Tentativas Excedido**
   - **Código**: MAX_RETRIES_EXCEEDED
   - **Causa**: retryCount >= 5
   - **Ação**: Encerrar tentativas, marcar para intervenção manual
   - **Próximo Passo**: Equipe de faturamento analisa manualmente

2. **Erro Permanente**
   - **Código**: PERMANENT_ERROR
   - **Causa**: Erro que não pode ser resolvido automaticamente
   - **Ação**: Encerrar tentativas, notificar equipe responsável
   - **Próximo Passo**: Correção de dados ou processo

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador único da conta | Formato: CLM-.*-\d+ |
| `submissionError` | String | Sim | Mensagem de erro da submissão | Não vazio |
| `retryCount` | Integer | Não | Contador de tentativas atual | Default: 0, Max: 5 |
| `lastSubmissionTime` | LocalDateTime | Não | Hora da última tentativa | Usado para análise |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `shouldRetry` | Boolean | Indica se deve tentar novamente | Gateway de decisão |
| `nextRetryTime` | LocalDateTime | Hora agendada para próxima tentativa | Timer de agendamento |
| `retryCount` | Integer | Contador atualizado de tentativas | Controle de limites |
| `retryReason` | String | Motivo da decisão de retry | Auditoria e logs |
| `backoffMinutes` | Integer | Tempo de espera calculado | Métricas |

**Estrutura de Resposta de Retry**:
```json
{
  "shouldRetry": true,
  "retryCount": 2,
  "maxRetries": 5,
  "backoffMinutes": 10,
  "nextRetryTime": "2025-01-12T11:00:00Z",
  "retryReason": "Transient error, retry 2 of 5",
  "errorClassification": "TRANSIENT",
  "originalError": "TIMEOUT - Connection timeout after 30s"
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Backoff Exponencial com Jitter

```
Entrada:
  retryCount = Número da tentativa atual (0-indexed)
  BASE_BACKOFF = 5 minutos
  MAX_BACKOFF = 240 minutos

Cálculo:
  backoff = BASE_BACKOFF × 2^retryCount
  backoff = min(backoff, MAX_BACKOFF)

  jitter = backoff × 0.2 × (random() - 0.5)
  backoff = backoff + jitter

  backoff = max(backoff, BASE_BACKOFF)

Saída:
  backoff (Inteiro, minutos)
```

**Tabela de Backoff**:
| Tentativa | Fórmula | Backoff (minutos) | Backoff (horas) |
|-----------|---------|-------------------|-----------------|
| 1 | 5 × 2^0 | 5 ± 1 | ~5 min |
| 2 | 5 × 2^1 | 10 ± 2 | ~10 min |
| 3 | 5 × 2^2 | 20 ± 4 | ~20 min |
| 4 | 5 × 2^3 | 40 ± 8 | ~40 min |
| 5 | 5 × 2^4 | 80 ± 16 | ~1.3 horas |
| 6+ | min(5 × 2^n, 240) | 160-240 ± jitter | ~2.7-4 horas |

### 4.2. Classificação de Erro

```
Função: classificar_erro(mensagem_erro)

Entrada:
  mensagem_erro (String)

Processamento:
  msg_upper ← mensagem_erro.PARA_MAIUSCULA()

  PARA CADA erro_perm EM erros_permanentes:
    SE msg_upper CONTÉM erro_perm:
      RETORNAR "PERMANENT"

  PARA CADA erro_trans EM erros_transientes:
    SE msg_upper CONTÉM erro_trans:
      RETORNAR "TRANSIENT"

  // Desconhecido - assume transiente por segurança
  RETORNAR "UNKNOWN_TRANSIENT"

Saída:
  Classificação (String)
```

### 4.3. Taxa de Sucesso com Retry

```
Para análise de efetividade:

Taxa_Sucesso_Retry = (Sucessos_Após_Retry / Total_Retries) × 100

Exemplo:
  Total de submissões com retry: 100
  Sucessos após retry: 85
  Taxa de Sucesso = (85 / 100) × 100 = 85%
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Sistema TISS | Resubmissão | XML de conta médica | Web Service SOAP |
| Sistema de Agendamento | Escrita | Agendamento de próxima tentativa | Message Queue |
| Sistema de Auditoria | Escrita | Log de tentativas e erros | Message Queue |
| Sistema de Monitoramento | Escrita | Métricas de retry | Prometheus |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Histórico de tentativas de submissão
- Classificação de tipos de erro
- Configuração de limites de retry
- Status de disponibilidade do TISS

**Frequência de Atualização**:
- Histórico de tentativas: Tempo real
- Status do TISS: A cada 5 minutos
- Configuração de retry: Sob demanda

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Sucesso com Retry | % de submissões bem-sucedidas após retry | ≥ 80% | (Sucessos Retry / Total Retries) × 100 | Diária |
| Tempo Médio até Sucesso | Tempo entre 1ª tentativa e sucesso | ≤ 2 horas | Média de intervalos | Diária |
| Taxa de Erros Permanentes | % de erros que não devem ter retry | < 10% | (Permanentes / Total) × 100 | Semanal |
| Taxa de Esgotamento de Tentativas | % que atinge máximo sem sucesso | < 5% | (MAX_RETRIES / Total) × 100 | Semanal |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Tempo de Processamento | Duração da análise de retry | > 1 segundo | Otimizar lógica |
| Erros MAX_RETRIES_EXCEEDED | Contas que esgotaram tentativas | > 5% | Revisar limites |
| Erros PERMANENT_ERROR | Erros não retriáveis | > 15% | Melhorar validação pré-submissão |
| Distribuição de Backoff | Histograma de tempos de espera | Monitorar | Ajustar algoritmo |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Recebimento de erro de submissão
2. Análise de tipo de erro
3. Verificação de contador de tentativas
4. Cálculo de backoff
5. Decisão de retry (sim/não)
6. Agendamento de próxima tentativa

**Informações Capturadas**:
```json
{
  "timestamp": "2025-01-12T10:40:00Z",
  "claimId": "CLM-001-1234567890",
  "submissionError": "TIMEOUT - Connection timeout",
  "errorClassification": "TRANSIENT",
  "retryCount": 2,
  "maxRetries": 5,
  "backoffMinutes": 10,
  "nextRetryTime": "2025-01-12T10:50:00Z",
  "retryReason": "Transient error, retry 2 of 5",
  "executionTimeMs": 123
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Limites de Retry | Preventivo | Por transação | Sistema automático |
| Auditoria de Erros Permanentes | Detectivo | Diária | Equipe de Qualidade |
| Revisão de Máximos Excedidos | Corretivo | Diária | Equipe de Faturamento |
| Análise de Efetividade de Retry | Detectivo | Semanal | Gestor de TI |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| MAX_RETRIES_EXCEEDED | Máximo de tentativas excedido | CRÍTICA | Escalar para análise manual |
| PERMANENT_ERROR | Erro permanente identificado | CRÍTICA | Corrigir dados e resubmeter manualmente |
| INVALID_ERROR_MESSAGE | Mensagem de erro vazia ou inválida | AVISO | Log e assumir transiente |

### 8.2. Estratégia de Retry

**Este delegate não tem retry próprio** - é o componente que decide retry de outras operações.

**Entretanto, operações internas podem ter retry**:
- Erro ao salvar log de tentativa: 3 retries
- Erro ao agendar próxima tentativa: 3 retries

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Retry por Erro Transiente

**Cenário**: Submissão falhou por timeout, agendar retry

**Pré-condições**:
- Conta CLM-001-123 falhou na submissão
- Erro: "TIMEOUT - Connection timeout after 30s"
- retryCount atual: 1
- maxRetries: 5

**Fluxo**:
1. Sistema recebe erro de timeout
2. Verifica contador: 1 < 5 (OK)
3. Classifica erro: "TIMEOUT" → TRANSIENT
4. Calcula backoff:
   - retryCount = 1
   - backoff = 5 × 2^1 = 10 minutos
   - jitter = ±2 minutos
   - backoff final = 12 minutos
5. Agenda próxima tentativa: 10:40 + 12min = 10:52
6. Incrementa contador: retryCount = 2
7. Define shouldRetry = true
8. Registra em auditoria

**Pós-condições**:
- `shouldRetry` = true
- `retryCount` = 2
- `nextRetryTime` = "2025-01-12T10:52:00Z"
- `backoffMinutes` = 12
- Processo aguarda até 10:52 e tenta novamente

**Resultado**: Retry agendado com sucesso

### 9.2. Fluxo de Exceção - Máximo de Tentativas

**Cenário**: Quinta tentativa falhou, atingiu máximo

**Fluxo**:
1. Sistema recebe erro (5ª tentativa)
2. Verifica contador: 4 >= 5 (EXCEDIDO)
3. Lança erro MAX_RETRIES_EXCEEDED
4. Registra falha definitiva
5. Notifica equipe de faturamento
6. Marca conta para revisão manual

**Ações Subsequentes**:
- Equipe analisa motivo das falhas
- Corrige problema (se aplicável)
- Resubmete manualmente se necessário

**Resultado**: Erro definitivo, requer intervenção

### 9.3. Fluxo de Exceção - Erro Permanente

**Cenário**: Erro de dados inválidos identificado

**Fluxo**:
1. Sistema recebe erro: "INVALID_PATIENT_DATA - CPF inválido"
2. Verifica contador: 0 (primeira tentativa)
3. Classifica erro: "INVALID_PATIENT_DATA" → PERMANENT
4. Identifica que retry não resolverá
5. Lança erro PERMANENT_ERROR
6. Notifica equipe de cadastro
7. Aguarda correção de dados

**Ações Corretivas**:
- Equipe de cadastro corrige CPF do paciente
- Validação de dados antes de nova submissão
- Submissão manual após correção

**Resultado**: Erro permanente, requer correção de dados

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS IN 41/2018 | Art. 5º | Prazo de 48h para reenvio | Retry automático dentro de 24h via backoff |
| ANS RN 305/2012 | Art. 7º | Rastreabilidade de tentativas | Log completo de todas as tentativas |
| TISS 4.0 | Componente 7 | Tratamento de erros de submissão | Classificação e análise de erros TISS |
| LGPD Art. 6º | Inciso VIII | Segurança | Retry não expõe dados sensíveis |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Análise de erro: Sistema automático
- Decisão de retry: Sistema automático
- Revisão manual: Equipe de faturamento (quando excede máximo)

**Retenção de Dados**:
- Logs de retry: 5 anos (ANS)
- Histórico de tentativas: 5 anos
- Análise de erros: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker pattern |
| Agendamento | Timer Events | Timer Start Events | Usar datas absolutas |
| Retry Config | Em código | No worker definition | Externalizar configuração |
| Idempotência | Opcional | Obrigatória | Garantir análise idempotente |

### 11.2. Estratégia de Migração

**Fase 1 - Worker de Análise**:
```java
@JobWorker(
    type = "analyze-retry",
    timeout = 10_000,
    maxJobsActive = 50
)
public RetryDecision analyzeRetry(
    @Variable String claimId,
    @Variable String submissionError,
    @Variable Integer retryCount
) {
    // Análise de erro
    // Decisão de retry
    // Cálculo de backoff
    return retryDecision;
}
```

**Fase 2 - Timer com Backoff**:
```xml
<bpmn:intermediateCatchEvent id="WaitForRetry">
  <bpmn:timerEventDefinition>
    <bpmn:timeDuration>PT${backoffMinutes}M</bpmn:timeDuration>
  </bpmn:timerEventDefinition>
</bpmn:intermediateCatchEvent>
```

### 11.3. Oportunidades de Melhoria

**Circuit Breaker**:
- Detectar quando TISS está instável
- Suspender submissões temporariamente
- Evitar tentativas desnecessárias

**Machine Learning**:
- Aprender padrões de erros transientes vs permanentes
- Ajustar backoff baseado em histórico
- Prever probabilidade de sucesso

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing Submission (Submissão de Cobrança)

**Sub-domínio**: Supporting Domain - Retry Logic

**Responsabilidade**: Análise inteligente de erros e gestão de tentativas de resubmissão

### 12.2. Agregados e Entidades

**Agregado Raiz**: `SubmissionRetryAttempt`

```
SubmissionRetryAttempt (Aggregate Root)
├── ClaimId (Value Object)
├── SubmissionError (String)
├── ErrorClassification (Enum: TRANSIENT, PERMANENT, UNKNOWN)
├── RetryCount (Integer)
├── MaxRetries (Integer)
├── BackoffMinutes (Integer)
├── NextRetryTime (LocalDateTime)
├── ShouldRetry (Boolean)
├── RetryReason (String)
├── AttemptHistory (Collection)
│   └── RetryAttempt
│       ├── AttemptNumber (Integer)
│       ├── Timestamp (Instant)
│       ├── Error (String)
│       └── BackoffApplied (Integer)
└── CreatedAt (Instant)
```

**Value Objects**:
- `ErrorClassification`: Enum de classificação de erro
- `BackoffCalculation`: Cálculo de tempo de espera

### 12.3. Domain Events

```
RetryScheduledEvent
├── claimId: ClaimId
├── retryCount: Integer
├── maxRetries: Integer
├── backoffMinutes: Integer
├── nextRetryTime: LocalDateTime
├── errorClassification: ErrorClassification
├── scheduledAt: Instant
└── version: Long

MaxRetriesExceededEvent
├── claimId: ClaimId
├── finalError: String
├── totalAttempts: Integer
├── totalDuration: Duration
├── exceededAt: Instant
└── severity: Severity.CRITICAL

PermanentErrorDetectedEvent
├── claimId: ClaimId
├── errorType: String
├── errorMessage: String
├── detectedAt: Instant
└── severity: Severity.CRITICAL
```

### 12.4. Serviços de Domínio

**RetryAnalysisService**:
```
Responsabilidades:
- Classificar erros como transiente ou permanente
- Calcular backoff exponencial
- Decidir se deve tentar novamente
- Registrar histórico de tentativas

Métodos:
- analyzeError(error): ErrorClassification
- calculateBackoff(retryCount): BackoffMinutes
- shouldRetrySubmission(claim, error, count): Boolean
- recordRetryAttempt(claim, attempt): void
```

### 12.5. Repositories

```
RetryAttemptRepository
├── findByClaimId(claimId): List<RetryAttempt>
├── saveAttempt(attempt): RetryAttempt
├── countAttempts(claimId): Integer
└── findPendingRetries(): List<RetryAttempt>
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Tentativa de Reenvio | Retry Attempt | Nova tentativa de submissão após falha |
| Erro Transiente | Transient Error | Erro temporário que pode ser resolvido com retry |
| Erro Permanente | Permanent Error | Erro que requer intervenção manual |
| Backoff Exponencial | Exponential Backoff | Aumento progressivo de tempo entre tentativas |
| Jitter | Jitter | Variação aleatória no tempo de espera |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `RetrySubmissionDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `retrySubmission` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Strategy, State Pattern |
| **Complexidade Ciclomática** | 7 (Média) |
| **Linhas de Código** | 229 |
| **Cobertura de Testes** | 91% |
| **Idempotência** | Sim (requiresIdempotency = true) |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x
- Java Random API

**Serviços Integrados** (futuro):
- ErrorClassificationService
- BackoffCalculationService
- RetrySchedulingService

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 5s | Análise rápida de erro |
| Max Retries | 5 | Balanceio entre persistência e eficiência |
| Base Backoff | 5 minutos | Tempo mínimo razoável |
| Max Backoff | 240 minutos | Evitar esperas excessivas |
| Jitter Percentage | 20% | Prevenir thundering herd |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "retry_scheduled",
  "claimId": "CLM-001-1234567890",
  "submissionError": "TIMEOUT",
  "errorClassification": "TRANSIENT",
  "retryCount": 2,
  "maxRetries": 5,
  "backoffMinutes": 10,
  "nextRetryTime": "2025-01-12T10:50:00Z",
  "executionTimeMs": 123,
  "timestamp": "2025-01-12T10:40:00Z"
}
```

**Métricas Prometheus**:
- `retry_analysis_duration_seconds` (Histogram)
- `retry_scheduled_total` (Counter)
- `max_retries_exceeded_total` (Counter)
- `permanent_errors_total` (Counter)
- `backoff_duration_minutes` (Histogram)
- `retry_success_rate` (Gauge)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Erro transiente agendando retry
2. ✅ Máximo de tentativas excedido
3. ✅ Erro permanente detectado
4. ✅ Cálculo de backoff exponencial
5. ✅ Jitter aplicado corretamente
6. ✅ Classificação de erros conhecidos
7. ✅ Tratamento de erros desconhecidos
8. ✅ Idempotência de análise

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
