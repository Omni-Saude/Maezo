# RN-RegisterRecoveryDelegate

**Camunda Delegate:** `registerRecoveryDelegate`
**Categoria:** Gestão de Glosas (Negações) - Registro de Recuperação
**Arquivo:** `RegisterRecoveryDelegate.java`

## Descrição

Registra recuperação bem-sucedida de glosas. Este delegate implementa o processo completo de reconhecimento de recuperação financeira, incluindo atualização de valores recuperados, reversão de provisões (quando aplicável), criação de lançamentos contábeis, atualização de métricas e notificação a stakeholders.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaId` | String | Sim | Identificador único da glosa |
| `recoveredAmount` | Double | Sim | Valor efetivamente recuperado |
| `recoveryMethod` | String | Não | Método de recuperação (padrão: APPEAL) |
| `recoveryNotes` | String | Não | Notas sobre a recuperação |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `recoveryId` | String | Identificador único do registro de recuperação |
| `recoveryRegistered` | Boolean | Confirmação de registro (sempre `true` em sucesso) |
| `recoveryDate` | LocalDateTime | Data/hora do registro da recuperação |
| `finalGlosaStatus` | String | Status final da glosa (RECOVERED) |

## Regras de Negócio

### Métodos de Recuperação

| Método | Descrição | Típico Para |
|--------|-----------|-------------|
| `APPEAL` | Recurso administrativo bem-sucedido | Glosas técnicas e documentais |
| `RESUBMISSION` | Reenvio com correções aprovado | Erros de billing |
| `NEGOTIATION` | Negociação direta com operadora | Ajustes de preço |
| `LITIGATION` | Ganho em processo judicial | Glosas contratuais complexas |
| `MEDIATION` | Acordo via mediação/arbitragem | Disputas de alto valor |

### Formato de IDs de Recuperação

```
REC-{glosaId}-{timestamp}
```

**Exemplo:** `REC-GLOSA-12345-1736685296000`

### Status Final

Após registro: `RECOVERED`

## Contabilização

### Lançamentos Contábeis - Reconhecimento de Receita

**Tipo:** Reconhecimento de receita de recuperação

```
Dr: Contas a Receber (1101) - Balanço Patrimonial (Ativo)
    Valor: recoveredAmount

Cr: Receita de Serviços ao Paciente (4101) - Demonstração de Resultado
    Valor: recoveredAmount
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
  ('1101', ?, 0, ?),    -- Contas a Receber
  ('4101', 0, ?, ?)     -- Receita de Serviços
```

### Impacto Financeiro

| Relatório | Impacto | Natureza |
|-----------|---------|----------|
| **Balanço Patrimonial** | Aumenta Ativo Circulante (Contas a Receber) | Positivo |
| **DRE** | Aumenta Receita Operacional | Positivo |
| **Fluxo de Caixa** | Impacto futuro quando recebido | Accrual |
| **EBITDA** | Aumenta | Positivo |

## Reversão de Provisão

### Quando Reverter Provisão

Se uma provisão foi criada anteriormente (via `CreateProvisionDelegate`), ela deve ser revertida:

**Condição:** Provisão com `status = 'ACTIVE'` para a glosa

### Lançamento de Reversão

**Tipo:** Reversão de provisão e reconhecimento de ganho

```
Dr: Provisão para Glosas (2101) - Balanço Patrimonial (Passivo)
    Valor: recoveredAmount

Cr: Reversão de Provisão (6302) - Demonstração de Resultado (Receita)
    Valor: recoveredAmount
```

### Efeito Líquido no Resultado

1. **Quando provisão foi criada**: Despesa reconhecida (redução de lucro)
2. **Quando recuperação ocorre**:
   - Receita reconhecida (recuperação registrada)
   - Reversão de provisão (ganho na DRE)
3. **Efeito líquido**: Resultado volta ao ponto pré-provisão

## Integrações

### Banco de Dados

```sql
-- 1. Criação do registro de recuperação
INSERT INTO glosa_recoveries (
  recovery_id,
  glosa_id,
  recovered_amount,
  recovery_method,
  notes,
  created_at
) VALUES (?, ?, ?, ?, ?, NOW())

-- 2. Atualização do status da glosa
UPDATE glosas
SET status = 'RECOVERED',
    recovered = true,
    recovery_date = NOW()
WHERE glosa_id = ?

-- 3. Atualização do valor recuperado
UPDATE glosas
SET recovered_amount = ?
WHERE glosa_id = ?

-- 4. Reversão de provisão (se existir)
SELECT provision_id
FROM glosa_provisions
WHERE glosa_id = ?
  AND status = 'ACTIVE'

-- Se provisão existe, criar lançamento de reversão

-- 5. Atualização de métricas
UPDATE recovery_metrics
SET total_recovered = total_recovered + ?,
    recovery_count = recovery_count + 1
```

### Notificações via Kafka

**Topic:** `glosa-recoveries`

**Payload:**
```json
{
  "eventType": "RECOVERY_REGISTERED",
  "recoveryId": "REC-GLOSA-12345-1736685296000",
  "glosaId": "GLOSA-12345",
  "recoveredAmount": 5000.00,
  "recoveryMethod": "APPEAL",
  "recoveryNotes": "Recurso administrativo aceito após apresentação de documentação adicional",
  "timestamp": "2025-01-12T10:30:00Z",
  "stakeholders": ["RECOVERY_TEAM", "FINANCE", "CLINICAL_TEAM"]
}
```

### Destinatários de Notificações

1. **Equipe de Recuperação**: Confirmação de sucesso
2. **Equipe Financeira**: Reconhecimento de receita
3. **Equipe Clínica**: Se recurso envolveu necessidade médica
4. **Gestão**: Para recuperações de alto valor

## Exemplo de Fluxo

```
1. Receber notificação de recuperação bem-sucedida:
   - glosaId: GLOSA-12345
   - recoveredAmount: R$ 5.000,00
   - recoveryMethod: APPEAL
   - recoveryNotes: "Recurso aceito após documentação clínica"

2. Gerar ID de recuperação: REC-GLOSA-12345-1736685296000

3. Criar registro de recuperação no banco de dados

4. Atualizar status da glosa:
   - status = RECOVERED
   - recovered = true
   - recovery_date = NOW()

5. Atualizar valor recuperado:
   - recovered_amount = 5000.00

6. Verificar se existe provisão ativa:
   - SELECT provision_id FROM glosa_provisions
   - WHERE glosa_id = GLOSA-12345 AND status = 'ACTIVE'

7a. Se provisão existe, reverter:
    - Dr: Provisão para Glosas (2101) R$ 5.000,00
    - Cr: Reversão de Provisão (6302) R$ 5.000,00

7b. Criar lançamento de receita:
    - Dr: Contas a Receber (1101) R$ 5.000,00
    - Cr: Receita de Serviços (4101) R$ 5.000,00

8. Atualizar métricas de recuperação:
   - total_recovered += 5000.00
   - recovery_count += 1
   - Atualizar recovery_rate
   - Atualizar avg_recovery_time

9. Notificar stakeholders via Kafka:
   - Topic: glosa-recoveries
   - Destinatários: Recovery Team, Finance, Clinical

10. Retornar:
    - recoveryId
    - recoveryRegistered: true
    - recoveryDate
    - finalGlosaStatus: RECOVERED
```

## Exceções e Erros

### BPMN Error: RECOVERY_REGISTRATION_FAILED

**Código:** `RECOVERY_REGISTRATION_FAILED`
**Causas:**
- Erro na criação do registro de recuperação
- Falha nos lançamentos contábeis
- Erro na atualização de métricas
- Dados de entrada inválidos

**Tratamento:** Processo BPMN deve capturar erro e decidir ação de compensação

## Idempotência

**requiresIdempotency():** `true`

Este é um **delegate crítico financeiro** que requer garantia de idempotência para evitar:
- Recuperações duplicadas
- Lançamentos contábeis em duplicidade
- Distorção de métricas de recuperação
- Reversão duplicada de provisões

**Mecanismo:** BaseDelegate verifica operações já executadas antes de processar.

## Métricas de Recuperação

### KPIs Acompanhados

| Métrica | Descrição | Fórmula |
|---------|-----------|---------|
| **Taxa de Recuperação** | % de glosas recuperadas | (Recuperadas / Total Glosas) × 100% |
| **Taxa de Recuperação Financeira** | % do valor recuperado | (Total Recuperado / Total Glosas $) × 100% |
| **Tempo Médio de Recuperação** | Dias desde identificação até recuperação | AVG(recovery_date - identification_date) |
| **Taxa de Sucesso por Método** | % de sucesso por método de recuperação | Por método: (Sucessos / Tentativas) × 100% |

### Análise por Método

```sql
SELECT
  recovery_method,
  COUNT(*) as recovery_count,
  SUM(recovered_amount) as total_amount,
  AVG(recovered_amount) as avg_amount,
  AVG(DATEDIFF(recovery_date, glosa_date)) as avg_days
FROM glosa_recoveries
GROUP BY recovery_method
ORDER BY total_amount DESC
```

**Objetivo:** Identificar métodos mais efetivos e eficientes

## Auditoria e Logging

**Nível de Log:** INFO/DEBUG/ERROR
**Eventos Auditados:**
- Registro de recuperação criado
- Valor recuperado
- Método de recuperação
- Reversão de provisão (se aplicável)
- Lançamentos contábeis
- Atualização de métricas
- Notificações enviadas
- Erros no processo

## Impacto na Performance Financeira

### Demonstração de Resultado (DRE)

**Sem Provisão Prévia:**
```
Receita de Serviços ao Paciente    R$ 10.000.000
  Receita de Recuperação           R$     50.000  ← Aumenta receita
```

**Com Provisão Prévia:**
```
Receita Operacional                R$ 10.000.000
  Receita de Recuperação           R$     50.000  ← Receita reconhecida

Despesas Operacionais
  Reversão de Provisão             R$    (50.000) ← Redução de despesa
```

### Balanço Patrimonial

```
ATIVO CIRCULANTE
  Contas a Receber                 R$  1.550.000  ← Aumenta aqui

PASSIVO CIRCULANTE
  Provisão para Glosas             R$     50.000  ← Reduz aqui (se provisão)
```

## Benchmark do Setor

### Taxas de Recuperação Típicas

| Setor | Taxa de Recuperação | Observação |
|-------|---------------------|------------|
| **Hospitais Privados** | 60-75% | Recursos administrativos |
| **Clínicas** | 50-60% | Menor estrutura de recurso |
| **Hospitais Públicos** | 40-50% | Processos mais longos |
| **Excelência** | 80%+ | Best-in-class com tecnologia |

### Tempo Médio de Recuperação

| Método | Tempo Médio | Range |
|--------|-------------|-------|
| **Resubmission** | 15-30 dias | Mais rápido |
| **Appeal** | 30-60 dias | Padrão |
| **Negotiation** | 60-90 dias | Depende da operadora |
| **Litigation** | 180-365 dias | Mais longo |

## Melhores Práticas

1. **Documentação**: Manter registro detalhado de estratégia e evidências
2. **Timing**: Recuperar o mais rápido possível - valor do dinheiro no tempo
3. **Método**: Escolher método apropriado para cada tipo de glosa
4. **Follow-up**: Monitorar status de recursos ativamente
5. **Aprendizado**: Usar casos de sucesso como template para futuros

## Considerações Importantes

1. **Timing de Reconhecimento**: Receita reconhecida quando recuperação é confirmada, não necessariamente quando paga

2. **Accrual Basis**: Contabilidade por competência - receita reconhecida independente de recebimento

3. **Reversão Completa**: Se provisão foi 100% e recuperação é 100%, efeito líquido é neutro no resultado

4. **Recuperação Parcial**: Se recuperação é menor que provisão, diferença permanece provisionada ou vira perda

5. **Métricas de Sucesso**: Alta taxa de recuperação indica processo efetivo de gestão de glosas

## Conformidade

- **CPC 47**: Receita de Contratos com Clientes
- **CPC 25**: Provisões e Reversões
- **RN ANS 443/2019**: Gestão de glosas
- **Regulação Tributária**: Reconhecimento de receita (IR/CSLL)

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** AI Swarm - Forensics Delegate Generation
