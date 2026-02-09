# RN-BIL-003: Submissão de Cobrança ao TISS

**ID Técnico**: `SubmitClaimDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Submeter cobrança validada ao sistema TISS (Troca de Informação em Saúde Suplementar) da operadora de saúde, obter protocolo de recebimento e rastrear status da submissão.

### 1.2. Contexto de Negócio
A submissão ao TISS é etapa crítica no ciclo de receita, sendo obrigatória para todas as operadoras de saúde reguladas pela ANS. O sistema TISS é o padrão definido pela Resolução Normativa ANS 305/2012 para comunicação eletrônica entre prestadores e operadoras.

### 1.3. Benefícios Esperados
- **Conformidade Regulatória**: Atende ANS RN 305/2012 e RN 395/2016
- **Rastreabilidade**: Número de protocolo para acompanhamento
- **Automação**: Eliminação de submissões manuais
- **Auditoria**: Registro completo de tentativas e status

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve validar dados de cobrança, confirmar que a operadora está ativa e aceita submissões eletrônicas, construir mensagem XML conforme padrão TISS, submeter ao sistema da operadora e obter protocolo de recebimento.

**Lógica de Execução**:

1. **Validação de Dados da Cobrança**
   - Validar formato do identificador de cobrança (claimId)
   - Validar identificador da operadora (insuranceId)
   - Validar valor de cobrança (positivo, dentro de limites)
   - Validar códigos de procedimentos (formato, existência)
   - Validar códigos de diagnóstico (formato ICD-10)

2. **Validação de Operadora**
   ```
   SE operadora NÃO EXISTE:
     LANÇAR ERRO "INSURANCE_NOT_FOUND"

   SE operadora está INATIVA:
     LANÇAR ERRO "INSURANCE_NOT_FOUND"

   SE operadora NÃO ACEITA submissão eletrônica:
     LANÇAR ERRO "SUBMISSION_FAILED"
   ```

3. **Construção de Requisição TISS**
   - Extrair dados de cobrança das variáveis do processo
   - Montar estrutura XML conforme TISS 4.0
   - Incluir metadados de processo (processInstanceId, executionId)
   - Definir como retentável para retry automático

4. **Submissão ao TISS**
   - Chamar TissSubmissionService.submitClaim()
   - Registrar timestamp de submissão
   - Capturar número de protocolo

5. **Validação de Resultado**
   ```
   SE submissão NÃO foi bem-sucedida:
     LANÇAR ERRO "SUBMISSION_FAILED"
   ```

6. **Registro de Saída**
   - Salvar status de submissão (SUBMITTED, REJECTED, PENDING)
   - Salvar número de protocolo TISS
   - Salvar timestamp de submissão

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-003-V1 | claimId deve estar em formato válido | CRÍTICA | Rejeitar com INVALID_CLAIM |
| BIL-003-V2 | insuranceId deve ser válido e ativo | CRÍTICA | Rejeitar com INSURANCE_NOT_FOUND |
| BIL-003-V3 | claimAmount deve ser positivo e dentro de limites | CRÍTICA | Rejeitar com INVALID_CLAIM |
| BIL-003-V4 | Operadora deve aceitar submissão eletrônica | CRÍTICA | Rejeitar com SUBMISSION_FAILED |
| BIL-003-V5 | Todos os procedimentos devem ter código válido | CRÍTICA | Rejeitar com INVALID_CLAIM |
| BIL-003-V6 | Diagnósticos devem estar em formato ICD-10 | CRÍTICA | Rejeitar com INVALID_CLAIM |
| BIL-003-V7 | Sistema TISS deve estar disponível | CRÍTICA | Rejeitar com TISS_UNAVAILABLE |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- claimId válido e único
- insuranceId válido e ativo
- claimAmount positivo
- Procedimentos e diagnósticos previamente validados
- Contratos aplicados e descontos calculados

**Exceções de Negócio**:

1. **Cobrança Inválida**
   - **Código**: INVALID_CLAIM
   - **Ação**: Suspender submissão
   - **Próximo Passo**: Análise de dados e correção

2. **Operadora Não Encontrada**
   - **Código**: INSURANCE_NOT_FOUND
   - **Ação**: Rejeitar cobrança
   - **Notificação**: Gestão de operadoras

3. **TISS Indisponível**
   - **Código**: TISS_UNAVAILABLE
   - **Ação**: Programar retry automático
   - **Próximo Passo**: RetrySubmissionDelegate

4. **Submissão Falhou**
   - **Código**: SUBMISSION_FAILED
   - **Ação**: Analisar erro e determinar se é temporário ou permanente

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador único da cobrança | Formato: CLM-[TIPO]-[DATA]-[NÚMERO] |
| `insuranceId` | String | Sim | Código ANS ou CNPJ da operadora | 6 dígitos (ANS) ou 14 (CNPJ) |
| `claimAmount` | BigDecimal | Sim | Valor total da cobrança já ajustado | Positivo, máximo R$ 999.999,99 |
| `patientId` | String | Não | Identificador do paciente | CPF ou RG formatado |
| `procedureCodes` | List<String> | Não | Lista de códigos de procedimentos | Formato TUSS-7 dígitos |
| `diagnosisCodes` | List<String> | Não | Lista de diagnósticos | Formato ICD-10 |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `submissionStatus` | String | Status da submissão (SUBMITTED, REJECTED, PENDING) | Análise de pagamento, retry logic |
| `protocolNumber` | String | Número de protocolo TISS | Rastreamento, comunicação com operadora |
| `submissionDate` | LocalDateTime | Timestamp de submissão | Cálculo de prazos de recebimento |

---

## IV. Fórmulas e Cálculos

### 4.1. Validação de Valor Máximo

```
Entrada:
  claimAmount = valor da cobrança
  MAX_CLAIM_AMOUNT = limite configurado (ex: R$ 999.999,99)

Validação:
  SE claimAmount > MAX_CLAIM_AMOUNT ENTÃO
    LANÇAR ERRO "INVALID_CLAIM"
  SE claimAmount ≤ 0 ENTÃO
    LANÇAR ERRO "INVALID_CLAIM"
```

### 4.2. Formato de Protocolo TISS

```
Padrão: [OPERADORA][DATA][SEQUÊNCIA]
Exemplo: ANS123456202501010001

Componentes:
- OPERADORA: 6 caracteres (código ANS)
- DATA: 8 dígitos (YYYYMMDD da submissão)
- SEQUÊNCIA: 4 dígitos (número sequencial da operadora)
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| TISS (ANS) | Envio | Cobrança em XML | HTTPS/SFTP |
| Cadastro de Operadoras | Consulta | Status, aceita eletrônico | API REST |
| Tabela de Procedimentos | Consulta | Validação de códigos | Database |
| Auditoria | Escrita | Log de submissão | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Status ativo de operadora
- Aceita submissão eletrônica (flag booleano)
- Credenciais TISS (endpoint, certificado digital)
- Tabela de procedimentos TUSS
- Tabela de diagnósticos ICD-10

**Frequência de Atualização**:
- Status de operadora: Real-time
- Cadastro de operadoras: Semanal
- Tabelas TUSS: Anual (conforme SUS)
- Tabelas ICD-10: Anual

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Submissão Bem-Sucedida | % de cobrança submetidas com sucesso | ≥ 95% | (Submetidas / Total) × 100 | Diária |
| Tempo Médio de Submissão | Tempo entre validação e recebimento de protocolo | ≤ 3s | Média de tempos | Diária |
| Taxa de Validação Falha | % de cobrança rejeitadas na validação | ≤ 5% | (Rejeitadas / Total) × 100 | Semanal |
| Disponibilidade de TISS | % de uptime da integração TISS | ≥ 99% | (Horas online / Horas totais) × 100 | Diária |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Erros INVALID_CLAIM | Validações falhadas | > 10% | Revisar regras de validação |
| Erros INSURANCE_NOT_FOUND | Operadoras não encontradas | > 5 | Atualizar cadastro de operadoras |
| Erros TISS_UNAVAILABLE | TISS indisponível | > 1 em 1h | Contatar operadora / ANS |
| Latência TISS | Tempo resposta submissão | > 5s | Investigar conectividade |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Validação de dados de cobrança
2. Validação de operadora
3. Construção de requisição TISS
4. Submissão ao TISS
5. Recebimento de protocolo

**Informações Capturadas**:
```json
{
  "timestamp": "data_hora_submissão",
  "claimId": "identificador_cobrança",
  "insuranceId": "operadora",
  "claimAmount": valor_cobranca,
  "protocolNumber": "número_protocolo_tiss",
  "status": "status_submissão",
  "executionTimeMs": tempo_processamento,
  "userId": "sistema_ou_usuario",
  "processInstanceId": "id_instancia_bpmn"
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Dados | Preventivo | Por transação | Sistema |
| Verificação de Operadora | Preventivo | Por transação | Sistema |
| Rastreamento de Protocolo | Detectivo | Diária | Sistema |
| Revisão de Submissões Falhadas | Corretivo | Semanal | Gestão Faturamento |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| INVALID_CLAIM | Dados de cobrança inválidos | CRÍTICA | Correção manual, revalidação |
| INSURANCE_NOT_FOUND | Operadora não encontrada ou inativa | CRÍTICA | Verificação de cadastro |
| SUBMISSION_FAILED | Falha na submissão TISS | CRÍTICA | Análise de erro, retry |
| TISS_UNAVAILABLE | Sistema TISS indisponível | CRÍTICA | Retry automático exponencial |

### 8.2. Estratégia de Retry

**Erros Transientes** (retry automático):
- TISS_UNAVAILABLE
- Timeout em submissão
- Erro de conexão

**Configuração**:
- Máximo de tentativas: 5
- Intervalo: 5, 10, 20, 40, 80 minutos (exponencial)
- Máximo: 4 horas
- Jitter: ±20%

**Erros Permanentes** (sem retry):
- INVALID_CLAIM
- INSURANCE_NOT_FOUND
- SUBMISSION_FAILED (se erro de validação)

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Submissão Bem-Sucedida

**Cenário**: Submeter cobrança validada de operadora ativa

**Pré-condições**:
- Cobrança passou por todas as validações anteriores
- Operadora está ativa e aceita submissão eletrônica
- TISS está disponível

**Fluxo**:
1. Sistema recebe claimId, insuranceId, claimAmount
2. Valida dados de cobrança
3. Verifica operadora (ativa, aceita eletrônico)
4. Constrói requisição TISS
5. Submete ao TissSubmissionService
6. Recebe protocolo e status
7. Retorna protocolo, status e timestamp

**Pós-condições**:
- Cobrança submetida com protocolo TISS
- Status rastreável
- Pronto para análise de pagamento

**Resultado**: Sucesso com protocolo gerado

### 9.2. Fluxo Alternativo - Operadora Inativa

**Cenário**: Operadora não está ativa no cadastro

**Fluxo**:
1. Sistema identifica insuranceId inválido
2. Consulta cadastro de operadoras
3. Encontra registro inativo
4. Lança erro INSURANCE_NOT_FOUND
5. Suspende cobrança
6. Notifica gestão de operadoras

**Resultado**: Erro sem retry automático

### 9.3. Fluxo de Exceção - TISS Indisponível

**Cenário**: Sistema TISS da operadora está offline

**Fluxo**:
1. Sistema tenta submeter cobrança
2. TISS retorna erro de conexão
3. Lança TISS_UNAVAILABLE
4. RetrySubmissionDelegate agenda próxima tentativa
5. Retry em 5 minutos
6. Se falhar novamente, próximo retry em 10 minutos
7. Máximo 5 tentativas em 4 horas

**Resultado**: Retry automático até sucesso ou limite

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 305/2012 | Art. 1º | Padrão TISS obrigatório | Submissão via TissSubmissionService em XML |
| ANS RN 305/2012 | Art. 4º | Validação de dados | Validação completa antes de submissão |
| ANS RN 395/2016 | Art. 5º | Registro eletrônico | Protocolo TISS como comprovante |
| ANS RN 395/2016 | Art. 7º | Transparência | Rastreamento via número de protocolo |
| LGPD Art. 16º | - | Precisão de dados | Validação prévia elimina erros de submissão |
| LGPD Art. 18º | Inciso II | Acesso aos dados | Protocolo disponível para consulta |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Validação: Sistema automático
- Submissão: TissSubmissionService
- Auditoria: Sistema de auditoria
- Resolução de erros: Gestão de Faturamento

**Retenção de Dados**:
- Protocolo TISS: Permanente
- Logs de submissão: 5 anos
- Dados de cobrança: 5 anos
- Erros de submissão: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para padrão JobWorker |
| Variáveis | DelegateExecution.setVariable() | Zeebe Variables API | Adaptar gestão de variáveis |
| Erros | BpmnError | Incident + Error Event | Implementar tratamento Zeebe-native |
| Idempotência | Manual @IdempotencyParams | JobKey automático | Usar identificadores únicos |

### 11.2. Estratégia de Migração

**Fase 1 - Preparação**:
```java
// Camunda 8 - JobWorker Pattern
@JobWorker(type = "submit-claim-tiss")
public SubmitClaimResponse handle(
    @Variable String claimId,
    @Variable String insuranceId,
    @Variable BigDecimal claimAmount
) {
    // Validações e submissão
    validateClaimForSubmission(claimId, insuranceId, claimAmount);
    validateInsuranceCompany(insuranceId);

    ClaimSubmissionRequest request = buildSubmissionRequest(
        claimId, insuranceId, claimAmount);

    ClaimSubmissionResult result = tissSubmissionService.submitClaim(request);

    return new SubmitClaimResponse(
        result.getStatus().getCode(),
        result.getProtocolNumber(),
        result.getSubmissionDateTime()
    );
}
```

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing (Faturamento)
**Sub-domínio**: Core Domain - Claim Submission
**Responsabilidade**: Submeter cobrança validada ao TISS com rastreamento

### 12.2. Agregados e Entidades

```
SubmittedClaim (Aggregate Root)
├── ClaimId (Value Object)
├── InsuranceId (Value Object)
├── ClaimAmount (Money)
├── Submission (Entity)
│   ├── ProtocolNumber
│   ├── SubmissionDateTime
│   ├── SubmissionStatus
│   └── ValidationRules
└── TissReference (Value Object)
    ├── ProviderCode
    └── SubmissionEndpoint
```

### 12.3. Domain Events

```
ClaimSubmittedEvent
├── claimId: ClaimId
├── insuranceId: InsuranceId
├── protocolNumber: String
├── submissionDateTime: Instant
├── claimAmount: Money
└── timestamp: Instant

ClaimSubmissionFailedEvent
├── claimId: ClaimId
├── insuranceId: InsuranceId
├── errorCode: String
├── errorMessage: String
└── retryable: Boolean
```

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `SubmitClaimDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `submitClaim` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Template Method, Builder |
| **Complexidade Ciclomática** | 6 (Moderada) |
| **Linhas de Código** | 264 |
| **Cobertura de Testes** | 92% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- TissSubmissionService
- DataAccessStrategy
- ClaimValidationUtils

**Serviços Integrados**:
- TissSubmissionService (via interface)
- InsuranceValidationService (via DataAccessStrategy)

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 10s | Submissão síncrona com TISS |
| Pool de Threads | 20 | Baseado em carga estimada |
| Cache TTL (Operadoras) | 1 hora | Dados mudam raramente |
| Retry Máximo | 5 tentativas | Conforme RetrySubmissionDelegate |
| Circuit Breaker | 50% falhas em 1 min | Proteger TISS |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "claim_submitted",
  "claimId": "CLM-ENC-001-1234567890",
  "insuranceId": "ANS-12345",
  "claimAmount": 1550.00,
  "protocolNumber": "ANS123456202501010001",
  "submissionStatus": "SUBMITTED",
  "executionTimeMs": 850,
  "timestamp": "2025-01-12T10:30:00Z"
}
```

**Métricas Prometheus**:
- `claim_submission_duration_seconds` (Histogram)
- `claim_submission_total` (Counter)
- `claim_submission_errors_total` (Counter)
- `claim_tiss_availability` (Gauge)

### 13.5. Testes

**Cenários de Teste**:
1. ✅ Submissão bem-sucedida com protocolo
2. ✅ Operadora não encontrada
3. ✅ Operadora inativa
4. ✅ Operadora não aceita eletrônico
5. ✅ Dados de cobrança inválidos
6. ✅ TISS indisponível (retentável)
7. ✅ Idempotência: mesmo claimId não duplica

---

## XIV. Glossário de Termos

| Termo | Definição |
|-------|-----------|
| **TISS** | Padrão eletrônico de comunicação entre prestadores e operadoras |
| **Protocolo TISS** | Número único de rastreamento da submissão na operadora |
| **Submissão Eletrônica** | Envio de cobrança via TISS em lugar de papel |
| **Status de Submissão** | SUBMITTED (aceito), REJECTED (rejeitado), PENDING (aguardando) |
| **Idempotência** | Submissão repetida do mesmo claimId não gera duplicata |

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
