# RN-ExternalTaskClientConfig: Configuração do External Task Client

## 📋 Metadados
- **ID**: RN-ExternalTaskClientConfig
- **Categoria**: Workers > Configuração
- **Versão**: 1.0
- **Última Atualização**: 2025-12-24
- **Arquivo**: `ExternalTaskClientConfig.java`
- **Localização**: `com.hospital.revenuecycle.workers.config`

---

## 🎯 Visão Geral

Classe de configuração Spring que inicializa o External Task Client do Camunda 7 e registra todos os workers nas respectivas topics. Gerencia o ciclo de vida de 10 workers distribuídos em 3 categorias.

### Responsabilidades

1. **External Task Client**: Criar e configurar o cliente
2. **Worker Subscriptions**: Registrar workers em topics
3. **Connection Management**: Gerenciar conexão com Camunda Engine
4. **Metrics**: Registrar métricas de inicialização

---

## ⚙️ Propriedades de Configuração

### application.properties / application.yml

```properties
# Camunda External Task Client Configuration

# Engine REST API URL
camunda.bpm.client.base-url=http://localhost:8080/engine-rest

# Worker Identifier
camunda.bpm.client.worker-id=revenue-cycle-workers

# Max Concurrent Tasks
camunda.bpm.client.max-tasks=10

# Lock Duration (ms)
camunda.bpm.client.lock-duration=60000

# Async Response Timeout (ms)
camunda.bpm.client.async-response-timeout=5000
```

### Valores Padrão

| Propriedade                | Valor Padrão                             | Descrição                              |
|----------------------------|------------------------------------------|----------------------------------------|
| `base-url`                 | `http://localhost:8080/engine-rest`      | URL do Camunda Engine REST API         |
| `worker-id`                | `revenue-cycle-workers`                  | Identificador do worker group          |
| `max-tasks`                | `10`                                     | Máximo de tarefas concorrentes         |
| `lock-duration`            | `60000` (60 segundos)                    | Duração do lock de tarefa              |
| `async-response-timeout`   | `5000` (5 segundos)                      | Timeout para long polling              |

---

## 📊 Workers Registrados

### 1. Notification Workers (2 workers)

| Worker                          | Topic                     | Descrição                        | Status          |
|---------------------------------|---------------------------|----------------------------------|-----------------|
| `NotificacaoPacienteWorker`     | `notificacao-paciente`    | Notificações WhatsApp pacientes  | ✅ PRODUCTION   |
| `NotificationServiceWorker`     | `notification-service`    | Notificações multi-canal         | ✅ PRODUCTION   |

### 2. IoT Workers (2 workers)

| Worker                    | Topic                 | Descrição                    | Status             |
|---------------------------|-----------------------|------------------------------|--------------------|
| `RFIDCaptureWorker`       | `iot-rfid-capture`    | Captura de tags RFID         | ⚠️ MOCK (HUMAN-006)|
| `WeightSensorWorker`      | `iot-weight-sensor`   | Leitura de sensores de peso  | ⚠️ MOCK (HUMAN-006)|

### 3. RPA Workers (6 workers)

| Worker                        | Topic                     | Descrição                          | Status              |
|-------------------------------|---------------------------|------------------------------------|---------------------|
| `CNABParserWorker`            | `rpa-cnab-parser`         | Parser de arquivos CNAB bancários  | ✅ FUNCTIONAL       |
| `PortalScrapingWorker`        | `rpa-portal-scraping`     | Scraping de portais de convênios  | ⚠️ MOCK (HUMANA-008)|
| `PortalSubmitWorker`          | `rpa-portal-submit`       | Submissão de recursos em portais  | ⚠️ MOCK (HUMANA-008)|
| `PortalUploadWorker`          | `rpa-portal-upload`       | Upload de arquivos TISS           | ⚠️ MOCK (HUMANA-008)|
| `ReportGenerationWorker`      | `rpa-report-generation`   | Geração de relatórios PDF/Excel   | ✅ FUNCTIONAL       |
| `StatusCheckWorker`           | `rpa-status-check`        | Consulta de status em portais     | ⚠️ MOCK (HUMANA-008)|

---

## 🔧 Fluxo de Inicialização

```
┌─────────────────────────────────────────────────────────────┐
│           Spring Boot Application Startup                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│    ExternalTaskClientConfig.externalTaskClient()            │
│                                                              │
│  1. Create ExternalTaskClient                               │
│     └── Configure baseUrl, workerId, maxTasks, etc.         │
│                                                              │
│  2. subscribeToNotificationTopics()                         │
│     ├── NotificacaoPacienteWorker → "notificacao-paciente"  │
│     └── NotificationServiceWorker → "notification-service"  │
│                                                              │
│  3. subscribeToIoTTopics()                                  │
│     ├── RFIDCaptureWorker → "iot-rfid-capture" [MOCK]      │
│     └── WeightSensorWorker → "iot-weight-sensor" [MOCK]    │
│                                                              │
│  4. subscribeToRPATopics()                                  │
│     ├── CNABParserWorker → "rpa-cnab-parser"               │
│     ├── PortalScrapingWorker → "rpa-portal-scraping" [MOCK]│
│     ├── PortalSubmitWorker → "rpa-portal-submit" [MOCK]    │
│     ├── PortalUploadWorker → "rpa-portal-upload" [MOCK]    │
│     ├── ReportGenerationWorker → "rpa-report-generation"   │
│     └── StatusCheckWorker → "rpa-status-check" [MOCK]      │
│                                                              │
│  5. Log initialization complete                             │
│  6. Record metrics: external_task_client.initialized        │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       External Task Client Polling Loop Active              │
│   (Fetches tasks from Camunda Engine every X seconds)      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 Código de Subscription

### Padrão de Subscription

```java
client.subscribe("topic-name")
      .lockDuration(lockDuration)
      .handler(workerInstance)
      .open();
```

### Exemplo: Notification Topics

```java
private void subscribeToNotificationTopics(
        ExternalTaskClient client,
        NotificacaoPacienteWorker notificacaoPacienteWorker,
        NotificationServiceWorker notificationServiceWorker) {

    // Patient notification via WhatsApp
    client.subscribe("notificacao-paciente")
          .lockDuration(lockDuration)
          .handler(notificacaoPacienteWorker)
          .open();

    logger.info("Subscribed NotificacaoPacienteWorker to topic: notificacao-paciente");

    // Generic notification service
    client.subscribe("notification-service")
          .lockDuration(lockDuration)
          .handler(notificationServiceWorker)
          .open();

    logger.info("Subscribed NotificationServiceWorker to topic: notification-service");
}
```

---

## ⚠️ Warnings e Status

### MOCK Implementation Warnings

O sistema emite **warnings específicos** para workers em modo MOCK:

```log
⚠️  Subscribed RFIDCaptureWorker to topic: iot-rfid-capture
    (MOCK IMPLEMENTATION - see HUMAN-006)

⚠️  Subscribed WeightSensorWorker to topic: iot-weight-sensor
    (MOCK IMPLEMENTATION - see HUMAN-006)

⚠️  Subscribed CNABParserWorker to topic: rpa-cnab-parser
    (TODO IMPLEMENTATION - see HUMANA-008)

⚠️  Subscribed PortalScrapingWorker to topic: rpa-portal-scraping
    (TODO IMPLEMENTATION - see HUMANA-008)
```

### Bloqueadores de Implementação

| Bloqueador | Workers Afetados | Descrição |
|------------|------------------|-----------|
| **HUMAN-006** | `RFIDCaptureWorker`, `WeightSensorWorker` | Acesso a dispositivos IoT não configurado |
| **HUMANA-008** | `PortalScrapingWorker`, `PortalSubmitWorker`, `PortalUploadWorker`, `StatusCheckWorker` | Credenciais de portais não disponíveis |

---

## 🔐 External Task Client Configuration

### Client Builder Pattern

```java
ExternalTaskClient client = ExternalTaskClient.create()
    .baseUrl(camundaBaseUrl)           // REST API endpoint
    .workerId(workerId)                // Worker identifier
    .maxTasks(maxTasks)                // Concurrent task limit
    .lockDuration(lockDuration)        // Task lock duration
    .asyncResponseTimeout(asyncResponseTimeout) // Long polling timeout
    .build();
```

### Lock Duration Strategy

```
┌──────────────────────────────────────────────────────────────┐
│                    Lock Duration: 60s                        │
│                                                              │
│  ┌────────────┐                                             │
│  │   Fetch    │   Worker has 60 seconds to complete task   │
│  │   Task     │   Before lock expires and task returns     │
│  └──────┬─────┘   to available pool                        │
│         │                                                    │
│         │ Lock starts                                       │
│         ▼                                                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          Task Processing (0-60s)                     │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │ 1. Validate task                               │ │  │
│  │  │ 2. Process business logic                      │ │  │
│  │  │ 3. Complete task                               │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│         │                                                    │
│         │ If lock expires before completion                 │
│         ▼                                                    │
│  ┌────────────┐                                             │
│  │   Task     │   Task becomes available again             │
│  │ Released   │   for other workers to fetch               │
│  └────────────┘                                             │
└──────────────────────────────────────────────────────────────┘
```

---

## 📊 Métricas

### external_task_client.initialized

```
Type: Counter
Description: Total number of External Task Client initializations
Tags: none
Value: Incremented once at startup
```

**Uso**: Verificar se client foi inicializado com sucesso.

---

## 🧪 Testes

### Unit Test Example

```java
@Test
void shouldInitializeExternalTaskClientWithAllWorkers() {
    // Given
    ExternalTaskClientConfig config = new ExternalTaskClientConfig();
    config.setCamundaBaseUrl("http://localhost:8080/engine-rest");
    config.setWorkerId("test-workers");
    config.setMaxTasks(5);

    // When
    ExternalTaskClient client = config.externalTaskClient(
        notificacaoPacienteWorker,
        notificationServiceWorker,
        rfidCaptureWorker,
        weightSensorWorker,
        cnabParserWorker,
        portalScrapingWorker,
        portalSubmitWorker,
        portalUploadWorker,
        reportGenerationWorker,
        statusCheckWorker,
        meterRegistry
    );

    // Then
    assertNotNull(client);
    verify(meterRegistry).counter("external_task_client.initialized");
}
```

---

## 🛠️ Troubleshooting

### Problema: Workers não recebem tarefas

**Sintomas**:
- Workers registrados mas não processam tarefas
- Logs mostram "Subscribed to topic: X" mas nenhuma execução

**Checklist**:
1. ✅ Camunda Engine está rodando?
2. ✅ `base-url` está correto?
3. ✅ Topic name no BPMN corresponde à subscription?
4. ✅ Tarefas External Task Service foram criadas no processo BPMN?
5. ✅ Network connectivity entre worker e engine?

### Problema: Lock timeout frequente

**Sintomas**:
- Tarefas expiram antes de completar
- Logs mostram "Lock expired for task X"

**Soluções**:
1. Aumentar `lock-duration` na configuração
2. Otimizar processamento do worker
3. Verificar operações blocking (I/O, HTTP calls)

---

## 🎯 Boas Práticas

### ✅ DO

1. **Usar mesmo lockDuration** para todos workers (consistência)
2. **Logar cada subscription** para auditoria
3. **Registrar métricas** de inicialização
4. **Documentar workers MOCK** com warnings visíveis
5. **Validar conexão** com Camunda Engine antes de subir workers

### ❌ DON'T

1. ❌ Não hardcodear URLs (usar properties)
2. ❌ Não ignorar erros de subscription
3. ❌ Não criar subscriptions duplicadas
4. ❌ Não usar lockDuration muito curto (<10s)
5. ❌ Não inicializar client sem workers

---

## 📚 Referências

- **ADR-003**: BPMN Implementation Standards
- **Documentação**: Camunda 7 External Task Client
- **Padrão**: Dependency Injection (Spring)

---

**Status**: ✅ PRODUCTION READY
**Total de Workers**: 10 (2 Notification + 2 IoT + 6 RPA)
**Mock Workers**: 7 (aguardando HUMAN-006 e HUMANA-008)
