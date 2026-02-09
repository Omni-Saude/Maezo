# RN-BIL-001: Aplicação de Regras Contratuais

**ID Técnico**: `ApplyContractRulesDelegate`
**Processo BPMN**: SUB_06 - Submissão de Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Aplicar regras contratuais específicas de cada operadora de saúde aos valores de cobrança, incluindo descontos por categoria de procedimento, limites contratuais e validação de procedimentos cobertos.

### 1.2. Contexto de Negócio
Cada operadora de saúde possui contrato específico com o hospital definindo:
- Taxas de desconto por categoria de procedimento (profissional, hospitalar, materiais, medicamentos)
- Valores máximos por guia/fatura
- Lista de procedimentos cobertos
- Regras de precificação diferenciadas

### 1.3. Benefícios Esperados
- **Conformidade Contratual**: Garantia de aplicação correta dos termos contratuais
- **Precisão Financeira**: Redução de glosas por valores incorretos
- **Transparência**: Rastreabilidade completa dos ajustes aplicados
- **Eficiência**: Automação de cálculos complexos de descontos

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve recuperar as regras contratuais da operadora, aplicar descontos específicos por categoria de procedimento, validar se todos os procedimentos estão cobertos pelo contrato e calcular o valor ajustado final respeitando os limites máximos estabelecidos.

**Lógica de Execução**:

1. **Recuperação de Regras Contratuais**
   - Consultar base de contratos usando identificador da operadora
   - Validar vigência do contrato
   - Extrair tabela de descontos por categoria
   - Obter lista de procedimentos autorizados
   - Recuperar valor máximo por guia

2. **Aplicação de Descontos por Categoria**
   ```
   PARA CADA cobrança NA lista_consolidada:
     categoria ← obter_categoria(cobrança)
     taxa_desconto ← tabela_descontos[categoria]
     valor_desconto ← valor_original × taxa_desconto
     valor_ajustado ← valor_original - valor_desconto

     ARMAZENAR:
       - valor_original
       - taxa_desconto_aplicada
       - valor_desconto
       - valor_ajustado
   ```

3. **Validação de Cobertura**
   ```
   PARA CADA cobrança:
     SE procedimento NÃO ESTÁ EM lista_procedimentos_autorizados:
       LANÇAR ERRO "PROCEDURE_NOT_COVERED"
   ```

4. **Validação de Limites**
   ```
   valor_total_ajustado ← SOMA(todos_valores_ajustados)

   SE valor_total_ajustado > limite_maximo_contrato:
     LANÇAR ERRO "INVALID_CONTRACT_RULES"
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-001-V1 | Contrato deve estar ativo | CRÍTICA | Rejeitar com erro CONTRACT_NOT_FOUND |
| BIL-001-V2 | Todos os procedimentos devem estar autorizados | CRÍTICA | Rejeitar com erro PROCEDURE_NOT_COVERED |
| BIL-001-V3 | Valor ajustado não pode exceder limite contratual | CRÍTICA | Rejeitar com erro INVALID_CONTRACT_RULES |
| BIL-001-V4 | Taxa de desconto deve ser entre 0% e 100% | CRÍTICA | Aplicar desconto zero se inválido |
| BIL-001-V5 | Categoria do procedimento deve existir na tabela | AVISO | Aplicar desconto zero se categoria não encontrada |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador da operadora válido e ativo
- Lista de cobranças consolidadas com valores originais
- Valor total de cobranças calculado
- Categorias de procedimentos identificadas

**Exceções de Negócio**:

1. **Contrato Inativo ou Inexistente**
   - **Código**: CONTRACT_NOT_FOUND
   - **Ação**: Suspender processo de cobrança
   - **Notificação**: Equipe de contratos e faturamento

2. **Procedimento Não Coberto**
   - **Código**: PROCEDURE_NOT_COVERED
   - **Ação**: Rejeitar cobrança específica
   - **Próximo Passo**: Análise de cobertura alternativa ou glosa administrativa

3. **Excesso de Limite Contratual**
   - **Código**: INVALID_CONTRACT_RULES
   - **Ação**: Suspender para revisão manual
   - **Próximo Passo**: Possível fracionamento em múltiplas guias

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `payerId` | String | Sim | Identificador da operadora de saúde | Formato: código ANS ou CNPJ |
| `consolidatedCharges` | Lista<Objeto> | Sim | Lista de cobranças consolidadas | Mínimo 1 item |
| `totalChargeAmount` | Decimal | Sim | Valor total antes de ajustes | Maior que zero |

**Estrutura de `consolidatedCharges`**:
```
{
  "chargeCode": "código do procedimento",
  "description": "descrição do item",
  "amount": valor_original,
  "category": "PROFESSIONAL | HOSPITAL | MATERIALS | MEDICATIONS",
  "quantity": quantidade,
  "complete": true/false
}
```

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `contractAdjustedCharges` | Lista<Objeto> | Cobranças com descontos aplicados | Geração de guia TISS |
| `contractAdjustedAmount` | Decimal | Valor total após ajustes contratuais | Cálculo de receita esperada |
| `contractDiscount` | Decimal | Valor total de desconto concedido | Análise financeira |
| `contractRulesApplied` | Lista<String> | Lista descritiva das regras aplicadas | Auditoria e documentação |

**Estrutura de `contractAdjustedCharges`**:
```
{
  ...campos_originais,
  "originalAmount": valor_antes_desconto,
  "contractDiscount": valor_desconto_aplicado,
  "amount": valor_final_ajustado,
  "discountRate": taxa_percentual_aplicada
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Cálculo de Desconto por Item

```
Entrada:
  V_original = valor original do procedimento
  T_categoria = taxa de desconto da categoria (0.00 a 1.00)

Cálculo:
  D_item = V_original × T_categoria
  D_item_arredondado = ARREDONDAR(D_item, 2 casas decimais, meio_para_cima)

  V_ajustado = V_original - D_item_arredondado
  V_ajustado_final = ARREDONDAR(V_ajustado, 2 casas decimais, meio_para_cima)

Saída:
  D_item_arredondado, V_ajustado_final
```

**Exemplo**:
```
Procedimento: Consulta Profissional
V_original = R$ 200,00
T_categoria = 0.10 (10% de desconto para PROFESSIONAL)

D_item = 200,00 × 0.10 = 20,00
V_ajustado = 200,00 - 20,00 = 180,00

Resultado: Desconto de R$ 20,00, Valor Ajustado de R$ 180,00
```

### 4.2. Cálculo de Valor Total Ajustado

```
Entrada:
  Lista L = {item₁, item₂, ..., itemₙ}
  Cada item contém V_ajustado

Cálculo:
  V_total_ajustado = Σ(V_ajustado_i) para i = 1 até n

Validação:
  SE V_total_ajustado > L_max_contrato ENTÃO
    LANÇAR ERRO "INVALID_CONTRACT_RULES"
```

### 4.3. Tabela de Taxas de Desconto (Exemplo)

| Categoria | Taxa Padrão | Faixa Aplicável | Observações |
|-----------|-------------|-----------------|-------------|
| PROFESSIONAL | 10% | Honorários médicos | Conforme AMB/CBHPM |
| HOSPITAL | 15% | Diárias, taxas hospitalares | Inclui hotelaria |
| MATERIALS | 5% | OPME, materiais descartáveis | Pode variar por item |
| MEDICATIONS | 8% | Medicamentos e soluções | Conforme tabela SIMPRO/Brasíndice |

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Sistema de Contratos | Consulta | Regras contratuais, tabelas de preços | API REST |
| Cadastro de Operadoras | Consulta | Status de contrato, vigência | API REST |
| Tabelas de Procedimentos | Consulta | Categorização de procedimentos | Database |
| Sistema de Auditoria | Escrita | Log de regras aplicadas | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Contratos vigentes por operadora
- Tabelas de desconto atualizadas
- Lista de procedimentos autorizados
- Limites contratuais por tipo de guia

**Frequência de Atualização**:
- Contratos: Mensal ou conforme revisão contratual
- Tabelas de desconto: Trimestral
- Procedimentos autorizados: Conforme negociação

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Aplicação Bem-Sucedida | % de cobranças com regras aplicadas sem erro | ≥ 98% | (Sucessos / Total) × 100 | Diária |
| Desconto Médio Concedido | Valor médio de desconto por guia | Conforme contrato | Σ Descontos / Qtd Guias | Mensal |
| Taxa de Exceções Contratuais | % de cobranças que excedem limites | ≤ 2% | (Exceções / Total) × 100 | Semanal |
| Tempo Médio de Processamento | Tempo de aplicação de regras | ≤ 500ms | Média de tempos | Diária |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Erros CONTRACT_NOT_FOUND | Contratos não encontrados | > 5 em 1 hora | Atualizar cadastro de contratos |
| Erros PROCEDURE_NOT_COVERED | Procedimentos não autorizados | > 10 em 1 dia | Revisar lista de procedimentos |
| Tempo de Consulta de Contrato | Latência de consulta | > 1 segundo | Otimizar cache de contratos |
| Cache Hit Rate | Taxa de acerto em cache de contratos | < 80% | Ajustar estratégia de cache |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Recuperação de regras contratuais
2. Aplicação de cada desconto individual
3. Validação de cobertura de procedimentos
4. Validação de limites contratuais
5. Cálculo de valores ajustados

**Informações Capturadas**:
```
{
  "timestamp": "data_hora_execução",
  "claimId": "identificador_cobrança",
  "payerId": "operadora",
  "contractId": "id_contrato_aplicado",
  "originalAmount": valor_original,
  "adjustedAmount": valor_ajustado,
  "discountAmount": total_desconto,
  "rulesApplied": ["lista", "de", "regras"],
  "executionTimeMs": tempo_processamento,
  "userId": "usuario_ou_sistema"
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Vigência de Contratos | Preventivo | Diária | Sistema automático |
| Revisão de Descontos Aplicados | Detectivo | Mensal | Auditoria Interna |
| Conferência de Limites Contratuais | Preventivo | Por transação | Sistema |
| Análise de Exceções | Corretivo | Semanal | Gestão de Contratos |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| CONTRACT_NOT_FOUND | Contrato não encontrado ou inativo | CRÍTICA | Suspender processo, notificar gestão de contratos |
| PROCEDURE_NOT_COVERED | Procedimento não coberto pelo contrato | CRÍTICA | Rejeitar item, avaliar cobertura alternativa |
| INVALID_CONTRACT_RULES | Regras contratuais inválidas ou valor excede limite | CRÍTICA | Revisão manual, possível fracionamento |
| INVALID_DISCOUNT_RATE | Taxa de desconto fora da faixa válida | AVISO | Aplicar taxa zero, log para revisão |

### 8.2. Estratégia de Retry

**Erros Transientes (retry automático)**:
- Timeout em consulta de contratos
- Erro de conexão com base de dados
- Indisponibilidade temporária de serviço

**Configuração**:
- Máximo de tentativas: 3
- Intervalo entre tentativas: 2s, 4s, 8s (exponencial)
- Timeout por tentativa: 5 segundos

**Erros Permanentes (sem retry)**:
- CONTRACT_NOT_FOUND
- PROCEDURE_NOT_COVERED
- INVALID_CONTRACT_RULES

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Aplicação Bem-Sucedida

**Cenário**: Aplicar regras contratuais para operadora com contrato ativo

**Pré-condições**:
- Operadora possui contrato vigente
- Todos os procedimentos estão na lista autorizada
- Valor total respeita limite contratual

**Fluxo**:
1. Sistema recebe lista de cobranças consolidadas
2. Recupera regras contratuais da operadora
3. Para cada cobrança:
   - Identifica categoria do procedimento
   - Aplica taxa de desconto correspondente
   - Calcula valor ajustado
4. Valida se procedimentos estão autorizados
5. Valida se valor total está dentro do limite
6. Retorna cobranças ajustadas e total de descontos

**Pós-condições**:
- Cobranças ajustadas prontas para geração de guia
- Desconto total calculado
- Regras aplicadas registradas em auditoria

**Resultado**: Sucesso com valores ajustados

### 9.2. Fluxo Alternativo - Procedimento Não Coberto

**Cenário**: Cobrança inclui procedimento não autorizado pelo contrato

**Fluxo**:
1. Sistema identifica procedimento "MAT-999" não autorizado
2. Lança erro PROCEDURE_NOT_COVERED
3. Suspende processamento da guia
4. Notifica equipe de faturamento
5. Aguarda análise manual para:
   - Remover procedimento não coberto
   - Solicitar autorização adicional
   - Cobrar em guia separada

**Resultado**: Erro com necessidade de intervenção

### 9.3. Fluxo de Exceção - Excesso de Limite

**Cenário**: Valor ajustado excede limite máximo do contrato

**Fluxo**:
1. Sistema calcula valor total ajustado: R$ 55.000,00
2. Compara com limite contratual: R$ 50.000,00
3. Identifica excesso de R$ 5.000,00
4. Lança erro INVALID_CONTRACT_RULES
5. Sugere opções:
   - Fracionamento em múltiplas guias
   - Solicitação de autorização especial
   - Remoção de itens não essenciais

**Resultado**: Erro com necessidade de ajuste

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 395/2016 | Art. 5º | Aplicação de tabelas de preços contratuais | Sistema consulta e aplica tabelas vigentes automaticamente |
| ANS RN 395/2016 | Art. 7º | Transparência nos valores cobrados | Todos os descontos são registrados com rastreabilidade completa |
| TISS 4.0 | Componente 4 | Validação de procedimentos autorizados | Validação automática contra lista de procedimentos do contrato |
| LGPD Art. 6º | Inciso VI | Transparência no processamento | Log completo de regras aplicadas e valores ajustados |
| LGPD Art. 16º | - | Precisão dos dados financeiros | Arredondamentos conforme normas contábeis (meio para cima) |
| LGPD Art. 18º | Inciso II | Acesso aos dados de cobrança | Regras aplicadas disponíveis para consulta |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Cadastro de contratos: Gestor de Contratos
- Aplicação de regras: Sistema automático
- Auditoria de descontos: Auditoria Interna
- Aprovação de exceções: Gestor Financeiro

**Retenção de Dados**:
- Regras aplicadas: 5 anos (conforme CFM)
- Logs de auditoria: 5 anos
- Contratos: Permanente
- Cálculos de desconto: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para padrão JobWorker |
| Variáveis de Processo | DelegateExecution.setVariable() | API de variáveis Zeebe | Adaptar gestão de variáveis |
| Tratamento de Erros | BpmnError | Incident + Error Event | Implementar tratamento Zeebe-native |
| Transações | Controle manual | Gerenciado por Zeebe | Remover controle transacional explícito |
| Cache de Contratos | Spring Cache local | Distribuído (Redis) | Implementar cache distribuído |

### 11.2. Estratégia de Migração

**Fase 1 - Preparação**:
1. Extrair lógica de negócio para serviços independentes
2. Criar interfaces abstratas para desacoplamento
3. Implementar testes de integração abrangentes

**Fase 2 - Adaptação**:
```java
// Camunda 8 - JobWorker Pattern
@JobWorker(type = "apply-contract-rules")
public ApplyContractRulesResponse handle(
    @Variable String payerId,
    @Variable List<ChargeItem> consolidatedCharges,
    @Variable BigDecimal totalChargeAmount
) {
    // Lógica de negócio permanece igual
    ContractRules rules = retrieveContractRules(payerId);
    List<ChargeItem> adjusted = applyRulesToCharges(consolidatedCharges, rules);

    return new ApplyContractRulesResponse(
        adjusted,
        calculateAdjustedAmount(adjusted),
        // ...
    );
}
```

**Fase 3 - Validação**:
- Testes paralelos Camunda 7 vs Camunda 8
- Validação de resultados financeiros
- Verificação de performance

### 11.3. Recomendação DMN

**Oportunidade de Externalização**:
A lógica de aplicação de descontos por categoria pode ser externalizada em uma tabela DMN para facilitar manutenção:

```
Tabela DMN: contract-discount-rules.dmn

| Categoria | Tipo Contrato | Desconto (%) | Limite Máximo |
|-----------|---------------|--------------|---------------|
| PROFESSIONAL | AMB | 10 | - |
| PROFESSIONAL | PARTICULAR | 0 | - |
| HOSPITAL | AMB | 15 | 50000 |
| HOSPITAL | SUS | 20 | 100000 |
| MATERIALS | AMB | 5 | - |
| MEDICATIONS | AMB | 8 | - |
```

**Benefícios**:
- Atualização de regras sem deploy de código
- Versionamento de tabelas de desconto
- Auditoria facilitada de mudanças

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Billing (Faturamento)

**Sub-domínio**: Core Domain - Pricing & Contracts

**Responsabilidade**: Aplicação de regras de precificação contratuais para geração de cobranças precisas

### 12.2. Agregados e Entidades

**Agregado Raiz**: `ContractAdjustedClaim`

```
ContractAdjustedClaim (Aggregate Root)
├── ClaimId (Value Object)
├── PayerId (Value Object)
├── Contract (Entity)
│   ├── ContractId
│   ├── DiscountTable
│   ├── CoveredProcedures
│   └── MaximumAmount
├── AdjustedCharges (Collection of Entities)
│   └── AdjustedChargeItem
│       ├── ChargeCode
│       ├── OriginalAmount (Money)
│       ├── DiscountRate
│       ├── DiscountAmount (Money)
│       └── AdjustedAmount (Money)
└── TotalDiscount (Money)
```

**Value Objects**:
- `Money`: Representação imutável de valores monetários
- `DiscountRate`: Taxa percentual com validações
- `ChargeCode`: Código de procedimento com formato validado

### 12.3. Domain Events

```
ContractRulesAppliedEvent
├── aggregateId: ClaimId
├── payerId: String
├── originalAmount: Money
├── adjustedAmount: Money
├── discountAmount: Money
├── rulesApplied: List<String>
├── timestamp: Instant
└── version: Long

ProcedureNotCoveredEvent
├── claimId: ClaimId
├── procedureCode: String
├── payerId: String
├── timestamp: Instant
└── reason: String

ContractLimitExceededEvent
├── claimId: ClaimId
├── attemptedAmount: Money
├── contractLimit: Money
├── excessAmount: Money
└── timestamp: Instant
```

### 12.4. Serviços de Domínio

**ContractRulesApplicationService**:
```
Responsabilidades:
- Orquestrar aplicação de regras contratuais
- Coordenar validações de cobertura
- Calcular descontos agregados
- Emitir domain events

Métodos:
- applyContractRules(claim, contract): AdjustedClaim
- validateProcedureCoverage(procedures, contract): ValidationResult
- calculateAggregateDiscounts(charges, discountTable): TotalDiscount
```

### 12.5. Repositories

```
ContractRepository
├── findByPayerId(payerId): Optional<Contract>
├── findActiveContracts(): List<Contract>
└── save(contract): Contract

DiscountTableRepository
├── findByContractId(contractId): DiscountTable
└── findEffectiveTable(payerId, date): DiscountTable
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Desconto Contratual | Contract Discount | Redução percentual aplicada conforme contrato |
| Regra de Precificação | Pricing Rule | Política de cálculo de valores por categoria |
| Valor Ajustado | Adjusted Amount | Valor após aplicação de descontos contratuais |
| Procedimento Autorizado | Covered Procedure | Procedimento incluído na lista de cobertura do contrato |
| Limite de Guia | Claim Limit | Valor máximo permitido por guia conforme contrato |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `ApplyContractRulesDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `applyContractRules` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Template Method, Strategy |
| **Complexidade Ciclomática** | 8 (Moderada) |
| **Linhas de Código** | 222 |
| **Cobertura de Testes** | 95% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x

**Serviços Integrados**:
- ContractManagementService (futuro)
- PayerRegistryService (futuro)
- AuditService (futuro)

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 10s | Operação síncrona com consultas a BD |
| Pool de Threads | 20 | Baseado em carga estimada |
| Cache TTL (Contratos) | 1 hora | Contratos raramente mudam durante operação |
| Retry Máximo | 3 tentativas | Erros transientes de BD |
| Circuit Breaker Threshold | 50% falhas em 1 min | Proteger sistemas downstream |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "contract_rules_applied",
  "claimId": "CLM-ENC-001-1234567890",
  "payerId": "ANS-12345",
  "originalAmount": 1730.00,
  "adjustedAmount": 1550.00,
  "discountAmount": 180.00,
  "rulesApplied": 4,
  "executionTimeMs": 245,
  "timestamp": "2025-01-12T10:30:00Z"
}
```

**Métricas Prometheus**:
- `contract_rules_application_duration_seconds` (Histogram)
- `contract_rules_application_total` (Counter)
- `contract_rules_application_errors_total` (Counter por tipo)
- `contract_discount_amount_total` (Counter)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Aplicação bem-sucedida com múltiplas categorias
2. ✅ Contrato não encontrado
3. ✅ Procedimento não coberto
4. ✅ Excesso de limite contratual
5. ✅ Descontos zero para categorias não mapeadas
6. ✅ Arredondamento correto de valores
7. ✅ Validação de taxa de desconto inválida
8. ✅ Performance com 100+ itens de cobrança

**Estratégia de Teste**:
- Unitários: Mocks para repositórios e serviços externos
- Integração: Banco H2 em memória
- Performance: JMH benchmarks

---

## XIV. Glossário de Termos

| Termo | Definição |
|-------|-----------|
| **Contrato Hospitalar** | Acordo entre hospital e operadora definindo preços, descontos e condições de pagamento |
| **Taxa de Desconto** | Percentual de redução aplicado ao valor original conforme categoria |
| **Valor Ajustado** | Valor final após aplicação de descontos contratuais |
| **Procedimento Autorizado** | Procedimento médico incluído na lista de cobertura do contrato específico |
| **Limite de Guia** | Valor máximo que pode ser cobrado em uma única guia conforme contrato |
| **Categoria de Procedimento** | Classificação do procedimento (Professional, Hospital, Materials, Medications) |
| **Tabela Contratual** | Conjunto de regras de precificação específicas de um contrato |

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
