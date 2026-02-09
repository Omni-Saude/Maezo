# RN-WhatsAppTemplateDTO - Estruturas de Mensagens Template

## 1. Visão Geral

### 1.1 Objetivo
DTOs (Data Transfer Objects) que representam a estrutura de mensagens template do WhatsApp Business API, incluindo componentes, parâmetros, linguagem e respostas da API.

### 1.2 Contexto no Ciclo da Receita
- **Módulo**: Integration Layer - DTOs
- **Processo BPMN**: Message Serialization & Deserialization
- **Componente**: `com.hospital.revenuecycle.integration.whatsapp.WhatsAppTemplateDTO`
- **Tipo**: Data Transfer Object (DTO)

### 1.3 Casos de Uso
- Serialização de mensagens template para envio
- Deserialização de respostas da API
- Validação de estrutura de mensagens
- Construção de mensagens dinâmicas com parâmetros

---

## 2. Estrutura dos DTOs

### 2.1 WhatsAppTemplateDTO (Principal)
**Descrição**: DTO principal que encapsula toda a mensagem template.

**Estrutura**:
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class WhatsAppTemplateDTO {

    @JsonProperty("messaging_product")
    @Builder.Default
    private String messagingProduct = "whatsapp";

    @JsonProperty("to")
    private String recipientNumber;

    @JsonProperty("type")
    @Builder.Default
    private String type = "template";

    @JsonProperty("template")
    private Template template;
}
```

**Campos**:
- `messagingProduct`: Sempre "whatsapp" (fixo)
- `recipientNumber`: Número do destinatário (formato E.164)
- `type`: Tipo de mensagem, sempre "template" para mensagens proativas
- `template`: Objeto com detalhes do template

**JSON Serializado**:
```json
{
  "messaging_product": "whatsapp",
  "to": "+5511987654321",
  "type": "template",
  "template": {
    "name": "payment_reminder",
    "language": {
      "code": "pt_BR"
    },
    "components": [...]
  }
}
```

---

### 2.2 Template
**Descrição**: Contém informações do template (nome, idioma, componentes).

**Estrutura**:
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public static class Template {
    @JsonProperty("name")
    private String name;

    @JsonProperty("language")
    private Language language;

    @JsonProperty("components")
    private List<Component> components;
}
```

**Campos**:
- `name`: Nome do template aprovado no WhatsApp Business Manager
- `language`: Código de idioma do template
- `components`: Lista de componentes (header, body, footer, buttons)

**Exemplo**:
```json
{
  "name": "payment_reminder",
  "language": {
    "code": "pt_BR"
  },
  "components": [
    {
      "type": "body",
      "parameters": [
        {"type": "text", "text": "João Silva"},
        {"type": "text", "text": "R$ 250,00"},
        {"type": "text", "text": "15/01/2025"}
      ]
    }
  ]
}
```

---

### 2.3 Language
**Descrição**: Define o idioma do template.

**Estrutura**:
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public static class Language {
    @JsonProperty("code")
    @Builder.Default
    private String code = "pt_BR";
}
```

**Códigos de Idioma Suportados**:
- `pt_BR` - Português (Brasil)
- `en_US` - Inglês (Estados Unidos)
- `es_ES` - Espanhol (Espanha)
- `es_MX` - Espanhol (México)

**Regra de Negócio**:
O código de idioma deve corresponder ao idioma do template aprovado no WhatsApp Business Manager. Usar código incorreto resultará em erro 400.

---

### 2.4 Component
**Descrição**: Representa um componente do template (header, body, footer, button).

**Estrutura**:
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public static class Component {
    @JsonProperty("type")
    private String type; // header, body, button

    @JsonProperty("parameters")
    private List<Parameter> parameters;
}
```

**Tipos de Componentes**:

1. **HEADER** (opcional):
```json
{
  "type": "header",
  "parameters": [
    {"type": "text", "text": "Hospital XYZ"}
  ]
}
```

2. **BODY** (obrigatório):
```json
{
  "type": "body",
  "parameters": [
    {"type": "text", "text": "João Silva"},
    {"type": "text", "text": "R$ 250,00"}
  ]
}
```

3. **FOOTER** (opcional):
```json
{
  "type": "footer",
  "parameters": []
}
```

4. **BUTTON** (opcional):
```json
{
  "type": "button",
  "sub_type": "url",
  "index": 0,
  "parameters": [
    {"type": "text", "text": "ABC123"}
  ]
}
```

---

### 2.5 Parameter
**Descrição**: Parâmetro dinâmico a ser substituído no template.

**Estrutura**:
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public static class Parameter {
    @JsonProperty("type")
    private String type; // text, currency, date_time

    @JsonProperty("text")
    private String text;
}
```

**Tipos de Parâmetros**:

1. **TEXT**:
```java
Parameter.builder()
    .type("text")
    .text("João Silva")
    .build()
```

2. **CURRENCY**:
```java
Parameter.builder()
    .type("currency")
    .currency(Currency.builder()
        .fallbackValue("R$ 250,00")
        .code("BRL")
        .amount1000(250000) // 250.00 * 1000
        .build())
    .build()
```

3. **DATE_TIME**:
```java
Parameter.builder()
    .type("date_time")
    .dateTime(DateTime.builder()
        .fallbackValue("15/01/2025 14:30")
        .unixTimestamp(1736950200)
        .build())
    .build()
```

---

### 2.6 WhatsAppResponse
**Descrição**: Resposta da API após envio de mensagem.

**Estrutura**:
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public static class WhatsAppResponse {
    @JsonProperty("messaging_product")
    private String messagingProduct;

    @JsonProperty("contacts")
    private List<Contact> contacts;

    @JsonProperty("messages")
    private List<Message> messages;
}
```

**Resposta de Sucesso**:
```json
{
  "messaging_product": "whatsapp",
  "contacts": [
    {
      "input": "+5511987654321",
      "wa_id": "5511987654321"
    }
  ],
  "messages": [
    {
      "id": "wamid.HBgNNTUxMTk4NzY1NDMyMRUCABIYFjNFQjA2RjcyRjI2QzQ5RkZBMDlGREEA",
      "message_status": "accepted"
    }
  ]
}
```

**Campos**:
- `contacts`: Informações do destinatário
- `messages`: Array com ID da mensagem e status inicial

---

### 2.7 Contact
**Descrição**: Informações do contato destinatário.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Contact {
    @JsonProperty("input")
    private String input;

    @JsonProperty("wa_id")
    private String waId;
}
```

**Campos**:
- `input`: Número fornecido na requisição
- `wa_id`: ID do WhatsApp (número normalizado sem +)

---

### 2.8 Message
**Descrição**: Informações da mensagem enviada.

**Estrutura**:
```java
@Data
@NoArgsConstructor
@AllArgsConstructor
public static class Message {
    @JsonProperty("id")
    private String id;

    @JsonProperty("message_status")
    private String messageStatus;
}
```

**Campos**:
- `id`: WhatsApp Message ID (wamid)
- `messageStatus`: Status inicial ("accepted", "queued")

---

## 3. Regras de Negócio

### RN-WTD-001: Construção de Mensagem Template
**Descrição**: Mensagens template devem ser construídas com todos os campos obrigatórios e parâmetros corretos.

**Implementação**:
```java
public WhatsAppTemplateDTO buildPaymentReminder(
        String recipientNumber,
        String patientName,
        BigDecimal amount,
        LocalDate dueDate) {

    return WhatsAppTemplateDTO.builder()
        .messagingProduct("whatsapp")
        .recipientNumber(recipientNumber)
        .type("template")
        .template(Template.builder()
            .name("payment_reminder")
            .language(Language.builder()
                .code("pt_BR")
                .build())
            .components(List.of(
                Component.builder()
                    .type("body")
                    .parameters(List.of(
                        Parameter.builder()
                            .type("text")
                            .text(patientName)
                            .build(),
                        Parameter.builder()
                            .type("text")
                            .text(formatCurrency(amount))
                            .build(),
                        Parameter.builder()
                            .type("text")
                            .text(formatDate(dueDate))
                            .build()
                    ))
                    .build()
            ))
            .build())
        .build();
}
```

**Validações**:
```java
public void validate(WhatsAppTemplateDTO dto) {
    if (dto.getRecipientNumber() == null) {
        throw new ValidationException("Recipient number is required");
    }

    if (dto.getTemplate() == null) {
        throw new ValidationException("Template is required");
    }

    if (dto.getTemplate().getName() == null) {
        throw new ValidationException("Template name is required");
    }

    if (dto.getTemplate().getLanguage() == null) {
        throw new ValidationException("Template language is required");
    }

    validateComponents(dto.getTemplate().getComponents());
}

private void validateComponents(List<Component> components) {
    if (components == null || components.isEmpty()) {
        throw new ValidationException("At least one component is required");
    }

    boolean hasBody = components.stream()
        .anyMatch(c -> "body".equals(c.getType()));

    if (!hasBody) {
        throw new ValidationException("Body component is required");
    }
}
```

---

### RN-WTD-002: Templates Pré-Definidos
**Descrição**: O sistema deve ter builders para templates comuns usados no ciclo da receita.

**Payment Reminder**:
```java
public class WhatsAppTemplateBuilder {

    public static WhatsAppTemplateDTO paymentReminder(
            String phone,
            String patientName,
            BigDecimal amount,
            LocalDate dueDate) {

        return WhatsAppTemplateDTO.builder()
            .recipientNumber(phone)
            .template(Template.builder()
                .name("payment_reminder")
                .language(Language.builder().code("pt_BR").build())
                .components(List.of(
                    bodyComponent(
                        textParam(patientName),
                        textParam(formatCurrency(amount)),
                        textParam(formatDate(dueDate))
                    )
                ))
                .build())
            .build();
    }

    public static WhatsAppTemplateDTO appointmentConfirmation(
            String phone,
            String patientName,
            String doctorName,
            LocalDateTime appointmentTime,
            String location) {

        return WhatsAppTemplateDTO.builder()
            .recipientNumber(phone)
            .template(Template.builder()
                .name("appointment_confirmation")
                .language(Language.builder().code("pt_BR").build())
                .components(List.of(
                    bodyComponent(
                        textParam(patientName),
                        textParam(doctorName),
                        textParam(formatDateTime(appointmentTime)),
                        textParam(location)
                    )
                ))
                .build())
            .build();
    }

    public static WhatsAppTemplateDTO examResultAvailable(
            String phone,
            String patientName,
            String examType,
            String portalLink) {

        return WhatsAppTemplateDTO.builder()
            .recipientNumber(phone)
            .template(Template.builder()
                .name("exam_result_available")
                .language(Language.builder().code("pt_BR").build())
                .components(List.of(
                    bodyComponent(
                        textParam(patientName),
                        textParam(examType),
                        textParam(portalLink)
                    )
                ))
                .build())
            .build();
    }

    // Métodos auxiliares
    private static Component bodyComponent(Parameter... parameters) {
        return Component.builder()
            .type("body")
            .parameters(Arrays.asList(parameters))
            .build();
    }

    private static Parameter textParam(String text) {
        return Parameter.builder()
            .type("text")
            .text(text)
            .build();
    }
}
```

---

### RN-WTD-003: Formatação de Dados
**Descrição**: Dados dinâmicos devem ser formatados conforme padrões brasileiros.

**Implementação**:
```java
public class WhatsAppDataFormatter {

    private static final NumberFormat CURRENCY_FORMAT =
        NumberFormat.getCurrencyInstance(new Locale("pt", "BR"));

    private static final DateTimeFormatter DATE_FORMAT =
        DateTimeFormatter.ofPattern("dd/MM/yyyy");

    private static final DateTimeFormatter DATETIME_FORMAT =
        DateTimeFormatter.ofPattern("dd/MM/yyyy 'às' HH:mm");

    public static String formatCurrency(BigDecimal amount) {
        return CURRENCY_FORMAT.format(amount);
    }

    public static String formatDate(LocalDate date) {
        return date.format(DATE_FORMAT);
    }

    public static String formatDateTime(LocalDateTime dateTime) {
        return dateTime.format(DATETIME_FORMAT);
    }

    public static String formatPhone(String phone) {
        // +5511987654321 -> (11) 98765-4321
        if (phone.startsWith("+55")) {
            String digits = phone.substring(3);
            if (digits.length() == 11) { // Celular
                return String.format("(%s) %s-%s",
                    digits.substring(0, 2),
                    digits.substring(2, 7),
                    digits.substring(7)
                );
            } else if (digits.length() == 10) { // Fixo
                return String.format("(%s) %s-%s",
                    digits.substring(0, 2),
                    digits.substring(2, 6),
                    digits.substring(6)
                );
            }
        }
        return phone;
    }
}
```

---

### RN-WTD-004: Serialização JSON
**Descrição**: DTOs devem ser serializados corretamente para JSON usando Jackson.

**Configuração Jackson**:
```java
@Configuration
public class JacksonConfig {

    @Bean
    public ObjectMapper objectMapper() {
        ObjectMapper mapper = new ObjectMapper();

        // Usar snake_case para propriedades
        mapper.setPropertyNamingStrategy(
            PropertyNamingStrategies.SNAKE_CASE
        );

        // Ignorar propriedades nulas
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);

        // Não falhar em propriedades desconhecidas
        mapper.configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            false
        );

        return mapper;
    }
}
```

**Teste de Serialização**:
```java
@Test
void serialize_PaymentReminder_CorrectJSON() throws Exception {
    WhatsAppTemplateDTO dto = WhatsAppTemplateBuilder.paymentReminder(
        "+5511987654321",
        "João Silva",
        new BigDecimal("250.00"),
        LocalDate.of(2025, 1, 15)
    );

    ObjectMapper mapper = new ObjectMapper();
    String json = mapper.writeValueAsString(dto);

    assertThat(json).contains("\"messaging_product\":\"whatsapp\"");
    assertThat(json).contains("\"to\":\"+5511987654321\"");
    assertThat(json).contains("\"type\":\"template\"");
    assertThat(json).contains("\"name\":\"payment_reminder\"");
}
```

---

## 4. Exemplos de Uso

### 4.1 Envio de Lembrete de Pagamento
```java
@Service
public class PaymentNotificationService {

    @Autowired
    private WhatsAppClient whatsAppClient;

    @Value("${whatsapp.phone-number-id}")
    private String phoneNumberId;

    @Value("${whatsapp.access-token}")
    private String accessToken;

    public String sendPaymentReminder(Invoice invoice) {
        Patient patient = invoice.getPatient();

        WhatsAppTemplateDTO template = WhatsAppTemplateBuilder.paymentReminder(
            patient.getPhoneNumber(),
            patient.getName(),
            invoice.getAmount(),
            invoice.getDueDate()
        );

        Call<WhatsAppResponse> call = whatsAppClient.sendTemplateMessage(
            phoneNumberId,
            "Bearer " + accessToken,
            template
        );

        Response<WhatsAppResponse> response = call.execute();

        if (!response.isSuccessful()) {
            throw new WhatsAppException("Failed to send message: " +
                response.errorBody().string());
        }

        return response.body().getMessages().get(0).getId();
    }
}
```

### 4.2 Confirmação de Consulta
```java
public String sendAppointmentConfirmation(Appointment appointment) {
    Patient patient = appointment.getPatient();
    Doctor doctor = appointment.getDoctor();

    WhatsAppTemplateDTO template = WhatsAppTemplateBuilder.appointmentConfirmation(
        patient.getPhoneNumber(),
        patient.getName(),
        doctor.getName(),
        appointment.getDateTime(),
        appointment.getLocation()
    );

    Call<WhatsAppResponse> call = whatsAppClient.sendTemplateMessage(
        phoneNumberId,
        "Bearer " + accessToken,
        template
    );

    Response<WhatsAppResponse> response = call.execute();
    return response.body().getMessages().get(0).getId();
}
```

---

## 5. Testes

### 5.1 Testes Unitários
```java
class WhatsAppTemplateDTOTest {

    @Test
    void builder_AllFields_Success() {
        WhatsAppTemplateDTO dto = WhatsAppTemplateDTO.builder()
            .messagingProduct("whatsapp")
            .recipientNumber("+5511987654321")
            .type("template")
            .template(Template.builder()
                .name("test_template")
                .language(Language.builder().code("pt_BR").build())
                .components(Collections.emptyList())
                .build())
            .build();

        assertNotNull(dto);
        assertEquals("whatsapp", dto.getMessagingProduct());
        assertEquals("+5511987654321", dto.getRecipientNumber());
        assertEquals("test_template", dto.getTemplate().getName());
    }

    @Test
    void serialize_Template_CorrectJSON() throws Exception {
        WhatsAppTemplateDTO dto = buildTestTemplate();

        ObjectMapper mapper = new ObjectMapper();
        String json = mapper.writeValueAsString(dto);

        assertThat(json).contains("messaging_product");
        assertThat(json).contains("whatsapp");
    }

    @Test
    void deserialize_Response_Success() throws Exception {
        String json = """
            {
              "messaging_product": "whatsapp",
              "contacts": [{
                "input": "+5511987654321",
                "wa_id": "5511987654321"
              }],
              "messages": [{
                "id": "wamid.ABC123",
                "message_status": "accepted"
              }]
            }
            """;

        ObjectMapper mapper = new ObjectMapper();
        WhatsAppResponse response = mapper.readValue(
            json,
            WhatsAppResponse.class
        );

        assertNotNull(response);
        assertEquals("wamid.ABC123", response.getMessages().get(0).getId());
    }
}
```

---

## 6. Troubleshooting

### 6.1 Erro: Template Not Found
**Problema**: Template não encontrado no WhatsApp Business Manager.

**Solução**:
1. Verificar nome do template
2. Confirmar aprovação no Business Manager
3. Verificar código de idioma corresponde ao template

### 6.2 Erro: Parameter Count Mismatch
**Problema**: Número de parâmetros não corresponde ao template.

**Solução**:
```java
// Template esperado: "Olá {{1}}, sua consulta com Dr. {{2}} está confirmada."
// Deve ter exatamente 2 parâmetros

Component.builder()
    .type("body")
    .parameters(List.of(
        textParam("João"),      // {{1}}
        textParam("Dr. Silva")  // {{2}}
    ))
    .build()
```

---

## 7. Referências

- [WhatsApp Message Templates](https://developers.facebook.com/docs/whatsapp/message-templates)
- [Template Components](https://developers.facebook.com/docs/whatsapp/message-templates/components)
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations)
- Código relacionado: `WhatsAppClient.java`, `WhatsAppService.java`
