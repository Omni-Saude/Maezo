# RN-GLOSA-001: Análise e Estratégia de Recurso de Glosas

## I. Identificação da Regra

**Código**: RN-GLOSA-001
**Nome**: Análise e Estratégia de Recurso de Glosas
**Versão**: 1.0.0
**Módulo**: Gestão de Glosas
**Processo de Negócio**: Análise de Negação de Pagamento
**Data de Criação**: 2026-01-12
**Última Atualização**: 2026-01-12
**Autor**: Equipe de Revenue Cycle

## II. Definição e Propósito

### Definição
Define o processo sistemático de análise de glosas (negações parciais ou totais de pagamento) e determinação de estratégias apropriadas de recurso, incluindo classificação de prioridade e atribuição de equipes especializadas.

### Propósito
Garantir análise consistente e eficiente de todas as glosas recebidas, maximizando taxas de recuperação através de estratégias adequadas e alocação otimizada de recursos.

### Escopo
Aplica-se a todas as glosas identificadas em contas hospitalares, abrangendo operadoras de saúde públicas e privadas, com valores acima do limite de tolerância estabelecido.

## III. Descrição da Lógica de Negócio

### Fluxo Principal

1. **Validação de Dados da Glosa**
   - Sistema verifica presença obrigatória de tipo de glosa
   - Sistema valida que valor da glosa seja não-negativo
   - Sistema converte valores recebidos para formato decimal padronizado

2. **Determinação de Estratégia de Recurso**
   - Sistema classifica glosa por tipo (negação total, parcial, subpagamento, etc.)
   - Sistema analisa código e motivo da glosa
   - Sistema aplica regras específicas baseadas em padrões de negação:
     - Negações por autorização → Recurso de autorização
     - Negações por elegibilidade → Verificação de elegibilidade
     - Negações por codificação → Revisão de códigos
     - Negações por necessidade médica → Recurso clínico
     - Negações por prazo → Recurso de prazo

3. **Classificação de Prioridade**
   - Sistema avalia valor da glosa contra limiares estabelecidos:
     - ALTA: Valores ≥ R$ 5.000,00 ou negações totais ≥ R$ 1.000,00
     - MÉDIA: Valores entre R$ 1.000,00 e R$ 4.999,99
     - BAIXA: Valores < R$ 1.000,00

4. **Atribuição de Responsável**
   - Sistema aloca glosa para equipe especializada baseado em:
     - Valor da glosa (valores altos → equipe sênior)
     - Tipo de estratégia requerida
     - Especialização técnica necessária

5. **Integração com Regras de Negócio DMN**
   - Sistema consulta tabela de decisão Camunda DMN para classificação adicional
   - Sistema sobrescreve decisões se DMN retornar classificação diferenciada
   - Sistema registra aplicação de regras DMN para auditoria

### Regras de Decisão

**RD-001: Estratégia para Negação Total**
- SE tipo glosa = "FULL_DENIAL"
- E motivo contém "AUTHORIZATION" OU "PRE-AUTH"
- ENTÃO estratégia = "AUTHORIZATION_APPEAL"
- SENÃO SE motivo contém "ELIGIBILITY" OU "COVERAGE"
- ENTÃO estratégia = "ELIGIBILITY_VERIFICATION_APPEAL"
- SENÃO estratégia = "COMPREHENSIVE_APPEAL"

**RD-002: Estratégia para Negação Parcial**
- SE tipo glosa = "PARTIAL_DENIAL"
- E valor ≥ R$ 5.000,00
- ENTÃO estratégia = "COMPREHENSIVE_APPEAL"
- SENÃO SE motivo contém "DUPLICATE"
- ENTÃO estratégia = "DUPLICATE_CLAIM_RESOLUTION"
- SENÃO estratégia = "STANDARD_APPEAL"

**RD-003: Classificação de Prioridade**
- SE tipo glosa = "FULL_DENIAL"
- E valor ≥ R$ 1.000,00
- ENTÃO prioridade = "HIGH"
- SENÃO SE valor ≥ R$ 5.000,00
- ENTÃO prioridade = "HIGH"
- SENÃO SE valor ≥ R$ 1.000,00
- ENTÃO prioridade = "MEDIUM"
- SENÃO prioridade = "LOW"

**RD-004: Atribuição de Equipe**
- SE valor ≥ R$ 5.000,00
- ENTÃO atribuir = "SENIOR_APPEALS_TEAM"
- SENÃO SE estratégia = "AUTHORIZATION_APPEAL"
- ENTÃO atribuir = "AUTHORIZATION_TEAM"
- SENÃO SE estratégia contém "CODING"
- ENTÃO atribuir = "CODING_TEAM"
- SENÃO atribuir = "GENERAL_APPEALS_TEAM"

## IV. Variáveis e Parâmetros

### Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| glosaType | String | Sim | Tipo da glosa (FULL_DENIAL, PARTIAL_DENIAL, UNDERPAYMENT) |
| glosaReason | String | Não | Motivo textual da negação |
| glosaAmount | BigDecimal | Sim | Valor monetário da glosa |

### Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| appealStrategy | String | Estratégia de recurso recomendada |
| priority | String | Nível de prioridade (HIGH, MEDIUM, LOW) |
| assignedTo | String | Equipe ou pessoa responsável pelo recurso |

### Parâmetros de Configuração
| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| HIGH_PRIORITY_THRESHOLD | R$ 5.000,00 | Limite para classificação de alta prioridade |
| MEDIUM_PRIORITY_THRESHOLD | R$ 1.000,00 | Limite para classificação de média prioridade |
| DMN_TABLE_KEY | glosa-classification | Chave da tabela DMN para classificação |

## V. Cálculos e Fórmulas

### Cálculo de Prioridade
```
prioridade = CASO
  QUANDO tipo_glosa = "FULL_DENIAL" E valor ≥ MEDIUM_THRESHOLD
    ENTÃO "HIGH"
  QUANDO valor ≥ HIGH_THRESHOLD
    ENTÃO "HIGH"
  QUANDO valor ≥ MEDIUM_THRESHOLD
    ENTÃO "MEDIUM"
  SENÃO "LOW"
FIM CASO
```

### Classificação de Percentual de Negação Parcial
```
percentual_pago = (valor_pago / valor_esperado) × 100

categoria_negação = CASO
  QUANDO percentual_pago < 50%
    ENTÃO "PARTIAL_DENIAL" (negação significativa)
  QUANDO percentual_pago ≥ 50%
    ENTÃO "UNDERPAYMENT" (subpagamento)
FIM CASO
```

## VI. Validações e Restrições

### Validações de Entrada
- **VLD-001**: Tipo de glosa não pode ser nulo ou vazio
- **VLD-002**: Valor da glosa deve ser não-negativo (≥ 0)
- **VLD-003**: Tipo de dado de valor deve ser conversível para BigDecimal

### Restrições de Negócio
- **RST-001**: Análise deve ser determinística (mesmos inputs = mesmos outputs)
- **RST-002**: Estratégia "NO_ACTION_REQUIRED" só aplicável quando tipo = "NO_GLOSA"
- **RST-003**: Negações totais sempre recebem prioridade mínima MEDIUM

## VII. Exceções e Tratamento de Erros

### Códigos de Erro BPMN
| Código | Descrição | Tratamento |
|--------|-----------|------------|
| INVALID_GLOSA_DATA | Dados da glosa inválidos ou incompletos | Interrompe fluxo, solicita correção de dados |
| ANALYSIS_FAILED | Falha na análise da glosa | Registra erro, escalona para análise manual |

### Cenários de Exceção
1. **Tipo de Glosa Desconhecido**
   - Sistema registra warning em log
   - Sistema aplica estratégia padrão "STANDARD_APPEAL"
   - Sistema marca para revisão humana

2. **Falha em Integração DMN**
   - Sistema continua com classificação programática
   - Sistema registra falha para análise posterior
   - Sistema não interrompe processamento

## VIII. Integrações de Sistemas

### Sistemas Integrados
| Sistema | Tipo | Dados Trocados |
|---------|------|----------------|
| Camunda DMN Engine | Saída | Consulta tabela glosa-classification.dmn para regras adicionais |
| Sistema de Workflow | Saída | Publicação de estratégia e prioridade para roteamento |

### Formato de Dados DMN
```yaml
Entrada DMN:
  glosaType: String
  glosaReason: String
  glosaAmount: BigDecimal
  payerType: String (contexto)
  serviceType: String (contexto)

Saída DMN:
  appealStrategy: String (opcional - sobrescreve se presente)
  priority: String (opcional - sobrescreve se presente)
  assignedTo: String (opcional - sobrescreve se presente)
```

## IX. Indicadores de Performance (KPIs)

### KPIs Monitorados
| KPI | Métrica | Meta | Descrição |
|-----|---------|------|-----------|
| Taxa de Análise Correta | % | 95% | Percentual de análises validadas como corretas após recurso |
| Tempo Médio de Análise | Minutos | < 2 min | Tempo médio para completar análise de glosa |
| Taxa de Priorização Efetiva | % | 90% | Percentual de priorizações que resultaram em ação no prazo |
| Taxa de Alocação Correta | % | 85% | Percentual de glosas alocadas à equipe adequada |

## X. Conformidade Regulatória

### Normas Aplicáveis

**ANS - Resolução Normativa 395/2016**
- Art. 18: Prazos para resposta a recursos de glosa
- Art. 29: Fundamentação técnica de glosas
- Conformidade: Sistema registra timestamp de análise e estratégia para comprovação de prazo

**TISS - Padrão TISS 4.0**
- Componente: Guia de Comunicação de Beneficiário de Internação
- Tabelas: Motivos de Glosa (Tabela TISS 44)
- Conformidade: Sistema utiliza códigos padronizados TISS para classificação

**LGPD - Lei 13.709/2018**
- Art. 46: Minimização de dados processados
- Conformidade: Sistema processa apenas dados essenciais para análise (tipo, valor, motivo)

## XI. Notas de Migração

### Migração Camunda 7 → Camunda 8

**Complexidade de Migração**: 7/10 (Média-Alta)

**Impactos Identificados**:
1. **Variáveis de Processo**
   - Camunda 7: Usa `execution.getVariable()` com tipos Java nativos
   - Camunda 8: Requer serialização JSON para variáveis complexas
   - Ação: Manter BigDecimal como Double em variáveis de processo

2. **Erros BPMN**
   - Camunda 7: `throw new BpmnError(errorCode, message)`
   - Camunda 8: Usa `zeebe-client` com mapeamento de erros via job workers
   - Ação: Converter erros BPMN para exceções de tarefa Zeebe

3. **Integração DMN**
   - Camunda 7: DMN integrado nativamente via `DecisionService`
   - Camunda 8: DMN requer serviço externo ou integração via REST
   - Ação: Implementar DMN como tarefa de serviço externa ou migrar regras para FEEL

4. **Transações**
   - Camunda 7: Suporta transações Java/Spring
   - Camunda 8: Modelo de eventos assíncronos
   - Ação: Garantir idempotência em análises (já implementado)

**Esforço Estimado**: 16-24 horas
- Refatoração de integração DMN: 8h
- Adaptação de variáveis: 4h
- Testes de regressão: 8h
- Migração de tabelas DMN: 4h

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Nome**: Gestão de Glosas (Glosa Management)

### Agregados
- **Agregado Principal**: Glosa
- **Entidades**:
  - Glosa (raiz)
  - Análise de Glosa
  - Estratégia de Recurso
- **Value Objects**:
  - Tipo de Glosa (enum)
  - Prioridade (enum)
  - Valor Monetário

### Eventos de Domínio
| Evento | Descrição | Dados |
|--------|-----------|-------|
| GlosaAnalisada | Glosa foi analisada e estratégia definida | glosaId, estratégia, prioridade, timestamp |
| RecursoAtribuido | Recurso foi atribuído a equipe | glosaId, equipe, timestamp |
| PrioridadeEscalonada | Prioridade da glosa foi elevada | glosaId, prioridadeAnterior, prioridadeNova |

### Linguagem Ubíqua
- **Glosa**: Negação total ou parcial de pagamento por operadora
- **Recurso**: Processo formal de contestação de glosa
- **Estratégia de Recurso**: Abordagem técnica para contestação
- **Prioridade**: Nível de urgência baseado em valor e tipo
- **Equipe Especializada**: Grupo técnico com expertise específica

## XIII. Metadados Técnicos

### Informações de Implementação
| Atributo | Valor |
|----------|-------|
| Classe Java | `AnalyzeGlosaDelegate` |
| Bean Spring | `analyzeGlosa` |
| Camunda Task Type | Service Task (JavaDelegate) |
| Idempotência | Não requerida (operação determinística) |
| Escopo de Variáveis | PROCESS (variáveis compartilhadas com orquestrador) |

### Estatísticas de Código
| Métrica | Valor |
|---------|-------|
| Linhas de Código | 406 |
| Complexidade Ciclomática | 8/10 (Média) |
| Métodos Públicos | 3 |
| Métodos Privados | 8 |
| Cobertura de Testes | 85% (estimado) |

### Performance
| Métrica | Valor Esperado | Valor Crítico |
|---------|----------------|---------------|
| Tempo de Execução | 50-150ms | > 500ms |
| Uso de Memória | < 10MB | > 50MB |
| Taxa de Sucesso | > 99% | < 95% |
| Throughput | 500 análises/min | < 100 análises/min |

### Dependências Técnicas
- **Spring Framework**: Injeção de dependências e gerenciamento de beans
- **Camunda BPM 7.x**: Engine de workflow e integração DMN
- **Lombok**: Geração de código boilerplate
- **SLF4J**: Logging estruturado

### Tags de Busca
`glosa`, `análise`, `recurso`, `estratégia`, `prioridade`, `classificação`, `DMN`, `denial-management`, `appeals`, `healthcare-billing`

---

**Próxima Revisão**: 2026-04-12
**Responsável pela Manutenção**: Equipe de Revenue Cycle
**Criticidade**: ALTA
