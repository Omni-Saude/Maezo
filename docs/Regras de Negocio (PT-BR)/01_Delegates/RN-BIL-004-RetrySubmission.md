# RN-BIL-004: Retry de Submissão com Backoff Exponencial

**ID Técnico**: `RetrySubmissionDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Analisar erros de submissão ao TISS e determinar se nova tentativa é apropriada, implementando backoff exponencial com jitter para evitar "thundering herd" e permitir recuperação de falhas transitórias.

### 1.2. Contexto de Negócio
Falhas de submissão podem ser transitórias (indisponibilidade temporária de TISS, timeout de rede) ou permanentes (dados inválidos, operadora não encontrada). A regra diferencia esses cenários e implementa estratégia de retry inteligente, maximizando taxa de sucesso sem impedir diagnóstico de problemas reais.

### 1.3. Benefícios Esperados
- **Resiliência**: Recuperação automática de falhas transitórias
- **Eficiência**: Reduz intervenção manual através de retry inteligente
- **Confiabilidade**: Backoff exponencial evita sobrecarga de TISS
- **Diagnóstico**: Identifica permanentemente falhas que requerem investigação

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
Sistema deve analisar mensagem de erro de submissão, classificar como transitória ou permanente, e se transitória, calcular tempo de espera usando exponencial backoff e agendar próxima tentativa. Se permanente, lançar erro crítico. Máximo 5 tentativas em 4 horas.

**Lógica de Execução**:

1. **Extração de Variáveis**
   - claimId: identificador da cobrança
   - submissionError: mensagem de erro da tentativa anterior
   - retryCount: número da tentativa atual (0-4)
   - lastSubmissionTime: timestamp da última tentativa

2. **Validação de Retry Count**
   ```
   SE retryCount >= MAX_RETRIES (5):
     LANÇAR ERRO "MAX_RETRIES_EXCEEDED"
   ```

3. **Análise de Tipo de Erro**
   ```
   erros_permanentes = [
     "INVALID_PATIENT_DATA",
     "INSURANCE_EXPIRED",
     "AUTHORIZATION_DENIED",
     "DUPLICATE_CLAIM",
     "INVALID_PROCEDURE_CODE"
   ]

   erros_transientes = [
     "TIMEOUT",
     "CONNECTION_ERROR",
     "SERVICE_UNAVAILABLE",
     "NETWORK_ERROR",
     "TEMPORARY_ERROR",
     "RATE_LIMIT",
     "SERVER_ERROR",
     "503", "504"
   ]

   SE erro está em erros_permanentes:
     LANÇAR ERRO "PERMANENT_ERROR"

   SE erro está em erros_transientes:
     shouldRetry = true
   SENÃO:
     shouldRetry = true (por segurança, retry desconhecido)
   ```

4. **Cálculo de Backoff**
   ```
   backoff = BASE_BACKOFF × 2^retryCount
   backoff = min(backoff, MAX_BACKOFF)
   jitter = random(-20% a +20%) × backoff
   backoffFinal = backoff + jitter
   backoffFinal = max(backoffFinal, BASE_BACKOFF)
   ```

5. **Agendamento de Próxima Tentativa**
   - Calcular nextRetryTime = agora + backoffFinal
   - Incrementar retryCount
   - Registrar na auditoria

6. **Saída de Variáveis**
   - shouldRetry: true (será processado por timer ou job)
   - nextRetryTime: quando tentar novamente
   - retryCount: nova contagem
   - retryReason: descrição do motivo
   - backoffMinutes: tempo de espera

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-004-V1 | Máximo 5 tentativas | CRÍTICA | Erro MAX_RETRIES_EXCEEDED |
| BIL-004-V2 | Erro permanente não deve retryr | CRÍTICA | Erro PERMANENT_ERROR |
| BIL-004-V3 | Backoff deve estar entre 5 e 240 minutos | CRÍTICA | Enforçar limites |
| BIL-004-V4 | Jitter deve estar entre -20% e +20% | CRÍTICA | Validar geração aleatória |
| BIL-004-V5 | retryCount não pode ser negativo | CRÍTICA | Rejeitar entrada |
| BIL-004-V6 | submissionError não pode ser vazio | CRÍTICA | Rejeitar entrada |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- claimId válido
- submissionError contém mensagem de erro anterior
- retryCount entre 0 e 4
- lastSubmissionTime válido (pode ser null na primeira tentativa)

**Exceções de Negócio**:

1. **Máximo de Tentativas Excedido**
   - **Código**: MAX_RETRIES_EXCEEDED
   - **Ação**: Suspender cobrança para análise manual
   - **Notificação**: Gestão de Faturamento

2. **Erro Permanente Identificado**
   - **Código**: PERMANENT_ERROR
   - **Ação**: Suspender sem retry
   - **Próximo Passo**: Análise de dados ou cobertura

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador da cobrança | Formato válido |
| `submissionError` | String | Sim | Mensagem de erro de submissão anterior | Não vazio |
| `retryCount` | Integer | Não | Número de tentativas já realizadas | 0-4, default 0 |
| `lastSubmissionTime` | LocalDateTime | Não | Timestamp da última tentativa | Pode ser null |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `shouldRetry` | Boolean | Se deve fazer retry | Condição de gateway |
| `nextRetryTime` | LocalDateTime | Quando tentar novamente | Timer de espera |
| `retryCount` | Integer | Nova contagem de tentativas | Próximo retry |
| `retryReason` | String | Motivo do retry | Auditoria e logs |
| `backoffMinutes` | Integer | Tempo de espera em minutos | Informativo |

---

## IV. Fórmulas e Cálculos

### 4.1. Backoff Exponencial

```
Entrada:
  retryCount = n (0, 1, 2, 3, 4)
  BASE_BACKOFF = 5 minutos
  MAX_BACKOFF = 240 minutos (4 horas)

Cálculo:
  backoff_exponencial = BASE × 2^n
  = 5 × 2^0 = 5 minutos (tentativa 1)
  = 5 × 2^1 = 10 minutos (tentativa 2)
  = 5 × 2^2 = 20 minutos (tentativa 3)
  = 5 × 2^3 = 40 minutos (tentativa 4)
  = 5 × 2^4 = 80 minutos (tentativa 5)

Aplicação de Limite:
  backoff_limitado = min(backoff_exponencial, MAX_BACKOFF)
  = min(80, 240) = 80 minutos
```

### 4.2. Jitter Aleatório

```
Objetivo: Evitar "thundering herd" (todos retry no mesmo momento)

Fórmula:
  jitter_percent = random(-20%, +20%)
  = ±0.20 × backoff_limitado

Exemplo (retryCount=2):
  backoff = 20 minutos
  jitter = ±0.20 × 20 = ±4 minutos
  resultado = 20 ± random(-4, +4) minutos
  = entre 16 e 24 minutos

Aplicação:
  backoff_final = max(backoff_limitado + jitter, BASE_BACKOFF)
  (garante mínimo de 5 minutos mesmo com jitter negativo)
```

### 4.3. Matriz de Decisão de Erro

```
Entrada: errorMessage (string)

┌─────────────────────────────────────┐
│ Análise de Tipo de Erro             │
├─────────────────────────────────────┤
│                                     │
│ SE error CONTÉM:                    │
│   • "INVALID_PATIENT_DATA"          │
│   • "INSURANCE_EXPIRED"             │
│   • "AUTHORIZATION_DENIED"          │
│   • "DUPLICATE_CLAIM"               │
│   • "INVALID_PROCEDURE_CODE"        │
│ ENTÃO: PERMANENTE (não retry)       │
│                                     │
│ SE error CONTÉM:                    │
│   • "TIMEOUT"                       │
│   • "CONNECTION_ERROR"              │
│   • "SERVICE_UNAVAILABLE"           │
│   • "NETWORK_ERROR"                 │
│   • "RATE_LIMIT" / "503" / "504"   │
│ ENTÃO: TRANSITÓRIO (retry)          │
│                                     │
│ SENÃO: DESCONHECIDO (retry seguro)  │
│                                     │
└─────────────────────────────────────┘
```

### 4.4. Progressão de Tentativas

| Tentativa | retryCount | Backoff Base | Jitter | Backoff Final | Tempo Acumulado |
|-----------|-----------|-------------|--------|---------------|-----------------|
| 1ª | 0 | 5 min | ±4 min | 1-9 min | 1-9 min |
| 2ª | 1 | 10 min | ±8 min | 2-18 min | 3-27 min |
| 3ª | 2 | 20 min | ±16 min | 4-36 min | 7-63 min |
| 4ª | 3 | 40 min | ±32 min | 8-72 min | 15-135 min |
| 5ª | 4 | 80 min | ±64 min | 16-144 min | 31-279 min |

**Tempo Total Máximo**: ~4,5 horas entre primeira tentativa e quinta tentativa

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Timer de Processo | Envelope | nextRetryTime | BPMN Timer Event |
| Auditoria | Escrita | Log de retry | Message Queue |
| Monitoramento | Métricas | Backoff, tentativas | Prometheus |

### 5.2. Dependências de Dados

**Configurações Críticas**:
- MAX_RETRIES = 5
- BASE_BACKOFF_MINUTES = 5
- MAX_BACKOFF_MINUTES = 240

**Dados de Análise**:
- Lista de erros permanentes
- Lista de erros transitórios

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Sucesso após Retry | % de cobrança recuperadas por retry | ≥ 85% | (Sucesso Retry / Total Retry) × 100 | Diária |
| Tentativas Médias | Quantas tentativas até sucesso | ≤ 1.2 | Média aritmética | Diária |
| Cobrança Perdida | % que excede MAX_RETRIES | ≤ 3% | (Perdidas / Total Retry) × 100 | Semanal |
| Tempo até Sucesso | Tempo total de retry até sucesso | ≤ 60 min | Mediana de tempos | Diária |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Taxa de Erro Permanente | % identificadas como permanentes | > 10% | Investigar validações |
| Taxa de Backoff Máximo | % que atingem MAX_BACKOFF | > 5% | Indicar problema de TISS |
| Uniformidade Jitter | Distribuição de jitter | Desvio > 30% | Revisar gerador aleatório |
| Tempo Médio Backoff | Tempo médio entre retries | > 30 min | Investigar latência TISS |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Análise de erro (transitório/permanente)
2. Cálculo de backoff
3. Agendamento de próxima tentativa
4. Decisão de retry ou não

**Informações Capturadas**:
```json
{
  "timestamp": "data_hora_analise",
  "claimId": "identificador_cobranca",
  "errorMessage": "mensagem_erro_original",
  "retryCount": numero_tentativa,
  "errorClassification": "TRANSIENT|PERMANENT|UNKNOWN",
  "backoffMinutes": tempo_espera,
  "nextRetryTime": "data_hora_proxima_tentativa",
  "shouldRetry": true|false,
  "retryReason": "motivo_retry"
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação Classificação Erro | Preventivo | Por retry | Sistema |
| Monitoramento Backoff | Preventivo | Por retry | Sistema |
| Análise de Erros Permanentes | Detectivo | Diária | Análise de Dados |
| Revisão de Falhas | Corretivo | Semanal | Gestão Faturamento |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| MAX_RETRIES_EXCEEDED | 5 tentativas sem sucesso | CRÍTICA | Revisão manual, análise de erro |
| PERMANENT_ERROR | Erro permanente, não retentável | CRÍTICA | Correção de dados ou investigação |

### 8.2. Padrão de Retry

**Padrão: Exponential Backoff with Jitter**

```
Benefícios:
- Exponencial: Aumenta espera progressivamente
- Jitter: Distribui retries ao longo do tempo
- Máximo: Previne esperas muito longas

Resultado:
- Primeira falha: tenta em 1-9 minutos
- Segunda falha: tenta em 2-18 minutos
- Terceira falha: tenta em 4-36 minutos
- Quarta falha: tenta em 8-72 minutos
- Quinta falha: tenta em 16-144 minutos (~2,5 horas)

Máximo: ~5 horas desde primeira tentativa até quinta
```

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Erro Transitório com Retry Bem-Sucedido

**Cenário**: TISS indisponível, retry recupera cobrança

**Pré-condições**:
- Primeira tentativa de submissão falhou com timeout
- Retry count = 0
- Erro = "SERVICE_UNAVAILABLE"

**Fluxo**:
1. Sistema recebe submissionError = "SERVICE_UNAVAILABLE"
2. Classifica como TRANSIENT
3. Calcula backoff: 5 + jitter (±4) = 7 minutos
4. Agenda retry em 7 minutos
5. Retorna nextRetryTime, retryCount=1
6. Timer aguarda 7 minutos
7. SubmitClaimDelegate tenta novamente
8. TISS está online, submissão bem-sucedida
9. Protocolo gerado

**Resultado**: Sucesso após retry automático

### 9.2. Fluxo Alternativo - Erro Permanente

**Cenário**: Procedimento inválido, não há como corrigir com retry

**Fluxo**:
1. Sistema recebe submissionError = "INVALID_PROCEDURE_CODE"
2. Identifica em lista de erros permanentes
3. Lança PERMANENT_ERROR
4. Não agenda retry
5. Suspende cobrança
6. Notifica gestão de faturamento para correção

**Resultado**: Erro sem retry

### 9.3. Fluxo de Exceção - Máximo de Tentativas

**Cenário**: TISS continua indisponível após 5 tentativas

**Fluxo**:
1. Primeira falha: retry em 5-9 min (7 min médio)
2. Segunda falha: retry em 10-18 min (14 min médio)
3. Terceira falha: retry em 20-36 min (28 min médio)
4. Quarta falha: retry em 40-72 min (56 min médio)
5. Quinta falha: retry em 80-144 min (112 min médio)
6. Sexta tentativa: teria sido necessário > 5 retries
7. Sistema lança MAX_RETRIES_EXCEEDED
8. Cobrança suspenso para análise manual

**Tempo Total**: ~3.5 horas de tentativas automáticas

**Resultado**: Escalação para gestão

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 305/2012 | Art. 4º | Submissão confiável | Retry automático garante entrega |
| ANS RN 395/2016 | Art. 5º | Rastreamento | Cada retry é registrado em auditoria |
| LGPD Art. 16º | - | Segurança de dados | Transientes vs permanentes diferenciados |
| LGPD Art. 18º | Inciso II | Acesso aos logs | Histórico de retries disponível |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Análise de erro: Sistema automático
- Agendamento: Timer Camunda
- Auditoria: Sistema de auditoria
- Investigação de permanentes: Gestão

**Retenção de Dados**:
- Log de retry: 5 anos
- Histórico de tentativas: 5 anos
- Análise de erro: Permanente

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker |
| Timer | BpmnTimerEvent | Zeebe Timer | Adaptar agendamento |
| Variáveis | setVariable() | Zeebe API | Adaptar gestão |
| Idempotência | Manual | JobKey automático | Usar claimId + retryCount |

### 11.2. Estratégia de Migração

**Fase 1 - Camunda 8 JobWorker**:
```java
@JobWorker(type = "retry-submission-backoff")
public RetrySubmissionResponse handle(
    @Variable String claimId,
    @Variable String submissionError,
    @Variable(defaultValue = "0") Integer retryCount
) {
    // Validar retryCount
    if (retryCount >= MAX_RETRIES) {
        // Throw incident
        throw new BpmnError("MAX_RETRIES_EXCEEDED");
    }

    // Classificar erro
    boolean shouldRetry = shouldRetryError(submissionError);
    if (!shouldRetry) {
        throw new BpmnError("PERMANENT_ERROR", submissionError);
    }

    // Calcular backoff
    int backoffMinutes = calculateBackoffMinutes(retryCount);
    LocalDateTime nextRetryTime =
        LocalDateTime.now().plusMinutes(backoffMinutes);

    return new RetrySubmissionResponse(
        true,
        nextRetryTime,
        retryCount + 1,
        String.format("Retry %d of %d",
            retryCount + 1, MAX_RETRIES),
        backoffMinutes
    );
}
```

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing (Faturamento)
**Sub-domínio**: Resilience & Error Recovery
**Responsabilidade**: Recuperação automática de falhas transitórias

### 12.2. Agregados e Entidades

```
SubmissionRetry (Value Object)
├── ClaimId
├── RetryCount (0-5)
├── ErrorClassification (TRANSIENT|PERMANENT|UNKNOWN)
├── BackoffDuration
├── NextRetryTime
└── AuditTrail
```

### 12.3. Domain Events

```
SubmissionRetryScheduledEvent
├── claimId: ClaimId
├── retryCount: Integer
├── errorClassification: String
├── nextRetryTime: Instant
├── backoffMinutes: Integer
└── timestamp: Instant

SubmissionRetryExhaustedEvent
├── claimId: ClaimId
├── retryCount: Integer (5)
├── lastError: String
└── timestamp: Instant
```

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `RetrySubmissionDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `retrySubmission` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Strategy, Template Method |
| **Complexidade Ciclomática** | 5 (Baixa) |
| **Linhas de Código** | 229 |
| **Cobertura de Testes** | 96% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x

**Sem dependências de serviços externos** (apenas cálculos)

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 2s | Apenas cálculos, sem I/O |
| Pool de Threads | 10 | Baixo consumo |
| Frequência Cálculo | Por retry | Máximo 5 execuções/cobrança |
| Gerador Aleatório | java.util.Random | ThreadLocal-safe |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "submission_retry_scheduled",
  "claimId": "CLM-ENC-001-1234567890",
  "submissionError": "SERVICE_UNAVAILABLE",
  "retryCount": 1,
  "errorClassification": "TRANSIENT",
  "backoffMinutes": 7,
  "nextRetryTime": "2025-01-12T10:37:00Z",
  "timestamp": "2025-01-12T10:30:00Z"
}
```

**Métricas Prometheus**:
- `submission_retry_total` (Counter)
- `submission_retry_backoff_minutes` (Histogram)
- `submission_retry_max_exceeded` (Counter)
- `error_classification_distribution` (Counter)

### 13.5. Testes

**Cenários de Teste**:
1. ✅ Erro transitório (SERVICE_UNAVAILABLE)
2. ✅ Erro permanente (INVALID_PROCEDURE_CODE)
3. ✅ Erro desconhecido (retry por segurança)
4. ✅ Backoff exponencial crescente
5. ✅ Jitter distribuído (-20% a +20%)
6. ✅ Máximo de retries (5 tentativas)
7. ✅ Backoff máximo (240 minutos cap)
8. ✅ Backoff mínimo (5 minutos garantido)

---

## XIV. Glossário de Termos

| Termo | Definição |
|-------|-----------|
| **Erro Transitório** | Falha temporária (network, timeout, indisponibilidade) |
| **Erro Permanente** | Falha estrutural (dados inválidos, cobertura negada) |
| **Backoff Exponencial** | Espera aumenta exponencialmente a cada tentativa |
| **Jitter** | Variação aleatória na espera para evitar "thundering herd" |
| **Thundering Herd** | Múltiplas requisições simultâneas após timeout |
| **Max Retries** | Limite máximo de tentativas (5) |

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
