# RN - CloseEncounterDelegate

**ID:** RN-CLINICAL-001
**Camada:** Delegates (Clinical Workflow)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** CRITICAL
**BPMN Reference:** `${closeEncounterDelegate}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável por encerrar atendimentos clínicos com validação abrangente e finalização. Orquestra o fluxo completo de fechamento de atendimento, validando documentação, atualizando sistemas e disparando processos de cobrança.

### 1.2 Objetivo
- Validar completude da documentação clínica
- Verificar sumário de alta
- Confirmar prescrições e agendamentos de follow-up
- Atualizar status do atendimento no TASY ERP
- Disparar workflow de cobrança
- Arquivar documentos clínicos
- Enviar notificações de alta

### 1.3 Contexto no Fluxo de Negócio
Este delegate é executado ao final do atendimento clínico, antes de iniciar o processo de cobrança. É o ponto crítico de transição entre o cuidado clínico e o ciclo de receita, garantindo que toda documentação necessária está completa antes de gerar cobranças.

---

## 2. Regras de Negócio

### RN-CLINICAL-001.1: Validação de Documentação Completa
**Descrição:** Verifica se toda documentação clínica obrigatória está presente

**Condição:**
```java
DocumentationValidationResult docValidation =
    encounterClosureService.validateDocumentation(encounterId);
```

**Ação:**
- Se documentação incompleta: lança BpmnError `INCOMPLETE_DOCUMENTATION`
- Lista documentos faltantes em `validation_errors`
- Bloqueia fechamento do atendimento

**Documentação Obrigatória:**
- Nota de admissão (internação)
- Notas de evolução (mínimo 1)
- Sumário de alta
- Relatórios de exames laboratoriais (se solicitados)
- Laudos de imagem (se realizados)
- Nota operatória (casos cirúrgicos)
- Notas de consulta (se solicitadas)

---

### RN-CLINICAL-001.2: Validação de Sumário de Alta
**Descrição:** Confirma que o sumário de alta está completo com todos campos obrigatórios

**Condição:**
```java
boolean dischargeSummaryComplete =
    encounterClosureService.validateDischargeSummary(encounterId);
```

**Campos Obrigatórios:**
- Data de alta (`dischargeDate`)
- Motivo da alta (`dischargeReason`)
- Diagnóstico principal (`primaryDiagnosis`)

**Ação:**
- Se incompleto: lança BpmnError `INCOMPLETE_DISCHARGE_SUMMARY`
- Bloqueia fechamento do atendimento

---

### RN-CLINICAL-001.3: Verificação de Prescrições e Follow-up
**Descrição:** Verifica se prescrições foram emitidas ou consultas de retorno agendadas

**Condição:**
```java
PrescriptionValidationResult prescriptionValidation =
    encounterClosureService.validatePrescriptionsAndFollowUp(encounterId);
```

**Ação:**
- Se nenhum dos dois presente: registra WARNING (não bloqueia)
- Alguns atendimentos não requerem prescrições nem follow-up
- Define variáveis:
  - `prescriptions_issued`: true/false
  - `followup_scheduled`: true/false

---

### RN-CLINICAL-001.4: Atualização de Status no TASY
**Descrição:** Atualiza status do atendimento para CLOSED no sistema TASY ERP

**Ação:**
```java
TasyEncounterDTO updatedEncounter =
    encounterClosureService.updateEncounterStatus(encounterId, "CLOSED");
```

**Integração:**
- Sistema: TASY ERP
- Endpoint: `PUT /encounters/{id}/status`
- Status: `CLOSED`

---

### RN-CLINICAL-001.5: Arquivamento de Documentos
**Descrição:** Arquiva todos documentos clínicos do atendimento

**Ação:**
```java
int archivedCount = encounterClosureService.archiveDocuments(encounterId);
```

**Resultado:**
- Retorna contagem de documentos arquivados
- Define variável `documents_archived`

---

### RN-CLINICAL-001.6: Disparo de Workflow de Cobrança
**Descrição:** Sinaliza que atendimento está pronto para processo de cobrança

**Variáveis Definidas:**
- `encounter_closed`: true
- `ready_for_billing`: true ← **GATILHO CRÍTICO**
- `encounter_closure_timestamp`: timestamp atual

**Impacto:** Esta variável dispara o subprocess de cobrança (SUB_04_Faturamento)

---

### RN-CLINICAL-001.7: Notificações de Alta
**Descrição:** Define variáveis para envio de notificações de alta

**Variáveis de Notificação:**
- `notification_type`: "DISCHARGE"
- `patient_id`: ID do paciente
- `attending_physician_id`: ID do médico
- `discharge_date`: data da alta

**Destinatários:**
- Paciente
- Médico assistente
- Equipe de cobrança

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `encounter_id` | String | ID do atendimento | "ENC-12345" |

### 3.2 Variáveis de Saída
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `encounter_closed` | Boolean | Atendimento encerrado com sucesso | PROCESS |
| `encounter_closure_timestamp` | String | Timestamp do fechamento | PROCESS |
| `ready_for_billing` | Boolean | **Pronto para cobrança** | PROCESS |
| `documents_archived` | Integer | Quantidade de documentos arquivados | PROCESS |
| `prescriptions_issued` | Boolean | Prescrições emitidas | PROCESS |
| `followup_scheduled` | Boolean | Retorno agendado | PROCESS |
| `notification_type` | String | Tipo de notificação | PROCESS |
| `patient_id` | String | ID do paciente | PROCESS |
| `attending_physician_id` | String | ID do médico | PROCESS |
| `discharge_date` | String | Data da alta | PROCESS |
| `primary_diagnosis` | String | Diagnóstico principal | PROCESS |
| `discharge_reason` | String | Motivo da alta | PROCESS |
| `encounter_type` | String | Tipo de atendimento | PROCESS |
| `payer_id` | String | ID do pagador | PROCESS |

### 3.3 Variáveis de Erro
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `validation_errors` | List<String> | Documentos faltantes |
| `discharge_summary_complete` | Boolean | Status do sumário de alta |
| `encounter_closure_error` | String | Mensagem de erro |

---

## 4. Integrações

### 4.1 EncounterClosureService
**Métodos:**
- `validateDocumentation(encounterId)`: Valida documentação completa
- `validateDischargeSummary(encounterId)`: Valida sumário de alta
- `validatePrescriptionsAndFollowUp(encounterId)`: Verifica prescrições/follow-up
- `updateEncounterStatus(encounterId, status)`: Atualiza status no TASY
- `archiveDocuments(encounterId)`: Arquiva documentos

---

## 5. Tratamento de Erros

### 5.1 BpmnErrors
| Código | Descrição | Ação |
|--------|-----------|------|
| `INCOMPLETE_DOCUMENTATION` | Documentação obrigatória faltante | Retornar para documentação clínica |
| `INCOMPLETE_DISCHARGE_SUMMARY` | Sumário de alta incompleto | Solicitar preenchimento |

### 5.2 Exceções Técnicas
- Log de erro completo
- Define `encounter_closed = false`
- Define `encounter_closure_error` com mensagem

---

## 6. Conformidade e Auditoria

### 6.1 Regulamentações
- **CFM:** Resolução sobre prontuário eletrônico
- **LGPD:** Arquivamento seguro de dados médicos
- **ANS:** Completude de documentação para cobrança

### 6.2 Logs de Auditoria
```
INFO: Executing CloseEncounterDelegate - Process: {id}, Activity: {activity}
INFO: Starting encounter closure - EncounterId: {id}
INFO: Documentation validation passed - EncounterId: {id}
INFO: Discharge summary validation passed - EncounterId: {id}
INFO: Encounter status updated in TASY - EncounterId: {id}, Status: CLOSED
INFO: Clinical documents archived - EncounterId: {id}, Count: {count}
INFO: Encounter closure completed successfully - EncounterId: {id}, ReadyForBilling: true
```

---

## 7. Dependências

### 7.1 Serviços
- `EncounterClosureService`: Lógica de fechamento de atendimento
- `TasyClient`: Integração com TASY ERP

### 7.2 Delegates Relacionados
- `FinalizarAtendimentoDelegate`: Finalização prévia
- `CompletenessCheckDelegate`: Verificação de completude
- (Próximo) Delegates de cobrança disparados por `ready_for_billing`

---

## 8. Requisitos Não-Funcionais

### 8.1 Performance
- Tempo médio de execução: < 5 segundos
- Timeout: 30 segundos

### 8.2 Idempotência
- **requiresIdempotency()**: `true`
- Múltiplas execuções não criam duplicatas

### 8.3 Disponibilidade
- Dependência crítica: TASY ERP (uptime > 99.5%)
- Estratégia de fallback: Fila de retry se TASY indisponível

---

## 9. Cenários de Teste

### 9.1 Cenário: Fechamento com Sucesso
**Dado:** Atendimento com documentação completa
**Quando:** CloseEncounterDelegate executado
**Então:**
- `encounter_closed = true`
- `ready_for_billing = true`
- Status TASY = CLOSED
- Documentos arquivados

### 9.2 Cenário: Documentação Incompleta
**Dado:** Atendimento sem sumário de alta
**Quando:** CloseEncounterDelegate executado
**Então:**
- BpmnError `INCOMPLETE_DISCHARGE_SUMMARY`
- `encounter_closed = false`
- Processo retorna para documentação

### 9.3 Cenário: Sem Prescrições (Permitido)
**Dado:** Atendimento sem prescrições nem follow-up
**Quando:** CloseEncounterDelegate executado
**Então:**
- WARNING registrado (não bloqueia)
- `prescriptions_issued = false`
- `followup_scheduled = false`
- Fechamento continua

---

## 10. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/CloseEncounterDelegate.java`

**Serviços:**
- `/src/main/java/com/hospital/revenuecycle/services/EncounterClosureService.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/CloseEncounterDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
