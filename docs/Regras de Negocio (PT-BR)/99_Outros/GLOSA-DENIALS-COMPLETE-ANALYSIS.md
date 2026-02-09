# Análise Completa de Glosas: Delegates, Regras de Negócio e Conformidade Regulatória

**Data**: 2026-01-24
**Versão**: 1.0.0
**Módulo**: Gestão de Glosas (Denial Management)
**Escopo**: Análise integral dos três delegates principais de glosa

---

## RESUMO EXECUTIVO

O sistema de gestão de glosas (denials) implementa um fluxo integrado de três componentes principais:

1. **IdentifyGlosaDelegate** (RN-GLOSA-005): Detecção de discrepâncias entre pagamento recebido vs. esperado
2. **ApplyCorrectionsDelegate** (RN-GLOSA-002): Aplicação de correções específicas para cada tipo de negação
3. **CreateProvisionDelegate** (RN-GLOSA-003): Reconhecimento contábil conservador de perdas

Este documento consolida as regras de negócio, validações, integrações e conformidade regulatória de todos os três componentes.

---

## PARTE 1: IDENTIFICAÇÃO DE GLOSAS (IdentifyGlosaDelegate)

### 1.1 Responsabilidades Principais

O IdentifyGlosaDelegate implementa a detecção automática de glosas através da comparação de valores:

```
glosa_identificada = (valor_esperado ≠ valor_recebido) E (diferença > tolerância)
```

### 1.2 Fluxo de Processamento

```
ENTRADA: claimId, paymentReceived, expectedAmount
  ↓
VALIDAÇÃO: Tipos de dados, domínios positivos/zero
  ↓
CÁLCULO: glosaAmount = expectedAmount - paymentReceived
  ↓
TOLERÂNCIA: diferença_absoluta ≤ (expectedAmount × 1%)
  ↓
CLASSIFICAÇÃO: FULL_DENIAL | PARTIAL_DENIAL | UNDERPAYMENT | OVERPAYMENT | NO_GLOSA
  ↓
SAÍDA: glosaIdentified, glosaAmount, glosaType
```

### 1.3 Classificação de Tipos de Glosa

| Tipo | Condição | Descrição |
|------|----------|-----------|
| **NO_GLOSA** | Diferença dentro de tolerância (1%) | Sem discrepância materially relevant |
| **FULL_DENIAL** | paymentReceived = 0 | Operadora negou totalmente o pagamento |
| **PARTIAL_DENIAL** | 0 < paymentReceived < 50% × expectedAmount | Negação significativa (< 50% pago) |
| **UNDERPAYMENT** | 50% ≤ paymentReceived < 100% × expectedAmount | Subpagamento (> 50% pago) |
| **OVERPAYMENT** | paymentReceived > expectedAmount | Operadora pagou além do esperado |

### 1.4 Lógica de Tolerância

**Propósito**: Evitar falsos positivos de centavos causados por arredondamentos.

**Fórmula**:
```
tolerance_percentage = 0.01  // 1% é padrão
tolerance_absolute = expectedAmount × tolerance_percentage
within_tolerance = ABS(expectedAmount - paymentReceived) ≤ tolerance_absolute
```

**Exemplo Prático**:
- Esperado: R$ 1.000,00
- Recebido: R$ 1.009,50 (diferença de R$ 9,50)
- Tolerância: 1.000,00 × 1% = R$ 10,00
- Resultado: Dentro da tolerância → NO_GLOSA

### 1.5 Validações de Entrada

```java
// Validação RN-GLOSA-005-VLD-001
SE claimId = NULL OU claimId.isEmpty()
  ENTÃO lançar erro: INVALID_CLAIM_DATA ("Claim ID is required")

// Validação RN-GLOSA-005-VLD-002
SE paymentReceived < 0
  ENTÃO lançar erro: INVALID_AMOUNT ("Payment cannot be negative")

// Validação RN-GLOSA-005-VLD-003
SE expectedAmount ≤ 0
  ENTÃO lançar erro: INVALID_AMOUNT ("Expected amount must be positive")

// Validação RN-GLOSA-005-VLD-004 (conversão)
tipos_suportados = [BigDecimal, Double, Integer, Long, String]
SE valor.class NÃO IN tipos_suportados
  ENTÃO lançar erro: INVALID_AMOUNT ("Unsupported type")
```

### 1.6 Tratamento de Tipos de Dados

IdentifyGlosaDelegate suporta múltiplos tipos de entrada e normaliza para BigDecimal:

```java
extractAmount(execution, "paymentReceived"):
  IF valor instanceof BigDecimal → retorna como-é
  ELSE IF valor instanceof Double → BigDecimal.valueOf((Double))
  ELSE IF valor instanceof Integer → BigDecimal.valueOf((Integer))
  ELSE IF valor instanceof Long → BigDecimal.valueOf((Long))
  ELSE IF valor instanceof String → new BigDecimal((String))
  ELSE → erro INVALID_AMOUNT
```

### 1.7 Cálculo de Percentual de Pagamento

Para classificação PARTIAL_DENIAL vs UNDERPAYMENT:

```
percentual_pago = (paymentReceived / expectedAmount) × 100

classificação = CASO
  QUANDO percentual_pago < 50%
    ENTÃO PARTIAL_DENIAL (negação significativa)
  QUANDO percentual_pago ≥ 50%
    ENTÃO UNDERPAYMENT (subpagamento)
FIM CASO
```

### 1.8 Idempotência

IdentifyGlosaDelegate é **naturalmente idempotente**:
- Não altera dados de origem
- Operação é read-only (apenas cálculos)
- Mesmos inputs sempre produzem mesmos outputs
- Seguro para retry sem efeitos colaterais

---

## PARTE 2: APLICAÇÃO DE CORREÇÕES (ApplyCorrectionsDelegate)

### 2.1 Responsabilidades Principais

O ApplyCorrectionsDelegate implementa correções específicas para cada código de negação TISS:

```
ENTRADA: claimId, denialCode, denialCategory, foundDocuments, correctionNotes
  ↓
ROTEAMENTO: Mapear código TISS → CorrectionStrategy
  ↓
EXECUÇÃO: Aplicar correção conforme estratégia específica
  ↓
VALIDAÇÃO: Confirmar correção via regras TISS
  ↓
REENVIO: Marcar como pronto para resubmissão
  ↓
SAÍDA: correctionApplied, correctionType, readyForResubmission
```

### 2.2 Estratégias de Correção por Código TISS

| Código TISS | Motivo | Estratégia | Ações |
|-------------|--------|-----------|-------|
| **01** | Duplicidade | DUPLICATE_RESOLUTION | Buscar similares; anular dup; evidenciar unicidade |
| **03** | Não Autorizado | AUTHORIZATION_APPEAL | Buscar auth em documentos; adicionar número |
| **04/08** | Código Incorreto | CODE_CORRECTION | Validar via TISS; corrigir TUSS; validar |
| **05** | Valor > Contratado | PRICE_ADJUSTMENT | Recuperar preço contratual; ajustar valor |
| **06** | Falta Documentação | DOCUMENTATION_ATTACHMENT | Anexar documentos disponíveis; validar completude |
| **09** | CID Incompatível | DIAGNOSIS_CORRECTION | Validar compatibilidade; buscar CID compatível; atualizar |

### 2.3 Arquitetura de Estratégias

ApplyCorrectionsDelegate usa **Strategy Pattern** via `CorrectionStrategyRegistry`:

```java
// Interface
interface CorrectionStrategy {
  String getStrategyName()
  CorrectionResult applyCorrection(
    claimId: String,
    denialCode: String,
    claimData: Map<String, Object>,
    foundDocuments: List<Map>,
    correctionNotes: String
  ): CorrectionResult
}

// Implementações
class DuplicateResolutionStrategy implements CorrectionStrategy { ... }
class AuthorizationAppealStrategy implements CorrectionStrategy { ... }
class CodeCorrectionStrategy implements CorrectionStrategy { ... }
class PriceAdjustmentStrategy implements CorrectionStrategy { ... }
class DocumentationAttachmentStrategy implements CorrectionStrategy { ... }
class DiagnosisCorrectionStrategy implements CorrectionStrategy { ... }

// Registry (lookup)
CorrectionStrategyRegistry:
  findStrategy(denialCode: String): Optional<CorrectionStrategy>
```

### 2.4 Fluxo de Decisão para Cada Código

#### Código 01: Duplicidade

```
BUSCAR similares no TASY:
  searchSimilarClaims(claimId) → List<Claim>

SE similares.isEmpty()
  AÇÃO: REENVIA_COM_EVIDENCIA
  RESULTADO: readyForResubmission = TRUE
  NOTES: "Unicidade comprovada"
SENÃO
  AÇÃO: ANULA_DUPLICATA
  RESULTADO: readyForResubmission = FALSE
  NOTES: "Duplicata identificada e anulada"
```

#### Código 03: Não Autorizado

```
BUSCAR autorização:
  searchAuthorizationNumber(claimId, claimData) → String?

SE autorização encontrada
  AÇÃO: updateClaimAuthorization(claimId, authNumber)
  RESULTADO: readyForResubmission = TRUE
  NOTES: "Autorização adicionada: " + authNumber
SENÃO
  AÇÃO: REQUER_SOLICITACAO_AUTHORIZATION
  RESULTADO: readyForResubmission = FALSE
  NOTES: "Autorização não encontrada"
```

#### Código 04/08: Código Incorreto

```
VALIDAR código via TISS Client:
  validateProcedureCode(procedureCode) → Boolean

SE código_válido
  AÇÃO: REENVIA_COM_VALIDACAO
  RESULTADO: readyForResubmission = TRUE
  NOTES: "Código TUSS validado"
SENÃO
  AÇÃO: REQUER_REVISAO_MANUAL
  RESULTADO: readyForResubmission = FALSE
  NOTES: "Código TUSS inválido: " + procedureCode
```

#### Código 05: Valor > Contratado

```
RECUPERAR preço contratado:
  contractPrice = getContractedPrice(payerId, procedureCode)

SE valor_faturado > valor_contratado
  novo_valor = valor_contratado
  AÇÃO: updateClaimAmount(claimId, novo_valor)
  RESULTADO: readyForResubmission = TRUE
  NOTES: "Valor ajustado de " + valor_faturado + " para " + novo_valor
SENÃO
  AÇÃO: REENVIA_COM_JUSTIFICATIVA
  RESULTADO: readyForResubmission = TRUE
  NOTES: "Valor já está dentro do contratado"
```

#### Código 06: Falta Documentação

```
DOCUMENTOS disponíveis:
  docs = foundDocuments (de SearchEvidenceDelegate)

SE docs.size() > 0
  PARA CADA documento:
    attachDocumentToClaim(claimId, documentId, documentType)
  AÇÃO: REENVIA_COM_DOCUMENTACAO
  RESULTADO: readyForResubmission = TRUE
  NOTES: "Documentos anexados: " + docs.size()
SENÃO
  AÇÃO: REQUER_INTERVENCAO_MANUAL
  RESULTADO: readyForResubmission = FALSE
  NOTES: "Nenhum documento disponível para anexação"
```

#### Código 09: CID Incompatível

```
VALIDAR compatibilidade:
  isCompatible = validateDiagnosisProcedureCompatibility(
    procedureCode,
    diagnosisCode
  )

SE NÃO isCompatible
  diagnosis = searchCompatibleDiagnosis(claimId, procedureCode)
  SE diagnosis encontrado
    AÇÃO: updateClaimDiagnosis(claimId, diagnosis)
    RESULTADO: readyForResubmission = TRUE
    NOTES: "CID atualizado para " + diagnosis
  SENÃO
    AÇÃO: REQUER_REVISAO_MEDICA
    RESULTADO: readyForResubmission = FALSE
    NOTES: "CID incompatível, nenhuma alternativa encontrada"
SENÃO
  AÇÃO: REENVIA_COM_VALIDACAO
  RESULTADO: readyForResubmission = TRUE
  NOTES: "CID e procedimento compatíveis"
```

### 2.5 Estrutura de CorrectionResult

```java
@Data
class CorrectionResult {
  String claimId;              // ID original da conta
  String correctedClaimId;     // ID da conta corrigida (se nova)
  String correctionType;       // Tipo de correção aplicado
  boolean success;             // Se correção foi bem-sucedida
  boolean readyForResubmission; // Se pronto para reenvio
  Map<String, Object> details; // Detalhes da correção
  LocalDateTime resubmissionDate; // Data de reenvio
  List<String> attachedDocuments; // Documentos anexados
  String notes;               // Notas sobre a correção
  LocalDateTime createdAt;
  LocalDateTime updatedAt;
}
```

### 2.6 Integração com TASY ERP

ApplyCorrectionsDelegate chama TasyClient para:

```java
// Obter detalhes completos da conta
TasyClaimDTO claimDto = tasyClient.getClaimDetails(claimId)

// Buscar contas similares
List<TasyClaimDTO> similar = tasyClient.searchSimilarClaims(claimId)

// Recuperar preço contratado
BigDecimal price = tasyClient.getContractedPrice(payerId, procedureCode)

// Buscar CID compatível
String compatibleDiagnosis = tasyClient.getCompatibleDiagnosis(claimId, procedureCode)

// Atualizar valores
tasyClient.updateClaimAmount(claimId, newAmount)

// Atualizar diagnóstico
tasyClient.updateClaimDiagnosis(claimId, diagnosisCode)

// Adicionar autorização
tasyClient.updateClaimAuthorization(claimId, authNumber)

// Anexar documento
tasyClient.attachDocumentToClaim(claimId, documentId, type)

// Reenviar conta
tasyClient.resubmitClaim(claimId)
```

### 2.7 Tratamento de Falhas

```java
SE strategy NÃO encontrada para denialCode
  ENTÃO:
    result = CorrectionResult.builder()
      .success(false)
      .readyForResubmission(false)
      .correctionType("UNKNOWN")
      .details({"denialCode": denialCode, "manualReview": true})
      .notes("No correction strategy found for denial code: " + denialCode)
      .build()
SE strategy.applyCorrection() LANÇA exceção
  ENTÃO:
    result = FAILURE_RESULT (mesmo como acima)
```

### 2.8 Idempotência

ApplyCorrectionsDelegate **requer idempotência explícita**:
- Múltiplos reenvios da mesma conta não devem criar duplicadas
- Anexação de documentos deve ser idempotente
- Ajustes de valores devem ser reversíveis
- **Implementação**: Verificar estado anterior antes de aplicar mudanças

---

## PARTE 3: CRIAÇÃO DE PROVISÃO (CreateProvisionDelegate)

### 3.1 Responsabilidades Principais

O CreateProvisionDelegate implementa reconhecimento contábil conservador de glosas:

```
ENTRADA: glosaId, glosaAmount, accountingPeriod
  ↓
CÁLCULO: provisionAmount = glosaAmount × 100% (conservador)
  ↓
GERAÇÃO: provisionId = "PROV-{glosaId}-{timestamp}"
  ↓
CRIAÇÃO: Insert em glosa_provisions
  ↓
LANÇAMENTOS: Débito 6301, Crédito 2101
  ↓
INTEGRAÇÃO: Enfileirar para ERP
  ↓
NOTIFICAÇÃO: Publicar evento Kafka
  ↓
SAÍDA: provisionId, provisionAmount, provisionCreated, provisionDate
```

### 3.2 Cálculo de Provisão

**Princípio**: Conservadorismo Contábil

```
provision_amount = glosa_amount × 1.0  // 100% - conservador
```

**Justificativa**: Reconhecer 100% da glosa como passivo até recuperação:
- Assegura prudência contábil
- Evita subestimação de perdas
- Atende CPC 25 (Provisões)
- Permite ajustes futuros baseados em histórico de recuperação

### 3.3 Estrutura de Lançamentos Contábeis

```
Tipo: Double Entry Journal Entry
Período: accountingPeriod (YYYY-MM)

Lançamento Débito:
  Conta: 6301 (Provision Expense - Despesa de Provisão)
  Débito: provision_amount
  Crédito: 0
  Descrição: "Provisão de Glosa"
  Referência: "PROV-{glosaId}"

Lançamento Crédito:
  Conta: 2101 (Provision for Glosas - Passivo)
  Débito: 0
  Crédito: provision_amount
  Descrição: "Provisão para Glosas"
  Referência: "PROV-{glosaId}"

Validação:
  Débito Total = Crédito Total = provision_amount
```

### 3.4 Geração de ID de Provisão

```
provisionId = "PROV-" + glosaId + "-" + System.currentTimeMillis()

Exemplo: "PROV-GLO-20260124-00001-1738108800000"

Garantias:
- Unicidade assegurada por timestamp
- Rastreabilidade clara
- Sortimento por timestamp permite auditoria
```

### 3.5 Período Contábil

```java
SE accountingPeriod == null
  ENTÃO:
    ano_atual = LocalDateTime.now().getYear()       // 2026
    mes_atual = LocalDateTime.now().getMonthValue() // 01
    accountingPeriod = ano_atual + "-" + String.format("%02d", mes_atual)
    // Resultado: "2026-01"
SENÃO:
  USAR accountingPeriod fornecido
```

### 3.6 Operações de Banco de Dados

```sql
-- Criação de Registro de Provisão
INSERT INTO glosa_provisions (
  provision_id,
  glosa_id,
  amount,
  period,
  created_at
) VALUES (
  'PROV-GLO-20260124-00001-1738108800000',
  'GLO-20260124-00001',
  5000.00,
  '2026-01',
  NOW()
)

-- Lançamentos Contábeis
INSERT INTO journal_entries (
  account_code,
  debit,
  credit,
  period,
  reference,
  created_at
) VALUES
  ('6301', 5000.00, 0, '2026-01', 'PROV-GLO-20260124-00001-1738108800000', NOW()),
  ('2101', 0, 5000.00, '2026-01', 'PROV-GLO-20260124-00001-1738108800000', NOW())
```

### 3.7 Integração com ERP

```yaml
Operação: POST /api/v1/provisions (quando ERPIntegrationService implementado)

Payload:
  provisionId: "PROV-GLO-20260124-00001-1738108800000"
  glosaId: "GLO-20260124-00001"
  amount: 5000.00
  accountingPeriod: "2026-01"
  debitAccount: "6301"
  creditAccount: "2101"
  journalEntries:
    - { account: "6301", debit: 5000.00, credit: 0, period: "2026-01" }
    - { account: "2101", debit: 0, credit: 5000.00, period: "2026-01" }

Resposta:
  erpProvisionId: "ERP-12345"
  status: "CREATED"
  integrationDate: "2026-01-24T10:30:00Z"

Tratamento de Falha:
  SE erro na integração
    ENTÃO: registrar log, continuar com provisão local, agendar retry
    NÃO interromper fluxo
```

### 3.8 Notificação via Kafka

```json
Topic: financial-provisions
Evento:
{
  "eventType": "ProvisionCreated",
  "provisionId": "PROV-GLO-20260124-00001-1738108800000",
  "glosaId": "GLO-20260124-00001",
  "amount": 5000.00,
  "accountingPeriod": "2026-01",
  "createdAt": "2026-01-24T10:30:00Z",
  "debitAccount": "6301",
  "creditAccount": "2101",
  "status": "CREATED"
}

Subscribers:
  - Dashboard Financeiro
  - Sistema de Controllers (email/notificação)
  - Auditoria e Compliance
```

### 3.9 Atualização de Status de Glosa

```sql
UPDATE glosas
SET
  status = 'PROVISIONED',
  provisioned = true,
  provision_id = 'PROV-GLO-20260124-00001-1738108800000',
  provision_date = NOW()
WHERE glosa_id = 'GLO-20260124-00001'
```

### 3.10 Idempotência

CreateProvisionDelegate **requer idempotência**:

```java
// Verificar se provisão já existe
Optional<Provision> existing = provisionsRepository
  .findByGlosaId(glosaId)

SE existing.isPresent()
  ENTÃO:
    // Retornar provisão existente sem criar duplicata
    return existing.get()
SENÃO:
  // Criar nova provisão
  Provision newProvision = createNewProvision(...)
  return newProvision
```

---

## PARTE 4: CONFORMIDADE REGULATÓRIA INTEGRADA

### 4.1 Mapeamento de Normas x Delegates

| Norma | Artigo | Requisito | Implementação |
|-------|--------|-----------|----------------|
| **ANS Res. 395/2016** | Art. 17 | Transparência em negações | IdentifyGlosa: registra todas diferenças |
| **ANS Res. 395/2016** | Art. 18-19 | Prazos para recursos | ApplyCorrections: marca data de reenvio |
| **ANS Res. 395/2016** | Art. 20 | 10 dias para correção | ApplyCorrections: timestamps para auditoria |
| **ANS Res. 395/2016** | Art. 21 | Documentação comprobatória | ApplyCorrections: anexa documentos |
| **TISS 4.0** | Tabela 44 | Motivos de Glosa (01-99) | ApplyCorrections: mapeia códigos TISS |
| **TISS 4.0** | Seção 3.2.1 | Correção de códigos procedimentos | ApplyCorrections: valida via TISS Client |
| **CPC 48** | Itens 10, 36 | Reconhecimento provisões | CreateProvision: 100% conservador |
| **CPC 25** | Itens 14, 36 | Provisões, passivos contingentes | CreateProvision: lançamentos contábeis |
| **Lei 6.404/1976** | Art. 183 | Avaliação de passivos | CreateProvision: contas 2101 (passivo) |
| **LGPD Lei 13.709** | Art. 6º | Minimização de dados | Todos: processam apenas dados necessários |

### 4.2 TISS - Tabela 44 (Motivos de Glosa)

CreateProvisionDelegate e ApplyCorrectionsDelegate usam códigos TISS:

```
01 - Duplicidade de faturamento
03 - Falta de autorização
04 - Código inválido
05 - Valor acima do contratado
06 - Falta de documentação obrigatória
08 - Código incorreto
09 - CID incompatível com o código da guia
... (códigos adicionais conforme tabela TISS)
```

### 4.3 CPC 48 - Instrumentos Financeiros

**Reconhecimento de Provisão**:
- Quando glosa identificada → PassivoIdentificado
- Provisão = 100% × Valor Glosa (conservador)
- Contas: Débito 6301 (Expense), Crédito 2101 (Liability)

**Reversão de Provisão**:
- Quando glosa recuperada → ReverterProvisão
- Lançamento inverso ao reconhecimento original
- Reconhecer ganho em receita (componente de CPC 48)

### 4.4 ANS - Prazos Regulatórios

```
Timeline de Conformidade:

[Glosa Recebida]
  ↓ (0 dias)
[IdentifyGlosa: Detectar e Classificar]
  ↓ (até 1 dia)
[ApplyCorrections: Aplicar Estratégia de Recurso]
  ↓ (até 10 dias conforme ANS Art. 20)
[Reenvio de Conta Corrigida]
  ↓ (até 10 dias)
[Resposta Operadora]
```

Implementação: Todos delegates registram timestamps para auditoria de conformidade.

---

## PARTE 5: FLUXO INTEGRADO DE GLOSAS

### 5.1 Sequência de Execução no BPMN

```
[RECEBIMENTO DE GLOSA]
       ↓
[IdentifyGlosaDelegate]
  • Comparar valores
  • Calcular diferença
  • Aplicar tolerância (1%)
  • Classificar tipo (FULL/PARTIAL/UNDERPAYMENT/OVERPAYMENT)
       ↓
[SearchEvidenceDelegate] ← paralelo
  • Buscar documentos clínicos
  • Encontrar autorizações
  • Coletar comprovantes
       ↓
[ApplyCorrectionsDelegate]
  • Roteamento por denialCode
  • Execução de estratégia específica
  • Validação de correção
  • Marcação como pronto para reenvio
       ↓
[CreateProvisionDelegate]
  • Cálculo conservador (100%)
  • Criação de lançamentos contábeis
  • Integração ERP
  • Notificação financeira
       ↓
[REENVIO DE CONTA CORRIGIDA]
```

### 5.2 Dados Compartilhados Entre Delegates

```
Variáveis de Processo BPMN:

IdentifyGlosa OUTPUT:
  • glosaIdentified: Boolean
  • glosaAmount: BigDecimal
  • glosaType: String

ApplyCorrections INPUT (alguns):
  • claimId (de entrada inicial)
  • denialCode (identificado via IdentifyGlosa tipo)
  • foundDocuments (de SearchEvidence)

ApplyCorrections OUTPUT:
  • correctionApplied: Boolean
  • readyForResubmission: Boolean
  • correctionDetails: Map

CreateProvision INPUT:
  • glosaId (de IdentifyGlosa)
  • glosaAmount (de IdentifyGlosa)

CreateProvision OUTPUT:
  • provisionId: String
  • provisionCreated: Boolean
  • accountingPeriod: String
```

### 5.3 Caminhos Alternativos por Tipo de Glosa

```
FULL_DENIAL (paymentReceived = 0)
  ├→ ApplyCorrections com alta prioridade
  ├→ Documentação completa requerida
  └→ Provisão 100%

PARTIAL_DENIAL (< 50% pago)
  ├→ ApplyCorrections com prioridade média
  ├→ Análise de motivo necessária
  └→ Provisão do saldo não pago

UNDERPAYMENT (50-99% pago)
  ├→ ApplyCorrections com prioridade baixa
  ├→ Pode incluir ajustes de código/valor
  └→ Provisão da diferença

OVERPAYMENT (> 100% pago)
  ├→ Sem ApplyCorrections (não é negação)
  └→ Sem CreateProvision (é crédito)
```

---

## PARTE 6: ENTIDADES DE DOMÍNIO E RELACIONAMENTOS

### 6.1 Agregados e Value Objects

```
AGGREGADO: Glosa
├─ Entidade Raiz: Glosa
│  ├─ glosaId: String (ID)
│  ├─ claimId: String (Referência)
│  ├─ originalAmount: BigDecimal
│  ├─ glosaAmount: BigDecimal
│  ├─ glosaType: String (FULL_DENIAL | PARTIAL_DENIAL | UNDERPAYMENT)
│  ├─ denialCode: String (TISS code 01-99)
│  ├─ denialReason: String
│  ├─ status: String (IDENTIFIED | ANALYZED | CORRECTED | PROVISIONED | APPEALED)
│  ├─ createdAt: LocalDateTime
│  └─ updatedAt: LocalDateTime
│
├─ Entidade: Análise de Glosa
│  ├─ analysisId: String
│  ├─ glosaId: String (FK)
│  ├─ analysisType: String (AUTOMATIC | MANUAL)
│  ├─ strategyRecommended: String
│  ├─ priorityLevel: String (HIGH | MEDIUM | LOW)
│  ├─ recoveryProbability: Double (0-1)
│  ├─ analysisDate: LocalDateTime
│  └─ analysisNotes: String
│
├─ Entidade: Correção Aplicada
│  ├─ correctionId: String
│  ├─ glosaId: String (FK)
│  ├─ correctionType: String
│  ├─ originalValue: BigDecimal
│  ├─ correctedValue: BigDecimal
│  ├─ documentsAttached: List<String>
│  ├─ approvedForResubmission: Boolean
│  ├─ resubmissionDate: LocalDateTime
│  └─ correctionNotes: String
│
└─ Entidade: Provisão Contábil
   ├─ provisionId: String
   ├─ glosaId: String (FK)
   ├─ provisionAmount: BigDecimal
   ├─ accountingPeriod: String (YYYY-MM)
   ├─ journalEntries: List<JournalEntry>
   ├─ erpIntegrationStatus: String (PENDING | CREATED | FAILED)
   ├─ erpProvisionId: String (quando integrado)
   ├─ createdAt: LocalDateTime
   └─ reversalDate: LocalDateTime (quando revertida)

VALUE OBJECT: Tolerância
├─ percentageThreshold: BigDecimal = 0.01 (1%)
├─ aplicarToleância(expectedAmount, difference): Boolean

VALUE OBJECT: Período Contábil
├─ ano: Integer
├─ mês: Integer
├─ format(): String = "YYYY-MM"

VALUE OBJECT: Código TISS
├─ codigo: String (01-99)
├─ descrição: String
├─ estratégia: String
```

### 6.2 Relacionamentos

```
Glosa
  1..*─────────────1 Operadora (Payer)
  1..*─────────────1 Conta (Claim)
  1.1─────────────1 Análise de Glosa
  0..*─────────────1 Correção Aplicada
  0..1────────────1 Provisão Contábil

Análise de Glosa
  *..*─────────────* Motivo de Negação (TISS)
  *..*─────────────* Estratégia de Recurso

Correção Aplicada
  *..*─────────────* Documento
  *..*─────────────* Validação TISS

Provisão Contábil
  1..*─────────────* Lançamento Contábil
  1.1─────────────1 Integração ERP
```

---

## PARTE 7: CASOS DE USO E EXEMPLOS PRÁTICOS

### 7.1 Caso de Uso 1: Negação Total por Autorização Faltante

```
[SCENARIO]
Operadora nega 100% do pagamento porque autorização faltava.
Valor: R$ 5.000,00
Código TISS: 03 (Não Autorizado)

[FLUXO]

1. IdentifyGlosaDelegate:
   Input: claimId="CLM001", expectedAmount=5000, paymentReceived=0
   Cálculo: glosaAmount = 5000 - 0 = 5000
   Tolerância: 5000 × 1% = 50 → 5000 > 50 → fora de tolerância
   Classificação: glosaType = "FULL_DENIAL"
   Output: glosaIdentified=true, glosaAmount=5000, glosaType="FULL_DENIAL"

2. SearchEvidenceDelegate:
   Busca por número de autorização em documentos → ENCONTRADA: "AUTH-20260101-001"
   Output: foundDocuments=[{type: "AUTHORIZATION", number: "AUTH-20260101-001"}]

3. ApplyCorrectionsDelegate:
   Input: claimId="CLM001", denialCode="03", foundDocuments=[...]
   Roteamento: denialCode "03" → AuthorizationAppealStrategy
   Execução:
     - searchAuthorizationNumber(claimId, documents) → "AUTH-20260101-001"
     - tasyClient.updateClaimAuthorization("CLM001", "AUTH-20260101-001")
     - Validação: AUTH_FOUND → OK
   Output: correctionApplied=true, readyForResubmission=true,
           correctionType="AUTHORIZATION_ADDED"

4. CreateProvisionDelegate:
   Input: glosaId="GLO-001", glosaAmount=5000, accountingPeriod="2026-01"
   Cálculo: provisionAmount = 5000 × 100% = 5000
   Geração ID: "PROV-GLO-001-1738108800000"
   Lançamentos:
     - Débito: Conta 6301 (Expense) = 5000
     - Crédito: Conta 2101 (Liability) = 5000
   ERP Integration: POST /api/v1/provisions → QUEUED
   Kafka: {"eventType": "ProvisionCreated", "provisionId": "PROV-GLO-001-...", ...}
   Output: provisionCreated=true, provisionId="PROV-GLO-001-..."

[RESULTADO]
✓ Glosa identificada e classificada como FULL_DENIAL
✓ Autorização adicionada e conta pronta para reenvio
✓ Provisão contábil criada (passivo R$ 5.000)
✓ Controladores financeiros notificados
```

### 7.2 Caso de Uso 2: Subpagamento por Valor Acima do Contratado

```
[SCENARIO]
Operadora paga 70% do valor porque faturamos acima da tabela contratual.
Esperado: R$ 10.000,00
Recebido: R$ 7.000,00
Diferença: R$ 3.000,00
Contratado: R$ 8.000,00 (máximo)
Código TISS: 05 (Valor > Contratado)

[FLUXO]

1. IdentifyGlosaDelegate:
   Input: claimId="CLM002", expectedAmount=10000, paymentReceived=7000
   Cálculo: glosaAmount = 10000 - 7000 = 3000
   Tolerância: 10000 × 1% = 100 → 3000 > 100 → fora de tolerância
   Percentual: (7000 / 10000) × 100 = 70%
   Classificação: 70% >= 50% → glosaType = "UNDERPAYMENT"
   Output: glosaIdentified=true, glosaAmount=3000, glosaType="UNDERPAYMENT"

2. ApplyCorrectionsDelegate:
   Input: claimId="CLM002", denialCode="05"
   Roteamento: denialCode "05" → PriceAdjustmentStrategy
   Execução:
     - payerId="PAY-001", procedureCode="3010101"
     - contractPrice = getContractedPrice("PAY-001", "3010101") → 8000
     - valorFaturado = 10000
     - SE 10000 > 8000:
         newAmount = 8000
         tasyClient.updateClaimAmount("CLM002", 8000)
     - Agora esperado = 8000, recebido = 7000, diferença = 1000
   Output: correctionApplied=true, correctionType="PRICE_ADJUSTMENT",
           readyForResubmission=true,
           details={"original": 10000, "adjusted": 8000}

3. CreateProvisionDelegate:
   Input: glosaId="GLO-002", glosaAmount=1000 (diferença final)
   Cálculo: provisionAmount = 1000 × 100% = 1000
   Lançamentos: Débito 6301=1000, Crédito 2101=1000
   Output: provisionCreated=true, provisionId="PROV-GLO-002-..."

[RESULTADO]
✓ Glosa identificada como UNDERPAYMENT (70% pago)
✓ Valor ajustado de 10.000 para 8.000 (contratado)
✓ Nova diferença calculada: 1.000
✓ Provisão criada para saldo não pago: 1.000
✓ Conta pronta para reenvio com valor corrigido
```

### 7.3 Caso de Uso 3: Tolerância de Arredondamento

```
[SCENARIO]
Operadora paga valor praticamente igual (diferença de centavos por arredondamento).
Esperado: R$ 1.000,00
Recebido: R$ 1.009,50
Diferença: R$ -9,50 (overpayment de centavos)

[FLUXO]

1. IdentifyGlosaDelegate:
   Input: claimId="CLM003", expectedAmount=1000, paymentReceived=1009.50
   Cálculo: glosaAmount = 1000 - 1009.50 = -9.50
   Tolerância: 1000 × 1% = 10
   ABS(-9.50) = 9.50
   withinTolerance: 9.50 <= 10 → TRUE
   Classificação: isWithinTolerance = true → glosaType = "NO_GLOSA"
   Output: glosaIdentified=false, glosaType="NO_GLOSA"

[RESULTADO]
✓ Diferença identificada como arredondamento (dentro de 1%)
✓ Nenhuma glosa registrada
✓ Nenhuma correção necessária
✓ Nenhuma provisão contábil criada
✓ Processo termina sem ações adicionais
```

---

## PARTE 8: TRATAMENTO DE EXCEÇÕES CONSOLIDADO

### 8.1 Matriz de Exceções

| Exceção | Origem | Código BPMN | Tratamento | Escalação |
|---------|--------|------------|-----------|-----------|
| Claim não encontrado | ApplyCorrections | CLAIM_NOT_FOUND | Log + retry | Manual review |
| Valor inválido | IdentifyGlosa | INVALID_AMOUNT | Rejeita fluxo | Manual review |
| Código TISS inválido | ApplyCorrections | INVALID_DENIAL_CODE | Log + aplica genérico | Manual review |
| Falha integração TASY | ApplyCorrections | TASY_INTEGRATION_ERROR | Log + continua | Assincrono retry |
| Falha integração ERP | CreateProvision | ERP_INTEGRATION_ERROR | Log + continua | Assincrono retry |
| Período fechado | CreateProvision | CLOSED_PERIOD | Rejeita fluxo | Solicita período atual |
| Estratégia não encontrada | ApplyCorrections | UNKNOWN_STRATEGY | Aplica genérico | Manual review |
| Documentos insuficientes | ApplyCorrections | INSUFFICIENT_DOCS | readyForResubmission=false | Coleta manual |

### 8.2 Fluxo de Tratamento de Exceção (ApplyCorrections)

```java
TRY:
  strategy = strategyRegistry.findStrategy(denialCode)
  IF strategy.isEmpty():
    result = createFailureResult("No strategy for: " + denialCode)
  ELSE:
    result = strategy.applyCorrection(...)
CATCH Exception e:
  log.error("Strategy execution failed: " + e.getMessage())
  result = createFailureResult("Correction failed: " + e.getMessage())
FINALLY:
  setExecutionVariables(execution, result)
  // Fluxo continua, não interrompe
```

---

## PARTE 9: KPIs E MÉTRICAS CONSOLIDADAS

### 9.1 KPIs por Delegate

**IdentifyGlosaDelegate**:
- Taxa de Detecção: 100% (detecta todas as diferenças > tolerância)
- Falsos Positivos: < 0.1%
- Tempo de Identificação: < 100ms
- Acurácia de Classificação: 98%

**ApplyCorrectionsDelegate**:
- Taxa de Correção Automática: 70%
- Tempo Médio de Correção: < 24h
- Taxa de Aceitação Pós-Correção: 85%
- Taxa de Reenvio Bem-Sucedido: 90%

**CreateProvisionDelegate**:
- Taxa de Criação Automática: 100%
- Tempo de Criação: < 500ms
- Taxa de Sucesso ERP: > 95%
- Acurácia de Lançamentos: 100%

### 9.2 KPIs Financeiros

- **Total Provisionado**: Soma de provisões ativas
- **Idade Média de Provisões**: Tempo médio antes de reversão
- **Taxa de Recuperação**: % de glosas recuperadas
- **Tempo de Ciclo**: Dias de identificação até recuperação

---

## PARTE 10: RECOMENDAÇÕES E MELHORIAS FUTURAS

### 10.1 Otimizações Imediatas

1. **Machine Learning em ApplyCorrections**:
   - Treinar modelo para prever sucesso de cada estratégia
   - Ajustar priorização de estratégias por histórico

2. **Probabilidade de Recuperação em CreateProvision**:
   - Calcular probabilidade baseada em tipo e histórico
   - Provisão = glosa × (1 - probabilidade_recuperação)
   - Mais realista que 100% conservador

3. **Integração ERP Síncrona**:
   - Atual: Enfileirada e assíncrona
   - Melhor: Integração real-time quando ERP disponível

### 10.2 Conformidade Futura

1. **Camunda 7 → Camunda 8 Migration**:
   - Esforço estimado: 40-60 horas combinado
   - Maior impacto: Transações assíncronas e jobs

2. **Sistema de Auditoria Completo**:
   - Rastreabilidade de todas as alterações
   - Logs imutáveis para compliance

3. **Dashboard de Conformidade ANS**:
   - Monitoramento de prazos (10 dias)
   - Alertas automáticos de vencimento

---

## APÊNDICE A: GLOSSÁRIO

| Termo | Definição |
|-------|-----------|
| **Glosa** | Negação total ou parcial de pagamento por operadora |
| **Denial Code** | Código TISS (01-99) que identifica motivo da glosa |
| **Provisão** | Reconhecimento contábil de passivo potencial |
| **TISS** | Padrão de Troca de Informações de Saúde Suplementar |
| **TASY** | Sistema ERP hospitalar (HIS) |
| **Appeal** | Processo formal de recurso/contestação de glosa |
| **Tolerance** | Margem aceitável para discrepâncias (1% padrão) |
| **Resubmission** | Reenvio de conta corrigida à operadora |

---

**Documento Completo de Análise de Glosas**
Data de Criação: 2026-01-24
Próxima Revisão: 2026-04-24
Criticidade: ALTA
