# RN-AgendamentoCompensationStrategy - Estratégia de Compensação para Agendamento

**Arquivo:** `src/main/java/com/hospital/revenuecycle/domain/compensation/strategies/AgendamentoCompensationStrategy.java`

**Tipo:** Estratégia de Compensação SAGA

**Versão:** 2.0

**Última Atualização:** 2025-12-25

---

## 1. VISÃO GERAL

### 1.1 Descrição
Implementa a estratégia de compensação (rollback) para transações de agendamento em arquitetura SAGA distribuída. Garante que agendamentos de pacientes sejam revertidos corretamente em caso de falha no processo.

### 1.2 Propósito
- Reverter agendamentos criados em transações falhadas
- Liberar recursos alocados (horários, salas, equipamentos)
- Restaurar disponibilidade da agenda
- Manter integridade transacional distribuída

### 1.3 Padrão de Implementação
- **Padrão:** SAGA Compensation Strategy
- **Tipo:** Compensação Semântica
- **Escopo:** Transação Distribuída

---

## 2. REGRAS DE NEGÓCIO

### RN-AGCOMP-001: Cancelamento de Agendamento
**Descrição:** O sistema deve cancelar agendamentos de pacientes quando a compensação é executada.

**Critérios:**
- Verificar se appointmentId existe
- Marcar agendamento como CANCELADO
- Registrar motivo do cancelamento
- Preservar histórico para auditoria

**Implementação:**
```java
private void cancelAppointment(String appointmentId) {
    log.debug("Cancelling appointment: {}", appointmentId);
    // TODO: Integration with appointment system
}
```

### RN-AGCOMP-002: Liberação de Slot de Tempo
**Descrição:** O sistema deve liberar o slot de tempo alocado ao agendamento.

**Critérios:**
- Identificar slot associado ao appointmentId
- Marcar slot como DISPONÍVEL
- Atualizar contadores de disponibilidade
- Notificar sistema de agendamento

**Implementação:**
```java
private void releaseTimeSlot(String appointmentId) {
    log.debug("Releasing time slot for appointment: {}", appointmentId);
    // TODO: Integration with scheduling system
}
```

### RN-AGCOMP-003: Restauração de Recursos
**Descrição:** O sistema deve restaurar disponibilidade de recursos alocados (médico, sala, equipamento).

**Critérios:**
- Identificar recursos reservados
- Liberar reservas de recursos
- Atualizar capacidade disponível
- Permitir realocação para outros agendamentos

**Implementação:**
```java
private void restoreResourceAvailability(String appointmentId) {
    log.debug("Restoring resource availability for appointment: {}", appointmentId);
    // TODO: Integration with resource management
}
```

---

## 3. ESTRUTURA DE DADOS

### 3.1 Variáveis de Contexto Utilizadas
```java
CompensationContext {
    String appointmentId;      // ID do agendamento a compensar
    String processInstanceId;  // ID da instância do processo
}
```

### 3.2 Tipo de Compensação
```java
@Override
public String getCompensationType() {
    return "AGENDAMENTO";
}
```

---

## 4. FLUXO DE EXECUÇÃO

### 4.1 Sequência de Compensação
```
1. Cancelar Agendamento (appointmentId)
   ↓
2. Liberar Slot de Tempo
   ↓
3. Restaurar Disponibilidade de Recursos
   ↓
4. Log de Conclusão
```

### 4.2 Exemplo de Execução
```java
@Override
public void execute(CompensationContext context) throws Exception {
    String appointmentId = context.getVariable("appointmentId", String.class);

    log.info("[COMPENSATION] Executing agendamento rollback - AppointmentId: {}", appointmentId);

    // Step 1: Cancel appointment
    if (appointmentId != null) {
        cancelAppointment(appointmentId);
    }

    // Step 2: Release time slot
    releaseTimeSlot(appointmentId);

    // Step 3: Restore resource availability
    restoreResourceAvailability(appointmentId);

    log.info("[COMPENSATION] Agendamento rollback completed - AppointmentId: {}", appointmentId);
}
```

---

## 5. INTEGRAÇÕES NECESSÁRIAS

### 5.1 Sistema de Agendamento
- **Operação:** Cancelamento de agendamento
- **Método:** API REST ou Message Queue
- **Endpoint:** `/api/appointments/{id}/cancel`

### 5.2 Sistema de Gestão de Agenda
- **Operação:** Liberação de slot
- **Método:** API REST
- **Endpoint:** `/api/slots/{id}/release`

### 5.3 Sistema de Gestão de Recursos
- **Operação:** Restauração de disponibilidade
- **Método:** API REST
- **Endpoint:** `/api/resources/restore`

---

## 6. REQUISITOS DE AUDITORIA

### 6.1 Log de Compensação
```
[COMPENSATION] Executing agendamento rollback - AppointmentId: {appointmentId}, ProcessInstance: {processInstanceId}
[COMPENSATION] Agendamento rollback completed - AppointmentId: {appointmentId}, ProcessInstance: {processInstanceId}
```

### 6.2 Informações Rastreáveis
- ID do agendamento compensado
- Timestamp de execução
- ID da instância do processo
- Recursos liberados

---

## 7. TRATAMENTO DE ERROS

### 7.1 Exceções Possíveis
- `AppointmentNotFoundException`: Agendamento não encontrado
- `SlotReleaseException`: Falha ao liberar slot
- `ResourceRestoreException`: Falha ao restaurar recursos

### 7.2 Estratégia de Retry
- Tentativas automáticas: 3x
- Intervalo entre tentativas: 5 segundos
- Escalação para compensação manual após falhas

---

## 8. MÉTRICAS E MONITORAMENTO

### 8.1 Indicadores
- Taxa de sucesso de compensação
- Tempo médio de execução
- Número de compensações por período
- Taxa de falhas na compensação

### 8.2 Alertas
- Falha em compensação crítica
- Tempo de execução excedendo SLA
- Recursos não liberados corretamente

---

## 9. CONFORMIDADE

### 9.1 Padrões Aplicáveis
- **SAGA Pattern:** Compensação semântica
- **Distributed Transactions:** Eventual consistency
- **ACID-BASE:** BASE transactions

### 9.2 Requisitos de Auditoria
- Registro completo de ações de compensação
- Rastreabilidade de recursos liberados
- Histórico de falhas e sucessos

---

## 10. IMPLEMENTAÇÃO FUTURA

### 10.1 Melhorias Planejadas
- [ ] Integração com sistema de agendamento TASY
- [ ] Notificação automática ao paciente
- [ ] Dashboard de monitoramento de compensações
- [ ] Compensação automática em batch

### 10.2 Dependências
- Sistema de agendamento externo
- Sistema de gestão de recursos
- Serviço de notificações

---

## 11. REFERÊNCIAS

### 11.1 Código Relacionado
- `CompensationStrategy.java` - Interface base
- `CompensationContext.java` - Contexto de compensação
- `SagaCompensationService.java` - Orquestrador de compensações

### 11.2 Documentação Externa
- SAGA Pattern - Microservices.io
- Distributed Transactions Best Practices
- Camunda 7 Compensation Events

---

**Data de Criação:** 2026-01-12
**Autor:** Hive Mind Swarm - Coder Agent
**Revisão:** v1.0
