# RN-EscalateDelegate

**Camunda Delegate:** `escalateDelegate`
**Categoria:** Gestão de Glosas (Negações) - Escalação
**Arquivo:** `EscalateDelegate.java`

## Descrição

Escalona glosas complexas para especialistas. Este delegate gerencia o processo de escalação de negações que requerem expertise especializada, atribuindo casos para analistas seniores, especialistas clínicos, assessoria jurídica ou gestão, conforme o nível de escalação necessário.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaId` | String | Sim | Identificador único da glosa |
| `escalationLevel` | String | Não | Nível de escalação (padrão: SENIOR_ANALYST) |
| `escalationReason` | String | Não | Motivo da escalação |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `escalationId` | String | Identificador único da escalação |
| `assignedSpecialist` | String | ID do especialista atribuído |
| `escalationDate` | LocalDateTime | Data/hora da escalação |
| `glosaStatus` | String | Novo status da glosa (ESCALATED) |
| `priority` | String | Prioridade atualizada (HIGH) |

## Regras de Negócio

### Níveis de Escalação

| Nível | Especialista Atribuído | Quando Usar |
|-------|------------------------|-------------|
| `SENIOR_ANALYST` | Analista Sênior de Gestão de Glosas | Glosas complexas que requerem experiência avançada |
| `CLINICAL_SPECIALIST` | Especialista Clínico / Physician Advisor | Negações de necessidade médica ou documentação clínica |
| `LEGAL_COUNSEL` | Assessoria Jurídica / Advogado de Saúde | Glosas que podem resultar em litígio |
| `MANAGEMENT` | Diretor de Ciclo de Receita | Glosas de alto valor ou impacto estratégico |

### Matriz de Atribuição de Especialistas

```java
switch (escalationLevel) {
    case "SENIOR_ANALYST":
        specialist = "ANALYST-SENIOR-001";
        break;
    case "CLINICAL_SPECIALIST":
        specialist = "CLINICAL-SPEC-001";
        break;
    case "LEGAL_COUNSEL":
        specialist = "LEGAL-001";
        break;
    case "MANAGEMENT":
        specialist = "MGR-RC-001";
        break;
    default:
        specialist = "ANALYST-SENIOR-001";
}
```

**Nota:** Em ambiente de produção, a atribuição seria dinâmica baseada em:
- Disponibilidade do especialista
- Carga de trabalho atual
- Especialização por tipo de glosa
- Round-robin ou load balancing

### Formato de IDs de Escalação

```
ESC-{glosaId}-{timestamp}
```

**Exemplo:** `ESC-GLOSA-12345-1736685296000`

### Atualização de Prioridade

Todas as glosas escalonadas recebem prioridade **HIGH** automaticamente.

### Motivo de Escalação Padrão

Se não fornecido: `"Complex denial requiring specialist review"`

## Integrações

### Banco de Dados

```sql
-- Criação do registro de escalação
INSERT INTO glosa_escalations (
  escalation_id,
  glosa_id,
  escalation_level,
  reason,
  status,
  created_at
) VALUES (?, ?, ?, ?, 'PENDING', NOW())

-- Atualização de prioridade da glosa
UPDATE glosas
SET priority = 'HIGH'
WHERE glosa_id = ?

-- Atualização de status da glosa
UPDATE glosas
SET status = 'ESCALATED',
    escalated = true,
    escalation_date = NOW()
WHERE glosa_id = ?
```

### Sistema de Workflow
- **Criação de Tarefa**: Atribui tarefa ao especialista no sistema de workflow
- **Notificação de E-mail**: Envia e-mail com detalhes da escalação
- **SMS**: Para escalações urgentes (MANAGEMENT, LEGAL_COUNSEL)

### Briefing de Escalação

Prepara documentação abrangente incluindo:
- Histórico completo da glosa e timeline
- Tentativas de recurso anteriores
- Resumo de documentação clínica
- Ações recomendadas
- Contexto financeiro e contratual

## Notificações

### Para o Especialista Atribuído

**Canal:** E-mail + Sistema de Workflow + SMS (casos urgentes)
**Conteúdo:**
- ID da escalação
- ID da glosa
- Nível de escalação
- Motivo da escalação
- Link para briefing completo
- Prazo de resposta

### Para a Equipe Originadora

**Canal:** Sistema de Workflow + E-mail
**Conteúdo:**
- Confirmação de escalação
- Especialista atribuído
- Timeline esperado

## Exemplo de Fluxo

```
1. Receber solicitação de escalação:
   - glosaId: GLOSA-12345
   - escalationLevel: CLINICAL_SPECIALIST
   - reason: "Medical necessity documentation required"

2. Gerar ID de escalação: ESC-GLOSA-12345-1736685296000

3. Criar registro de escalação no banco de dados

4. Atribuir especialista: CLINICAL-SPEC-001

5. Atualizar glosa:
   - priority = HIGH
   - status = ESCALATED

6. Preparar briefing de escalação

7. Notificar especialista:
   - E-mail prioritário
   - Tarefa no workflow
   - SMS se urgente

8. Notificar equipe originadora

9. Retornar:
   - escalationId = ESC-GLOSA-12345-1736685296000
   - assignedSpecialist = CLINICAL-SPEC-001
   - glosaStatus = ESCALATED
```

## Exceções e Erros

**Tratamento:** Não lança exceções BPMN - propaga exceções runtime

Em caso de falha:
```java
throw new RuntimeException("Failed to escalate glosa " + glosaId, e);
```

**Motivos de Falha:**
- Erro na criação do registro de escalação
- Falha na atribuição de especialista
- Erro na atualização do status da glosa
- Falha no envio de notificações

## Briefing de Escalação

### Conteúdo do Briefing

1. **Histórico da Glosa**
   - Data de identificação
   - Valor original
   - Tentativas de resolução anteriores
   - Timeline de eventos

2. **Documentação Clínica**
   - Resumo de procedimentos realizados
   - Diagnósticos principais
   - Documentos disponíveis
   - Lacunas de documentação

3. **Análise Anterior**
   - Estratégias tentadas
   - Resultados obtidos
   - Obstáculos identificados

4. **Ações Recomendadas**
   - Próximos passos sugeridos
   - Documentação adicional necessária
   - Contatos relevantes

5. **Contexto Financeiro**
   - Valor em risco
   - Impacto no budget
   - Provisões criadas

## Auditoria e Logging

**Nível de Log:** INFO/DEBUG/ERROR
**Eventos Auditados:**
- Criação de escalação
- Nível e motivo de escalação
- Especialista atribuído
- Atualização de status e prioridade
- Notificações enviadas
- Erros no processo

## KPIs e Métricas

- **Taxa de Escalação**: % de glosas escalonadas do total
- **Distribuição por Nível**: Contagem por tipo de escalação
- **Tempo Médio de Resolução**: Após escalação
- **Taxa de Sucesso Pós-Escalação**: % de glosas recuperadas
- **SLA de Resposta**: Tempo até primeira ação do especialista

## Considerações Importantes

1. **Timing**: Escalonamento no momento certo é crítico - nem muito cedo (custos desnecessários) nem muito tarde (perda de prazos)

2. **Especialização**: Atribuir ao especialista correto aumenta taxa de sucesso

3. **Comunicação**: Briefing completo reduz tempo de ramp-up do especialista

4. **Priorização**: Escalações automáticas recebem HIGH priority para garantir atenção

5. **Tracking**: Todas as escalações devem ser rastreadas para análise de eficácia

## Critérios para Escalação

### Situações que Justificam Escalação

- **Alto Valor**: Glosas acima de threshold definido (ex: R$ 10.000)
- **Complexidade Clínica**: Negações de necessidade médica
- **Questões Contratuais**: Disputas de interpretação de contrato
- **Múltiplas Tentativas Falhas**: Após 2+ recursos sem sucesso
- **Prazo Crítico**: Próximo ao vencimento de prazo de recurso
- **Risco Jurídico**: Possibilidade de litígio

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** AI Swarm - Forensics Delegate Generation
