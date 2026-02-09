# RN-ParticipantDTO - Participante do Agendamento

**Categoria**: DTO (Data Transfer Object)
**Prioridade**: Alta
**Status**: Implementado
**Versão**: 1.0.0
**Padrão**: HL7 FHIR R4 Appointment.participant

---

## 1. VISÃO GERAL

### 1.1 Propósito
DTO que representa um **participante** de um Appointment conforme FHIR R4, identificando:
- Tipo de participante (paciente, profissional, local, etc.)
- Identificação do ator
- Obrigatoriedade da participação
- Status de aceitação

### 1.2 Localização
```
Arquivo: src/main/java/com/hospital/revenuecycle/integration/scheduling/dto/ParticipantDTO.java
Pacote: com.hospital.revenuecycle.integration.scheduling.dto
```

---

## 2. ESTRUTURA DE DADOS

### 2.1 Código Completo
```java
package com.hospital.revenuecycle.integration.scheduling.dto;

import lombok.Data;

@Data
public class ParticipantDTO {
    private String type;
    private String actorId;
    private String actorName;
    private String required;
    private String status;
}
```

---

## 3. CAMPOS E REGRAS

### 3.1 Tipo de Participante

#### `type` (String) - **OBRIGATÓRIO**
Define o papel do participante no appointment.

**Valores Permitidos**:
- `patient`: Paciente sendo atendido
- `practitioner`: Profissional de saúde
- `location`: Local físico do atendimento
- `related-person`: Pessoa relacionada (acompanhante, responsável)
- `device`: Equipamento necessário
- `healthcare-service`: Serviço de saúde

**Regras de Negócio**:
- Todo appointment DEVE ter ao menos 1 participante tipo `patient`
- Todo appointment DEVE ter ao menos 1 participante tipo `practitioner`
- Participante tipo `location` é opcional mas recomendado

**Exemplos**:
```json
{"type": "patient"}       // Paciente
{"type": "practitioner"}  // Médico, enfermeiro, terapeuta
{"type": "location"}      // Consultório, sala cirúrgica
{"type": "device"}        // Equipamento de ressonância, raio-x
```

---

### 3.2 Identificação do Ator

#### `actorId` (String) - **OBRIGATÓRIO**
Identificador único do participante no formato FHIR Reference.

**Formato**: `{ResourceType}/{id}`

**Exemplos**:
- `"Patient/12345"`: Referência a paciente
- `"Practitioner/67890"`: Referência a profissional
- `"Location/clinic-1"`: Referência a localização
- `"Device/mri-machine-01"`: Referência a equipamento

**Validações**:
- Formato válido de FHIR Reference
- Recurso deve existir no sistema
- ResourceType compatível com `type`

---

### 3.3 Nome do Ator

#### `actorName` (String)
Nome descritivo do participante (opcional, mas recomendado para UI).

**Exemplos**:
- `"João Silva"`: Nome do paciente
- `"Dr. Maria Santos - Cardiologia"`: Nome e especialidade do profissional
- `"Consultório 1 - Ala A"`: Nome e localização
- `"Ressonância Magnética - Equipamento 2"`: Nome do equipamento

**Uso**:
- Exibição em interfaces de usuário
- Notificações e mensagens
- Relatórios e logs

---

### 3.4 Obrigatoriedade

#### `required` (String) - **OBRIGATÓRIO**
Define se a participação é obrigatória para o appointment acontecer.

**Valores Permitidos**:
- `required`: Participação obrigatória
- `optional`: Participação opcional
- `information-only`: Apenas informativo

**Regras**:
- Participantes tipo `patient` e `practitioner` geralmente são `required`
- Participantes tipo `location` podem ser `optional`
- Participantes tipo `device` são `required` se o procedimento depender dele

**Exemplos**:
```json
{
  "type": "patient",
  "required": "required",     // Paciente DEVE estar presente
  "status": "accepted"
}

{
  "type": "practitioner",
  "required": "required",     // Médico DEVE estar presente
  "status": "accepted"
}

{
  "type": "location",
  "required": "optional",     // Sala pode mudar se necessário
  "status": "tentative"
}

{
  "type": "related-person",
  "required": "information-only",  // Apenas notificar acompanhante
  "status": "needs-action"
}
```

---

### 3.5 Status de Participação

#### `status` (String) - **OBRIGATÓRIO**
Indica se o participante aceitou/confirmou sua participação.

**Valores Permitidos**:
- `accepted`: Aceitou participar
- `declined`: Recusou participar
- `tentative`: Participação provisória
- `needs-action`: Aguardando resposta

**Fluxo de Status**:
```
needs-action → accepted    (participante confirmou)
needs-action → declined    (participante recusou)
needs-action → tentative   (participante provisoriamente confirmou)
tentative → accepted       (confirmação definitiva)
tentative → declined       (desistiu)
```

**Regras de Negócio**:
- Se um participante `required` estiver `declined`, o appointment não pode ser `booked`
- Participantes `optional` com status `declined` não impedem o appointment
- Todos participantes `required` devem estar `accepted` para status `booked`

---

## 4. VALIDAÇÕES

### 4.1 Validação de Criação
```java
public void validateParticipant(ParticipantDTO participant) {
    // Campos obrigatórios
    if (participant.getType() == null || participant.getType().isEmpty()) {
        throw new ValidationException("Participant type is required");
    }
    if (participant.getActorId() == null || participant.getActorId().isEmpty()) {
        throw new ValidationException("Actor ID is required");
    }
    if (participant.getRequired() == null) {
        throw new ValidationException("Required field is mandatory");
    }
    if (participant.getStatus() == null) {
        throw new ValidationException("Status is required");
    }

    // Valores permitidos
    List<String> validTypes = List.of(
        "patient", "practitioner", "location",
        "related-person", "device", "healthcare-service"
    );
    if (!validTypes.contains(participant.getType())) {
        throw new ValidationException("Invalid participant type: " + participant.getType());
    }

    List<String> validRequired = List.of("required", "optional", "information-only");
    if (!validRequired.contains(participant.getRequired())) {
        throw new ValidationException("Invalid required value: " + participant.getRequired());
    }

    List<String> validStatuses = List.of("accepted", "declined", "tentative", "needs-action");
    if (!validStatuses.contains(participant.getStatus())) {
        throw new ValidationException("Invalid status: " + participant.getStatus());
    }

    // Formato de actorId
    if (!participant.getActorId().matches("^[A-Za-z]+/[A-Za-z0-9-]+$")) {
        throw new ValidationException("Invalid actorId format. Expected: ResourceType/id");
    }
}
```

### 4.2 Validação de Lista de Participantes
```java
public void validateParticipantList(List<ParticipantDTO> participants) {
    if (participants == null || participants.isEmpty()) {
        throw new ValidationException("At least one participant is required");
    }

    // Verificar se tem paciente
    boolean hasPatient = participants.stream()
        .anyMatch(p -> "patient".equals(p.getType()));
    if (!hasPatient) {
        throw new ValidationException("Appointment must have at least one patient");
    }

    // Verificar se tem profissional
    boolean hasPractitioner = participants.stream()
        .anyMatch(p -> "practitioner".equals(p.getType()));
    if (!hasPractitioner) {
        throw new ValidationException("Appointment must have at least one practitioner");
    }

    // Verificar se todos os required estão accepted
    boolean allRequiredAccepted = participants.stream()
        .filter(p -> "required".equals(p.getRequired()))
        .allMatch(p -> "accepted".equals(p.getStatus()));

    if (!allRequiredAccepted) {
        throw new ValidationException("All required participants must be accepted");
    }
}
```

---

## 5. EXEMPLOS

### 5.1 Participantes Típicos de Consulta
```json
[
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
  },
  {
    "type": "location",
    "actorId": "Location/clinic-1",
    "actorName": "Consultório 1 - Ala A",
    "required": "optional",
    "status": "accepted"
  }
]
```

### 5.2 Participantes de Cirurgia
```json
[
  {
    "type": "patient",
    "actorId": "Patient/12345",
    "actorName": "João Silva",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "practitioner",
    "actorId": "Practitioner/surgeon-1",
    "actorName": "Dr. Carlos Lima - Cirurgião",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "practitioner",
    "actorId": "Practitioner/anesthesiologist-1",
    "actorName": "Dra. Ana Costa - Anestesiologista",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "location",
    "actorId": "Location/operating-room-3",
    "actorName": "Centro Cirúrgico - Sala 3",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "device",
    "actorId": "Device/surgical-equipment-1",
    "actorName": "Kit Cirúrgico Ortopédico",
    "required": "required",
    "status": "accepted"
  },
  {
    "type": "related-person",
    "actorId": "RelatedPerson/emergency-contact-1",
    "actorName": "Maria Silva (Esposa)",
    "required": "information-only",
    "status": "needs-action"
  }
]
```

### 5.3 Participante Aguardando Confirmação
```json
{
  "type": "practitioner",
  "actorId": "Practitioner/67890",
  "actorName": "Dr. Pedro Alves - Pediatria",
  "required": "required",
  "status": "needs-action"
}
```

### 5.4 Participante Recusou
```json
{
  "type": "practitioner",
  "actorId": "Practitioner/12345",
  "actorName": "Dr. João Dias - Ortopedia",
  "required": "required",
  "status": "declined"
}
```

---

## 6. REGRAS DE NEGÓCIO

### RN-PART-001: Participantes Obrigatórios
**Descrição**: Todo appointment deve ter paciente e profissional.

**Validação**:
```java
public boolean hasRequiredParticipants(List<ParticipantDTO> participants) {
    long patientCount = participants.stream()
        .filter(p -> "patient".equals(p.getType()))
        .count();

    long practitionerCount = participants.stream()
        .filter(p -> "practitioner".equals(p.getType()))
        .count();

    return patientCount >= 1 && practitionerCount >= 1;
}
```

---

### RN-PART-002: Confirmação de Participantes
**Descrição**: Appointment só pode ser confirmado se todos `required` estão `accepted`.

**Validação**:
```java
public boolean canConfirmAppointment(List<ParticipantDTO> participants) {
    return participants.stream()
        .filter(p -> "required".equals(p.getRequired()))
        .allMatch(p -> "accepted".equals(p.getStatus()));
}
```

---

### RN-PART-003: Substituição de Participante
**Descrição**: Participantes opcionais podem ser substituídos sem cancelar appointment.

**Regra**:
- `required` com `declined`: Appointment deve ser cancelado ou reagendado
- `optional` com `declined`: Appointment pode continuar

---

## 7. INTEGRAÇÃO COM APPOINTMENT

### 7.1 Extração de IDs Principais
```java
public String getPatientId(AppointmentDTO appointment) {
    return appointment.getParticipants().stream()
        .filter(p -> "patient".equals(p.getType()))
        .map(ParticipantDTO::getActorId)
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("No patient participant found"));
}

public String getPractitionerId(AppointmentDTO appointment) {
    return appointment.getParticipants().stream()
        .filter(p -> "practitioner".equals(p.getType()))
        .map(ParticipantDTO::getActorId)
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("No practitioner participant found"));
}

public String getLocationId(AppointmentDTO appointment) {
    return appointment.getParticipants().stream()
        .filter(p -> "location".equals(p.getType()))
        .map(ParticipantDTO::getActorId)
        .findFirst()
        .orElse(null);
}
```

---

## 8. REFERÊNCIAS

### 8.1 Padrões
- HL7 FHIR R4 Appointment.participant: https://hl7.org/fhir/R4/appointment-definitions.html#Appointment.participant
- FHIR Participation Status: https://hl7.org/fhir/R4/valueset-participationstatus.html

### 8.2 Documentos Relacionados
- `RN-AppointmentDTO.md`: Estrutura principal do appointment
- `RN-SchedulingClient.md`: Cliente de agendamento
- `RN-SlotDTO.md`: Slots de disponibilidade

---

**Última Atualização**: 2026-01-12
**Responsável**: Equipe de Integração
**Revisores**: Arquitetura, Faturamento
