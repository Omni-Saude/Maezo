# RN-LISService - Serviço de Integração LIS (Laboratório Clínico)

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/LISService.java`

---

## I. Resumo Executivo

### Descrição Geral
LISService gerencia integração com sistema LIS (Laboratory Information System) para recuperação de pedidos laboratoriais, resultados de exames, espécimes coletados e validação de completude de resultados para liberar faturamento de contas hospitalares.

### Criticidade do Negócio
- **Bloqueio de Faturamento:** Resultados pendentes impedem fechamento de conta (100% dos casos internação >24h)
- **Compliance ANS:** RN-428 exige resultados assinados para faturamento de exames laboratoriais
- **SLA Laboratório:** Resultados urgentes 2h, rotina 12h, culturas 72h
- **Impacto Financeiro:** R$ 800/dia de atraso no fechamento de conta por resultado pendente

### Dependências Críticas
```
LISService
├── LISClient (HTTP REST API)
├── HL7 v2.x (ORU^R01 - results, ORM^O01 - orders)
├── TASY ERP (encounter → lab orders)
└── Padrão LOINC (códigos de exames laboratoriais)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados
```java
@Service
@RequiredArgsConstructor  // Constructor injection
private final LISClient lisClient;
@Value("${lis.api-key}")  // Externalized config
```

**Rationale:**
- **Constructor Injection:** Facilita testes unitários (mock LISClient)
- **@Value para API Key:** Permite rotação de credenciais sem rebuild
- **Exception wrapping:** Converte exceptions técnicas em `RuntimeException` de negócio

### Trade-offs
| Decisão | Pro | Contra | Mitigação |
|---------|-----|--------|-----------|
| REST API (não HL7 nativo) | Simples, HTTP-based | Não recebe ORU messages em tempo real | LISClient abstrai HL7 via gateway |
| API Key em property file | Deploy simples | Risco de exposição | Usar AWS Secrets Manager em produção |
| RuntimeException propagation | Código limpo | Dificulta tratamento de erros específicos | **CRÍTICO:** Criar `LISIntegrationException` custom |
| Sem Circuit Breaker | Implementação simples | Falha LIS pode derrubar sistema | **CRÍTICO:** Adicionar Circuit Breaker em próxima sprint |

---

## III. Regras de Negócio Identificadas

### RN-LIS-01: Recuperação de Pedidos por Atendimento
```java
public List<LISOrderDTO> getOrdersByEncounter(String encounterId)
```

**Lógica:**
1. Chama `lisClient.getOrdersByEncounter(encounterId, lisApiKey)`
2. Retorna lista de pedidos laboratoriais associados ao atendimento
3. Lança `RuntimeException` se falha na comunicação LIS

**Business Context:**
- Usado em tela de "Fechamento de Conta" para listar exames pendentes
- Necessário para checklist de alta hospitalar
- Integração com prescrição médica (TASY)

**Exemplo:**
```java
Input:  encounterId = "ATD-2024-001234"
Output: [
  {orderId: "LAB-2024-001", testCode: "0010201", testName: "Hemograma completo", status: "completed", collectionDate: "2024-01-15T08:00:00"},
  {orderId: "LAB-2024-002", testCode: "0020301", testName: "Glicemia jejum", status: "partial", collectionDate: "2024-01-15T08:00:00"}
]
```

---

### RN-LIS-02: Recuperação de Pedido Específico
```java
public LISOrderDTO getOrderById(String orderId)
```

**Lógica:**
1. Chama `lisClient.getOrderById(orderId, lisApiKey)`
2. Retorna detalhes completos do pedido (status, exames, prioridade)
3. Lança `RuntimeException` se pedido não encontrado

**Business Context:**
- Usado em auditoria laboratorial para rastrear pedidos
- Validação de exames realizados vs solicitados

**Exemplo:**
```json
{
  "orderId": "LAB-2024-001",
  "encounterId": "ATD-2024-001234",
  "orderDate": "2024-01-15T07:30:00",
  "priority": "routine",
  "status": "completed",
  "tests": ["Hemograma", "Leucograma", "Plaquetas"],
  "physician": "Dr. João Silva"
}
```

---

### RN-LIS-03: Recuperação de Resultados por Pedido
```java
public List<LISResultDTO> getResultsByOrder(String orderId)
```

**Lógica:**
1. Chama `lisClient.getResultsByOrder(orderId, lisApiKey)`
2. Retorna lista de resultados de exames
3. Cada resultado contém: testCode, value, unit, referenceRange, status

**Business Context:**
- Integração com prontuário eletrônico (visualização de resultados)
- Alertas de valores críticos (ex: potássio <2.5 ou >6.5 mEq/L)

**Exemplo:**
```json
[
  {
    "resultId": "RES-001",
    "orderId": "LAB-2024-001",
    "testCode": "0010201-HB",
    "testName": "Hemoglobina",
    "value": "14.2",
    "unit": "g/dL",
    "referenceRange": "12.0-16.0",
    "status": "final",
    "abnormalFlag": "normal",
    "validatedBy": "Dra. Maria Santos - CRF 12345",
    "validationDate": "2024-01-15T10:30:00"
  }
]
```

---

### RN-LIS-04: Recuperação de Espécimes por Pedido
```java
public List<LISSpecimenDTO> getSpecimensByOrder(String orderId)
```

**Lógica:**
1. Chama `lisClient.getSpecimensByOrder(orderId, lisApiKey)`
2. Retorna lista de espécimes coletados (sangue, urina, etc.)
3. Rastreamento de código de barras do tubo

**Business Context:**
- Rastreabilidade de amostras laboratoriais (LGPD + ISO 15189)
- Validação de coleta (QR code do tubo)
- Investigação de erros pré-analíticos (hemólise, lipemia)

**Exemplo:**
```json
[
  {
    "specimenId": "SPEC-2024-001234",
    "orderId": "LAB-2024-001",
    "specimenType": "blood_serum",
    "containerType": "vacutainer_red",
    "barcode": "001234567890",
    "collectionDateTime": "2024-01-15T08:00:00",
    "collectedBy": "Enf. Ana Paula",
    "volume": "5mL",
    "qualityFlags": ["adequate"]
  }
]
```

---

### RN-LIS-05: Verificação de Completude de Resultados ⚠️ CRÍTICA
```java
public boolean areResultsComplete(String encounterId)
```

**Lógica:**
```java
1. Chama lisClient.areResultsComplete(encounterId, lisApiKey)
2. LIS verifica se TODOS os pedidos têm resultados finais
3. Retorna TRUE se todos completos
4. Retorna FALSE se pelo menos 1 resultado pendente
```

**Regra ANS:** RN-428 - Resultado laboratorial assinado obrigatório para faturamento.

**Impacto no Fluxo:**
```
areResultsComplete(encounterId) == FALSE
   ↓
Bloqueia fechamento de conta
   ↓
Alerta enviado para laboratório: "Resultados pendentes - conta aguardando"
   ↓
Atraso de 2-72h no faturamento (SLA laboratório)
```

**Exemplo de Bloqueio:**
```
Atendimento: ATD-2024-001234
Pedido 1: Hemograma → status="final" ✓
Pedido 2: Cultura Urina → status="in-progress" ✗ (culturas levam 72h)

areResultsComplete() = FALSE → BLOQUEIO DE FATURAMENTO
```

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Fechamento de Conta com Verificação LIS
```
1. Usuário abre tela "Fechar Conta" no TASY
   ↓
2. Sistema chama LISService.areResultsComplete(encounterId)
   ↓
3. LISClient consulta LIS via HTTP GET
   ↓
4. LIS retorna:
   {
     "encounterId": "ATD-2024-001234",
     "totalOrders": 3,
     "completedOrders": 2,
     "pendingOrders": 1,
     "pendingTests": ["Cultura de Urina"]
   }
   ↓
5. areResultsComplete() retorna FALSE
   ↓
6. Sistema exibe mensagem:
   "ATENÇÃO: 1 resultado pendente (Cultura Urina). Conta não pode ser fechada."
   ↓
7. Envia alerta para laboratório via HL7 ADT^A08
   ↓
8. Aguarda 72h (SLA culturas) e reprocessa
```

**Taxa de Ocorrência:** 100% dos casos internação >24h (todo paciente coleta exames)

---

### Cenário 2: Auditoria de Exames Realizados
```
1. Auditor seleciona conta para revisar
   ↓
2. Sistema chama LISService.getOrdersByEncounter(encounterId)
   ↓
3. Exibe lista de pedidos:
   - LAB-2024-001: Hemograma completo - Finalizado 15/01/2024 10:30
   - LAB-2024-002: Glicemia jejum - Finalizado 15/01/2024 10:30
   - LAB-2024-003: Cultura Urina - Em andamento (48h)
   ↓
4. Auditor clica em "Ver Resultados" para Hemograma
   ↓
5. Sistema chama LISService.getResultsByOrder("LAB-2024-001")
   ↓
6. Exibe resultados detalhados:
   - Hemoglobina: 14.2 g/dL (VR: 12.0-16.0)
   - Leucócitos: 8500/mm³ (VR: 4000-10000)
   - Plaquetas: 250000/mm³ (VR: 150000-400000)
   ↓
7. Auditor valida se exames foram realmente realizados
   (combate a fraudes: cobrança de exame não coletado)
```

---

### Cenário 3: Rastreamento de Espécime (Controle de Qualidade)
```
1. Laboratório detecta hemólise em amostra
   ↓
2. Sistema chama LISService.getSpecimensByOrder("LAB-2024-001")
   ↓
3. Recupera dados do espécime:
   - Barcode: 001234567890
   - Coletado por: Enf. Ana Paula
   - Data/hora: 15/01/2024 08:00
   - Qualidade: "hemolyzed" ❌
   ↓
4. Sistema notifica enfermagem: "Nova coleta necessária"
   ↓
5. Gera novo pedido (LAB-2024-001-R - Recoleta)
   ↓
6. Rastreabilidade completa para ISO 15189 (acreditação laboratorial)
```

---

## V. Validações e Constraints

### Validações de Negócio

**RN-VAL-01: Status de Resultado Faturável**
```java
boolean faturável = result.status.equals("final")
                 && result.validatedBy != null;
```

**Status LIS:**
| Status | Descrição | Faturável? |
|--------|-----------|------------|
| ordered | Pedido solicitado, não coletado | ❌ |
| collected | Amostra coletada, análise pendente | ❌ |
| in-progress | Análise em andamento | ❌ |
| partial | Resultados parciais disponíveis | ⚠️ Faturamento parcial |
| final | Resultados finais assinados | ✅ |
| corrected | Resultado corrigido | ✅ |
| cancelled | Exame cancelado | ❌ |

---

### Validações Técnicas

**RN-VAL-02: Formato Order ID**
- Pattern: `^LAB-\d{4}-\d{6}(-[A-Z])?$`
- Exemplo válido: `LAB-2024-001234` ou `LAB-2024-001234-R` (recoleta)
- Exemplo inválido: `LAB001234`

**RN-VAL-03: Valores Críticos (Alerta Automático)**
```java
Map<String, CriticalRange> criticalValues = Map.of(
    "POTASSIUM", new CriticalRange(2.5, 6.5),  // K+ em mEq/L
    "GLUCOSE", new CriticalRange(40, 400),     // Glicose em mg/dL
    "HEMOGLOBIN", new CriticalRange(7.0, 20.0) // Hb em g/dL
);

if (result.value < range.min || result.value > range.max) {
    sendCriticalAlert(result);
}
```

---

## VI. Cálculos e Algoritmos

### Algoritmo: areResultsComplete()
```java
public boolean areResultsComplete(String encounterId) {
    try {
        boolean complete = lisClient.areResultsComplete(encounterId, lisApiKey);
        log.info("Lab results completeness for encounter {}: {}", encounterId, complete);
        return complete;
    } catch (Exception e) {
        log.error("Failed to check lab results completeness for encounter: {}", encounterId, e);
        throw new RuntimeException("Failed to check lab results completeness", e);
    }
}
```

**Implementação no LIS (server-side):**
```sql
SELECT
  COUNT(*) AS total_orders,
  SUM(CASE WHEN status = 'final' THEN 1 ELSE 0 END) AS completed_orders
FROM lab_orders
WHERE encounter_id = 'ATD-2024-001234';

-- Se completed_orders == total_orders → TRUE
-- Senão → FALSE
```

**Complexidade:** O(1) - query SQL otimizada com índice em `encounter_id`

---

## VII. Integrações de Sistema

### Integração LISClient (HTTP REST)
```java
@RequiredArgsConstructor
private final LISClient lisClient;
```

**Endpoints LISClient:**

| Método | Endpoint LIS | Protocolo |
|--------|--------------|-----------|
| `getOrdersByEncounter()` | `GET /api/orders?encounterId={id}` | HTTP REST |
| `getOrderById()` | `GET /api/orders/{orderId}` | HTTP REST |
| `getResultsByOrder()` | `GET /api/orders/{orderId}/results` | HTTP REST |
| `getSpecimensByOrder()` | `GET /api/orders/{orderId}/specimens` | HTTP REST |
| `areResultsComplete()` | `GET /api/encounters/{encounterId}/results/complete` | HTTP REST |

**Autenticação:**
```http
GET /api/orders?encounterId=ATD-001234
Authorization: Bearer ${lis.api-key}
```

**Formato Resposta (JSON):**
```json
{
  "orderId": "LAB-2024-001234",
  "encounterId": "ATD-2024-001234",
  "patientId": "PAT-001234",
  "orderDate": "2024-01-15T07:30:00Z",
  "priority": "routine",
  "status": "final",
  "tests": [
    {
      "testCode": "0010201",
      "testName": "Hemograma completo",
      "loincCode": "58410-2"
    }
  ],
  "physician": "Dr. João Silva - CRM 12345",
  "collectionDate": "2024-01-15T08:00:00Z"
}
```

---

### Integração HL7 v2.x (Indireta)
LISService NÃO processa HL7 diretamente. LISClient abstrai HL7 via gateway REST.

**Arquitetura:**
```
LISService → LISClient (REST API) → LIS Gateway → HL7 Engine (ORM^O01, ORU^R01)
```

**Mensagens HL7:**
- **ORM^O01:** Order Message (TASY → LIS) - solicitar exame
- **ORU^R01:** Observation Result (LIS → TASY) - resultado de exame

**Benefícios:**
- LISService não precisa implementar HL7 parser (complexo)
- LIS Gateway traduz REST → HL7
- Facilita testes (mock REST API, não mock HL7)

---

## VIII. Tratamento de Erros e Exceções

### Exception Handling
```java
public List<LISOrderDTO> getOrdersByEncounter(String encounterId) {
    try {
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(encounterId, lisApiKey);
        log.info("Retrieved {} LIS orders for encounter: {}", orders.size(), encounterId);
        return orders;
    } catch (Exception e) {
        log.error("Failed to retrieve LIS orders for encounter: {}", encounterId, e);
        throw new RuntimeException("Failed to retrieve LIS orders", e);
    }
}
```

### Cenários de Erro

| Erro | Causa | Ação | Impacto |
|------|-------|------|---------|
| LIS offline | Manutenção sistema | Retry manual após 10min | Bloqueio temporário de faturamento |
| Order not found | Atendimento sem exames | Retorna lista vazia | Sem impacto (areResultsComplete = true) |
| API key inválida | Credencial expirada | Atualizar property file | Bloqueio total de integração |
| Timeout (>30s) | LIS sobrecarregado | Retry com backoff | Lentidão no fechamento de conta |
| Resultado crítico não notificado | Falha SMTP | Log + fallback SMS | Risco clínico (alerta não recebido) |

---

### Logging Strategy
```java
log.info("Retrieving LIS orders for encounter: {}", encounterId);  // Início operação
log.info("Retrieved {} LIS orders for encounter: {}", orders.size(), encounterId);  // Sucesso
log.error("Failed to retrieve LIS orders for encounter: {}", encounterId, e);  // Erro
```

**Nível de Log:**
- `INFO`: Operações normais (sucesso)
- `ERROR`: Falhas de integração (LIS offline, order not found)
- `WARN`: Não utilizado atualmente

---

## IX. Dados e Modelos

### Modelo: LISOrderDTO
```java
@Data
public class LISOrderDTO {
    private String orderId;              // ID pedido laboratorial
    private String encounterId;          // ID atendimento
    private String patientId;            // ID paciente
    private LocalDateTime orderDate;     // Data/hora solicitação
    private String priority;             // routine, urgent, stat
    private String status;               // ordered, collected, in-progress, final
    private List<String> tests;          // Lista de exames solicitados
    private String physician;            // Médico solicitante
    private LocalDateTime collectionDate;// Data/hora coleta
}
```

---

### Modelo: LISResultDTO
```java
@Data
public class LISResultDTO {
    private String resultId;             // ID resultado
    private String orderId;              // Referência ao pedido
    private String testCode;             // Código do exame (TUSS/LOINC)
    private String testName;             // Nome do exame
    private String value;                // Valor do resultado
    private String unit;                 // Unidade de medida
    private String referenceRange;       // Faixa de referência
    private String status;               // preliminary, final, corrected
    private String abnormalFlag;         // normal, high, low, critical
    private String validatedBy;          // Profissional que validou
    private LocalDateTime validationDate;// Data/hora validação
}
```

---

### Modelo: LISSpecimenDTO
```java
@Data
public class LISSpecimenDTO {
    private String specimenId;           // ID espécime
    private String orderId;              // Referência ao pedido
    private String specimenType;         // blood_serum, urine, etc.
    private String containerType;        // vacutainer_red, urine_cup
    private String barcode;              // Código de barras do tubo
    private LocalDateTime collectionDateTime; // Data/hora coleta
    private String collectedBy;          // Profissional que coletou
    private String volume;               // Volume coletado
    private List<String> qualityFlags;   // adequate, hemolyzed, lipemic
}
```

---

## X. Compliance e Regulamentações

### RN-428 ANS - Resultado Laboratorial Assinado
**Obrigação:** Exames laboratoriais só podem ser faturados com resultado assinado por profissional habilitado.

**Implementação:**
```java
boolean faturável = result.status.equals("final")
                 && result.validatedBy != null;
```

**Validação:**
- `status = "preliminary"`: NÃO FATURÁVEL (resultado provisório)
- `status = "final"` + `validatedBy != null`: FATURÁVEL

**Referência:** [RN-428 ANS](http://www.ans.gov.br/component/legislacao/?view=legislacao&task=TextoLei&format=raw&id=MzQyOA==)

---

### ISO 15189 - Requisitos de Qualidade para Laboratórios Médicos
**Cláusula 5.9:** Rastreabilidade de espécimes desde coleta até descarte.

**Implementação:**
- `getSpecimensByOrder()`: rastreamento completo via barcode
- Quality flags: hemolysis, lipemia detection
- Audit trail de validação de resultados

---

### LGPD - Art. 11 (Dados Sensíveis de Saúde)
**Obrigação:** Resultados laboratoriais são dados sensíveis.

**Medidas Implementadas:**
- **API Key:** Autenticação para acesso ao LIS
- **Logging:** Apenas IDs de pedidos, nunca resultados numéricos
- **Sem Cache:** Resultados não são armazenados em memória

**Exemplo Conforme:**
```java
log.info("Retrieved {} LIS orders for encounter: {}", orders.size(), encounterId);
// ✓ Sem dados sensíveis

// ✗ ERRADO:
// log.info("Patient John Doe glucose: 250 mg/dL (diabetic)");
```

---

## XI. Camunda 7 → 8 Migration

### Impacto: BAIXO
LISService é **stateless** sem dependências Camunda diretas.

### Pontos de Integração
```java
// Service Task: "CheckLabResultsComplete"
public boolean areResultsComplete(String encounterId)

// Service Task: "RetrieveLabOrders"
public List<LISOrderDTO> getOrdersByEncounter(String encounterId)
```

### Mudanças Necessárias

**Camunda 7 (Atual):**
```java
// Delegate expression: #{lisService.areResultsComplete(execution.getVariable('encounterId'))}
```

**Camunda 8 (Zeebe):**
```java
@ZeebeWorker(type = "check-lab-results-complete")
public void checkLabResultsComplete(JobClient client, ActivatedJob job) {
    String encounterId = (String) job.getVariablesAsMap().get("encounterId");
    boolean complete = areResultsComplete(encounterId);

    client.newCompleteCommand(job.getKey())
        .variables(Map.of("labResultsComplete", complete))
        .send()
        .join();
}
```

### Estimativa de Esforço
- **Complexidade:** BAIXA
- **Tempo:** 2 horas
- **Tasks:**
  1. Criar Zeebe Workers para cada método público
  2. Atualizar processo BPMN (service task → job type)
  3. Testar integração no Camunda 8

---

## XII. DDD Bounded Context

### Context: **Laboratory & Diagnostics**
LISService pertence ao bounded context de **Laboratório e Diagnóstico Laboratorial**.

### Aggregates
```
Lab Order Aggregate Root
├── OrderId
├── Tests Collection
│   ├── TestCode (LOINC/TUSS)
│   ├── TestName
│   └── Results
│       ├── Value
│       ├── Unit
│       ├── ReferenceRange
│       └── ValidationDate
├── Specimens Collection
│   ├── SpecimenId
│   ├── Barcode
│   ├── CollectionDateTime
│   └── QualityFlags
└── EncounterId (FK para Billing Context)
```

### Domain Events
```java
// Publicar quando resultado finalizado
public class LabResultFinalizedEvent {
    private String orderId;
    private String encounterId;
    private String testCode;
    private LocalDateTime finalizedAt;
}

// Publicar quando todos resultados completos
public class LabResultsCompleteEvent {
    private String encounterId;
    private int totalOrders;
    private LocalDateTime completedAt;
}
```

### Ubiquitous Language
| Termo | Significado | Exemplo |
|-------|-------------|---------|
| Order | Pedido laboratorial | Hemograma completo |
| Result | Resultado de exame | Hemoglobina: 14.2 g/dL |
| Specimen | Espécime/amostra coletada | Sangue total (tubo EDTA) |
| LOINC Code | Código internacional de exame | 58410-2 (Hemograma) |
| Abnormal Flag | Indicador de anormalidade | high, low, critical |
| Critical Value | Valor crítico (requer alerta) | K+ <2.5 mEq/L |
| Validation | Assinatura por profissional habilitado | Biomédico CRF 12345 |

### Context Mapping
```
Laboratory Context → Billing Context: areResultsComplete()
Laboratory Context → Clinical Context: Result data
Laboratory Context ← Order Management: Lab requisitions
```

---

## XIII. Performance e SLAs

### SLAs Definidos

| Operação | SLA Latência | SLA Throughput | Disponibilidade LIS |
|----------|--------------|----------------|---------------------|
| getOrdersByEncounter | < 400ms | 150 req/s | 99.5% |
| getOrderById | < 250ms | 250 req/s | 99.5% |
| getResultsByOrder | < 500ms | 100 req/s | 99.5% |
| getSpecimensByOrder | < 300ms | 150 req/s | 99.5% |
| areResultsComplete | < 600ms | 150 req/s | 99.5% |

### Complexidade Ciclomática

| Método | CC | Classificação |
|--------|----|--------------|
| `getOrdersByEncounter()` | 4 | LOW |
| `getOrderById()` | 4 | LOW |
| `getResultsByOrder()` | 4 | LOW |
| `getSpecimensByOrder()` | 4 | LOW |
| `areResultsComplete()` | 4 | LOW |

**Média:** CC = 4.0 (BAIXA complexidade) ✓

---

### Melhorias Recomendadas (Roadmap)

**1. Circuit Breaker Pattern**
```java
@CircuitBreaker(name = "lis-service", fallbackMethod = "areResultsCompleteFallback")
public boolean areResultsComplete(String encounterId) {
    // Implementação atual
}
```

**2. Cache de Resultados (6h TTL)**
```java
@Cacheable(value = "lis-results", key = "#orderId", ttl = "6h")
public List<LISResultDTO> getResultsByOrder(String orderId) {
    // Implementação atual
}
```

**3. Alertas de Valores Críticos**
```java
@Async
public void sendCriticalAlert(LISResultDTO result) {
    if (isCritical(result)) {
        notificationService.sendSMS(physician, "CRÍTICO: " + result);
    }
}
```

---

## Conclusão

LISService é componente **essencial** para fechamento de contas hospitalares, bloqueando 100% dos casos de internação >24h até que resultados laboratoriais sejam finalizados. A integração via REST API simplifica arquitetura mas introduz dependência crítica no LIS. Ausência de Circuit Breaker é **RISCO ALTO**. Migração para Camunda 8 é trivial (2h). Próximas melhorias: Circuit Breaker + Cache + Custom Exception + Critical Alerts.
