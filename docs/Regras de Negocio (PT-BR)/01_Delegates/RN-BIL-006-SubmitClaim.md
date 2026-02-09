# RN-BIL-006: Submissão de Conta ao TISS

**ID Técnico**: `SubmitClaimDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Submeter contas médicas ao sistema TISS da operadora de saúde, validando dados previamente, gerando XML conforme padrão ANS, obtendo número de protocolo e registrando status de submissão.

### 1.2. Contexto de Negócio
O TISS (Troca de Informações de Saúde Suplementar) é o padrão obrigatório estabelecido pela ANS para comunicação entre prestadores de serviços de saúde e operadoras. A submissão correta de contas médicas via TISS é crítica para:

- **Conformidade Legal**: ANS exige uso do padrão TISS (RN 305/2012)
- **Recebimento de Pagamentos**: Operadoras só processam contas em formato TISS válido
- **Rastreabilidade**: Número de protocolo TISS permite acompanhamento
- **Padronização**: Reduz erros de interpretação entre sistemas

A submissão envolve:
1. Validação de dados da conta (formato, valores, códigos)
2. Validação da operadora (ativa, aceita submissão eletrônica)
3. Geração de XML TISS conforme schema ANS
4. Envio ao web service da operadora
5. Recebimento de protocolo e status

### 1.3. Benefícios Esperados
- **Conformidade**: Atendimento ao padrão obrigatório ANS
- **Eficiência**: Automação de submissão reduz trabalho manual
- **Rastreabilidade**: Protocolo TISS para acompanhamento
- **Redução de Glosas**: Validação prévia identifica problemas
- **Integração**: Comunicação padronizada com operadoras

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve validar os dados da conta médica e da operadora, construir mensagem XML conforme padrão TISS, submeter ao web service da operadora, processar resposta e registrar protocolo e status de submissão.

**Lógica de Execução**:

1. **Validação de Dados da Conta**
   ```
   VALIDAR claimId:
     - Formato: CLM-.*-\d+
     - Não nulo, não vazio

   VALIDAR insuranceId:
     - Não nulo, não vazio
     - Formato válido

   VALIDAR claimAmount:
     - Não nulo
     - Maior que zero
     - Menor ou igual a R$ 1.000.000,00

   SE alguma_validacao_falhar:
     LANÇAR ERRO "INVALID_CLAIM"
   ```

2. **Validação da Operadora**
   ```
   operadora ← BUSCAR_OPERADORA(insuranceId)

   SE operadora É NULO:
     LANÇAR ERRO "INSURANCE_NOT_FOUND"

   SE operadora.status ≠ "ATIVA":
     LANÇAR ERRO "INSURANCE_NOT_FOUND" COM "Operadora inativa"

   SE NÃO operadora.acceptsElectronicSubmission:
     LANÇAR ERRO "SUBMISSION_FAILED" COM "Sem submissão eletrônica"
   ```

3. **Construção de XML TISS**
   ```
   tissXML ← CONSTRUIR_XML_TISS(
     claimId,
     insuranceId,
     claimAmount,
     execution.variables
   )

   // XML deve conter:
   // - Cabeçalho padrão TISS
   // - Identificação de prestador
   // - Dados do beneficiário
   // - Itens de cobrança detalhados
   // - Totalizadores
   ```

4. **Submissão ao Web Service TISS**
   ```
   TENTAR:
     resposta ← CHAMAR_ENDPOINT_TISS(
       tissXML,
       insuranceId
     )

     protocolNumber ← resposta.protocol
     submissionStatus ← resposta.status

   CAPTURAR TissException:
     LANÇAR ERRO "TISS_UNAVAILABLE"

   CAPTURAR TimeoutException:
     LANÇAR ERRO "SUBMISSION_FAILED" COM "Timeout"

   CAPTURAR Exception:
     LANÇAR ERRO "SUBMISSION_FAILED" COM detalhes
   ```

5. **Geração de Número de Protocolo**
   ```
   Formato TISS: TISS-AAAAMMDDHHMMSS-UUID

   timestamp ← FORMATAR_DATA(AGORA, "yyyyMMddHHmmss")
   uuid_short ← UUID_ALEATORIO.substring(0, 8)

   protocolNumber ← "TISS-" + timestamp + "-" + uuid_short

   Exemplo: TISS-20250112104500-a1b2c3d4
   ```

6. **Classificação de Status**
   ```
   Status possíveis da resposta TISS:
   - SUBMITTED: Recebido e aceito para processamento
   - PENDING: Recebido mas aguardando validação
   - REJECTED: Rejeitado por validações TISS

   // 90% dos casos retornam SUBMITTED
   // 10% retornam PENDING (validação assíncrona)
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-006-V1 | Formato de claimId válido | CRÍTICA | Rejeitar com INVALID_CLAIM |
| BIL-006-V2 | Valor da conta entre R$ 0,01 e R$ 1.000.000,00 | CRÍTICA | Rejeitar com INVALID_CLAIM |
| BIL-006-V3 | Operadora deve existir e estar ativa | CRÍTICA | Rejeitar com INSURANCE_NOT_FOUND |
| BIL-006-V4 | Operadora deve aceitar submissão eletrônica | CRÍTICA | Rejeitar com SUBMISSION_FAILED |
| BIL-006-V5 | XML TISS deve ser válido conforme schema ANS | CRÍTICA | Rejeitar com SUBMISSION_FAILED |
| BIL-006-V6 | Web service TISS deve estar disponível | CRÍTICA | Rejeitar com TISS_UNAVAILABLE |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador de conta (claimId) válido
- Identificador de operadora (insuranceId) válido
- Valor da conta (claimAmount) definido e positivo
- Dados completos da conta disponíveis

**Exceções de Negócio**:

1. **Conta Inválida**
   - **Código**: INVALID_CLAIM
   - **Causa**: Dados da conta não passam em validações básicas
   - **Ação**: Rejeitar submissão
   - **Próximo Passo**: Corrigir dados da conta

2. **Operadora Não Encontrada**
   - **Código**: INSURANCE_NOT_FOUND
   - **Causa**: insuranceId inválido ou operadora inativa
   - **Ação**: Rejeitar submissão
   - **Próximo Passo**: Validar cadastro de operadora

3. **Falha na Submissão**
   - **Código**: SUBMISSION_FAILED
   - **Causa**: Erro ao comunicar com TISS ou XML inválido
   - **Ação**: Registrar erro para retry
   - **Próximo Passo**: Análise de retry (RetrySubmissionDelegate)

4. **TISS Indisponível**
   - **Código**: TISS_UNAVAILABLE
   - **Causa**: Web service da operadora fora do ar
   - **Ação**: Registrar erro transiente para retry
   - **Próximo Passo**: Retry automático com backoff

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador único da conta | Formato: CLM-.*-\d+ |
| `insuranceId` | String | Sim | Identificador da operadora | Não vazio |
| `claimAmount` | BigDecimal | Sim | Valor total da conta | 0 < valor ≤ 1.000.000 |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `submissionStatus` | String | Status da submissão (SUBMITTED, PENDING, REJECTED) | Decisões de fluxo |
| `protocolNumber` | String | Número de protocolo TISS | Rastreamento |
| `submissionDate` | LocalDateTime | Data/hora da submissão | Auditoria e SLA |

**Estrutura de Resposta TISS**:
```json
{
  "submissionStatus": "SUBMITTED",
  "protocolNumber": "TISS-20250112104500-a1b2c3d4",
  "submissionDate": "2025-01-12T10:45:00Z",
  "insuranceCompany": "INS-UNIMED",
  "insuranceResponse": {
    "code": "000",
    "message": "Claim received by TISS system",
    "estimatedProcessingTime": "48h"
  }
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Geração de Número de Protocolo TISS

```
Formato Padrão:
  TISS-{TIMESTAMP}-{UUID_SHORT}

Componentes:
  TIMESTAMP = AAAAMMDDHHMMSS (14 dígitos)
  UUID_SHORT = Primeiros 8 caracteres de UUID v4

Exemplo de Geração:
  Data/Hora: 2025-01-12 10:45:00
  UUID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

  TIMESTAMP = 20250112104500
  UUID_SHORT = a1b2c3d4

  Protocol = "TISS-20250112104500-a1b2c3d4"

Comprimento Total: 28 caracteres
```

### 4.2. Validação de Valor de Conta

```
Entrada:
  amount (BigDecimal)

Regras:
  MIN_AMOUNT = 0.01
  MAX_AMOUNT = 1000000.00

Validação:
  SE amount É NULO:
    RETORNAR INVÁLIDO "Valor não pode ser nulo"

  SE amount ≤ 0:
    RETORNAR INVÁLIDO "Valor deve ser maior que zero"

  SE amount > MAX_AMOUNT:
    RETORNAR INVÁLIDO "Valor excede máximo permitido"

  RETORNAR VÁLIDO
```

### 4.3. Taxa de Sucesso de Submissão

```
Para monitoramento:

Taxa_Sucesso = (Submissões_Aceitas / Total_Submissões) × 100

Onde:
  Submissões_Aceitas = Status SUBMITTED ou PENDING
  Total_Submissões = Todas as tentativas

Exemplo:
  Total: 1000 submissões
  SUBMITTED: 850
  PENDING: 100
  REJECTED: 50

  Taxa_Sucesso = ((850 + 100) / 1000) × 100 = 95%
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Web Service TISS | Envio | XML de conta médica TISS 4.0 | SOAP/HTTPS |
| Sistema de Operadoras | Consulta | Validação de cadastro e status | API REST |
| Sistema de Protocolo | Escrita | Registro de números de protocolo | Database |
| Sistema de Auditoria | Escrita | Log de submissões | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Schema TISS XML (versão 4.0 da ANS)
- Cadastro atualizado de operadoras
- Endpoints de web services por operadora
- Certificados digitais para HTTPS

**Frequência de Atualização**:
- Schema TISS: Anual (conforme ANS)
- Cadastro de operadoras: Diário
- Endpoints: Sob demanda (mudanças raras)
- Certificados: Anual ou conforme vencimento

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Aceitação TISS | % de submissões aceitas | ≥ 95% | (Aceitas / Total) × 100 | Diária |
| Tempo Médio de Submissão | Tempo de processamento | ≤ 10 segundos | Média de duração | Diária |
| Taxa de Disponibilidade TISS | % de tentativas sem falha de conexão | ≥ 99% | (Sucessos Conexão / Total) × 100 | Horária |
| Conformidade com Schema TISS | % de XMLs válidos | 100% | (XMLs Válidos / Total) × 100 | Diária |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Tempo de Geração XML | Duração da construção do XML | > 5 segundos | Otimizar builder |
| Erros TISS_UNAVAILABLE | Falhas de conexão com TISS | > 2% | Verificar rede/endpoints |
| Erros INVALID_CLAIM | Validações que falharam | > 5% | Melhorar validação prévia |
| Tamanho Médio de XML | Tamanho do payload | Monitorar | Otimizar se necessário |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Início da submissão
2. Validação de dados da conta
3. Validação da operadora
4. Construção do XML TISS
5. Envio ao web service
6. Recebimento de protocolo
7. Registro de status

**Informações Capturadas**:
```json
{
  "timestamp": "2025-01-12T10:45:00Z",
  "claimId": "CLM-001-1234567890",
  "insuranceId": "INS-UNIMED",
  "claimAmount": 1500.00,
  "protocolNumber": "TISS-20250112104500-a1b2c3d4",
  "submissionStatus": "SUBMITTED",
  "xmlSize": 15234,
  "responseTime": 3214,
  "endpoint": "https://tiss.unimed.com.br/webservice",
  "executionTimeMs": 3456
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Schema TISS | Preventivo | Por transação | Sistema automático |
| Auditoria de Protocolos | Detectivo | Diária | Equipe de TI |
| Conformidade com ANS | Detectivo | Mensal | Auditoria Interna |
| Disponibilidade de TISS | Detectivo | Contínua | Monitoramento |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| INVALID_CLAIM | Dados da conta inválidos | CRÍTICA | Corrigir dados e resubmeter |
| INSURANCE_NOT_FOUND | Operadora não encontrada ou inativa | CRÍTICA | Validar cadastro |
| SUBMISSION_FAILED | Falha na submissão ao TISS | ALTA | Retry automático |
| TISS_UNAVAILABLE | Web service TISS indisponível | ALTA | Retry automático com backoff |

### 8.2. Estratégia de Retry

**Erros Transientes (retry automático via RetrySubmissionDelegate)**:
- TISS_UNAVAILABLE
- SUBMISSION_FAILED (timeout, conexão)
- Erros HTTP 503, 504

**Erros Permanentes (sem retry)**:
- INVALID_CLAIM (dados incorretos)
- INSURANCE_NOT_FOUND (cadastro)
- Erros HTTP 400, 401, 403

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Submissão Bem-Sucedida

**Cenário**: Submeter conta válida e receber protocolo

**Pré-condições**:
- Conta CLM-001-123 validada
- Operadora INS-UNIMED ativa
- Valor: R$ 1.500,00
- TISS disponível

**Fluxo**:
1. Sistema recebe dados da conta
2. Valida formato claimId: OK
3. Valida valor: R$ 1.500,00 (OK, 0 < 1500 < 1.000.000)
4. Busca operadora INS-UNIMED: Ativa, aceita eletrônica
5. Constrói XML TISS conforme schema
6. Envia ao endpoint TISS da Unimed
7. Recebe resposta:
   - Protocol: TISS-20250112104500-a1b2c3d4
   - Status: SUBMITTED
   - Código: 000 (Sucesso)
8. Registra protocolo no banco
9. Retorna sucesso

**Pós-condições**:
- `submissionStatus` = "SUBMITTED"
- `protocolNumber` = "TISS-20250112104500-a1b2c3d4"
- `submissionDate` = "2025-01-12T10:45:00Z"
- Conta pronta para acompanhamento

**Resultado**: Sucesso com protocolo TISS

### 9.2. Fluxo Alternativo - Operadora Inválida

**Cenário**: Tentar submeter para operadora inativa

**Fluxo**:
1. Sistema recebe insuranceId: "INS-EXPIRED999"
2. Valida dados da conta: OK
3. Busca operadora: Encontrada mas status "INATIVA"
4. Validação falha: operadora não aceita submissões
5. Lança erro INSURANCE_NOT_FOUND
6. Registra em auditoria
7. Notifica equipe de cadastro

**Ações Corretivas**:
- Atualizar cadastro da operadora
- Ou redirecionar para operadora ativa

**Resultado**: Erro com necessidade de atualização

### 9.3. Fluxo de Exceção - TISS Indisponível

**Cenário**: Web service TISS fora do ar

**Fluxo**:
1. Sistema prepara submissão
2. Valida dados: OK
3. Constrói XML: OK
4. Tenta enviar ao TISS
5. Timeout após 30 segundos
6. Captura exceção de conexão
7. Lança erro TISS_UNAVAILABLE
8. Registra para retry automático
9. RetrySubmissionDelegate agenda nova tentativa

**Próximos Passos**:
- Retry automático em 5 minutos
- Se persistir, escalar para equipe

**Resultado**: Erro transiente, retry agendado

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 305/2012 | Art. 2º | Uso obrigatório do padrão TISS | Geração de XML conforme schema TISS 4.0 |
| ANS RN 305/2012 | Art. 3º | Estrutura de dados padronizada | Validação contra schema XSD da ANS |
| ANS IN 41/2018 | Art. 3º | Submissão eletrônica | Envio via web service SOAP/HTTPS |
| Lei 9.656/98 | Art. 25 | Rastreabilidade de contas | Número de protocolo único |
| LGPD Art. 6º | Inciso IX | Segurança na transmissão | HTTPS com certificado digital |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Preparação da conta: Equipe de faturamento
- Validação: Sistema automático
- Submissão: Sistema automático
- Auditoria: Equipe de compliance

**Retenção de Dados**:
- XMLs TISS: 5 anos (ANS)
- Protocolos: 5 anos
- Logs de submissão: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker pattern |
| Chamadas SOAP | Síncronas | Assíncronas com workers | Implementar worker de integração |
| Geração XML | Em memória | Streaming se grande | Considerar streaming para XMLs grandes |
| Protocolo | Gerado no delegate | Gerado em serviço separado | Externalizar geração |

### 11.2. Estratégia de Migração

**Fase 1 - Worker de Submissão**:
```java
@JobWorker(
    type = "submit-claim-tiss",
    timeout = 60_000,
    maxJobsActive = 20
)
public SubmissionResponse submitClaim(
    @Variable String claimId,
    @Variable String insuranceId,
    @Variable BigDecimal claimAmount
) {
    // Validar dados
    // Construir XML TISS
    // Submeter ao web service
    // Retornar protocolo e status
    return submissionResponse;
}
```

**Fase 2 - Integração Assíncrona**:
```
Main Process → Submit Claim Task
    ↓
  [Send Message: submit-tiss-request]
    ↓
TISS Integration Process (async)
├── Build XML
├── Call TISS Web Service
└── Send Response Message
    ↓
Main Process → [Receive: tiss-response]
```

### 11.3. Oportunidades de Melhoria

**Pool de Conexões**:
- Manter pool de conexões HTTP para operadoras
- Reduzir latência de handshake SSL
- Melhorar throughput

**Validação Assíncrona**:
- Validar schema XML em worker separado
- Paralelizar validações
- Cache de schemas XSD

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing Submission (Submissão de Cobrança)

**Sub-domínio**: Core Domain - TISS Integration

**Responsabilidade**: Submissão de contas médicas ao sistema TISS das operadoras

### 12.2. Agregados e Entidades

**Agregado Raiz**: `TISSSubmission`

```
TISSSubmission (Aggregate Root)
├── ClaimId (Value Object)
├── InsuranceId (Value Object)
├── ClaimAmount (Money)
├── ProtocolNumber (Value Object)
├── SubmissionStatus (Enum: SUBMITTED, PENDING, REJECTED)
├── SubmissionDate (Instant)
├── TISSXml (String - large)
├── ResponseData (Value Object)
│   ├── ResponseCode (String)
│   ├── ResponseMessage (String)
│   └── EstimatedProcessing (Duration)
└── CreatedAt (Instant)
```

**Value Objects**:
- `ProtocolNumber`: Número de protocolo TISS único
- `TISSXml`: Representação do XML gerado
- `ResponseData`: Dados da resposta TISS

### 12.3. Domain Events

```
ClaimSubmittedEvent
├── claimId: ClaimId
├── protocolNumber: ProtocolNumber
├── insuranceId: InsuranceId
├── submissionStatus: SubmissionStatus
├── submittedAt: Instant
└── version: Long

TISSSubmissionFailedEvent
├── claimId: ClaimId
├── insuranceId: InsuranceId
├── errorCode: String
├── errorMessage: String
├── failedAt: Instant
└── severity: Severity

TISSUnavailableEvent
├── insuranceId: InsuranceId
├── endpoint: URL
├── detectedAt: Instant
└── severity: Severity.HIGH
```

### 12.4. Serviços de Domínio

**TISSSubmissionService**:
```
Responsabilidades:
- Validar dados antes de submissão
- Construir XML TISS conforme schema
- Submeter ao web service da operadora
- Processar resposta e extrair protocolo

Métodos:
- validateClaim(claim): ValidationResult
- buildTISSXml(claim): TISSXml
- submitToTISS(xml, insurance): SubmissionResponse
- parseProtocol(response): ProtocolNumber
```

### 12.5. Repositories

```
TISSSubmissionRepository
├── save(submission): TISSSubmission
├── findByClaimId(claimId): TISSSubmission
├── findByProtocol(protocol): TISSSubmission
└── findPendingSubmissions(): List<TISSSubmission>

InsuranceRepository
├── findById(insuranceId): Insurance
├── findActive(): List<Insurance>
└── checkElectronicSubmission(id): Boolean
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Submissão TISS | TISS Submission | Envio de conta ao sistema TISS |
| Protocolo | Protocol Number | Número único de rastreamento TISS |
| XML TISS | TISS XML | Mensagem formatada conforme padrão ANS |
| Operadora | Insurance Company | Empresa de plano de saúde |
| Web Service TISS | TISS Endpoint | Interface de comunicação TISS |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `SubmitClaimDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `submitClaim` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Builder (XML), Adapter (TISS) |
| **Complexidade Ciclomática** | 10 (Média-Alta) |
| **Linhas de Código** | 301 |
| **Cobertura de Testes** | 89% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x
- Apache CXF 3.x (SOAP client)
- JAXB 2.x (XML marshalling)

**Serviços Integrados** (futuro):
- TISSXmlBuilder
- TISSWebServiceClient
- InsuranceRegistryService

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 60s | Web service TISS pode ser lento |
| Timeout HTTP | 30s | Evitar espera excessiva |
| Pool de Threads | 20 | Submissões paralelas |
| Max XML Size | 10 MB | Limite TISS típico |
| Connection Pool | 50 conexões | Múltiplas operadoras |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "claim_submitted",
  "claimId": "CLM-001-1234567890",
  "insuranceId": "INS-UNIMED",
  "claimAmount": 1500.00,
  "protocolNumber": "TISS-20250112104500-a1b2c3d4",
  "submissionStatus": "SUBMITTED",
  "responseTime": 3214,
  "xmlSize": 15234,
  "executionTimeMs": 3456,
  "timestamp": "2025-01-12T10:45:00Z"
}
```

**Métricas Prometheus**:
- `tiss_submission_duration_seconds` (Histogram)
- `tiss_submissions_total` (Counter por status)
- `tiss_xml_size_bytes` (Histogram)
- `tiss_errors_total` (Counter por tipo)
- `tiss_availability` (Gauge por operadora)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Submissão bem-sucedida com protocolo
2. ✅ Validação de conta inválida
3. ✅ Operadora não encontrada
4. ✅ Operadora inativa
5. ✅ TISS indisponível (timeout)
6. ✅ XML TISS gerado corretamente
7. ✅ Protocolo no formato correto
8. ✅ Performance com múltiplas submissões

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
