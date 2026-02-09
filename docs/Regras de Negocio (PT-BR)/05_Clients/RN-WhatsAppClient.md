# RN-WhatsAppClient - Cliente Retrofit para WhatsApp Business API

## 1. Visão Geral

### 1.1 Objetivo
Interface Retrofit que define os endpoints para integração com a WhatsApp Business API, permitindo o envio de mensagens template e controle de status de entrega.

### 1.2 Contexto no Ciclo da Receita
- **Módulo**: Integration Layer
- **Processo BPMN**: Patient Communication & Billing Notifications
- **Componente**: `com.hospital.revenuecycle.integration.whatsapp.WhatsAppClient`
- **Tipo**: Retrofit HTTP Client Interface

### 1.3 Casos de Uso
- Envio de lembretes de consulta
- Notificações de cobrança e pagamento
- Entrega de resultados de exames
- Confirmações de agendamento
- Comunicação oficial com pacientes

---

## 2. Regras de Negócio

### RN-WA-001: Envio de Mensagens Template
**Descrição**: O sistema deve enviar apenas mensagens template pré-aprovadas pela WhatsApp Business API.

**Regra**:
```java
@POST("{phoneNumberId}/messages")
Call<WhatsAppResponse> sendTemplateMessage(
    @Path("phoneNumberId") String phoneNumberId,
    @Header("Authorization") String accessToken,
    @Body WhatsAppTemplateDTO message
)
```

**Validações**:
- Phone Number ID deve ser válido
- Access Token deve estar no formato "Bearer {token}"
- Mensagem deve seguir estrutura WhatsAppTemplateDTO
- Template deve estar pré-aprovado pelo WhatsApp

**Exceções**:
- `401 Unauthorized`: Token inválido ou expirado
- `400 Bad Request`: Payload inválido
- `403 Forbidden`: Template não aprovado
- `429 Too Many Requests`: Limite de taxa excedido

---

### RN-WA-002: Marcar Mensagem como Lida
**Descrição**: O sistema deve permitir marcar mensagens como lidas após processamento.

**Regra**:
```java
@POST("{phoneNumberId}/messages")
Call<Void> markMessageAsRead(
    @Path("phoneNumberId") String phoneNumberId,
    @Header("Authorization") String accessToken,
    @Body MarkReadRequest messageId
)
```

**Payload**:
```json
{
  "messaging_product": "whatsapp",
  "status": "read",
  "message_id": "wamid.123456789"
}
```

**Validações**:
- Message ID deve ser válido
- Mensagem deve existir no sistema WhatsApp
- Status anterior deve permitir transição para "read"

---

### RN-WA-003: Tipos de Mensagens Suportadas
**Descrição**: Define os tipos de mensagens que podem ser enviadas via WhatsApp Business API.

**Tipos Permitidos**:
1. **Template Messages**:
   - Lembretes de pagamento
   - Confirmações de consulta
   - Notificações de cobrança
   - Alertas de vencimento

2. **Session Messages** (após interação do usuário):
   - Respostas a dúvidas
   - Suporte ao paciente
   - Confirmações interativas

**Restrições**:
- Mensagens promocionais requerem opt-in explícito
- Mensagens template devem ser aprovadas previamente
- Respeitar janela de 24h para session messages

---

### RN-WA-004: Autorização e Segurança
**Descrição**: Todas as requisições devem incluir autenticação adequada.

**Headers Obrigatórios**:
```java
@Headers("Content-Type: application/json")
@Header("Authorization") String accessToken
```

**Formato do Token**:
```
Authorization: Bearer EAAJxF5ZAZCfG8BAMBAA...
```

**Validações**:
- Token deve ser válido e não expirado
- Token deve ter permissões adequadas
- Phone Number ID deve pertencer à conta autorizada

**Renovação de Token**:
- Tokens temporários: validade de 1 hora
- Tokens permanentes: validade de 60 dias
- Sistema deve implementar refresh automático

---

### RN-WA-005: Estrutura de Resposta
**Descrição**: Todas as respostas da API devem seguir formato padronizado.

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

**Campos de Resposta**:
- `messaging_product`: Sempre "whatsapp"
- `contacts`: Array com informações do destinatário
- `messages`: Array com ID e status da mensagem

---

## 3. Conformidade Regulatória

### 3.1 LGPD (Lei Geral de Proteção de Dados)
**Aplicação**: Todas as comunicações via WhatsApp devem respeitar a LGPD.

**Requisitos**:
1. **Consentimento**:
   - Paciente deve autorizar recebimento de mensagens
   - Opt-in explícito para cada tipo de notificação
   - Registro de consentimento com timestamp

2. **Dados Sensíveis**:
   - Não enviar informações clínicas detalhadas via WhatsApp
   - Usar links seguros para acesso a resultados
   - Criptografia end-to-end nativa do WhatsApp

3. **Direitos do Titular**:
   - Permitir opt-out a qualquer momento
   - Deletar histórico de mensagens mediante solicitação
   - Fornecer transparência sobre uso de dados

**Implementação**:
```java
// Verificar consentimento antes de enviar
if (!patientService.hasWhatsAppConsent(patientId)) {
    throw new ConsentException("Patient has not consented to WhatsApp communications");
}
```

---

### 3.2 WhatsApp Business Policy
**Aplicação**: Cumprir políticas da plataforma WhatsApp Business.

**Políticas Obrigatórias**:
1. **Templates Aprovados**:
   - Todos os templates devem ser submetidos para aprovação
   - Conteúdo deve seguir guidelines do WhatsApp
   - Proibido envio de spam ou conteúdo enganoso

2. **Qualidade de Mensagens**:
   - Manter taxa de bloqueio < 2%
   - Evitar mensagens não solicitadas
   - Responder a dúvidas em até 24h

3. **Limites de Taxa**:
   - Respeitar limites de mensagens por segundo
   - Implementar backoff exponencial em caso de rate limit
   - Monitorar tier da conta (1000, 10k, 100k, unlimited)

---

## 4. Integração com Outros Componentes

### 4.1 WhatsAppService
```java
@Service
public class WhatsAppService {
    @Autowired
    private WhatsAppClient whatsAppClient;

    public String sendTemplateMessage(...) {
        Call<WhatsAppResponse> call = whatsAppClient.sendTemplateMessage(
            phoneNumberId,
            "Bearer " + accessToken,
            templateDTO
        );
        Response<WhatsAppResponse> response = call.execute();
        return response.body().getMessages().get(0).getId();
    }
}
```

### 4.2 WhatsAppWebhookHandler
```java
@RestController
@RequestMapping("/webhooks/whatsapp")
public class WhatsAppWebhookController {
    @PostMapping
    public void handleWebhook(@RequestBody WhatsAppWebhookDTO webhook) {
        // Processar callbacks de status de entrega
        webhookHandler.processWebhook(webhook);
    }
}
```

### 4.3 NotificationService
```java
@Service
public class NotificationService {
    public void sendPaymentReminder(Patient patient, Invoice invoice) {
        if (patient.hasWhatsAppConsent()) {
            whatsAppService.sendTemplateMessage(
                patient.getPhone(),
                "payment_reminder",
                buildPaymentMessage(invoice),
                Map.of("amount", invoice.getAmount())
            );
        }
    }
}
```

---

## 5. Fluxo de Mensagens

### 5.1 Fluxo de Envio
```
┌─────────────────┐
│ Sistema         │
│ (NotificationSvc)│
└────────┬────────┘
         │ 1. sendTemplateMessage()
         ▼
┌─────────────────┐
│ WhatsAppService │
└────────┬────────┘
         │ 2. Validações + Build DTO
         ▼
┌─────────────────┐
│ WhatsAppClient  │
└────────┬────────┘
         │ 3. HTTP POST
         ▼
┌─────────────────┐
│ WhatsApp API    │
│ (Graph API)     │
└────────┬────────┘
         │ 4. Response
         ▼
┌─────────────────┐
│ Sistema         │
│ (Message ID)    │
└─────────────────┘
```

### 5.2 Fluxo de Callback (Webhook)
```
┌─────────────────┐
│ WhatsApp API    │
└────────┬────────┘
         │ 1. Status Update
         ▼
┌─────────────────┐
│ Webhook Handler │
└────────┬────────┘
         │ 2. Parse Event
         ▼
┌─────────────────┐
│ Status Store    │
│ (ConcurrentMap) │
└────────┬────────┘
         │ 3. Trigger Actions
         ▼
┌─────────────────┐
│ Business Logic  │
│ (Retry/Alert)   │
└─────────────────┘
```

---

## 6. Tratamento de Erros

### 6.1 Códigos de Erro HTTP
| Código | Descrição | Ação |
|--------|-----------|------|
| 400 | Bad Request | Validar payload antes de enviar |
| 401 | Unauthorized | Renovar access token |
| 403 | Forbidden | Verificar permissões da conta |
| 404 | Not Found | Verificar Phone Number ID |
| 429 | Rate Limit | Implementar backoff exponencial |
| 500 | Server Error | Retry com jitter |

### 6.2 Estratégia de Retry
```java
RetryPolicy retryPolicy = RetryPolicy.builder()
    .maxRetries(3)
    .backoff(ExponentialBackoff.builder()
        .initialDelay(Duration.ofSeconds(1))
        .maxDelay(Duration.ofSeconds(30))
        .multiplier(2.0)
        .build())
    .retryOn(IOException.class, WhatsAppException.class)
    .build();
```

---

## 7. Monitoramento e Métricas

### 7.1 Métricas de API
- Taxa de sucesso de envio (target: > 98%)
- Latência de resposta (target: < 2s)
- Taxa de bloqueio (target: < 2%)
- Taxa de entrega (target: > 95%)

### 7.2 Logs Obrigatórios
```java
log.info("WhatsApp message sent: messageId={}, phone={}, template={}",
    messageId, phoneNumber, templateId);
log.error("WhatsApp API error: status={}, error={}",
    response.code(), response.errorBody());
```

### 7.3 Alertas
- Falha de autenticação (token expirado)
- Taxa de erro > 5%
- Rate limit atingido
- Webhook não recebendo callbacks

---

## 8. Configuração

### 8.1 Propriedades Necessárias
```yaml
whatsapp:
  api:
    base-url: https://graph.facebook.com/v18.0/
    phone-number-id: ${WHATSAPP_PHONE_NUMBER_ID}
    access-token: ${WHATSAPP_ACCESS_TOKEN}
  client:
    connect-timeout: 10s
    read-timeout: 30s
    write-timeout: 30s
```

### 8.2 Retrofit Configuration
```java
@Configuration
public class WhatsAppClientConfig {
    @Bean
    public WhatsAppClient whatsAppClient() {
        return new Retrofit.Builder()
            .baseUrl(whatsappBaseUrl)
            .client(okHttpClient())
            .addConverterFactory(JacksonConverterFactory.create())
            .build()
            .create(WhatsAppClient.class);
    }
}
```

---

## 9. Testes

### 9.1 Testes Unitários
```java
@Test
void sendTemplateMessage_Success() {
    WhatsAppTemplateDTO template = buildTemplate();
    Call<WhatsAppResponse> call = whatsAppClient.sendTemplateMessage(
        phoneNumberId, "Bearer token", template
    );

    assertNotNull(call);
    Response<WhatsAppResponse> response = call.execute();
    assertTrue(response.isSuccessful());
    assertNotNull(response.body().getMessages().get(0).getId());
}
```

### 9.2 Testes de Integração
```java
@Test
void integration_SendRealMessage() {
    // Usar WhatsApp Test Numbers
    String testPhoneNumber = "+15550000001";
    String messageId = whatsAppService.sendTemplateMessage(
        testPhoneNumber, "test_template", "Test message", Map.of()
    );

    assertNotNull(messageId);
    assertTrue(messageId.startsWith("wamid."));
}
```

---

## 10. Glossário

- **Template Message**: Mensagem pré-aprovada pelo WhatsApp para envio proativo
- **Session Message**: Mensagem enviada dentro da janela de 24h após interação do usuário
- **Phone Number ID**: Identificador único do número WhatsApp Business
- **Access Token**: Token de autenticação OAuth 2.0 para WhatsApp API
- **WAMID**: WhatsApp Message ID (identificador único de mensagem)
- **Opt-in**: Consentimento explícito do usuário para receber mensagens
- **Rate Limit**: Limite de requisições por segundo/minuto/dia

---

## 11. Referências

### 11.1 Documentação Externa
- [WhatsApp Business API Documentation](https://developers.facebook.com/docs/whatsapp)
- [WhatsApp Cloud API Reference](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [WhatsApp Business Policy](https://www.whatsapp.com/legal/business-policy)

### 11.2 Código Relacionado
- `WhatsAppService.java` - Serviço de alto nível
- `WhatsAppWebhookHandler.java` - Processamento de callbacks
- `WhatsAppTemplateDTO.java` - DTOs de mensagem
- `WhatsAppClientConfig.java` - Configuração Retrofit

### 11.3 Legislação
- LGPD Art. 7º - Base legal para tratamento de dados
- LGPD Art. 9º - Tratamento de dados sensíveis de saúde
- CFM Resolução 2.314/2022 - Comunicação digital médico-paciente
