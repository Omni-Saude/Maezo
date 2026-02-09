# RN-COMP-003: Compensação de Submissão de Cobrança

**ID Técnico**: `CompensateSubmitDelegate`
**Padrão**: SAGA - Compensating Transaction
**Versão**: 1.0
**Data**: 2026-01-24

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra

Desfazer operações de submissão de cobrança (envio de guias de cobrança para operadoras de saúde) quando o processamento de um SAGA falha após a etapa de submissão, cancelando transmissões com payers e restaurando o status de claims para estado anterior.

### 1.2. Contexto de Negócio

O SAGA envia guias de cobrança (claims) para operadoras de saúde através de:
- Submissão direta via API do payer
- Transmissão de arquivos EDI X12 837
- Integração com clearing houses

Se falhas posteriores ocorrem (após submissão), a compensação deve:
- Cancelar a submissão com a operadora
- Deletar registros de submissão
- Retornar claim ao status anterior (PENDING_SUBMISSION)
- Liberar claim numbers que foram assignados
- Cancelar transações EDI X12
- Notificar equipe de faturamento
- Auditoria completa

### 1.3. Benefícios Esperados

- **Segurança de Reenvio**: Evitar múltiplas submissões de mesma guia
- **Rastreabilidade**: Histórico completo de submissões e cancelamentos
- **Conformidade**: Não deixar claims "perdidos" em processamento
- **Recuperabilidade**: Permitir retry automático seguro

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
Quando um SAGA falha em etapas posteriores à submissão (ex: erro em validação assíncrona da resposta), o sistema deve compensar (reverter) a submissão através de:
1. Cancelar submissão com payer (API call)
2. Atualizar claim status para PENDING_SUBMISSION
3. Deletar registro de submissão
4. Reverter atribuição de claim number (se houver)
5. Cancelar transação EDI X12
6. Notificar billing team
7. Auditoria completa

**Lógica de Execução**:

```
FUNÇÃO CompensarSubmissao(submissionId, claimId, payerId):
  TRANSAÇÃO:
    # Passo 1: Cancelar com payer via API
    API_POST /payers/{payerId}/submissions/{submissionId}/cancel

    # Passo 2: Atualizar claim status
    UPDATE claims
    SET status = 'PENDING_SUBMISSION',
        submitted_at = NULL,
        payer_submission_id = NULL
    WHERE claim_id = ?

    # Passo 3: Deletar submission record
    DELETE claim_submissions WHERE submission_id = ?

    # Passo 4: Reverter claim number assignment
    UPDATE claims
    SET payer_claim_number = NULL
    WHERE claim_id = ?

    # Passo 5: Cancelar EDI transaction
    EDI_CANCELLATION(submissionId, claimId)

    # Passo 6: Notificar billing team
    NOTIFICAR(tipo=SUBMISSION_CANCELLED, submission=submissionId, claim=claimId)

    # Passo 7: Atualizar auditoria
    INSERT submission_audit_trail (
      submission_id, action='COMPENSATED', timestamp
    )

    RETORNAR sucesso
  FIM_TRANSAÇÃO
```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| COMP-003-V1 | submissionId obrigatório | CRÍTICA | Rejeitar MISSING_PARAMETER |
| COMP-003-V2 | claimId obrigatório | CRÍTICA | Rejeitar MISSING_PARAMETER |
| COMP-003-V3 | payerId obrigatório (pode ser inferido) | CRÍTICA | Rejeitar MISSING_PARAMETER |
| COMP-003-V4 | Submission deve existir | AVISO | Tratar como IDEMPOTENT |
| COMP-003-V5 | Claim deve existir | CRÍTICA | Falhar se não encontrado |
| COMP-003-V6 | Status deve ser SUBMITTED ou WAITING_RESPONSE | AVISO | Log se status diferente |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- submissionId identificando submissão válida
- claimId da guia submetida
- payerId da operadora (obtém de claim se não fornecido)

**Exceções de Negócio**:

1. **Submission Não Encontrada**
   - **Código**: SUBMISSION_NOT_FOUND
   - **Severidade**: AVISO (idempotente)
   - **Ação**: Retornar sucesso, registrar como já cancelada
   - **Notificação**: Não requerida

2. **Claim Não Encontrado**
   - **Código**: CLAIM_NOT_FOUND
   - **Severidade**: CRÍTICA
   - **Ação**: Falhar, escalar
   - **Notificação**: Equipe de Faturamento

3. **Payer API Indisponível**
   - **Código**: PAYER_API_UNAVAILABLE
   - **Severidade**: CRÍTICA
   - **Ação**: Retry automático (3x)
   - **Fallback**: Continuar com DB update mesmo se API falha

4. **EDI Cancellation Falha**
   - **Código**: EDI_CANCELLATION_FAILED
   - **Severidade**: AVISO
   - **Ação**: Log e continuar (pode não ter sido enviado EDI)
   - **Notificação**: Equipe de Integração EDI

5. **Claim Status Inconsistente**
   - **Código**: CLAIM_STATUS_INCONSISTENT
   - **Severidade**: AVISO
   - **Ação**: Log e continuar (compensação ainda válida)

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `submissionId` | String | Sim | Identificador da submissão | UUID válido |
| `claimId` | String | Sim | Identificador da guia | UUID válido |
| `payerId` | String | Não | Identificador da operadora | Pode ser recuperado de claim |

**Exemplo de Dados de Entrada**:
```json
{
  "submissionId": "SUB-2026-001-789012",
  "claimId": "CLM-ENC-001-1234567890",
  "payerId": "ANS-12345"
}
```

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `compensationCompleted` | Boolean | Sucesso da compensação | Definir próximo gateway |
| `compensationTimestamp` | LocalDateTime | Momento do cancelamento | Trilha de auditoria |

**Exemplo de Dados de Saída**:
```json
{
  "compensationCompleted": true,
  "compensationTimestamp": "2026-01-24T10:32:00.789Z"
}
```

---

## IV. Operações Detalhadas

### 4.1. Operação 1: Cancelar com Payer via API

**Tipos de Payers e Métodos de Submissão**:

#### A. Submissão via API REST (Moderno)
```
POST /api/v1/payers/{payerId}/submissions/{submissionId}/cancel

Headers:
  Content-Type: application/json
  Authorization: Bearer {token}
  X-Request-ID: {idempotencyKey}

Body:
{
  "submissionId": "SUB-2026-001-789012",
  "claimId": "CLM-ENC-001-1234567890",
  "reason": "SAGA_COMPENSATION",
  "timestamp": "2026-01-24T10:32:00.789Z"
}

Resposta esperada (200):
{
  "status": "CANCELLED",
  "submissionId": "SUB-2026-001-789012",
  "cancelledAt": "2026-01-24T10:32:01.234Z"
}
```

#### B. Submissão via EDI X12 837
```
- Arquivo X12 837 foi enviado para clearing house
- Cancelamento requer envio de arquivo de reversão
- Handled por operação 5 (cancelEDITransaction)
```

**Tratamento de Resposta**:
- Status 200: Cancelamento bem-sucedido
- Status 400: Bad request (validar payload)
- Status 401: Autenticação falhou (refresh token)
- Status 404: Submission não encontrada em payer (tratar como idempotent)
- Status 500: Erro no payer (retry)
- Status 503: Payer indisponível (retry)
- Timeout: Retry automático

**Idempotency Key**:
```
X-Request-ID = SHA256(submissionId + claimId)
```
Garante que se retentarmos, payer não processa novamente.

### 4.2. Operação 2: Atualizar Claim Status

**SQL**:
```sql
UPDATE claims
SET status = 'PENDING_SUBMISSION',
    submitted_at = NULL,
    payer_submission_id = NULL,
    last_modified = NOW(),
    modified_by = 'SAGA_COMPENSATION'
WHERE claim_id = ?
```

**Transição de Status**:
- Status anterior: 'SUBMITTED' ou 'WAITING_RESPONSE'
- Status novo: 'PENDING_SUBMISSION'
- Significado: Claim pode ser resubmetido

**Validação**:
- Claim deve existir
- Status atual deve ser SUBMITTED
- Não permite voltar de status ERROR (requer análise)

### 4.3. Operação 3: Deletar Submission Record

**SQL**:
```sql
DELETE FROM claim_submissions
WHERE submission_id = ?
```

**Estrutura da Tabela**:
```sql
claim_submissions (
  submission_id UUID PRIMARY KEY,
  claim_id UUID,
  payer_id VARCHAR,
  submission_number VARCHAR,  -- Número assignado pelo payer
  submission_date TIMESTAMP,
  status VARCHAR,             -- PENDING, SUBMITTED, FAILED
  response_received_at TIMESTAMP,
  payer_reference VARCHAR,    -- ID do payer para rastrear
  created_at TIMESTAMP
)
```

**Validação**:
- Confirmar que submission existe antes de deletar
- Se 0 linhas deletadas: tratar como idempotent

### 4.4. Operação 4: Reverter Claim Number Assignment

**SQL**:
```sql
UPDATE claims
SET payer_claim_number = NULL,
    claim_number_assigned_at = NULL
WHERE claim_id = ?
```

**Contexto**:
- Alguns payers assignam claim number na submissão
- Quando cancelamos, esse número fica inválido
- Próxima submissão receberá novo claim number

**Validação**:
- Só apaga se foi assignado (não está NULL)
- Log se já estava NULL (não é erro)

### 4.5. Operação 5: Cancelar EDI Transaction

**Tipos de Cancelamento EDI**:

#### A. Se foi enviado via Clearing House
```
Criar arquivo X12 997 (Functional Acknowledgment Negative) ou
Enviar arquivo 997 com código de rejeição

Referência: Original transaction ID
Motivo: "CANCELLED_BY_ORIGINATOR"
```

#### B. Se estava em fila de envio
```
DELETE FROM edi_outbound_queue
WHERE submission_id = ?

Libertar arquivo de transmissão pendente
```

**SQL de Cancelamento**:
```sql
UPDATE edi_transactions
SET status = 'CANCELLED',
    cancelled_at = NOW(),
    cancellation_reason = 'SAGA_COMPENSATION'
WHERE submission_id = ?
  AND status IN ('PENDING', 'SENT', 'IN_PROCESS')
```

**Validação**:
- Se não encontrar EDI transaction: não é erro (pode não ter sido enviado)
- Log para auditoria em qualquer caso

### 4.6. Operação 6: Notificar Billing Team

**Canais de Notificação**:
- Kafka topic: `hospital.rcm.submission.cancelled`
- Email para supervisor de faturamento (se criticalidade)

**Payload de Notificação**:
```json
{
  "eventType": "SUBMISSION_CANCELLED",
  "submissionId": "SUB-2026-001-789012",
  "claimId": "CLM-ENC-001-1234567890",
  "payerId": "ANS-12345",
  "reason": "SAGA compensation due to downstream failure",
  "timestamp": "2026-01-24T10:32:00.789Z",
  "action": "CLAIM_AVAILABLE_FOR_RESUBMISSION",
  "severity": "INFO"
}
```

**Destinatários**:
- Billing Supervisor (sempre)
- Payer Relations Manager (se payer crítico)
- CFO (se valor > threshold)

### 4.7. Operação 7: Atualizar Auditoria

**Audit Trail Record**:
```json
{
  "auditId": "AUDIT-SUB-...",
  "entityId": "SUB-2026-001-789012",
  "entityType": "submission",
  "action": "COMPENSATED",
  "actor": "SAGA_COMPENSATION_SYSTEM",
  "timestamp": "2026-01-24T10:32:00.789Z",
  "details": {
    "claimId": "CLM-ENC-001-1234567890",
    "payerId": "ANS-12345",
    "reason": "SAGA compensation after downstream failure",
    "status": "SUCCESS",
    "claimStatusReverted": "PENDING_SUBMISSION",
    "claimNumberCleared": true,
    "payerApiCancelled": true,
    "ediCancelled": true,
    "executionTimeMs": 1234
  }
}
```

---

## V. Padrão SAGA e Compensação

### 5.1. Posição no SAGA

```
SAGA: Ciclo de Receita Completo
│
├─ Step 1: Receber Pagamento
├─ Step 2: Alocar Pagamento → Compensation: CompensateAllocationDelegate
├─ Step 3: Criar Provisão → Compensation: CompensateProvisionDelegate
├─ Step 4: Submeter Cobrança
│  └─ Compensation: CompensateSubmitDelegate [VOCÊ ESTÁ AQUI]
│     Reversa: CANCEL com payer, DELETE submission, REVERT claim status
└─ Step 5: Atualizar Status (geralmente sem compensação)
```

### 5.2. Quando é Acionado

CompensateSubmitDelegate é acionado quando:
1. Validação assíncrona falha após submissão
2. Payer rejeita a guia imediatamente
3. EDI transmission falha depois de registrado
4. Timeout em processamento assíncrono do payer

**NÃO é acionado quando**:
- Submissão nem foi enviada (nunca chamou submit delegate)
- Payer recusa claim (compensação não resolve issue)

### 5.3. ADR-010 Compliance

**Conformidade**:
- ✓ Idempotência: submissionId reutilizável
- ✓ Isolamento: Cancelamentos isolados por claim
- ✓ Ordenação: Submissão é último passo compensável
- ✓ Rastreabilidade: Trilha de cancelamentos
- ✓ Notificação: Eventos publicados

**Idempotência**:
```
SE submissionId NÃO ENCONTRADO EM claim_submissions:
  RETORNAR sucesso com status="ALREADY_COMPENSATED"
```

---

## VI. Fluxos de Processamento

### 6.1. Fluxo Principal - Cancelamento Bem-Sucedido

**Cenário**: Validação assíncrona falha após submissão bem-sucedida

**Pré-condições**:
- Submissão foi enviada para payer
- Claim foi marcado como SUBMITTED
- EDI transaction foi gravado
- Nenhum erro detectado imediatamente

**Fluxo**:
1. Validação assíncrona executada (após 5-10 segundos)
2. Detecta erro (ex: procedimento inválido)
3. SAGA dispara CompensateSubmitDelegate
4. Executa 7 operações em sequência
5. Cancela com payer via API
6. Atualiza claim status
7. Deleta submission record
8. Cancela EDI se aplicável
9. Notifica team
10. Auditoria registrada

**Pós-condições**:
- claim_submissions: deletado
- claims.status: PENDING_SUBMISSION
- Payer tem claim como cancelado
- EDI transaction marcado como CANCELLED
- Billing team notificado
- Pronto para resubmissão

**Tempo Esperado**: 1-2 segundos (inclui API call ao payer)
**Resultado**: Submissão cancelada, claim pronto para retry

### 6.2. Fluxo Idempotente - Cancelamento Já Feito

**Cenário**: Compensation é chamado novamente

**Fluxo**:
1. Recebe submissionId
2. Procura em claim_submissions
3. Não encontra (já foi deletado)
4. **Ação Especial**: Retorna sucesso imediatamente
5. Auditoria: "COMPENSATION_ALREADY_APPLIED"

**Benefício**: Retry do SAGA é seguro

### 6.3. Fluxo de Erro - Payer API Indisponível

**Cenário**: Payer (ANS-12345) não responde na API

**Fluxo**:
1. Tenta POST /payers/ANS-12345/submissions/SUB.../cancel
2. Timeout (conexão não responde)
3. **Ação**: Registra erro, tenta retry (3x)
   - Retry 1: Wait 2s, POST novamente
   - Retry 2: Wait 4s, POST novamente
   - Retry 3: Wait 8s, POST novamente
4. Se 3x falham:
   - **Importante**: DB local foi atualizado (claim status)
   - Log de erro, mas continua com sucesso "partial"
   - Notifica Integration team para sincronizar payer
5. Background job tentará sincronizar depois

**Resultado**: Cancelamento local OK, payer sync async

### 6.4. Fluxo Parcial - EDI Não Encontrado

**Cenário**: Claim foi submetido via API, não via EDI

**Fluxo**:
1. Cancela com payer via API: sucesso
2. Atualiza claim status: sucesso
3. Deleta submission: sucesso
4. Tenta cancelar EDI transaction
5. Não encontra (nunca foi enviado EDI)
6. **Ação**: Log de info, não é erro
7. Continua com sucesso completo

**Validação**:
- Nem todos os claims usam EDI
- Alguns usam API direto do payer
- É normal não encontrar EDI

---

## VII. Tipos de Payers e Integrações

### 7.1. Payers Suportados

| Payer | Tipo | Método | Cancelamento |
|-------|------|--------|-------------|
| UNIMED | Health Plan | API REST + EDI | API POST /cancel |
| Bradesco Saúde | Health Plan | API + EDI | API POST /cancel |
| SulAmérica | Health Plan | EDI X12 | Arquivo de reversão |
| Seguros Unimed | Health Plan | EDI | Arquivo de reversão |
| Clearing House | Intermediária | EDI | EDI X12 997 negativa |

### 7.2. Métodos de Integração

**API REST**:
- Moderno, resposta imediata
- Idempotency key recomendado
- Melhor para audit trail

**EDI X12 837**:
- Tradicional, lote de transmissão
- Requer arquivo de transmissão
- Resposta via 997 ou 999

**Clearing House**:
- Intermediário centralizador
- Recebe e distribui para payers
- Maior latência

---

## VIII. Tratamento de Erros

### 8.1. Erros Específicos

| Código | Descrição | Severidade | Recuperação | Retry |
|--------|-----------|------------|-------------|-------|
| SUBMISSION_NOT_FOUND | Submissão não existe | AVISO | Retornar sucesso (idempotent) | Não |
| CLAIM_NOT_FOUND | Claim não existe | CRÍTICA | Falhar, escalar | Sim (3x) |
| PAYER_API_UNAVAILABLE | Payer não responde | CRÍTICA | Continuar localmente | Sim (3x async) |
| EDI_CANCELLATION_FAILED | EDI cancel falha | AVISO | Log, continuar | Não |
| CLAIM_STATUS_INCONSISTENT | Status diferente | AVISO | Log, continuar | Não |

### 8.2. Retry Strategy

**Transientes** (retry automático):
- PAYER_API_UNAVAILABLE
- CLAIM_NOT_FOUND (race condition rara)

**Permanentes**:
- SUBMISSION_NOT_FOUND (idempotent)
- CLAIM_STATUS_INCONSISTENT (log only)

**Configuração**:
```
MaxRetries: 3
WaitStrategy: Exponential (2s, 4s, 8s)
Timeout per retry: 5s
```

---

## IX. Conformidade Regulatória

### 9.1. Normas Aplicáveis

| Norma | Artigo | Requisito | Conformidade |
|-------|--------|-----------|-------------|
| ANS RN 395/2016 | Art. 10 | Cancelamento de submissão | Implementado |
| ANS RN 396/2016 | - | Protocolos EDI | Suportado |
| TISS 4.0 | - | Padrão de submissão | Compatível |
| Lei 6.404/76 | Art. 177 | Registros financeiros | Audit trail |
| LGPD | Art. 6 | Transparência | Logs estruturados |

### 9.2. Segregação de Funções

- **Execução**: SAGA automático
- **Aprovação**: Não requerida (cancelamento automático)
- **Auditoria**: Auditoria Interna (mensal)
- **Investigação**: Payer Relations (se payer reclama)

---

## X. Indicadores e Métricas

### 10.1. KPIs de Negócio

| KPI | Meta | Fórmula | Frequência |
|-----|------|---------|-----------|
| Taxa de Cancelamento Bem-Sucedido | ≥ 99% | (Sucesso / Total) × 100 | Diária |
| Tempo Médio de Cancelamento | ≤ 2s | Avg(cancel_time_ms) | Diária |
| Taxa de Claims Ressubmetidos | ≥ 95% | (Ressubmitted / Cancelled) × 100 | Mensal |
| Payer API Availability | ≥ 99.5% | (Sucesso / Total) × 100 | Diária |

### 10.2. Métricas Técnicas

**Prometheus**:
```
compensate_submit_total{status="success|failure"}
compensate_submit_duration_seconds (histogram)
compensate_submit_errors_total{error="..."}
payer_api_calls_total{payer="...", status="..."}
claim_submission_cancellations_total
```

**Alertas**:
- Taxa de erro > 2% → WARNING
- Tempo > 5s → WARNING
- Payer unavailable > 10 min → CRITICAL

---

## XI. Casos de Uso Detalhados

### 11.1. Caso 1: Validação Assíncrona Falha

**Contexto**:
- Submissão SUB-2026-001-789012 foi enviada
- Claim CLM-ENC-001-1234567890 foi marcado SUBMITTED
- Sistema retorna sucesso imediatamente
- Validação assíncrona executada após 5s
- Detecta: "Procedimento MAT-999 não existe"

**Execução**:
1. SAGA dispara CompensateSubmitDelegate
2. API POST /payers/ANS-12345/submissions/.../cancel → 200 OK
3. Atualiza claim status → PENDING_SUBMISSION
4. Deleta submission record
5. Reverter claim number (se foi assignado)
6. Cancela EDI se houver
7. Notifica: "Submissão cancelada, procedimento inválido"
8. Auditoria registrada

**Resultado**: Claim disponível para resubmissão após corrigir procedimento

### 11.2. Caso 2: Payer API Timeout

**Cenário**: Payer está lento, timeout na API

**Fluxo**:
1. Tenta cancelamento na API
2. Timeout (> 5s sem resposta)
3. Retry 1 (2s wait): ainda timeout
4. Retry 2 (4s wait): ainda timeout
5. Retry 3 (8s wait): ainda timeout
6. DB local foi atualizado
7. Registra erro mas sucesso "partial"
8. Notifica Integration team
9. Background job sincroniza depois

**Resultado**: Local OK, payer sync pendente

### 11.3. Caso 3: Resubmissão Bem-Sucedida

**Cenário**: Após cancelamento, claim é resubmetido

**Fluxo**:
1. Claim volta a status PENDING_SUBMISSION
2. Equipe corrige o procedimento MAT-999
3. Resubmete claim via novo submit delegate
4. Recebe novo submission ID
5. Payer processa novo claim com sucesso

**Validação**:
- Novo submission não terá referência ao antigo
- Payer tratará como nova submissão
- Idempotency key diferente

---

## XII. Monitoramento e Observabilidade

### 12.1. Logs Estruturados

```json
{
  "timestamp": "2026-01-24T10:32:00.789Z",
  "logLevel": "INFO",
  "event": "compensation_submit_completed",
  "processInstanceId": "PROC-2026-001",
  "submissionId": "SUB-2026-001-789012",
  "claimId": "CLM-ENC-001-1234567890",
  "payerId": "ANS-12345",
  "payerApiCalled": true,
  "payerApiStatus": 200,
  "claimStatusReverted": "PENDING_SUBMISSION",
  "executionTimeMs": 1234,
  "status": "SUCCESS",
  "actor": "SAGA_COMPENSATION_SYSTEM"
}
```

### 12.2. Dashboard Grafana

**Dashboard: Submission Compensation**
- Taxa de sucesso (%)
- Tempo médio (ms)
- Erros por tipo
- Taxa de idempotência
- Payer API availability

---

## XIII. Dependências

### 13.1. Dependências de Código

- `BaseDelegate`: Gerenciamento de variáveis
- Integração com payer APIs (REST clients)
- EDI X12 library

### 13.2. Dependências Externas

| Sistema | Tipo | Dados | Frequência |
|---------|------|-------|-----------|
| PostgreSQL | BD | Submissions, claims | Por transação |
| Kafka | Message Broker | Notificações | Assíncrono |
| Payer APIs | HTTP REST | Cancelamento | Por compensação |
| Clearing House | EDI | X12 transmissão | Por submissão |

---

## XIV. Configuração

### 14.1. Parâmetros

```properties
compensation.submit.timeout.ms=10000
compensation.submit.max.retries=3
compensation.submit.payer.api.timeout.ms=5000
compensation.submit.kafka.topic=hospital.rcm.submission.cancelled
compensation.submit.idempotency.enabled=true
```

### 14.2. Índices BD

```sql
CREATE INDEX idx_sub_id ON claim_submissions(submission_id);
CREATE INDEX idx_sub_claim_id ON claim_submissions(claim_id);
CREATE INDEX idx_claims_submission_id ON claims(payer_submission_id);
CREATE INDEX idx_sub_audit_ts ON submission_audit_trail(timestamp DESC);
```

---

## XV. Próximas Etapas

Após CompensateSubmitDelegate:
- Claim retorna a PENDING_SUBMISSION
- Pode ser resubmetido após correção de erros
- Notificação guia equipe sobre ação corretiva necessária
- Auditoria registra todo o ciclo

---

## XVI. Glossário

| Termo | Definição |
|-------|-----------|
| **Submission** | Envio de guia de cobrança para operadora |
| **Claim** | Guia de cobrança com procedimentos e valores |
| **Payer** | Operadora de saúde que recebe a cobrança |
| **EDI X12 837** | Padrão de arquivo para transmissão de guias |
| **Clearing House** | Intermediária que centraliza transmissões EDI |
| **Claim Number** | Identificador assignado pelo payer |
| **SAGA** | Padrão de transação distribuída |
| **Compensação** | Reversão de operação em SAGA |

---

**Aprovação**:
- **Autor**: Revenue Cycle Development Team
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2026-01-24
