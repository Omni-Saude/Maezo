# RN-SchedulingService - Serviço de Integração com Sistema de Agendamento

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/SchedulingService.java`

---

## I. Resumo Executivo

### Descrição Geral
SchedulingService gerencia integração com sistema de agendamento (Scheduling System) para consulta de agendamentos de consultas/procedimentos, confirmação de presença, verificação de disponibilidade de agenda médica e busca de slots disponíveis para remarcação.

### Criticidade do Negócio
- **Validação de Presença:** Confirmar comparecimento do paciente antes de iniciar faturamento
- **Compliance ANS:** RN-259 exige registro de data/hora de atendimento real (não agendada)
- **Controle de No-Show:** Taxa de não comparecimento média 15% (R$ 250/consulta perdida)
- **Impacto Financeiro:** Faturamento só ocorre se atendimento confirmado (presença física)

### Dependências Críticas
```
SchedulingService
├── SchedulingClient (HTTP REST API)
├── HL7 v2.x (SIU^S12 - appointment notification)
├── FHIR R4 (Appointment resource)
└── TASY ERP (patient registration)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados
```java
@Service
@RequiredArgsConstructor  // Constructor injection
private final SchedulingClient schedulingClient;
@Value("${scheduling.api-key}")  // Externalized config
```

**Rationale:**
- **Constructor Injection:** Facilita testes unitários
- **@Value para API Key:** Rotação de credenciais sem rebuild
- **Multiparameter queries:** Flexibilidade para buscar por paciente, médico, data ou status

### Trade-offs
| Decisão | Pro | Contra | Mitigação |
|---------|-----|--------|-----------|
| REST API (não HL7 nativo) | Simples, HTTP-based | Não recebe SIU messages em tempo real | SchedulingClient abstrai HL7 via gateway |
| Query methods sem paginação | API simples | Pode retornar muitos resultados | Roadmap: adicionar page/size parameters |
| RuntimeException propagation | Código limpo | Dificulta tratamento específico | Criar `SchedulingIntegrationException` custom |
| Sem Circuit Breaker | Implementação simples | Falha scheduler pode impactar faturamento | **CRÍTICO:** Adicionar em próxima sprint |

---

## III. Regras de Negócio Identificadas

### RN-SCH-01: Consulta de Agendamentos com Filtros
```java
public List<AppointmentDTO> queryAppointments(
    String patientId,
    String practitionerId,
    LocalDate date,
    String status)
```

**Lógica:**
1. Chama `schedulingClient.queryAppointments(patientId, practitionerId, date, status, schedulingApiKey)`
2. Todos os parâmetros são opcionais (podem ser null)
3. Retorna lista de agendamentos que correspondem aos filtros
4. Lança `RuntimeException` se falha na comunicação

**Business Context:**
- Buscar agendamentos do dia para check-in de pacientes
- Listar agenda do médico para planejamento de atendimentos
- Verificar histórico de agendamentos do paciente

**Exemplos de Uso:**
```java
// Buscar todos agendamentos de um paciente
queryAppointments("PAT-001234", null, null, null)

// Buscar agenda de um médico em uma data específica
queryAppointments(null, "DR-12345", LocalDate.of(2024, 1, 15), null)

// Buscar agendamentos confirmados de hoje
queryAppointments(null, null, LocalDate.now(), "booked")
```

**Status de Agendamento:**
| Status | Descrição | Faturável? |
|--------|-----------|------------|
| proposed | Proposta de agendamento | ❌ |
| pending | Aguardando confirmação | ❌ |
| booked | Confirmado pelo paciente | ⚠️ Aguarda chegada |
| arrived | Paciente chegou (check-in) | ✅ Iniciar faturamento |
| fulfilled | Atendimento concluído | ✅ Fechar conta |
| cancelled | Cancelado pelo paciente | ❌ |
| noshow | Paciente não compareceu | ❌ Taxa de no-show |

---

### RN-SCH-02: Recuperação de Agendamento Específico
```java
public AppointmentDTO getAppointmentById(String appointmentId)
```

**Lógica:**
1. Chama `schedulingClient.getAppointmentById(appointmentId, schedulingApiKey)`
2. Retorna detalhes completos do agendamento
3. Lança `RuntimeException` se agendamento não encontrado

**Business Context:**
- Validar dados do agendamento antes de iniciar atendimento
- Verificar tipo de procedimento agendado vs realizado (glosa por divergência)

**Exemplo:**
```json
{
  "appointmentId": "APT-2024-001234",
  "patientId": "PAT-001234",
  "practitionerId": "DR-12345",
  "specialtyCode": "010101",
  "specialtyName": "Cardiologia",
  "appointmentDate": "2024-01-15",
  "appointmentTime": "10:00",
  "duration": 30,
  "status": "booked",
  "reasonCode": "TUSS-4.03.01.12-0",
  "reasonName": "Consulta em Cardiologia",
  "insuranceId": "UNIMED-123"
}
```

---

### RN-SCH-03: Confirmação de Agendamento (Check-in)
```java
public AppointmentDTO confirmAppointment(String appointmentId)
```

**Lógica:**
1. Chama `schedulingClient.confirmAppointment(appointmentId, schedulingApiKey)`
2. Atualiza status de `booked` → `arrived` (paciente chegou)
3. Registra timestamp de check-in
4. Retorna agendamento atualizado

**Business Context:**
- **CRÍTICO:** Check-in é gatilho para início do faturamento
- Registra horário real de chegada (compliance RN-259 ANS)
- Diferença >30min entre agendado e chegada gera alerta de atraso

**Impacto no Fluxo:**
```
1. Paciente chega na recepção
   ↓
2. Recepcionista confirma presença
   ↓
3. confirmAppointment(appointmentId) → status="arrived"
   ↓
4. Trigger: Camunda inicia processo "Billing Cycle"
   ↓
5. Cria Encounter (atendimento) no TASY
   ↓
6. Faturamento iniciado
```

**Regra ANS:** RN-259 - Data/hora de atendimento deve ser hora real (não agendada).

---

### RN-SCH-04: Consulta de Agenda do Profissional
```java
public List<ScheduleDTO> getPractitionerSchedule(
    String practitionerId,
    LocalDate startDate,
    LocalDate endDate)
```

**Lógica:**
1. Chama `schedulingClient.getPractitionerSchedule(practitionerId, startDate, endDate, schedulingApiKey)`
2. Retorna lista de schedules (blocos de disponibilidade)
3. Cada schedule contém: scheduleId, dayOfWeek, startTime, endTime, location

**Business Context:**
- Planejamento de capacidade: quantos pacientes podem ser atendidos por dia
- Validação de overbooking: não agendar mais pacientes que a capacidade
- Integração com escala médica (plantões, férias, ausências)

**Exemplo:**
```json
[
  {
    "scheduleId": "SCH-DR12345-001",
    "practitionerId": "DR-12345",
    "dayOfWeek": "MONDAY",
    "startTime": "08:00",
    "endTime": "12:00",
    "location": "Consultório 201",
    "capacity": 8,
    "booked": 6
  }
]
```

---

### RN-SCH-05: Busca de Slots Disponíveis
```java
public List<SlotDTO> getAvailableSlots(
    String scheduleId,
    LocalDate startDate,
    LocalDate endDate)
```

**Lógica:**
1. Chama `schedulingClient.getAvailableSlots(scheduleId, startDate, endDate, "free", schedulingApiKey)`
2. Retorna lista de slots livres (30min cada)
3. Usado para remarcação de consultas canceladas

**Business Context:**
- Paciente cancela consulta → sistema oferece novos slots disponíveis
- Reduzir taxa de no-show: facilitar remarcação imediata

**Exemplo:**
```json
[
  {
    "slotId": "SLOT-001",
    "scheduleId": "SCH-DR12345-001",
    "date": "2024-01-20",
    "startTime": "09:30",
    "endTime": "10:00",
    "status": "free"
  },
  {
    "slotId": "SLOT-002",
    "scheduleId": "SCH-DR12345-001",
    "date": "2024-01-20",
    "startTime": "11:00",
    "endTime": "11:30",
    "status": "free"
  }
]
```

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Check-in de Paciente com Agendamento
```
1. Paciente chega na recepção às 10:05
   (agendamento: 10:00)
   ↓
2. Recepcionista busca agendamento:
   queryAppointments("PAT-001234", null, LocalDate.now(), "booked")
   ↓
3. Sistema retorna: APT-2024-001234 - Dr. Silva - 10:00
   ↓
4. Recepcionista confirma presença:
   confirmAppointment("APT-2024-001234")
   ↓
5. Sistema atualiza status: "booked" → "arrived"
   Registra check-in: 10:05 (5min atraso)
   ↓
6. Camunda recebe evento "AppointmentArrived"
   ↓
7. Inicia processo "Billing Cycle"
   ↓
8. Cria Encounter no TASY com timestamp real: 10:05
```

**Compliance:** RN-259 ANS exige timestamp real (10:05), não agendado (10:00).

---

### Cenário 2: Validação de Procedimento Agendado vs Realizado
```
1. Paciente agendado para: "Consulta Cardiologia" (TUSS 4.03.01.12-0)
   ↓
2. Durante atendimento, médico realiza: "ECG" (TUSS 4.13.01.01-0)
   ↓
3. Sistema detecta divergência:
   getAppointmentById(appointmentId) → reasonCode: "4.03.01.12-0"
   Encounter.procedureCodes → ["4.03.01.12-0", "4.13.01.01-0"]
   ↓
4. Alerta de glosa potencial:
   "ECG não estava no agendamento original"
   ↓
5. Regra de negócio:
   - Consulta com ECG: ACEITO (procedimento complementar)
   - Consulta sem consulta: GLOSA (só faturou ECG)
   ↓
6. Sistema sugere:
   "Adicionar consulta (4.03.01.12-0) ao faturamento"
```

---

### Cenário 3: Remarcação de Consulta Cancelada
```
1. Paciente cancela consulta de 15/01/2024 10:00
   ↓
2. Sistema busca slots disponíveis na próxima semana:
   getPractitionerSchedule("DR-12345", LocalDate.of(2024, 1, 20), LocalDate.of(2024, 1, 27))
   ↓
3. Para cada schedule, busca slots livres:
   getAvailableSlots("SCH-DR12345-001", LocalDate.of(2024, 1, 20), LocalDate.of(2024, 1, 27))
   ↓
4. Sistema exibe opções ao paciente:
   - 20/01 09:30 ✓
   - 20/01 11:00 ✓
   - 22/01 14:00 ✓
   ↓
5. Paciente escolhe 20/01 09:30
   ↓
6. Sistema cria novo agendamento e confirma
```

---

## V. Validações e Constraints

### Validações de Negócio

**RN-VAL-01: Status Válido para Faturamento**
```java
boolean podeIniciarFaturamento = appointment.status.equals("arrived")
                               || appointment.status.equals("fulfilled");
```

**RN-VAL-02: Check-in Dentro da Janela de Tempo**
```java
LocalDateTime agendado = appointment.appointmentDateTime;
LocalDateTime checkIn = LocalDateTime.now();
long minutosAtraso = ChronoUnit.MINUTES.between(agendado, checkIn);

if (minutosAtraso > 60) {
    // Alerta: paciente com >1h de atraso (possível no-show)
    sendLateArrivalAlert(appointment);
}
```

**RN-VAL-03: Validação de Overbooking**
```java
ScheduleDTO schedule = getSchedule(scheduleId);
int agendamentosConfirmados = queryAppointments(null, practitionerId, date, "booked").size();

if (agendamentosConfirmados >= schedule.capacity) {
    throw new OverbookingException("Capacidade máxima atingida");
}
```

---

## VI. Cálculos e Algoritmos

### Algoritmo: Calcular Taxa de No-Show
```java
public double calculateNoShowRate(String practitionerId, LocalDate startDate, LocalDate endDate) {
    List<AppointmentDTO> allAppointments = queryAppointments(null, practitionerId, null, null)
        .stream()
        .filter(apt -> !apt.date.isBefore(startDate) && !apt.date.isAfter(endDate))
        .toList();

    long totalBooked = allAppointments.stream()
        .filter(apt -> "booked".equals(apt.status) || "noshow".equals(apt.status) || "arrived".equals(apt.status))
        .count();

    long noShows = allAppointments.stream()
        .filter(apt -> "noshow".equals(apt.status))
        .count();

    return totalBooked > 0 ? (double) noShows / totalBooked * 100 : 0.0;
}
```

**Benchmark:** Taxa de no-show aceitável: <15%

---

## VII. Integrações de Sistema

### Integração SchedulingClient (HTTP REST)

| Método | Endpoint | Protocolo |
|--------|----------|-----------|
| `queryAppointments()` | `GET /api/appointments?patientId={id}&practitionerId={id}&date={date}&status={status}` | HTTP REST |
| `getAppointmentById()` | `GET /api/appointments/{id}` | HTTP REST |
| `confirmAppointment()` | `POST /api/appointments/{id}/confirm` | HTTP REST |
| `getPractitionerSchedule()` | `GET /api/schedules?practitionerId={id}&start={date}&end={date}` | HTTP REST |
| `getAvailableSlots()` | `GET /api/schedules/{id}/slots?start={date}&end={date}&status=free` | HTTP REST |

**Autenticação:**
```http
GET /api/appointments?patientId=PAT-001234
Authorization: Bearer ${scheduling.api-key}
```

---

## VIII. Tratamento de Erros e Exceções

### Exception Handling
```java
public List<AppointmentDTO> queryAppointments(...) {
    try {
        List<AppointmentDTO> appointments = schedulingClient.queryAppointments(...);
        log.info("Retrieved {} appointments", appointments.size());
        return appointments;
    } catch (Exception e) {
        log.error("Failed to query appointments", e);
        throw new RuntimeException("Failed to query appointments", e);
    }
}
```

### Cenários de Erro

| Erro | Causa | Ação | Impacto |
|------|-------|------|---------|
| Scheduling system offline | Manutenção | Retry manual após 10min | Bloqueio de check-in |
| Appointment not found | ID inválido | Retornar erro 404 | Recepção deve buscar novamente |
| Overbooking detected | Capacidade excedida | Bloquear agendamento | Protege contra sobrecarga |
| API key inválida | Credencial expirada | Atualizar property file | Bloqueio total |

---

## IX. Dados e Modelos

### Modelo: AppointmentDTO
```java
@Data
public class AppointmentDTO {
    private String appointmentId;
    private String patientId;
    private String practitionerId;
    private String specialtyCode;
    private String specialtyName;
    private LocalDate appointmentDate;
    private LocalTime appointmentTime;
    private int duration; // minutos
    private String status; // proposed, pending, booked, arrived, fulfilled, cancelled, noshow
    private String reasonCode; // TUSS code
    private String reasonName;
    private String insuranceId;
    private String location;
    private LocalDateTime checkInTime;
}
```

---

### Modelo: ScheduleDTO
```java
@Data
public class ScheduleDTO {
    private String scheduleId;
    private String practitionerId;
    private String dayOfWeek; // MONDAY, TUESDAY, ...
    private LocalTime startTime;
    private LocalTime endTime;
    private String location;
    private int capacity; // máximo de pacientes
    private int booked; // agendamentos confirmados
}
```

---

### Modelo: SlotDTO
```java
@Data
public class SlotDTO {
    private String slotId;
    private String scheduleId;
    private LocalDate date;
    private LocalTime startTime;
    private LocalTime endTime;
    private String status; // free, busy, busy-tentative
}
```

---

## X. Compliance e Regulamentações

### RN-259 ANS - Registro de Data/Hora Real de Atendimento
**Obrigação:** Data/hora de atendimento deve ser a hora real (não a agendada).

**Implementação:**
```java
public AppointmentDTO confirmAppointment(String appointmentId) {
    // status: booked → arrived
    // Registra LocalDateTime.now() como checkInTime
}
```

**Referência:** [RN-259 ANS](http://www.ans.gov.br/component/legislacao/?view=legislacao&task=TextoLei&format=raw&id=MjI0NQ==)

---

### LGPD - Art. 11 (Dados Sensíveis de Saúde)
**Obrigação:** Agendamentos contêm dados de saúde (especialidade, motivo).

**Medidas:**
- API Key para autenticação
- Logging sem dados sensíveis
- Sem cache de appointments

---

## XI. Camunda 7 → 8 Migration

### Impacto: BAIXO
SchedulingService é **stateless**.

### Mudanças Necessárias

**Camunda 8 (Zeebe):**
```java
@ZeebeWorker(type = "confirm-appointment")
public void confirmAppointment(JobClient client, ActivatedJob job) {
    String appointmentId = (String) job.getVariablesAsMap().get("appointmentId");
    AppointmentDTO appointment = confirmAppointment(appointmentId);

    client.newCompleteCommand(job.getKey())
        .variables(Map.of(
            "appointmentStatus", appointment.getStatus(),
            "checkInTime", appointment.getCheckInTime()
        ))
        .send()
        .join();
}
```

### Estimativa: 3 horas

---

## XII. DDD Bounded Context

### Context: **Scheduling & Appointment Management**

### Aggregates
```
Appointment Aggregate Root
├── AppointmentId
├── Patient (reference)
├── Practitioner (reference)
├── DateTime (scheduled)
├── CheckInTime (actual)
├── Status (booked, arrived, fulfilled)
└── ReasonCode (TUSS)
```

### Domain Events
```java
public class AppointmentConfirmedEvent {
    private String appointmentId;
    private LocalDateTime checkInTime;
}

public class AppointmentNoShowEvent {
    private String appointmentId;
    private String practitionerId;
}
```

---

## XIII. Performance e SLAs

### SLAs Definidos

| Operação | SLA Latência | SLA Throughput |
|----------|--------------|----------------|
| queryAppointments | < 400ms | 200 req/s |
| getAppointmentById | < 250ms | 300 req/s |
| confirmAppointment | < 500ms | 150 req/s |
| getPractitionerSchedule | < 600ms | 100 req/s |
| getAvailableSlots | < 800ms | 80 req/s |

### Complexidade Ciclomática

| Método | CC | Classificação |
|--------|----|--------------|
| `queryAppointments()` | 4 | LOW |
| `getAppointmentById()` | 4 | LOW |
| `confirmAppointment()` | 4 | LOW |
| `getPractitionerSchedule()` | 4 | LOW |
| `getAvailableSlots()` | 4 | LOW |

**Média:** CC = 4.0 ✓

---

### Melhorias Recomendadas

**1. Circuit Breaker**
**2. Cache de Schedules (1h TTL)**
**3. Paginação em queryAppointments()**

---

## Conclusão

SchedulingService é componente **essencial** para validar presença de pacientes e iniciar faturamento. Check-in (confirmAppointment) é gatilho crítico do processo. Compliance RN-259 ANS exige timestamp real. Ausência de Circuit Breaker é RISCO. Migração Camunda 8: 3h. Próximas melhorias: Circuit Breaker + Cache + Paginação.
