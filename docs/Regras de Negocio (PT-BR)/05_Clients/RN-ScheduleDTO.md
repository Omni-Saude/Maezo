# RN-ScheduleDTO - Grade de Atendimento

**Categoria**: DTO (Data Transfer Object)
**Prioridade**: Alta
**Status**: Implementado
**Versão**: 1.0.0
**Padrão**: HL7 FHIR R4 Schedule Resource

---

## 1. VISÃO GERAL

### 1.1 Propósito
DTO que representa uma **Schedule** (grade de atendimento) conforme FHIR R4, definindo:
- Disponibilidade de um profissional, local ou recurso
- Período de planejamento (planning horizon)
- Tipos de serviço oferecidos
- Especialidades cobertas

### 1.2 Contexto
Um **Schedule** é um container para **Slots** (horários disponíveis). Representa a "agenda" ou "grade de atendimento" de um recurso (geralmente um profissional de saúde).

### 1.3 Localização
```
Arquivo: src/main/java/com/hospital/revenuecycle/integration/scheduling/dto/ScheduleDTO.java
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
public class ScheduleDTO {
    private String id;
    private String identifier;
    private Boolean active;
    private List<String> serviceCategories;
    private List<String> serviceTypes;
    private List<String> specialties;
    private String actorId;
    private String actorType;
    private LocalDateTime planningHorizonStart;
    private LocalDateTime planningHorizonEnd;
    private String comment;
}
```

---

## 3. CAMPOS E REGRAS

### 3.1 Identificação

#### `id` (String)
- **Tipo**: Identificador único do sistema
- **Obrigatoriedade**: Gerado pelo servidor (POST), obrigatório em GET
- **Formato**: UUID ou identificador numérico
- **Exemplo**: `"schedule-12345"`, `"sched-cardio-dr-maria-2026-01"`

#### `identifier` (String)
- **Tipo**: Identificador de negócio (opcional)
- **Uso**: Número da grade para referência externa
- **Exemplo**: `"GRADE-CARDIO-001"`, `"SCH-2026-Q1-PEDIATRIA"`

---

### 3.2 Status

#### `active` (Boolean) - **OBRIGATÓRIO**
Indica se a grade está ativa e aceitando agendamentos.

**Valores**:
- `true`: Grade ativa, slots disponíveis para agendamento
- `false`: Grade inativa, não aceita novos agendamentos

**Regras**:
- Grades inativas não retornam slots disponíveis
- Appointments existentes não são afetados ao desativar grade
- Recomendado desativar grade se profissional estiver ausente

---

### 3.3 Categorização de Serviços

#### `serviceCategories` (List\<String\>)
Categorias amplas de serviço oferecidas nesta grade.

**Valores Comuns**:
- `"General Medicine"`: Clínica geral
- `"Surgery"`: Cirurgia
- `"Diagnostic Imaging"`: Diagnóstico por imagem
- `"Laboratory"`: Laboratório
- `"Emergency"`: Emergência

**Exemplo**:
```json
"serviceCategories": ["General Medicine", "Preventive Care"]
```

---

#### `serviceTypes` (List\<String\>)
Tipos específicos de serviço oferecidos.

**Exemplos**:
- `["Consultation"]`: Consultas
- `["Surgery", "Minor Surgery"]`: Cirurgias de pequeno porte
- `["MRI", "CT Scan"]`: Exames de imagem
- `["Blood Test", "Urinalysis"]`: Exames laboratoriais

**Exemplo**:
```json
"serviceTypes": ["Consultation", "Follow-up"]
```

---

#### `specialties` (List\<String\>)
Especialidades médicas cobertas pela grade.

**Exemplos**:
- `["Cardiology"]`: Cardiologia
- `["Orthopedics", "Sports Medicine"]`: Ortopedia esportiva
- `["Pediatrics"]`: Pediatria
- `["General Surgery", "Laparoscopic Surgery"]`: Cirurgia geral e laparoscópica

**Exemplo**:
```json
"specialties": ["Cardiology", "Internal Medicine"]
```

**Uso no Agendamento**:
- Filtrar grades por especialidade desejada
- Validar compatibilidade entre appointment e schedule

---

### 3.4 Ator (Recurso)

#### `actorId` (String) - **OBRIGATÓRIO**
Identificador do recurso ao qual a grade pertence.

**Formato**: FHIR Reference `{ResourceType}/{id}`

**Exemplos**:
- `"Practitioner/67890"`: Grade de um profissional
- `"Location/mri-room-1"`: Grade de uma sala de exames
- `"Device/xray-machine-01"`: Grade de equipamento

**Tipos Comuns**:
- **Practitioner**: Médico, enfermeiro, terapeuta
- **Location**: Sala cirúrgica, consultório, sala de exames
- **Device**: Equipamento de ressonância, raio-x, ultrassom
- **HealthcareService**: Serviço de saúde genérico

---

#### `actorType` (String) - **OBRIGATÓRIO**
Tipo do recurso (ResourceType do FHIR).

**Valores Permitidos**:
- `"Practitioner"`: Profissional de saúde
- `"Location"`: Localização física
- `"Device"`: Equipamento médico
- `"HealthcareService"`: Serviço de saúde

**Validação**:
```java
if (!actorId.startsWith(actorType + "/")) {
    throw new ValidationException("actorType must match actorId prefix");
}
```

---

### 3.5 Período de Planejamento

#### `planningHorizonStart` (LocalDateTime) - **OBRIGATÓRIO**
Data e hora de início da grade.

**Formato**: ISO 8601
**Exemplo**: `2026-01-01T00:00:00`

**Regras**:
- Deve ser no futuro (no momento da criação)
- Marca o início dos slots disponíveis

---

#### `planningHorizonEnd` (LocalDateTime) - **OBRIGATÓRIO**
Data e hora de término da grade.

**Formato**: ISO 8601
**Exemplo**: `2026-03-31T23:59:59`

**Validações**:
- `planningHorizonEnd` > `planningHorizonStart`
- Intervalo comum: 1 mês a 6 meses
- Após término, grade deve ser renovada ou nova criada

**Cálculo de Duração**:
```java
long days = ChronoUnit.DAYS.between(
    schedule.getPlanningHorizonStart(),
    schedule.getPlanningHorizonEnd()
);
```

---

### 3.6 Observações

#### `comment` (String)
Comentários ou observações sobre a grade (opcional).

**Exemplos**:
- `"Grade de férias - profissional retorna em 15/02"`
- `"Atendimento apenas emergências durante reforma"`
- `"Disponibilidade limitada devido a cirurgias agendadas"`

---

## 4. VALIDAÇÕES

### 4.1 Validação de Criação
```java
public void validateSchedule(ScheduleDTO schedule) {
    // Campos obrigatórios
    if (schedule.getActive() == null) {
        throw new ValidationException("Active status is required");
    }
    if (schedule.getActorId() == null || schedule.getActorId().isEmpty()) {
        throw new ValidationException("Actor ID is required");
    }
    if (schedule.getActorType() == null || schedule.getActorType().isEmpty()) {
        throw new ValidationException("Actor type is required");
    }
    if (schedule.getPlanningHorizonStart() == null) {
        throw new ValidationException("Planning horizon start is required");
    }
    if (schedule.getPlanningHorizonEnd() == null) {
        throw new ValidationException("Planning horizon end is required");
    }

    // Validar actorId e actorType
    if (!schedule.getActorId().startsWith(schedule.getActorType() + "/")) {
        throw new ValidationException(
            "actorId must start with actorType. Expected: "
            + schedule.getActorType() + "/..."
        );
    }

    // Validar período
    if (!schedule.getPlanningHorizonEnd().isAfter(schedule.getPlanningHorizonStart())) {
        throw new ValidationException(
            "Planning horizon end must be after start"
        );
    }

    // Validar período não seja muito longo (ex: máximo 1 ano)
    long days = ChronoUnit.DAYS.between(
        schedule.getPlanningHorizonStart(),
        schedule.getPlanningHorizonEnd()
    );
    if (days > 365) {
        throw new ValidationException(
            "Planning horizon cannot exceed 365 days"
        );
    }
}
```

---

## 5. EXEMPLOS

### 5.1 Grade de Profissional - Cardiologia
```json
{
  "id": "schedule-cardio-dr-maria",
  "identifier": "GRADE-CARDIO-Q1-2026",
  "active": true,
  "serviceCategories": ["General Medicine"],
  "serviceTypes": ["Consultation", "Follow-up", "ECG"],
  "specialties": ["Cardiology"],
  "actorId": "Practitioner/67890",
  "actorType": "Practitioner",
  "planningHorizonStart": "2026-01-01T08:00:00",
  "planningHorizonEnd": "2026-03-31T18:00:00",
  "comment": "Atendimento de segunda a sexta, 8h às 18h"
}
```

### 5.2 Grade de Sala de Ressonância
```json
{
  "id": "schedule-mri-room-1",
  "identifier": "GRADE-MRI-SALA1-2026",
  "active": true,
  "serviceCategories": ["Diagnostic Imaging"],
  "serviceTypes": ["MRI", "MRI with Contrast"],
  "specialties": ["Radiology"],
  "actorId": "Location/mri-room-1",
  "actorType": "Location",
  "planningHorizonStart": "2026-01-01T07:00:00",
  "planningHorizonEnd": "2026-06-30T19:00:00",
  "comment": "Sala disponível 7h às 19h, segunda a sábado"
}
```

### 5.3 Grade Inativa (Profissional de Férias)
```json
{
  "id": "schedule-pediatria-dr-joao",
  "identifier": "GRADE-PEDIATRIA-012026",
  "active": false,
  "serviceCategories": ["General Medicine"],
  "serviceTypes": ["Consultation", "Vaccination"],
  "specialties": ["Pediatrics"],
  "actorId": "Practitioner/12345",
  "actorType": "Practitioner",
  "planningHorizonStart": "2026-01-01T08:00:00",
  "planningHorizonEnd": "2026-01-31T18:00:00",
  "comment": "Profissional de férias. Retorna em 01/02/2026"
}
```

---

## 6. REGRAS DE NEGÓCIO

### RN-SCHED-GRADE-001: Consulta de Grade por Profissional
**Descrição**: Buscar grades de um profissional específico em um período.

**Endpoint**:
```java
GET /Schedule?actor=Practitioner/67890&date=ge2026-01-01&_date=le2026-03-31
```

**Validações**:
- Actor deve existir no sistema
- Período não pode exceder 90 dias
- Apenas grades ativas retornadas por padrão

---

### RN-SCHED-GRADE-002: Filtro por Especialidade
**Descrição**: Buscar grades que oferecem determinada especialidade.

**Validação**:
```java
public List<ScheduleDTO> findBySpecialty(String specialty) {
    return schedules.stream()
        .filter(s -> s.getActive())
        .filter(s -> s.getSpecialties() != null
            && s.getSpecialties().contains(specialty))
        .collect(Collectors.toList());
}
```

---

### RN-SCHED-GRADE-003: Ativação/Desativação
**Descrição**: Controlar disponibilidade de agendamentos via flag `active`.

**Impacto**:
- `active = false`: Não retorna slots disponíveis
- `active = false`: Appointments existentes não afetados
- `active = false`: Permite manutenção sem cancelar appointments

**Exemplo de Uso**:
```java
// Desativar grade temporariamente
schedulingClient.updateSchedule(scheduleId, Map.of("active", false));

// Reativar após retorno de férias
schedulingClient.updateSchedule(scheduleId, Map.of("active", true));
```

---

## 7. INTEGRAÇÃO COM SLOTS

### 7.1 Relacionamento Schedule → Slot
Um Schedule contém múltiplos Slots.

```
Schedule (Grade)
  ├── Slot 2026-01-15 08:00-08:30
  ├── Slot 2026-01-15 08:30-09:00
  ├── Slot 2026-01-15 09:00-09:30
  └── ...
```

### 7.2 Consultar Slots de uma Grade
```java
// 1. Buscar grade do profissional
List<ScheduleDTO> schedules = schedulingClient.getPractitionerSchedule(
    "Practitioner/67890",
    LocalDate.of(2026, 1, 1),
    LocalDate.of(2026, 3, 31),
    "Bearer " + apiKey
);

// 2. Para cada grade ativa, buscar slots
for (ScheduleDTO schedule : schedules) {
    if (Boolean.TRUE.equals(schedule.getActive())) {
        List<SlotDTO> slots = schedulingClient.getAvailableSlots(
            schedule.getId(),
            LocalDate.now(),
            LocalDate.now().plusDays(30),
            "free",
            "Bearer " + apiKey
        );
        // Processar slots disponíveis
    }
}
```

---

## 8. CASOS DE USO

### 8.1 Criar Grade Trimestral
```java
public ScheduleDTO criarGradeTrimestral(String practitionerId, String specialty) {
    ScheduleDTO schedule = new ScheduleDTO();
    schedule.setActive(true);
    schedule.setActorId(practitionerId);
    schedule.setActorType("Practitioner");
    schedule.setServiceCategories(List.of("General Medicine"));
    schedule.setServiceTypes(List.of("Consultation", "Follow-up"));
    schedule.setSpecialties(List.of(specialty));

    LocalDateTime start = LocalDateTime.now().withDayOfMonth(1).withHour(8).withMinute(0);
    LocalDateTime end = start.plusMonths(3).withDayOfMonth(1).minusDays(1).withHour(18).withMinute(0);

    schedule.setPlanningHorizonStart(start);
    schedule.setPlanningHorizonEnd(end);
    schedule.setComment("Grade trimestral Q" + ((start.getMonthValue()-1)/3 + 1) + "/" + start.getYear());

    return schedulingClient.createSchedule(schedule, "Bearer " + apiKey);
}
```

### 8.2 Verificar Disponibilidade de Profissional
```java
public boolean isPractitionerAvailable(String practitionerId, LocalDate date) {
    List<ScheduleDTO> schedules = schedulingClient.getPractitionerSchedule(
        practitionerId,
        date,
        date,
        "Bearer " + apiKey
    );

    return schedules.stream()
        .anyMatch(s -> Boolean.TRUE.equals(s.getActive())
            && !date.isBefore(s.getPlanningHorizonStart().toLocalDate())
            && !date.isAfter(s.getPlanningHorizonEnd().toLocalDate()));
}
```

---

## 9. REFERÊNCIAS

### 9.1 Padrões
- HL7 FHIR R4 Schedule: https://hl7.org/fhir/R4/schedule.html
- FHIR Schedule Examples: https://hl7.org/fhir/R4/schedule-examples.html

### 9.2 Documentos Relacionados
- `RN-SchedulingClient.md`: Cliente de agendamento
- `RN-SlotDTO.md`: Slots de horário disponível
- `RN-AppointmentDTO.md`: Appointment vinculado a slot

---

**Última Atualização**: 2026-01-12
**Responsável**: Equipe de Integração
**Revisores**: Arquitetura, Operações
