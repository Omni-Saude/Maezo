# Regras de Negócio: Identificação e Análise de Glosas

**Domínio**: Gestão de Glosas (Negativas de Pagamento)
**Subsistemas**: Identificação, Análise, Provisionamento Financeiro
**Compliance**: TISS ANS, CPC (Normas Contábeis Brasileiras)
**Data de Extração**: 2026-01-11

---

## Índice
1. [Regras de Identificação de Glosa](#regras-de-identificação-de-glosa)
2. [Regras de Análise de Glosa](#regras-de-análise-de-glosa)
3. [Regras de Provisionamento Financeiro](#regras-de-provisionamento-financeiro)
4. [Integração TISS/ANS](#integração-tissans)
5. [Mapeamento de Processos Camunda](#mapeamento-de-processos-camunda)

---

## Regras de Identificação de Glosa

### RN-GLOSA-IDENTIFY-001: Identificação de Glosa por Comparação de Valores
**Arquivo**: `IdentifyGlosaDelegate.java` (linhas 77-88)
**Tipo**: CÁLCULO + CONDICIONAL

**Descrição**: O sistema identifica a ocorrência de glosa comparando o valor recebido do pagador com o valor esperado da cobrança, aplicando tolerância para evitar falsos positivos.

**Lógica**:
```java
glosaAmount = expectedAmount - paymentReceived
tolerance = expectedAmount × 0.01 (1%)
isWithinTolerance = |glosaAmount| ≤ tolerance
glosaIdentified = !isWithinTolerance AND glosaAmount > 0
```

**Pré-condições**:
- `paymentReceived` ≥ 0 (não pode ser negativo)
- `expectedAmount` > 0 (deve ser positivo)
- `claimId` não vazio

**Pós-condições**:
- `glosaIdentified` (Boolean) definida
- `glosaAmount` (BigDecimal) calculada
- `glosaType` (String) classificada

**Parâmetros**:
- Entrada: `claimId`, `paymentReceived`, `expectedAmount`
- Saída: `glosaIdentified`, `glosaAmount`, `glosaType`

**Compliance TISS**: Utiliza tabela de motivos de glosa da ANS

---

### RN-GLOSA-IDENTIFY-002: Classificação de Tipo de Glosa
**Arquivo**: `IdentifyGlosaDelegate.java` (linhas 174-205)
**Tipo**: CONDICIONAL + ROUTING

**Descrição**: Classifica o tipo de glosa baseado na porcentagem de pagamento recebido em relação ao esperado.

**Regras de Classificação**:
1. **NO_GLOSA**: Diferença dentro da tolerância (±1%)
2. **FULL_DENIAL**: `paymentReceived` = 0
3. **OVERPAYMENT**: `glosaAmount` < 0 (recebido > esperado)
4. **PARTIAL_DENIAL**: `paymentReceived` < 50% do `expectedAmount`
5. **UNDERPAYMENT**: `paymentReceived` ≥ 50% do `expectedAmount`

**Cálculo**:
```java
paymentPercentage = (paymentReceived / expectedAmount) × 100
if (paymentPercentage < 50%) → PARTIAL_DENIAL
else → UNDERPAYMENT
```

**Domínio**: Gestão de Glosas
**Impacto**: Define estratégia de recurso e prioridade

---

### RN-GLOSA-IDENTIFY-003: Validação de Valores Monetários
**Arquivo**: `IdentifyGlosaDelegate.java` (linhas 112-140, 149-163)
**Tipo**: VALIDAÇÃO + TRANSFORMAÇÃO

**Descrição**: Valida e converte valores monetários de múltiplos tipos para BigDecimal, garantindo precisão financeira.

**Tipos Suportados**:
- BigDecimal (direto)
- Double → `BigDecimal.valueOf()`
- Integer → `BigDecimal.valueOf()`
- Long → `BigDecimal.valueOf()`
- String → `new BigDecimal()` com tratamento de exceção

**Validações**:
1. Valor não nulo
2. `paymentReceived` ≥ 0
3. `expectedAmount` > 0

**Exceções**:
- `INVALID_AMOUNT`: Tipo não suportado ou parsing falhou
- `INVALID_CLAIM_DATA`: Dados obrigatórios ausentes

---

## Regras de Análise de Glosa

### RN-GLOSA-ANALYZE-001: Determinação de Estratégia de Recurso - Negação Total
**Arquivo**: `AnalyzeGlosaDelegate.java` (linhas 194-214)
**Tipo**: CONDICIONAL + ROUTING

**Descrição**: Determina a estratégia de recurso para glosas do tipo FULL_DENIAL baseada no motivo da negação.

**Estratégias por Motivo**:
| Motivo (keywords) | Estratégia |
|-------------------|-----------|
| AUTHORIZATION, PRE-AUTH | AUTHORIZATION_APPEAL |
| ELIGIBILITY, COVERAGE | ELIGIBILITY_VERIFICATION_APPEAL |
| CODING, PROCEDURE | CODING_REVIEW_APPEAL |
| MEDICAL NECESSITY | MEDICAL_NECESSITY_APPEAL |
| TIMELY, DEADLINE | TIMELY_FILING_APPEAL |
| Padrão (null ou outros) | COMPREHENSIVE_APPEAL |

**Parâmetros**:
- Entrada: `glosaReason` (String, opcional)
- Saída: `appealStrategy` (String)

**Domínio**: Gestão de Recursos de Glosa

---

### RN-GLOSA-ANALYZE-002: Determinação de Estratégia de Recurso - Negação Parcial
**Arquivo**: `AnalyzeGlosaDelegate.java` (linhas 223-244)
**Tipo**: CONDICIONAL + CÁLCULO

**Descrição**: Determina a estratégia de recurso para glosas do tipo PARTIAL_DENIAL, considerando valor e motivo.

**Lógica**:
```java
if (glosaAmount ≥ R$ 5.000,00) → COMPREHENSIVE_APPEAL
else if (reason.contains("DUPLICATE")) → DUPLICATE_CLAIM_RESOLUTION
else if (reason.contains("BUNDLING") OR "UNBUNDLING") → CODING_REVIEW_APPEAL
else if (reason.contains("MODIFIER")) → MODIFIER_CORRECTION_APPEAL
else → STANDARD_APPEAL
```

**Threshold**: `HIGH_PRIORITY_THRESHOLD = R$ 5.000,00`

---

### RN-GLOSA-ANALYZE-003: Determinação de Prioridade
**Arquivo**: `AnalyzeGlosaDelegate.java` (linhas 253-267)
**Tipo**: CONDICIONAL + CÁLCULO

**Descrição**: Atribui nível de prioridade baseado no tipo de glosa e valor negado.

**Regras**:
1. **FULL_DENIAL**:
   - Se `glosaAmount` ≥ R$ 1.000,00 → HIGH
   - Senão → MEDIUM
2. **Outros tipos**:
   - Se `glosaAmount` ≥ R$ 5.000,00 → HIGH
   - Se `glosaAmount` ≥ R$ 1.000,00 → MEDIUM
   - Senão → LOW

**Thresholds**:
- `HIGH_PRIORITY_THRESHOLD = R$ 5.000,00`
- `MEDIUM_PRIORITY_THRESHOLD = R$ 1.000,00`

**Pós-condição**: `priority` ∈ {HIGH, MEDIUM, LOW}

---

### RN-GLOSA-ANALYZE-004: Atribuição de Responsável
**Arquivo**: `AnalyzeGlosaDelegate.java` (linhas 277-317)
**Tipo**: ROUTING + CONDICIONAL

**Descrição**: Atribui equipe ou pessoa responsável pelo recurso baseado no valor e estratégia.

**Regras de Atribuição**:
1. **Por Valor**: Se `glosaAmount` ≥ R$ 5.000,00 → SENIOR_APPEALS_TEAM
2. **Por Estratégia**:
   - AUTHORIZATION_APPEAL → AUTHORIZATION_TEAM
   - ELIGIBILITY_VERIFICATION_APPEAL → ELIGIBILITY_TEAM
   - CODING_REVIEW_APPEAL, MODIFIER_CORRECTION_APPEAL → CODING_TEAM
   - MEDICAL_NECESSITY_APPEAL → CLINICAL_APPEALS_TEAM
   - TIMELY_FILING_APPEAL → COMPLIANCE_TEAM
   - QUICK_REVIEW_AND_RESUBMIT → BILLING_TEAM
   - COMPREHENSIVE_APPEAL, STANDARD_APPEAL → GENERAL_APPEALS_TEAM
   - REFUND_PROCESSING → ACCOUNTING_TEAM
   - NO_ACTION_REQUIRED → NONE

**Domínio**: Gestão de Recursos, Alocação de Tarefas

---

### RN-GLOSA-ANALYZE-005: Integração DMN para Classificação de Glosas
**Arquivo**: `AnalyzeGlosaDelegate.java` (linhas 327-386)
**Tipo**: INTEGRAÇÃO + CONDICIONAL

**Descrição**: Integra com tabela de decisão DMN "glosa-classification.dmn" para classificação avançada de glosas.

**Variáveis DMN**:
- Entrada: `glosaType`, `glosaReason`, `glosaAmount`, `payerType`, `serviceType`
- Saída: `appealStrategy`, `priority`, `assignedTo`

**Comportamento**:
- Se DMN disponível: sobrescreve decisões programáticas
- Se DMN indisponível: usa lógica programática como fallback
- Exceções: capturadas e logadas, processo continua

**Status Atual**: Implementação preparada, aguardando deployment do arquivo DMN

---

## Regras de Análise com TISS/ANS

### RN-GLOSA-ANALYSIS-001: Mapeamento de Códigos TISS de Motivos de Glosa
**Arquivo**: `GlosaAnalysisService.java` (linhas 30-43)
**Tipo**: INTEGRAÇÃO + ROUTING

**Descrição**: Mapeia códigos padronizados TISS ANS para motivos de glosa.

**Tabela de Motivos TISS**:
| Código | Descrição |
|--------|-----------|
| 01 | Cobrança em duplicidade |
| 02 | Serviço não coberto pelo contrato |
| 03 | Serviço não autorizado |
| 04 | Procedimento não realizado |
| 05 | Valor acima do contratado |
| 06 | Falta de documentação |
| 07 | Prazo de cobrança expirado |
| 08 | Código de procedimento incorreto |
| 09 | CID incompatível com procedimento |
| 10 | Carência não cumprida |
| 11 | Beneficiário não identificado |
| 12 | Internação não autorizada |

**Compliance**: TISS ANS - Tabela de Motivos de Glosa

---

### RN-GLOSA-ANALYSIS-002: Identificação de Padrão de Negação
**Arquivo**: `GlosaAnalysisService.java` (linhas 128-179)
**Tipo**: CONDICIONAL + ROUTING

**Descrição**: Identifica padrão de negação baseado no código TISS, incluindo categoria, complexidade e tempo típico de resolução.

**Padrões por Código**:

| Código | Categoria | Complexidade | Dias Resolução | Requer Doc |
|--------|-----------|--------------|----------------|------------|
| 01 | ADMINISTRATIVE | LOW | 5 | Não |
| 02, 03 | CONTRACTUAL | HIGH | 30 | Sim |
| 04, 08 | BILLING_ERROR | MEDIUM | 10 | Sim |
| 06 | DOCUMENTATION | MEDIUM | 15 | Sim |
| 09 | CLINICAL | HIGH | 20 | Sim |
| Outros | OTHER | MEDIUM | 15 | Sim |

**Saída**: Objeto `DenialPattern` com propriedades estruturadas

---

### RN-GLOSA-ANALYSIS-003: Cálculo de Probabilidade de Recuperação
**Arquivo**: `GlosaAnalysisService.java` (linhas 184-219)
**Tipo**: CÁLCULO + CONDICIONAL

**Descrição**: Calcula probabilidade de recuperação da glosa baseada em dados históricos e características do caso.

**Probabilidades Base por Código**:
```java
01 (Duplicidade) → 95%
04, 08 (Erros faturamento) → 85%
06 (Falta documentação) → 70%
09 (CID incompatível) → 55%
03 (Não autorizado) → 45%
02 (Não coberto) → 25%
07 (Prazo expirado) → 10%
Padrão → 50%
```

**Ajustes**:
1. **Documentação completa**: `+15%` (se requerida e disponível)
2. **Documentação faltante**: `-20%` (se requerida e ausente)
3. **Pagador público**: `-10%`
4. **Idade > 90 dias**: `-15%`

**Fórmula Final**:
```
recoveryProbability = baseProbability + adjustments
resultado ∈ [0.0, 1.0] (limitado)
```

---

### RN-GLOSA-ANALYSIS-004: Determinação de Ações Recomendadas
**Arquivo**: `GlosaAnalysisService.java` (linhas 224-266)
**Tipo**: CONDICIONAL + ROUTING

**Descrição**: Determina conjunto de ações recomendadas baseado na probabilidade de recuperação e valor.

**Ações por Probabilidade de Recuperação**:

**Alta Probabilidade (≥75%)**:
1. ANALYZE - Analisar motivo
2. SEARCH_EVIDENCE - Buscar evidência (se requer doc)
3. APPLY_CORRECTIONS - Aplicar correções e reenviar imediatamente
4. CREATE_PROVISION - Criar provisão mínima

**Média Probabilidade (≥40%)**:
1. ANALYZE - Analisar motivo
2. SEARCH_EVIDENCE - Buscar evidência adicional
3. APPLY_CORRECTIONS - Aplicar correções com doc adicional
4. CREATE_PROVISION - Criar provisão moderada
5. ESCALATE - Escalar se valor > R$ 50.000,00

**Baixa Probabilidade (<40%)**:
1. ANALYZE - Analisar motivo
2. CREATE_PROVISION - Criar provisão total
3. LEGAL_REFERRAL - Referir ao jurídico se > R$ 100.000,00
4. ESCALATE - Escalar à gestão se > R$ 50.000,00
5. REGISTER_LOSS - Registrar perda (se outros falharem)

**Thresholds**:
- `HIGH_VALUE_THRESHOLD = R$ 50.000,00`
- `LEGAL_THRESHOLD = R$ 100.000,00`

---

## Regras de Provisionamento Financeiro

### RN-GLOSA-PROVISION-001: Cálculo de Valor de Provisão
**Arquivo**: `FinancialProvisionService.java` (linhas 282-291)
**Tipo**: CÁLCULO

**Descrição**: Calcula o valor da provisão financeira baseado no valor negado e probabilidade de recuperação, seguindo normas CPC.

**Fórmula**:
```java
provisionAmount = deniedAmount × (1 - recoveryProbability)
```

**Exemplo**:
- Valor negado: R$ 10.000,00
- Probabilidade recuperação: 70% (0.70)
- Provisão: R$ 10.000,00 × (1 - 0.70) = R$ 3.000,00

**Precisão**: Arredondamento HALF_UP com 2 casas decimais

**Compliance**: CPC - Normas Contábeis Brasileiras

---

### RN-GLOSA-PROVISION-002: Determinação de Tipo de Provisão
**Arquivo**: `FinancialProvisionService.java` (linhas 296-306)
**Tipo**: CONDICIONAL

**Descrição**: Classifica o tipo de provisão baseado na probabilidade de recuperação.

**Classificação**:
```java
if (recoveryProbability ≥ 60%) → MINIMAL
else if (recoveryProbability ≥ 20%) → PARTIAL
else → FULL
```

**Thresholds**:
- `PARTIAL_PROVISION_THRESHOLD = 0.60 (60%)`
- `FULL_PROVISION_THRESHOLD = 0.20 (20%)`

**Tipos**:
- **MINIMAL**: <40% do valor negado
- **PARTIAL**: 40-80% do valor negado
- **FULL**: >80% do valor negado

---

### RN-GLOSA-PROVISION-003: Lançamentos Contábeis de Criação de Provisão
**Arquivo**: `FinancialProvisionService.java` (linhas 311-337)
**Tipo**: INTEGRAÇÃO + CONTABILIDADE

**Descrição**: Gera lançamentos contábeis duplos para criação de provisão de glosa.

**Lançamentos (Partidas Dobradas)**:
1. **Débito**: 3.1.2.01.001 - Despesa com Provisão
2. **Crédito**: 2.1.3.01.001 - Provisão para Glosas

**Plano de Contas**:
- `GL_PROVISION_EXPENSE = 3.1.2.01.001`
- `GL_PROVISION_LIABILITY = 2.1.3.01.001`
- `GL_RECOVERY_REVENUE = 3.2.1.01.005`
- `GL_WRITE_OFF = 3.1.2.01.002`

**Integração**: TASY ERP

---

### RN-GLOSA-PROVISION-004: Atualização de Provisão por Mudança de Probabilidade
**Arquivo**: `FinancialProvisionService.java` (linhas 109-174)
**Tipo**: CÁLCULO + CONDICIONAL

**Descrição**: Atualiza provisão existente quando probabilidade de recuperação muda significativamente.

**Lógica**:
```java
adjustmentAmount = newProvision - oldProvision
changePercentage = |adjustmentAmount| / oldProvision × 100

if (changePercentage < 5%) → No update
else → Update provision
```

**Threshold de Atualização**: 5% de mudança

**Lançamentos de Ajuste**:
- Se aumento: Débito Despesa / Crédito Provisão
- Se redução: Crédito Despesa / Débito Provisão

---

### RN-GLOSA-PROVISION-005: Reversão de Provisão por Recuperação
**Arquivo**: `FinancialProvisionService.java` (linhas 179-232)
**Tipo**: CÁLCULO + INTEGRAÇÃO

**Descrição**: Reverte provisão (parcial ou total) quando valor é recuperado.

**Validação**: `recoveredAmount` pode ser > `provisionAmount` (gera warning)

**Lançamentos Contábeis**:
1. **Débito**: 2.1.3.01.001 - Provisão para Glosas (reversão)
2. **Crédito**: 3.2.1.01.005 - Receita com Recuperação de Glosas

**Cálculo**:
```java
remainingProvision = provisionAmount - recoveredAmount
recoveryPercentage = (recoveredAmount / provisionAmount) × 100
```

---

### RN-GLOSA-PROVISION-006: Baixa de Provisão (Write-off)
**Arquivo**: `FinancialProvisionService.java` (linhas 237-277)
**Tipo**: INTEGRAÇÃO + CONTABILIDADE

**Descrição**: Realiza baixa contábil da provisão quando valor é considerado irrecuperável.

**Lançamentos Contábeis**:
1. **Débito**: 2.1.3.01.001 - Provisão para Glosas (reversão)
2. **Crédito**: 3.1.2.01.002 - Perdas com Glosas (confirma perda)

**Motivos Típicos**:
- Esgotamento de recursos administrativos
- Decisão judicial desfavorável
- Valor irrecuperável (< R$ 100,00)
- Prazo de prescrição

---

## Mapeamento de Processos Camunda

### Variáveis de Processo

**Input Variables**:
- `claimId` (String) - Identificador da guia
- `paymentReceived` (BigDecimal) - Valor recebido
- `expectedAmount` (BigDecimal) - Valor esperado
- `glosaType` (String) - Tipo de glosa
- `glosaReason` (String) - Motivo da glosa
- `glosaAmount` (BigDecimal) - Valor da glosa
- `denialCode` (String) - Código TISS

**Output Variables**:
- `glosaIdentified` (Boolean) - Glosa identificada
- `appealStrategy` (String) - Estratégia de recurso
- `priority` (String) - Prioridade (HIGH/MEDIUM/LOW)
- `assignedTo` (String) - Equipe responsável
- `provisionId` (String) - ID da provisão criada
- `provisionAmount` (BigDecimal) - Valor provisionado
- `recoveryProbability` (Double) - Probabilidade de recuperação

### BPMN Errors

| Error Code | Descrição | Fonte |
|------------|-----------|-------|
| INVALID_GLOSA_DATA | Dados de glosa inválidos | AnalyzeGlosaDelegate |
| INVALID_CLAIM_DATA | Dados de guia inválidos | IdentifyGlosaDelegate |
| INVALID_AMOUNT | Valor monetário inválido | Ambos |
| ANALYSIS_FAILED | Falha na análise | AnalyzeGlosaDelegate |

### Delegates Bean Names

- `analyzeGlosa` → AnalyzeGlosaDelegate
- `identifyGlosa` → IdentifyGlosaDelegate

---

## Resumo de Integração

### Sistemas Externos
1. **TASY ERP**: Gestão de guias, provisões e contabilidade
2. **TISS ANS**: Códigos padronizados de motivos de glosa
3. **Camunda DMN**: Tabela de decisão glosa-classification.dmn

### Domínios de Negócio
- Gestão de Glosas
- Gestão de Recursos
- Provisionamento Financeiro
- Contabilidade (CPC)
- Compliance ANS/TISS

### Métricas de Negócio
- Taxa de recuperação de glosas
- Tempo médio de resolução por categoria
- Provisão total vs. perdas efetivas
- Distribuição por motivo TISS

---

**Total de Regras Extraídas**: 19 regras principais
**Arquivos Fonte**: 4 arquivos Java
**Linhas de Código Analisadas**: ~1.600 linhas
**Compliance**: TISS ANS, CPC (Contabilidade)

---

## X. Conformidade Regulatória

### Normativas ANS
- **RN 424/2017:** Diretrizes para recursos de glosas (Arts. 8-15)
- **RN 443/2019:** Padrão TISS para motivos de glosa (Anexo III)
- **RN 465/2021:** Atualização de tabelas de glosas
- **RN 500/2022:** Prazos para análise e recurso de glosas

### Padrão TISS (Versão 4.02.02)
- **Componente:** Demonstrativo de Retorno de Guia
- **Campo 55:** Código do motivo da glosa (Tabela 36 - TISS)
- **Campo 56:** Valor da glosa
- **Campo 57:** Observação da glosa
- **Glosa Codes:**
  - 01-09: Erros administrativos
  - 10-19: Erros técnicos
  - 20-29: Falta de documentação
  - 30-39: Procedimentos não cobertos

### CPC 00 (Estrutura Conceitual)
- **Item 4.59:** Reconhecimento de provisão para perdas
- **Item 6.54:** Probabilidade de perda (provável, possível, remota)
- **Item 7.16:** Divulgação de contingências

### CPC 25 (Provisões, Passivos Contingentes e Ativos Contingentes)
- **Item 14:** Obrigação presente resultante de evento passado
- **Item 23:** Melhor estimativa de desembolso futuro
- **Item 85:** Divulgação de incertezas sobre valor e prazo

### LGPD (Lei 13.709/2018)
- **Art. 6º, III:** Necessidade de tratamento de dados de glosa
- **Art. 11, II, 'e':** Proteção da vida - análise de glosas médicas
- **Art. 48:** Comunicação de incidente de segurança (vazamento de glosas)

### SOX (Sarbanes-Oxley)
- **Section 302:** Controles internos para provisões de glosa
- **Section 404:** Auditoria de processos de glosa
- **Section 409:** Divulgação tempestiva de mudanças em provisões

### Lei 13.097/2015 (Participação de Capital Estrangeiro em Saúde)
- **Art. 142:** Obrigações contratuais entre prestador e operadora
- **Art. 143:** Transparência em glosas e recursos

---

## XI. Notas de Migração

### Complexidade de Migração
**Rating:** 🔴 ALTA (8/10)

**Justificativa:**
- Múltiplos arquivos Java interconectados (4 classes)
- Integração com contabilidade (CPC 00/25)
- Tabela TISS de motivos (36 códigos)
- Fluxo de recursos de glosa complexo

### Mudanças Incompatíveis (Breaking Changes)
1. **Tabela de Motivos TISS:** Migração de códigos internos para Tabela 36 TISS
2. **Provisão CPC 25:** Novas regras de cálculo de provisão
3. **Recurso de Glosa:** Novo fluxo de workflow para contestação
4. **Categorização:** Substituição de categorias internas por TISS

### Migração para DMN
**Candidato:** ✅ SIM (ALTA PRIORIDADE)

```yaml
dmn_migration:
  decision_tables:
    - decision_id: "glosa-classification"
      decision_name: "Classificação de Glosa"
      inputs:
        - glosaCode: String (TISS Table 36)
        - glosaAmount: BigDecimal
        - documentationMissing: Boolean
      outputs:
        - glosaCategory: String (ADMINISTRATIVE/TECHNICAL/DOCUMENTATION/COVERAGE)
        - severity: String (LOW/MEDIUM/HIGH/CRITICAL)
        - requiresManualReview: Boolean
      rules:
        - "Códigos 01-09 = ADMINISTRATIVE"
        - "Códigos 10-19 = TECHNICAL"
        - "Códigos 20-29 = DOCUMENTATION"
        - "Códigos 30-39 = COVERAGE"

    - decision_id: "financial-provision"
      decision_name: "Cálculo de Provisão Financeira (CPC 25)"
      inputs:
        - glosaCategory: String
        - historicalRecoveryRate: Float
        - appealDeadline: Integer (dias)
      outputs:
        - provisionPercentage: Float (0.0-1.0)
        - provisionType: String (PROVABLE/POSSIBLE/REMOTE)
        - accountingEntry: String (CPC 25)
      rules:
        - "TECHNICAL + recoveryRate > 60% = 40% provisão (POSSIBLE)"
        - "COVERAGE + recoveryRate < 30% = 100% provisão (PROVABLE)"
        - "DOCUMENTATION + appealDeadline > 0 = 50% provisão"

    - decision_id: "appeal-strategy"
      decision_name: "Estratégia de Recurso"
      inputs:
        - glosaAmount: BigDecimal
        - glosaCategory: String
        - historicalWinRate: Float
      outputs:
        - shouldAppeal: Boolean
        - appealPriority: String (LOW/MEDIUM/HIGH)
        - estimatedCost: BigDecimal
      rules:
        - "glosaAmount > 10000 AND winRate > 50% = HIGH priority"
        - "DOCUMENTATION + winRate > 70% = Should appeal"
        - "appealCost > glosaAmount * 0.8 = Do not appeal"
```

### Fases de Implementação
**Fase 1 - Core Glosa Detection (Sprint 8):**
- Identificação e categorização de glosas
- Integração com Tabela 36 TISS
- Logging e rastreabilidade

**Fase 2 - Financial Provision (Sprint 9):**
- Cálculo de provisão CPC 25
- Integração com contabilidade
- Lançamentos contábeis automáticos

**Fase 3 - Appeal Workflow (Sprint 10):**
- Fluxo de recurso de glosa
- Análise de viabilidade de recurso
- Dashboard de taxa de recuperação

**Fase 4 - DMN Integration (Sprint 11):**
- Migração de regras para DMN
- Decision tables para classificação e provisão
- Versionamento de regras

### Dependências Críticas
```yaml
dependencies:
  tiss_tables:
    - tabela_36_motivos_glosa  # 36 códigos padronizados
    - tabela_22_terminologia   # Procedimentos

  accounting_standards:
    - cpc_00_framework         # Estrutura conceitual
    - cpc_25_provisions        # Provisões e contingências

  databases:
    - glosa_identificacao      # Detecção de glosas
    - glosa_recursos           # Recursos contestados
    - provisao_financeira      # Provisões CPC 25
    - historico_recuperacao    # Taxas de sucesso

  external_services:
    - ANS Demonstrativo Retorno API
    - Contabilidade ERP (lançamentos)
    - Insurance Claims System
```

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Contexto:** Revenue Cycle Management - Glosa & Appeals

**Subdomínio:** Glosa Identification & Financial Provision (Core Domain)

**Responsabilidades:**
- Identificação e classificação de glosas (TISS Table 36)
- Cálculo de provisão financeira (CPC 25)
- Gestão de recursos de glosa
- Contabilização de perdas prováveis/possíveis

### Aggregates e Entidades

```yaml
aggregate: GlosaManagement
  root_entity: Glosa
    properties:
      - glosaId: UUID
      - claimId: UUID
      - glosaCode: String (TISS Table 36)
      - glosaAmount: BigDecimal
      - glosaDate: LocalDate
      - category: GlosaCategory (ADMINISTRATIVE/TECHNICAL/DOCUMENTATION/COVERAGE)
      - status: GlosaStatus (IDENTIFIED/PROVISIONED/APPEALED/RECOVERED/LOST)

  value_objects:
    - GlosaDetails:
        - motivo: String (Descrição TISS)
        - procedureCode: String
        - procedureDescription: String
        - serviceDate: LocalDate
        - observation: String

    - FinancialProvision:
        - provisionPercentage: Float (0.0-1.0)
        - provisionType: ProvisionType (PROVABLE/POSSIBLE/REMOTE)
        - accountingEntry: String (CPC 25)
        - calculatedAt: Instant

  entities:
    - GlosaRecurso:
        - recursoId: UUID
        - glosaId: UUID (FK)
        - appealDate: LocalDate
        - appealJustification: String
        - appealStatus: AppealStatus (PENDING/APPROVED/DENIED)
        - recoveredAmount: BigDecimal?

    - GlosaHistory:
        - historyId: UUID
        - glosaId: UUID (FK)
        - previousStatus: GlosaStatus
        - newStatus: GlosaStatus
        - changedBy: String
        - changedAt: Instant
```

### Domain Events

```json
{
  "domain_events": [
    {
      "event": "GlosaIdentified",
      "triggers": ["Nova glosa detectada no claim"],
      "payload": {
        "glosaId": "uuid",
        "claimId": "uuid",
        "glosaCode": "string",
        "glosaAmount": "bigdecimal",
        "category": "enum"
      },
      "subscribers": [
        "FinancialProvisionService",
        "AppealWorkflowService",
        "AuditService"
      ]
    },
    {
      "event": "FinancialProvisionCalculated",
      "triggers": ["Provisão financeira calculada (CPC 25)"],
      "payload": {
        "glosaId": "uuid",
        "provisionAmount": "bigdecimal",
        "provisionPercentage": "float",
        "provisionType": "enum",
        "accountingEntry": "string"
      },
      "subscribers": [
        "AccountingERP",
        "FinancialDashboard",
        "CFOReport"
      ]
    },
    {
      "event": "AppealInitiated",
      "triggers": ["Recurso de glosa iniciado"],
      "payload": {
        "recursoId": "uuid",
        "glosaId": "uuid",
        "appealDate": "date",
        "estimatedRecovery": "bigdecimal"
      },
      "subscribers": [
        "AppealManagementQueue",
        "InsuranceCommunication",
        "LegalCompliance"
      ]
    },
    {
      "event": "GlosaRecovered",
      "triggers": ["Recurso de glosa aprovado"],
      "payload": {
        "glosaId": "uuid",
        "recoveredAmount": "bigdecimal",
        "approvalDate": "date"
      },
      "subscribers": [
        "AccountingReversal",
        "RevenueCycleMetrics",
        "ProvisionAdjustment"
      ]
    },
    {
      "event": "GlosaLost",
      "triggers": ["Recurso negado ou prazo expirado"],
      "payload": {
        "glosaId": "uuid",
        "lostAmount": "bigdecimal",
        "lossReason": "string"
      },
      "subscribers": [
        "AccountingWriteOff",
        "QualityImprovement",
        "CodingEducation"
      ]
    }
  ]
}
```

### Invariantes do Domínio
1. **Provisão CPC 25:** Provisão obrigatória para glosas identificadas
2. **Prazo de Recurso:** 30 dias após identificação da glosa
3. **Categorização TISS:** Glosa deve ter código válido da Tabela 36
4. **Imutabilidade:** Histórico de glosas é append-only (auditoria)

### Viabilidade para Microserviço
**Candidato:** ✅ SIM

**Justificativa:**
- Responsabilidade clara: gestão de glosas e recursos
- Volume alto de transações (escalabilidade importante)
- Estado isolado (glosas, recursos, provisões)
- Comunicação via eventos (GlosaIdentified, FinancialProvisionCalculated)

**Integração:**
```yaml
microservice: glosa-management-service
  api:
    - POST /glosas/identify
    - POST /glosas/{id}/appeal
    - GET /glosas/{id}/provision
    - GET /glosas/metrics/recovery-rate

  events_published:
    - GlosaIdentified
    - FinancialProvisionCalculated
    - AppealInitiated
    - GlosaRecovered
    - GlosaLost

  events_subscribed:
    - ClaimSubmitted (from BillingService)
    - PaymentReceived (from PaymentService)
    - AppealDecision (from InsuranceService)

  dmn_decisions:
    - glosa-classification.dmn
    - financial-provision.dmn
    - appeal-strategy.dmn

  external_integrations:
    - accounting_erp (lançamentos CPC 25)
    - ans_demonstrativo_retorno_api
    - insurance_claims_system
```

---

## XIII. Metadados Técnicos

### Complexidade e Esforço

```yaml
complexity_metrics:
  cyclomatic_complexity: 22  # Alto
  cognitive_complexity: 35   # Muito Alto
  lines_of_code: ~1600 (4 arquivos Java)

  time_estimates:
    implementation: 8 dias
    testing: 4 dias
    dmn_migration: 4 dias
    accounting_integration: 3 dias
    documentation: 2 dias
    total: 21 dias (~4 sprints)
```

### Cobertura de Testes

```yaml
test_coverage_targets:
  unit_tests: 85%
  integration_tests: 80%

  critical_test_scenarios:
    - glosa_identification
    - glosa_categorization_tiss_table36
    - financial_provision_cpc25
    - provision_type_calculation
    - appeal_initiation
    - appeal_approval_recovery
    - appeal_denial_writeoff
    - historical_recovery_rate
    - accounting_entry_generation
    - dmn_decision_integration
```

### Performance e SLA

```yaml
performance_requirements:
  glosa_identification_latency: <300ms (p95)
  provision_calculation_time: <500ms
  appeal_workflow_initiation: <1000ms

  availability: 99.5%

  resource_limits:
    cpu: 2 cores
    memory: 4 GB
    database_connections: 20
```

### Dependências e Integrações

```yaml
dependencies:
  internal_services:
    - BillingService (claims)
    - PaymentService (received payments)
    - AccountingService (CPC 25 entries)
    - AppealWorkflowService (recurso de glosa)

  external_services:
    - ANS Demonstrativo Retorno API (glosa codes)
    - Insurance Claims System (appeal submission)
    - Accounting ERP (GL posting)

  databases:
    - glosa_identificacao (PostgreSQL)
    - glosa_recursos (PostgreSQL)
    - provisao_financeira (PostgreSQL)
    - historico_recuperacao (TimescaleDB)

  dmn_engines:
    - camunda_decision_engine (classification, provision, appeal strategy)

  message_queues:
    - glosa_events (Kafka)
    - accounting_events (Kafka)
```

### Monitoramento e Observabilidade

```yaml
metrics:
  business:
    - glosa_rate_by_category (ADMINISTRATIVE/TECHNICAL/DOCUMENTATION/COVERAGE)
    - appeal_success_rate
    - average_recovery_time
    - provision_total_vs_actual_loss
    - top_glosa_codes (TISS Table 36)

  technical:
    - glosa_identification_latency_p50_p95_p99
    - provision_calculation_time
    - appeal_workflow_duration
    - dmn_decision_evaluation_time

  accounting:
    - provision_balance (CPC 25)
    - recovered_amount_by_month
    - writeoff_amount_by_category
    - provision_adjustment_frequency

  alerts:
    - glosa_rate > 15% (weekly)
    - appeal_success_rate < 40% (monthly)
    - provision_calculation_error > 0 (immediate)
    - glosa_identification_latency_p95 > 500ms
```

---

**Última Atualização:** 2025-01-12
**Versão do Documento:** 2.0
**Status de Conformidade:** ✅ Completo (X-XIII)
