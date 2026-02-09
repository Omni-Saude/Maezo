# RN-CreateProvisionDelegate

**Camunda Delegate:** `createProvisionDelegate`
**Categoria:** Gestão de Glosas (Negações) - Provisão Financeira
**Arquivo:** `CreateProvisionDelegate.java`

## Descrição

Cria provisão financeira para glosas identificadas. Este delegate implementa a criação completa de provisões, incluindo cálculo do valor, geração de lançamentos contábeis, integração com ERP e notificação aos controladores financeiros.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaId` | String | Sim | Identificador único da glosa |
| `glosaAmount` | Double | Sim | Valor da glosa identificada |
| `accountingPeriod` | String | Não | Período contábil (padrão: YYYY-MM atual) |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `provisionId` | String | Identificador único da provisão criada |
| `provisionAmount` | Double | Valor da provisão (calculado) |
| `provisionCreated` | Boolean | Confirmação de criação da provisão |
| `provisionDate` | LocalDateTime | Data/hora da criação da provisão |
| `accountingPeriod` | String | Período contábil da provisão |

## Regras de Negócio

### Cálculo do Valor da Provisão

**Regra:** Provisão conservadora de 100% do valor da glosa

```
provisionAmount = glosaAmount * 1.00
```

**Justificativa:** Abordagem conservadora para proteção financeira até resolução da glosa.

**Ajustes Futuros Possíveis:**
- Provisão ajustada por tipo de glosa
- Provisão baseada em probabilidade de recuperação
- Provisão parcial para glosas com histórico de recuperação

### Formato de IDs de Provisão

```
PROV-{glosaId}-{timestamp}
```

**Exemplo:** `PROV-GLOSA-12345-1736685296000`

### Período Contábil

**Formato:** `YYYY-MM`
**Padrão:** Ano e mês correntes
**Exemplo:** `2025-01`

## Lançamentos Contábeis

### Contabilização da Provisão

**Natureza:** Criação de provisão para perda potencial

```
Dr: Despesa com Provisão (6301) - Demonstração de Resultado
    Valor: provisionAmount

Cr: Provisão para Glosas (2101) - Balanço Patrimonial (Passivo)
    Valor: provisionAmount
```

### Impacto Financeiro

- **Balanço Patrimonial**: Aumenta passivo circulante
- **DRE**: Aumenta despesas operacionais
- **Fluxo de Caixa**: Sem impacto imediato (não-caixa)

## Integrações

### Banco de Dados
```sql
-- Criação do registro de provisão
INSERT INTO glosa_provisions (
  provision_id,
  glosa_id,
  amount,
  period,
  created_at
) VALUES (?, ?, ?, ?, NOW())

-- Atualização do status da glosa
UPDATE glosas
SET status = 'PROVISIONED',
    provisioned = true
WHERE glosa_id = ?
```

### Lançamentos Contábeis
```sql
-- Criação dos lançamentos no plano de contas
INSERT INTO journal_entries (
  account_code,
  debit,
  credit,
  period,
  reference
) VALUES
  ('6301', ?, 0, ?, ?),    -- Despesa com Provisão
  ('2101', 0, ?, ?, ?)     -- Provisão para Glosas
```

### ERP Externo
**Endpoint:** `POST /api/v1/provisions`
**Payload:**
```json
{
  "provisionId": "PROV-GLOSA-12345-1736685296000",
  "glosaId": "GLOSA-12345",
  "amount": 5000.00,
  "accountingPeriod": "2025-01",
  "status": "ACTIVE"
}
```

**Sistemas Suportados:**
- TOTVS Protheus
- SAP S/4HANA
- Oracle ERP Cloud

### Notificações
**Kafka Topic:** `financial-provisions`
**Payload:**
```json
{
  "eventType": "PROVISION_CREATED",
  "provisionId": "PROV-GLOSA-12345-1736685296000",
  "glosaId": "GLOSA-12345",
  "amount": 5000.00,
  "period": "2025-01",
  "timestamp": "2025-01-12T10:30:00Z"
}
```

## Exceções e Erros

### BPMN Error: PROVISION_CREATION_FAILED

**Código:** `PROVISION_CREATION_FAILED`
**Causas:**
- Falha na criação do registro de provisão
- Erro nos lançamentos contábeis
- Falha na integração com ERP
- Dados de entrada inválidos

**Tratamento:** Processo BPMN deve capturar erro e decidir ação de compensação

## Plano de Contas

### Contas Utilizadas

| Código | Descrição | Tipo | Relatório |
|--------|-----------|------|-----------|
| 6301 | Despesa com Provisão | Despesa | Demonstração de Resultado |
| 2101 | Provisão para Glosas | Passivo Circulante | Balanço Patrimonial |

## Exemplo de Fluxo

```
1. Glosa identificada: GLOSA-12345, valor: R$ 5.000,00
2. Calcular provisão: R$ 5.000,00 (100%)
3. Gerar ID: PROV-GLOSA-12345-1736685296000
4. Criar registro no banco de dados
5. Criar lançamentos contábeis:
   - Dr: 6301 R$ 5.000,00
   - Cr: 2101 R$ 5.000,00
6. Integrar com ERP (assíncrono)
7. Atualizar status da glosa para PROVISIONED
8. Notificar controladores financeiros via Kafka
9. Retornar: provisionCreated=true
```

## Idempotência

**requiresIdempotency():** `true`

Este é um **delegate crítico financeiro** que requer garantia de idempotência para evitar:
- Provisões duplicadas
- Lançamentos contábeis em duplicidade
- Distorção de relatórios financeiros

**Mecanismo:** BaseDelegate verifica operações já executadas antes de processar.

## Auditoria e Logging

**Nível de Log:** INFO/DEBUG/ERROR
**Eventos Auditados:**
- Criação de provisão
- Valor calculado
- Lançamentos contábeis gerados
- Status da integração ERP
- Notificações enviadas
- Erros e falhas

## KPIs e Métricas

- **Total de Provisões Criadas**: Por período
- **Valor Total Provisionado**: Por período e por tipo de glosa
- **Tempo Médio de Criação**: Performance do delegate
- **Taxa de Sucesso na Integração ERP**: Reliability
- **Provisões Revertidas**: Após recuperação de glosas

## Reversão de Provisão

A provisão será revertida quando:
1. **Glosa Recuperada**: RegisterRecoveryDelegate reverterá a provisão
2. **Glosa Registrada como Perda**: RegisterLossDelegate finalizará a provisão

**Lançamento de Reversão (quando recuperada):**
```
Dr: Provisão para Glosas (2101)
Cr: Reversão de Provisão (6302) - Receita
```

## Considerações Importantes

1. **Conservadorismo**: Provisão de 100% protege contra perdas inesperadas
2. **Impacto no Resultado**: Provisões reduzem lucro no período de criação
3. **Não afeta Caixa**: Provisão é lançamento não-caixa
4. **Compliance**: Atende normas contábeis brasileiras (CPC 25)
5. **Auditoria**: Provisões são foco de auditores externos

## Conformidade

- **CPC 25**: Provisões, Passivos Contingentes e Ativos Contingentes
- **RN ANS 443/2019**: Gestão de glosas no setor de saúde suplementar
- **Sarbanes-Oxley**: Controles internos financeiros (empresas de capital aberto)

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** AI Swarm - Forensics Delegate Generation
