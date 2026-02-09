# Clinical Delegates - Index and Integration Guide

**Document:** Clinical Workflow Delegates Documentation
**Created:** 2026-01-24
**Last Updated:** 2026-01-24
**Status:** Complete

---

## Overview

This document provides a consolidated index and integration guide for all clinical workflow delegates in the Revenue Cycle Management BPMN process. The clinical delegates handle the core medical data capture and encounter lifecycle within the SUB_03_Atendimento_Clinico subprocess.

---

## Clinical Delegates Summary

### 1. RN-CLIN-001: Fechamento de Atendimento Clínico (CloseEncounterDelegate)

**File:** `RN-CLIN-001-CloseEncounter.md`
**ID:** RN-CLIN-001
**Priority:** CRITICAL
**BPMN Bean:** `${closeEncounterDelegate}`

**Purpose:**
Finaliza atendimento clínico com validação abrangente de documentação, sumário de alta, prescrições e agendamentos de follow-up. Orquestra transição do ciclo clínico para ciclo de faturamento.

**Key Business Rules:**
- RN-CLIN-001.1: Validação de Documentação Completa
- RN-CLIN-001.2: Validação de Sumário de Alta
- RN-CLIN-001.3: Verificação de Prescrições e Follow-up
- RN-CLIN-001.4: Atualização de Status no TASY
- RN-CLIN-001.5: Arquivamento de Documentos
- RN-CLIN-001.6: Disparo de Workflow de Cobrança
- RN-CLIN-001.7: Notificações de Alta

**Input Variables:**
- `encounter_id` (String, required): Identificador do atendimento

**Output Variables:**
- `encounter_closed` (Boolean): Sucesso do fechamento
- `ready_for_billing` (Boolean): **GATILHO CRÍTICO** para processo de cobrança
- `documents_archived` (Integer): Quantidade de documentos arquivados

**Integration:**
- TASY ERP: Atualiza status do encounter
- Document Storage: Arquiva documentos clínicos
- Notification Service: Envia notificações de alta

**LGPD Considerations:**
- Arquivamento seguro de documentos clínicos
- Retenção conforme legislação (mínimo 7 anos)
- Acesso restrito a dados médicos

---

### 2. RN-CLIN-002: Coleta de Dados Clínicos do TASY (CollectTASYDataDelegate)

**File:** `RN-CLIN-002-CollectTASYData.md`
**ID:** RN-CLIN-002
**Priority:** HIGH
**BPMN Bean:** `${collectTASYData}`

**Purpose:**
Coleta dados clínicos abrangentes do sistema TASY EHR, incluindo procedimentos, diagnósticos, medicações e resultados laboratoriais. Prepara dados para processos de coding e faturamento.

**Key Business Rules:**
- RN-CLIN-002.1: Validação de ID do Paciente
- RN-CLIN-002.2: Validação de ID do Atendimento
- RN-CLIN-002.3: Escopo de Coleta (FULL, BASIC, BILLING_ONLY)
- RN-CLIN-002.4: Coleta de Dados Demográficos
- RN-CLIN-002.5: Coleta de Procedimentos (códigos TUSS)
- RN-CLIN-002.6: Coleta de Diagnósticos (ICD-10)
- RN-CLIN-002.7: Coleta de Medicações (escopo FULL)
- RN-CLIN-002.8: Coleta de Resultados Laboratoriais (escopo FULL)

**Input Variables:**
- `patientId` (String, required): ID do paciente
- `encounterId` (String, required): ID do atendimento
- `dataScope` (String, optional): FULL (default), BASIC, BILLING_ONLY

**Output Variables:**
- `clinicalData` (Map): Dados demográficos e clínicos
- `procedures` (List<Map>): Procedimentos com códigos TUSS
- `diagnoses` (List<Map>): Diagnósticos com códigos ICD-10
- `medications` (List<Map>, if FULL): Medicações administradas
- `labResults` (List<Map>, if FULL): Resultados laboratoriais
- `dataCollectionTimestamp` (LocalDateTime): Quando dados foram coletados
- `dataSource` (String): "TASY_EHR"

**Integration:**
- TASY ERP: REST APIs para extraction de dados clínicos
- HL7 Interfaces: ADR messages para real-time updates
- FHIR Endpoints: Observation, Procedure, Condition, Medication resources

**LGPD Considerations:**
- Dados sensíveis de saúde processados
- Base legal: Execução de contrato e interesse legítimo
- Direito de acesso, correção, portabilidade
- Transmissão via HTTPS/TLS

---

### 3. RN-CLINICAL-007: Registro de Atendimento (RegisterEncounterDelegate)

**File:** `RN-RegisterEncounterDelegate.md`
**ID:** RN-CLINICAL-007
**Priority:** HIGH
**BPMN Bean:** `${registerEncounter}`

**Purpose:**
Registra novo atendimento/admissão no sistema TASY ERP via módulo ADT. Cria identificador único de atendimento e captura dados demográficos iniciais do paciente.

**Key Business Rules:**
- Validação de ID do Paciente
- Validação de Tipo de Serviço (INPATIENT, OUTPATIENT, EMERGENCY, AMBULATORY)
- Criação de Encounter no TASY ADT
- Status Inicial (REGISTERED)
- Dados Demográficos Opcionais
- Confirmação de Registro
- Idempotência (previne registros duplicados)

**Input Variables:**
- `patientId` (String, required): ID do paciente
- `serviceType` (String, required): INPATIENT | OUTPATIENT | EMERGENCY | AMBULATORY
- `clinicalData` (Map, optional): Dados clínicos iniciais
- `departmentCode` (String, optional): Código do departamento
- `attendingPhysician` (String, optional): ID do médico

**Output Variables:**
- `encounterId` (String): ID único do atendimento (ENC-XXXXXXXX)
- `encounterDate` (LocalDateTime): Data/hora do registro
- `encounterStatus` (String): Status (REGISTERED, ACTIVE)
- `registrationConfirmation` (Map): Confirmação do TASY

**Integration:**
- TASY ERP: ADT module (Admission/Discharge/Transfer)
- HL7 ADT-A01: Admit Patient message
- FHIR: Encounter resource

**LGPD Considerations:**
- Captura de dados demográficos (nome, data nascimento, gênero)
- Base legal: Execução de contrato
- Direito de acesso e portabilidade
- Segurança na transmissão

---

## Clinical Workflow Sequence

```
Patient Arrival
    ↓
1. RegisterEncounterDelegate
   └─> Creates encounter in TASY
       Generates encounterId
    ↓
2. Clinical Evaluation (Manual/External)
   └─> Medical record creation
       Procedures performed
       Diagnoses documented
       Medications administered
       Lab tests ordered
    ↓
3. CollectTASYDataDelegate
   └─> Retrieves all clinical data
       Procedures (TUSS codes)
       Diagnoses (ICD-10 codes)
       Medications
       Lab results
    ↓
4. Clinical Coding & Validation
   └─> Validate codes
       Check documentation
       Verify completeness
    ↓
5. CloseEncounterDelegate
   └─> Validate all documentation
       Verify discharge summary
       Check prescriptions/follow-up
       Update status to CLOSED
       Trigger billing process
    ↓
Billing Process (SUB_04_Faturamento)
```

---

## TASY ERP Integration Architecture

### System Integrations

```
Clinical Delegates
    ↓
┌───────────────────────────────────────────┐
│ TASY ERP                                   │
│ ┌─────────────────────────────────────┐   │
│ │ ADT Module                          │   │
│ │ - Encounters                        │   │
│ │ - Admissions/Discharges            │   │
│ │ - Transfers                        │   │
│ └─────────────────────────────────────┘   │
│ ┌─────────────────────────────────────┐   │
│ │ Clinical Module                     │   │
│ │ - Patient Demographics              │   │
│ │ - Procedures (TUSS)                 │   │
│ │ - Diagnoses (ICD-10)                │   │
│ │ - Medications                       │   │
│ └─────────────────────────────────────┘   │
│ ┌─────────────────────────────────────┐   │
│ │ Lab Module / LIS                    │   │
│ │ - Lab Results                       │   │
│ │ - Test Orders                       │   │
│ └─────────────────────────────────────┘   │
└───────────────────────────────────────────┘
    ↑                                    ↑
REST APIs                         HL7 ADR/ADT Messages
FHIR Endpoints
```

### API Endpoints

**Register Encounter:**
```
POST /tasy/encounters
Body: {patientId, serviceType, departmentCode, attendingPhysician, clinicalData}
Response: {encounterId, status, tasyConfirmationNumber, encounterDate}
```

**Collect Clinical Data:**
```
GET /tasy/patients/{patientId}
GET /tasy/encounters/{encounterId}
GET /tasy/encounters/{encounterId}/procedures
GET /tasy/encounters/{encounterId}/diagnoses
GET /tasy/encounters/{encounterId}/medications
GET /tasy/encounters/{encounterId}/lab-results
```

**Close Encounter:**
```
PUT /tasy/encounters/{encounterId}/status
Body: {status: "CLOSED", dischargeDate, dischargeReason}
Response: {status, updatedAt, tasyConfirmationNumber}
```

---

## HL7 Message Standards

### ADT-A01 (Admit Patient) - RegisterEncounterDelegate
**Segmentos Principais:**
- MSH: Message Header
- EVN: Event Type (Admit)
- PID: Patient Identification
- PV1: Patient Visit (Encounter Details)

### ADR Messages (Admission/Discharge/Return) - CollectTASYDataDelegate
**Real-time data feeds** from TASY for encounter updates

---

## Data Flow and Variables

### Cross-Delegate Variable Flow

```
RegisterEncounterDelegate
├─ Output: encounterId
│
├─> CollectTASYDataDelegate
│   ├─ Input: encounterId, patientId
│   ├─ Output: clinicalData, procedures, diagnoses, medications, labResults
│   │
│   └─> Downstream Coding/Validation Processes
│
└─> CloseEncounterDelegate
    ├─ Input: encounter_id (used as reference)
    ├─ Output: ready_for_billing (TRIGGERS BILLING)
    │
    └─> Billing Process (SUB_04_Faturamento)
```

### Key Shared Variables

| Variable | Source | Consumer | Scope |
|----------|--------|----------|-------|
| `encounterId` | RegisterEncounter | CollectTASY, Close | PROCESS |
| `patientId` | Parent Process | All three | PROCESS |
| `clinicalData` | CollectTASY | Coding, Validation | PROCESS |
| `procedures` | CollectTASY | Coding, Billing | PROCESS |
| `diagnoses` | CollectTASY | Coding, Billing | PROCESS |
| `ready_for_billing` | CloseEncounter | Billing Process | PROCESS |

---

## LGPD Compliance Framework

### Dados de Saúde Processados
**Dados Pessoais Sensíveis (Artigo 5, LGPD):**
- Dados demográficos (nome, data nascimento, gênero)
- Diagnósticos e condições clínicas
- Procedimentos realizados
- Medicações prescritas
- Resultados de testes (laboratoriais, vitals)
- Informações de contato

### Bases Legais (Artigo 7, LGPD)
1. **Execução de Contrato:** Atendimento clínico e assistência à saúde
2. **Interesse Legítimo:** Faturamento, compliance, auditoria
3. **Obrigação Legal:** Regulamentações CFM, ANS, CFF

### Direitos do Paciente (Artigos 17-22)
- **Acesso:** Paciente pode acessar seus dados clínicos
- **Correção:** Informações incorretas podem ser corrigidas
- **Exclusão:** Com restrições legais (mínimo 7 anos)
- **Portabilidade:** Dados em formato estruturado/interoperável
- **Oposição:** A limitado processamento (com justificativas)

### Medidas de Segurança
- **Transmissão:** HTTPS/TLS 1.2+ obrigatório
- **Armazenamento:** Encriptação de dados sensíveis
- **Acesso:** Controle de acesso granular por role
- **Auditoria:** Logging completo de acessos e modificações
- **Retenção:** 7 anos mínimo (conforme CFM/ANS)

### Conformidade Regulatória
- **CFM:** Resolução 1638/2002 (prontuário eletrônico)
- **ANS:** Normas de completude de documentação
- **ANVISA:** Padrões de segurança (quando aplicável)
- **LGPD:** Proteção de dados pessoais de saúde

---

## Error Handling and Resilience

### BpmnError Codes

**RegisterEncounter:**
- `INVALID_PATIENT_ID`: Patient ID missing/invalid
- `INVALID_SERVICE_TYPE`: Service type not supported
- `ENCOUNTER_REGISTRATION_FAILED`: TASY creation failure

**CollectTASY:**
- `INVALID_PATIENT_ID`: Patient ID missing/invalid
- `INVALID_ENCOUNTER_ID`: Encounter ID missing/invalid
- `TASY_DATA_COLLECTION_FAILED`: Data retrieval failure

**CloseEncounter:**
- `INCOMPLETE_DOCUMENTATION`: Required docs missing
- `INCOMPLETE_DISCHARGE_SUMMARY`: Discharge summary incomplete

### Retry Strategy
- **Backoff:** Exponential backoff (1s, 2s, 4s, 8s, 16s)
- **Max Retries:** 5 attempts
- **Timeout:** 30 minutes total for critical operations
- **Fallback:** Cache or manual intervention

### Logging

**Log Levels:**
- `INFO`: Entry/exit, major operations, success
- `DEBUG`: Validation details, intermediate data
- `WARN`: Non-blocking issues, fallbacks
- `ERROR`: Failures, exceptions, blocks

**Log Format Example:**
```
2026-01-24T14:30:00.123Z INFO [RegisterEncounterDelegate] Registering encounter:
patientId=PAT-12345, serviceType=INPATIENT, processInstance=PROC-ABC123
```

---

## Performance Characteristics

### Expected Execution Times

| Delegate | Operation | Avg Time | P95 | Timeout |
|----------|-----------|----------|-----|---------|
| RegisterEncounter | Create encounter | 1-2s | 4s | 15s |
| CollectTASY (FULL) | Retrieve all data | 2-3s | 7s | 20s |
| CollectTASY (BASIC) | Retrieve core data | 1-2s | 4s | 15s |
| CloseEncounter | Validate & close | 2-4s | 7s | 30s |

### Volume Estimates

**Typical Data Volumes:**
- Procedures per encounter: 0-20
- Diagnoses per encounter: 1-10
- Medications per encounter: 0-30
- Lab results per encounter: 0-50

### Concurrency
- **Max Parallel:** 5 RegisterEncounter per patient (rare)
- **Database Connections:** 1-2 per delegate execution
- **Memory:** < 100MB per execution

---

## Testing Strategy

### Unit Tests
- Input validation
- Business rule validation
- Error handling
- Variable setting

### Integration Tests
- TASY API communication
- HL7 message generation
- Data completeness
- Error scenarios

### End-to-End Tests
- Full workflow execution
- Cross-delegate data flow
- Error recovery
- Performance under load

### Test Data Scenarios
- Valid encounters with complete data
- Encounters with optional fields
- Invalid inputs (null, empty, malformed)
- TASY unavailability
- Partial data scenarios
- Data scope variations

---

## Monitoring and Observability

### Key Metrics to Monitor

**Volume Metrics:**
- Encounters registered per day
- Encounters closed per day
- Data collection scopes distribution (FULL/BASIC/BILLING_ONLY)

**Performance Metrics:**
- Execution time percentiles (P50, P95, P99)
- Timeout rate
- Retry rate

**Quality Metrics:**
- Documentation completeness
- Error rate per delegate
- Recovery rate

**Business Metrics:**
- Encounters progressing to billing (% of closed)
- Days in clinical phase (avg)
- Rejection rate due to incomplete data

### Alerts
- Execution time > 2x baseline
- Error rate > 1%
- TASY unavailability > 5 minutes
- Timeout rate > 0.5%

---

## Related Documentation

### Clinical Delegates (This Suite)
1. `RN-CLIN-001-CloseEncounter.md`: Encounter closure with validation
2. `RN-CLIN-002-CollectTASYData.md`: Clinical data extraction
3. `RN-RegisterEncounterDelegate.md`: Encounter registration

### Related Services
- `EncounterClosureService.java`: Close encounter logic
- `TasyEncounterService.java`: TASY encounter operations
- `TasyWebClient.java`: TASY REST API client
- `HL7ADTMessageBuilder.java`: HL7 message construction

### Related Processes
- `SUB_03_Atendimento_Clinico.bpmn`: Clinical subprocess
- `SUB_04_Faturamento.bpmn`: Billing subprocess
- Eligibility verification process
- Insurance authorization process

### Related Entities
- `Encounter.java`: Domain entity
- `Patient.java`: Domain entity
- `Procedure.java`: Domain entity
- `Diagnosis.java`: Domain entity

---

## Troubleshooting Guide

### Issue: Encounter Registration Fails
**Symptom:** `ENCOUNTER_REGISTRATION_FAILED`
**Causes:**
- TASY API unavailable
- Invalid patient ID
- Network connectivity
- TASY credentials expired
**Solution:**
1. Check TASY health status
2. Verify patient exists in TASY
3. Check network connectivity
4. Verify API credentials
5. Retry after exponential backoff

### Issue: Missing Clinical Data
**Symptom:** `clinicalData` empty or incomplete
**Causes:**
- Data not entered in TASY yet
- Timing issue (data collection before entry)
- TASY API performance degradation
- Incorrect encounterId
**Solution:**
1. Wait for medical staff to complete entry
2. Verify encounterId
3. Check TASY performance
4. Consider using BASIC scope instead of FULL
5. Manual data entry as fallback

### Issue: Cannot Close Encounter
**Symptom:** `INCOMPLETE_DOCUMENTATION` or `INCOMPLETE_DISCHARGE_SUMMARY`
**Causes:**
- Medical documentation incomplete
- Discharge summary not filled
- Prescriptions not issued
**Solution:**
1. Notify medical staff of missing documentation
2. Provide list of required documents
3. Allow editing of discharge summary
4. Manual review and approval by physician

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Revenue Cycle Team | Initial comprehensive clinical delegates index and integration guide |

---

**Document Status:** COMPLETE AND REVIEWED
**Next Review Date:** 2026-04-24
**Owner:** Revenue Cycle Development Team
