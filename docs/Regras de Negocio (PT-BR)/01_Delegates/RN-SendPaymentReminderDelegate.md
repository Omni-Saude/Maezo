# RN-SendPaymentReminderDelegate - Envio de Lembretes de Pagamento

## Metadados
- **ID**: RN-SendPaymentReminderDelegate
- **Categoria**: Cobrança (SUB_09_Collections)
- **Prioridade**: MEDIUM
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Última Atualização**: 2026-01-12
- **Status**: Ativo

## Referência de Implementação
- **Arquivo**: `/src/main/java/com/hospital/revenuecycle/delegates/collection/SendPaymentReminderDelegate.java`
- **Bean BPMN**: `sendPaymentReminder`

---

## Descrição Geral

O **SendPaymentReminderDelegate** gerencia o envio de lembretes de pagamento para pacientes através de múltiplos canais de comunicação (WhatsApp, SMS, Email, Telefone). Este delegate implementa lógica de retry e agendamento de próximos lembretes baseado em sucesso/falha.

**Contexto de Negócio:**
- Lembretes regulares aumentam significativamente taxa de recuperação de recebíveis
- Diferentes canais têm diferentes taxas de resposta e custos
- Frequência de lembretes deve equilibrar efetividade e experiência do paciente

---

## Regras de Negócio

### RN-SPR-001: Canais de Comunicação Suportados
**Descrição:** Sistema suporta 4 canais de comunicação com características distintas.

| Canal | Código | Velocidade | Custo | Taxa de Abertura | Melhor Para |
|-------|--------|-----------|-------|------------------|-------------|
| WhatsApp | `whatsapp` | Instantâneo | Baixo | ~90% | Valores baixos a médios |
| SMS | `sms` | Instantâneo | Médio | ~95% | Valores médios |
| Email | `email` | Minutos | Muito Baixo | ~20-30% | Documentação formal |
| Telefone | `phone` | Agendado | Alto | ~100% | Valores altos, situações complexas |

**Implementação:**
```java
switch (contactMethod.toLowerCase()) {
    case "whatsapp":
        reminderSent = sendWhatsAppReminder(patientId, amountDue);
        break;
    case "sms":
        reminderSent = sendSMSReminder(patientId, amountDue);
        break;
    case "email":
        reminderSent = sendEmailReminder(patientId, amountDue);
        break;
    case "phone":
        reminderSent = schedulePhoneCall(patientId, amountDue);
        break;
    default:
        // Fallback to SMS
        reminderSent = sendSMSReminder(patientId, amountDue);
        actualChannel = "sms";
}
```

---

### RN-SPR-002: Rastreamento de Tentativas
**Descrição:** Rastrear número de tentativas de lembrete para cada paciente.

**Incremento:**
```java
Integer reminderAttempts = getVariable(execution, "reminderAttempts", Integer.class, 0);
reminderAttempts++;
execution.setVariable("reminderAttempts", reminderAttempts);
```

**Uso:**
- Determinar se deve escalar para canal mais assertivo
- Limitar número máximo de tentativas (prevenção de spam)
- Análise de efetividade de canais

---

### RN-SPR-003: Agendamento de Próximo Lembrete
**Descrição:** Calcular data do próximo lembrete baseado em sucesso/falha do envio atual.

**Regras:**
- **Sucesso**: Próximo lembrete em 7 dias
- **Falha**: Retry em 3 dias

**Implementação:**
```java
LocalDateTime nextReminder = LocalDateTime.now()
    .plusDays(reminderSent ? 7 : 3);
String nextReminderDate = nextReminder.format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
execution.setVariable("nextReminderDate", nextReminderDate);
```

**Justificativa:**
- 7 dias permite tempo para paciente processar e efetuar pagamento
- 3 dias em caso de falha permite retry rápido sem ser excessivo

---

### RN-SPR-004: WhatsApp - Business API Integration
**Descrição:** Enviar lembrete via WhatsApp Business API utilizando templates aprovados.

**Fluxo:**
1. Obter configurações do WhatsApp Business API
2. Utilizar template pré-aprovado "payment_reminder"
3. Parametrizar com valor devido em formato currency
4. Enviar via API POST

**Configuração:**
```bash
WHATSAPP_API_URL=https://graph.facebook.com/v18.0/{phone-number-id}/messages
WHATSAPP_API_KEY=your_access_token
WHATSAPP_BUSINESS_PHONE=+5511999999999
```

**Template Exemplo:**
```
Olá! Lembramos que você possui um valor pendente de R$ {{1}}.
Por favor, regularize seu pagamento. Para dúvidas, entre em contato conosco.
```

**Payload:**
```json
{
  "to": "5511987654321",
  "type": "template",
  "template": {
    "name": "payment_reminder",
    "language": { "code": "pt_BR" },
    "components": [{
      "type": "body",
      "parameters": [{
        "type": "currency",
        "currency": {
          "fallback_value": "1000.00",
          "code": "BRL",
          "amount_1000": 1000000
        }
      }]
    }]
  }
}
```

**Vantagens:**
- Alta taxa de abertura (~90%)
- Custo baixo
- Permite mídia rica (futuramente)

---

### RN-SPR-005: SMS - Twilio Integration
**Descrição:** Enviar lembrete via SMS utilizando Twilio API.

**Fluxo:**
1. Obter credenciais Twilio (Account SID, Auth Token, Phone)
2. Formatar mensagem (máximo 160 caracteres)
3. Enviar via API POST com autenticação Basic

**Configuração:**
```bash
TWILIO_ACCOUNT_SID=AC1234567890abcdef
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE=+5511999999999
```

**Mensagem Exemplo:**
```
Pendência de R$ 1,000.00. Regularize seu pagamento. Hospital XYZ
```

**Endpoint:**
```
POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json
Authorization: Basic {Base64(AccountSid:AuthToken)}
Body (form-urlencoded):
  From={twilioPhoneNumber}
  To={patientId}
  Body={message}
```

**Limitações:**
- 160 caracteres para SMS padrão
- Sem formatação rica
- Custo médio por mensagem

---

### RN-SPR-006: Email - SMTP Integration
**Descrição:** Enviar lembrete via email utilizando servidor SMTP.

**Fluxo:**
1. Obter configurações SMTP (host, port, credentials)
2. Buscar email do paciente no banco de dados
3. Gerar link de pagamento
4. Enviar email formatado com informações completas

**Configuração:**
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=financeiro@hospital.com.br
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=financeiro@hospital.com.br
```

**Template de Email:**
```
Assunto: Lembrete de Pagamento - Hospital XYZ

Prezado(a) {patientName},

Identificamos um valor pendente de R$ {amountDue} em sua conta.

Data de vencimento: {dueDate}

Para facilitar, você pode realizar o pagamento através do link abaixo:
{paymentLink}

Caso já tenha efetuado o pagamento, por favor desconsidere esta mensagem.

Atenciosamente,
Equipe Hospital XYZ

Para dúvidas, entre em contato: financeiro@hospital.com.br
```

**Link de Pagamento:**
```java
String paymentLink = String.format(
    "https://hospital.example.com/payments/pay?patient=%s&amount=%.2f",
    patientId, amountDue
);
```

**Vantagens:**
- Custo muito baixo
- Permite conteúdo detalhado e formatado
- Registro permanente para o paciente

**Desvantagens:**
- Taxa de abertura baixa (~20-30%)
- Pode cair em spam

---

### RN-SPR-007: Telefone - Call Center Integration
**Descrição:** Agendar ligação telefônica via sistema de Call Center.

**Fluxo:**
1. Obter configurações da API do Call Center
2. Criar tarefa de ligação com prioridade baseada em valor
3. Incluir script para o operador
4. Agendar para próximas 2 horas

**Configuração:**
```bash
CALL_CENTER_API_URL=https://api.callcenter.com
CALL_CENTER_API_KEY=your_api_key
```

**Prioridade:**
- **Alta**: Valor devido > $1000
- **Média**: Valor devido ≤ $1000

**Payload:**
```json
{
  "patient_id": "PAT-67890",
  "task_type": "collection_reminder",
  "priority": "high",
  "amount_due": 2500.00,
  "script_type": "payment_reminder",
  "scheduled_at": "2026-01-12T16:30:00",
  "max_attempts": 3,
  "notes": "Patient has outstanding balance of R$ 2,500.00. Request payment and offer payment plan if needed."
}
```

**Script Sugerido:**
```
Bom dia/tarde, {patientName}. Aqui é {operatorName} do Hospital XYZ.

Identificamos um valor pendente de R$ {amountDue} em sua conta.

Gostaria de verificar se houve algum problema ou se podemos auxiliar de alguma forma?

[Oferecer opções de pagamento e plano de parcelamento se necessário]
```

**Vantagens:**
- Taxa de contato mais alta
- Permite negociação imediata
- Adequado para situações complexas

**Desvantagens:**
- Custo operacional alto
- Requer agendamento e disponibilidade

---

### RN-SPR-008: Armazenamento de Log de Lembretes
**Descrição:** Armazenar histórico completo de cada tentativa de lembrete.

**Campos do Log:**
- `patientId`: ID do paciente
- `amountDue`: Valor devido
- `contactMethod`: Canal utilizado
- `success`: Boolean indicando sucesso
- `attemptNumber`: Número da tentativa
- `sentAt`: Timestamp de envio
- `nextReminderDate`: Data do próximo lembrete

**Implementação:**
```java
Map<String, Object> reminderLog = new HashMap<>();
reminderLog.put("patientId", patientId);
reminderLog.put("amountDue", amountDue);
reminderLog.put("contactMethod", actualChannel);
reminderLog.put("success", reminderSent);
reminderLog.put("attemptNumber", reminderAttempts);
reminderLog.put("sentAt", LocalDateTime.now().toString());
reminderLog.put("nextReminderDate", nextReminderDate);

ObjectValue reminderLogValue = Variables.objectValue(reminderLog)
    .serializationDataFormat(Variables.SerializationDataFormats.JSON)
    .create();
execution.setVariable("lastReminderLog", reminderLogValue);
```

---

### RN-SPR-009: Tratamento de Falhas
**Descrição:** Implementar tratamento robusto de falhas com fallback e logging.

**Comportamento:**
```java
try {
    switch (contactMethod.toLowerCase()) {
        case "whatsapp":
            reminderSent = sendWhatsAppReminder(patientId, amountDue);
            break;
        // ... outros casos
    }
} catch (Exception e) {
    logger.error("Failed to send reminder via {}, will retry", contactMethod, e);
    reminderSent = false;
}
```

**Consequências de Falha:**
- `reminderSent` = false
- Próximo lembrete agendado para 3 dias (em vez de 7)
- Erro registrado em logs
- Processo continua (não lança exceção)

---

## Variáveis do Processo BPMN

### Variáveis de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `patientId` | String | Sim | Identificador do paciente |
| `amountDue` | BigDecimal | Sim | Valor devido |
| `contactMethod` | String | Não | Método de contato (padrão: "whatsapp") |

### Variáveis de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `reminderSent` | Boolean | Indica se lembrete foi enviado com sucesso |
| `reminderChannel` | String | Canal efetivamente utilizado |
| `nextReminderDate` | String | Data/hora do próximo lembrete (formato ISO) |
| `reminderAttempts` | Integer | Total de tentativas de lembrete |
| `lastReminderLog` | ObjectValue | Log completo da tentativa atual |

---

## Cenários de Teste

### CT-SPR-001: WhatsApp - Envio Bem-Sucedido
**Dado:**
- `patientId` = "PAT-12345"
- `amountDue` = $500
- `contactMethod` = "whatsapp"
- WhatsApp API configurado

**Quando:** Enviar lembrete

**Então:**
- `reminderSent` = true
- `reminderChannel` = "whatsapp"
- `nextReminderDate` = +7 dias
- `reminderAttempts` incrementado

---

### CT-SPR-002: SMS - Primeira Tentativa
**Dado:**
- `contactMethod` = "sms"
- `reminderAttempts` = 0

**Quando:** Enviar lembrete

**Então:**
- SMS enviado via Twilio
- `reminderAttempts` = 1
- `lastReminderLog` contém tentativa

---

### CT-SPR-003: Email - Com Link de Pagamento
**Dado:**
- `contactMethod` = "email"
- `amountDue` = $750

**Quando:** Enviar lembrete

**Então:**
- Email contém link: `https://hospital.example.com/payments/pay?patient=PAT-12345&amount=750.00`
- Data de vencimento incluída (7 dias no futuro)
- Assinatura do hospital

---

### CT-SPR-004: Telefone - Alta Prioridade
**Dado:**
- `contactMethod` = "phone"
- `amountDue` = $2500 (> $1000)

**Quando:** Agendar ligação

**Então:**
- Tarefa criada no Call Center
- Prioridade = "high"
- Script inclui oferta de plano de pagamento

---

### CT-SPR-005: Fallback - Método Desconhecido
**Dado:**
- `contactMethod` = "telegram"

**Quando:** Enviar lembrete

**Então:**
- Warning log gerado
- Fallback para SMS
- `reminderChannel` = "sms"

---

### CT-SPR-006: Falha - API Indisponível
**Dado:**
- WhatsApp API offline

**Quando:** Enviar lembrete

**Então:**
- `reminderSent` = false
- Erro registrado em logs
- `nextReminderDate` = +3 dias (retry mais cedo)

---

### CT-SPR-007: Múltiplas Tentativas
**Dado:**
- `reminderAttempts` = 4 (tentativas anteriores)

**Quando:** Enviar novo lembrete

**Então:**
- `reminderAttempts` = 5
- Histórico mantido em `lastReminderLog`
- Considerar escalação para canal mais assertivo

---

## Métricas e KPIs

### Efetividade de Canais
- **Taxa de Entrega**: % de lembretes entregues com sucesso
- **Taxa de Resposta**: % de pacientes que pagam após lembrete
- **Tempo Médio até Pagamento**: Por canal

### Operacionais
- **Volume de Lembretes por Canal**: Contagem diária
- **Taxa de Falha por Canal**: % de falhas de envio
- **Tentativas Médias até Pagamento**: Média de lembretes necessários

### Custos
- **Custo por Canal**: Custo médio por lembrete enviado
- **Custo por Recuperação**: Custo total / valor recuperado
- **ROI de Lembretes**: Valor recuperado vs custo operacional

---

## Considerações de Segurança

### Proteção de Dados (LGPD)
- Minimizar dados pessoais em mensagens
- Não incluir informações médicas sensíveis
- Obter consentimento para comunicações

### Prevenção de Spam
- Limitar frequência de lembretes (máximo 1 por 3 dias)
- Respeitar opt-out de pacientes
- Horário comercial para ligações telefônicas

### Compliance Regulatório
- Seguir Código de Defesa do Consumidor
- Respeitar horários adequados (não enviar à noite)
- Fornecer opção de cancelamento de lembretes

---

## Observações de Implementação

### Tratamento de Configuração Faltante
```java
String whatsappApiUrl = System.getenv("WHATSAPP_API_URL");
String whatsappApiKey = System.getenv("WHATSAPP_API_KEY");

if (whatsappApiUrl == null || whatsappApiKey == null) {
    logger.warn("WhatsApp API not configured, skipping WhatsApp reminder");
    return false;
}
```

### Formato de Mensagens
- **SMS**: Máximo 160 caracteres (padrão GSM)
- **WhatsApp**: Templates pré-aprovados (Facebook Business Manager)
- **Email**: HTML formatado com branding do hospital

### Logging Estruturado
```java
logger.info("Sending payment reminder to patient: {} via {}, Amount: {}, Attempt: {}",
            patientId, contactMethod, amountDue, reminderAttempts);

logger.info("Reminder {} for patient: {}, Next reminder: {}",
            reminderSent ? "sent successfully" : "failed",
            patientId, nextReminderDate);
```

---

## Referências
- WhatsApp Business API Documentation
- Twilio API Documentation
- LGPD (Lei Geral de Proteção de Dados)
- Código de Defesa do Consumidor
- BPMN Process: SUB_09_Collections

---

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Versão inicial com 4 canais de comunicação |
