# RN-SlotDTO - Horário Disponível para Agendamento

**Categoria**: DTO (Data Transfer Object)
**Prioridade**: Alta
**Status**: Implementado
**Versão**: 1.0.0
**Padrão**: HL7 FHIR R4 Slot Resource

---

## 1. VISÃO GERAL

### 1.1 Propósito
DTO que representa um **Slot** (horário disponível) conforme FHIR R4, definindo:
- Período específico de tempo disponível para agendamento
- Status de disponibilidade (livre, ocupado, indisponível)
- Vinculação a uma grade (Schedule)
- Tipo de serviço oferecido neste horário

### 1.2 Contexto
Um **Slot** é parte de um **Schedule** (grade), representando um bloco de tempo específico que pode ser reservado para um **Appointment**.

```
Schedule (Grade de Atendimento)
  ├── Slot 08:00-08:30 [free]
  ├── Slot 08:30-09:00 [busy] → Appointment #123
  ├── Slot 09:00-09:30 [free]
  └── Slot 09:30-10:00 [busy-unavailable]
```

### 1.3 Localização
```
Arquivo: src/main/java/com/hospital/revenuecycle/integration/scheduling/dto/SlotDTO.java
Pacote: com.hospital.revenuecycle.integration.scheduling.dto
```

---

## 2. ESTRUTURA DE DADOS

### 2.1 Código Completo
```java
package com.hospital.revenuecycle.integration.scheduling.dto;

import lombok.Data;
import java.time.LocalDateTime;
import java.util.List;

@Data
public class SlotDTO {
    private String id;
    private String identifier;
    private String scheduleId;
    private String status;
    private List<String> serviceCategories;
    private List<String> serviceTypes;
    private List<String> specialties;
    private String appointmentType;
    private LocalDateTime start;
    private LocalDateTime end;
    private Boolean overbooked;
    private String comment;
}
```

---

## 3. CAMPOS E REGRAS

### 3.1 Identificação

#### `id` (String)
- **Tipo**: Identificador único do slot
- **Obrigatoriedade**: Gerado pelo servidor
- **Formato**: UUID ou identificador composto
- **Exemplo**: `"slot-2026-01-15-0900"`, `"slot-12345"`

#### `identifier` (String)
- **Tipo**: Identificador de negócio (opcional)
- **Uso**: Referência externa ou código interno
- **Exemplo**: `"SLOT-CARDIO-2026-01-15-09"`

---

### 3.2 Vinculação à Grade

#### `scheduleId` (String) - **OBRIGATÓRIO**
Identificador da grade (Schedule) à qual este slot pertence.

**Formato**: ID do Schedule ou FHIR Reference
**Exemplo**: `"schedule-12345"`, `"Schedule/cardio-dr-maria"`

**Regras**:
- Schedule deve existir e estar ativo
- Slot herda características do Schedule (serviceTypes, specialties)

---

### 3.3 Status de Disponibilidade

#### `status` (String) - **OBRIGATÓRIO**
Define o estado atual do slot.

**Valores Permitidos**:
- `free`: Livre para agendamento
- `busy`: Ocupado por um appointment confirmado
- `busy-unavailable`: Indisponível (bloqueio administrativo, manutenção)
- `busy-tentative`: Reservado provisoriamente (aguardando confirmação)

**Fluxo de Status**:
```
free → busy-tentative → busy (appointment confirmado)
free → busy (appointment direto)
busy → free (appointment cancelado)
free → busy-unavailable (bloqueio administrativo)
busy-unavailable → free (desbloqueio)
```

**Regras de Negócio**:
- Apenas slots com status `free` podem ser agendados
- Status `busy` indica que há um Appointment vinculado
- Status `busy-unavailable` bloqueia agendamento (ex: férias, manutenção)
- Status `busy-tentative` é temporário durante processo de confirmação

---

### 3.4 Categorização de Serviços

#### `serviceCategories` (List\<String\>)
Categorias de serviço oferecidas neste slot (herdadas do Schedule).

**Exemplos**:
- `["General Medicine"]`
- `["Surgery"]`
- `["Diagnostic Imaging"]`

#### `serviceTypes` (List\<String\>)
Tipos específicos de serviço.

**Exemplos**:
- `["Consultation"]`
- `["Follow-up"]`
- `["MRI", "MRI with Contrast"]`

#### `specialties` (List\<String\>)
Especialidades médicas disponíveis.

**Exemplos**:
- `["Cardiology"]`
- `["Orthopedics"]`
- `["Pediatrics", "Neonatology"]`

**Uso**:
- Filtrar slots por especialidade desejada
- Validar compatibilidade com appointment

---

### 3.5 Tipo de Agendamento

#### `appointmentType` (String)
Tipo de appointment permitido neste slot.

**Valores Comuns**:
- `ROUTINE`: Atendimento de rotina
- `WALKIN`: Atendimento sem agendamento prévio
- `CHECKUP`: Exame de rotina
- `FOLLOWUP`: Retorno
- `EMERGENCY`: Emergência

**Regra**:
- Se especificado, apenas appointments do tipo correspondente podem usar o slot
- Se `null`, qualquer tipo é aceito

---

### 3.6 Período de Tempo

#### `start` (LocalDateTime) - **OBRIGATÓRIO**
Data e hora de início do slot.

**Formato**: ISO 8601
**Exemplo**: `2026-01-15T09:00:00`

**Validações**:
- Deve estar dentro do planning horizon do Schedule
- Deve ser no futuro (para novos slots)
- Deve ser múltiplo do intervalo de agendamento (ex: 15 min, 30 min)

#### `end` (LocalDateTime) - **OBRIGATÓRIO**
Data e hora de término do slot.

**Validações**:
- `end` > `start`
- Duração comum: 15, 30, 60 minutos
- Não pode sobrepor outro slot do mesmo Schedule

**Cálculo de Duração**:
```java
long minutes = ChronoUnit.MINUTES.between(slot.getStart(), slot.getEnd());
```

---

### 3.7 Overbooking

#### `overbooked` (Boolean)
Indica se o slot permite mais de um appointment (sobremarcação).

**Valores**:
- `true`: Slot pode ter múltiplos appointments (ex: vacinação em grupo)
- `false`: Slot aceita apenas 1 appointment (padrão)

**Uso**:
- Clínicas de vacinação
- Sessões de terapia em grupo
- Exames que permitem múltiplos pacientes

**Regra**:
- Se `overbooked = true`, status pode ser `busy` mas ainda aceitar agendamentos
- Se `overbooked = false`, status `busy` bloqueia novos agendamentos

---

### 3.8 Observações

#### `comment` (String)
Comentários ou observações sobre o slot (opcional).

**Exemplos**:
- `"Último horário disponível no dia"`
- `"Reservado para casos urgentes"`
- `"Slot para retornos apenas"`

---

## 4. VALIDAÇÕES

### 4.1 Validação de Criação
```java
public void validateSlot(SlotDTO slot) {
    // Campos obrigatórios
    if (slot.getScheduleId() == null || slot.getScheduleId().isEmpty()) {
        throw new ValidationException("Schedule ID is required");
    }
    if (slot.getStatus() == null) {
        throw new ValidationException("Status is required");
    }
    if (slot.getStart() == null) {
        throw new ValidationException("Start time is required");
    }
    if (slot.getEnd() == null) {
        throw new ValidationException("End time is required");
    }

    // Validar status
    List<String> validStatuses = List.of(
        "free", "busy", "busy-unavailable", "busy-tentative"
    );
    if (!validStatuses.contains(slot.getStatus())) {
        throw new ValidationException("Invalid status: " + slot.getStatus());
    }

    // Validar período
    if (!slot.getEnd().isAfter(slot.getStart())) {
        throw new ValidationException("End time must be after start time");
    }

    // Validar duração mínima (ex: 5 minutos)
    long minutes = ChronoUnit.MINUTES.between(slot.getStart(), slot.getEnd());
    if (minutes < 5) {
        throw new ValidationException("Slot duration must be at least 5 minutes");
    }

    // Validar que start está no futuro (para novos slots)
    if (slot.getId() == null && slot.getStart().isBefore(LocalDateTime.now())) {
        throw new ValidationException("Start time must be in the future");
    }
}
```

### 4.2 Validação de Disponibilidade
```java
public boolean isAvailable(SlotDTO slot) {
    // Slot deve estar com status "free"
    if (!"free".equals(slot.getStatus())) {
        return false;
    }

    // Slot deve estar no futuro
    if (slot.getStart().isBefore(LocalDateTime.now())) {
        return false;
    }

    // Schedule deve estar ativo
    ScheduleDTO schedule = getSchedule(slot.getScheduleId());
    if (!Boolean.TRUE.equals(schedule.getActive())) {
        return false;
    }

    return true;
}
```

---

## 5. EXEMPLOS

### 5.1 Slot Disponível - Consulta Cardiologia
```json
{
  "id": "slot-2026-01-15-0900",
  "identifier": "SLOT-CARDIO-150126-09",
  "scheduleId": "schedule-cardio-dr-maria",
  "status": "free",
  "serviceCategories": ["General Medicine"],
  "serviceTypes": ["Consultation"],
  "specialties": ["Cardiology"],
  "appointmentType": "ROUTINE",
  "start": "2026-01-15T09:00:00",
  "end": "2026-01-15T09:30:00",
  "overbooked": false,
  "comment": null
}
```

### 5.2 Slot Ocupado
```json
{
  "id": "slot-2026-01-15-0930",
  "scheduleId": "schedule-cardio-dr-maria",
  "status": "busy",
  "serviceCategories": ["General Medicine"],
  "serviceTypes": ["Consultation"],
  "specialties": ["Cardiology"],
  "appointmentType": "ROUTINE",
  "start": "2026-01-15T09:30:00",
  "end": "2026-01-15T10:00:00",
  "overbooked": false,
  "comment": "Appointment #12345 - João Silva"
}
```

### 5.3 Slot Bloqueado (Indisponível)
```json
{
  "id": "slot-2026-01-15-1000",
  "scheduleId": "schedule-cardio-dr-maria",
  "status": "busy-unavailable",
  "serviceCategories": ["General Medicine"],
  "serviceTypes": ["Consultation"],
  "specialties": ["Cardiology"],
  "appointmentType": null,
  "start": "2026-01-15T10:00:00",
  "end": "2026-01-15T10:30:00",
  "overbooked": false,
  "comment": "Reunião administrativa"
}
```

### 5.4 Slot com Overbooking (Vacinação)
```json
{
  "id": "slot-vaccination-2026-01-15-1400",
  "scheduleId": "schedule-vaccination-clinic",
  "status": "free",
  "serviceCategories": ["Preventive Care"],
  "serviceTypes": ["Vaccination"],
  "specialties": ["Immunization"],
  "appointmentType": "ROUTINE",
  "start": "2026-01-15T14:00:00",
  "end": "2026-01-15T14:30:00",
  "overbooked": true,
  "comment": "Permite até 5 pacientes simultaneamente"
}
```

---

## 6. REGRAS DE NEGÓCIO

### RN-SLOT-001: Consulta de Slots Disponíveis
**Descrição**: Buscar slots livres em uma grade para um período.

**Endpoint**:
```java
GET /Slot?schedule=schedule-12345&start=ge2026-01-15&end=le2026-01-31&status=free
```

**Validações**:
- Schedule deve existir e estar ativo
- Período não pode exceder 30 dias
- Apenas slots no futuro

---

### RN-SLOT-002: Reserva de Slot
**Descrição**: Atualizar status de `free` para `busy-tentative` durante criação de appointment.

**Processo**:
1. Verificar se slot está `free`
2. Atualizar para `busy-tentative`
3. Criar appointment
4. Se sucesso: atualizar para `busy`
5. Se falha: reverter para `free`

**Implementação**:
```java
@Transactional
public AppointmentDTO createAppointmentWithSlot(AppointmentDTO appointment, String slotId) {
    // 1. Reservar slot
    SlotDTO slot = schedulingClient.getSlot(slotId);
    if (!"free".equals(slot.getStatus())) {
        throw new SlotNotAvailableException("Slot is not available");
    }

    schedulingClient.updateSlotStatus(slotId, "busy-tentative");

    try {
        // 2. Criar appointment
        AppointmentDTO created = schedulingClient.createAppointment(appointment);

        // 3. Confirmar slot
        schedulingClient.updateSlotStatus(slotId, "busy");

        return created;
    } catch (Exception e) {
        // 4. Reverter slot
        schedulingClient.updateSlotStatus(slotId, "free");
        throw e;
    }
}
```

---

### RN-SLOT-003: Liberação de Slot
**Descrição**: Quando appointment é cancelado, liberar slot.

**Processo**:
1. Cancelar appointment (status = cancelled)
2. Obter slotId do appointment
3. Atualizar slot para `free`

**Implementação**:
```java
public void cancelAppointmentAndFreeSlot(String appointmentId) {
    // 1. Obter appointment
    AppointmentDTO appointment = schedulingClient.getAppointmentById(appointmentId);

    // 2. Cancelar
    schedulingClient.cancelAppointment(appointmentId, "Patient request");

    // 3. Liberar slot
    if (appointment.getSlotId() != null) {
        schedulingClient.updateSlotStatus(appointment.getSlotId(), "free");
    }
}
```

---

### RN-SLOT-004: Bloqueio Administrativo
**Descrição**: Bloquear slots para manutenção, reuniões, etc.

**Uso**:
```java
public void blockSlots(String scheduleId, LocalDateTime start, LocalDateTime end, String reason) {
    List<SlotDTO> slots = schedulingClient.getAvailableSlots(
        scheduleId,
        start.toLocalDate(),
        end.toLocalDate(),
        "free"
    );

    for (SlotDTO slot : slots) {
        if (!slot.getStart().isBefore(start) && !slot.getEnd().isAfter(end)) {
            slot.setStatus("busy-unavailable");
            slot.setComment(reason);
            schedulingClient.updateSlot(slot);
        }
    }
}
```

---

## 7. INTEGRAÇÃO COM APPOINTMENT

### 7.1 Fluxo de Agendamento
```
1. Cliente consulta slots disponíveis (status=free)
2. Cliente seleciona slot
3. Sistema reserva slot (status=busy-tentative)
4. Sistema cria appointment vinculado ao slot
5. Sistema confirma slot (status=busy)
6. Appointment fica vinculado ao slot
```

### 7.2 Consulta de Slots e Criação de Appointment
```java
public AppointmentDTO agendarConsulta(
    String patientId,
    String practitionerId,
    LocalDate date,
    String specialty
) {
    // 1. Buscar schedule do profissional
    List<ScheduleDTO> schedules = schedulingClient.getPractitionerSchedule(
        practitionerId, date, date, "Bearer " + apiKey
    );

    ScheduleDTO schedule = schedules.stream()
        .filter(s -> s.getSpecialties().contains(specialty))
        .findFirst()
        .orElseThrow(() -> new NoScheduleFoundException("No schedule for specialty"));

    // 2. Buscar slots disponíveis
    List<SlotDTO> slots = schedulingClient.getAvailableSlots(
        schedule.getId(), date, date, "free", "Bearer " + apiKey
    );

    if (slots.isEmpty()) {
        throw new NoSlotsAvailableException("No available slots on " + date);
    }

    // 3. Selecionar primeiro slot disponível
    SlotDTO selectedSlot = slots.get(0);

    // 4. Criar appointment
    AppointmentDTO appointment = new AppointmentDTO();
    appointment.setPatientId(patientId);
    appointment.setPractitionerId(practitionerId);
    appointment.setSlotId(selectedSlot.getId());
    appointment.setStart(selectedSlot.getStart());
    appointment.setEnd(selectedSlot.getEnd());
    appointment.setStatus("proposed");

    return createAppointmentWithSlot(appointment, selectedSlot.getId());
}
```

---

## 8. CASOS DE USO

### 8.1 Buscar Próximo Horário Disponível
```java
public SlotDTO findNextAvailableSlot(String scheduleId) {
    LocalDate today = LocalDate.now();
    LocalDate endDate = today.plusDays(30);

    List<SlotDTO> slots = schedulingClient.getAvailableSlots(
        scheduleId, today, endDate, "free", "Bearer " + apiKey
    );

    return slots.stream()
        .filter(slot -> slot.getStart().isAfter(LocalDateTime.now()))
        .min(Comparator.comparing(SlotDTO::getStart))
        .orElse(null);
}
```

### 8.2 Verificar Disponibilidade em Horário Específico
```java
public boolean isTimeSlotAvailable(String scheduleId, LocalDateTime dateTime, int durationMinutes) {
    LocalDate date = dateTime.toLocalDate();

    List<SlotDTO> slots = schedulingClient.getAvailableSlots(
        scheduleId, date, date, "free", "Bearer " + apiKey
    );

    LocalDateTime expectedEnd = dateTime.plusMinutes(durationMinutes);

    return slots.stream()
        .anyMatch(slot ->
            !slot.getStart().isAfter(dateTime)
            && !slot.getEnd().isBefore(expectedEnd)
            && "free".equals(slot.getStatus())
        );
}
```

---

## 9. REFERÊNCIAS

### 9.1 Padrões
- HL7 FHIR R4 Slot: https://hl7.org/fhir/R4/slot.html
- FHIR Slot Status: https://hl7.org/fhir/R4/valueset-slotstatus.html

### 9.2 Documentos Relacionados
- `RN-SchedulingClient.md`: Cliente de agendamento
- `RN-ScheduleDTO.md`: Grade de atendimento
- `RN-AppointmentDTO.md`: Appointment vinculado ao slot

---

**Última Atualização**: 2026-01-12
**Responsável**: Equipe de Integração
**Revisores**: Arquitetura, Operações
