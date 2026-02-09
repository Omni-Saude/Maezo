# RN-ProcessPatientPaymentDelegate - Processamento de Pagamentos de Pacientes

## Metadados
- **ID**: RN-ProcessPatientPaymentDelegate
- **Categoria**: Cobrança (SUB_09_Collections) / Pagamentos
- **Prioridade**: CRITICAL
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Última Atualização**: 2026-01-12
- **Status**: Ativo

## Referência de Implementação
- **Arquivo**: `/src/main/java/com/hospital/revenuecycle/delegates/collection/ProcessPatientPaymentDelegate.java`
- **Bean BPMN**: `processPatientPayment`

---

## Descrição Geral

O **ProcessPatientPaymentDelegate** gerencia o processamento completo de pagamentos de pacientes através de múltiplos métodos (cartão, PIX, dinheiro, transferência bancária). Este delegate integra com gateways de pagamento, sistemas bancários e registra todas as transações para reconciliação financeira.

**Contexto de Negócio:**
- Hospitais brasileiros precisam suportar múltiplos métodos de pagamento (PIX, cartões, dinheiro, transferência)
- Cada método tem fluxo específico de processamento e confirmação
- Rastreabilidade completa é essencial para auditoria financeira e compliance

---

## Regras de Negócio

### RN-PPP-001: Validação de Valor de Pagamento
**Descrição:** O valor do pagamento deve ser maior que zero.

**Condições:**
- `paymentAmount > 0`

**Exceção:** `IllegalArgumentException` - "Payment amount must be greater than zero"

**Implementação:**
```java
if (paymentAmount.compareTo(BigDecimal.ZERO) <= 0) {
    throw new IllegalArgumentException("Payment amount must be greater than zero");
}
```

---

### RN-PPP-002: Métodos de Pagamento Suportados
**Descrição:** Sistema suporta 5 métodos de pagamento com fluxos específicos.

| Método | Código | Processamento | Confirmação |
|--------|--------|---------------|-------------|
| Cartão de Crédito | `credit_card` | Payment Gateway API | Imediata |
| Cartão de Débito | `debit_card` | Payment Gateway API | Imediata |
| PIX | `pix` | Banco Central API | QR Code + Polling |
| Dinheiro | `cash` | Registro manual | Imediata |
| Transferência Bancária | `bank_transfer` | Validação bancária | Manual/API |

**Implementação:**
```java
switch (paymentMethod.toLowerCase()) {
    case "credit_card":
    case "debit_card":
        paymentReceived = processCardPayment(...);
        break;
    case "pix":
        paymentReceived = processPixPayment(...);
        break;
    case "cash":
        paymentReceived = processCashPayment(...);
        break;
    case "bank_transfer":
        paymentReceived = processBankTransfer(...);
        break;
    default:
        throw new IllegalArgumentException("Unsupported payment method: " + paymentMethod);
}
```

---

### RN-PPP-003: Processamento de Cartão (Crédito/Débito)
**Descrição:** Processar pagamento via gateway de pagamento externo com autenticação segura.

**Fluxo:**
1. Obter configurações do gateway (URL, API Key, Merchant ID)
2. Construir payload de pagamento com token do cartão
3. Enviar requisição POST para gateway
4. Validar resposta (status "authorized" ou "captured")
5. Registrar gateway transaction ID

**Payload Exemplo:**
```json
{
  "merchant_id": "MERCHANT_12345",
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": 50000,  // $500.00 em centavos
  "currency": "BRL",
  "payment_method": "credit_card",
  "customer": {
    "id": "PAT-67890",
    "type": "patient"
  },
  "card_token": "tok_550e8400-e29b-41d4-a716",
  "capture": true,
  "description": "Hospital payment - Patient PAT-67890"
}
```

**Variáveis de Ambiente:**
- `PAYMENT_GATEWAY_URL`: URL do gateway de pagamento
- `PAYMENT_GATEWAY_API_KEY`: API key para autenticação
- `PAYMENT_GATEWAY_MERCHANT_ID`: ID do merchant hospital

**Segurança:**
- **Nunca** armazenar número de cartão completo
- Utilizar apenas tokens tokenizados do frontend
- Transmitir apenas via HTTPS
- Seguir PCI-DSS compliance

---

### RN-PPP-004: Processamento PIX
**Descrição:** Gerar cobrança PIX via gateway do Banco Central e aguardar confirmação.

**Fluxo:**
1. Obter configurações PIX (URL, API Key, chave PIX)
2. Criar cobrança com expiração de 15 minutos
3. Gerar QR Code (string e imagem base64)
4. Polling para confirmação de pagamento
5. Atualizar status quando pago

**Payload de Criação:**
```json
{
  "key": "12345678000190",  // CNPJ do hospital
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": 500.00,
  "payer": {
    "id": "PAT-67890",
    "type": "patient"
  },
  "expiration": 900,  // 15 minutos
  "description": "Pagamento Hospital - Paciente PAT-67890"
}
```

**Response Exemplo:**
```json
{
  "charge_id": "pix_xyz123",
  "qr_code": "00020126580014br.gov.bcb.pix...",
  "qr_code_image": "data:image/png;base64,iVBORw0KGgo...",
  "expiration": "2026-01-12T15:30:00Z",
  "status": "pending"
}
```

**Confirmação:**
- Polling a cada 5 segundos por até 15 minutos
- Status muda para "paid" quando confirmado
- Webhook pode ser configurado para confirmação instantânea

**Variáveis de Ambiente:**
- `PIX_GATEWAY_URL`: URL do gateway PIX
- `PIX_API_KEY`: API key do gateway
- `PIX_KEY`: Chave PIX do hospital (CNPJ/email/phone/random)

---

### RN-PPP-005: Processamento Dinheiro (Cash)
**Descrição:** Registrar pagamento em dinheiro no sistema financeiro e gerar recibo físico.

**Fluxo:**
1. Gerar número de recibo único (formato: CASH-YYYYMMDD-HHmmss-{UUID})
2. Registrar recebimento no sistema financeiro
3. Atualizar saldo do caixa
4. Criar trilha de auditoria
5. Gerar PDF do recibo

**Estrutura de Recibo:**
```json
{
  "receipt_number": "CASH-20260112-143000-550e8400",
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient_id": "PAT-67890",
  "amount": 500.00,
  "payment_method": "cash",
  "received_at": "2026-01-12T14:30:00",
  "cashier_id": "USER-123",
  "register_id": "REG-01"
}
```

**Operações Bancárias:**
```sql
-- Registrar recebimento
INSERT INTO cash_receipts (receipt_number, transaction_id, patient_id, amount, cashier_id, register_id, received_at)
VALUES (?, ?, ?, ?, ?, ?, NOW());

-- Atualizar caixa
UPDATE cash_registers
SET current_balance = current_balance + ?,
    last_transaction = ?,
    updated_at = NOW()
WHERE register_id = ?;

-- Auditoria
INSERT INTO financial_audit_log (action, entity_type, entity_id, amount, user_id, timestamp)
VALUES ('cash_receipt', 'patient_payment', ?, ?, ?, NOW());
```

**Geração de Recibo:**
- Utilizar `PdfAppealLetterGenerator` ou serviço dedicado
- Armazenar em `DocumentStorageService`
- Disponibilizar URL para download

---

### RN-PPP-006: Processamento Transferência Bancária
**Descrição:** Validar transferência bancária contra depósitos esperados via API bancária.

**Fluxo:**
1. Obter configurações bancárias
2. Receber número de confirmação do paciente
3. Validar transferência via API bancária
4. Verificar valor (tolerância de 1% para taxas)
5. Confirmar referência contém ID do paciente

**Payload de Validação:**
```json
{
  "account_number": "12345-6",
  "confirmation_number": "TRF-12345",
  "expected_amount": 1000.00,
  "reference": "PAT-67890"
}
```

**Response Exemplo:**
```json
{
  "valid": true,
  "transfer_id": "TRF-12345",
  "amount": 1000.00,
  "payer_name": "João da Silva",
  "payer_account": "98765-4",
  "transfer_date": "2026-01-12T10:30:00Z",
  "status": "confirmed"
}
```

**Validações:**
1. **Valor**: `|received_amount - expected_amount| <= expected_amount * 0.01`
2. **Referência**: Contém `patient_id`
3. **Status**: "confirmed"
4. **Data**: Dentro de período aceitável

**Fallback:**
- Se API não disponível ou validação falha, marcar para verificação manual
- Adicionar à fila de reconciliação bancária

**Variáveis de Ambiente:**
- `BANK_API_URL`: URL da API bancária
- `BANK_API_KEY`: API key
- `BANK_ACCOUNT_NUMBER`: Conta do hospital

---

### RN-PPP-007: Cálculo de Novo Saldo
**Descrição:** Calcular saldo remanescente após aplicação do pagamento.

**Fórmula:**
```
new_balance = max(0, amount_due - payment_amount)
```

**Nota:** Saldo nunca pode ser negativo. Se pagamento exceder valor devido, saldo é zero.

**Implementação:**
```java
BigDecimal newBalance = amountDue.subtract(paymentAmount);
if (newBalance.compareTo(BigDecimal.ZERO) < 0) {
    newBalance = BigDecimal.ZERO;
}
```

---

### RN-PPP-008: Geração de URL de Recibo
**Descrição:** Gerar URL única para acesso ao recibo digital.

**Formato:** `https://hospital.example.com/receipts/{transaction_id}.pdf`

**Exemplo:** `https://hospital.example.com/receipts/550e8400-e29b-41d4-a716-446655440000.pdf`

**Implementação:**
```java
private String generateReceiptUrl(String transactionId) {
    return String.format("https://hospital.example.com/receipts/%s.pdf", transactionId);
}
```

---

### RN-PPP-009: Armazenamento de Detalhes de Pagamento
**Descrição:** Armazenar todos os detalhes do pagamento em objeto serializado JSON para auditoria.

**Campos:**
- `patientId`: ID do paciente
- `transactionId`: ID único da transação
- `paymentAmount`: Valor pago
- `paymentMethod`: Método utilizado
- `originalBalance`: Saldo antes do pagamento
- `newBalance`: Saldo após pagamento
- `status`: Status do pagamento
- `receiptUrl`: URL do recibo
- `processedAt`: Timestamp de processamento

**Implementação:**
```java
Map<String, Object> paymentDetails = new HashMap<>();
paymentDetails.put("patientId", patientId);
paymentDetails.put("transactionId", transactionId);
paymentDetails.put("paymentAmount", paymentAmount);
paymentDetails.put("paymentMethod", paymentMethod);
paymentDetails.put("originalBalance", amountDue);
paymentDetails.put("newBalance", newBalance);
paymentDetails.put("status", paymentStatus);
paymentDetails.put("receiptUrl", receiptUrl);
paymentDetails.put("processedAt", LocalDateTime.now().toString());

ObjectValue paymentDetailsValue = Variables.objectValue(paymentDetails)
    .serializationDataFormat(Variables.SerializationDataFormats.JSON)
    .create();
execution.setVariable("paymentDetails", paymentDetailsValue);
```

---

### RN-PPP-010: Contador de Pagamentos
**Descrição:** Incrementar contador de total de pagamentos do paciente para histórico.

**Implementação:**
```java
Integer paymentCount = getVariable(execution, "totalPayments", Integer.class, 0);
execution.setVariable("totalPayments", paymentCount + 1);
```

---

## Variáveis do Processo BPMN

### Variáveis de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `patientId` | String | Sim | Identificador do paciente |
| `paymentAmount` | BigDecimal | Sim | Valor sendo pago |
| `paymentMethod` | String | Sim | Método de pagamento (credit_card, debit_card, pix, cash, bank_transfer) |
| `amountDue` | BigDecimal | Não | Valor devido original (padrão: $0) |

### Variáveis de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `paymentReceived` | Boolean | Indica se pagamento foi processado com sucesso |
| `newBalance` | BigDecimal | Saldo remanescente após pagamento |
| `transactionId` | String | ID único da transação (UUID) |
| `paymentStatus` | String | Status do pagamento ("completed", "pending", "failed") |
| `receiptUrl` | String | URL para download do recibo |
| `paymentDetails` | ObjectValue | Objeto JSON com todos os detalhes do pagamento |
| `totalPayments` | Integer | Contador total de pagamentos do paciente |

---

## Cenários de Teste

### CT-PPP-001: Cartão de Crédito - Sucesso
**Dado:**
- Pagamento de $500 via cartão de crédito
- Gateway de pagamento configurado e disponível

**Quando:** Processar pagamento

**Então:**
- `paymentReceived` = true
- `paymentStatus` = "completed"
- `transactionId` gerado
- `receiptUrl` disponível
- Gateway retorna transaction_id

---

### CT-PPP-002: PIX - Geração de QR Code
**Dado:**
- Pagamento de $1000 via PIX
- Gateway PIX configurado

**Quando:** Processar pagamento

**Então:**
- QR Code gerado
- Cobrança com expiração de 15 minutos
- Polling iniciado para confirmação
- `paymentStatus` = "pending" (até confirmação)

---

### CT-PPP-003: Dinheiro - Registro e Recibo
**Dado:**
- Pagamento de $250 em dinheiro
- Caixa registradora REG-01

**Quando:** Processar pagamento

**Então:**
- Número de recibo gerado (formato correto)
- Saldo do caixa atualizado
- Auditoria registrada
- PDF do recibo gerado
- `paymentStatus` = "completed"

---

### CT-PPP-004: Transferência - Validação Bem-Sucedida
**Dado:**
- Transferência de $1500
- API bancária confirma transferência

**Quando:** Validar transferência

**Então:**
- Validação bem-sucedida
- Valor confere (dentro da tolerância)
- Referência contém patientId
- `paymentStatus` = "completed"

---

### CT-PPP-005: Erro - Valor Inválido
**Dado:**
- `paymentAmount` = $0

**Quando:** Processar pagamento

**Então:**
- `IllegalArgumentException` lançada
- Mensagem: "Payment amount must be greater than zero"

---

### CT-PPP-006: Erro - Método Não Suportado
**Dado:**
- `paymentMethod` = "cryptocurrency"

**Quando:** Processar pagamento

**Então:**
- `IllegalArgumentException` lançada
- Mensagem: "Unsupported payment method: cryptocurrency"

---

### CT-PPP-007: Gateway Indisponível - Fallback
**Dado:**
- Cartão de crédito
- Gateway de pagamento offline

**Quando:** Processar pagamento

**Então:**
- `paymentReceived` = false
- `paymentStatus` = "failed"
- Erro registrado em logs
- Pagamento pode ser retentado

---

### CT-PPP-008: Novo Saldo Calculado Corretamente
**Dado:**
- `amountDue` = $1000
- `paymentAmount` = $700

**Quando:** Processar pagamento

**Então:**
- `newBalance` = $300
- `paymentDetails` contém originalBalance e newBalance

---

## Métricas e KPIs

### Transacionais
- **Volume de Pagamentos por Método**: Contagem diária por método
- **Valor Total Processado**: Soma por dia/semana/mês
- **Taxa de Sucesso por Método**: % de pagamentos bem-sucedidos

### Performance
- **Tempo Médio de Processamento**: Por método de pagamento
- **Latência P95**: Percentil 95 de latência
- **Taxa de Falha**: % de falhas por método

### Financeiros
- **Valor Médio de Pagamento**: Por método
- **Distribuição de Valores**: Histograma
- **Recovery Rate**: % de valor devido recuperado

---

## Considerações de Segurança

### PCI-DSS Compliance (Cartões)
- **Nunca** armazenar dados de cartão completos
- Usar apenas tokens do frontend
- Transmitir apenas via HTTPS/TLS 1.2+
- Logs não devem conter dados sensíveis

### Proteção de Dados Financeiros
- Criptografar dados de pagamento em repouso
- Mascarar números de conta em logs
- Aplicar LGPD para dados de pacientes

### Auditoria e Compliance
- Registrar todas as transações financeiras
- Manter trilha completa para auditoria
- Relatórios de reconciliação diários

### Prevenção de Fraude
- Validar consistência de valores
- Detectar padrões anômalos de pagamento
- Implementar rate limiting por paciente

---

## Referências
- PCI-DSS (Payment Card Industry Data Security Standard)
- Banco Central do Brasil - Regulamentação PIX
- LGPD (Lei Geral de Proteção de Dados)
- Payment Gateway Integration Best Practices
- BPMN Process: SUB_09_Collections

---

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Versão inicial com 5 métodos de pagamento |
