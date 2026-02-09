# RN-GLOSA-003: Criação de Provisão Financeira para Glosas

## I. Identificação da Regra

**Código**: RN-GLOSA-003
**Nome**: Criação de Provisão Financeira para Glosas
**Versão**: 1.0.0
**Módulo**: Gestão Financeira de Glosas
**Processo de Negócio**: Provisionamento Contábil de Perdas
**Data de Criação**: 2026-01-12
**Última Atualização**: 2026-01-12
**Autor**: Equipe de Revenue Cycle

## II. Definição e Propósito

### Definição
Define o processo de criação de provisões financeiras para glosas identificadas, incluindo cálculo de valores provisionados, lançamentos contábeis e integração com sistemas ERP.

### Propósito
Garantir conformidade contábil através de reconhecimento tempestivo de perdas potenciais, atendendo princípios contábeis de conservadorismo e fornecendo visibilidade financeira precisa.

### Escopo
Aplica-se a todas as glosas confirmadas que requerem provisionamento contábil, seguindo políticas financeiras da instituição e normas contábeis vigentes.

## III. Descrição da Lógica de Negócio

### Fluxo Principal

1. **Extração de Parâmetros da Glosa**
   - Sistema recupera identificador único da glosa
   - Sistema obtém valor monetário da glosa
   - Sistema determina período contábil apropriado (padrão: mês/ano atual)

2. **Cálculo do Valor de Provisão**
   - Sistema aplica percentual de provisionamento (tipicamente 100%)
   - Sistema considera probabilidade de recuperação (pode ser ajustado)
   - Sistema valida valor calculado contra limites estabelecidos

3. **Geração de Identificador de Provisão**
   - Sistema cria ID único no formato: `PROV-{glosaId}-{timestamp}`
   - Sistema garante unicidade através de timestamp em milissegundos

4. **Criação de Registro de Provisão**
   - Sistema insere registro na tabela `glosa_provisions`
   - Sistema registra: ID provisão, ID glosa, valor, período, data criação

5. **Lançamentos Contábeis (Journal Entries)**
   - Sistema cria lançamento DÉBITO: Despesa de Provisão (conta 6301)
   - Sistema cria lançamento CRÉDITO: Provisão para Glosas (conta 2101)
   - Sistema vincula lançamentos ao período contábil correto

6. **Integração com ERP**
   - Sistema enfileira provisão para integração com ERP externo (TOTVS/SAP)
   - Sistema registra status de integração pendente
   - Sistema permite processamento assíncrono

7. **Atualização de Status da Glosa**
   - Sistema marca glosa como "PROVISIONADA"
   - Sistema registra flag `provisioned = true`
   - Sistema atualiza timestamp de provisionamento

8. **Notificação a Controladores Financeiros**
   - Sistema publica evento em tópico Kafka `financial-provisions`
   - Sistema notifica equipe financeira via email/sistema
   - Sistema disponibiliza dados para dashboards financeiros

### Regras de Decisão

**RD-001: Cálculo de Valor de Provisão**
- valor_provisão = valor_glosa × percentual_provisionamento
- percentual_provisionamento = 100% (conservadorismo contábil)
- Futuras versões podem ajustar baseado em histórico de recuperação

**RD-002: Determinação de Período Contábil**
- SE período não informado
- ENTÃO período = ANO_ATUAL + "-" + MÊS_ATUAL_ZERO_PAD
- Exemplo: "2026-01"

**RD-003: Política de Provisionamento Integral**
- TODAS glosas requerem provisão de 100% do valor
- Objetivo: princípio contábil do conservadorismo
- Ajustes futuros baseados em análise estatística de recuperação

## IV. Variáveis e Parâmetros

### Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| glosaId | String | Sim | Identificador único da glosa |
| glosaAmount | Double | Sim | Valor monetário da glosa |
| accountingPeriod | String | Não | Período contábil (formato: YYYY-MM) |

### Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| provisionId | String | Identificador único da provisão criada |
| provisionAmount | Double | Valor provisionado |
| provisionCreated | Boolean | Indicador de sucesso da criação |
| provisionDate | LocalDateTime | Data/hora de criação da provisão |
| accountingPeriod | String | Período contábil utilizado |

### Parâmetros de Configuração
| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| PROVISION_PERCENTAGE | 100% | Percentual de valor a provisionar |
| DEBIT_ACCOUNT | 6301 | Conta contábil de despesa |
| CREDIT_ACCOUNT | 2101 | Conta contábil de passivo |
| ERP_INTEGRATION_ENABLED | true | Habilita integração com ERP |

## V. Cálculos e Fórmulas

### Cálculo de Valor de Provisão
```
valor_provisão = valor_glosa × 1.0

// Para implementações futuras com probabilidade de recuperação:
valor_provisão_ajustado = valor_glosa × (1 - probabilidade_recuperação)
```

### Geração de ID de Provisão
```
provisão_id = "PROV-" + glosa_id + "-" + UNIX_TIMESTAMP_MILLIS()
```

### Validação de Período Contábil
```
SE accounting_period NULO
  ano_atual = ANO_CORRENTE()
  mes_atual = MES_CORRENTE()
  accounting_period = ano_atual + "-" + FORMATAR(mes_atual, "00")
FIM SE
```

## VI. Validações e Restrições

### Validações de Entrada
- **VLD-001**: ID da glosa deve ser não-nulo e não-vazio
- **VLD-002**: Valor da glosa deve ser > 0
- **VLD-003**: Período contábil deve seguir formato YYYY-MM se fornecido

### Restrições de Negócio
- **RST-001**: Provisão só pode ser criada uma vez por glosa (idempotência)
- **RST-002**: Valor de provisão não pode exceder valor da glosa original
- **RST-003**: Período contábil deve estar dentro do exercício fiscal corrente

### Controles de Auditoria
- **AUD-001**: Todos lançamentos contábeis devem ter rastreabilidade
- **AUD-002**: Provisões devem ser revisadas mensalmente
- **AUD-003**: Integração ERP deve ser reconciliada periodicamente

## VII. Exceções e Tratamento de Erros

### Código de Erro BPMN
| Código | Descrição | Tratamento |
|--------|-----------|------------|
| PROVISION_CREATION_FAILED | Falha na criação da provisão | Interrompe fluxo, registra erro, notifica equipe financeira |

### Cenários de Exceção

**EXC-001: Falha em Integração ERP**
- Sistema registra erro em log
- Sistema mantém provisão local criada
- Sistema agenda retry de integração
- Sistema notifica equipe de TI financeiro

**EXC-002: Provisão Duplicada**
- Sistema verifica existência prévia de provisão para glosa
- Sistema retorna provisão existente sem criar nova
- Sistema registra tentativa de duplicação para auditoria

**EXC-003: Período Contábil Fechado**
- Sistema valida se período está aberto para lançamentos
- Sistema rejeita criação se período fechado
- Sistema sugere período atual aberto

## VIII. Integrações de Sistemas

### Sistemas Integrados
| Sistema | Tipo | Operações |
|---------|------|-----------|
| ERP (TOTVS/SAP) | Assíncrona | Criação de provisão, lançamentos contábeis |
| Kafka | Evento | Publicação de eventos `financial-provisions` |
| Sistema de Email | Saída | Notificação a controladores |
| Dashboard Financeiro | Consulta | Dados de provisões para visualização |

### Estrutura de Eventos Kafka
```json
{
  "eventType": "ProvisionCreated",
  "provisionId": "PROV-GLOSA-123-1736421235000",
  "glosaId": "GLOSA-123",
  "amount": 5000.00,
  "accountingPeriod": "2026-01",
  "createdAt": "2026-01-12T10:30:00Z",
  "debitAccount": "6301",
  "creditAccount": "2101"
}
```

### Interface ERP (Futura Implementação)
```yaml
Endpoint: POST /api/v1/provisions
Payload:
  provisionId: String
  glosaId: String
  amount: Double
  accountingPeriod: String
  debitAccount: String
  creditAccount: String

Response:
  erpProvisionId: String
  status: String (CREATED | PENDING | FAILED)
  integrationDate: DateTime
```

## IX. Indicadores de Performance (KPIs)

### KPIs Monitorados
| KPI | Métrica | Meta | Descrição |
|-----|---------|------|-----------|
| Tempo de Provisionamento | Minutos | < 5 min | Tempo desde glosa identificada até provisão criada |
| Taxa de Sucesso de Provisão | % | 99.5% | Percentual de provisões criadas sem erros |
| Taxa de Integração ERP | % | 98% | Percentual de provisões integradas com sucesso |
| Acurácia de Valores | % | 100% | Exatidão entre valor glosa e valor provisionado |

### KPIs Financeiros
| KPI | Descrição |
|-----|-----------|
| Total Provisionado | Soma de todas provisões ativas no período |
| Idade Média de Provisões | Tempo médio de permanência antes de reversão/perda |
| Taxa de Reversão | Percentual de provisões revertidas (glosas recuperadas) |

## X. Conformidade Regulatória

### Normas Aplicáveis

**CPC 25 - Provisões, Passivos Contingentes e Ativos Contingentes**
- Item 14: Reconhecimento quando obrigação presente provável
- Item 36: Melhor estimativa de desembolso
- Conformidade: Sistema provisiona 100% do valor por conservadorismo

**Lei 6.404/1976 - Lei das Sociedades por Ações**
- Art. 183: Critérios de avaliação de passivos
- Conformidade: Provisões classificadas como passivo circulante

**NBC TG 25 (Norma Brasileira de Contabilidade)**
- Provisões devem ser reconhecidas no momento da glosa
- Conformidade: Sistema cria provisão imediatamente após confirmação

**LGPD - Lei 13.709/2018**
- Art. 6º: Tratamento apenas de dados necessários
- Conformidade: Sistema não processa dados pessoais de pacientes

## XI. Notas de Migração

### Migração Camunda 7 → Camunda 8

**Complexidade de Migração**: 6/10 (Média)

**Impactos Identificados**:

1. **Idempotência Requerida**
   - Camunda 7: Indicado `requiresIdempotency() = true`
   - Camunda 8: Zeebe garante at-least-once delivery
   - Ação: Implementar verificação de provisão existente antes de criar

2. **Integração ERP Assíncrona**
   - Camunda 7: Código comentado indica integração futura
   - Camunda 8: Usar Zeebe job workers para integração
   - Ação: Implementar worker específico para integração ERP

3. **Notificações Kafka**
   - Camunda 7: Código comentado indica estrutura preparada
   - Camunda 8: Usar conectores Kafka nativos
   - Ação: Configurar conector Kafka Zeebe

4. **Lançamentos Contábeis**
   - Camunda 7: Stubs de SQL comentados
   - Camunda 8: Implementar como serviço externo
   - Ação: Criar microserviço de contabilidade

**Esforço Estimado**: 16-20 horas
- Implementação de idempotência: 4h
- Criação de workers ERP: 6h
- Configuração Kafka: 4h
- Testes de integração: 6h

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Nome**: Provisionamento Financeiro (Financial Provisioning)

### Agregados
- **Agregado Principal**: Provisão Financeira
- **Entidades**:
  - Provisão (raiz)
  - Lançamento Contábil
  - Integração ERP
- **Value Objects**:
  - Valor Monetário
  - Período Contábil
  - Conta Contábil
  - Status de Provisão

### Eventos de Domínio
| Evento | Descrição | Dados |
|--------|-----------|-------|
| ProvisaoCriada | Provisão financeira foi criada | provisionId, glosaId, amount, period, timestamp |
| LançamentoContabilCriado | Lançamento contábil foi registrado | journalEntryId, debitAccount, creditAccount, amount |
| IntegracaoERPSolicitada | Provisão foi enfileirada para ERP | provisionId, erpQueueId, timestamp |
| ProvisaoRevertida | Provisão foi revertida (glosa recuperada) | provisionId, reversalAmount, reversalDate |

### Linguagem Ubíqua
- **Provisão**: Reconhecimento contábil de perda potencial
- **Período Contábil**: Mês/ano de competência do lançamento
- **Lançamento Contábil**: Registro de débito e crédito
- **Conservadorismo**: Princípio de provisionar 100% do valor
- **Reversão**: Cancelamento de provisão quando glosa recuperada

## XIII. Metadados Técnicos

### Informações de Implementação
| Atributo | Valor |
|----------|-------|
| Classe Java | `CreateProvisionDelegate` |
| Bean Spring | `createProvisionDelegate` |
| Camunda Task Type | Service Task (JavaDelegate) |
| Idempotência | Sim (crítico - operação financeira) |
| Escopo de Variáveis | PROCESS |

### Estatísticas de Código
| Métrica | Valor |
|---------|-------|
| Linhas de Código | 146 |
| Complexidade Ciclomática | 3/10 (Baixa) |
| Métodos Públicos | 3 |
| Métodos Privados | 6 |
| Cobertura de Testes | 75% (estimado) |

### Performance
| Métrica | Valor Esperado | Valor Crítico |
|---------|----------------|---------------|
| Tempo de Execução | 100-300ms | > 1s |
| Uso de Memória | < 20MB | > 100MB |
| Taxa de Sucesso | > 99% | < 95% |
| Throughput | 200 provisões/min | < 50 provisões/min |

### Dependências Técnicas
- **Spring Framework**: Gerenciamento de transações e injeção
- **Camunda BPM 7.x**: Engine de workflow
- **Lombok**: Geração de código boilerplate
- **SLF4J**: Logging estruturado
- **Kafka Client** (futuro): Publicação de eventos
- **ERP Client** (futuro): Integração com TOTVS/SAP

### Tags de Busca
`provisão`, `contabilidade`, `lançamento`, `ERP`, `passivo`, `conservadorismo`, `journal-entry`, `financial-accounting`, `provision`, `accrual`

---

**Próxima Revisão**: 2026-04-12
**Responsável pela Manutenção**: Equipe Financeira
**Criticidade**: ALTA
