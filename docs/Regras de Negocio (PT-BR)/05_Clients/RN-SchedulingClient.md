# RN-SchedulingClient - Cliente de Integração com Sistema de Agendamento

**Categoria**: Cliente REST (Feign Client)
**Prioridade**: Alta
**Status**: Implementado
**Versão**: 1.0.0

---

## 1. VISÃO GERAL

### 1.1 Propósito
Cliente Feign para integração com sistema externo de agendamento utilizando **HL7 FHIR R4** padrão de recursos `Appointment`, `Schedule` e `Slot`.

### 1.2 Escopo
- Consulta e gerenciamento de agendamentos
- Verificação de disponibilidade de horários
- Confirmação e cancelamento de consultas
- Atualização de status de appointments
- Consulta de grades de atendimento

### 1.3 Contexto no Ciclo da Receita
- **Entrada**: Check-in do paciente dispara processo de faturamento
- **Gatilho**: Status "arrived" inicia captação de dados
- **Dependência**: EligibilityClient valida cobertura antes de confirmação

---

## 2. ESPECIFICAÇÃO TÉCNICA

### 2.1 Localização
```
Arquivo: src/main/java/com/hospital/revenuecycle/integration/scheduling/SchedulingClient.java
Pacote: com.hospital.revenuecycle.integration.scheduling
```

### 2.2 Configuração
```yaml
# application.yml
scheduling:
  base-url: https://scheduling-api.hospital.com/fhir/R4
  api-key: ${SCHEDULING_API_KEY}
  timeout:
    connect: 5000
    read: 10000
```

### 2.3 Recursos FHIR Utilizados

#### 2.3.1 Appointment Resource
Representa um compromisso agendado entre paciente e prestador.

**Status do Appointment:**
- `proposed`: Proposto mas não confirmado
- `pending`: Aguardando confirmação
- `booked`: Confirmado
- `arrived`: Paciente chegou (TRIGGER BILLING)
- `fulfilled`: Atendimento concluído
- `cancelled`: Cancelado
- `noshow`: Paciente não compareceu

#### 2.3.2 Schedule Resource
Define disponibilidade de um prestador/recurso.

#### 2.3.3 Slot Resource
Representa um período específico disponível para agendamento.

---

## 3. REGRAS DE NEGÓCIO

### RN-SCHED-001: Consulta de Agendamentos
**Descrição**: Busca appointments com filtros opcionais
**Entrada**:
- `patientId` (opcional): Identificador do paciente
- `practitionerId` (opcional): Identificador do profissional
- `date` (opcional): Data do agendamento
- `status` (opcional): Status do appointment

**Saída**: Lista de `AppointmentDTO`

**Validações**:
- API key válida no header `Authorization`
- Ao menos um filtro deve ser fornecido
- Data no formato ISO 8601

**Endpoint**: `GET /Appointment`

```java
@GetMapping("/Appointment")
List<AppointmentDTO> queryAppointments(
    @RequestParam(required = false) String patientId,
    @RequestParam(required = false) String practitionerId,
    @RequestParam(required = false) LocalDate date,
    @RequestParam(required = false) String status,
    @RequestHeader("Authorization") String apiKey
);
```

---

### RN-SCHED-002: Busca por ID
**Descrição**: Recupera appointment específico
**Entrada**: `appointmentId`
**Saída**: `AppointmentDTO`
**Validações**:
- ID válido e existente
- API key válida

**Endpoint**: `GET /Appointment/{appointmentId}`

```java
@GetMapping("/Appointment/{appointmentId}")
AppointmentDTO getAppointmentById(
    @PathVariable("appointmentId") String appointmentId,
    @RequestHeader("Authorization") String apiKey
);
```

---

### RN-SCHED-003: Criar Agendamento
**Descrição**: Cria novo appointment
**Entrada**: `AppointmentDTO`
**Saída**: `AppointmentDTO` com ID gerado

**Validações**:
- Paciente e profissional identificados
- Data/hora futura
- Slot disponível
- Duração válida (minutesDuration > 0)
- Participantes obrigatórios presentes

**Endpoint**: `POST /Appointment`

```java
@PostMapping("/Appointment")
AppointmentDTO createAppointment(
    @RequestBody AppointmentDTO appointment,
    @RequestHeader("Authorization") String apiKey
);
```

**Payload Exemplo**:
```json
{
  "status": "proposed",
  "serviceCategory": "General Medicine",
  "appointmentType": "ROUTINE",
  "start": "2026-01-15T09:00:00",
  "end": "2026-01-15T09:30:00",
  "minutesDuration": 30,
  "patientId": "Patient/12345",
  "practitionerId": "Practitioner/67890",
  "locationId": "Location/clinic-1",
  "participants": [
    {
      "type": "patient",
      "actorId": "Patient/12345",
      "required": "required",
      "status": "accepted"
    },
    {
      "type": "practitioner",
      "actorId": "Practitioner/67890",
      "required": "required",
      "status": "accepted"
    }
  ]
}
```

---

### RN-SCHED-004: Atualizar Status
**Descrição**: Atualiza status do appointment
**Entrada**:
- `appointmentId`
- `status` (proposed, pending, booked, arrived, fulfilled, cancelled, noshow)

**Saída**: `AppointmentDTO` atualizado

**Validações**:
- Transição de status válida
- Status permitido no sistema

**Endpoint**: `PATCH /Appointment/{appointmentId}`

```java
@PatchMapping("/Appointment/{appointmentId}")
AppointmentDTO updateAppointmentStatus(
    @PathVariable("appointmentId") String appointmentId,
    @RequestParam("status") String status,
    @RequestHeader("Authorization") String apiKey
);
```

**Fluxo de Status Permitido**:
```
proposed → pending → booked → arrived → fulfilled
              ↓         ↓         ↓
           cancelled  cancelled  noshow
```

---

### RN-SCHED-005: Consultar Grade de Atendimento
**Descrição**: Busca schedule de um profissional
**Entrada**:
- `practitionerId` (actor)
- `startDate`
- `endDate`

**Saída**: Lista de `ScheduleDTO`

**Validações**:
- Intervalo de datas válido (endDate >= startDate)
- Período não superior a 90 dias

**Endpoint**: `GET /Schedule`

```java
@GetMapping("/Schedule")
List<ScheduleDTO> getPractitionerSchedule(
    @RequestParam("actor") String practitionerId,
    @RequestParam("date") LocalDate startDate,
    @RequestParam("_date") LocalDate endDate,
    @RequestHeader("Authorization") String apiKey
);
```

---

### RN-SCHED-006: Consultar Slots Disponíveis
**Descrição**: Busca horários disponíveis em uma grade
**Entrada**:
- `scheduleId`
- `startDate`
- `endDate`
- `status` (free)

**Saída**: Lista de `SlotDTO`

**Validações**:
- Schedule ativo
- Status "free" para disponíveis
- Slots não expirados

**Endpoint**: `GET /Slot`

```java
@GetMapping("/Slot")
List<SlotDTO> getAvailableSlots(
    @RequestParam("schedule") String scheduleId,
    @RequestParam("start") LocalDate startDate,
    @RequestParam("end") LocalDate endDate,
    @RequestParam("status") String status,
    @RequestHeader("Authorization") String apiKey
);
```

---

### RN-SCHED-007: Confirmar Agendamento
**Descrição**: Operação FHIR `$confirm` - altera status para "booked"
**Entrada**: `appointmentId`
**Saída**: `AppointmentDTO` confirmado (status=booked)

**Validações**:
- Appointment em status "pending" ou "proposed"
- Slot ainda disponível
- Elegibilidade verificada (integração com EligibilityClient)

**Endpoint**: `POST /Appointment/{appointmentId}/$confirm`

```java
@PostMapping("/Appointment/{appointmentId}/$confirm")
AppointmentDTO confirmAppointment(
    @PathVariable("appointmentId") String appointmentId,
    @RequestHeader("Authorization") String apiKey
);
```

**Processo de Confirmação**:
1. Verificar elegibilidade do paciente
2. Validar disponibilidade do slot
3. Atualizar status para "booked"
4. Notificar paciente e profissional
5. Registrar no sistema de faturamento

---

### RN-SCHED-008: Cancelar Agendamento
**Descrição**: Operação FHIR `$cancel` - cancela appointment
**Entrada**:
- `appointmentId`
- `reason` (motivo do cancelamento)

**Saída**: `AppointmentDTO` cancelado (status=cancelled)

**Validações**:
- Motivo obrigatório
- Appointment não pode estar em status "fulfilled"
- Política de cancelamento respeitada (antecedência mínima)

**Endpoint**: `POST /Appointment/{appointmentId}/$cancel`

```java
@PostMapping("/Appointment/{appointmentId}/$cancel")
AppointmentDTO cancelAppointment(
    @PathVariable("appointmentId") String appointmentId,
    @RequestParam("reason") String reason,
    @RequestHeader("Authorization") String apiKey
);
```

**Motivos de Cancelamento**:
- `patient-request`: Solicitação do paciente
- `provider-unavailable`: Profissional indisponível
- `facility-closed`: Estabelecimento fechado
- `weather`: Condições climáticas
- `no-show-previous`: Histórico de falta
- `other`: Outros motivos

---

## 4. INTEGRAÇÃO COM CICLO DA RECEITA

### 4.1 Trigger de Faturamento
```java
// Quando status = "arrived"
if (appointment.getStatus().equals("arrived")) {
    // Inicia processo de captação
    registrarTriagem(appointment);
    verificarElegibilidade(appointment.getPatientId());
    gerarProntuario(appointment);
    iniciarCaptacao(appointment.getId());
}
```

### 4.2 Fluxo de Integração
```
1. Paciente agenda (status: proposed)
2. Sistema confirma (status: booked)
3. Verificação de elegibilidade
4. Paciente chega (status: arrived) ← TRIGGER
5. Triagem e prontuário
6. Atendimento realizado
7. Captação de procedimentos
8. Geração de conta
9. Atualiza status (fulfilled)
```

---

## 5. TRATAMENTO DE ERROS

### 5.1 Códigos de Retorno HTTP
- **200 OK**: Operação bem-sucedida
- **201 Created**: Appointment criado
- **400 Bad Request**: Dados inválidos
- **401 Unauthorized**: API key inválida
- **404 Not Found**: Appointment não encontrado
- **409 Conflict**: Slot não disponível
- **422 Unprocessable Entity**: Regra de negócio violada

### 5.2 Estratégias de Retry
```java
@Retryable(
    value = {FeignException.class},
    maxAttempts = 3,
    backoff = @Backoff(delay = 1000)
)
```

---

## 6. SEGURANÇA

### 6.1 Autenticação
- API Key via header `Authorization: Bearer {token}`
- Configuração em `SchedulingClientConfig`

### 6.2 Headers FHIR
```
Authorization: Bearer {api-key}
Accept: application/fhir+json
Content-Type: application/fhir+json
```

---

## 7. MONITORAMENTO

### 7.1 Métricas
- Taxa de confirmação de appointments
- Taxa de no-show
- Tempo médio de resposta do cliente
- Falhas de integração

### 7.2 Logs
```java
log.info("Appointment {} updated to status {}", appointmentId, newStatus);
log.warn("No slots available for schedule {} on date {}", scheduleId, date);
log.error("Failed to create appointment: {}", errorMessage);
```

---

## 8. DEPENDÊNCIAS

### 8.1 Bibliotecas
- Spring Cloud OpenFeign
- Jackson (serialização FHIR JSON)
- Lombok

### 8.2 Integrações
- **EligibilityClient**: Verifica cobertura antes de confirmar
- **TriagemService**: Registra check-in e dados iniciais
- **ProntuarioService**: Cria/atualiza prontuário

---

## 9. REFERÊNCIAS

### 9.1 Padrões
- HL7 FHIR R4: https://hl7.org/fhir/R4/appointment.html
- FHIR Schedule: https://hl7.org/fhir/R4/schedule.html
- FHIR Slot: https://hl7.org/fhir/R4/slot.html

### 9.2 Documentação Relacionada
- `RN-SchedulingClientConfig.md`: Configuração do cliente
- `RN-AppointmentDTO.md`: Estrutura de dados do appointment
- `RN-ScheduleDTO.md`: Estrutura de grade de atendimento
- `RN-SlotDTO.md`: Estrutura de horário disponível
- `RN-ParticipantDTO.md`: Participantes do appointment

---

## 10. EXEMPLOS DE USO

### 10.1 Buscar Appointments de um Paciente
```java
@Service
public class AppointmentService {
    @Autowired
    private SchedulingClient schedulingClient;

    public List<AppointmentDTO> getPatientAppointments(String patientId) {
        return schedulingClient.queryAppointments(
            patientId,
            null,
            LocalDate.now(),
            "booked",
            "Bearer " + apiKey
        );
    }
}
```

### 10.2 Criar e Confirmar Appointment
```java
public AppointmentDTO agendarConsulta(AppointmentRequest request) {
    // 1. Criar appointment
    AppointmentDTO appointment = new AppointmentDTO();
    appointment.setPatientId(request.getPatientId());
    appointment.setPractitionerId(request.getPractitionerId());
    appointment.setStart(request.getDateTime());
    appointment.setEnd(request.getDateTime().plusMinutes(30));
    appointment.setStatus("proposed");

    AppointmentDTO created = schedulingClient.createAppointment(
        appointment, "Bearer " + apiKey
    );

    // 2. Verificar elegibilidade
    if (eligibilityClient.checkCoverage(request.getPatientId())) {
        // 3. Confirmar
        return schedulingClient.confirmAppointment(
            created.getId(), "Bearer " + apiKey
        );
    }

    return created;
}
```

### 10.3 Processar Check-In
```java
public void processarCheckIn(String appointmentId) {
    // 1. Atualizar status para "arrived"
    AppointmentDTO appointment = schedulingClient.updateAppointmentStatus(
        appointmentId, "arrived", "Bearer " + apiKey
    );

    // 2. Iniciar fluxo de faturamento
    triagemService.registrar(appointment);
    elegibilidadeService.verificar(appointment.getPatientId());
    contaService.iniciar(appointmentId);

    log.info("Check-in processado para appointment {}", appointmentId);
}
```

---

**Última Atualização**: 2026-01-12
**Responsável**: Equipe de Integração
**Revisores**: Arquitetura, Faturamento
