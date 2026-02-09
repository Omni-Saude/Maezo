# RN - RegisterEncounterDelegate

**ID:** RN-CLINICAL-007
**Camada:** Delegates (Encounter Registration)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** HIGH
**BPMN Reference:** `${registerEncounter}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável por registrar novos atendimentos no sistema TASY EHR. Cria registro de atendimento/admissão capturando dados demográficos do paciente, tipo de serviço, detalhes de admissão e informações clínicas iniciais.

### 1.2 Objetivo
- Criar registro de atendimento no TASY ADT (Admission/Discharge/Transfer)
- Capturar tipo de serviço e dados iniciais
- Integrar via HL7 ADT-A01 (Admit Patient)
- Gerar identificadores de atendimento
- Validar parâmetros obrigatórios

### 1.3 Contexto no Fluxo de Negócio
Este delegate é executado no início do processo clínico, criando o registro base que será utilizado por todos os processos downstream (documentação clínica, codificação, faturamento).

---

## 2. Regras de Negócio

### RN-CLINICAL-007.1: Validação de Patient ID
**Descrição:** Valida que o ID do paciente é válido e não vazio

**Condição:**
```java
if (patientId == null || patientId.trim().isEmpty()) {
    throw new BpmnError("INVALID_PATIENT_ID", "Patient ID cannot be empty");
}
```

**Impacto:** Bloqueia registro se Patient ID inválido

---

### RN-CLINICAL-007.2: Validação de Service Type
**Descrição:** Valida que o tipo de serviço é um dos valores permitidos

**Tipos de Serviço Válidos:**
- `INPATIENT`: Internação hospitalar
- `OUTPATIENT`: Ambulatório/consulta
- `EMERGENCY`: Emergência/pronto-socorro
- `AMBULATORY`: Atendimento ambulatorial

**Validação:**
```java
if (!serviceType.matches("^(INPATIENT|OUTPATIENT|EMERGENCY|AMBULATORY)$")) {
    throw new BpmnError("INVALID_SERVICE_TYPE",
        "Invalid service type: " + serviceType);
}
```

**Impacto:** Bloqueia registro se tipo inválido

---

### RN-CLINICAL-007.3: Geração de Encounter ID
**Descrição:** Gera identificador único para o atendimento

**Formato:**
```java
String encounterId = "ENC-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
// Exemplo: "ENC-A1B2C3D4"
```

**Produção:** O ID real seria retornado pela API do TASY após criação do registro

---

### RN-CLINICAL-007.4: Registro no TASY ADT
**Descrição:** Cria registro de atendimento no módulo ADT do TASY

**Integração:**
1. **TASY ADT API:** Cria novo registro via REST
2. **HL7 ADT-A01:** Envia mensagem de admissão de paciente
3. **FHIR Encounter:** Cria recurso Encounter

**Dados Registrados:**
- ID do atendimento
- ID do paciente
- Tipo de serviço
- Data/hora do atendimento
- Departamento/especialidade
- Médico assistente
- Dados clínicos iniciais (opcional)

---

### RN-CLINICAL-007.5: Confirmação e Rastreabilidade
**Descrição:** Gera números de confirmação para auditoria

**Confirmações Geradas:**
```java
registrationResult.put("tasyConfirmationNumber", "TASY-" + System.currentTimeMillis());
registrationResult.put("hl7MessageId", "HL7-ADT-A01-" + System.currentTimeMillis());
```

**Utilidade:** Rastreamento em logs do TASY e HL7 para troubleshooting

---

### RN-CLINICAL-007.6: Atribuição de Defaults
**Descrição:** Atribui valores padrão para campos opcionais não fornecidos

**Defaults:**
```java
departmentCode = departmentCode != null ? departmentCode : "GENERAL";
attendingPhysician = attendingPhysician != null ? attendingPhysician : "UNASSIGNED";
```

**Impacto:** Garante que registro sempre tem valores válidos, mesmo sem todos os dados

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `patientId` | String | ID do paciente no TASY | "PAT-12345" |
| `serviceType` | String | Tipo de serviço | "INPATIENT" |

### 3.2 Variáveis de Entrada (Opcionais)
| Variável | Tipo | Descrição | Padrão |
|----------|------|-----------|---------|
| `clinicalData` | Map | Dados clínicos iniciais | null |
| `departmentCode` | String | Código do departamento | "GENERAL" |
| `attendingPhysician` | String | ID do médico assistente | "UNASSIGNED" |

### 3.3 Variáveis de Saída
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `encounterId` | String | ID do atendimento gerado | PROCESS |
| `encounterDate` | LocalDateTime | Data/hora do registro | PROCESS |
| `encounterStatus` | String | Status inicial ("REGISTERED") | PROCESS |
| `registrationConfirmation` | Map | Detalhes da confirmação | PROCESS |

---

## 4. Estrutura de Dados

### 4.1 Registration Confirmation
```json
{
  "encounterId": "ENC-A1B2C3D4",
  "encounterDate": "2026-01-12T10:30:00",
  "status": "REGISTERED",
  "patientId": "PAT-12345",
  "serviceType": "INPATIENT",
  "departmentCode": "CARDIOLOGY",
  "attendingPhysician": "DR-456",
  "tasyConfirmationNumber": "TASY-1736679000000",
  "hl7MessageId": "HL7-ADT-A01-1736679000000",
  "clinicalDataRecorded": true,
  "chiefComplaint": "Chest pain"
}
```

---

## 5. Integrações

### 5.1 TASY ADT API
**Endpoint:** `POST /api/v1/encounters`
**Finalidade:** Criar novo registro de atendimento

**Request Body:**
```json
{
  "patientId": "PAT-12345",
  "serviceType": "INPATIENT",
  "departmentCode": "CARDIOLOGY",
  "attendingPhysician": "DR-456",
  "clinicalData": {
    "chiefComplaint": "Chest pain"
  }
}
```

**Response:**
```json
{
  "encounterId": "ENC-A1B2C3D4",
  "status": "REGISTERED",
  "confirmationNumber": "TASY-1736679000000"
}
```

---

### 5.2 HL7 ADT-A01 Message
**Tipo:** ADT^A01^ADT_A01 (Admit Patient)

**Segmentos:**
```hl7
MSH|^~\&|HOSPITAL|FACILITY|TASY|TASY|20260112103000||ADT^A01|HL7-ADT-A01-1736679000000|P|2.5
EVN|A01|20260112103000
PID|1||PAT-12345^^^HOSPITAL^MR||Smith^John^||19800101|M
PV1|1|I|CARDIOLOGY^301^A|R|||DR-456^Attending^Physician||||||||||V123456789
```

**Segmentos Principais:**
- `MSH`: Message Header
- `EVN`: Event Type (A01 = Admit)
- `PID`: Patient Identification
- `PV1`: Patient Visit (encounter details)

---

### 5.3 FHIR Encounter Resource
**Resource Type:** Encounter (R4)

```json
{
  "resourceType": "Encounter",
  "id": "ENC-A1B2C3D4",
  "status": "in-progress",
  "class": {
    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "code": "IMP",
    "display": "inpatient encounter"
  },
  "subject": {
    "reference": "Patient/PAT-12345"
  },
  "period": {
    "start": "2026-01-12T10:30:00Z"
  },
  "serviceProvider": {
    "reference": "Organization/HOSPITAL"
  }
}
```

---

## 6. Tratamento de Erros

### 6.1 BpmnErrors
| Código | Descrição | Ação |
|--------|-----------|------|
| `INVALID_PATIENT_ID` | Patient ID vazio ou nulo | Retornar erro ao chamador |
| `INVALID_SERVICE_TYPE` | Service Type inválido | Retornar erro ao chamador |
| `ENCOUNTER_REGISTRATION_FAILED` | Falha na criação do registro | Retry automático |

### 6.2 Exceções Técnicas
```java
catch (Exception e) {
    log.error("Failed to register encounter in TASY: patientId={}, serviceType={}",
        patientId, serviceType, e);
    throw new BpmnError("ENCOUNTER_REGISTRATION_FAILED",
        "Failed to register encounter in TASY: " + e.getMessage());
}
```

---

## 7. Conformidade e Auditoria

### 7.1 Regulamentações
- **HL7 v2.5:** ADT messages
- **HL7 FHIR R4:** Encounter resource
- **CFM:** Registro de atendimento médico
- **LGPD:** Privacidade de dados demográficos

### 7.2 Logs de Auditoria
```
INFO: Registering encounter in TASY: patientId={id}, serviceType={type}, department={dept}
INFO: Encounter registered successfully in TASY: patientId={id}, encounterId={id}, status={status}
ERROR: Failed to register encounter in TASY: patientId={id}, serviceType={type}
```

---

## 8. Dependências

### 8.1 Clientes de Integração
- `TasyClient`: Cliente para APIs TASY específicas
- `TasyWebClient`: Cliente REST para TASY
- `HL7MessageBuilder`: Construtor de mensagens HL7

### 8.2 Delegates Relacionados
- (Downstream) `CollectTASYDataDelegate`: Coleta dados do atendimento registrado
- (Downstream) Delegates clínicos que usam `encounterId`

---

## 9. Requisitos Não-Funcionais

### 9.1 Performance
- Tempo médio de execução: < 2 segundos
- Timeout: 15 segundos

### 9.2 Idempotência
- **requiresIdempotency()**: `true`
- Previne registros duplicados

**Chave de Idempotência:**
```java
protected Map<String, Object> extractInputParameters(DelegateExecution execution) {
    return Map.of(
        "patientId", execution.getVariable("patientId"),
        "serviceType", execution.getVariable("serviceType"),
        "timestamp", LocalDateTime.now().toString().substring(0, 16) // Minuto
    );
}
```

**Granularidade:** Por minuto (previne duplicatas em retry rápido)

### 9.3 Disponibilidade
- Dependência crítica: TASY (uptime > 99%)

---

## 10. Cenários de Teste

### 10.1 Cenário: Registro de Internação
**Dado:**
- `patientId="PAT-12345"`
- `serviceType="INPATIENT"`
- `departmentCode="CARDIOLOGY"`

**Quando:** RegisterEncounterDelegate executado
**Então:**
- `encounterId` gerado (formato "ENC-XXXXXXXX")
- `encounterStatus = "REGISTERED"`
- `registrationConfirmation` populado
- Mensagem HL7 ADT-A01 enviada

---

### 10.2 Cenário: Registro de Consulta Ambulatorial
**Dado:**
- `patientId="PAT-67890"`
- `serviceType="OUTPATIENT"`
- Sem `departmentCode` (usa default)

**Quando:** RegisterEncounterDelegate executado
**Então:**
- `encounterId` gerado
- `departmentCode = "GENERAL"` (default)
- `attendingPhysician = "UNASSIGNED"` (default)

---

### 10.3 Cenário: Patient ID Inválido
**Dado:** `patientId=""` (vazio)
**Quando:** RegisterEncounterDelegate executado
**Então:**
- BpmnError `INVALID_PATIENT_ID`
- Processo interrompido

---

### 10.4 Cenário: Service Type Inválido
**Dado:** `serviceType="INVALID"`
**Quando:** RegisterEncounterDelegate executado
**Então:**
- BpmnError `INVALID_SERVICE_TYPE`
- Mensagem: "Invalid service type: INVALID. Valid types: INPATIENT, OUTPATIENT, EMERGENCY, AMBULATORY"

---

## 11. Tipos de Serviço

| Service Type | Descrição | Local Típico | Duração Típica |
|--------------|-----------|--------------|----------------|
| `INPATIENT` | Internação hospitalar | Enfermaria/Leito | Dias/Semanas |
| `OUTPATIENT` | Consulta ambulatorial | Consultório | Horas |
| `EMERGENCY` | Pronto-socorro | PS/Emergência | Horas |
| `AMBULATORY` | Atendimento ambulatorial | Ambulatório | Horas |

---

## 12. Mock Data (Desenvolvimento)

Quando API TASY não disponível, o delegate gera dados simulados:

**Encounter ID Gerado:**
```java
String encounterId = "ENC-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
// Exemplo: "ENC-A1B2C3D4"
```

**Confirmação Simulada:**
```java
registrationResult.put("tasyConfirmationNumber", "TASY-" + System.currentTimeMillis());
registrationResult.put("hl7MessageId", "HL7-ADT-A01-" + System.currentTimeMillis());
```

---

## 13. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/RegisterEncounterDelegate.java`

**Clientes:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyWebClient.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/RegisterEncounterDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
