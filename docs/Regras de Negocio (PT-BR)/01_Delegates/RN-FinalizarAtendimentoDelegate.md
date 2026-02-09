# RN - FinalizarAtendimentoDelegate

**ID:** RN-CLINICAL-004
**Camada:** Delegates (Clinical Finalization)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** CRITICAL
**BPMN Reference:** `${finalizarAtendimentoDelegate}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável por finalizar atendimentos clínicos com validação abrangente antes de disparar processos de cobrança e codificação. Orquestra validações de exames laboratoriais (LIS), laudos de imagem (PACS) e sumário de alta, atualizando o status do atendimento para COMPLETED no TASY ERP.

### 1.2 Objetivo
- Validar completude de resultados laboratoriais (LIS)
- Verificar finalização de laudos de imagem (PACS)
- Confirmar sumário de alta completo
- Atualizar status do atendimento para COMPLETED no TASY
- Disparar workflows de cobrança e codificação
- Preparar notificações de finalização

### 1.3 Contexto no Fluxo de Negócio
Este delegate é o último passo de validação clínica antes de iniciar os processos de codificação e cobrança. Garante que todos os dados necessários para faturamento estão disponíveis e finalizados.

---

## 2. Regras de Negócio

### RN-CLINICAL-004.1: Validação de Resultados Laboratoriais (LIS)
**Descrição:** Verifica se todos os exames laboratoriais possuem resultados finais

**Condição:**
```java
boolean labResultsComplete = validateLabResults(encounterId);
```

**Critério de Aceitação:**
- Todos os pedidos de exame devem ter resultados com status `final`, `amended`, ou `corrected`
- Integração com LIS via `LISService.areResultsComplete(encounterId)`

**Ação se Incompleto:**
```java
throw new BpmnError("LAB_RESULTS_INCOMPLETE",
    "Not all lab results are final. Cannot finalize encounter.");
```

**Impacto:** Bloqueia finalização do atendimento até que todos exames tenham resultados finais

---

### RN-CLINICAL-004.2: Validação de Laudos de Imagem (PACS)
**Descrição:** Verifica se todos os estudos de imagem possuem laudos finais

**Condição:**
```java
boolean imagingComplete = validateImagingReports(encounterId);
```

**Critério de Aceitação:**
- Todos os estudos devem ter status `available`
- Todos os laudos devem ter status `final`
- Integração com PACS via `PACSService.isImagingComplete(encounterId)`

**Ação se Incompleto:**
```java
throw new BpmnError("IMAGING_INCOMPLETE",
    "Not all imaging studies have final reports. Cannot finalize encounter.");
```

**Impacto:** Bloqueia finalização até que todos laudos estejam finalizados

---

### RN-CLINICAL-004.3: Validação de Sumário de Alta
**Descrição:** Confirma que o sumário de alta está completo com todos campos obrigatórios

**Condição:**
```java
boolean dischargeSummaryComplete = validateDischargeSummary(encounter);
```

**Campos Obrigatórios:**
- `dischargeDate`: Data da alta
- `dischargeReason`: Motivo da alta
- `primaryDiagnosis`: Diagnóstico principal (CID-10)

**Validação:**
```java
boolean hasDischargeDate = encounter.getDischargeDate() != null;
boolean hasDischargeReason = encounter.getDischargeReason() != null
    && !encounter.getDischargeReason().isEmpty();
boolean hasPrimaryDiagnosis = encounter.getPrimaryDiagnosis() != null
    && !encounter.getPrimaryDiagnosis().isEmpty();

boolean isComplete = hasDischargeDate && hasDischargeReason && hasPrimaryDiagnosis;
```

**Ação se Incompleto:**
```java
throw new BpmnError("DISCHARGE_SUMMARY_INCOMPLETE",
    "Discharge summary must be completed before finalizing encounter");
```

---

### RN-CLINICAL-004.4: Atualização de Status no TASY
**Descrição:** Atualiza o status do atendimento para COMPLETED no sistema TASY ERP

**Ação:**
```java
TasyEncounterDTO updatedEncounter =
    tasyClient.updateEncounterStatus(encounterId, "COMPLETED", tasyApiKey);
```

**Integração:**
- Sistema: TASY ERP
- Endpoint: `PUT /encounters/{id}/status`
- Status: `COMPLETED`

**Transição de Status:**
- `ACTIVE` → `COMPLETED` (normal)
- `IN_PROGRESS` → `COMPLETED` (casos específicos)

---

### RN-CLINICAL-004.5: Disparo de Workflows Downstream
**Descrição:** Sinaliza que atendimento está pronto para codificação e cobrança

**Variáveis de Disparo:**
```java
setVariable(execution, "encounter_finalized", true);
setVariable(execution, "ready_for_billing", true);    // ← Dispara SUB_04_Faturamento
setVariable(execution, "ready_for_coding", true);     // ← Dispara SUB_05_Codificacao_Clinica
```

**Impacto Crítico:** Estas variáveis disparam os subprocessos de codificação clínica e faturamento

---

### RN-CLINICAL-004.6: Preparação de Dados para Cobrança
**Descrição:** Extrai e define variáveis necessárias para processo de cobrança

**Variáveis de Cobrança:**
```java
setVariable(execution, "patient_id", encounter.getPatientId());
setVariable(execution, "payer_id", encounter.getPayerId());
setVariable(execution, "encounter_type", encounter.getEncounterType());
setVariable(execution, "primary_diagnosis", encounter.getPrimaryDiagnosis());
setVariable(execution, "discharge_date", encounter.getDischargeDate().toString());
```

**Utilização:** Estas variáveis alimentam o processo de geração de guia TISS e cálculo de valores

---

### RN-CLINICAL-004.7: Notificações de Finalização
**Descrição:** Define variáveis para disparo de notificações

**Variáveis de Notificação:**
```java
setVariable(execution, "notification_type", "ENCOUNTER_FINALIZED");
setVariable(execution, "attending_physician_id", encounter.getAttendingPhysicianId());
```

**Destinatários:**
- Médico assistente
- Equipe de codificação
- Equipe de faturamento

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `encounter_id` | String | ID do atendimento | "ENC-12345" |

### 3.2 Variáveis de Saída (Status)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `encounter_finalized` | Boolean | Atendimento finalizado | PROCESS |
| `encounter_finalization_timestamp` | String | Timestamp da finalização | PROCESS |
| `lab_results_complete` | Boolean | Exames laboratoriais completos | PROCESS |
| `imaging_complete` | Boolean | Laudos de imagem completos | PROCESS |
| `discharge_summary_complete` | Boolean | Sumário de alta completo | PROCESS |

### 3.3 Variáveis de Saída (Disparo de Workflows)
| Variável | Tipo | Descrição | Impacto |
|----------|------|-----------|---------|
| `ready_for_billing` | Boolean | **Dispara faturamento** | SUB_04 |
| `ready_for_coding` | Boolean | **Dispara codificação** | SUB_05 |

### 3.4 Variáveis de Saída (Dados de Cobrança)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `patient_id` | String | ID do paciente | PROCESS |
| `payer_id` | String | ID do convênio | PROCESS |
| `encounter_type` | String | Tipo de atendimento | PROCESS |
| `primary_diagnosis` | String | Diagnóstico principal (CID-10) | PROCESS |
| `discharge_date` | String | Data da alta | PROCESS |
| `attending_physician_id` | String | ID do médico | PROCESS |

### 3.5 Variáveis de Notificação
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `notification_type` | String | "ENCOUNTER_FINALIZED" | PROCESS |

### 3.6 Variáveis de Erro
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `encounter_finalization_error` | String | Mensagem de erro |

---

## 4. Integrações

### 4.1 TasyClient
**Métodos:**
- `getEncounter(encounterId, apiKey)`: Recupera dados do atendimento
- `updateEncounterStatus(encounterId, status, apiKey)`: Atualiza status

**Endpoint:** `PUT /api/v1/encounters/{id}/status`

---

### 4.2 LISService (Laboratory Information System)
**Método:** `areResultsComplete(encounterId)`
**Retorno:** Boolean indicando se todos exames têm resultados finais

**Critério:**
- Status dos resultados: `final`, `amended`, `corrected`

---

### 4.3 PACSService (Picture Archiving System)
**Método:** `isImagingComplete(encounterId)`
**Retorno:** Boolean indicando se todos estudos têm laudos finais

**Critério:**
- Status do estudo: `available`
- Status do laudo: `final`

---

## 5. Tratamento de Erros

### 5.1 BpmnErrors
| Código | Descrição | Ação no BPMN |
|--------|-----------|--------------|
| `ENCOUNTER_NOT_FOUND` | Atendimento não encontrado no TASY | Retornar erro |
| `LAB_RESULTS_INCOMPLETE` | Exames laboratoriais pendentes | Bloquear finalização |
| `IMAGING_INCOMPLETE` | Laudos de imagem pendentes | Bloquear finalização |
| `DISCHARGE_SUMMARY_INCOMPLETE` | Sumário de alta incompleto | Solicitar preenchimento |

### 5.2 Exceções Técnicas
- Log completo com stack trace
- Define `encounter_finalized = false`
- Define `encounter_finalization_error` com mensagem
- Re-lança `RuntimeException`

---

## 6. Conformidade e Auditoria

### 6.1 Regulamentações
- **ANS:** RN 305/2012 - Documentação completa para auditoria
- **CFM:** Resolução sobre sumário de alta
- **LGPD:** Finalização segura de dados médicos

### 6.2 Logs de Auditoria
```
INFO: Executing FinalizarAtendimentoDelegate - Process: {id}, Activity: {activity}
INFO: Starting encounter finalization - EncounterId: {id}
INFO: Retrieved encounter from TASY - EncounterId: {id}, Status: {status}
INFO: Lab results validation passed - EncounterId: {id}
INFO: Imaging reports validation passed - EncounterId: {id}
INFO: Discharge summary validation passed - EncounterId: {id}
INFO: Encounter status updated in TASY - EncounterId: {id}, Status: COMPLETED
INFO: Encounter finalization completed successfully - EncounterId: {id}, ReadyForBilling: true
```

---

## 7. Dependências

### 7.1 Serviços
- `TasyClient`: Integração com TASY ERP
- `LISService`: Integração com sistema laboratorial
- `PACSService`: Integração com sistema de imagens

### 7.2 Delegates Relacionados
- `CompletenessCheckDelegate`: Verificação prévia de documentação
- `CloseEncounterDelegate`: Fechamento final do atendimento
- (Downstream) Delegates de codificação e faturamento

---

## 8. Requisitos Não-Funcionais

### 8.1 Performance
- Tempo médio de execução: < 4 segundos
- Timeout: 30 segundos

### 8.2 Idempotência
- **requiresIdempotency()**: `true`
- Múltiplas execuções não geram duplicatas

### 8.3 Disponibilidade
- Dependências críticas: TASY, LIS, PACS (uptime > 99%)

---

## 9. Cenários de Teste

### 9.1 Cenário: Finalização com Sucesso
**Dado:**
- Atendimento com status ACTIVE
- Exames laboratoriais todos finais
- Laudos de imagem todos finais
- Sumário de alta completo

**Quando:** FinalizarAtendimentoDelegate executado
**Então:**
- `encounter_finalized = true`
- `ready_for_billing = true`
- `ready_for_coding = true`
- Status TASY = COMPLETED

---

### 9.2 Cenário: Exames Laboratoriais Pendentes
**Dado:**
- `lisService.areResultsComplete(id)` retorna false

**Quando:** FinalizarAtendimentoDelegate executado
**Então:**
- BpmnError `LAB_RESULTS_INCOMPLETE`
- `encounter_finalized = false`
- `lab_results_complete = false`

---

### 9.3 Cenário: Laudos de Imagem Pendentes
**Dado:**
- `pacsService.isImagingComplete(id)` retorna false

**Quando:** FinalizarAtendimentoDelegate executado
**Então:**
- BpmnError `IMAGING_INCOMPLETE`
- `encounter_finalized = false`
- `imaging_complete = false`

---

### 9.4 Cenário: Sumário de Alta Incompleto
**Dado:**
- Falta campo `primary_diagnosis` no sumário

**Quando:** FinalizarAtendimentoDelegate executado
**Então:**
- BpmnError `DISCHARGE_SUMMARY_INCOMPLETE`
- `encounter_finalized = false`
- `discharge_summary_complete = false`

---

## 10. Fluxo de Validação

```
┌─────────────────────────────────────────────────────┐
│ 1. Get Encounter from TASY                         │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ 2. Validate Lab Results (LIS)                      │
│    ✓ All results final/amended/corrected?          │
│    ✗ BpmnError: LAB_RESULTS_INCOMPLETE              │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ 3. Validate Imaging Reports (PACS)                 │
│    ✓ All studies available + reports final?        │
│    ✗ BpmnError: IMAGING_INCOMPLETE                  │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ 4. Validate Discharge Summary                      │
│    ✓ dischargeDate + dischargeReason + diagnosis?  │
│    ✗ BpmnError: DISCHARGE_SUMMARY_INCOMPLETE        │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ 5. Update Status to COMPLETED in TASY              │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ 6. Set Process Variables                           │
│    • encounter_finalized = true                    │
│    • ready_for_billing = true  ← DISPARA SUB_04    │
│    • ready_for_coding = true   ← DISPARA SUB_05    │
└─────────────────────────────────────────────────────┘
```

---

## 11. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/FinalizarAtendimentoDelegate.java`

**Serviços:**
- `/src/main/java/com/hospital/revenuecycle/service/LISService.java`
- `/src/main/java/com/hospital/revenuecycle/service/PACSService.java`

**Clientes:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`

**DTOs:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/dto/TasyEncounterDTO.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/FinalizarAtendimentoDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
