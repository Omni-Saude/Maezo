# RN-BIL-002: Consolidação de Cobranças

**ID Técnico**: `ConsolidateChargesDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Consolidar todas as cobranças relacionadas a um atendimento hospitalar, agrupando taxas profissionais, diárias hospitalares, materiais e medicamentos em uma estrutura unificada pronta para faturamento.

### 1.2. Contexto de Negócio
Durante um atendimento hospitalar, múltiplas cobranças são geradas por diferentes departamentos:
- **Serviços Profissionais**: Honorários médicos, consultas, procedimentos
- **Serviços Hospitalares**: Diárias, taxas de sala, equipamentos
- **Materiais**: OPME, descartáveis, insumos
- **Medicamentos**: Medicações administradas, soluções

Antes de submeter à operadora, é necessário consolidar todas estas cobranças, validar completude e categorizar para aplicação correta de regras contratuais.

### 1.3. Benefícios Esperados
- **Precisão de Faturamento**: Garantia de inclusão de todas as cobranças do atendimento
- **Organização**: Estruturação lógica por categoria para aplicação de regras
- **Rastreabilidade**: Vínculo claro entre atendimento e cobranças
- **Eficiência**: Automação de consolidação reduz tempo de fechamento de contas

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve recuperar todas as cobranças registradas durante o atendimento, validar a completude dos dados, categorizar por tipo de serviço e calcular totais agregados, gerando uma lista consolidada pronta para processamento de faturamento.

**Lógica de Execução**:

1. **Recuperação de Cobranças**
   ```
   cobrancas_totais ← RECUPERAR_TODAS_COBRANCAS(encounterId)

   Fontes de Dados:
     - Sistema de Faturamento Profissional
     - Sistema de Hotelaria Hospitalar
     - Sistema de Farmácia
     - Sistema de Almoxarifado
     - Sistema de OPME
   ```

2. **Validação de Completude**
   ```
   PARA CADA cobranca EM cobrancas_totais:
     VALIDAR:
       - chargeCode NÃO É NULO E NÃO É VAZIO
       - amount > 0
       - category É VÁLIDA
       - description EXISTE
       - quantity ≥ 1

     SE validacao_falhar:
       LANÇAR ERRO "INCOMPLETE_CHARGES" COM detalhes
   ```

3. **Categorização por Tipo**
   ```
   categorias ← NOVO_MAPA_VAZIO

   PARA CADA cobranca:
     categoria ← cobranca.category
     valor ← cobranca.amount

     SE categoria NÃO EXISTE EM categorias:
       categorias[categoria] ← 0

     categorias[categoria] ← categorias[categoria] + valor
   ```

4. **Cálculo de Total Consolidado**
   ```
   total_geral ← 0

   PARA CADA cobranca:
     total_geral ← total_geral + cobranca.amount

   SE total_geral ≤ 0:
     LANÇAR ERRO "NO_CHARGES_FOUND"
   ```

5. **Verificação de Completude**
   ```
   todas_completas ← VERDADEIRO

   PARA CADA cobranca:
     SE cobranca.complete = FALSO:
       todas_completas ← FALSO
       LOG AVISO "Cobrança incompleta: " + cobranca.chargeCode
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-002-V1 | Atendimento deve existir e ter cobranças | CRÍTICA | Rejeitar com erro NO_CHARGES_FOUND |
| BIL-002-V2 | Código de cobrança obrigatório | CRÍTICA | Rejeitar com erro INCOMPLETE_CHARGES |
| BIL-002-V3 | Valor de cobrança deve ser maior que zero | CRÍTICA | Rejeitar com erro INCOMPLETE_CHARGES |
| BIL-002-V4 | Categoria deve ser uma das definidas no sistema | AVISO | Categorizar como "OTHER" |
| BIL-002-V5 | Descrição deve estar presente | CRÍTICA | Rejeitar com erro INCOMPLETE_CHARGES |
| BIL-002-V6 | Quantidade deve ser no mínimo 1 | CRÍTICA | Assumir quantidade = 1 se ausente |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador de atendimento (encounterId) válido
- Atendimento possui ao menos uma cobrança registrada
- Data de serviço válida

**Exceções de Negócio**:

1. **Nenhuma Cobrança Encontrada**
   - **Código**: NO_CHARGES_FOUND
   - **Causa**: Atendimento sem cobranças registradas
   - **Ação**: Suspender faturamento, notificar equipe clínica
   - **Próximo Passo**: Revisar registro de serviços prestados

2. **Cobranças Incompletas**
   - **Código**: INCOMPLETE_CHARGES
   - **Causa**: Dados obrigatórios ausentes (código, valor, descrição)
   - **Ação**: Rejeitar consolidação
   - **Próximo Passo**: Correção manual dos registros incompletos

3. **Atendimento Não Encontrado**
   - **Código**: ENCOUNTER_NOT_FOUND
   - **Causa**: encounterId inválido ou inexistente
   - **Ação**: Rejeitar operação
   - **Próximo Passo**: Validar dados de entrada

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `encounterId` | String | Sim | Identificador único do atendimento | Formato: ENC-NNNN-NNNNNNNNNN |
| `serviceDate` | LocalDateTime | Não | Data do serviço prestado | Não pode ser futura |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `consolidatedCharges` | Lista<Objeto> | Lista de todas as cobranças consolidadas | Aplicação de regras contratuais |
| `totalChargeAmount` | Decimal | Valor total de todas as cobranças | Validações financeiras |
| `chargeCategories` | Mapa<String, Decimal> | Totais agrupados por categoria | Análise e relatórios |
| `chargesComplete` | Boolean | Indica se todas as cobranças estão completas | Decisão de prosseguir ou aguardar |
| `consolidationDate` | LocalDateTime | Data/hora da consolidação | Auditoria |

**Estrutura de `consolidatedCharges`**:
```
[
  {
    "chargeCode": "PROF-001",
    "description": "Consulta Médica",
    "amount": 200.00,
    "category": "PROFESSIONAL",
    "quantity": 1,
    "complete": true
  },
  {
    "chargeCode": "HOSP-001",
    "description": "Diária Hospitalar",
    "amount": 800.00,
    "category": "HOSPITAL",
    "quantity": 1,
    "complete": true
  }
]
```

**Estrutura de `chargeCategories`**:
```
{
  "PROFESSIONAL": 200.00,
  "HOSPITAL": 1300.00,
  "MATERIALS": 150.00,
  "MEDICATIONS": 80.00
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Cálculo de Total por Categoria

```
Entrada:
  L = Lista de cobranças
  C = Categoria alvo

Cálculo:
  T_categoria = Σ(L[i].amount)
                ONDE L[i].category = C
                PARA i = 1 ATÉ n

Saída:
  T_categoria (Decimal)
```

**Exemplo**:
```
Cobranças da categoria HOSPITAL:
  - Diária Quarto: R$ 800,00
  - Taxa Emergência: R$ 500,00

T_HOSPITAL = 800,00 + 500,00 = R$ 1.300,00
```

### 4.2. Cálculo de Total Geral

```
Entrada:
  L = Lista de cobranças
  n = Número total de cobranças

Cálculo:
  T_geral = Σ(L[i].amount) PARA i = 1 ATÉ n

Validação:
  SE T_geral ≤ 0 ENTÃO
    LANÇAR ERRO "Total de cobranças deve ser maior que zero"

Saída:
  T_geral (Decimal)
```

### 4.3. Verificação de Completude

```
Entrada:
  L = Lista de cobranças

Cálculo:
  completude = VERDADEIRO

  PARA CADA cobranca EM L:
    SE cobranca.complete = FALSO ENTÃO
      completude = FALSO
      LOG_AVISO("Cobrança incompleta: " + cobranca.chargeCode)

Saída:
  completude (Boolean)
```

### 4.4. Distribuição Percentual por Categoria

```
Para análise e relatórios:

P_categoria = (T_categoria / T_geral) × 100

Exemplo:
  T_HOSPITAL = R$ 1.300,00
  T_geral = R$ 1.730,00

  P_HOSPITAL = (1.300,00 / 1.730,00) × 100 = 75,14%
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Sistema de Contas Médicas | Consulta | Honorários profissionais, procedimentos | API REST |
| Sistema de Hotelaria | Consulta | Diárias, taxas de sala, serviços | API REST |
| Sistema de Farmácia | Consulta | Medicações administradas, doses | API REST |
| Sistema de Almoxarifado | Consulta | Materiais e insumos utilizados | API REST |
| Sistema de OPME | Consulta | Órteses, próteses, materiais especiais | API REST |
| Sistema de Auditoria | Escrita | Log de consolidação, itens validados | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Registro completo de serviços prestados
- Tabela de códigos de cobrança (TUSS/CBHPM)
- Categorização de procedimentos
- Preços unitários dos itens

**Frequência de Atualização**:
- Cobranças: Tempo real conforme serviços são prestados
- Tabelas de códigos: Mensal (TUSS/CBHPM)
- Preços: Conforme negociação contratual

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Consolidação Bem-Sucedida | % de atendimentos consolidados sem erro | ≥ 99% | (Sucessos / Total) × 100 | Diária |
| Tempo Médio de Consolidação | Tempo entre alta e consolidação | ≤ 24 horas | Média de intervalos | Diária |
| Taxa de Completude | % de cobranças completas na primeira tentativa | ≥ 95% | (Completas / Total) × 100 | Semanal |
| Valor Médio Consolidado | Valor médio por atendimento | Conforme perfil | Σ Valores / Qtd Atendimentos | Mensal |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Tempo de Processamento | Duração da consolidação | > 5 segundos | Otimizar consultas |
| Erros INCOMPLETE_CHARGES | Cobranças com dados faltantes | > 5% | Revisar processos de registro |
| Erros NO_CHARGES_FOUND | Atendimentos sem cobranças | > 2% | Validar integração com sistemas clínicos |
| Taxa de Cache Hit | Acerto em cache de códigos | < 85% | Ajustar estratégia de cache |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Início da consolidação
2. Recuperação de cobranças por sistema fonte
3. Validação de cada item de cobrança
4. Cálculo de totais por categoria
5. Identificação de itens incompletos
6. Conclusão da consolidação

**Informações Capturadas**:
```json
{
  "timestamp": "2025-01-12T10:15:00Z",
  "encounterId": "ENC-001-1234567890",
  "serviceDate": "2025-01-10",
  "totalItems": 5,
  "totalAmount": 1730.00,
  "categories": {
    "PROFESSIONAL": 200.00,
    "HOSPITAL": 1300.00,
    "MATERIALS": 150.00,
    "MEDICATIONS": 80.00
  },
  "completeness": true,
  "executionTimeMs": 342,
  "sourceSystems": ["ProfessionalFees", "Hospitality", "Pharmacy", "Materials"]
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Completude de Dados | Preventivo | Por transação | Sistema automático |
| Reconciliação com Sistemas Fonte | Detectivo | Diária | Equipe de TI |
| Auditoria de Valores Consolidados | Detectivo | Semanal | Auditoria Interna |
| Revisão de Cobranças Incompletas | Corretivo | Diária | Equipe de Faturamento |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| NO_CHARGES_FOUND | Nenhuma cobrança encontrada para o atendimento | CRÍTICA | Suspender faturamento, revisar registro de serviços |
| INCOMPLETE_CHARGES | Cobranças com dados obrigatórios ausentes | CRÍTICA | Rejeitar consolidação, notificar equipe para correção |
| ENCOUNTER_NOT_FOUND | Atendimento não existe no sistema | CRÍTICA | Validar dados de entrada |
| INVALID_CHARGE_AMOUNT | Valor de cobrança zero ou negativo | CRÍTICA | Correção manual do registro |

### 8.2. Estratégia de Retry

**Erros Transientes (retry automático)**:
- Timeout em consulta de sistemas fonte
- Erro de conexão com bases de dados
- Indisponibilidade temporária de serviço

**Configuração**:
- Máximo de tentativas: 3
- Intervalo entre tentativas: 1s, 2s, 4s (exponencial)
- Timeout por tentativa: 10 segundos

**Erros Permanentes (sem retry)**:
- NO_CHARGES_FOUND
- INCOMPLETE_CHARGES
- ENCOUNTER_NOT_FOUND

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Consolidação Bem-Sucedida

**Cenário**: Consolidar cobranças de atendimento ambulatorial completo

**Pré-condições**:
- Atendimento registrado no sistema
- Serviços prestados registrados em sistemas fonte
- Todos os dados de cobrança completos

**Fluxo**:
1. Sistema recebe encounterId = "ENC-001-123"
2. Consulta sistemas fonte:
   - Profissional: Consulta médica (R$ 200)
   - Hospitalar: Diária + Taxa de emergência (R$ 1.300)
   - Materiais: Insumos (R$ 150)
   - Farmácia: Medicação (R$ 80)
3. Valida completude de todos os itens
4. Categoriza cobranças
5. Calcula totais:
   - Por categoria: {PROFESSIONAL: 200, HOSPITAL: 1300, ...}
   - Total geral: R$ 1.730
6. Marca todas como completas
7. Retorna lista consolidada

**Pós-condições**:
- `consolidatedCharges` contém 5 itens
- `totalChargeAmount` = R$ 1.730,00
- `chargesComplete` = true
- Pronto para aplicação de regras contratuais

**Resultado**: Sucesso com consolidação completa

### 9.2. Fluxo Alternativo - Cobranças Incompletas

**Cenário**: Consolidação com itens faltando dados obrigatórios

**Fluxo**:
1. Sistema recupera cobranças
2. Identifica item "MAT-001" sem código de cobrança
3. Validação falha: chargeCode é nulo
4. Lança erro INCOMPLETE_CHARGES
5. Notifica equipe de materiais
6. Aguarda correção para nova tentativa

**Resultado**: Erro com necessidade de correção

### 9.3. Fluxo de Exceção - Atendimento Sem Cobranças

**Cenário**: Tentar consolidar atendimento sem serviços faturáveis registrados

**Fluxo**:
1. Sistema consulta cobranças para encounterId
2. Retorno vazio de todos os sistemas fonte
3. Valida lista de cobranças: tamanho = 0
4. Lança erro NO_CHARGES_FOUND
5. Suspende faturamento
6. Notifica gestor clínico e faturamento

**Ações Corretivas**:
- Verificar se serviços foram prestados mas não registrados
- Validar integração com sistemas clínicos
- Revisar processos de documentação de atendimento

**Resultado**: Erro com investigação necessária

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 395/2016 | Art. 4º | Registro completo de serviços prestados | Validação de completude de dados obrigatórios |
| ANS RN 395/2016 | Art. 6º | Detalhamento de cobranças por categoria | Categorização automática PROFESSIONAL/HOSPITAL/MATERIALS/MEDICATIONS |
| TISS 4.0 | Componente 3 | Estrutura padronizada de itens de cobrança | Campos obrigatórios validados (código, valor, descrição) |
| CFM Res. 1.821/2007 | Art. 2º | Registro de materiais e medicamentos utilizados | Consolidação de dados de farmácia e almoxarifado |
| LGPD Art. 6º | Inciso III | Minimização de dados | Apenas dados necessários para faturamento |
| LGPD Art. 18º | Inciso I | Acesso aos dados de cobrança | Rastreabilidade de origem de cada cobrança |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Registro de serviços: Equipe clínica/assistencial
- Consolidação: Sistema automático
- Validação: Auditoria de contas
- Aprovação: Gestor de faturamento

**Retenção de Dados**:
- Cobranças consolidadas: 5 anos (CFM)
- Logs de consolidação: 5 anos
- Rastreabilidade de origem: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker pattern |
| Consulta de Sistemas | Síncrona em delegate | Assíncrona com workers | Implementar workers para cada sistema fonte |
| Agregação de Dados | Em memória no delegate | Via variáveis Zeebe | Usar variáveis intermediárias |
| Tratamento de Erros | BpmnError | Incident + Error Boundary | Adaptar estratégia de erros |
| Performance | Sequencial | Paralela (multi-worker) | Implementar consultas paralelas |

### 11.2. Estratégia de Migração

**Fase 1 - Decomposição**:
Separar consolidação em sub-workers especializados:

```
ConsolidateChargesWorker (Orquestrador)
├── FetchProfessionalChargesWorker
├── FetchHospitalChargesWorker
├── FetchMaterialsChargesWorker
├── FetchMedicationsWorkerChargesWorker
└── AggregateAndValidateWorker
```

**Fase 2 - Implementação Paralela**:
```java
@JobWorker(type = "consolidate-charges-orchestrator")
public ConsolidationResponse orchestrateConsolidation(
    @Variable String encounterId
) {
    // Dispara sub-processos paralelos para cada fonte
    // Aguarda conclusão de todos
    // Agrega resultados
    // Valida completude
    return consolidatedResult;
}
```

**Fase 3 - Otimização**:
- Implementar cache distribuído (Redis) para códigos de cobrança
- Usar message correlation para aggregação assíncrona
- Implementar circuit breakers para sistemas fonte

### 11.3. Oportunidades de Melhoria

**Event-Driven Architecture**:
Substituir consolidação por eventos:
- `ChargeRegisteredEvent` de cada sistema fonte
- Consolidador reativo agrega eventos
- Notifica quando consolidação completa

**Benefícios**:
- Tempo real na consolidação
- Menor latência
- Melhor rastreabilidade

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing (Faturamento)

**Sub-domínio**: Core Domain - Charge Consolidation

**Responsabilidade**: Agregação e validação de todas as cobranças de um atendimento

### 12.2. Agregados e Entidades

**Agregado Raiz**: `ConsolidatedEncounterCharges`

```
ConsolidatedEncounterCharges (Aggregate Root)
├── EncounterId (Value Object)
├── ServiceDate (Value Object)
├── Charges (Collection of Entities)
│   └── ChargeItem
│       ├── ChargeCode (Value Object)
│       ├── Description
│       ├── Amount (Money)
│       ├── Category (Enum)
│       ├── Quantity
│       └── IsComplete (Boolean)
├── CategoryTotals (Value Object)
│   ├── ProfessionalTotal (Money)
│   ├── HospitalTotal (Money)
│   ├── MaterialsTotal (Money)
│   └── MedicationsTotal (Money)
├── TotalAmount (Money)
├── IsComplete (Boolean)
└── ConsolidatedAt (Instant)
```

**Value Objects**:
- `EncounterId`: Identificador imutável de atendimento
- `Money`: Representação monetária com validações
- `ChargeCode`: Código de procedimento validado
- `CategoryTotals`: Agregação imutável de totais

### 12.3. Domain Events

```
ChargesConsolidatedEvent
├── aggregateId: EncounterId
├── totalAmount: Money
├── categoryBreakdown: CategoryTotals
├── chargeCount: Integer
├── isComplete: Boolean
├── consolidatedAt: Instant
└── version: Long

IncompleteChargesDetectedEvent
├── encounterId: EncounterId
├── incompleteCharges: List<ChargeCode>
├── missingFields: Map<ChargeCode, List<String>>
├── detectedAt: Instant
└── severity: Severity

NoChargesFoundEvent
├── encounterId: EncounterId
├── serviceDate: LocalDate
├── checkedAt: Instant
└── reason: String
```

### 12.4. Serviços de Domínio

**ChargeConsolidationService**:
```
Responsabilidades:
- Orquestrar recuperação de cobranças de múltiplas fontes
- Validar completude de dados
- Categorizar e agregar valores
- Emitir eventos de domínio

Métodos:
- consolidateEncounterCharges(encounterId): ConsolidatedCharges
- validateChargeCompleteness(charges): ValidationResult
- categorizeCharges(charges): CategoryTotals
- calculateTotal(charges): Money
```

### 12.5. Repositories

```
ChargeRepository
├── findByEncounterId(encounterId): List<Charge>
├── findByCategory(category): List<Charge>
└── saveConsolidation(consolidatedCharges): ConsolidatedCharges

CategoryTotalsRepository
├── findByEncounterId(encounterId): CategoryTotals
└── save(categoryTotals): CategoryTotals
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Cobrança | Charge | Item individual de serviço prestado que gera faturamento |
| Consolidação | Consolidation | Processo de agregação de todas as cobranças de um atendimento |
| Categoria de Serviço | Service Category | Classificação de cobrança (Profissional, Hospitalar, Materiais, Medicamentos) |
| Completude | Completeness | Estado que indica se todos os dados obrigatórios estão presentes |
| Atendimento | Encounter | Episódio de cuidado para o qual cobranças são geradas |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `ConsolidateChargesDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `consolidateCharges` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Template Method, Builder |
| **Complexidade Ciclomática** | 6 (Baixa) |
| **Linhas de Código** | 201 |
| **Cobertura de Testes** | 92% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x

**Serviços Integrados** (futuro):
- ProfessionalChargesService
- HospitalChargesService
- PharmacyChargesService
- MaterialsChargesService

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 15s | Consulta a múltiplos sistemas |
| Pool de Threads | 30 | Consultas paralelas a 4-5 sistemas |
| Cache TTL (Códigos) | 4 horas | Códigos TUSS/CBHPM raramente mudam |
| Retry Máximo | 3 tentativas | Tolerância a falhas transientes |
| Batch Size | 100 cobranças | Limite prático por atendimento |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "charges_consolidated",
  "encounterId": "ENC-001-1234567890",
  "totalItems": 5,
  "totalAmount": 1730.00,
  "categories": {
    "PROFESSIONAL": 200.00,
    "HOSPITAL": 1300.00,
    "MATERIALS": 150.00,
    "MEDICATIONS": 80.00
  },
  "isComplete": true,
  "executionTimeMs": 342,
  "timestamp": "2025-01-12T10:15:00Z"
}
```

**Métricas Prometheus**:
- `charges_consolidation_duration_seconds` (Histogram)
- `charges_consolidated_total` (Counter)
- `charges_consolidation_errors_total` (Counter por tipo)
- `charges_per_encounter_total` (Histogram)
- `charge_categories_distribution` (Gauge por categoria)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Consolidação bem-sucedida com múltiplas categorias
2. ✅ Nenhuma cobrança encontrada
3. ✅ Cobranças com dados incompletos
4. ✅ Atendimento não encontrado
5. ✅ Validação de valores zero ou negativos
6. ✅ Categorização correta por tipo
7. ✅ Cálculo de totais agregados
8. ✅ Performance com 50+ itens

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
