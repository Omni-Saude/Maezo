# SAGA Compensation System - Visão Geral Completa

**Módulo**: Domain Models - Compensation
**Versão**: 2.0
**Última Atualização**: 2026-01-12
**Status**: Produção ✅

---

## 1. ARQUITETURA GERAL

### 1.1. Padrão SAGA

O sistema implementa o **padrão SAGA** para transações distribuídas, garantindo consistência eventual através de compensações coordenadas.

```
Normal Flow:        Step 1 → Step 2 → Step 3 → Step 4 ✓
                      ↓        ↓        ↓        ↓
Compensation Flow:  C1 ← -----C2 ← ----C3 ← ----FAIL
                   (LIFO - Last In First Out)
```

### 1.2. Componentes Principais

#### **Domain Layer** (Strategy Pattern)
- `CompensationStrategy` - Interface base (Strategy Pattern)
- 13 estratégias concretas - Uma por módulo BPMN
- `CompensationContext` - Value Object com dados de contexto
- `ValidationResult` - Value Object para validações
- `CompensationStrategyRegistry` - Registry Pattern para lookup

#### **Infrastructure Layer** (Adapters)
- `CompensationDelegateAdapter` - Single orchestrator para Camunda
- `ExecutionContextMapper` - Mapeia Camunda → Domain
- `SagaCompensationService` - Serviço de orquestração SAGA

#### **Delegates Layer** (Legacy - Em migração)
- 6 delegates específicos (Appeal, Allocation, Recovery, etc.)
- Sendo migrados para o sistema unificado de estratégias

---

## 2. INVENTÁRIO COMPLETO DE DOCUMENTAÇÃO

### 2.1. Base Domain Models (4 Documentos)

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `RN-CompensationStrategy.md` | Interface de estratégia | ✅ Completo |
| `RN-CompensationContext.md` | Value Object de contexto | ✅ Completo |
| `RN-ValidationResult.md` | Value Object de validação | ✅ Completo |
| `RN-CompensationStrategyRegistry.md` | Registry de estratégias | ✅ Completo |

### 2.2. Concrete Strategies (13 Estratégias)

#### Pré-Atendimento e Elegibilidade
| Estratégia | Tipo | Arquivo |
|------------|------|---------|
| `EligibilityCompensationStrategy` | ELIGIBILITY | `src/main/java/.../strategies/` |
| `AgendamentoCompensationStrategy` | AGENDAMENTO | `src/main/java/.../strategies/` |
| `PreAtendimentoCompensationStrategy` | PRE_ATENDIMENTO | `src/main/java/.../strategies/` |

#### Atendimento e Codificação
| Estratégia | Tipo | Arquivo |
|------------|------|---------|
| `AtendimentoClinicoCompensationStrategy` | ATENDIMENTO_CLINICO | `src/main/java/.../strategies/` |
| `CodingCompensationStrategy` | CODING | `src/main/java/.../strategies/` |
| `AuditoriaMedicaCompensationStrategy` | AUDITORIA_MEDICA | `src/main/java/.../strategies/` |

#### Faturamento e Cobrança
| Estratégia | Tipo | Arquivo |
|------------|------|---------|
| `ClaimCompensationStrategy` | CLAIM | `src/main/java/.../strategies/` |
| `FaturamentoCompensationStrategy` | FATURAMENTO | `src/main/java/.../strategies/` |
| `GlosasCompensationStrategy` | GLOSAS | `src/main/java/.../strategies/` |
| `CobrancaCompensationStrategy` | COBRANCA | `src/main/java/.../strategies/` |
| `RecebimentoPagamentoCompensationStrategy` | RECEBIMENTO_PAGAMENTO | `src/main/java/.../strategies/` |

#### Gestão e Análise
| Estratégia | Tipo | Arquivo |
|------------|------|---------|
| `AnaliseIndicadoresCompensationStrategy` | ANALISE_INDICADORES | `src/main/java/.../strategies/` |
| `MelhoriaContinuaCompensationStrategy` | MELHORIA_CONTINUA | `src/main/java/.../strategies/` |

### 2.3. Compensation Delegates (6 Delegates Específicos)

| Delegate | Operação Compensada | Arquivo |
|----------|---------------------|---------|
| `CompensateAppealDelegate` | Recurso de glosa | `src/main/java/.../delegates/compensation/` |
| `CompensateAllocationDelegate` | Alocação de pagamento | `src/main/java/.../delegates/compensation/` |
| `CompensateRecoveryDelegate` | Recuperação de glosa | `src/main/java/.../delegates/compensation/` |
| `CompensateProvisionDelegate` | Criação de provisão | `src/main/java/.../delegates/compensation/` |
| `CompensateCalculateDelegate` | Cálculo de faturamento | `src/main/java/.../delegates/compensation/` |
| `CompensateSubmitDelegate` | Submissão de guia | `src/main/java/.../delegates/compensation/` |

### 2.4. Infrastructure (3 Componentes)

| Componente | Responsabilidade | Arquivo |
|------------|------------------|---------|
| `CompensationDelegateAdapter` | Orchestrator único Camunda | `src/main/java/.../adapters/camunda/` |
| `ExecutionContextMapper` | Mapping Camunda ↔ Domain | `src/main/java/.../adapters/camunda/` |
| `SagaCompensationService` | Orquestração SAGA completa | `src/main/java/.../service/` |

---

## 3. FLUXO DE EXECUÇÃO

### 3.1. Normal Flow (Processo Principal)

```
1. Process Start
    ↓
2. Execute Business Operation (Success)
    ↓
3. Register Compensation Action in SAGA
    SagaCompensationService.recordCompensationAction(...)
    ↓
4. Continue to Next Step
    ↓
5. Process Complete
```

### 3.2. Compensation Flow (Erro Detectado)

```
1. Business Operation FAILS
    ↓
2. BPMN Error Boundary Event Triggered
    ↓
3. Compensation Orchestrator Invoked
    CompensationDelegateAdapter.execute()
    ↓
4. Strategy Lookup
    registry.getStrategy(compensationType)
    ↓
5. Context Mapping
    mapper.toCompensationContext(execution)
    ↓
6. Validation
    strategy.validate(context)
    ↓
7. Execute Compensation
    strategy.execute(context)  // LIFO order
    ↓
8. Update SAGA State
    SagaCompensationService.compensate(transactionId)
    ↓
9. Process Ends (Compensated State)
```

### 3.3. Ordem LIFO de Compensação

```
Transaction Start
  Step 1: Verify Eligibility     → C1 (last)
  Step 2: Generate Claim          → C2
  Step 3: Submit to Payer         → C3
  Step 4: Record Payment (FAIL!)  → C4 (first)

Compensation Order:
  C4: Compensate Payment Recording
  C3: Compensate Claim Submission
  C2: Compensate Claim Generation
  C1: Compensate Eligibility Check
```

---

## 4. PADRÕES DE DESIGN UTILIZADOS

### 4.1. Domain Layer

| Padrão | Uso | Benefício |
|--------|-----|-----------|
| **Strategy** | `CompensationStrategy` interface | Troca de algoritmos de compensação |
| **Registry** | `CompensationStrategyRegistry` | Lookup centralizado |
| **Value Object** | `CompensationContext`, `ValidationResult` | Imutabilidade e tipo-segurança |
| **Result Pattern** | `ValidationResult` | Evita exceções para fluxo de controle |

### 4.2. Infrastructure Layer

| Padrão | Uso | Benefício |
|--------|-----|-----------|
| **Adapter** | `CompensationDelegateAdapter` | Isola domain de Camunda |
| **Mapper** | `ExecutionContextMapper` | Conversão Camunda ↔ Domain |
| **Facade** | `SagaCompensationService` | Interface simplificada para SAGA |
| **SAGA** | Todo o sistema | Transações distribuídas |

---

## 5. INTEGRAÇÃO CAMUNDA

### 5.1. BPMN Configuration

```xml
<!-- Compensation Task -->
<serviceTask id="compensateEligibility"
             name="Compensate Eligibility"
             camunda:delegateExpression="${compensation}">
  <extensionElements>
    <camunda:inputOutput>
      <camunda:inputParameter name="compensationType">ELIGIBILITY</camunda:inputParameter>
      <camunda:inputParameter name="eligibilityCheckId">${eligibilityCheckId}</camunda:inputParameter>
      <camunda:inputParameter name="patientId">${patientId}</camunda:inputParameter>
    </camunda:inputOutput>
  </extensionElements>
</serviceTask>

<!-- Error Boundary Event -->
<boundaryEvent id="errorBoundary" attachedToRef="verifyEligibility">
  <errorEventDefinition errorRef="Error_EligibilityFailed"/>
</boundaryEvent>

<!-- Compensation Association -->
<association sourceRef="errorBoundary" targetRef="compensateEligibility"/>
```

### 5.2. Process Variables

| Variável | Tipo | Descrição | Obrigatória |
|----------|------|-----------|-------------|
| `compensationType` | String | Tipo de compensação (ex: "ELIGIBILITY") | ✅ Sim |
| `<entityId>` | String | ID da entidade sendo compensada | ✅ Sim |
| `originalStatus` | String | Status antes da operação | ⚠️ Condicional |
| `amount` | Double | Valor monetário (se aplicável) | ⚠️ Condicional |

---

## 6. GARANTIAS E PROPRIEDADES

### 6.1. Garantias SAGA

| Propriedade | Status | Descrição |
|-------------|--------|-----------|
| **Idempotência** | ✅ Garantida | Mesma compensação pode executar N vezes |
| **Atomicidade** | ✅ Por operação | Cada compensação é atômica |
| **Isolamento** | ✅ Entre compensações | Compensações não interferem |
| **Consistência** | ⚠️ Eventual | Não ACID, mas eventual consistency |
| **Durabilidade** | ✅ Via Camunda | Estado persistido no Camunda |

### 6.2. Tratamento de Falhas

```
Compensation Success:
  → Transaction marked as COMPENSATED
  → Process ends gracefully
  → Audit trail recorded

Compensation Failure:
  → Transaction marked as COMPENSATION_FAILED
  → Error logged with details
  → Manual intervention required
  → Alert triggered
```

---

## 7. MONITORAMENTO E OBSERVABILIDADE

### 7.1. Métricas Recomendadas

```java
// Compensations executadas
Counter: compensation.executions.total
  Tags: [type, status]

// Tempo de execução
Timer: compensation.execution.duration
  Tags: [type]

// Falhas de compensação
Counter: compensation.failures.total
  Tags: [type, reason]

// Estratégias registradas
Gauge: compensation.strategies.registered
```

### 7.2. Logs Estruturados

```java
// Início
log.info("[COMPENSATION] Starting: type={}, processInstance={}, context={}",
    compensationType, processInstanceId, context);

// Sucesso
log.info("[COMPENSATION] Completed: type={}, processInstance={}, duration={}ms",
    compensationType, processInstanceId, duration);

// Falha
log.error("[COMPENSATION] Failed: type={}, processInstance={}, error={}",
    compensationType, processInstanceId, error, exception);
```

### 7.3. Audit Trail

```sql
-- Tabela de auditoria SAGA
CREATE TABLE saga_compensation_audit (
    id UUID PRIMARY KEY,
    transaction_id VARCHAR(255) NOT NULL,
    compensation_type VARCHAR(100) NOT NULL,
    action_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- PENDING, COMPLETED, FAILED
    compensation_data JSONB,
    error_message TEXT,
    executed_at TIMESTAMP NOT NULL,
    executed_by VARCHAR(255),
    process_instance_id VARCHAR(255),
    INDEX idx_transaction (transaction_id),
    INDEX idx_process (process_instance_id),
    INDEX idx_status (status)
);
```

---

## 8. ROADMAP DE MIGRAÇÃO

### 8.1. Estado Atual (Janeiro 2026)

| Componente | Status | Observação |
|------------|--------|------------|
| Domain Models | ✅ Completo | 13 estratégias + base classes |
| Strategy Registry | ✅ Completo | Auto-discovery funcionando |
| Adapter Pattern | ✅ Completo | Single orchestrator |
| Legacy Delegates | ⚠️ Ativo | 6 delegates específicos |
| SAGA Service | ✅ Completo | Orquestração completa |

### 8.2. Próximos Passos

**Sprint 7 (Q1 2026)**:
- [ ] Migrar delegates específicos para estratégias
- [ ] Deprecar delegates legados
- [ ] Unificar todos os tipos de compensação

**Sprint 8 (Q2 2026)**:
- [ ] Implementar retry automático com backoff
- [ ] Circuit breakers para sistemas externos
- [ ] Dead letter queue para compensações falhas

**Sprint 9 (Q3 2026)**:
- [ ] Dashboard de monitoramento SAGA
- [ ] Métricas avançadas de performance
- [ ] Alertas proativos de falhas

---

## 9. REFERÊNCIAS

### 9.1. Documentação Interna
- `AI_SWARM_EXECUTION_PROTOCOL.txt` (linhas 150-221)
- Architecture Decision Records (ADR-005: SAGA Pattern)
- Camunda 7 Best Practices Guide

### 9.2. Literatura Técnica
- Garcia-Molina, H., & Salem, K. (1987). "Sagas" - ACM SIGMOD
- Gamma et al. (1994). "Design Patterns" - Strategy Pattern
- Richardson, C. (2018). "Microservices Patterns" - SAGA Chapter
- Evans, E. (2003). "Domain-Driven Design" - Value Objects

### 9.3. Código Fonte
```
src/main/java/com/hospital/revenuecycle/
├── domain/
│   └── compensation/
│       ├── CompensationStrategy.java
│       ├── CompensationContext.java
│       ├── ValidationResult.java
│       ├── CompensationStrategyRegistry.java
│       └── strategies/ (13 classes)
├── adapters/
│   └── camunda/
│       ├── CompensationDelegateAdapter.java
│       └── ExecutionContextMapper.java
├── delegates/
│   └── compensation/ (6 legacy delegates)
└── service/
    └── SagaCompensationService.java
```

---

## 10. CONTATOS E SUPORTE

**Arquitetura**: Hive Mind Architecture Agent
**Desenvolvimento**: Revenue Cycle Development Team
**Suporte**: Swarm Coordinator (swarm-1768222388973-gj49an3qn)

**Documentação Atualizada**: 2026-01-12 14:07 UTC
**Próxima Revisão**: 2026-04-12

---

## ANEXOS

### A. Checklist de Implementação

```markdown
Nova Compensação - Checklist:
- [ ] Criar classe de estratégia implementando CompensationStrategy
- [ ] Anotar com @Component para auto-discovery
- [ ] Implementar getCompensationType() com tipo único
- [ ] Implementar execute() com lógica de rollback
- [ ] Implementar validate() se necessário
- [ ] Adicionar testes unitários
- [ ] Adicionar testes de integração
- [ ] Documentar em RN-<Nome>CompensationStrategy.md
- [ ] Configurar no BPMN
- [ ] Validar idempotência
- [ ] Adicionar logs estruturados
- [ ] Configurar métricas
- [ ] Deploy e validação
```

### B. Template de Estratégia

```java
package com.hospital.revenuecycle.domain.compensation.strategies;

import com.hospital.revenuecycle.domain.compensation.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * Compensation strategy for [OPERATION] rollback.
 *
 * Rollback Actions:
 * - [Action 1]
 * - [Action 2]
 * - [Action 3]
 *
 * @author Revenue Cycle Development Team
 * @version 1.0
 * @since [DATE]
 */
@Slf4j
@Component
public class [Name]CompensationStrategy implements CompensationStrategy {

    @Override
    public void execute(CompensationContext context) throws Exception {
        String entityId = context.getVariable("entityId", String.class);

        log.info("[COMPENSATION] Executing [OPERATION] rollback - EntityId: {}, ProcessInstance: {}",
                entityId, context.getProcessInstanceId());

        // Step 1: [Description]
        step1(entityId);

        // Step 2: [Description]
        step2(entityId);

        log.info("[COMPENSATION] [OPERATION] rollback completed - EntityId: {}, ProcessInstance: {}",
                entityId, context.getProcessInstanceId());
    }

    @Override
    public String getCompensationType() {
        return "[UNIQUE_TYPE]";
    }

    @Override
    public ValidationResult validate(CompensationContext context) {
        String entityId = context.getVariable("entityId", String.class);
        if (entityId == null) {
            return ValidationResult.failure("entityId is required");
        }
        return ValidationResult.success();
    }

    private void step1(String entityId) {
        log.debug("Step 1 for entity: {}", entityId);
        // TODO: Implementation
    }

    private void step2(String entityId) {
        log.debug("Step 2 for entity: {}", entityId);
        // TODO: Implementation
    }
}
```

---

**FIM DO DOCUMENTO**
