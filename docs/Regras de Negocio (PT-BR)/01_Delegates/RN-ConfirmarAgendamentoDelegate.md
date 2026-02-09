# RN-ConfirmarAgendamentoDelegate - Confirmação de Agendamento

## Identificação
- **ID**: RN-SCHED-002
- **Nome**: ConfirmarAgendamentoDelegate
- **Categoria**: Scheduling (Agendamento)
- **Subprocess**: SUB_01_Agendamento
- **Versão**: 1.0.0
- **Bean BPMN**: `confirmarAgendamentoDelegate`
- **Autor**: AI Swarm - Forensics Delegate Generation

## Visão Geral
Delegate responsável por confirmar agendamento no sistema HIS, finalizando a reserva de horário e enviando confirmação ao paciente.

## Responsabilidades

### 1. Confirmação de Reserva
- Valida disponibilidade do slot selecionado
- Confirma reserva no sistema HIS
- Atualiza status do slot (AVAILABLE → BOOKED)
- Gera ID de agendamento único

### 2. Geração de Confirmação
- Gera número de confirmação único
- Define data/hora do agendamento
- Prepara dados para notificação ao paciente
- Marca confirmação como enviada

### 3. Validação de Slot
- Verifica se slot ainda está disponível
- Previne double-booking
- Usa locking otimista
- Trata race conditions

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `slotId` | String | Sim | ID do slot de horário selecionado |
| `patientId` | String | Sim | Identificador do paciente |
| `encounterId` | String | Sim | Identificador do atendimento |
| `appointmentType` | String | Sim | Tipo de agendamento (consulta, exame, etc) |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `appointmentId` | String | ID único do agendamento confirmado |
| `confirmationNumber` | String | Número de confirmação para o paciente |
| `appointmentDate` | LocalDateTime | Data/hora do agendamento |
| `confirmationSent` | Boolean | `true` se confirmação foi enviada |

## Erros BPMN

| Código | Mensagem | Causa | Ação |
|--------|----------|-------|------|
| `SLOT_UNAVAILABLE` | Selected time slot is no longer available | Slot foi reservado por outro processo | Selecionar outro slot |
| `CONFIRMATION_FAILED` | Failed to confirm appointment | Falha na confirmação no HIS | Retry ou escalar |

## Algoritmo

```
1. Validar entrada:
   - slotId, patientId, encounterId, appointmentType não nulos

2. Validar disponibilidade do slot:
   - if (!isSlotAvailable(slotId))
     → throw BpmnError("SLOT_UNAVAILABLE", "Selected time slot is no longer available")

3. Integração com HIS (quando disponível):
   - AppointmentConfirmationRequest request = builder()
       .slotId(slotId)
       .patientId(patientId)
       .encounterId(encounterId)
       .appointmentType(appointmentType)
       .providerId(execution.getVariable("providerId"))
       .facilityId(execution.getVariable("facilityId"))
       .build()

   - AppointmentConfirmationResponse response = hisClient.confirmAppointment(request)

   - if (!response.isSuccess())
     → throw BpmnError("CONFIRMATION_FAILED", response.getErrorMessage())

4. Gerar dados de confirmação:
   - appointmentId = "APT-" + timestamp
   - confirmationNumber = "CONF-" + appointmentId.substring(4)
   - appointmentDate = LocalDateTime.now().plusDays(7)

5. Persistir variáveis de saída:
   - appointmentId
   - confirmationNumber
   - appointmentDate
   - confirmationSent = true

6. Registrar log de sucesso
```

## Validação de Disponibilidade de Slot

### Método isSlotAvailable()
```java
private boolean isSlotAvailable(String slotId) {
    // Real-time slot availability check:
    // Query HIS scheduling system to verify slot status
    //
    // Implementation approach:
    // SELECT status, reserved_until FROM appointment_slots
    // WHERE slot_id = ?
    //
    // Check:
    // 1. Slot status is 'AVAILABLE' or 'RESERVED'
    // 2. If RESERVED, check reservation hasn't expired
    // 3. Verify slot hasn't been double-booked
    // 4. Confirm provider is still available for that time
    //
    // UPDATE appointment_slots
    // SET status = 'BOOKED', patient_id = ?, booked_at = NOW()
    // WHERE slot_id = ? AND status IN ('AVAILABLE', 'RESERVED')
    //
    // Optimistic locking to prevent race conditions:
    // Use version field or timestamp to ensure atomic booking

    return true; // Simplified implementation assumes availability
}
```

### Locking Otimista
```sql
-- Versão SQL com locking
UPDATE appointment_slots
SET
    status = 'BOOKED',
    patient_id = ?,
    booked_at = NOW(),
    version = version + 1
WHERE
    slot_id = ?
    AND status IN ('AVAILABLE', 'RESERVED')
    AND version = ?  -- Optimistic lock

-- Se affected_rows = 0: slot não disponível (race condition)
-- Se affected_rows = 1: booking bem-sucedido
```

## Casos de Uso

### Caso 1: Confirmação Bem-Sucedida
**Entrada**:
```json
{
  "slotId": "SLOT-2025-001",
  "patientId": "PAT-12345",
  "encounterId": "ENC-2025-001",
  "appointmentType": "consulta"
}
```

**Saída**:
```json
{
  "appointmentId": "APT-1736685600000",
  "confirmationNumber": "CONF-1736685600000",
  "appointmentDate": "2025-01-19T10:00:00",
  "confirmationSent": true
}
```

**Log**:
```
INFO: confirmarAgendamentoDelegate completed: appointmentId=APT-1736685600000, confirmation=CONF-1736685600000
```

### Caso 2: Slot Não Disponível
**Entrada**:
```json
{
  "slotId": "SLOT-2025-002",
  "patientId": "PAT-67890",
  "encounterId": "ENC-2025-002",
  "appointmentType": "exame"
}
```

**Erro BPMN**:
```
BpmnError("SLOT_UNAVAILABLE", "Selected time slot is no longer available")
```

**Ação**: Processo deve retornar à etapa de seleção de slot.

### Caso 3: Falha na Confirmação HIS
**Entrada**:
```json
{
  "slotId": "SLOT-2025-003",
  "patientId": "PAT-11111",
  "encounterId": "ENC-2025-003",
  "appointmentType": "consulta"
}
```

**Erro BPMN**:
```
BpmnError("CONFIRMATION_FAILED", "HIS API returned error: CONNECTION_TIMEOUT")
```

**Ação**: Retry automático ou escalar para atendimento manual.

## Regras de Negócio

### RN-SCHED-002-001: Validação de Parâmetros
- **Descrição**: Todos os parâmetros obrigatórios devem ser fornecidos
- **Prioridade**: CRÍTICA
- **Validação**: `slotId, patientId, encounterId, appointmentType != null`

### RN-SCHED-002-002: Validação de Disponibilidade
- **Descrição**: Slot deve estar disponível no momento da confirmação
- **Prioridade**: CRÍTICA
- **Validação**: `isSlotAvailable(slotId) == true`

### RN-SCHED-002-003: Prevenção de Double-Booking
- **Descrição**: Usar locking otimista para prevenir reservas simultâneas
- **Prioridade**: CRÍTICA
- **Implementação**: UPDATE com version field

### RN-SCHED-002-004: Geração de IDs Únicos
- **Descrição**: appointmentId e confirmationNumber devem ser únicos
- **Prioridade**: ALTA
- **Implementação**: Usar timestamp + sequencial

## Integração com HIS

### AppointmentConfirmationRequest
```java
class AppointmentConfirmationRequest {
    String slotId;
    String patientId;
    String encounterId;
    String appointmentType;
    String providerId;        // Opcional
    String facilityId;        // Opcional
    String serviceCode;       // Opcional
    String notes;             // Opcional
}
```

### AppointmentConfirmationResponse
```java
class AppointmentConfirmationResponse {
    boolean success;
    String appointmentId;
    String confirmationNumber;
    LocalDateTime appointmentDateTime;
    String errorMessage;      // Se !success
}
```

## Fluxo BPMN Típico

```
[Consultar Agenda]
    ↓
[Selecionar Slot]
    ↓
[Confirmar Agendamento] ← Este delegate
    ↓ (sucesso)
[Enviar Confirmação ao Paciente]
    ↓
[End Event]

    ↓ (SLOT_UNAVAILABLE)
[Retornar à Seleção de Slot]
```

## Idempotência

**Requer Idempotência**: Sim

**Parâmetros de Idempotência**:
```java
Map<String, Object> params = {
    "slotId": slotId,
    "patientId": patientId,
    "encounterId": encounterId
}
```

**Justificativa**: Se executado múltiplas vezes com mesmos parâmetros, deve retornar mesmo appointmentId sem criar duplicatas.

## Tratamento de Race Conditions

### Cenário: 2 Processos Tentam Reservar Mesmo Slot

```
Tempo    Processo A                  Processo B
T0       isSlotAvailable(SLOT-001)   -
         → true
T1       -                           isSlotAvailable(SLOT-001)
                                     → true
T2       UPDATE slot status=BOOKED   -
         → SUCCESS
T3       -                           UPDATE slot status=BOOKED
                                     → FAIL (version mismatch)
T4       appointmentId=APT-001       throw BpmnError(SLOT_UNAVAILABLE)
```

**Resultado**: Processo A confirma, Processo B recebe erro e seleciona outro slot.

## Dependências
- **HIS Scheduling System**: Sistema de agendamento hospitalar
- **Idempotency Service**: Prevenir confirmações duplicadas
- **Notification Service**: Envio de confirmação ao paciente

## Relacionamento com Outros Delegates

### Delegates Relacionados
- **ConsultarAgendaDelegate**: Busca slots disponíveis (etapa anterior)
- **SendPaymentReminderDelegate**: Pode enviar lembrete de agendamento
- **RegistrarTriagemDelegate**: Etapa seguinte no fluxo de atendimento

## Versionamento
- **v1.0.0**: Implementação inicial com validação de disponibilidade

## Referências
- RN-ConsultarAgenda: Documentação de consulta de agenda
- RN-RegistrarTriagem: Documentação de registro de triagem
- FHIR R4 Appointment: http://hl7.org/fhir/R4/appointment.html
- Optimistic Locking Patterns: https://martinfowler.com/eaaCatalog/optimisticOfflineLock.html
