# RN-WhatsAppService - Serviço de Integração WhatsApp

## 1. Visão Geral

### 1.1 Objetivo
Serviço de alto nível que encapsula a lógica de negócio para envio de mensagens WhatsApp, gerenciando validações, formatação e tratamento de erros.

### 1.2 Contexto no Ciclo da Receita
- **Módulo**: Integration Layer
- **Processo BPMN**: Patient Communication & Notifications
- **Componente**: `com.hospital.revenuecycle.integration.whatsapp.WhatsAppService`
- **Tipo**: Spring Service (@Service)

### 1.3 Casos de Uso
- Envio de lembretes de pagamento
- Notificações de agendamento
- Confirmações de consulta
- Alertas de vencimento de boletos
- Comunicação de resultados (via link seguro)

---

## 2. Regras de Negócio

### RN-WAS-001: Envio de Mensagem Template
**Descrição**: O serviço deve validar e enviar mensagens template via WhatsApp Business API.

**Assinatura**:
```java
public String sendTemplateMessage(
    String phoneNumber,       // Formato E.164: +5511987654321
    String templateId,        // ID do template aprovado
    String message,           // Conteúdo da mensagem
    Map<String, String> parameters  // Parâmetros dinâmicos
) throws WhatsAppException
```

**Validações Obrigatórias**:
1. **Validação de Telefone**:
```java
if (phoneNumber == null || phoneNumber.isEmpty()) {
    throw new WhatsAppException("Phone number is required");
}
// Formato E.164: +[country code][number]
Pattern e164Pattern = Pattern.compile("^\\+[1-9]\\d{1,14}$");
if (!e164Pattern.matcher(phoneNumber).matches()) {
    throw new WhatsAppException("Invalid phone number format. Use E.164: +5511987654321");
}
```

2. **Validação de Template**:
```java
if (templateId == null || templateId.isEmpty()) {
    throw new WhatsAppException("Template ID is required");
}
// Template deve existir e estar aprovado
if (!templateRegistry.isApproved(templateId)) {
    throw new WhatsAppException("Template not approved: " + templateId);
}
```

3. **Validação de Parâmetros**:
```java
Template template = templateRegistry.getTemplate(templateId);
Set<String> requiredParams = template.getRequiredParameters();
if (!parameters.keySet().containsAll(requiredParams)) {
    throw new WhatsAppException("Missing required parameters: " +
        requiredParams.stream()
            .filter(p -> !parameters.containsKey(p))
            .collect(Collectors.joining(", ")));
}
```

**Retorno**:
- String: WhatsApp Message ID (formato: `wamid.HBgN...`)
- Exceção: `WhatsAppException` em caso de falha

---

### RN-WAS-002: Tratamento de Erros
**Descrição**: O serviço deve capturar e tratar adequadamente erros da API do WhatsApp.

**Exception Hierarchy**:
```java
public static class WhatsAppException extends RuntimeException {
    public WhatsAppException(String message) {
        super(message);
    }

    public WhatsAppException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

**Categorias de Erro**:

1. **Erros de Validação** (400 Bad Request):
```java
try {
    validatePhoneNumber(phoneNumber);
    validateTemplate(templateId);
} catch (ValidationException e) {
    throw new WhatsAppException("Validation failed: " + e.getMessage());
}
```

2. **Erros de Autenticação** (401 Unauthorized):
```java
catch (UnauthorizedException e) {
    log.error("WhatsApp authentication failed. Token may be expired.");
    throw new WhatsAppException("Authentication failed. Please check credentials.", e);
}
```

3. **Erros de Rate Limit** (429 Too Many Requests):
```java
catch (RateLimitException e) {
    log.warn("WhatsApp rate limit exceeded. Retry after: {}", e.getRetryAfter());
    throw new WhatsAppException("Rate limit exceeded. Please try again later.", e);
}
```

4. **Erros de Rede** (IOException):
```java
catch (IOException e) {
    log.error("Network error sending WhatsApp message", e);
    throw new WhatsAppException("Network error. Message not sent.", e);
}
```

---

### RN-WAS-003: Logging e Auditoria
**Descrição**: Todas as operações devem ser registradas para auditoria e troubleshooting.

**Logs Obrigatórios**:

1. **Antes do Envio**:
```java
log.info("Sending WhatsApp template message: phone={}, template={}",
    maskPhoneNumber(phoneNumber), templateId);
```

2. **Sucesso**:
```java
log.info("WhatsApp message sent successfully: messageId={}, phone={}",
    messageId, maskPhoneNumber(phoneNumber));
```

3. **Falha**:
```java
log.error("Failed to send WhatsApp message: phone={}, template={}, error={}",
    maskPhoneNumber(phoneNumber), templateId, e.getMessage(), e);
```

**Mascaramento de Dados Sensíveis**:
```java
private String maskPhoneNumber(String phoneNumber) {
    // +5511987654321 -> +5511****4321
    if (phoneNumber.length() > 8) {
        return phoneNumber.substring(0, 6) + "****" +
               phoneNumber.substring(phoneNumber.length() - 4);
    }
    return "****";
}
```

---

### RN-WAS-004: Geração de Message ID
**Descrição**: O sistema deve retornar um identificador único para cada mensagem enviada.

**Implementação Atual (Placeholder)**:
```java
// TODO: Substituir por integração real com WhatsApp API
String messageId = "wa_" + System.currentTimeMillis();
```

**Implementação Futura (Real)**:
```java
Response<WhatsAppResponse> response = whatsAppClient
    .sendTemplateMessage(phoneNumberId, "Bearer " + accessToken, templateDTO)
    .execute();

if (!response.isSuccessful()) {
    throw new WhatsAppException("API error: " + response.code());
}

WhatsAppResponse body = response.body();
return body.getMessages().get(0).getId();
```

**Formato do Message ID**:
- Prefixo: `wamid.`
- Exemplo: `wamid.HBgNNTUxMTk4NzY1NDMyMRUCABIYFjNFQjA2RjcyRjI2QzQ5RkZBMDlGREEA`
- Único globalmente
- Usado para tracking e callbacks

---

### RN-WAS-005: Formatação de Números de Telefone
**Descrição**: Números de telefone devem seguir o padrão E.164 internacional.

**Formato E.164**:
```
+[country code][area code][number]
```

**Exemplos Válidos**:
- Brasil (móvel): `+5511987654321`
- Brasil (fixo): `+551132123456`
- EUA: `+14155552671`
- Portugal: `+351912345678`

**Validação Regex**:
```java
private static final Pattern E164_PATTERN =
    Pattern.compile("^\\+[1-9]\\d{1,14}$");

public boolean isValidE164(String phoneNumber) {
    return E164_PATTERN.matcher(phoneNumber).matches();
}
```

**Normalização**:
```java
public String normalizePhoneNumber(String input) {
    // Remove espaços, parênteses, hífens
    String cleaned = input.replaceAll("[\\s()\\-]", "");

    // Adiciona + se ausente
    if (!cleaned.startsWith("+")) {
        cleaned = "+" + cleaned;
    }

    // Validar formato
    if (!isValidE164(cleaned)) {
        throw new IllegalArgumentException("Invalid phone number: " + input);
    }

    return cleaned;
}
```

---

### RN-WAS-006: Verificação de Consentimento (LGPD)
**Descrição**: Antes de enviar qualquer mensagem, o sistema deve verificar o consentimento do paciente.

**Implementação**:
```java
public String sendTemplateMessage(
    String phoneNumber,
    String templateId,
    String message,
    Map<String, String> parameters) {

    // 1. Verificar consentimento LGPD
    Patient patient = patientService.findByPhoneNumber(phoneNumber);
    if (patient == null || !patient.hasWhatsAppConsent()) {
        throw new WhatsAppException(
            "Patient has not consented to WhatsApp communications. " +
            "Consent required per LGPD Art. 7º"
        );
    }

    // 2. Verificar se consentimento não foi revogado
    if (patient.getWhatsAppConsentRevokedAt() != null) {
        throw new WhatsAppException(
            "Patient has revoked WhatsApp consent on " +
            patient.getWhatsAppConsentRevokedAt()
        );
    }

    // 3. Registrar envio para auditoria
    auditService.logWhatsAppMessage(
        patient.getId(),
        templateId,
        LocalDateTime.now()
    );

    // 4. Enviar mensagem
    return doSendTemplateMessage(phoneNumber, templateId, message, parameters);
}
```

**Registro de Consentimento**:
```java
@Entity
public class PatientConsent {
    @Id
    private Long id;

    @ManyToOne
    private Patient patient;

    @Enumerated(EnumType.STRING)
    private ConsentType type; // WHATSAPP, EMAIL, SMS

    private Boolean granted;
    private LocalDateTime grantedAt;
    private LocalDateTime revokedAt;
    private String ipAddress;
    private String userAgent;

    // Evidência de consentimento
    private String consentText;
    private String consentMethod; // WEB, MOBILE, PRESENCIAL
}
```

---

## 3. Conformidade Regulatória

### 3.1 LGPD - Lei Geral de Proteção de Dados

**Artigos Aplicáveis**:

**Art. 7º - Base Legal**:
- Consentimento explícito do titular (paciente)
- Execução de contrato (lembretes de consulta/pagamento)
- Cumprimento de obrigação legal (notificações fiscais)

**Implementação**:
```java
public enum ConsentBasis {
    CONSENT,              // Consentimento explícito
    CONTRACT_EXECUTION,   // Execução de contrato
    LEGAL_OBLIGATION,     // Obrigação legal
    LEGITIMATE_INTEREST   // Interesse legítimo
}

@Entity
public class WhatsAppMessage {
    @Enumerated(EnumType.STRING)
    private ConsentBasis legalBasis;

    private String justification; // Justificativa da base legal
}
```

**Art. 9º - Dados Sensíveis de Saúde**:
```java
// NUNCA enviar informações clínicas detalhadas via WhatsApp
// Usar apenas links seguros para acesso a resultados

// ❌ ERRADO
"Seu resultado de glicemia é 250 mg/dL (hiperglicemia)"

// ✅ CORRETO
"Seu resultado de exame está disponível. Acesse: https://portal.hospital.com/results/{token}"
```

**Art. 18º - Direitos do Titular**:
```java
public interface PatientRights {
    // Confirmação de tratamento
    List<WhatsAppMessage> getMyMessages(Long patientId);

    // Acesso aos dados
    ConsentRecord getMyConsent(Long patientId);

    // Correção de dados
    void updatePhoneNumber(Long patientId, String newPhone);

    // Eliminação
    void deleteMyMessages(Long patientId);

    // Revogação de consentimento
    void revokeWhatsAppConsent(Long patientId);
}
```

---

### 3.2 WhatsApp Business Policy

**Política de Qualidade de Mensagens**:
```java
@Service
public class WhatsAppQualityMonitor {

    private static final double MAX_BLOCK_RATE = 0.02; // 2%
    private static final int RATE_WINDOW_HOURS = 24;

    public void checkQuality() {
        MessageQualityMetrics metrics = calculateMetrics();

        if (metrics.getBlockRate() > MAX_BLOCK_RATE) {
            // Pausar envios automáticos
            log.error("WhatsApp block rate exceeded: {}%",
                metrics.getBlockRate() * 100);
            alertService.notifyAdministrators(
                "WhatsApp Quality Alert: Block rate above 2%"
            );
            pauseAutomaticMessages();
        }
    }

    private MessageQualityMetrics calculateMetrics() {
        long totalSent = messageRepository.countSentInLast(RATE_WINDOW_HOURS);
        long totalBlocked = messageRepository.countBlockedInLast(RATE_WINDOW_HOURS);

        return MessageQualityMetrics.builder()
            .totalSent(totalSent)
            .totalBlocked(totalBlocked)
            .blockRate((double) totalBlocked / totalSent)
            .timestamp(LocalDateTime.now())
            .build();
    }
}
```

**Limites de Taxa por Tier**:
```java
public enum WhatsAppTier {
    TIER_1(1000),      // 1k mensagens/dia
    TIER_2(10_000),    // 10k mensagens/dia
    TIER_3(100_000),   // 100k mensagens/dia
    UNLIMITED(-1);     // Sem limite

    private final int dailyLimit;

    public boolean canSendMessage(int sentToday) {
        return dailyLimit == -1 || sentToday < dailyLimit;
    }
}
```

---

## 4. Integração com Outros Componentes

### 4.1 NotificationService
```java
@Service
public class NotificationService {
    @Autowired
    private WhatsAppService whatsAppService;

    public void sendPaymentReminder(Long patientId, Long invoiceId) {
        Patient patient = patientService.findById(patientId);
        Invoice invoice = invoiceService.findById(invoiceId);

        if (patient.hasWhatsAppConsent()) {
            whatsAppService.sendTemplateMessage(
                patient.getPhoneNumber(),
                "payment_reminder",
                buildPaymentMessage(invoice),
                Map.of(
                    "patient_name", patient.getName(),
                    "amount", formatCurrency(invoice.getAmount()),
                    "due_date", formatDate(invoice.getDueDate())
                )
            );
        }
    }
}
```

### 4.2 AppointmentService
```java
@Service
public class AppointmentService {
    @Autowired
    private WhatsAppService whatsAppService;

    public void sendAppointmentConfirmation(Long appointmentId) {
        Appointment appointment = appointmentRepository.findById(appointmentId);
        Patient patient = appointment.getPatient();

        if (patient.hasWhatsAppConsent()) {
            whatsAppService.sendTemplateMessage(
                patient.getPhoneNumber(),
                "appointment_confirmation",
                buildAppointmentMessage(appointment),
                Map.of(
                    "patient_name", patient.getName(),
                    "doctor_name", appointment.getDoctor().getName(),
                    "date", formatDate(appointment.getDateTime()),
                    "time", formatTime(appointment.getDateTime()),
                    "location", appointment.getLocation()
                )
            );
        }
    }
}
```

### 4.3 PatientService
```java
@Service
public class PatientService {

    public Patient findByPhoneNumber(String phoneNumber) {
        String normalized = normalizePhoneNumber(phoneNumber);
        return patientRepository.findByPhoneNumber(normalized)
            .orElseThrow(() -> new PatientNotFoundException(phoneNumber));
    }

    public void updateWhatsAppConsent(Long patientId, boolean consent) {
        Patient patient = findById(patientId);

        PatientConsent consentRecord = PatientConsent.builder()
            .patient(patient)
            .type(ConsentType.WHATSAPP)
            .granted(consent)
            .grantedAt(consent ? LocalDateTime.now() : null)
            .revokedAt(!consent ? LocalDateTime.now() : null)
            .consentMethod("WEB")
            .build();

        consentRepository.save(consentRecord);

        log.info("WhatsApp consent updated: patientId={}, consent={}",
            patientId, consent);
    }
}
```

---

## 5. Templates de Mensagens

### 5.1 Template de Lembrete de Pagamento
```json
{
  "name": "payment_reminder",
  "language": "pt_BR",
  "category": "UTILITY",
  "components": [
    {
      "type": "BODY",
      "text": "Olá {{1}}, temos uma fatura pendente no valor de {{2}} com vencimento em {{3}}. Para evitar juros, realize o pagamento até a data de vencimento."
    },
    {
      "type": "FOOTER",
      "text": "Hospital XYZ - Central de Atendimento"
    }
  ]
}
```

### 5.2 Template de Confirmação de Consulta
```json
{
  "name": "appointment_confirmation",
  "language": "pt_BR",
  "category": "UTILITY",
  "components": [
    {
      "type": "BODY",
      "text": "Olá {{1}}, sua consulta com Dr(a). {{2}} está confirmada para {{3}} às {{4}}. Local: {{5}}. Em caso de impedimento, favor reagendar com 24h de antecedência."
    },
    {
      "type": "BUTTON",
      "buttons": [
        {
          "type": "URL",
          "text": "Ver detalhes",
          "url": "https://portal.hospital.com/appointments/{{6}}"
        }
      ]
    }
  ]
}
```

### 5.3 Template de Resultado Disponível
```json
{
  "name": "exam_result_available",
  "language": "pt_BR",
  "category": "UTILITY",
  "components": [
    {
      "type": "BODY",
      "text": "Olá {{1}}, o resultado do seu exame já está disponível. Acesse o portal do paciente para visualizar: {{2}}"
    }
  ]
}
```

---

## 6. Tratamento de Cenários Especiais

### 6.1 Telefones Internacionais
```java
public boolean isBrazilianNumber(String phoneNumber) {
    return phoneNumber.startsWith("+55");
}

public boolean isInternationalNumber(String phoneNumber) {
    return !isBrazilianNumber(phoneNumber);
}

public void sendTemplateMessage(String phoneNumber, String templateId, ...) {
    // Ajustar idioma do template baseado no país
    String languageCode = isBrazilianNumber(phoneNumber) ? "pt_BR" : "en_US";

    Template template = templateRegistry.getTemplate(templateId, languageCode);
    // ...
}
```

### 6.2 Números Bloqueados
```java
@Service
public class PhoneBlocklistService {

    public boolean isBlocked(String phoneNumber) {
        return blocklistRepository.existsByPhoneNumber(phoneNumber);
    }

    public void blockNumber(String phoneNumber, String reason) {
        PhoneBlocklist entry = PhoneBlocklist.builder()
            .phoneNumber(phoneNumber)
            .reason(reason)
            .blockedAt(LocalDateTime.now())
            .build();
        blocklistRepository.save(entry);
    }
}

// No WhatsAppService
public String sendTemplateMessage(...) {
    if (blocklistService.isBlocked(phoneNumber)) {
        throw new WhatsAppException("Phone number is blocked");
    }
    // ...
}
```

### 6.3 Horário de Envio (Quiet Hours)
```java
@Service
public class MessageScheduler {

    private static final int QUIET_START_HOUR = 22; // 22:00
    private static final int QUIET_END_HOUR = 8;    // 08:00

    public boolean isQuietHours(ZonedDateTime now) {
        int hour = now.getHour();
        return hour >= QUIET_START_HOUR || hour < QUIET_END_HOUR;
    }

    public ZonedDateTime getNextAllowedTime(ZonedDateTime requested) {
        if (isQuietHours(requested)) {
            return requested
                .withHour(QUIET_END_HOUR)
                .withMinute(0)
                .plusDays(requested.getHour() >= QUIET_START_HOUR ? 1 : 0);
        }
        return requested;
    }
}
```

---

## 7. Monitoramento e Métricas

### 7.1 Métricas de Negócio
```java
@Service
public class WhatsAppMetricsService {

    public WhatsAppMetrics getMetrics(LocalDate startDate, LocalDate endDate) {
        return WhatsAppMetrics.builder()
            .totalSent(countSent(startDate, endDate))
            .totalDelivered(countDelivered(startDate, endDate))
            .totalRead(countRead(startDate, endDate))
            .totalFailed(countFailed(startDate, endDate))
            .deliveryRate(calculateDeliveryRate(startDate, endDate))
            .readRate(calculateReadRate(startDate, endDate))
            .avgDeliveryTime(calculateAvgDeliveryTime(startDate, endDate))
            .build();
    }

    private double calculateDeliveryRate(LocalDate start, LocalDate end) {
        long sent = countSent(start, end);
        long delivered = countDelivered(start, end);
        return sent > 0 ? (double) delivered / sent : 0.0;
    }
}
```

### 7.2 Alertas Automáticos
```java
@Component
public class WhatsAppHealthCheck {

    @Scheduled(fixedRate = 300000) // 5 minutos
    public void checkHealth() {
        WhatsAppMetrics metrics = metricsService.getRecentMetrics();

        if (metrics.getDeliveryRate() < 0.90) {
            alertService.sendAlert(
                AlertLevel.WARNING,
                "WhatsApp delivery rate below 90%: " + metrics.getDeliveryRate()
            );
        }

        if (metrics.getFailureRate() > 0.05) {
            alertService.sendAlert(
                AlertLevel.CRITICAL,
                "WhatsApp failure rate above 5%: " + metrics.getFailureRate()
            );
        }
    }
}
```

---

## 8. Testes

### 8.1 Testes Unitários
```java
@ExtendWith(MockitoExtension.class)
class WhatsAppServiceTest {

    @Mock
    private WhatsAppClient whatsAppClient;

    @InjectMocks
    private WhatsAppService whatsAppService;

    @Test
    void sendTemplateMessage_ValidInput_Success() {
        // Arrange
        String phoneNumber = "+5511987654321";
        String templateId = "payment_reminder";
        String message = "Test message";
        Map<String, String> parameters = Map.of("amount", "R$ 100,00");

        // Act
        String messageId = whatsAppService.sendTemplateMessage(
            phoneNumber, templateId, message, parameters
        );

        // Assert
        assertNotNull(messageId);
        assertTrue(messageId.startsWith("wa_"));
    }

    @Test
    void sendTemplateMessage_InvalidPhone_ThrowsException() {
        // Arrange
        String invalidPhone = "invalid";

        // Act & Assert
        assertThrows(WhatsAppException.class, () -> {
            whatsAppService.sendTemplateMessage(
                invalidPhone, "template", "message", Map.of()
            );
        });
    }

    @Test
    void sendTemplateMessage_NullPhone_ThrowsException() {
        // Act & Assert
        WhatsAppException exception = assertThrows(WhatsAppException.class, () -> {
            whatsAppService.sendTemplateMessage(
                null, "template", "message", Map.of()
            );
        });

        assertEquals("Phone number is required", exception.getMessage());
    }
}
```

---

## 9. TODO: Implementações Futuras

### 9.1 Integração Real com WhatsApp API
```java
// Substituir implementação placeholder por integração real
@Service
public class WhatsAppService {
    @Autowired
    private WhatsAppClient whatsAppClient;

    @Value("${whatsapp.phone-number-id}")
    private String phoneNumberId;

    @Value("${whatsapp.access-token}")
    private String accessToken;

    public String sendTemplateMessage(...) {
        // Construir DTO
        WhatsAppTemplateDTO templateDTO = buildTemplateDTO(...);

        // Enviar via Retrofit
        Response<WhatsAppResponse> response = whatsAppClient
            .sendTemplateMessage(
                phoneNumberId,
                "Bearer " + accessToken,
                templateDTO
            )
            .execute();

        // Processar resposta
        if (!response.isSuccessful()) {
            throw new WhatsAppException("API error: " + response.errorBody().string());
        }

        return response.body().getMessages().get(0).getId();
    }
}
```

### 9.2 Sistema de Retry Inteligente
```java
@Service
public class WhatsAppRetryService {

    @Retryable(
        value = {IOException.class, WhatsAppException.class},
        maxAttempts = 3,
        backoff = @Backoff(delay = 1000, multiplier = 2.0)
    )
    public String sendWithRetry(String phoneNumber, String templateId, ...) {
        return whatsAppService.sendTemplateMessage(phoneNumber, templateId, ...);
    }
}
```

### 9.3 Sistema de Fila para Envios em Massa
```java
@Service
public class WhatsAppBulkSender {

    @RabbitListener(queues = "whatsapp.outbound")
    public void processBulkMessage(WhatsAppMessageDTO message) {
        try {
            whatsAppService.sendTemplateMessage(
                message.getPhoneNumber(),
                message.getTemplateId(),
                message.getContent(),
                message.getParameters()
            );
        } catch (Exception e) {
            // Enviar para DLQ
            rabbitTemplate.convertAndSend("whatsapp.dlq", message);
        }
    }
}
```

---

## 10. Referências

### 10.1 Código Relacionado
- `WhatsAppClient.java` - Interface Retrofit
- `WhatsAppWebhookHandler.java` - Processamento de webhooks
- `WhatsAppTemplateDTO.java` - DTOs de mensagem
- `WhatsAppClientConfig.java` - Configuração

### 10.2 Documentação Externa
- [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp)
- [WhatsApp Templates](https://developers.facebook.com/docs/whatsapp/message-templates)
- [LGPD - Lei 13.709/2018](http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)

### 10.3 Padrões e Convenções
- E.164 Phone Number Format
- ISO 8601 Date/Time Format
- OAuth 2.0 Bearer Token
