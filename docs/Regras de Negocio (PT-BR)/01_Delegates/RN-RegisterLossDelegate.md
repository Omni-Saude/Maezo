# RN-RegisterLossDelegate

**Camunda Delegate:** `registerLossDelegate`
**Categoria:** Gestão de Glosas (Negações) - Registro de Perda
**Arquivo:** `RegisterLossDelegate.java`

## Descrição

Registra glosas irrecuperáveis como perda financeira (write-off). Este delegate implementa o processo completo de reconhecimento de perda, incluindo baixa de contas a receber, criação de despesa de dívida incobrável, finalização de provisões e notificação a stakeholders.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaId` | String | Sim | Identificador único da glosa |
| `glosaAmount` | Double | Sim | Valor da perda a ser registrada |
| `lossReason` | String | Não | Motivo da perda (padrão fornecido) |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `lossId` | String | Identificador único do registro de perda |
| `lossAmount` | Double | Valor da perda registrada |
| `lossRegistered` | Boolean | Confirmação de registro (sempre `true` em sucesso) |
| `lossDate` | LocalDateTime | Data/hora do registro da perda |
| `finalGlosaStatus` | String | Status final da glosa (LOSS) |

## Regras de Negócio

### Quando Registrar como Perda

Glosas devem ser registradas como perda quando:
1. **Recursos Esgotados**: Todos os recursos administrativos e jurídicos foram negados
2. **Decisão Judicial Desfavorável**: Processo perdido em última instância
3. **Acordo de Write-Off**: Operadora não pagará e acordo foi fechado
4. **Inviabilidade Econômica**: Custo de recuperação > valor da glosa
5. **Prazo Prescricional**: Direito prescreveu

### Formato de IDs de Perda

```
LOSS-{glosaId}-{timestamp}
```

**Exemplo:** `LOSS-GLOSA-12345-1736685296000`

### Motivo Padrão de Perda

Se não fornecido: `"Unrecoverable after exhausting all appeal options"`

### Status Final

Após registro: `LOSS`

## Contabilização

### Lançamentos Contábeis

**Tipo:** Baixa de Contas a Receber e Reconhecimento de Despesa

```
Dr: Despesa com Dívida Incobrável (6401) - Demonstração de Resultado
    Valor: lossAmount

Cr: Contas a Receber (1101) - Balanço Patrimonial (Ativo)
    Valor: lossAmount
```

### Estrutura SQL

```sql
-- Lançamentos no razão contábil
INSERT INTO journal_entries (
  account_code,
  debit,
  credit,
  reference
) VALUES
  ('6401', ?, 0, ?),    -- Despesa com Dívida Incobrável
  ('1101', 0, ?, ?)     -- Contas a Receber
```

### Impacto Financeiro

| Relatório | Impacto | Natureza |
|-----------|---------|----------|
| **Balanço Patrimonial** | Reduz Ativo Circulante (Contas a Receber) | Negativo |
| **DRE** | Aumenta Despesas Operacionais | Negativo |
| **Fluxo de Caixa** | Sem impacto | Não-caixa |
| **EBITDA** | Reduz (se incluído em despesas operacionais) | Negativo |

## Integrações

### Banco de Dados

```sql
-- 1. Criação do registro de perda
INSERT INTO glosa_losses (
  loss_id,
  glosa_id,
  loss_amount,
  reason,
  registered_at
) VALUES (?, ?, ?, ?, NOW())

-- 2. Write-off de contas a receber
UPDATE accounts_receivable
SET write_off_amount = ?,
    status = 'WRITTEN_OFF'
WHERE glosa_id = ?

-- 3. Finalização de provisão (se existir)
UPDATE glosa_provisions
SET status = 'REALIZED',
    finalized_at = NOW()
WHERE glosa_id = ?
  AND status = 'ACTIVE'

-- 4. Atualização do status da glosa
UPDATE glosas
SET status = 'LOSS',
    loss_registered = true,
    loss_date = NOW()
WHERE glosa_id = ?

-- 5. Atualização de métricas
UPDATE loss_metrics
SET total_losses = total_losses + ?,
    loss_count = loss_count + 1
```

### Notificações via Kafka

**Topic:** `glosa-losses`

**Payload:**
```json
{
  "eventType": "LOSS_REGISTERED",
  "lossId": "LOSS-GLOSA-12345-1736685296000",
  "glosaId": "GLOSA-12345",
  "lossAmount": 5000.00,
  "lossReason": "Decisão judicial desfavorável em última instância",
  "timestamp": "2025-01-12T10:30:00Z",
  "stakeholders": ["FINANCIAL_CONTROLLERS", "MANAGEMENT", "GLOSA_TEAM"]
}
```

### Destinatários de Notificações

1. **Controladores Financeiros**: Impacto significativo nas demonstrações financeiras
2. **Gestão**: Para perdas de alto valor ou padrões preocupantes
3. **Equipe de Glosas**: Para análise de processo e melhoria contínua

## Finalização de Provisão

Se uma provisão foi criada anteriormente (via `CreateProvisionDelegate`), ela deve ser finalizada:

**Status:** `ACTIVE` → `REALIZED`

**Significado:** A provisão foi "realizada" (a perda prevista se concretizou)

**Efeito Contábil:**
- Provisão já havia reduzido o lucro quando foi criada
- Não há impacto adicional no resultado quando finalizada
- Apenas realoca entre contas do passivo

## Exemplo de Fluxo

```
1. Receber solicitação de registro de perda:
   - glosaId: GLOSA-12345
   - glosaAmount: R$ 5.000,00
   - lossReason: "Decisão judicial desfavorável"

2. Gerar ID de perda: LOSS-GLOSA-12345-1736685296000

3. Criar registro de perda no banco de dados

4. Write-off de contas a receber:
   - UPDATE accounts_receivable
   - SET write_off_amount = 5000.00
   - SET status = 'WRITTEN_OFF'

5. Criar lançamento de despesa de dívida incobrável:
   - Dr: 6401 R$ 5.000,00 (Bad Debt Expense)
   - Cr: 1101 R$ 5.000,00 (Accounts Receivable)

6. Finalizar provisão (se existir):
   - UPDATE glosa_provisions
   - SET status = 'REALIZED'

7. Atualizar status da glosa:
   - status = LOSS
   - loss_registered = true
   - loss_date = NOW()

8. Atualizar métricas de perda:
   - total_losses += 5000.00
   - loss_count += 1

9. Notificar stakeholders via Kafka:
   - Topic: glosa-losses
   - Destinatários: Controllers, Management, Glosa Team

10. Retornar:
    - lossId
    - lossAmount: 5000.00
    - lossRegistered: true
    - finalGlosaStatus: LOSS
```

## Exceções e Erros

**Tratamento:** Não lança exceções BPMN - propaga exceções runtime

Em caso de falha:
```java
throw new RuntimeException("Failed to register loss for glosa " + glosaId, e);
```

**Motivos de Falha:**
- Erro na criação do registro de perda
- Falha no write-off de AR
- Erro nos lançamentos contábeis
- Falha na atualização de métricas
- Erro no envio de notificações

## Métricas de Perda

### KPIs Acompanhados

| Métrica | Descrição | Fórmula |
|---------|-----------|---------|
| **Total de Perdas** | Valor total de glosas registradas como perda | Σ lossAmount |
| **Contagem de Perdas** | Número de glosas perdidas | COUNT(losses) |
| **Taxa de Perda** | % de glosas que resultam em perda | (Perdas / Total Glosas) × 100% |
| **Taxa de Perda Financeira** | % do valor total de glosas perdido | (Total Perdas / Total Glosas $) × 100% |

### Análise por Razão

```sql
SELECT
  loss_reason,
  COUNT(*) as loss_count,
  SUM(loss_amount) as total_amount,
  AVG(loss_amount) as avg_amount
FROM glosa_losses
GROUP BY loss_reason
ORDER BY total_amount DESC
```

**Objetivo:** Identificar causas raiz mais custosas para melhoria de processo

## Auditoria e Logging

**Nível de Log:** INFO/DEBUG/ERROR
**Eventos Auditados:**
- Registro de perda criado
- Valor da perda
- Motivo da perda
- Write-off de AR
- Lançamentos contábeis
- Finalização de provisão
- Atualização de métricas
- Notificações enviadas
- Erros no processo

## Impacto na Performance Financeira

### Demonstração de Resultado (DRE)

```
Receita Operacional Bruta        R$ 10.000.000
(-) Deduções                      R$  (500.000)
(-) Dívidas Incobráveis          R$   (50.000)  ← Impacto aqui
= Receita Operacional Líquida     R$  9.450.000
```

### Balanço Patrimonial

```
ATIVO CIRCULANTE
  Caixa e Equivalentes           R$  1.000.000
  Contas a Receber               R$  1.500.000  ← Reduz aqui
  (-) Provisão para Perdas       R$   (100.000)
```

## Análise de Melhoria Contínua

### Perguntas para Investigação

Quando uma perda é registrada, a equipe deve investigar:

1. **Causa Raiz**: Por que a glosa ocorreu originalmente?
2. **Recuperabilidade**: Por que não foi possível recuperar?
3. **Prevenção**: Como prevenir casos similares?
4. **Processo**: Falhas no processo de gestão de glosas?
5. **Documentação**: Documentação inadequada?
6. **Timing**: Recurso iniciado tardiamente?
7. **Expertise**: Falta de conhecimento especializado?

### Ciclo de Feedback

```
1. Perda registrada
2. Análise de causa raiz
3. Identificação de padrões
4. Implementação de melhorias
5. Treinamento de equipe
6. Monitoramento de impacto
7. Ajuste de processos
```

## Considerações Importantes

1. **Timing**: Não postergar write-off além do necessário - distorce relatórios financeiros

2. **Compliance**: Write-offs devem seguir políticas contábeis e tributárias

3. **Auditoria**: Auditores externos revisarão políticas de write-off

4. **Benchmark**: Comparar taxa de perda com benchmarks do setor (tipicamente 1-3%)

5. **Governança**: Perdas acima de threshold devem ter aprovação de CFO/CEO

6. **Aprendizado**: Cada perda é oportunidade de melhoria de processo

## Conformidade

- **CPC 48**: Instrumentos Financeiros - Reconhecimento de perda
- **NBC TG 38**: Provisões e Contingências
- **Regulação Tributária**: Dedutibilidade de perdas (IR/CSLL)
- **RN ANS**: Gestão de glosas no setor de saúde suplementar

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** AI Swarm - Forensics Delegate Generation
