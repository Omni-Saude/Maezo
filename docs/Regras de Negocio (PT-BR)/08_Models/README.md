# Modelos de Domínio - Documentação Completa

**Diretório:** `docs/Regras de Negocio (PT-BR)/08_Models/`

**Data:** 2026-01-12

**Versão:** 1.0

---

## 1. VISÃO GERAL

Este diretório contém a documentação completa de 24 modelos de domínio críticos do sistema de ciclo de receita hospitalar:

- **13 Estratégias de Compensação SAGA** - Padrões de rollback distribuído
- **11 Modelos de Domínio** - Entidades core do sistema

---

## 2. ESTRATÉGIAS DE COMPENSAÇÃO SAGA (13 arquivos)

### 2.1 Propósito
Implementam o padrão SAGA para transações distribuídas, garantindo consistência eventual através de compensações semânticas quando ocorrem falhas.

### 2.2 Estratégias Documentadas

| # | Estratégia | Tipo de Compensação | Arquivo |
|---|------------|---------------------|---------|
| 1 | **AgendamentoCompensationStrategy** | AGENDAMENTO | RN-AgendamentoCompensationStrategy.md |
| 2 | **AnaliseIndicadoresCompensationStrategy** | ANALISE_INDICADORES | RN-AnaliseIndicadoresCompensationStrategy.md |
| 3 | **AtendimentoClinicoCompensationStrategy** | ATENDIMENTO_CLINICO | RN-AtendimentoClinicoCompensationStrategy.md |
| 4 | **AuditoriaMedicaCompensationStrategy** | AUDITORIA_MEDICA | RN-AuditoriaMedicaCompensationStrategy.md |
| 5 | **ClaimCompensationStrategy** | CLAIM | RN-ClaimCompensationStrategy.md |
| 6 | **CodingCompensationStrategy** | CODING | RN-CodingCompensationStrategy.md |
| 7 | **CobrancaCompensationStrategy** | COBRANCA | RN-CobrancaCompensationStrategy.md |
| 8 | **EligibilityCompensationStrategy** | ELIGIBILITY | RN-EligibilityCompensationStrategy.md |
| 9 | **FaturamentoCompensationStrategy** | FATURAMENTO | RN-FaturamentoCompensationStrategy.md |
| 10 | **GlosasCompensationStrategy** | GLOSAS | RN-GlosasCompensationStrategy.md |
| 11 | **MelhoriaContinuaCompensationStrategy** | MELHORIA_CONTINUA | RN-MelhoriaContinuaCompensationStrategy.md |
| 12 | **PreAtendimentoCompensationStrategy** | PRE_ATENDIMENTO | RN-PreAtendimentoCompensationStrategy.md |
| 13 | **RecebimentoPagamentoCompensationStrategy** | RECEBIMENTO_PAGAMENTO | RN-RecebimentoPagamentoCompensationStrategy.md |

### 2.3 Padrão Comum de Compensação

Todas as estratégias seguem o mesmo padrão de implementação:

```java
@Component
public class [Name]CompensationStrategy implements CompensationStrategy {

    @Override
    public void execute(CompensationContext context) throws Exception {
        // 1. Extrair variáveis do contexto
        // 2. Log início de compensação
        // 3. Executar passos de rollback
        // 4. Log conclusão
    }

    @Override
    public String getCompensationType() {
        return "[TIPO]";
    }
}
```

### 2.4 Ações de Compensação por Estratégia

#### AGENDAMENTO
- Cancelar agendamento de paciente
- Liberar slot de tempo alocado
- Restaurar disponibilidade de recursos

#### ANALISE_INDICADORES
- Remover registros analíticos
- Deletar relatórios gerados
- Limpar cache de métricas
- Resetar dados de dashboard

#### ATENDIMENTO_CLINICO
- Void de encontro clínico
- Marcar dados clínicos como cancelados
- Remover da fila de faturamento

#### AUDITORIA_MEDICA
- Remover códigos médicos atribuídos
- Reverter achados de auditoria
- Limpar flags de validação de codificação
- Resetar para status não-codificado

#### CLAIM
- Cancelar claim no sistema de faturamento
- Reverter submissão TISS
- Liberar holds financeiros
- Notificar departamento de faturamento
- Atualizar status para CANCELLED

#### CODING
- Remover atribuições de códigos
- Liberar task de codificação para fila
- Notificar equipe de codificação
- Limpar cache de codificação

#### COBRANCA
- Cancelar atividades de cobrança
- Parar lembretes automatizados
- Remover contas de cobrança
- Restaurar status pré-cobrança

#### ELIGIBILITY
- Liberar holds de autorização
- Cancelar verificação de elegibilidade
- Notificar provedor de seguros
- Limpar cache de elegibilidade

#### FATURAMENTO
- Cancelar claim submetido
- Void claim no sistema do pagador
- Remover do rastreamento
- Restaurar status para rascunho

#### GLOSAS
- Abandonar processo de recurso
- Remover documentação de recurso
- Resetar status de denial
- Limpar rastreamento de recurso

#### MELHORIA_CONTINUA
- Reverter melhorias de processo
- Remover mudanças de otimização
- Restaurar workflows originais
- Limpar métricas de melhoria

#### PRE_ATENDIMENTO
- Reverter status de verificação de elegibilidade
- Remover registros de pré-autorização
- Limpar dados em cache de elegibilidade

#### RECEBIMENTO_PAGAMENTO
- Reverter postagem de pagamento
- Void de recibos de pagamento
- Restaurar saldo de conta
- Limpar reconciliação de pagamento

---

## 3. MODELOS DE DOMÍNIO (11 arquivos)

### 3.1 Modelos de Pagamento e Reconciliação

| Modelo | Domínio | Propósito | Arquivo |
|--------|---------|-----------|---------|
| **PaymentAllocation** | collection | Gestão de alocação de pagamentos | RN-PaymentAllocation.md |
| **ReconciliationDifference** | collection | Tracking de diferenças na reconciliação | RN-ReconciliationDifference.md |

#### PaymentAllocation - Características

```java
public class PaymentAllocation {
    // Identifiers
    String allocationId;
    String paymentId;

    // Financial
    BigDecimal paymentAmount;
    BigDecimal totalAllocated;
    BigDecimal unallocatedAmount;

    // Strategy
    String allocationStrategy;  // FIFO, OLDEST_FIRST, MANUAL
    List<Allocation> allocations;

    // Status
    String allocationStatus;    // PENDING, COMPLETED, REVERSED

    // Business Logic
    boolean isFullyAllocated();
    boolean isValid();
    long countAffectedInvoices();
}
```

**Estratégias de Alocação:**
- **FIFO:** Primeiro a entrar, primeiro a sair
- **OLDEST_FIRST:** Faturas vencidas há mais tempo
- **MANUAL:** Alocação manual pelo operador
- **PROPORTIONAL:** Distribuição proporcional

**Tipos de Alocação:**
- PRINCIPAL - Valor principal
- INTEREST - Juros acumulados
- FEE - Taxas administrativas
- PENALTY - Multas por atraso

#### ReconciliationDifference - Características

```java
public class ReconciliationDifference {
    // Identifiers
    String differenceId;
    String reconciliationBatchId;
    String paymentId;
    String invoiceId;

    // Amounts
    BigDecimal expectedAmount;
    BigDecimal actualAmount;
    BigDecimal differenceAmount;

    // Classification
    String differenceType;
    String differenceCategory;

    // Resolution
    String resolutionStatus;
    String resolutionAction;
    Boolean adjustmentRequired;
    BigDecimal adjustmentAmount;

    // Business Logic
    boolean isMaterial(BigDecimal threshold);
    boolean isResolved();
    BigDecimal calculateVariancePercentage();
    boolean isOverpayment();
}
```

**Tipos de Diferença:**
- OVERPAYMENT - Pagamento a maior
- UNDERPAYMENT - Pagamento a menor
- TIMING_DIFFERENCE - Diferença de timing
- CODING_ERROR - Erro de codificação

**Status de Resolução:**
- PENDING - Aguardando resolução
- INVESTIGATING - Em investigação
- RESOLVED - Resolvido
- CLOSED - Fechado

### 3.2 Modelos de Agendamento

| Modelo | Domínio | Propósito | Arquivo |
|--------|---------|-----------|---------|
| **AgendaSlot** | scheduling | Slots de agenda de provedores | RN-AgendaSlot.md |
| **AppointmentConfirmation** | scheduling | Confirmação e lembretes | RN-AppointmentConfirmation.md |

#### AgendaSlot - Características

```java
public class AgendaSlot {
    // Provider Information
    String providerId;
    String providerName;
    String specialty;

    // Location
    String facilityId;
    String roomNumber;

    // Time
    LocalDateTime slotStart;
    LocalDateTime slotEnd;
    Integer durationMinutes;

    // Availability
    Boolean isAvailable;
    Boolean isOverbooked;
    Integer maxOverbooking;
    Integer currentBookings;

    // Business Logic
    boolean canBook();
    boolean isFuture();
    boolean isReservationExpired();
}
```

**Status de Slot:**
- AVAILABLE - Disponível para agendamento
- RESERVED - Reservado temporariamente
- BOOKED - Agendado confirmado
- BLOCKED - Bloqueado (feriado, manutenção)

#### AppointmentConfirmation - Características

```java
public class AppointmentConfirmation {
    // Appointment Reference
    String confirmationId;
    String appointmentId;

    // Patient Contact
    String patientId;
    String patientPhone;
    String patientEmail;

    // Confirmation Process
    String confirmationStatus;
    String confirmationMethod;  // SMS, EMAIL, PHONE, APP
    List<ReminderAttempt> reminderAttempts;

    // Patient Response
    String patientResponse;     // CONFIRMED, CANCELLED, RESCHEDULED
    String cancellationReason;
    LocalDateTime rescheduledTo;

    // Business Logic
    boolean isPending();
    boolean hasReachedMaxAttempts(int maxAttempts);
    boolean isNextReminderDue(int reminderIntervalHours);
}
```

**Métodos de Confirmação:**
- SMS - Mensagem de texto
- EMAIL - Email automático
- PHONE - Ligação telefônica
- APP - Notificação no app

### 3.3 Modelos de Triagem e Atendimento

| Modelo | Domínio | Propósito | Arquivo |
|--------|---------|-----------|---------|
| **TriageRecord** | triage | Registro de triagem inicial | RN-TriageRecord.md |
| **AttendanceRouting** | triage | Roteamento de pacientes | RN-AttendanceRouting.md |

#### TriageRecord - Características

```java
public class TriageRecord {
    // Patient Information
    String patientId;
    String patientName;
    String chiefComplaint;

    // Triage Assessment
    VitalSigns vitalSigns;
    Integer painScale;          // 0-10
    String acuityLevel;         // CRITICAL, EMERGENCY, URGENT, SEMI-URGENT, NON-URGENT
    Integer priorityScore;      // 0-10

    // Clinical Flags
    Boolean isolationRequired;
    Boolean fastTrackEligible;
    String redFlags;

    // Routing
    String recommendedSpecialty;
    Integer estimatedWaitTimeMinutes;

    // Business Logic
    boolean isCritical();
    boolean hasAbnormalVitals();
}
```

**Níveis de Acuidade:**
- CRITICAL (Red) - Ameaça à vida imediata
- EMERGENCY (Orange) - Emergência
- URGENT (Yellow) - Urgente
- SEMI-URGENT (Green) - Semi-urgente
- NON-URGENT (Blue) - Não urgente

**Sinais Vitais:**
```java
public static class VitalSigns {
    Double temperatureCelsius;
    Integer heartRateBpm;
    Integer respiratoryRate;
    Integer bloodPressureSystolic;
    Integer bloodPressureDiastolic;
    Integer oxygenSaturation;
    String consciousnessLevel;  // ALERT, VERBAL, PAIN, UNRESPONSIVE
}
```

#### AttendanceRouting - Características

```java
public class AttendanceRouting {
    // Routing Information
    String routingId;
    String triageId;
    String patientId;

    // Locations
    String sourceLocation;
    String destinationLocation;
    String routingReason;

    // Assignment
    String assignedProviderId;
    String specialtyRequired;
    String routingPriority;

    // Timing
    LocalDateTime routingTimestamp;
    LocalDateTime arrivalAtDestination;
    Integer estimatedDurationMinutes;

    // Transport
    String transportMethod;     // WALKING, WHEELCHAIR, STRETCHER, AMBULANCE
    List<String> specialRequirements;

    // Business Logic
    boolean hasArrived();
    long calculateDelayMinutes();
    boolean isOverdue();
}
```

**Prioridades de Roteamento:**
- IMMEDIATE - Imediato (crítico)
- HIGH - Alta (emergência)
- MEDIUM - Média (urgente)
- LOW - Baixa (rotina)

**Métodos de Transporte:**
- WALKING - Caminhando
- WHEELCHAIR - Cadeira de rodas
- STRETCHER - Maca
- AMBULANCE - Ambulância interna

---

## 4. PADRÕES ARQUITETURAIS

### 4.1 Domain-Driven Design (DDD)
Todos os modelos seguem princípios DDD:
- **Entities:** Identidade única e ciclo de vida
- **Value Objects:** Imutáveis e comparáveis por valor
- **Aggregates:** Consistência transacional
- **Domain Services:** Lógica de negócio complexa

### 4.2 SAGA Pattern
Estratégias de compensação implementam SAGA:
- **Compensação Semântica:** Reverter efeitos de negócio
- **Idempotência:** Seguro executar múltiplas vezes
- **Eventual Consistency:** Consistência eventual garantida

### 4.3 Event Sourcing
Modelos suportam event sourcing:
- Histórico completo de mudanças
- Auditoria detalhada
- Capacidade de replay

---

## 5. INTEGRAÇÕES

### 5.1 Sistemas Internos
- **Camunda 7:** Orquestração de processos
- **PostgreSQL:** Persistência de dados
- **Redis:** Cache distribuído
- **Kafka:** Event streaming

### 5.2 Sistemas Externos
- **TASY:** Sistema clínico hospitalar
- **TISS:** Padrão de troca de informações
- **Operadoras:** ANS, SulAmérica, Bradesco Saúde
- **Sistemas de Pagamento:** Gateway de pagamentos

---

## 6. CONFORMIDADE REGULATÓRIA

### 6.1 Padrões Brasileiros
- **TISS 4.0:** Troca de informações em saúde suplementar
- **ANS:** Regulamentação da ANS
- **CFM:** Resolução de codificação médica

### 6.2 Padrões Internacionais
- **HL7 FHIR:** Interoperabilidade de dados de saúde
- **ICD-10:** Classificação de doenças
- **SNOMED CT:** Terminologia clínica

### 6.3 Privacidade e Segurança
- **LGPD:** Lei Geral de Proteção de Dados
- **HIPAA (referência):** Privacy and Security Rules
- **ISO 27001:** Gestão de segurança da informação

---

## 7. MÉTRICAS E KPIs

### 7.1 Métricas de Compensação
- Taxa de sucesso de compensações: > 99%
- Tempo médio de compensação: < 5 segundos
- Volume de compensações por dia
- Taxa de falhas em compensação

### 7.2 Métricas de Negócio
- Taxa de alocação de pagamentos: > 95%
- Tempo de reconciliação: < 24 horas
- Taxa de confirmação de agendamentos: > 80%
- Tempo de triagem: < 15 minutos

---

## 8. TESTES E QUALIDADE

### 8.1 Cobertura de Testes
- Unit Tests: > 90%
- Integration Tests: > 80%
- End-to-End Tests: Cenários críticos

### 8.2 Testes de Compensação
Cada estratégia deve ter testes para:
- Compensação bem-sucedida
- Compensação com falha parcial
- Idempotência
- Dados não encontrados
- Timeout

### 8.3 Testes de Domínio
Cada modelo deve ter testes para:
- Validações de negócio
- Cálculos e fórmulas
- Estados e transições
- Integridade de dados

---

## 9. DOCUMENTAÇÃO INDIVIDUAL

Cada arquivo RN-[Nome].md contém:
1. **Visão Geral:** Descrição e propósito
2. **Estrutura de Dados:** Atributos e tipos
3. **Regras de Negócio:** RN-XXX-YYY com critérios
4. **Fluxo de Execução:** Sequência de passos
5. **Integrações:** Sistemas e APIs
6. **Validações:** Obrigatórias e de consistência
7. **Auditoria:** Logs e rastreamento
8. **Tratamento de Erros:** Exceções e retry
9. **Métricas:** KPIs e monitoramento
10. **Conformidade:** Regulamentações
11. **Testes:** Casos de teste
12. **Referências:** Código e docs relacionados

---

## 10. MANUTENÇÃO E EVOLUÇÃO

### 10.1 Versionamento
- Documentação segue versionamento semântico
- Mudanças breaking: Major version
- Novas features: Minor version
- Bug fixes: Patch version

### 10.2 Processo de Atualização
1. Proposta de mudança (RFC)
2. Revisão técnica
3. Atualização de documentação
4. Atualização de testes
5. Deploy e monitoramento

---

## 11. REFERÊNCIAS

### 11.1 Código Fonte
- `/src/main/java/com/hospital/revenuecycle/domain/compensation/strategies/`
- `/src/main/java/com/hospital/revenuecycle/domain/*/`

### 11.2 Documentação Relacionada
- `docs/Regras de Negocio (PT-BR)/` - Outras regras de negócio
- `docs/COMPLETE_JAVA_INVENTORY_CATEGORIZATION.md` - Inventário completo
- `docs/research/ddd_patterns_healthcare.json` - Padrões DDD

### 11.3 Recursos Externos
- [SAGA Pattern](https://microservices.io/patterns/data/saga.html)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [Camunda 7 Compensation](https://docs.camunda.org/manual/7.17/reference/bpmn20/events/cancel-and-compensation-events/)

---

**Status:** 24 modelos documentados

**Última Atualização:** 2026-01-12

**Mantenedor:** Hive Mind Swarm - Coder Agent

**Contato:** Via swarm coordination memory
