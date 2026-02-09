# RN-LegalReferralDelegate

**Camunda Delegate:** `legalReferralDelegate`
**Categoria:** Gestão de Glosas (Negações) - Encaminhamento Jurídico
**Arquivo:** `LegalReferralDelegate.java`

## Descrição

Encaminha glosas para o departamento jurídico quando recursos administrativos foram esgotados ou quando há questões legais envolvidas. Este delegate gerencia o processo completo de referência legal, incluindo preparação de documentação, notificações e tracking de casos.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaId` | String | Sim | Identificador único da glosa |
| `glosaAmount` | Double | Sim | Valor da glosa em disputa |
| `glosaReason` | String | Não | Motivo original da glosa |
| `escalationReason` | String | Não | Motivo do encaminhamento jurídico (padrão fornecido) |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `legalReferralId` | String | Identificador único do encaminhamento jurídico |
| `legalReferralDate` | LocalDateTime | Data/hora do encaminhamento |
| `glosaStatus` | String | Novo status da glosa (LEGAL_REVIEW) |
| `referralCompleted` | Boolean | Confirmação de encaminhamento completo |

## Regras de Negócio

### Quando Encaminhar para Jurídico

Glosas devem ser encaminhadas ao jurídico quando:
1. **Recursos Esgotados**: Todos os recursos administrativos foram negados
2. **Alto Valor**: Glosas acima de threshold crítico (ex: > R$ 50.000)
3. **Questões Contratuais**: Disputa sobre interpretação de cláusulas
4. **Má-Fé Aparente**: Suspeita de negação indevida sistemática
5. **Prazo Expirado**: Operadora não respondeu dentro do prazo legal
6. **Precedente Importante**: Caso pode estabelecer precedente

### Formato de IDs de Referência

```
LEGAL-{glosaId}-{timestamp}
```

**Exemplo:** `LEGAL-GLOSA-12345-1736685296000`

### Motivo Padrão de Encaminhamento

Se não fornecido: `"High-value glosa requiring legal intervention"`

### Status da Glosa

Após encaminhamento: `LEGAL_REVIEW`

## Integrações

### Banco de Dados

```sql
-- Criação do registro de referência jurídica
INSERT INTO legal_referrals (
  referral_id,
  glosa_id,
  amount,
  reason,
  status,
  created_at
) VALUES (?, ?, ?, ?, 'PENDING_REVIEW', NOW())

-- Atualização do status da glosa
UPDATE glosas
SET status = 'LEGAL_REVIEW',
    legal_referral_date = NOW()
WHERE glosa_id = ?

-- Criação do registro de tracking
INSERT INTO legal_case_tracking (
  referral_id,
  glosa_id,
  status,
  assigned_attorney,
  created_at
) VALUES (?, ?, 'NEW', NULL, NOW())
```

### Gestão de Documentos

**Sistema:** Document Management System (DMS)
**Ação:** Coleta e organiza documentação legal completa

**Documentos Incluídos:**
- Documentos originais da cobrança
- Correspondência de negação da operadora
- Histórico completo de recursos
- Documentação clínica relevante
- Termos contratuais aplicáveis
- Comunicações com a operadora
- Análises técnicas anteriores

### Notificações

#### Para Departamento Jurídico

**Canais:**
- E-mail prioritário
- Integração com sistema de gerenciamento de casos
- Evento Kafka para trigger de workflow jurídico

**Conteúdo:**
```json
{
  "eventType": "LEGAL_REFERRAL_CREATED",
  "referralId": "LEGAL-GLOSA-12345-1736685296000",
  "glosaId": "GLOSA-12345",
  "amount": 75000.00,
  "priority": "HIGH",
  "reason": "High-value glosa requiring legal intervention",
  "documentsPackageId": "DOC-PKG-12345",
  "timestamp": "2025-01-12T10:30:00Z"
}
```

#### Para Equipe de Glosas

**Canal:** Sistema de Workflow + E-mail
**Conteúdo:**
- Confirmação de encaminhamento
- ID da referência
- Ação: `ESCALATED_TO_LEGAL`

## Pacote de Documentação Jurídica

### Estrutura do Pacote

1. **Resumo Executivo**
   - Valor em disputa
   - Cronologia dos eventos
   - Ações já tomadas
   - Recomendação de estratégia

2. **Documentação da Cobrança**
   - Guia TISS original
   - Demonstrativo de pagamento
   - Nota fiscal
   - Comprovantes de entrega

3. **Correspondências**
   - Carta de negação original
   - Recursos administrativos enviados
   - Respostas da operadora
   - Comunicações telefônicas (se registradas)

4. **Documentação Clínica**
   - Prontuário médico
   - Laudos e exames
   - Evolução clínica
   - Justificativas de necessidade médica

5. **Documentação Contratual**
   - Contrato com a operadora
   - Tabela de preços
   - Termos aplicáveis
   - Aditivos contratuais

6. **Análises Técnicas**
   - Análise de conformidade TISS
   - Parecer de auditoria interna
   - Análise de compatibilidade CID x procedimento
   - Comparação com casos similares

## Exemplo de Fluxo

```
1. Receber solicitação de encaminhamento jurídico:
   - glosaId: GLOSA-12345
   - glosaAmount: R$ 75.000,00
   - glosaReason: "Negação de necessidade médica"
   - escalationReason: "Operadora manteve negação após 3 recursos"

2. Gerar ID de referência: LEGAL-GLOSA-12345-1736685296000

3. Criar registro de referência jurídica:
   - status: PENDING_REVIEW
   - amount: 75000.00

4. Preparar pacote de documentação:
   - Coletar todos os documentos listados acima
   - Organizar em estrutura padronizada
   - Armazenar no DMS

5. Atualizar glosa:
   - status = LEGAL_REVIEW
   - legal_referral_date = NOW()

6. Notificar departamento jurídico:
   - E-mail prioritário
   - Integração com sistema de casos
   - Kafka event

7. Notificar equipe de glosas:
   - Confirmação de escalação

8. Criar registro de tracking:
   - status: NEW
   - assigned_attorney: NULL (a ser atribuído)

9. Retornar:
   - legalReferralId
   - legalReferralDate
   - glosaStatus = LEGAL_REVIEW
   - referralCompleted = true
```

## Case Tracking

### Status do Caso Jurídico

| Status | Descrição |
|--------|-----------|
| `NEW` | Caso recém-criado, aguardando análise |
| `UNDER_REVIEW` | Em análise pelo departamento jurídico |
| `ASSIGNED` | Atribuído a advogado específico |
| `IN_NEGOTIATION` | Em negociação com a operadora |
| `LITIGATION_FILED` | Ação judicial protocolada |
| `SETTLED` | Acordo extrajudicial alcançado |
| `WON` | Ganho em tribunal |
| `LOST` | Perda em tribunal |
| `WITHDRAWN` | Caso retirado |

### Atribuição de Advogado

**Critérios:**
- Especialização (direito da saúde)
- Carga de trabalho atual
- Experiência com casos similares
- Histórico de sucesso

## Exceções e Erros

**Tratamento:** Não lança exceções BPMN - propaga exceções runtime

Em caso de falha:
```java
throw new RuntimeException("Failed to create legal referral for glosa " + glosaId, e);
```

**Motivos de Falha:**
- Erro na criação do registro de referência
- Falha na preparação da documentação
- Erro na atualização do status
- Falha no envio de notificações

## Auditoria e Logging

**Nível de Log:** INFO/DEBUG/ERROR
**Eventos Auditados:**
- Criação de referência jurídica
- Valor em disputa
- Preparação do pacote de documentos
- Notificações enviadas
- Criação de tracking
- Erros no processo

## KPIs e Métricas

### Operacionais
- **Total de Encaminhamentos**: Por período
- **Tempo Médio até Encaminhamento**: Da identificação da glosa
- **Taxa de Encaminhamento**: % de glosas que vão para jurídico

### Financeiras
- **Valor em Disputa**: Total de glosas sob revisão legal
- **Custo Legal**: Estimativa de custos processuais
- **Valor Recuperado**: Após intervenção jurídica

### Efetividade
- **Taxa de Sucesso**: % de casos ganhos
- **Valor de Acordos**: Recuperação via acordo
- **Tempo Médio de Resolução**: Do encaminhamento até decisão

## Acordos Extrajudiciais

Departamento jurídico pode negociar acordos:
- **Acordo Parcial**: Operadora paga parte do valor em disputa
- **Acordo Total**: Operadora concorda em pagar integralmente
- **Acordo de Padrão**: Resolução que afeta casos futuros similares

**Vantagens:**
- Mais rápido que litígio
- Menor custo
- Mantém relacionamento comercial
- Reduz incerteza

## Considerações Importantes

1. **Custos**: Litígio é caro - avaliar custo-benefício antes de processar

2. **Tempo**: Processos judiciais podem levar anos

3. **Relacionamento**: Ações legais podem prejudicar relacionamento comercial com operadora

4. **Evidências**: Qualidade da documentação é crítica para sucesso

5. **Precedentes**: Casos ganhos estabelecem precedentes úteis para futuras disputas

6. **Compliance**: Departamento jurídico também avalia conformidade do hospital

## Aspectos Legais

### Legislação Aplicável

- **Lei 9.656/1998**: Planos de saúde
- **RN ANS 439/2018**: Preços e negações
- **Código Civil**: Contratos
- **CDC**: Relações de consumo (quando aplicável)

### Prazos Legais

- **Recurso Administrativo**: Geralmente 30 dias da negação
- **Ação Judicial**: Prazo prescricional aplicável
- **Prescrição**: Geralmente 3 anos (verificar legislação específica)

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** AI Swarm - Forensics Delegate Generation
