# RN - LISIntegrationDelegate

**ID:** RN-CLINICAL-005
**Camada:** Delegates (Laboratory Integration)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** HIGH
**BPMN Reference:** `${lisIntegrationDelegate}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável pela integração com LIS (Laboratory Information System) usando recursos HL7 FHIR. Recupera pedidos de exames laboratoriais, resultados, identifica valores críticos e valida completude para disparo de processos de cobrança.

### 1.2 Objetivo
- Recuperar pedidos laboratoriais via FHIR ServiceRequest
- Buscar resultados via FHIR DiagnosticReport + Observation
- Validar se todos resultados estão finais
- Identificar valores críticos/anormais
- Extrair metadados para cobrança
- Calcular estatísticas de pedidos e resultados

### 1.3 Contexto no Fluxo de Negócio
Este delegate integra dados laboratoriais ao prontuário clínico, permitindo validação de completude de documentação e fornecendo dados essenciais para codificação e cobrança de exames.

---

## 2. Regras de Negócio

### RN-CLINICAL-005.1: Verificação de Existência de Pedidos
**Descrição:** Verifica se o atendimento possui pedidos de exames laboratoriais

**Condição:**
```java
List<LISOrderDTO> orders = lisService.getOrdersByEncounter(encounterId);

if (orders.isEmpty()) {
    setVariable(execution, "has_lab_orders", false);
    setVariable(execution, "lis_all_final", true); // Sem pedidos = completo
    return;
}
```

**Impacto:** Se não há pedidos, delegate finaliza rapidamente sem erro

---

### RN-CLINICAL-005.2: Coleta de Resultados por Pedido
**Descrição:** Recupera resultados para cada pedido de exame

**Ação:**
```java
for (LISOrderDTO order : orders) {
    List<LISResultDTO> orderResults = lisService.getResultsByOrder(order.getId());
    allResults.addAll(orderResults);
}
```

**Integração FHIR:**
- **Pedidos:** FHIR `ServiceRequest` resource (R4)
- **Resultados:** FHIR `DiagnosticReport` resource (R4)
- **Observações:** FHIR `Observation` resource (R4)

---

### RN-CLINICAL-005.3: Validação de Status Final
**Descrição:** Verifica se todos os resultados possuem status final

**Condição:**
```java
boolean allFinal = allResults.stream()
    .allMatch(result -> "final".equalsIgnoreCase(result.getStatus())
            || "amended".equalsIgnoreCase(result.getStatus())
            || "corrected".equalsIgnoreCase(result.getStatus()));
```

**Status Aceitos como Final:**
- `final`: Resultado final
- `amended`: Resultado corrigido/emendado
- `corrected`: Resultado com correção

**Status NÃO Finais:**
- `preliminary`: Resultado preliminar
- `registered`: Registrado mas sem resultado
- `partial`: Resultado parcial

**Impacto:** Variável `lis_all_final` determina se atendimento pode ser finalizado

---

### RN-CLINICAL-005.4: Extração de Códigos LOINC
**Descrição:** Extrai códigos LOINC dos testes para padronização

**Ação:**
```java
List<String> testCodes = orders.stream()
    .flatMap(order -> order.getTestCodes().stream())
    .distinct()
    .collect(Collectors.toList());
```

**LOINC (Logical Observation Identifiers Names and Codes):**
- Padrão internacional para identificação de testes laboratoriais
- Utilizado para interoperabilidade e cobrança
- Exemplo: `2339-0` (Glucose [Mass/volume] in Blood)

---

### RN-CLINICAL-005.5: Identificação de Valores Críticos
**Descrição:** Identifica valores anormais ou críticos que requerem atenção clínica

**Critérios de Anormalidade:**
```java
private boolean isAbnormal(String interpretation) {
    String code = interpretation.toUpperCase();
    return code.equals("A")     // Abnormal
        || code.equals("H")     // High
        || code.equals("L")     // Low
        || code.equals("HH")    // Critical High
        || code.equals("LL")    // Critical Low
        || code.equals("AA")    // Very Abnormal
        || code.startsWith("ABNORMAL")
        || code.startsWith("CRITICAL");
}
```

**Códigos de Interpretação (HL7 v2):**
- `N`: Normal
- `A`: Abnormal
- `H`: High (acima do normal)
- `L`: Low (abaixo do normal)
- `HH`: Critical High (alto crítico)
- `LL`: Critical Low (baixo crítico)
- `AA`: Very Abnormal

**Dados Capturados para Valores Críticos:**
```java
Map<String, Object> critical = new HashMap<>();
critical.put("result_id", result.getId());
critical.put("observation_id", obs.getId());
critical.put("test_code", obs.getCode());        // LOINC code
critical.put("test_name", obs.getDisplay());
critical.put("value", obs.getValue());
critical.put("unit", obs.getUnit());
critical.put("reference_range", obs.getReferenceRange());
critical.put("interpretation", obs.getInterpretation());
```

---

### RN-CLINICAL-005.6: Cálculo de Estatísticas
**Descrição:** Calcula métricas sobre pedidos e resultados

**Estatísticas Calculadas:**
```java
long completedOrders = orders.stream()
    .filter(order -> "completed".equalsIgnoreCase(order.getStatus()))
    .count();

long pendingOrders = orders.stream()
    .filter(order -> "active".equalsIgnoreCase(order.getStatus()))
    .count();
```

**Variáveis Geradas:**
- `lis_order_count`: Total de pedidos
- `lis_result_count`: Total de resultados
- `lis_completed_orders`: Pedidos completos
- `lis_pending_orders`: Pedidos pendentes

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `encounter_id` | String | ID do atendimento | "ENC-12345" |

### 3.2 Variáveis de Saída (Status)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `has_lab_orders` | Boolean | Atendimento possui pedidos laboratoriais | PROCESS |
| `lis_all_final` | Boolean | Todos resultados finais | PROCESS |

### 3.3 Variáveis de Saída (Dados)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `lis_orders` | List<Map> | Metadados dos pedidos | PROCESS |
| `lis_results` | List<Map> | Metadados dos resultados | PROCESS |
| `lis_test_codes` | List<String> | Códigos LOINC dos testes | PROCESS |
| `lis_critical_values` | List<Map> | Valores críticos/anormais | PROCESS |

### 3.4 Variáveis de Saída (Estatísticas)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `lis_order_count` | Integer | Total de pedidos | PROCESS |
| `lis_result_count` | Integer | Total de resultados | PROCESS |
| `lis_completed_orders` | Long | Pedidos completos | PROCESS |
| `lis_pending_orders` | Long | Pedidos pendentes | PROCESS |

### 3.5 Variáveis de Erro
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `lis_integration_error` | String | Mensagem de erro |

---

## 4. Estrutura de Dados

### 4.1 Order Metadata (lis_orders)
```json
{
  "order_id": "ORDER-123",
  "identifier": "LAB-2026-001",
  "status": "completed",
  "priority": "routine",
  "test_codes": ["2339-0", "2345-7"],
  "ordered_on": "2026-01-12T08:30:00",
  "ordering_provider_id": "DR-456"
}
```

### 4.2 Result Metadata (lis_results)
```json
{
  "result_id": "RESULT-789",
  "order_id": "ORDER-123",
  "status": "final",
  "code": "2339-0",
  "effective_date": "2026-01-12T10:00:00",
  "issued": "2026-01-12T11:30:00",
  "interpretation": "N",
  "conclusion": "Normal glucose levels",
  "observation_count": 1
}
```

### 4.3 Critical Values (lis_critical_values)
```json
{
  "result_id": "RESULT-789",
  "observation_id": "OBS-456",
  "test_code": "2339-0",
  "test_name": "Glucose",
  "value": "180",
  "unit": "mg/dL",
  "reference_range": "70-110 mg/dL",
  "interpretation": "H"
}
```

---

## 5. Integrações

### 5.1 LISService
**Métodos:**
- `getOrdersByEncounter(encounterId)`: Recupera pedidos do atendimento
- `getResultsByOrder(orderId)`: Recupera resultados de um pedido

**DTOs:**
- `LISOrderDTO`: Pedido de exame (FHIR ServiceRequest)
- `LISResultDTO`: Resultado de exame (FHIR DiagnosticReport)
- `ObservationDTO`: Observação individual (FHIR Observation)

---

### 5.2 FHIR Resources

#### ServiceRequest (Pedido)
```json
{
  "resourceType": "ServiceRequest",
  "id": "ORDER-123",
  "status": "completed",
  "intent": "order",
  "priority": "routine",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "2339-0"
    }]
  }
}
```

#### DiagnosticReport (Resultado)
```json
{
  "resourceType": "DiagnosticReport",
  "id": "RESULT-789",
  "status": "final",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "2339-0"
    }]
  },
  "conclusion": "Normal glucose levels"
}
```

#### Observation (Observação)
```json
{
  "resourceType": "Observation",
  "id": "OBS-456",
  "status": "final",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "2339-0",
      "display": "Glucose"
    }]
  },
  "valueQuantity": {
    "value": 95,
    "unit": "mg/dL"
  },
  "interpretation": [{
    "coding": [{
      "code": "N"
    }]
  }]
}
```

---

## 6. Tratamento de Erros

### 6.1 Exceções Técnicas
```java
catch (Exception e) {
    log.error("LIS integration failed - Process: {}, Error: {}",
        processInstanceId, e.getMessage(), e);

    setVariable(execution, "lis_integration_error", e.getMessage());
    setVariable(execution, "lis_all_final", false);

    throw new RuntimeException("Failed to integrate with LIS", e);
}
```

---

## 7. Conformidade e Auditoria

### 7.1 Regulamentações
- **HL7 FHIR R4:** Padrão de interoperabilidade
- **LOINC:** Padronização de códigos laboratoriais
- **ANS:** Documentação de exames para cobrança
- **LGPD:** Privacidade de dados médicos

### 7.2 Logs de Auditoria
```
INFO: Executing LISIntegrationDelegate - Process: {id}, Activity: {activity}
INFO: Retrieving LIS lab orders and results for encounter: {id}
INFO: Retrieved {count} LIS lab orders for encounter: {id}
INFO: Retrieved {count} LIS lab results for encounter: {id}
INFO: LIS result status - EncounterId: {id}, AllFinal: {status}
INFO: Identified {count} critical values for encounter: {id}
INFO: LIS integration completed - EncounterId: {id}, Orders: {count}, Results: {count}, AllFinal: {status}
```

---

## 8. Dependências

### 8.1 Serviços
- `LISService`: Integração com sistema laboratorial

### 8.2 DTOs
- `LISOrderDTO`: Pedido de exame
- `LISResultDTO`: Resultado de exame
- `ObservationDTO`: Observação FHIR

### 8.3 Delegates Relacionados
- `CompletenessCheckDelegate`: Valida completude de exames
- `FinalizarAtendimentoDelegate`: Verifica se todos exames estão finais

---

## 9. Requisitos Não-Funcionais

### 9.1 Performance
- Tempo médio de execução: < 3 segundos
- Timeout: 20 segundos

### 9.2 Idempotência
- **requiresIdempotency()**: `false`
- Operação de leitura, naturalmente idempotente

### 9.3 Disponibilidade
- Dependência: LIS (uptime > 99%)

---

## 10. Cenários de Teste

### 10.1 Cenário: Sem Pedidos Laboratoriais
**Dado:** Atendimento sem pedidos de exames
**Quando:** LISIntegrationDelegate executado
**Então:**
- `has_lab_orders = false`
- `lis_all_final = true`
- `lis_order_count = 0`

---

### 10.2 Cenário: Pedidos com Resultados Finais
**Dado:**
- 2 pedidos laboratoriais
- Todos com status `final`

**Quando:** LISIntegrationDelegate executado
**Então:**
- `has_lab_orders = true`
- `lis_all_final = true`
- `lis_order_count = 2`
- `lis_orders` populado
- `lis_results` populado

---

### 10.3 Cenário: Resultados Pendentes
**Dado:**
- 1 pedido com status `preliminary`

**Quando:** LISIntegrationDelegate executado
**Então:**
- `has_lab_orders = true`
- `lis_all_final = false`
- Bloqueia finalização do atendimento

---

### 10.4 Cenário: Valores Críticos Identificados
**Dado:**
- Resultado com interpretação `HH` (critical high)

**Quando:** LISIntegrationDelegate executado
**Então:**
- `lis_critical_values` contém 1+ valores
- Cada valor com test_code, value, interpretation

---

## 11. Matriz de Status

| Status LIS | Final? | Permite Finalização? | Descrição |
|------------|--------|---------------------|-----------|
| `final` | ✅ | ✅ | Resultado final liberado |
| `amended` | ✅ | ✅ | Resultado corrigido |
| `corrected` | ✅ | ✅ | Resultado com correção |
| `preliminary` | ❌ | ❌ | Resultado preliminar |
| `registered` | ❌ | ❌ | Registrado sem resultado |
| `partial` | ❌ | ❌ | Resultado parcial |
| `cancelled` | N/A | ⚠️ | Pedido cancelado |

---

## 12. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/LISIntegrationDelegate.java`

**Serviços:**
- `/src/main/java/com/hospital/revenuecycle/service/LISService.java`

**DTOs:**
- `/src/main/java/com/hospital/revenuecycle/integration/lis/dto/LISOrderDTO.java`
- `/src/main/java/com/hospital/revenuecycle/integration/lis/dto/LISResultDTO.java`
- `/src/main/java/com/hospital/revenuecycle/integration/lis/dto/ObservationDTO.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/LISIntegrationDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
