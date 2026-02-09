# RN-ApplyCorrectionsDelegate

**Camunda Delegate:** `applyCorrectionsDelegate`
**Categoria:** Gestão de Glosas (Negações)
**Arquivo:** `ApplyCorrectionsDelegate.java`

## Descrição

Aplica correções a cobranças negadas e prepara para reenvio. Este delegate implementa estratégias de correção específicas para cada código de glosa TISS, automatizando o processo de recurso e reenvio.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `claimId` | String | Sim | Identificador da cobrança no TASY |
| `denialCode` | String | Sim | Código de glosa TISS |
| `denialCategory` | String | Sim | Categoria da negação |
| `foundDocuments` | List&lt;Map&gt; | Não | Documentos de evidência disponíveis |
| `correctionNotes` | String | Não | Notas adicionais para correção |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `correctionApplied` | Boolean | Se correções foram aplicadas |
| `correctionType` | String | Tipo de correção aplicada |
| `correctionDetails` | Map | Detalhes das correções realizadas |
| `correctedClaimId` | String | Novo ID da cobrança após correção |
| `readyForResubmission` | Boolean | Se cobrança está pronta para reenvio |
| `resubmissionDate` | LocalDateTime | Data/hora de reenvio |
| `attachedDocuments` | List&lt;String&gt; | Documentos anexados à cobrança corrigida |
| `correctionNotes` | String | Notas sobre as correções realizadas |

## Regras de Negócio

### Estratégias de Correção por Código de Glosa

#### 1. Código 01 - Duplicidade
- **Ação**: Verifica se cobrança é duplicada através de busca de cobranças similares
- **Se não há duplicatas**: Fornece evidência de unicidade e reenvia
- **Se há duplicatas**: Cancela cobrança duplicada e mantém original

#### 2. Códigos 04 e 08 - Procedimento Não Realizado / Código Incorreto
- **Ação**: Valida código de procedimento através da tabela TUSS
- **Validação**: Verifica código através do cliente TISS
- **Se inválido**: Marca para revisão manual
- **Se válido**: Reenvia com confirmação de validação

#### 3. Código 05 - Valor Acima do Contratado
- **Ação**: Ajusta valor ao preço contratado
- **Busca**: Consulta tabela de preços contratuais no TASY
- **Comparação**: Compara valor cobrado vs. contratado
- **Ajuste**: Atualiza valor da cobrança se necessário

#### 4. Código 06 - Falta de Documentação
- **Ação**: Anexa documentos de suporte encontrados
- **Validação**: Verifica disponibilidade de documentos
- **Anexação**: Vincula documentos à cobrança via TASY
- **Se sem documentos**: Marca para intervenção manual

#### 5. Código 09 - CID Incompatível
- **Ação**: Corrige diagnóstico incompatível
- **Validação**: Verifica compatibilidade CID-10 vs. procedimento
- **Correção**: Busca diagnóstico compatível no TASY
- **Se sem diagnóstico compatível**: Solicita revisão médica

#### 6. Código 03 - Não Autorizado
- **Ação**: Atualiza número de autorização
- **Busca**: Procura guia de autorização em documentos
- **Atualização**: Adiciona número de autorização à cobrança
- **Se sem autorização**: Solicita autorização da operadora

#### 7. Código 02 - Não Coberto
- **Ação**: Verifica cobertura contratual
- **Validação**: Consulta termos do contrato no TASY
- **Se coberto**: Fornece evidência contratual
- **Se não coberto**: Marca para write-off

#### 8. Outros Códigos
- **Ação**: Marca para revisão manual com detalhes do código de negação

### Critérios de Pronto para Reenvio

Uma cobrança está pronta para reenvio quando:
1. ✅ Correção foi aplicada com sucesso (`correctionApplied = true`)
2. ✅ Todos os dados necessários estão completos
3. ✅ Validações específicas foram aprovadas
4. ✅ Documentos necessários foram anexados (quando aplicável)

## Integrações

### TASY ERP
- `getClaimDetails(claimId)` - Recupera detalhes da cobrança
- `searchSimilarClaims(claimId)` - Busca cobranças similares (duplicatas)
- `resubmitClaim(claimId)` - Reenvia cobrança
- `resubmitClaimWithEvidence(claimId, evidence)` - Reenvia com evidência
- `voidDuplicateClaim(claimId)` - Cancela cobrança duplicada
- `getContractedPrice(payerId, procedureCode)` - Busca preço contratado
- `updateClaimAmount(claimId, amount)` - Atualiza valor da cobrança
- `attachDocumentToClaim(claimId, documentId, type)` - Anexa documento
- `updateClaimDiagnosis(claimId, diagnosis)` - Atualiza diagnóstico
- `updateClaimAuthorization(claimId, authNumber)` - Atualiza autorização
- `verifyContractCoverage(payerId, procedureCode)` - Verifica cobertura

### TISS ANS
- `validateProcedureCode(code)` - Valida código de procedimento
- `validateDiagnosisCompatibility(cid, procedure)` - Valida compatibilidade CID vs. procedimento

## Exceções e Erros

Não lança exceções BPMN - define `correctionApplied = false` e `readyForResubmission = false` em caso de falhas, permitindo que o processo decida próximo passo.

## Tipos de Correção

| Tipo | Descrição |
|------|-----------|
| `DUPLICATE_RESOLUTION` | Resolução de duplicatas |
| `BILLING_CODE_CORRECTION` | Correção de código de faturamento |
| `PRICE_ADJUSTMENT` | Ajuste de preço |
| `DOCUMENTATION_ATTACHMENT` | Anexação de documentação |
| `DIAGNOSIS_CORRECTION` | Correção de diagnóstico |
| `AUTHORIZATION_UPDATE` | Atualização de autorização |
| `CONTRACTUAL_VERIFICATION` | Verificação contratual |
| `GENERIC_CORRECTION` | Correção genérica (requer revisão manual) |

## Estrutura de Dados

### CorrectionResult (Classe Interna)

```java
{
  "claimId": "CLM-12345",
  "correctedClaimId": "CLM-12345-R01",
  "correctionType": "PRICE_ADJUSTMENT",
  "success": true,
  "readyForResubmission": true,
  "resubmissionDate": "2025-01-12T10:30:00",
  "details": {
    "billedAmount": 1500.00,
    "contractedPrice": 1200.00,
    "adjustedAmount": 1200.00,
    "adjustment": 300.00
  },
  "attachedDocuments": [],
  "notes": "Amount adjusted to contracted price: 1200.00"
}
```

## Exemplo de Fluxo

```
1. Receber cobrança negada (claimId, denialCode=05)
2. Buscar detalhes da cobrança no TASY
3. Identificar correção necessária (PRICE_ADJUSTMENT)
4. Buscar preço contratado
5. Comparar valores
6. Atualizar valor na cobrança
7. Reenviar cobrança
8. Retornar correctionApplied=true, readyForResubmission=true
```

## Configurações

### Tolerância de Arredondamento
- Não especificada neste delegate (aplicada em IdentifyGlosaDelegate)

### Timeout
- Padrão: 60 segundos por operação

## Auditoria e Logging

**Nível de Log:** INFO/WARN
**Eventos Auditados:**
- Identificação de correção necessária
- Sucesso/falha de cada tipo de correção
- Cobranças reenviadas
- Correções que requerem intervenção manual

## KPIs e Métricas

- **Taxa de Correção Automática**: Correções aplicadas sem intervenção manual
- **Taxa de Reenvio Bem-Sucedido**: Cobranças corrigidas e reenviadas
- **Tempo Médio de Correção**: Por tipo de correção
- **Necessidade de Revisão Manual**: Por código de glosa

## Considerações Importantes

1. **Automação vs. Manual**: Nem todas as correções podem ser automatizadas - alguns casos requerem revisão manual especializada
2. **Evidências**: Manutenção de evidências detalhadas é crítica para auditoria e compliance
3. **Integridade de Dados**: Todas as correções mantêm histórico e rastreabilidade
4. **Regras Contratuais**: Ajustes devem respeitar termos contratuais específicos com cada operadora

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** Revenue Cycle Team
