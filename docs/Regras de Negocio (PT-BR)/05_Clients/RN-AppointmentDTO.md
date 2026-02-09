# RN-AppointmentDTO - Estrutura de Dados do Agendamento

**Categoria**: DTO (Data Transfer Object)
**Prioridade**: Alta
**Status**: Implementado
**Versão**: 1.0.0
**Padrão**: HL7 FHIR R4 Appointment Resource

---

## 1. VISÃO GERAL

### 1.1 Propósito
DTO que representa um **Appointment** (agendamento) conforme especificação HL7 FHIR R4, contendo:
- Informações de data e horário
- Participantes (paciente, profissional, local)
- Status do agendamento
- Tipo e categorização do atendimento
- Prioridade e duração

### 1.2 Localização
```
Arquivo: src/main/java/com/hospital/revenuecycle/integration/scheduling/dto/AppointmentDTO.java
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
public class AppointmentDTO {
    private String id;
    private String identifier;
    private String status;
    private String serviceCategory;
    private List<String> serviceTypes;
    private List<String> specialties;
    private String appointmentType;
    private String reasonCode;
    private String reasonReference;
    private Integer priority;
    private String description;
    private LocalDateTime start;
    private LocalDateTime end;
    private Integer minutesDuration;
    private List<ParticipantDTO> participants;
    private String patientId;
    private String practitionerId;
    private String locationId;
    private String slotId;
    private String comment;
    private String cancellationReason;
}
```

---

## 3. CAMPOS E REGRAS

### 3.1 Identificação

#### `id` (String)
- **Tipo**: Identificador único do sistema de agendamento
- **Obrigatoriedade**: Gerado pelo servidor (POST), obrigatório em GET/PUT
- **Formato**: UUID ou identificador numérico
- **Exemplo**: `"apt-12345"`, `"f47ac10b-58cc-4372-a567-0e02b2c3d479"`

#### `identifier` (String)
- **Tipo**: Identificador de negócio (opcional)
- **Uso**: Número do agendamento para referência externa
- **Exemplo**: `"AGD-2026-00123"`

---

### 3.2 Status do Agendamento

#### `status` (String) - **OBRIGATÓRIO**
**Valores Permitidos**:
- `proposed`: Proposto mas não confirmado
- `pending`: Aguardando confirmação
- `booked`: Confirmado e reservado
- `arrived`: Paciente chegou para atendimento (**TRIGGER BILLING**)
- `fulfilled`: Atendimento concluído
- `cancelled`: Cancelado
- `noshow`: Paciente não compareceu

**Fluxo de Transição**:
```
proposed → pending → booked → arrived → fulfilled
              ↓         ↓         ↓
           cancelled  cancelled  noshow
```

**Regra de Negócio**:
- Status `arrived` **dispara o processo de faturamento**
- Transição de `fulfilled` para outro status é proibida
- `noshow` só pode ser aplicado após horário do appointment

---

### 3.3 Categorização do Serviço

#### `serviceCategory` (String)
Categoria ampla do serviço.

**Valores Comuns**:
- `General Medicine`: Clínica geral
- `Surgery`: Cirurgia
- `Emergency`: Emergência
- `Diagnostic`: Diagnóstico
- `Rehabilitation`: Reabilitação

#### `serviceTypes` (List\<String\>)
Tipos específicos de serviço.

**Exemplos**:
- `["Consultation"]`: Consulta
- `["Surgery", "Day Surgery"]`: Cirurgia ambulatorial
- `["Imaging", "MRI"]`: Ressonância magnética

#### `specialties` (List\<String\>)
Especialidades médicas envolvidas.

**Exemplos**:
- `["Cardiology"]`: Cardiologia
- `["Orthopedics", "Sports Medicine"]`: Ortopedia esportiva
- `["Pediatrics", "Neonatology"]`: Pediatria/Neonatologia

---

### 3.4 Tipo de Agendamento

#### `appointmentType` (String)
**Valores Permitidos**:
- `ROUTINE`: Atendimento de rotina agendado
- `WALKIN`: Atendimento sem agendamento prévio
- `CHECKUP`: Exame de rotina/check-up
- `FOLLOWUP`: Retorno/acompanhamento
- `EMERGENCY`: Atendimento de emergência

**Impacto no Faturamento**:
- `EMERGENCY`: Pode ter cobrança diferenciada
- `FOLLOWUP`: Pode ter isenção conforme política
- `ROUTINE`: Cobrança padrão

---

### 3.5 Motivo do Agendamento

#### `reasonCode` (String)
Código do motivo (CID-10, SNOMED CT).

**Exemplos**:
- `"I10"`: Hipertensão essencial (CID-10)
- `"38341003"`: Hipertensão (SNOMED CT)

#### `reasonReference` (String)
Referência para recurso FHIR detalhando o motivo.

**Exemplo**: `"Condition/hypertension-123"`

---

### 3.6 Prioridade

#### `priority` (Integer)
Nível de urgência do atendimento.

**Escala**:
- `0`: Não urgente
- `1-3`: Baixa prioridade
- `4-6`: Prioridade média
- `7-9`: Alta prioridade / Urgente

**Regra**:
- Appointments com priority ≥ 7 podem ter confirmação automática
- Priority 0 pode ser reagendado com mais facilidade

---

### 3.7 Descrição e Comentários

#### `description` (String)
Descrição em texto livre do appointment.

**Exemplo**: `"Consulta de retorno para avaliação de resultados de exames"`

#### `comment` (String)
Observações adicionais.

**Exemplo**: `"Paciente solicitou horário pela manhã devido ao trabalho"`

---

### 3.8 Data e Horário

#### `start` (LocalDateTime) - **OBRIGATÓRIO**
Data e hora de início do appointment.

**Formato**: ISO 8601
**Exemplo**: `2026-01-15T09:00:00`

**Validações**:
- Deve ser no futuro (no momento da criação)
- Deve estar dentro do horário de funcionamento
- Deve corresponder a um slot disponível

#### `end` (LocalDateTime) - **OBRIGATÓRIO**
Data e hora de término do appointment.

**Validações**:
- `end` > `start`
- Diferença entre `end` e `start` deve ser ≥ `minutesDuration`

#### `minutesDuration` (Integer)
Duração em minutos.

**Validações**:
- Valor > 0
- Múltiplo de 5 (padrão)
- Compatível com duração do slot

**Cálculo**:
```java
minutesDuration = (int) ChronoUnit.MINUTES.between(start, end);
```

---

### 3.9 Participantes

#### `participants` (List\<ParticipantDTO\>) - **OBRIGATÓRIO**
Lista de participantes do appointment.

**Estrutura**: Ver `RN-ParticipantDTO.md`

**Regra**:
- Ao menos 1 participante tipo `patient`
- Ao menos 1 participante tipo `practitioner`
- Participante tipo `location` opcional mas recomendado

**Exemplo**:
```json
"participants": [
  {
    "type": "patient",
    "actorId": "Patient/12345",
    "actorName": "João Silva",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "practitioner",
    "actorId": "Practitioner/67890",
    "actorName": "Dr. Maria Santos",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "location",
    "actorId": "Location/clinic-1",
    "actorName": "Consultório 1",
    "required": "optional",
    "status": "accepted"
  }
]
```

---

### 3.10 Referências

#### `patientId` (String) - **OBRIGATÓRIO**
Identificador do paciente.

**Formato**: `Patient/{id}` (FHIR Reference)
**Exemplo**: `"Patient/12345"`

#### `practitionerId` (String) - **OBRIGATÓRIO**
Identificador do profissional.

**Formato**: `Practitioner/{id}`
**Exemplo**: `"Practitioner/67890"`

#### `locationId` (String)
Identificador do local de atendimento.

**Formato**: `Location/{id}`
**Exemplo**: `"Location/clinic-1"`

#### `slotId` (String)
Identificador do slot reservado.

**Formato**: `Slot/{id}`
**Exemplo**: `"Slot/slot-2026-01-15-0900"`

---

### 3.11 Cancelamento

#### `cancellationReason` (String)
Motivo do cancelamento (obrigatório se `status` = `cancelled`).

**Valores Comuns**:
- `patient-request`: Solicitação do paciente
- `provider-unavailable`: Profissional indisponível
- `facility-closed`: Estabelecimento fechado
- `weather`: Condições climáticas adversas
- `no-show-previous`: Histórico de faltas
- `other`: Outros motivos

---

## 4. VALIDAÇÕES DE NEGÓCIO

### 4.1 Criação de Appointment
```java
public void validateNewAppointment(AppointmentDTO dto) {
    // Campos obrigatórios
    if (dto.getStatus() == null) {
        throw new ValidationException("Status is required");
    }
    if (dto.getStart() == null || dto.getEnd() == null) {
        throw new ValidationException("Start and end times are required");
    }
    if (dto.getPatientId() == null || dto.getPractitionerId() == null) {
        throw new ValidationException("Patient and practitioner are required");
    }

    // Data futura
    if (dto.getStart().isBefore(LocalDateTime.now())) {
        throw new ValidationException("Start time must be in the future");
    }

    // End > Start
    if (!dto.getEnd().isAfter(dto.getStart())) {
        throw new ValidationException("End time must be after start time");
    }

    // Duração válida
    if (dto.getMinutesDuration() == null || dto.getMinutesDuration() <= 0) {
        throw new ValidationException("Duration must be positive");
    }

    // Participantes
    if (dto.getParticipants() == null || dto.getParticipants().isEmpty()) {
        throw new ValidationException("At least one participant is required");
    }
}
```

### 4.2 Atualização de Status
```java
public void validateStatusTransition(String currentStatus, String newStatus) {
    Map<String, List<String>> allowedTransitions = Map.of(
        "proposed", List.of("pending", "cancelled"),
        "pending", List.of("booked", "cancelled"),
        "booked", List.of("arrived", "cancelled", "noshow"),
        "arrived", List.of("fulfilled", "noshow"),
        "fulfilled", List.of(), // Terminal
        "cancelled", List.of(), // Terminal
        "noshow", List.of()     // Terminal
    );

    if (!allowedTransitions.get(currentStatus).contains(newStatus)) {
        throw new ValidationException(
            "Invalid status transition: " + currentStatus + " -> " + newStatus
        );
    }
}
```

---

## 5. EXEMPLOS DE PAYLOAD

### 5.1 Criação de Appointment (POST)
```json
{
  "status": "proposed",
  "serviceCategory": "General Medicine",
  "serviceTypes": ["Consultation"],
  "specialties": ["Cardiology"],
  "appointmentType": "ROUTINE",
  "reasonCode": "I10",
  "priority": 5,
  "description": "Consulta cardiológica de rotina",
  "start": "2026-01-15T09:00:00",
  "end": "2026-01-15T09:30:00",
  "minutesDuration": 30,
  "patientId": "Patient/12345",
  "practitionerId": "Practitioner/67890",
  "locationId": "Location/clinic-1",
  "slotId": "Slot/slot-2026-01-15-0900",
  "comment": "Paciente solicitou horário pela manhã",
  "participants": [
    {
      "type": "patient",
      "actorId": "Patient/12345",
      "actorName": "João Silva",
      "required": "required",
      "status": "accepted"
    },
    {
      "type": "practitioner",
      "actorId": "Practitioner/67890",
      "actorName": "Dr. Maria Santos - Cardiologia",
      "required": "required",
      "status": "accepted"
    }
  ]
}
```

### 5.2 Resposta de Criação (201 Created)
```json
{
  "id": "apt-67890",
  "identifier": "AGD-2026-00123",
  "status": "proposed",
  "serviceCategory": "General Medicine",
  "serviceTypes": ["Consultation"],
  "specialties": ["Cardiology"],
  "appointmentType": "ROUTINE",
  "reasonCode": "I10",
  "priority": 5,
  "description": "Consulta cardiológica de rotina",
  "start": "2026-01-15T09:00:00",
  "end": "2026-01-15T09:30:00",
  "minutesDuration": 30,
  "patientId": "Patient/12345",
  "practitionerId": "Practitioner/67890",
  "locationId": "Location/clinic-1",
  "slotId": "Slot/slot-2026-01-15-0900",
  "comment": "Paciente solicitou horário pela manhã",
  "participants": [
    {
      "type": "patient",
      "actorId": "Patient/12345",
      "actorName": "João Silva",
      "required": "required",
      "status": "accepted"
    },
    {
      "type": "practitioner",
      "actorId": "Practitioner/67890",
      "actorName": "Dr. Maria Santos - Cardiologia",
      "required": "required",
      "status": "accepted"
    }
  ]
}
```

### 5.3 Atualização de Status (PATCH)
```json
{
  "status": "arrived",
  "comment": "Paciente realizou check-in às 08:55"
}
```

### 5.4 Cancelamento (POST $cancel)
```json
{
  "cancellationReason": "patient-request",
  "comment": "Paciente solicitou reagendamento para próxima semana"
}
```

---

## 6. INTEGRAÇÃO COM CICLO DA RECEITA

### 6.1 Trigger de Faturamento
```java
// Quando status muda para "arrived"
if ("arrived".equals(appointment.getStatus())) {
    // 1. Registrar triagem
    triagemService.registrar(appointment);

    // 2. Verificar elegibilidade
    elegibilidadeService.verificar(appointment.getPatientId());

    // 3. Iniciar conta
    contaService.iniciar(appointment);

    // 4. Gerar prontuário se necessário
    prontuarioService.getOrCreate(appointment.getPatientId());
}
```

### 6.2 Mapeamento para Entidades
```java
public Triagem appointmentToTriagem(AppointmentDTO appointment) {
    Triagem triagem = new Triagem();
    triagem.setPatientId(appointment.getPatientId());
    triagem.setPractitionerId(appointment.getPractitionerId());
    triagem.setDataHora(appointment.getStart());
    triagem.setTipoAtendimento(appointment.getAppointmentType());
    triagem.setMotivo(appointment.getReasonCode());
    triagem.setObservacoes(appointment.getComment());
    return triagem;
}
```

---

## 7. REFERÊNCIAS

### 7.1 Padrões
- HL7 FHIR R4 Appointment: https://hl7.org/fhir/R4/appointment.html
- FHIR Appointment Status: https://hl7.org/fhir/R4/valueset-appointmentstatus.html

### 7.2 Documentos Relacionados
- `RN-SchedulingClient.md`: Cliente de agendamento
- `RN-ParticipantDTO.md`: Participantes do appointment
- `RN-SlotDTO.md`: Slots de disponibilidade

---

**Última Atualização**: 2026-01-12
**Responsável**: Equipe de Integração
**Revisores**: Arquitetura, Faturamento
