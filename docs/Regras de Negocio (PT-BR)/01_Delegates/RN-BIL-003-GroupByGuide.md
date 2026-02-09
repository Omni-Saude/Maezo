# RN-BIL-003: Agrupamento por Guia de Autorização

**ID Técnico**: `GroupByGuideDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Agrupar itens de faturamento de acordo com as guias de autorização correspondentes (TISS), garantindo que cada item seja faturado sob a autorização correta conforme os tipos de guia (Consulta, SADT, Internação, SP/SADT, Honorários).

### 1.2. Contexto de Negócio
No sistema de saúde suplementar brasileiro, todo serviço prestado requer autorização prévia da operadora de saúde. Estas autorizações são documentadas em guias TISS padronizadas pela ANS. Cada tipo de serviço possui um tipo específico de guia:

- **CONSULTA**: Atendimentos ambulatoriais e consultas
- **SADT**: Serviços de Apoio Diagnóstico e Terapêutico
- **INTERNACAO**: Serviços de internação hospitalar
- **SP_SADT**: SP/SADT - Serviços Profissionais em SADT
- **HONORARIOS**: Honorários médicos

Antes de submeter à operadora via TISS, é necessário agrupar os itens de cobrança de acordo com as guias de autorização para:
- Garantir conformidade com autorizações concedidas
- Facilitar rastreamento e auditoria
- Evitar glosas por falta de autorização
- Organizar submissão por tipo de serviço

### 1.3. Benefícios Esperados
- **Conformidade Regulatória**: Submissão correta conforme padrão TISS/ANS
- **Redução de Glosas**: Identificação antecipada de itens não autorizados
- **Rastreabilidade**: Vínculo claro entre cobrança e autorização
- **Eficiência Operacional**: Automação do agrupamento por guia
- **Auditoria**: Facilita validação de conformidade com autorizações

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve recuperar as guias de autorização do atendimento, validar os tipos de guia conforme padrão TISS, atribuir cada item de cobrança à guia correspondente, e identificar itens sem autorização válida.

**Lógica de Execução**:

1. **Recuperação de Guias de Autorização**
   ```
   guias_autorizacao ← RECUPERAR_GUIAS(encounterId)

   Informações por Guia:
     - guideNumber: Número único da guia
     - guideType: Tipo TISS (CONSULTA, SADT, INTERNACAO, etc.)
     - authorizationDate: Data de autorização
     - validUntil: Data de validade
     - authorizedProcedures: Lista de códigos autorizados

   SE guias_autorizacao.tamanho = 0:
     LANÇAR ERRO "NO_AUTHORIZATION_GUIDES"
   ```

2. **Validação de Tipos de Guia**
   ```
   tipos_validos ← {"CONSULTA", "SADT", "INTERNACAO", "SP_SADT", "HONORARIOS"}

   PARA CADA guia EM guias_autorizacao:
     SE guia.guideType NÃO ESTÁ EM tipos_validos:
       LANÇAR ERRO "INVALID_GUIDE_TYPE" COM tipo_invalido

     SE guia.guideNumber É NULO OU VAZIO:
       LANÇAR ERRO "INVALID_GUIDE_TYPE" COM "Número de guia ausente"
   ```

3. **Atribuição de Cobranças às Guias**
   ```
   grupos_faturamento ← NOVO_MAPA_VAZIO

   PARA CADA cobranca EM contractAdjustedCharges:
     codigo_cobranca ← cobranca.chargeCode
     guia_encontrada ← FALSO

     PARA CADA guia EM guias_autorizacao:
       SE codigo_cobranca ESTÁ EM guia.authorizedProcedures:
         grupos_faturamento[guia.guideNumber].ADICIONAR(cobranca)
         guia_encontrada ← VERDADEIRO
         SAIR DO LOOP

     SE NÃO guia_encontrada:
       LOG AVISO "Cobrança não atribuída: " + codigo_cobranca
   ```

4. **Mapeamento de Tipos de Guia**
   ```
   tipos_guias ← NOVO_MAPA_VAZIO

   PARA CADA guia EM guias_autorizacao:
     tipos_guias[guia.guideNumber] ← guia.guideType
   ```

5. **Identificação de Itens Não Autorizados**
   ```
   itens_nao_autorizados ← LISTA_VAZIA
   itens_atribuidos ← UNIÃO_DE_TODOS(grupos_faturamento.valores)

   PARA CADA cobranca EM contractAdjustedCharges:
     SE cobranca NÃO ESTÁ EM itens_atribuidos:
       itens_nao_autorizados.ADICIONAR(cobranca)

   SE itens_nao_autorizados.tamanho > 0:
     LANÇAR ERRO "UNAUTHORIZED_ITEMS" COM quantidade
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-003-V1 | Pelo menos uma guia de autorização deve existir | CRÍTICA | Rejeitar com NO_AUTHORIZATION_GUIDES |
| BIL-003-V2 | Tipo de guia deve ser válido conforme TISS | CRÍTICA | Rejeitar com INVALID_GUIDE_TYPE |
| BIL-003-V3 | Número de guia não pode ser nulo ou vazio | CRÍTICA | Rejeitar com INVALID_GUIDE_TYPE |
| BIL-003-V4 | Todos os itens devem ter autorização | CRÍTICA | Rejeitar com UNAUTHORIZED_ITEMS |
| BIL-003-V5 | Lista de procedimentos autorizados deve existir | AVISO | Log de advertência |
| BIL-003-V6 | Data de validade da guia não pode estar expirada | AVISO | Alertar para renovação |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador de atendimento (encounterId) válido
- Lista de cobranças ajustadas por contrato (contractAdjustedCharges) disponível
- Pelo menos uma guia de autorização registrada no sistema

**Exceções de Negócio**:

1. **Nenhuma Guia de Autorização Encontrada**
   - **Código**: NO_AUTHORIZATION_GUIDES
   - **Causa**: Atendimento sem guias de autorização registradas
   - **Ação**: Suspender faturamento, solicitar autorização retroativa
   - **Próximo Passo**: Equipe de autorização obter guias da operadora

2. **Tipo de Guia Inválido**
   - **Código**: INVALID_GUIDE_TYPE
   - **Causa**: Tipo de guia não conforme padrão TISS
   - **Ação**: Rejeitar agrupamento
   - **Próximo Passo**: Correção do tipo de guia no sistema

3. **Itens Não Autorizados**
   - **Código**: UNAUTHORIZED_ITEMS
   - **Causa**: Itens de cobrança sem autorização correspondente
   - **Ação**: Rejeitar submissão, solicitar autorização adicional
   - **Próximo Passo**: Revisar procedimentos realizados vs autorizados

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `encounterId` | String | Sim | Identificador único do atendimento | Formato: ENC-NNNN-NNNNNNNNNN |
| `contractAdjustedCharges` | Lista<Objeto> | Sim | Cobranças após ajustes contratuais | Mínimo 1 item |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `billingGroups` | Mapa<String, Lista<Objeto>> | Cobranças agrupadas por número de guia | Geração de XML TISS por guia |
| `guideTypes` | Mapa<String, String> | Mapeamento de número de guia para tipo | Seleção de template TISS |
| `groupCount` | Inteiro | Quantidade de grupos de faturamento criados | Métricas e rastreamento |
| `unauthorizedItems` | Lista<Objeto> | Itens sem autorização válida | Solicitação de autorização |

**Estrutura de `billingGroups`**:
```json
{
  "GUIA-2025-001234": [
    {
      "chargeCode": "PROF-001",
      "description": "Consulta Médica",
      "amount": 200.00,
      "category": "PROFESSIONAL"
    }
  ],
  "GUIA-2025-001235": [
    {
      "chargeCode": "HOSP-001",
      "description": "Diária Hospitalar",
      "amount": 800.00,
      "category": "HOSPITAL"
    },
    {
      "chargeCode": "HOSP-002",
      "description": "Taxa de Emergência",
      "amount": 500.00,
      "category": "HOSPITAL"
    }
  ]
}
```

**Estrutura de `guideTypes`**:
```json
{
  "GUIA-2025-001234": "CONSULTA",
  "GUIA-2025-001235": "INTERNACAO",
  "GUIA-2025-001236": "SADT"
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Cálculo de Taxa de Cobertura de Autorização

```
Entrada:
  T = Total de itens de cobrança
  A = Total de itens com autorização

Cálculo:
  Taxa_Cobertura = (A / T) × 100

Validação:
  SE Taxa_Cobertura < 100 ENTÃO
    identificar_itens_nao_autorizados()

Saída:
  Taxa_Cobertura (Percentual)
```

**Exemplo**:
```
Total de itens: 5
Itens autorizados: 5
Taxa de Cobertura = (5 / 5) × 100 = 100%
```

### 4.2. Distribuição de Itens por Tipo de Guia

```
Entrada:
  G = Lista de grupos de faturamento
  T = Tipo de guia alvo

Cálculo:
  Qtd_Itens_Tipo = Σ(|G[g].itens|)
                   ONDE G[g].tipo = T
                   PARA todos os grupos g

Saída:
  Qtd_Itens_Tipo (Inteiro)
```

### 4.3. Identificação de Lacunas de Autorização

```
Algoritmo de Detecção:

conjunto_cobranças ← CONJUNTO(todas_as_cobranças)
conjunto_autorizadas ← CONJUNTO_VAZIO

PARA CADA guia:
  PARA CADA procedimento_autorizado:
    conjunto_autorizadas.ADICIONAR(procedimento_autorizado)

lacunas ← conjunto_cobranças - conjunto_autorizadas

SE lacunas.tamanho > 0:
  RETORNAR lista de cobranças em lacunas
SENÃO:
  RETORNAR lista_vazia
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Sistema de Autorização | Consulta | Guias de autorização, procedimentos autorizados | API REST |
| Sistema TISS | Envio | XML de guias por tipo | Web Service SOAP |
| Base de Dados Operadora | Consulta | Validação de números de guia | API REST |
| Sistema de Auditoria | Escrita | Log de atribuições, itens não autorizados | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Cadastro de guias de autorização
- Procedimentos autorizados por guia
- Tipos de guia válidos (TISS)
- Validação de números de guia com operadora

**Frequência de Atualização**:
- Guias de autorização: Tempo real
- Tipos TISS: Anual (conforme atualização ANS)
- Validação com operadora: Por demanda

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Cobertura de Autorização | % de itens com autorização válida | 100% | (Autorizados / Total) × 100 | Diária |
| Tempo Médio de Agrupamento | Tempo de processamento | ≤ 3 segundos | Média de duração | Diária |
| Taxa de Rejeição por Falta de Autorização | % de agrupamentos rejeitados | < 2% | (Rejeitados / Total) × 100 | Semanal |
| Quantidade Média de Guias por Atendimento | Média de guias | 1-3 guias | Média por atendimento | Mensal |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Tempo de Processamento | Duração do agrupamento | > 5 segundos | Otimizar consultas de guias |
| Erros UNAUTHORIZED_ITEMS | Itens sem autorização | > 5% | Revisar processo de autorização |
| Erros NO_AUTHORIZATION_GUIDES | Atendimentos sem guias | > 1% | Validar fluxo de autorização |
| Guias Inválidas | Tipos de guia não conformes | > 0 | Corrigir cadastro de guias |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Início do agrupamento por guia
2. Recuperação de guias de autorização
3. Validação de tipos de guia TISS
4. Atribuição de cada item a uma guia
5. Identificação de itens não autorizados
6. Conclusão do agrupamento

**Informações Capturadas**:
```json
{
  "timestamp": "2025-01-12T10:20:00Z",
  "encounterId": "ENC-001-1234567890",
  "guidesFound": 3,
  "groupsCreated": 3,
  "guideTypes": {
    "GUIA-2025-001234": "CONSULTA",
    "GUIA-2025-001235": "INTERNACAO",
    "GUIA-2025-001236": "SADT"
  },
  "itemsAssigned": 5,
  "unauthorizedItems": 0,
  "executionTimeMs": 187
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Tipos TISS | Preventivo | Por transação | Sistema automático |
| Auditoria de Autorizações | Detectivo | Diária | Equipe de Autorização |
| Reconciliação com Operadora | Detectivo | Semanal | Auditoria Interna |
| Revisão de Itens Não Autorizados | Corretivo | Diária | Equipe de Faturamento |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| NO_AUTHORIZATION_GUIDES | Nenhuma guia de autorização encontrada | CRÍTICA | Suspender faturamento, solicitar guias |
| INVALID_GUIDE_TYPE | Tipo de guia não conforme TISS | CRÍTICA | Corrigir tipo no cadastro |
| UNAUTHORIZED_ITEMS | Itens sem autorização válida | CRÍTICA | Solicitar autorização adicional |
| EXPIRED_GUIDE | Guia de autorização expirada | AVISO | Renovar autorização |

### 8.2. Estratégia de Retry

**Erros Transientes (retry automático)**:
- Timeout em consulta de guias
- Erro de conexão com base de autorizações
- Indisponibilidade temporária de serviço

**Configuração**:
- Máximo de tentativas: 3
- Intervalo entre tentativas: 1s, 2s, 4s (exponencial)
- Timeout por tentativa: 10 segundos

**Erros Permanentes (sem retry)**:
- NO_AUTHORIZATION_GUIDES
- INVALID_GUIDE_TYPE
- UNAUTHORIZED_ITEMS

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Agrupamento Bem-Sucedido

**Cenário**: Agrupar cobranças de atendimento com múltiplas guias

**Pré-condições**:
- Atendimento com 5 itens de cobrança
- 3 guias de autorização registradas
- Todos os itens têm autorização

**Fluxo**:
1. Sistema recebe encounterId = "ENC-001-123"
2. Recupera 3 guias:
   - GUIA-001: Tipo CONSULTA, procedimentos [PROF-001]
   - GUIA-002: Tipo INTERNACAO, procedimentos [HOSP-001, HOSP-002]
   - GUIA-003: Tipo SADT, procedimentos [MAT-001, MED-001]
3. Valida tipos de guia: todos válidos
4. Atribui cobranças:
   - PROF-001 → GUIA-001
   - HOSP-001 → GUIA-002
   - HOSP-002 → GUIA-002
   - MAT-001 → GUIA-003
   - MED-001 → GUIA-003
5. Todos os itens atribuídos, nenhum não autorizado
6. Cria 3 grupos de faturamento

**Pós-condições**:
- `billingGroups` com 3 grupos
- `groupCount` = 3
- `unauthorizedItems` = []
- Pronto para geração de XML TISS

**Resultado**: Sucesso com agrupamento completo

### 9.2. Fluxo Alternativo - Itens Não Autorizados

**Cenário**: Agrupamento com item sem autorização

**Fluxo**:
1. Sistema recupera guias e cobranças
2. Identifica item "PROC-999" não está em nenhuma guia
3. Adiciona a lista de não autorizados
4. Lança erro UNAUTHORIZED_ITEMS
5. Notifica equipe de autorização
6. Aguarda autorização adicional

**Resultado**: Erro com necessidade de autorização

### 9.3. Fluxo de Exceção - Tipo de Guia Inválido

**Cenário**: Guia com tipo não conforme TISS

**Fluxo**:
1. Sistema recupera guia com tipo "CUSTOM_TYPE"
2. Valida contra tipos TISS válidos
3. Tipo não encontrado na lista
4. Lança erro INVALID_GUIDE_TYPE
5. Registra em auditoria
6. Notifica administrador do sistema

**Ações Corretivas**:
- Corrigir tipo de guia no cadastro
- Verificar integração com sistema de autorização
- Treinar equipe sobre tipos TISS válidos

**Resultado**: Erro com correção de cadastro necessária

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 305/2012 | Art. 3º | Utilização obrigatória de guias TISS | Validação de tipos de guia conforme padrão TISS |
| ANS RN 305/2012 | Art. 5º | Agrupamento por tipo de guia | Separação de itens por guideType (CONSULTA, SADT, etc.) |
| ANS RN 395/2016 | Art. 8º | Vinculação de procedimentos a autorizações | Atribuição de cobranças apenas a guias autorizadas |
| TISS 4.0 | Componente 4 | Estrutura de guias por tipo de atendimento | Mapeamento correto de tipos de guia |
| CFM Res. 1.821/2007 | Art. 5º | Rastreabilidade de autorizações | Log de atribuição item-guia |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Solicitação de autorização: Equipe assistencial
- Concessão de autorização: Operadora de saúde
- Agrupamento: Sistema automático
- Validação: Auditoria de contas

**Retenção de Dados**:
- Guias de autorização: 5 anos (ANS)
- Logs de agrupamento: 5 anos
- Rastreamento item-guia: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker pattern |
| Consulta de Guias | Síncrona | Assíncrona com workers | Implementar worker para busca de guias |
| Validação TISS | Em memória | Via variáveis | Externalizar tipos válidos |
| Atribuição | Sequencial | Paralela possível | Considerar paralelização |

### 11.2. Estratégia de Migração

**Fase 1 - Decomposição**:
```
GroupByGuideWorker (Principal)
├── FetchAuthorizationGuidesWorker
├── ValidateGuideTypesWorker
├── AssignChargesToGuidesWorker
└── DetectUnauthorizedItemsWorker
```

**Fase 2 - Event-Driven**:
```java
@JobWorker(type = "group-by-guide")
public GroupingResponse groupCharges(
    @Variable String encounterId,
    @Variable List<Map<String, Object>> charges
) {
    // Buscar guias de forma assíncrona
    // Validar tipos TISS
    // Atribuir cobranças
    // Retornar grupos ou erro
    return groupingResult;
}
```

### 11.3. Oportunidades de Melhoria

**Cache de Guias**:
- Implementar cache distribuído de guias ativas
- Reduzir consultas ao sistema de autorização
- Atualização via eventos de nova autorização

**Validação Assíncrona**:
- Validar tipos TISS em paralelo com busca
- Pre-validar guias antes de agrupamento
- Circuit breaker para sistema de autorização

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing (Faturamento)

**Sub-domínio**: Core Domain - Authorization Grouping

**Responsabilidade**: Agrupamento de cobranças por guias de autorização TISS

### 12.2. Agregados e Entidades

**Agregado Raiz**: `BillingGroupsByGuide`

```
BillingGroupsByGuide (Aggregate Root)
├── EncounterId (Value Object)
├── BillingGroups (Map)
│   └── [GuideNumber → List<ChargeItem>]
├── GuideTypes (Map)
│   └── [GuideNumber → GuideType (Enum)]
├── UnauthorizedItems (Collection)
│   └── ChargeItem
├── GroupCount (Integer)
└── GroupedAt (Instant)

AuthorizationGuide (Entity)
├── GuideNumber (Value Object)
├── GuideType (Enum: CONSULTA, SADT, INTERNACAO, SP_SADT, HONORARIOS)
├── AuthorizationDate (LocalDate)
├── ValidUntil (LocalDate)
├── AuthorizedProcedures (Collection of ProcedureCode)
└── IsActive (Boolean)
```

**Value Objects**:
- `GuideNumber`: Número único de guia
- `GuideType`: Enum de tipos TISS
- `ProcedureCode`: Código de procedimento autorizado

### 12.3. Domain Events

```
ChargesGroupedByGuideEvent
├── aggregateId: EncounterId
├── groupCount: Integer
├── guideTypes: Map<GuideNumber, GuideType>
├── totalItemsGrouped: Integer
├── groupedAt: Instant
└── version: Long

UnauthorizedItemsDetectedEvent
├── encounterId: EncounterId
├── unauthorizedItems: List<ChargeItem>
├── itemCount: Integer
├── detectedAt: Instant
└── severity: Severity.CRITICAL

InvalidGuideTypeDetectedEvent
├── guideNumber: GuideNumber
├── invalidType: String
├── encounterId: EncounterId
├── detectedAt: Instant
└── severity: Severity.CRITICAL
```

### 12.4. Serviços de Domínio

**GuideGroupingService**:
```
Responsabilidades:
- Recuperar guias de autorização
- Validar conformidade TISS
- Atribuir cobranças às guias
- Identificar itens não autorizados

Métodos:
- groupChargesByGuide(encounterId, charges): BillingGroups
- validateGuideTypes(guides): ValidationResult
- assignChargeToGuide(charge, guides): GuideNumber
- detectUnauthorizedItems(charges, groups): List<ChargeItem>
```

### 12.5. Repositories

```
AuthorizationGuideRepository
├── findByEncounterId(encounterId): List<AuthorizationGuide>
├── findByGuideNumber(guideNumber): AuthorizationGuide
└── findActiveGuides(): List<AuthorizationGuide>

BillingGroupRepository
├── saveBillingGroups(groups): BillingGroupsByGuide
└── findByEncounterId(encounterId): BillingGroupsByGuide
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Guia de Autorização | Authorization Guide | Documento TISS que autoriza procedimentos |
| Agrupamento | Grouping | Processo de atribuição de cobranças a guias |
| Tipo de Guia | Guide Type | Classificação TISS (CONSULTA, SADT, INTERNACAO, etc.) |
| Item Não Autorizado | Unauthorized Item | Cobrança sem autorização correspondente |
| Procedimento Autorizado | Authorized Procedure | Código de procedimento incluído na guia |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `GroupByGuideDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `groupByGuide` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Strategy, Builder |
| **Complexidade Ciclomática** | 8 (Média) |
| **Linhas de Código** | 239 |
| **Cobertura de Testes** | 88% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x

**Serviços Integrados** (futuro):
- AuthorizationGuideService
- TISSValidationService
- OperadoraIntegrationService

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 10s | Consulta de guias pode ser lenta |
| Cache TTL (Guias) | 15 minutos | Guias mudam com frequência média |
| Retry Máximo | 3 tentativas | Tolerância a falhas de rede |
| Batch Size | 50 itens | Limite de itens por guia |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "charges_grouped_by_guide",
  "encounterId": "ENC-001-1234567890",
  "guidesFound": 3,
  "groupsCreated": 3,
  "itemsAssigned": 5,
  "unauthorizedItems": 0,
  "guideTypes": ["CONSULTA", "INTERNACAO", "SADT"],
  "executionTimeMs": 187,
  "timestamp": "2025-01-12T10:20:00Z"
}
```

**Métricas Prometheus**:
- `guide_grouping_duration_seconds` (Histogram)
- `guides_per_encounter_total` (Histogram)
- `unauthorized_items_total` (Counter)
- `invalid_guide_types_total` (Counter)
- `grouping_errors_total` (Counter por tipo)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Agrupamento bem-sucedido com múltiplas guias
2. ✅ Nenhuma guia de autorização encontrada
3. ✅ Tipo de guia inválido
4. ✅ Itens sem autorização detectados
5. ✅ Validação de número de guia nulo
6. ✅ Atribuição correta por tipo TISS
7. ✅ Performance com 20+ guias

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
