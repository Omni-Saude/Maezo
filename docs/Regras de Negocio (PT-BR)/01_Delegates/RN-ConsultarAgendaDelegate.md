# RN-ConsultarAgendaDelegate - Consulta de Agenda FHIR

## Identificação
- **ID**: RN-SCHED-001
- **Nome**: ConsultarAgendaDelegate
- **Categoria**: Scheduling (Agendamento)
- **Subprocess**: SUB_01_Agendamento
- **Versão**: 1.0.0
- **Data**: 2026-01-09
- **Bean BPMN**: `consultarAgendaDelegate`
- **Prioridade**: ALTA

## Visão Geral
Delegate responsável por consultar o sistema de agendamento usando recursos FHIR R4 (Appointment, Schedule, Slot), permitindo buscar agendamentos, horários disponíveis e agenda de profissionais.

## Responsabilidades

### 1. Consulta de Agendamentos (Appointment)
- Busca agendamentos por paciente
- Busca agendamentos por profissional
- Filtra por data e status
- Retorna lista de appointments encontrados

### 2. Consulta de Agenda (Schedule)
- Obtém agenda do profissional
- Filtra por período (data início/fim)
- Lista especialidades e tipos de serviço
- Verifica disponibilidade do profissional

### 3. Consulta de Slots Disponíveis (Slot)
- Lista horários disponíveis do profissional
- Filtra por data e tipo de atendimento
- Verifica status (free, busy, busy-unavailable)
- Identifica overbooking

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `query_type` | String | Sim | Tipo de consulta: APPOINTMENTS, SCHEDULE, SLOTS |
| `patient_id` | String | Não | Identificador do paciente |
| `practitioner_id` | String | Não* | Identificador do profissional |
| `appointment_date` | LocalDate | Não | Data específica do agendamento |
| `appointment_status` | String | Não | Status do agendamento (booked, pending, fulfilled) |
| `start_date` | LocalDate | Não | Data inicial do período |
| `end_date` | LocalDate | Não | Data final do período |

*Obrigatório para query_type = SCHEDULE ou SLOTS

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `appointments` | List&lt;Map&lt;String, Object&gt;&gt; | Lista de agendamentos encontrados |
| `schedules` | List&lt;Map&lt;String, Object&gt;&gt; | Lista de agendas do profissional |
| `available_slots` | List&lt;Map&lt;String, Object&gt;&gt; | Lista de slots disponíveis |
| `appointment_count` | Integer | Número de agendamentos encontrados |
| `schedule_count` | Integer | Número de agendas encontradas |
| `slot_count` | Integer | Número de slots disponíveis |
| `query_successful` | Boolean | `true` se consulta foi bem-sucedida |

## Tipos de Consulta

### 1. APPOINTMENTS - Busca Agendamentos
**Parâmetros**:
- `patient_id`: Busca por paciente
- `practitioner_id`: Busca por profissional
- `appointment_date`: Filtra por data
- `appointment_status`: Filtra por status

**Retorno**: Lista de appointments com metadados

### 2. SCHEDULE - Busca Agenda de Profissional
**Parâmetros**:
- `practitioner_id`: **Obrigatório**
- `start_date`: Início do período (default: hoje)
- `end_date`: Fim do período (default: +30 dias)

**Retorno**: Lista de schedules do profissional

### 3. SLOTS - Busca Horários Disponíveis
**Parâmetros**:
- `practitioner_id`: **Obrigatório**
- `start_date`: Início do período (default: hoje)
- `end_date`: Fim do período (default: +7 dias)

**Retorno**: Lista de slots disponíveis

## Algoritmo

```
1. Validar query_type:
   - Deve ser: APPOINTMENTS, SCHEDULE ou SLOTS

2. Executar consulta baseada em query_type:

   APPOINTMENTS:
     - queryAppointments(patient_id, practitioner_id, appointment_date, status)
     - Extrair metadados dos appointments
     - Persistir: appointments, appointment_count

   SCHEDULE:
     - Validar: practitioner_id é obrigatório
     - Definir período padrão se não fornecido (hoje + 30 dias)
     - querySchedule(practitioner_id, start_date, end_date)
     - Extrair metadados das schedules
     - Persistir: schedules, schedule_count

   SLOTS:
     - Validar: practitioner_id é obrigatório
     - Definir período padrão se não fornecido (hoje + 7 dias)
     - Obter schedules do profissional
     - Para cada schedule, buscar slots disponíveis
     - Consolidar todos os slots
     - Persistir: available_slots, slot_count

3. Marcar consulta como bem-sucedida:
   - query_successful = true

4. Em caso de erro:
   - query_successful = false
   - query_error = mensagem de erro
   - throw RuntimeException
```

## Estruturas de Metadados

### Appointment Metadata
```json
{
  "appointment_id": "apt-12345",
  "identifier": "AGEND-2025-001",
  "status": "booked",
  "appointment_type": "consulta",
  "start": "2025-01-15T10:00:00",
  "end": "2025-01-15T10:30:00",
  "minutes_duration": 30,
  "patient_id": "PAT-12345",
  "practitioner_id": "PRAC-678",
  "location_id": "LOC-CONS-01",
  "reason_code": "checkup"
}
```

### Schedule Metadata
```json
{
  "schedule_id": "sched-678",
  "identifier": "AGENDA-CARDIO-01",
  "active": true,
  "actor_id": "PRAC-678",
  "actor_type": "Practitioner",
  "service_categories": ["Cardiologia"],
  "service_types": ["consulta", "retorno"],
  "specialties": ["cardiology"],
  "start": "2025-01-10",
  "end": "2025-02-10"
}
```

### Slot Metadata
```json
{
  "slot_id": "slot-9012",
  "identifier": "SLOT-2025-001",
  "schedule_id": "sched-678",
  "status": "free",
  "start": "2025-01-15T10:00:00",
  "end": "2025-01-15T10:30:00",
  "service_categories": ["Cardiologia"],
  "service_types": ["consulta"],
  "appointment_type": "primeira-consulta",
  "overbooked": false
}
```

## Casos de Uso

### Caso 1: Buscar Agendamentos do Paciente
**Entrada**:
```json
{
  "query_type": "APPOINTMENTS",
  "patient_id": "PAT-12345",
  "appointment_status": "booked"
}
```

**Saída**:
```json
{
  "appointments": [
    {
      "appointment_id": "apt-001",
      "status": "booked",
      "start": "2025-01-15T10:00:00",
      "practitioner_id": "PRAC-678"
    }
  ],
  "appointment_count": 1,
  "query_successful": true
}
```

### Caso 2: Buscar Agenda do Profissional
**Entrada**:
```json
{
  "query_type": "SCHEDULE",
  "practitioner_id": "PRAC-678",
  "start_date": "2025-01-10",
  "end_date": "2025-01-31"
}
```

**Saída**:
```json
{
  "schedules": [
    {
      "schedule_id": "sched-678",
      "active": true,
      "service_categories": ["Cardiologia"],
      "start": "2025-01-10",
      "end": "2025-01-31"
    }
  ],
  "schedule_count": 1,
  "query_successful": true
}
```

### Caso 3: Buscar Horários Disponíveis
**Entrada**:
```json
{
  "query_type": "SLOTS",
  "practitioner_id": "PRAC-678",
  "start_date": "2025-01-15",
  "end_date": "2025-01-16"
}
```

**Saída**:
```json
{
  "available_slots": [
    {
      "slot_id": "slot-001",
      "status": "free",
      "start": "2025-01-15T10:00:00",
      "end": "2025-01-15T10:30:00"
    },
    {
      "slot_id": "slot-002",
      "status": "free",
      "start": "2025-01-15T14:00:00",
      "end": "2025-01-15T14:30:00"
    }
  ],
  "slot_count": 2,
  "query_successful": true
}
```

## Regras de Negócio

### RN-SCHED-001-001: Query Type Obrigatório
- **Descrição**: query_type deve ser fornecido e válido
- **Prioridade**: CRÍTICA
- **Validação**: `query_type IN ('APPOINTMENTS', 'SCHEDULE', 'SLOTS')`

### RN-SCHED-001-002: Practitioner ID para Schedule/Slots
- **Descrição**: practitioner_id é obrigatório para SCHEDULE e SLOTS
- **Prioridade**: CRÍTICA
- **Validação**: `query_type IN ('SCHEDULE', 'SLOTS') → practitioner_id != null`

### RN-SCHED-001-003: Período Padrão para Schedule
- **Descrição**: Se datas não fornecidas, usar hoje + 30 dias
- **Prioridade**: MÉDIA
- **Default**: `start_date = hoje, end_date = hoje + 30 dias`

### RN-SCHED-001-004: Período Padrão para Slots
- **Descrição**: Se datas não fornecidas, usar hoje + 7 dias
- **Prioridade**: MÉDIA
- **Default**: `start_date = hoje, end_date = hoje + 7 dias`

## Integração com SchedulingService

### Consulta de Appointments
```java
List<AppointmentDTO> appointments =
    schedulingService.queryAppointments(
        patientId,
        practitionerId,
        appointmentDate,
        status
    );
```

### Consulta de Schedule
```java
List<ScheduleDTO> schedules =
    schedulingService.getPractitionerSchedule(
        practitionerId,
        startDate,
        endDate
    );
```

### Consulta de Slots
```java
List<SlotDTO> slots =
    schedulingService.getAvailableSlots(
        scheduleId,
        startDate,
        endDate
    );
```

## Recursos FHIR R4

### Appointment Resource
- **URL**: `http://hl7.org/fhir/R4/appointment.html`
- **Propósito**: Representa agendamento de serviço de saúde
- **Status**: proposed, pending, booked, arrived, fulfilled, cancelled, noshow

### Schedule Resource
- **URL**: `http://hl7.org/fhir/R4/schedule.html`
- **Propósito**: Container para slots de disponibilidade
- **Actor**: Practitioner, PractitionerRole, HealthcareService, Location

### Slot Resource
- **URL**: `http://hl7.org/fhir/R4/slot.html`
- **Propósito**: Horário específico disponível para agendamento
- **Status**: free, busy, busy-unavailable, busy-tentative, entered-in-error

## Idempotência

**Requer Idempotência**: Não

**Justificativa**: Operação read-only de consulta, pode ser executada múltiplas vezes sem efeitos colaterais.

## Dependências
- **SchedulingService**: Serviço de agendamento com integração FHIR
- **FHIR Server**: Servidor FHIR R4 compatível

## Versionamento
- **v1.0.0**: Implementação inicial com FHIR R4

## Referências
- RN-ConfirmarAgendamento: Confirmação de agendamento
- RN-RegistrarTriagem: Registro de triagem pós-agendamento
- FHIR R4 Appointment: http://hl7.org/fhir/R4/appointment.html
- FHIR R4 Schedule: http://hl7.org/fhir/R4/schedule.html
- FHIR R4 Slot: http://hl7.org/fhir/R4/slot.html
