# RN-WhatsAppWebhookHandler - Processador de Webhooks WhatsApp

## 1. Visão Geral

### 1.1 Objetivo
Componente responsável por processar eventos de webhook do WhatsApp Business API, incluindo atualizações de status de mensagens (enviada, entregue, lida, falhou) e métricas de entrega.

### 1.2 Contexto no Ciclo da Receita
- **Módulo**: Integration Layer
- **Processo BPMN**: Message Status Tracking & Monitoring
- **Componente**: `com.hospital.revenuecycle.integration.whatsapp.WhatsAppWebhookHandler`
- **Tipo**: Spring Component (@Component)

### 1.3 Casos de Uso
- Rastreamento de status de entrega de mensagens
- Monitoramento de taxa de leitura de notificações
- Detecção de falhas de entrega
- Cálculo de métricas de engajamento
- Acionamento de ações de follow-up baseadas em status

---

## 2. Regras de Negócio

### RN-WAH-001: Processamento de Webhook
**Descrição**: O handler deve processar eventos de webhook do WhatsApp de forma idempotente e resiliente.

**Assinatura**:
```java
public void processWebhook(WhatsAppWebhookDTO webhook)
```

**Fluxo de Processamento**:
```java
public void processWebhook(WhatsAppWebhookDTO webhook) {
    // 1. Validar estrutura do webhook
    if (webhook.getEntry() == null || webhook.getEntry().isEmpty()) {
        log.warn("Received empty webhook event");
        return;
    }

    // 2. Iterar sobre entries
    for (WhatsAppWebhookDTO.Entry entry : webhook.getEntry()) {
        if (entry.getChanges() != null) {
            // 3. Processar cada change
            for (WhatsAppWebhookDTO.Change change : entry.getChanges()) {
                processChange(change);
            }
        }
    }
}
```

**Validações**:
- Webhook não pode ser nulo
- Entry list não pode ser vazia
- Changes devem conter value
- Status updates devem ter message ID válido

---

### RN-WAH-002: Processamento de Change Events
**Descrição**: Cada change event representa uma atualização de status de mensagem.

**Implementação**:
```java
private void processChange(WhatsAppWebhookDTO.Change change) {
    WhatsAppWebhookDTO.Value value = change.getValue();

    // Verificar se há status updates
    if (value.getStatuses() != null) {
        for (WhatsAppWebhookDTO.Status status : value.getStatuses()) {
            processStatusUpdate(status);
        }
    }
}
```

**Estrutura do Change**:
```json
{
  "value": {
    "messaging_product": "whatsapp",
    "metadata": {
      "display_phone_number": "15550000001",
      "phone_number_id": "123456789"
    },
    "statuses": [
      {
        "id": "wamid.HBgN...",
        "status": "delivered",
        "timestamp": "1234567890",
        "recipient_id": "5511987654321"
      }
    ]
  },
  "field": "messages"
}
```

---

### RN-WAH-003: Atualização de Status de Mensagem
**Descrição**: O sistema deve armazenar e processar atualizações de status de mensagens em um store thread-safe.

**Implementação**:
```java
private final Map<String, MessageStatus> messageStatusStore = new ConcurrentHashMap<>();

private void processStatusUpdate(WhatsAppWebhookDTO.Status status) {
    // Construir objeto de status
    MessageStatus messageStatus = MessageStatus.builder()
        .messageId(status.getId())
        .status(status.getStatus())
        .timestamp(status.getTimestamp())
        .recipientId(status.getRecipientId())
        .build();

    // Armazenar no store (sobrescreve status anterior)
    messageStatusStore.put(status.getId(), messageStatus);

    log.info("WhatsApp message {} status updated to: {}",
        status.getId(), status.getStatus());

    // Processar ações específicas por status
    handleStatusTransition(messageStatus);
}
```

**Estados de Mensagem**:
| Status | Descrição | Ação |
|--------|-----------|------|
| `sent` | Mensagem enviada para WhatsApp | Registrar timestamp de envio |
| `delivered` | Entregue ao dispositivo do destinatário | Atualizar métrica de entrega |
| `read` | Lida pelo destinatário | Registrar engajamento |
| `failed` | Falha na entrega | Acionar retry ou alerta |

---

### RN-WAH-004: Handlers Específicos por Status
**Descrição**: Cada status de mensagem deve ter um handler específico para executar ações de follow-up.

**Implementação**:

**1. Handle Sent**:
```java
private void handleSent(MessageStatus status) {
    log.debug("Message sent: {}", status.getMessageId());

    // TODO: Atualizar registro na tabela de mensagens
    messageRepository.updateStatus(
        status.getMessageId(),
        MessageDeliveryStatus.SENT,
        status.getTimestamp()
    );
}
```

**2. Handle Delivered**:
```java
private void handleDelivered(MessageStatus status) {
    log.info("Message delivered: {}", status.getMessageId());

    // TODO: Atualizar métrica de entrega
    metricsService.incrementDeliveredCount();

    // Calcular tempo de entrega
    MessageRecord record = messageRepository.findById(status.getMessageId());
    if (record != null) {
        Duration deliveryTime = Duration.between(
            record.getSentAt(),
            Instant.parse(status.getTimestamp())
        );
        metricsService.recordDeliveryTime(deliveryTime);
    }
}
```

**3. Handle Read**:
```java
private void handleRead(MessageStatus status) {
    log.info("Message read: {}", status.getMessageId());

    // TODO: Registrar engajamento
    engagementService.recordMessageRead(
        status.getMessageId(),
        status.getRecipientId(),
        Instant.parse(status.getTimestamp())
    );

    // Calcular tempo de leitura
    MessageRecord record = messageRepository.findById(status.getMessageId());
    if (record != null) {
        Duration readTime = Duration.between(
            record.getDeliveredAt(),
            Instant.parse(status.getTimestamp())
        );
        metricsService.recordReadTime(readTime);
    }
}
```

**4. Handle Failed**:
```java
private void handleFailed(MessageStatus status) {
    log.error("Message failed: {}", status.getMessageId());

    // TODO: Implementar lógica de retry
    MessageRecord record = messageRepository.findById(status.getMessageId());

    if (record != null && record.getRetryCount() < MAX_RETRIES) {
        // Reagendar para retry
        retryScheduler.scheduleRetry(
            record,
            calculateBackoff(record.getRetryCount())
        );
    } else {
        // Alertar administradores após max retries
        alertService.sendAlert(
            AlertLevel.ERROR,
            "WhatsApp message delivery failed after max retries: " +
            status.getMessageId()
        );

        // Notificar usuário por canal alternativo (e-mail, SMS)
        fallbackNotificationService.sendFallbackNotification(
            record.getRecipientId(),
            record.getContent()
        );
    }
}
```

---

### RN-WAH-005: Consulta de Status de Mensagem
**Descrição**: O sistema deve permitir consulta de status de mensagens armazenadas.

**Implementação**:
```java
public MessageStatus getMessageStatus(String messageId) {
    return messageStatusStore.get(messageId);
}
```

**Retorno**:
- `MessageStatus`: Se mensagem encontrada
- `null`: Se mensagem não encontrada no store

**Uso**:
```java
// Verificar se mensagem foi entregue
MessageStatus status = webhookHandler.getMessageStatus("wamid.123...");
if (status != null && "delivered".equals(status.getStatus())) {
    log.info("Message was successfully delivered");
}
```

---

### RN-WAH-006: Estatísticas de Entrega
**Descrição**: O sistema deve calcular estatísticas agregadas de entrega de mensagens.

**Implementação**:
```java
public Map<String, Long> getDeliveryStatistics() {
    Map<String, Long> stats = new ConcurrentHashMap<>();

    stats.put("total", (long) messageStatusStore.size());
    stats.put("sent", countByStatus("sent"));
    stats.put("delivered", countByStatus("delivered"));
    stats.put("read", countByStatus("read"));
    stats.put("failed", countByStatus("failed"));

    return stats;
}

private long countByStatus(String status) {
    return messageStatusStore.values().stream()
        .filter(ms -> status.equals(ms.getStatus()))
        .count();
}
```

**Retorno**:
```json
{
  "total": 1000,
  "sent": 950,
  "delivered": 900,
  "read": 650,
  "failed": 50
}
```

**Métricas Calculadas**:
```java
public DeliveryMetrics calculateMetrics() {
    Map<String, Long> stats = getDeliveryStatistics();

    long total = stats.get("total");
    long delivered = stats.get("delivered");
    long read = stats.get("read");
    long failed = stats.get("failed");

    return DeliveryMetrics.builder()
        .totalMessages(total)
        .deliveryRate(total > 0 ? (double) delivered / total : 0.0)
        .readRate(delivered > 0 ? (double) read / delivered : 0.0)
        .failureRate(total > 0 ? (double) failed / total : 0.0)
        .build();
}
```

---

### RN-WAH-007: Idempotência de Webhooks
**Descrição**: O sistema deve processar webhooks de forma idempotente, tratando duplicatas.

**Problema**:
WhatsApp pode enviar o mesmo webhook múltiplas vezes (retry automático).

**Solução**:
```java
@Component
public class WhatsAppWebhookHandler {

    private final Set<String> processedWebhooks =
        Collections.synchronizedSet(new HashSet<>());

    public void processWebhook(WhatsAppWebhookDTO webhook) {
        // Gerar ID único para o webhook
        String webhookId = generateWebhookId(webhook);

        // Verificar se já foi processado
        if (processedWebhooks.contains(webhookId)) {
            log.debug("Webhook already processed: {}", webhookId);
            return;
        }

        // Processar webhook
        try {
            doProcessWebhook(webhook);
            processedWebhooks.add(webhookId);
        } catch (Exception e) {
            log.error("Error processing webhook: {}", webhookId, e);
            // Não adicionar ao set para permitir reprocessamento
        }
    }

    private String generateWebhookId(WhatsAppWebhookDTO webhook) {
        // Usar hash do conteúdo ou IDs únicos
        return webhook.getEntry().stream()
            .flatMap(e -> e.getChanges().stream())
            .flatMap(c -> c.getValue().getStatuses().stream())
            .map(s -> s.getId() + ":" + s.getStatus() + ":" + s.getTimestamp())
            .collect(Collectors.joining(","));
    }
}
```

**Limpeza Periódica**:
```java
@Scheduled(fixedRate = 3600000) // 1 hora
public void cleanupProcessedWebhooks() {
    // Limpar webhooks processados há mais de 24h
    // (assumindo que WhatsApp não reenvia após 24h)
    processedWebhooks.clear();
    log.info("Cleaned up processed webhooks set");
}
```

---

### RN-WAH-008: Persistência de Status
**Descrição**: Status de mensagens devem ser persistidos em banco de dados para auditoria e análise.

**Entidade**:
```java
@Entity
@Table(name = "whatsapp_message_status")
public class WhatsAppMessageStatusEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String messageId; // wamid

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private WhatsAppStatus status;

    private String recipientId;

    private Instant statusTimestamp;

    private Instant createdAt;

    private Instant updatedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "patient_id")
    private Patient patient;

    @Column(length = 1000)
    private String templateId;

    // Auditoria
    private String webhookId;
    private String phoneNumberId;
}
```

**Repository**:
```java
@Repository
public interface WhatsAppMessageStatusRepository
        extends JpaRepository<WhatsAppMessageStatusEntity, Long> {

    Optional<WhatsAppMessageStatusEntity> findByMessageId(String messageId);

    List<WhatsAppMessageStatusEntity> findByStatus(WhatsAppStatus status);

    List<WhatsAppMessageStatusEntity> findByRecipientIdAndStatusTimestampBetween(
        String recipientId,
        Instant start,
        Instant end
    );

    @Query("SELECT COUNT(e) FROM WhatsAppMessageStatusEntity e " +
           "WHERE e.status = :status AND e.statusTimestamp >= :since")
    long countByStatusSince(@Param("status") WhatsAppStatus status,
                           @Param("since") Instant since);
}
```

**Persistência no Handler**:
```java
private void processStatusUpdate(WhatsAppWebhookDTO.Status status) {
    // ... código anterior ...

    // Persistir no banco de dados
    WhatsAppMessageStatusEntity entity = new WhatsAppMessageStatusEntity();
    entity.setMessageId(status.getId());
    entity.setStatus(WhatsAppStatus.fromString(status.getStatus()));
    entity.setRecipientId(status.getRecipientId());
    entity.setStatusTimestamp(Instant.parse(status.getTimestamp()));
    entity.setCreatedAt(Instant.now());

    statusRepository.save(entity);
}
```

---

## 3. Webhook Security

### 3.1 Verificação de Assinatura
**Descrição**: Webhooks do WhatsApp devem ter assinatura verificada para segurança.

**Implementação**:
```java
@Component
public class WhatsAppWebhookSecurity {

    @Value("${whatsapp.webhook.verify-token}")
    private String verifyToken;

    @Value("${whatsapp.webhook.app-secret}")
    private String appSecret;

    /**
     * Verificar webhook challenge (GET request).
     */
    public String verifyChallenge(
            String mode,
            String token,
            String challenge) {

        if ("subscribe".equals(mode) && verifyToken.equals(token)) {
            log.info("Webhook verification successful");
            return challenge;
        }

        log.warn("Webhook verification failed: mode={}, token={}", mode, token);
        throw new SecurityException("Invalid verification token");
    }

    /**
     * Verificar assinatura do webhook (POST request).
     */
    public boolean verifySignature(String payload, String signature) {
        if (signature == null || !signature.startsWith("sha256=")) {
            return false;
        }

        String expectedSignature = "sha256=" +
            calculateHmacSHA256(payload, appSecret);

        return MessageDigest.isEqual(
            signature.getBytes(),
            expectedSignature.getBytes()
        );
    }

    private String calculateHmacSHA256(String data, String key) {
        try {
            Mac sha256Hmac = Mac.getInstance("HmacSHA256");
            SecretKeySpec secretKey = new SecretKeySpec(
                key.getBytes(StandardCharsets.UTF_8),
                "HmacSHA256"
            );
            sha256Hmac.init(secretKey);

            byte[] hash = sha256Hmac.doFinal(
                data.getBytes(StandardCharsets.UTF_8)
            );

            return bytesToHex(hash);
        } catch (Exception e) {
            throw new RuntimeException("Error calculating HMAC", e);
        }
    }

    private String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }
}
```

**Controller com Verificação**:
```java
@RestController
@RequestMapping("/webhooks/whatsapp")
public class WhatsAppWebhookController {

    @Autowired
    private WhatsAppWebhookHandler handler;

    @Autowired
    private WhatsAppWebhookSecurity security;

    /**
     * Webhook verification endpoint (GET).
     */
    @GetMapping
    public ResponseEntity<String> verifyWebhook(
            @RequestParam("hub.mode") String mode,
            @RequestParam("hub.verify_token") String token,
            @RequestParam("hub.challenge") String challenge) {

        try {
            String response = security.verifyChallenge(mode, token, challenge);
            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }
    }

    /**
     * Webhook event endpoint (POST).
     */
    @PostMapping
    public ResponseEntity<Void> handleWebhook(
            @RequestBody String payload,
            @RequestHeader("X-Hub-Signature-256") String signature) {

        // Verificar assinatura
        if (!security.verifySignature(payload, signature)) {
            log.warn("Invalid webhook signature");
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }

        // Processar webhook
        try {
            WhatsAppWebhookDTO webhook =
                objectMapper.readValue(payload, WhatsAppWebhookDTO.class);
            handler.processWebhook(webhook);
            return ResponseEntity.ok().build();
        } catch (Exception e) {
            log.error("Error processing webhook", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
}
```

---

## 4. Integração com Outros Componentes

### 4.1 MessageRepository
```java
@Service
public class MessageTrackingService {

    @Autowired
    private WhatsAppWebhookHandler webhookHandler;

    @Autowired
    private MessageRepository messageRepository;

    public MessageDeliveryReport getDeliveryReport(String messageId) {
        // Buscar status no handler
        MessageStatus status = webhookHandler.getMessageStatus(messageId);

        // Buscar registro no banco
        MessageRecord record = messageRepository.findById(messageId);

        return MessageDeliveryReport.builder()
            .messageId(messageId)
            .currentStatus(status != null ? status.getStatus() : "unknown")
            .sentAt(record.getSentAt())
            .deliveredAt(record.getDeliveredAt())
            .readAt(record.getReadAt())
            .failedAt(record.getFailedAt())
            .recipientId(status != null ? status.getRecipientId() : null)
            .build();
    }
}
```

### 4.2 RetryScheduler
```java
@Service
public class WhatsAppRetryScheduler {

    private static final int MAX_RETRIES = 3;
    private static final Duration[] BACKOFF_DELAYS = {
        Duration.ofMinutes(5),
        Duration.ofMinutes(15),
        Duration.ofHours(1)
    };

    public void scheduleRetry(MessageRecord record, int attemptNumber) {
        if (attemptNumber >= MAX_RETRIES) {
            log.warn("Max retries reached for message: {}", record.getMessageId());
            return;
        }

        Duration delay = BACKOFF_DELAYS[attemptNumber];
        Instant retryAt = Instant.now().plus(delay);

        // Criar job de retry
        RetryJob job = RetryJob.builder()
            .messageId(record.getMessageId())
            .attemptNumber(attemptNumber + 1)
            .scheduledFor(retryAt)
            .build();

        retryJobRepository.save(job);

        log.info("Scheduled retry #{} for message {} at {}",
            attemptNumber + 1, record.getMessageId(), retryAt);
    }

    @Scheduled(fixedRate = 60000) // 1 minuto
    public void processRetryQueue() {
        List<RetryJob> dueJobs = retryJobRepository.findByScheduledForBefore(
            Instant.now()
        );

        for (RetryJob job : dueJobs) {
            try {
                // Reenviar mensagem
                whatsAppService.retryMessage(job.getMessageId());
                retryJobRepository.delete(job);
            } catch (Exception e) {
                log.error("Error processing retry job: {}", job.getMessageId(), e);
            }
        }
    }
}
```

### 4.3 MetricsService
```java
@Service
public class WhatsAppMetricsService {

    @Autowired
    private WhatsAppWebhookHandler webhookHandler;

    public WhatsAppKPIs calculateKPIs(LocalDate date) {
        Map<String, Long> stats = webhookHandler.getDeliveryStatistics();

        long total = stats.get("total");
        long delivered = stats.get("delivered");
        long read = stats.get("read");
        long failed = stats.get("failed");

        return WhatsAppKPIs.builder()
            .date(date)
            .totalSent(total)
            .deliveryRate(total > 0 ? (double) delivered / total * 100 : 0.0)
            .readRate(delivered > 0 ? (double) read / delivered * 100 : 0.0)
            .failureRate(total > 0 ? (double) failed / total * 100 : 0.0)
            .engagement(delivered > 0 ? (double) read / delivered : 0.0)
            .build();
    }

    @Scheduled(cron = "0 0 * * * *") // A cada hora
    public void recordHourlyMetrics() {
        WhatsAppKPIs kpis = calculateKPIs(LocalDate.now());
        kpiRepository.save(kpis);

        // Alertar se métricas estiverem fora do esperado
        if (kpis.getDeliveryRate() < 90.0) {
            alertService.sendAlert(
                AlertLevel.WARNING,
                "WhatsApp delivery rate below 90%: " + kpis.getDeliveryRate()
            );
        }
    }
}
```

---

## 5. Monitoramento e Alertas

### 5.1 Health Check
```java
@Component
public class WhatsAppWebhookHealthIndicator implements HealthIndicator {

    @Autowired
    private WhatsAppWebhookHandler webhookHandler;

    @Override
    public Health health() {
        Map<String, Long> stats = webhookHandler.getDeliveryStatistics();

        long total = stats.get("total");
        long failed = stats.get("failed");

        double failureRate = total > 0 ? (double) failed / total : 0.0;

        if (failureRate > 0.1) { // > 10% failure
            return Health.down()
                .withDetail("failureRate", failureRate)
                .withDetail("totalMessages", total)
                .withDetail("failedMessages", failed)
                .build();
        }

        return Health.up()
            .withDetail("totalMessages", total)
            .withDetail("failureRate", failureRate)
            .build();
    }
}
```

### 5.2 Alertas Proativos
```java
@Component
public class WhatsAppQualityMonitor {

    @Scheduled(fixedRate = 300000) // 5 minutos
    public void checkMessageQuality() {
        Map<String, Long> stats = webhookHandler.getDeliveryStatistics();

        // Verificar taxa de falha
        long total = stats.get("total");
        long failed = stats.get("failed");
        double failureRate = total > 0 ? (double) failed / total : 0.0;

        if (failureRate > 0.05) { // > 5%
            alertService.sendAlert(
                AlertLevel.CRITICAL,
                "WhatsApp failure rate exceeded 5%: " + (failureRate * 100) + "%"
            );
        }

        // Verificar taxa de entrega
        long delivered = stats.get("delivered");
        double deliveryRate = total > 0 ? (double) delivered / total : 0.0;

        if (deliveryRate < 0.90) { // < 90%
            alertService.sendAlert(
                AlertLevel.WARNING,
                "WhatsApp delivery rate below 90%: " + (deliveryRate * 100) + "%"
            );
        }
    }
}
```

---

## 6. Testes

### 6.1 Testes Unitários
```java
@ExtendWith(MockitoExtension.class)
class WhatsAppWebhookHandlerTest {

    @InjectMocks
    private WhatsAppWebhookHandler handler;

    @Test
    void processWebhook_ValidEvent_Success() {
        // Arrange
        WhatsAppWebhookDTO webhook = buildMockWebhook();

        // Act
        handler.processWebhook(webhook);

        // Assert
        MessageStatus status = handler.getMessageStatus("wamid.123");
        assertNotNull(status);
        assertEquals("delivered", status.getStatus());
    }

    @Test
    void processWebhook_EmptyEntry_NoException() {
        // Arrange
        WhatsAppWebhookDTO webhook = new WhatsAppWebhookDTO();
        webhook.setEntry(Collections.emptyList());

        // Act & Assert
        assertDoesNotThrow(() -> handler.processWebhook(webhook));
    }

    @Test
    void getDeliveryStatistics_MultipleMessages_CorrectCounts() {
        // Arrange
        processMultipleWebhooks();

        // Act
        Map<String, Long> stats = handler.getDeliveryStatistics();

        // Assert
        assertEquals(10L, stats.get("total"));
        assertEquals(8L, stats.get("delivered"));
        assertEquals(5L, stats.get("read"));
        assertEquals(2L, stats.get("failed"));
    }

    private WhatsAppWebhookDTO buildMockWebhook() {
        WhatsAppWebhookDTO.Status status = new WhatsAppWebhookDTO.Status();
        status.setId("wamid.123");
        status.setStatus("delivered");
        status.setTimestamp("2025-01-12T10:00:00Z");
        status.setRecipientId("5511987654321");

        WhatsAppWebhookDTO.Value value = new WhatsAppWebhookDTO.Value();
        value.setStatuses(Collections.singletonList(status));

        WhatsAppWebhookDTO.Change change = new WhatsAppWebhookDTO.Change();
        change.setValue(value);

        WhatsAppWebhookDTO.Entry entry = new WhatsAppWebhookDTO.Entry();
        entry.setChanges(Collections.singletonList(change));

        WhatsAppWebhookDTO webhook = new WhatsAppWebhookDTO();
        webhook.setEntry(Collections.singletonList(entry));

        return webhook;
    }
}
```

---

## 7. Glossário

- **Webhook**: Callback HTTP para notificar eventos assíncronos
- **Status Update**: Atualização do estado de uma mensagem
- **Message ID (WAMID)**: Identificador único de mensagem WhatsApp
- **Recipient ID**: Número do destinatário no formato WhatsApp
- **Idempotência**: Capacidade de processar a mesma requisição múltiplas vezes sem efeitos colaterais

---

## 8. Referências

### 8.1 Código Relacionado
- `WhatsAppWebhookDTO.java` - DTOs de webhook
- `WhatsAppService.java` - Serviço de envio
- `WhatsAppClient.java` - Cliente HTTP

### 8.2 Documentação Externa
- [WhatsApp Webhooks](https://developers.facebook.com/docs/whatsapp/webhooks)
- [Webhook Security](https://developers.facebook.com/docs/graph-api/webhooks/getting-started#verification-requests)
