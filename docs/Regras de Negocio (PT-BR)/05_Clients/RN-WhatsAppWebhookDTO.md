# RN-WhatsAppWebhookDTO - Estruturas de Eventos Webhook

## 1. Visão Geral

### 1.1 Objetivo
DTOs (Data Transfer Objects) que representam eventos de webhook recebidos do WhatsApp Business API, incluindo atualizações de status de mensagens, callbacks de entrega e eventos de interação.

### 1.2 Contexto no Ciclo da Receita
- **Módulo**: Integration Layer - Webhook DTOs
- **Processo BPMN**: Webhook Event Processing & Status Tracking
- **Componente**: `com.hospital.revenuecycle.integration.whatsapp.WhatsAppWebhookDTO`
- **Tipo**: Data Transfer Object (DTO)

### 1.3 Casos de Uso
- Recepção de eventos de status de mensagens
- Deserialização de callbacks do WhatsApp
- Rastreamento de entregas e leituras
- Processamento de falhas de envio
- Cálculo de métricas de engajamento

---

## 2. Estrutura dos DTOs

### 2.1 WhatsAppWebhookDTO (Principal)
**Descrição**: DTO raiz que encapsula todos os eventos de webhook.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public class WhatsAppWebhookDTO {

    @JsonProperty("object")
    private String object;

    @JsonProperty("entry")
    private List<Entry> entry;
}
```

**Campos**:
- `object`: Sempre "whatsapp_business_account" para webhooks do WhatsApp Business
- `entry`: Array de entries (eventos agrupados)

**JSON Exemplo**:
```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "123456789",
      "changes": [
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
      ]
    }
  ]
}
```

---

### 2.2 Entry
**Descrição**: Representa uma entrada de evento, agrupando múltiplas mudanças.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Entry {
    @JsonProperty("id")
    private String id;

    @JsonProperty("changes")
    private List<Change> changes;
}
```

**Campos**:
- `id`: ID da conta WhatsApp Business
- `changes`: Array de mudanças/eventos

**Uso**:
Uma entry pode conter múltiplos changes (ex: múltiplas atualizações de status recebidas no mesmo webhook).

---

### 2.3 Change
**Descrição**: Representa uma mudança específica (status update, message received, etc).

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Change {
    @JsonProperty("value")
    private Value value;

    @JsonProperty("field")
    private String field;
}
```

**Campos**:
- `value`: Dados da mudança
- `field`: Tipo de campo alterado (sempre "messages" para status updates)

**Tipos de Field**:
- `messages` - Atualizações de status de mensagens
- (Outros tipos podem ser adicionados pela API no futuro)

---

### 2.4 Value
**Descrição**: Contém os dados efetivos do evento.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Value {
    @JsonProperty("messaging_product")
    private String messagingProduct;

    @JsonProperty("metadata")
    private Metadata metadata;

    @JsonProperty("statuses")
    private List<Status> statuses;
}
```

**Campos**:
- `messagingProduct`: Sempre "whatsapp"
- `metadata`: Metadados do número de telefone
- `statuses`: Array de status updates

**Nota**: Além de `statuses`, pode conter também:
- `messages`: Mensagens recebidas (quando paciente responde)
- `contacts`: Informações de contato
- (Outros campos conforme evolução da API)

---

### 2.5 Metadata
**Descrição**: Metadados sobre o número de telefone do negócio.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Metadata {
    @JsonProperty("display_phone_number")
    private String displayPhoneNumber;

    @JsonProperty("phone_number_id")
    private String phoneNumberId;
}
```

**Campos**:
- `displayPhoneNumber`: Número de telefone formatado (ex: "15550000001")
- `phoneNumberId`: ID único do número no WhatsApp Business

**Uso**:
Útil para sistemas que gerenciam múltiplos números de telefone WhatsApp Business.

---

### 2.6 Status
**Descrição**: Representa uma atualização de status de mensagem individual.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Status {
    @JsonProperty("id")
    private String id;

    @JsonProperty("status")
    private String status; // sent, delivered, read, failed

    @JsonProperty("timestamp")
    private String timestamp;

    @JsonProperty("recipient_id")
    private String recipientId;
}
```

**Campos**:
- `id`: WhatsApp Message ID (wamid)
- `status`: Status atual da mensagem
- `timestamp`: Timestamp Unix (string) do evento
- `recipientId`: ID do destinatário (número sem +)

---

## 3. Regras de Negócio

### RN-WHD-001: Estados de Mensagem
**Descrição**: Mensagens transitam por estados específicos desde envio até leitura.

**Fluxo de Estados**:
```
ENVIADA (sent)
    ↓
ENTREGUE (delivered)
    ↓
LIDA (read)
```

**Estados Possíveis**:

| Status | Descrição | Quando Ocorre |
|--------|-----------|---------------|
| `sent` | Mensagem enviada ao servidor WhatsApp | Imediatamente após API aceitar |
| `delivered` | Entregue ao dispositivo do destinatário | Quando dispositivo recebe |
| `read` | Lida pelo destinatário | Quando usuário abre a conversa |
| `failed` | Falha na entrega | Número inválido, bloqueado, etc |

**Implementação**:
```java
public enum WhatsAppMessageStatus {
    SENT("sent"),
    DELIVERED("delivered"),
    READ("read"),
    FAILED("failed");

    private final String value;

    WhatsAppMessageStatus(String value) {
        this.value = value;
    }

    public static WhatsAppMessageStatus fromString(String value) {
        for (WhatsAppMessageStatus status : values()) {
            if (status.value.equalsIgnoreCase(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown status: " + value);
    }

    public boolean canTransitionTo(WhatsAppMessageStatus next) {
        return switch (this) {
            case SENT -> next == DELIVERED || next == FAILED;
            case DELIVERED -> next == READ || next == FAILED;
            case READ -> false; // Estado final
            case FAILED -> false; // Estado final
        };
    }
}
```

---

### RN-WHD-002: Validação de Transições de Estado
**Descrição**: O sistema deve validar transições de estado para detectar inconsistências.

**Implementação**:
```java
@Service
public class MessageStatusValidator {

    public void validateTransition(
            WhatsAppMessageStatus currentStatus,
            WhatsAppMessageStatus newStatus) {

        if (currentStatus == null) {
            // Primeira atualização - qualquer status é válido
            return;
        }

        if (!currentStatus.canTransitionTo(newStatus)) {
            log.warn("Invalid status transition: {} -> {}",
                currentStatus, newStatus);

            // Registrar métrica de inconsistência
            metricsService.incrementInvalidTransitions();

            // Não lançar exceção - aceitar mesmo assim
            // pois WhatsApp pode enviar updates fora de ordem
        }
    }

    public boolean isTerminalState(WhatsAppMessageStatus status) {
        return status == WhatsAppMessageStatus.READ ||
               status == WhatsAppMessageStatus.FAILED;
    }
}
```

---

### RN-WHD-003: Deserialização de Webhooks
**Descrição**: Webhooks devem ser deserializados com tratamento robusto de erros.

**Implementação**:
```java
@RestController
@RequestMapping("/webhooks/whatsapp")
public class WhatsAppWebhookController {

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private WhatsAppWebhookHandler handler;

    @PostMapping
    public ResponseEntity<Void> handleWebhook(
            @RequestBody String payload,
            @RequestHeader("X-Hub-Signature-256") String signature) {

        try {
            // Verificar assinatura
            if (!securityService.verifySignature(payload, signature)) {
                log.warn("Invalid webhook signature");
                return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
            }

            // Deserializar
            WhatsAppWebhookDTO webhook = objectMapper.readValue(
                payload,
                WhatsAppWebhookDTO.class
            );

            // Processar
            handler.processWebhook(webhook);

            return ResponseEntity.ok().build();

        } catch (JsonProcessingException e) {
            log.error("Failed to parse webhook payload", e);
            return ResponseEntity.badRequest().build();

        } catch (Exception e) {
            log.error("Error processing webhook", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
}
```

---

### RN-WHD-004: Timestamp Parsing
**Descrição**: Timestamps de webhooks devem ser parseados corretamente.

**Formato do Timestamp**:
- Tipo: Unix timestamp (string)
- Exemplo: "1736950200"
- Unidade: Segundos desde epoch

**Implementação**:
```java
public class WebhookTimestampParser {

    public static Instant parseTimestamp(String timestamp) {
        try {
            long seconds = Long.parseLong(timestamp);
            return Instant.ofEpochSecond(seconds);
        } catch (NumberFormatException e) {
            log.error("Invalid timestamp format: {}", timestamp);
            throw new IllegalArgumentException("Invalid timestamp: " + timestamp, e);
        }
    }

    public static LocalDateTime parseTimestampAsDateTime(
            String timestamp,
            ZoneId zoneId) {
        Instant instant = parseTimestamp(timestamp);
        return LocalDateTime.ofInstant(instant, zoneId);
    }

    // Para zona de Brasília
    public static LocalDateTime parseTimestampBRT(String timestamp) {
        return parseTimestampAsDateTime(
            timestamp,
            ZoneId.of("America/Sao_Paulo")
        );
    }
}
```

**Uso**:
```java
private void processStatusUpdate(WhatsAppWebhookDTO.Status status) {
    Instant statusTime = WebhookTimestampParser.parseTimestamp(
        status.getTimestamp()
    );

    LocalDateTime localTime = WebhookTimestampParser.parseTimestampBRT(
        status.getTimestamp()
    );

    log.info("Status update received at: {} (local: {})",
        statusTime, localTime);
}
```

---

### RN-WHD-005: Recipient ID Normalization
**Descrição**: O recipient_id deve ser normalizado para formato consistente.

**Formato do Recipient ID**:
- WhatsApp envia sem prefixo "+"
- Exemplo: "5511987654321" (não "+5511987654321")

**Normalização**:
```java
public class PhoneNumberNormalizer {

    /**
     * Normalizar recipient_id do webhook para formato E.164.
     */
    public static String normalizeRecipientId(String recipientId) {
        if (recipientId == null || recipientId.isEmpty()) {
            throw new IllegalArgumentException("Recipient ID cannot be null or empty");
        }

        // Adicionar + se ausente
        if (!recipientId.startsWith("+")) {
            recipientId = "+" + recipientId;
        }

        return recipientId;
    }

    /**
     * Converter E.164 para formato do WhatsApp (sem +).
     */
    public static String toWhatsAppFormat(String e164Number) {
        if (e164Number == null || e164Number.isEmpty()) {
            throw new IllegalArgumentException("Phone number cannot be null or empty");
        }

        return e164Number.replace("+", "");
    }

    /**
     * Verificar se número é válido.
     */
    public static boolean isValidE164(String phoneNumber) {
        if (phoneNumber == null) {
            return false;
        }

        Pattern e164Pattern = Pattern.compile("^\\+[1-9]\\d{1,14}$");
        return e164Pattern.matcher(phoneNumber).matches();
    }
}
```

**Uso no Handler**:
```java
private void processStatusUpdate(WhatsAppWebhookDTO.Status status) {
    // Normalizar recipient ID
    String normalizedPhone = PhoneNumberNormalizer.normalizeRecipientId(
        status.getRecipientId()
    );

    // Buscar paciente
    Patient patient = patientService.findByPhoneNumber(normalizedPhone);

    // Atualizar status
    updateMessageStatus(status.getId(), status.getStatus(), patient);
}
```

---

### RN-WHD-006: Extração de Informações de Erro
**Descrição**: Quando status é "failed", o webhook pode conter informações adicionais sobre o erro.

**Estrutura Estendida**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Status {
    // ... campos existentes ...

    @JsonProperty("errors")
    private List<ErrorDetail> errors;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ErrorDetail {
        @JsonProperty("code")
        private Integer code;

        @JsonProperty("title")
        private String title;

        @JsonProperty("message")
        private String message;

        @JsonProperty("error_data")
        private ErrorData errorData;
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ErrorData {
        @JsonProperty("details")
        private String details;
    }
}
```

**Códigos de Erro Comuns**:
| Código | Descrição | Ação |
|--------|-----------|------|
| 131026 | Número de telefone não registrado no WhatsApp | Informar paciente |
| 131047 | Re-engagement message outside 24h window | Usar template |
| 131051 | Unsupported message type | Revisar template |
| 470 | Template não aprovado | Aguardar aprovação |
| 131005 | Número do destinatário é inválido | Validar número |

**Handler de Erros**:
```java
private void handleFailed(MessageStatus status) {
    log.error("Message failed: {}", status.getMessageId());

    // Analisar código de erro
    if (status.getErrors() != null && !status.getErrors().isEmpty()) {
        ErrorDetail error = status.getErrors().get(0);

        switch (error.getCode()) {
            case 131026: // Número não no WhatsApp
                handleNumberNotOnWhatsApp(status);
                break;

            case 131047: // Fora da janela de 24h
                handleOutsideEngagementWindow(status);
                break;

            case 131005: // Número inválido
                handleInvalidNumber(status);
                break;

            default:
                handleGenericError(status, error);
        }
    }
}

private void handleNumberNotOnWhatsApp(MessageStatus status) {
    // Marcar número como não WhatsApp
    Patient patient = patientService.findByMessageId(status.getMessageId());
    if (patient != null) {
        patient.setHasWhatsApp(false);
        patientRepository.save(patient);

        // Enviar por canal alternativo (SMS, e-mail)
        notificationService.sendFallbackNotification(patient);
    }
}
```

---

## 4. Webhook Verification

### 4.1 Verificação GET (Challenge)
**Descrição**: WhatsApp envia GET request para verificar o webhook endpoint.

**Implementação**:
```java
@GetMapping
public ResponseEntity<String> verifyWebhook(
        @RequestParam("hub.mode") String mode,
        @RequestParam("hub.verify_token") String token,
        @RequestParam("hub.challenge") String challenge) {

    log.info("Webhook verification request: mode={}, token={}",
        mode, token);

    if ("subscribe".equals(mode) && verifyToken.equals(token)) {
        log.info("Webhook verification successful");
        return ResponseEntity.ok(challenge);
    }

    log.warn("Webhook verification failed");
    return ResponseEntity.status(HttpStatus.FORBIDDEN).body("Verification failed");
}
```

**Query Parameters**:
- `hub.mode`: Sempre "subscribe"
- `hub.verify_token`: Token configurado no WhatsApp Business Manager
- `hub.challenge`: String aleatória que deve ser retornada

---

### 4.2 Verificação de Assinatura (POST)
**Descrição**: Webhooks POST devem ter assinatura HMAC-SHA256 verificada.

**Header**:
```
X-Hub-Signature-256: sha256=<hash>
```

**Verificação**:
```java
public boolean verifySignature(String payload, String signature) {
    if (signature == null || !signature.startsWith("sha256=")) {
        return false;
    }

    String receivedHash = signature.substring(7); // Remove "sha256="

    String expectedHash = calculateHmacSHA256(payload, appSecret);

    return MessageDigest.isEqual(
        receivedHash.getBytes(StandardCharsets.UTF_8),
        expectedHash.getBytes(StandardCharsets.UTF_8)
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
```

---

## 5. Exemplos de Webhooks Reais

### 5.1 Status Update: Sent
```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "123456789",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "15550000001",
          "phone_number_id": "123456789"
        },
        "statuses": [{
          "id": "wamid.HBgNNTUxMTk4NzY1NDMyMRUCABIYFjNFQjA2RjcyRjI2QzQ5RkZBMDlGREEA",
          "status": "sent",
          "timestamp": "1736950200",
          "recipient_id": "5511987654321"
        }]
      },
      "field": "messages"
    }]
  }]
}
```

### 5.2 Status Update: Delivered
```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "123456789",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "15550000001",
          "phone_number_id": "123456789"
        },
        "statuses": [{
          "id": "wamid.HBgNNTUxMTk4NzY1NDMyMRUCABIYFjNFQjA2RjcyRjI2QzQ5RkZBMDlGREEA",
          "status": "delivered",
          "timestamp": "1736950205",
          "recipient_id": "5511987654321"
        }]
      },
      "field": "messages"
    }]
  }]
}
```

### 5.3 Status Update: Failed
```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "123456789",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "15550000001",
          "phone_number_id": "123456789"
        },
        "statuses": [{
          "id": "wamid.HBgNNTUxMTk4NzY1NDMyMRUCABIYFjNFQjA2RjcyRjI2QzQ5RkZBMDlGREEA",
          "status": "failed",
          "timestamp": "1736950210",
          "recipient_id": "5511987654321",
          "errors": [{
            "code": 131026,
            "title": "Number not on WhatsApp",
            "message": "Phone number is not a WhatsApp phone number",
            "error_data": {
              "details": "The phone number is not registered with WhatsApp"
            }
          }]
        }]
      },
      "field": "messages"
    }]
  }]
}
```

---

## 6. Testes

### 6.1 Testes de Deserialização
```java
@Test
void deserialize_SentStatus_Success() throws Exception {
    String json = """
        {
          "object": "whatsapp_business_account",
          "entry": [{
            "id": "123456789",
            "changes": [{
              "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                  "display_phone_number": "15550000001",
                  "phone_number_id": "123456789"
                },
                "statuses": [{
                  "id": "wamid.ABC123",
                  "status": "sent",
                  "timestamp": "1736950200",
                  "recipient_id": "5511987654321"
                }]
              },
              "field": "messages"
            }]
          }]
        }
        """;

    ObjectMapper mapper = new ObjectMapper();
    WhatsAppWebhookDTO webhook = mapper.readValue(
        json,
        WhatsAppWebhookDTO.class
    );

    assertNotNull(webhook);
    assertEquals("whatsapp_business_account", webhook.getObject());
    assertEquals(1, webhook.getEntry().size());

    WhatsAppWebhookDTO.Status status =
        webhook.getEntry().get(0)
               .getChanges().get(0)
               .getValue().getStatuses().get(0);

    assertEquals("wamid.ABC123", status.getId());
    assertEquals("sent", status.getStatus());
    assertEquals("5511987654321", status.getRecipientId());
}
```

### 6.2 Testes de Validação
```java
@Test
void validateTransition_ValidTransition_NoException() {
    WhatsAppMessageStatus current = WhatsAppMessageStatus.SENT;
    WhatsAppMessageStatus next = WhatsAppMessageStatus.DELIVERED;

    assertDoesNotThrow(() ->
        validator.validateTransition(current, next)
    );
}

@Test
void validateTransition_InvalidTransition_LogsWarning() {
    WhatsAppMessageStatus current = WhatsAppMessageStatus.READ;
    WhatsAppMessageStatus next = WhatsAppMessageStatus.SENT;

    // Não deve lançar exceção, mas deve logar warning
    validator.validateTransition(current, next);

    verify(metricsService).incrementInvalidTransitions();
}
```

---

## 7. Monitoramento

### 7.1 Métricas de Webhook
```java
@Service
public class WebhookMetricsService {

    public WebhookStats getWebhookStats(Duration period) {
        Instant since = Instant.now().minus(period);

        return WebhookStats.builder()
            .totalReceived(countWebhooksReceived(since))
            .totalProcessed(countWebhooksProcessed(since))
            .totalFailed(countWebhooksFailed(since))
            .averageProcessingTime(calculateAvgProcessingTime(since))
            .statusBreakdown(getStatusBreakdown(since))
            .build();
    }

    private Map<String, Long> getStatusBreakdown(Instant since) {
        return Map.of(
            "sent", countStatusUpdates("sent", since),
            "delivered", countStatusUpdates("delivered", since),
            "read", countStatusUpdates("read", since),
            "failed", countStatusUpdates("failed", since)
        );
    }
}
```

---

## 8. Glossário

- **Webhook**: Callback HTTP para notificação de eventos
- **Entry**: Agrupamento de eventos no webhook
- **Change**: Mudança individual dentro de uma entry
- **Status Update**: Atualização de estado de uma mensagem
- **Recipient ID**: Identificador do destinatário (número sem +)
- **Unix Timestamp**: Segundos desde 1970-01-01 00:00:00 UTC

---

## 9. Referências

### 9.1 Código Relacionado
- `WhatsAppWebhookHandler.java` - Processador de webhooks
- `WhatsAppService.java` - Serviço de envio
- `WhatsAppClient.java` - Cliente HTTP

### 9.2 Documentação Externa
- [WhatsApp Webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks)
- [Webhook Status Updates](https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples#status-updates)
- [Error Codes](https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes)
