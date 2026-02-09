# RN-GLOSA-004: Escalação de Glosas Complexas para Especialistas

## I. Identificação da Regra

**Código**: RN-GLOSA-004
**Nome**: Escalação de Glosas Complexas para Especialistas
**Versão**: 1.0.0
**Módulo**: Gestão de Glosas
**Processo de Negócio**: Escalação e Análise Especializada
**Data de Criação**: 2026-01-12
**Última Atualização**: 2026-01-12
**Autor**: Equipe de Revenue Cycle

## II. Definição e Propósito

### Definição
Define o processo sistemático de escalação de glosas complexas ou de alto valor para analistas especializados, incluindo atribuição baseada em expertise, preparação de briefing e rastreamento de casos escalados.

### Propósito
Garantir que glosas complexas recebam atenção especializada apropriada, maximizando chances de recuperação através de análise técnica avançada e expertise específica de domínio.

### Escopo
Aplica-se a glosas que excedem capacidade de resolução de primeira linha, incluindo casos de alta complexidade técnica, alto valor financeiro ou necessidade de expertise clínica/jurídica.

## III. Descrição da Lógica de Negócio

### Fluxo Principal

1. **Identificação de Necessidade de Escalação**
   - Sistema recebe indicação de glosa para escalação
   - Sistema captura nível de escalação desejado
   - Sistema registra motivo da escalação

2. **Geração de Identificador de Escalação**
   - Sistema cria ID único: `ESC-{glosaId}-{timestamp}`
   - Sistema garante rastreabilidade através de timestamp

3. **Criação de Registro de Escalação**
   - Sistema insere registro na tabela `glosa_escalations`
   - Sistema registra: ID, glosa, nível, motivo, status PENDING

4. **Atribuição de Especialista**
   - Sistema seleciona especialista baseado em nível de escalação:
     - SENIOR_ANALYST → Analista sênior experiente
     - CLINICAL_SPECIALIST → Physician advisor ou especialista clínico
     - LEGAL_COUNSEL → Advogado especializado em saúde
     - MANAGEMENT → Diretor de revenue cycle
   - Sistema consulta disponibilidade e carga de trabalho

5. **Atualização de Prioridade da Glosa**
   - Sistema eleva prioridade para "HIGH" automaticamente
   - Sistema justifica elevação por escalação

6. **Atualização de Status da Glosa**
   - Sistema marca glosa como "ESCALATED"
   - Sistema registra data de escalação
   - Sistema define flag `escalated = true`

7. **Preparação de Briefing de Escalação**
   - Sistema compila histórico completo da glosa
   - Sistema inclui tentativas prévias de recurso
   - Sistema anexa documentação clínica relevante
   - Sistema adiciona recomendações de ação

8. **Notificação do Especialista Atribuído**
   - Sistema envia email de alta prioridade
   - Sistema cria tarefa no sistema de workflow
   - Sistema pode enviar SMS para escalações urgentes

9. **Notificação da Equipe Escalante**
   - Sistema confirma escalação bem-sucedida
   - Sistema informa especialista atribuído
   - Sistema define expectativas de tempo de resposta

### Regras de Decisão

**RD-001: Seleção de Especialista por Nível**
```
especialista = CASO nivel_escalação
  QUANDO "SENIOR_ANALYST"
    ENTÃO "ANALYST-SENIOR-001"
  QUANDO "CLINICAL_SPECIALIST"
    ENTÃO "CLINICAL-SPEC-001"
  QUANDO "LEGAL_COUNSEL"
    ENTÃO "LEGAL-001"
  QUANDO "MANAGEMENT"
    ENTÃO "MGR-RC-001"
  SENÃO "ANALYST-SENIOR-001"  // Padrão
FIM CASO
```

**RD-002: Critérios para Escalação**
- Valor da glosa > R$ 10.000,00 → Escalação automática
- Negação médica complexa → CLINICAL_SPECIALIST
- Questão contratual/jurídica → LEGAL_COUNSEL
- Falha em 2+ tentativas de recurso → SENIOR_ANALYST

**RD-003: Tempo de Resposta Esperado**
- MANAGEMENT: 4 horas
- LEGAL_COUNSEL: 24 horas
- CLINICAL_SPECIALIST: 48 horas
- SENIOR_ANALYST: 72 horas

## IV. Variáveis e Parâmetros

### Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| glosaId | String | Sim | Identificador único da glosa |
| escalationLevel | String | Não | Nível de escalação (padrão: SENIOR_ANALYST) |
| escalationReason | String | Não | Motivo detalhado da escalação |

### Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| escalationId | String | Identificador único da escalação |
| assignedSpecialist | String | ID do especialista atribuído |
| escalationDate | LocalDateTime | Data/hora da escalação |
| glosaStatus | String | Novo status da glosa (ESCALATED) |
| priority | String | Nova prioridade da glosa (HIGH) |

### Valores Padrão
| Variável | Valor Padrão |
|----------|--------------|
| escalationLevel | SENIOR_ANALYST |
| escalationReason | "Complex denial requiring specialist review" |

## V. Cálculos e Fórmulas

### Geração de ID de Escalação
```
escalation_id = "ESC-" + glosa_id + "-" + UNIX_TIMESTAMP_MILLIS()

Exemplo: "ESC-GLOSA-456-1736421335000"
```

### Cálculo de SLA por Nível
```
tempo_resposta_esperado = CASO nivel
  QUANDO "MANAGEMENT" ENTÃO 4 horas
  QUANDO "LEGAL_COUNSEL" ENTÃO 24 horas
  QUANDO "CLINICAL_SPECIALIST" ENTÃO 48 horas
  QUANDO "SENIOR_ANALYST" ENTÃO 72 horas
FIM CASO

data_limite = data_escalacao + tempo_resposta_esperado
```

## VI. Validações e Restrições

### Validações de Entrada
- **VLD-001**: ID da glosa deve existir no sistema
- **VLD-002**: Nível de escalação deve ser um dos valores permitidos
- **VLD-003**: Glosa não pode estar já em status RESOLVED ou CLOSED

### Restrições de Negócio
- **RST-001**: Glosa só pode ser escalada uma vez (re-escalação requer processo distinto)
- **RST-002**: Escalação sempre eleva prioridade para HIGH
- **RST-003**: Especialista atribuído deve ter capacidade disponível

### Regras de Autorização
- **AUTH-001**: Apenas roles ANALYST, SUPERVISOR, MANAGER podem escalar
- **AUTH-002**: Escalação para LEGAL_COUNSEL requer aprovação de SUPERVISOR
- **AUTH-003**: Escalação para MANAGEMENT requer justificativa documentada

## VII. Exceções e Tratamento de Erros

### Cenários de Exceção

**EXC-001: Especialista Não Disponível**
- Sistema busca próximo especialista disponível no pool
- Sistema registra tentativa de atribuição alternativa
- Sistema notifica supervisor se nenhum disponível

**EXC-002: Falha em Notificação**
- Sistema tenta email como canal primário
- Sistema escala para SMS se email falhar
- Sistema cria tarefa manual no sistema como fallback

**EXC-003: Glosa Já Escalada**
- Sistema verifica flag `escalated` antes de processar
- Sistema retorna informação de escalação existente
- Sistema não cria duplicata

**EXC-004: Nível de Escalação Inválido**
- Sistema usa valor padrão SENIOR_ANALYST
- Sistema registra warning em log
- Sistema continua processamento

## VIII. Integrações de Sistemas

### Sistemas Integrados
| Sistema | Tipo | Operações |
|---------|------|-----------|
| Sistema de Workflow | Bidirecional | Criação de tarefas, atribuição de usuários |
| Sistema de Email | Saída | Envio de notificações de escalação |
| Sistema de SMS | Saída | Notificações urgentes (opcional) |
| Sistema de Gerenciamento de Recursos | Consulta | Verificação de disponibilidade de especialistas |

### Estrutura de Notificação Email
```yaml
To: specialist_email
Subject: [URGENT] Glosa Escalation - {glosaId}
Priority: High

Body:
  Escalation ID: {escalationId}
  Glosa ID: {glosaId}
  Amount: {glosaAmount}
  Escalation Level: {escalationLevel}
  Reason: {escalationReason}
  Expected Response Time: {slaHours} hours
  Assigned Date: {escalationDate}

  Link to Briefing: {briefingUrl}
  Link to Glosa Details: {glosaDetailsUrl}
```

### Criação de Tarefa no Workflow
```json
{
  "taskType": "GlosaEscalationReview",
  "taskId": "{escalationId}",
  "assignee": "{specialistId}",
  "priority": "HIGH",
  "dueDate": "{calculatedDueDate}",
  "variables": {
    "glosaId": "{glosaId}",
    "escalationLevel": "{level}",
    "escalationReason": "{reason}",
    "briefingUrl": "{url}"
  }
}
```

## IX. Indicadores de Performance (KPIs)

### KPIs Monitorados
| KPI | Métrica | Meta | Descrição |
|-----|---------|------|-----------|
| Taxa de Resolução Pós-Escalação | % | 80% | Percentual de glosas resolvidas após escalação |
| Tempo Médio de Resposta | Horas | Variável por nível | Tempo desde escalação até primeira ação |
| Taxa de Aderência a SLA | % | 95% | Percentual de escalações respondidas no prazo |
| Taxa de Re-escalação | % | < 5% | Percentual que requer nova escalação |

### KPIs de Especialista
| KPI | Descrição |
|-----|-----------|
| Carga de Trabalho | Número de escalações ativas por especialista |
| Taxa de Sucesso | Percentual de recuperação por especialista |
| Tempo Médio de Resolução | Dias desde escalação até resolução |

## X. Conformidade Regulatória

### Normas Aplicáveis

**ANS - Resolução Normativa 395/2016**
- Art. 19: Escalonamento de recursos complexos
- Conformidade: Sistema garante escalação para expertise adequada

**CFC - Código de Ética Profissional**
- Sigilo e confidencialidade em casos clínicos
- Conformidade: Sistema restringe acesso a briefing apenas a atribuídos

**LGPD - Lei 13.709/2018**
- Art. 37: Compartilhamento apenas com necessidade legítima
- Conformidade: Sistema compartilha dados apenas com especialista atribuído

## XI. Notas de Migração

### Migração Camunda 7 → Camunda 8

**Complexidade de Migração**: 5/10 (Média)

**Impactos Identificados**:

1. **User Tasks e Atribuição**
   - Camunda 7: Integração com sistema de identidade via Spring Security
   - Camunda 8: Zeebe usa Tasklist próprio com autorização externa
   - Ação: Configurar Tasklist Zeebe com sistema de identidade corporativo

2. **Notificações Assíncronas**
   - Camunda 7: Código inline para email/SMS
   - Camunda 8: Usar conectores externos de notificação
   - Ação: Implementar workers para email e SMS

3. **SLA e Due Dates**
   - Camunda 7: Calculado programaticamente
   - Camunda 8: Suporte nativo a timers e deadlines
   - Ação: Configurar boundary events para SLA

4. **Preparação de Briefing**
   - Camunda 7: Método stub sem implementação real
   - Camunda 8: Implementar como serviço externo
   - Ação: Criar microserviço de agregação de dados

**Esforço Estimado**: 12-16 horas
- Configuração de Tasklist: 4h
- Implementação de conectores: 4h
- Configuração de timers SLA: 2h
- Serviço de briefing: 4h
- Testes: 2h

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Nome**: Escalação de Glosas (Glosa Escalation)

### Agregados
- **Agregado Principal**: Escalação
- **Entidades**:
  - Escalação (raiz)
  - Atribuição de Especialista
  - Briefing de Escalação
  - SLA de Resposta
- **Value Objects**:
  - Nível de Escalação (enum)
  - Status de Escalação
  - Tempo de Resposta

### Eventos de Domínio
| Evento | Descrição | Dados |
|--------|-----------|-------|
| GlosaEscalada | Glosa foi escalada para especialista | escalationId, glosaId, level, specialist, timestamp |
| EspecialistaAtribuido | Especialista foi atribuído à escalação | escalationId, specialistId, expectedResponseTime |
| PrioridadeElevada | Prioridade da glosa foi elevada | glosaId, newPriority, reason |
| SLAViolado | Tempo de resposta excedeu SLA | escalationId, slaDeadline, currentTime |
| EscalacaoResolvida | Especialista resolveu escalação | escalationId, resolution, resolutionDate |

### Linguagem Ubíqua
- **Escalação**: Transferência de glosa para nível superior de expertise
- **Especialista**: Profissional com conhecimento técnico específico
- **Briefing**: Compilação de informações relevantes para análise
- **SLA**: Acordo de nível de serviço para tempo de resposta
- **Re-escalação**: Nova escalação de caso já escalado previamente

## XIII. Metadados Técnicos

### Informações de Implementação
| Atributo | Valor |
|----------|-------|
| Classe Java | `EscalateDelegate` |
| Bean Spring | `escalateDelegate` |
| Camunda Task Type | Service Task (JavaDelegate) |
| Idempotência | Não explícita (recomendado adicionar) |
| Escopo de Variáveis | PROCESS |

### Estatísticas de Código
| Métrica | Valor |
|---------|-------|
| Linhas de Código | 161 |
| Complexidade Ciclomática | 4/10 (Baixa) |
| Métodos Públicos | 2 |
| Métodos Privados | 7 |
| Cobertura de Testes | 70% (estimado) |

### Performance
| Métrica | Valor Esperado | Valor Crítico |
|---------|----------------|---------------|
| Tempo de Execução | 150-400ms | > 1s |
| Uso de Memória | < 25MB | > 100MB |
| Taxa de Sucesso | > 98% | < 95% |
| Throughput | 50 escalações/min | < 10 escalações/min |

### Dependências Técnicas
- **Spring Framework**: Injeção de dependências
- **Camunda BPM 7.x**: Engine de workflow
- **Lombok**: Geração de código boilerplate
- **SLF4J**: Logging estruturado
- **Email Service** (futuro): Envio de notificações
- **SMS Gateway** (futuro): Notificações urgentes

### Tags de Busca
`escalação`, `especialista`, `análise-avançada`, `priorização`, `SLA`, `briefing`, `clinical-specialist`, `legal-counsel`, `senior-analyst`, `expert-review`

---

**Próxima Revisão**: 2026-04-12
**Responsável pela Manutenção**: Equipe de Revenue Cycle
**Criticidade**: MÉDIA-ALTA
