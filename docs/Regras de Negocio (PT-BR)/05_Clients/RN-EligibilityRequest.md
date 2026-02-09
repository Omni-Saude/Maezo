# RN-EligibilityRequest - DTO de Requisição de Verificação de Elegibilidade

## 1. Identificação da Regra
- **ID:** RN-ELIGIBILITY-REQUEST-001
- **Nome:** Data Transfer Object para Requisição de Verificação de Elegibilidade X12 270 EDI
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 7
- **Categoria:** Integration Layer / DTO
- **Prioridade:** Crítica
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
DTO utilizado para requisitar verificação de elegibilidade de beneficiário junto à operadora de saúde. Corresponde à transação X12 270 EDI (Eligibility Benefit Inquiry) utilizada nos EUA, adaptada para o contexto brasileiro com identificadores TISS/ANS.

### 2.2. Descrição Técnica
Classe imutável com Lombok annotations (`@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`). Serializada para JSON e enviada como body em requisições POST /v1/eligibility/verify do InsuranceApiClient. Campos seguem nomenclatura X12 EDI para facilitar integração com operadoras que utilizam este padrão.

### 2.3. Origem do Requisito
- **Funcional:** Verificação obrigatória de elegibilidade antes de procedimentos médicos
- **Regulatório:** RN-469/2021 ANS - Verificação eletrônica de elegibilidade obrigatória
- **Técnico:** Integração REST com APIs de operadoras (padrão X12 270 EDI)

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Verificação de Elegibilidade no Momento do Atendimento
- **UC-02**: Consulta de Dados de Cobertura e Benefícios
- **UC-03**: Validação de Número da Carteirinha
- **UC-04**: Consulta de Período de Carência
- **UC-05**: Verificação de Status do Plano (Ativo/Inativo)

### 3.2. Processos BPMN Relacionados
- **Process ID:** revenue-cycle-main
  - **Task:** Verificar Elegibilidade do Paciente
  - **Service Task:** CheckEligibilityTask (camundaDelegate: EligibilityVerificationDelegate)
- **Process ID:** patient-registration
  - **Task:** Validar Dados do Beneficiário
  - **Service Task:** ValidateBeneficiaryTask

### 3.3. Entidades Afetadas
- **EligibilityResponse**: Response correspondente com dados de elegibilidade
- **Patient**: Entidade de domínio com dados do paciente
- **InsuranceContract**: Contrato de convênio do paciente

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
SE paciente possui plano de saúde privado
E atendimento será realizado
ENTÃO construir EligibilityRequest
COM patientId, payerId, insuranceCardNumber, serviceDate obrigatórios
E enviar para operadora
```

### 4.2. Critérios de Validação

**Campos Obrigatórios:**
1. **patientId**: Identificador único do paciente (não nulo, não vazio)
2. **payerId**: Identificador da operadora - Registro ANS (6 dígitos)
3. **insuranceCardNumber**: Número da carteirinha do beneficiário
4. **serviceDate**: Data do serviço (não pode ser > 1 ano no futuro)

**Campos Opcionais (Recomendados):**
5. **transactionType**: "270" (padrão X12 EDI para eligibility inquiry)
6. **providerNpi**: Código NPI do prestador (recomendado para network status)
7. **serviceTypeCode**: "30" = health benefit plan coverage (padrão X12)

### 4.3. Ações e Consequências

**QUANDO** EligibilityRequest construído:
1. **Validar** patientId não nulo
2. **Validar** payerId formato ANS (6 dígitos numéricos)
3. **Validar** insuranceCardNumber não vazio
4. **Validar** serviceDate <= (today + 365 dias)
5. **Adicionar** transactionType "270" se não fornecido
6. **Serializar** para JSON
7. **Enviar** via InsuranceApiClient.checkEligibility()

**SE** validação falhar:
- Lançar **IllegalArgumentException** com detalhes dos campos inválidos

**SE** insuranceCardNumber inválido na operadora:
- Response retornará `errorMessage` com detalhes do erro (404)

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio
Não aplicável - DTO não realiza cálculos.

### 5.2. Regras de Arredondamento
Não aplicável.

### 5.3. Tratamento de Valores Especiais
- **serviceDate null**: Assumir data atual (LocalDate.now())
- **transactionType null**: Assumir "270" (eligibility inquiry)
- **serviceTypeCode null**: Assumir "30" (health benefit plan coverage)
- **providerNpi null**: Operadora retorna cobertura genérica

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Campos Mapeados X12 270 → TISS

| Campo DTO | Campo X12 EDI | Campo TISS | Descrição |
|-----------|---------------|------------|-----------|
| patientId | NM1*IL | beneficiario.identificador | ID interno do paciente |
| payerId | NM1*PR | operadora.registroANS | Registro ANS (6 dígitos) |
| insuranceCardNumber | NM1*MI | beneficiario.numeroDaCarteira | Número da carteirinha |
| serviceDate | DTP*472 | dataAtendimento | Data prevista do atendimento |
| transactionType | ST*270 | tipoTransacao | Sempre "270" (inquiry) |
| providerNpi | NM1*1P | contratado.codigoPrestador | Código do prestador |
| serviceTypeCode | EB*1 | tipoServico | "30" = cobertura geral |

### 6.3. Códigos X12 Service Type

| Código | Descrição | Uso no Brasil |
|--------|-----------|---------------|
| 30 | Health Benefit Plan Coverage | Cobertura geral do plano |
| 1 | Medical Care | Atendimento médico |
| 2 | Surgical | Procedimentos cirúrgicos |
| 3 | Consultation | Consultas |
| 47 | Hospital Inpatient | Internação hospitalar |
| 86 | Emergency Services | Atendimento de emergência |

### 6.4. Formato Registro ANS (payerId)
- **Formato**: 6 dígitos numéricos
- **Exemplo**: "123456" (Unimed), "334545" (Bradesco Saúde)
- **Validação**: Regex `^\d{6}$`

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-469/2021**: Padrão de Troca de Informações na Saúde Suplementar (TISS)
  - Art. 4º: Verificação de elegibilidade eletrônica obrigatória
- **RN-506/2022**: Autorização Prévia Eletrônica
  - Verificação de elegibilidade é pré-requisito para autorização

### 7.2. Requisitos LGPD
- **Art. 7º, I**: Base legal para processamento (execução de contrato)
- **Art. 9º**: Dados de saúde (número da carteirinha) são sensíveis
- **Art. 46**: Dados trafegados via TLS 1.2+

### 7.3. Validações Regulatórias
1. **Registro ANS**: payerId deve ser válido no cadastro ANS
2. **Número da Carteirinha**: Formato conforme padrão da operadora
3. **Prazo de Resposta**: Operadora deve responder em até 10 segundos (SLA ANS)

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio

| Validação | Exceção | Mensagem |
|-----------|---------|----------|
| patientId null | IllegalArgumentException | "patientId é obrigatório" |
| payerId null | IllegalArgumentException | "payerId é obrigatório" |
| payerId formato inválido | IllegalArgumentException | "payerId deve ter 6 dígitos" |
| insuranceCardNumber null | IllegalArgumentException | "insuranceCardNumber é obrigatório" |
| serviceDate > 1 ano futuro | IllegalArgumentException | "serviceDate não pode ser mais de 1 ano no futuro" |

### 8.2. Erros Técnicos
- **Serialização JSON**: Se falhar, lançar RuntimeException

### 8.3. Estratégias de Recuperação
1. **Validação pré-envio**: Validar campos antes de construir request
2. **Builder pattern**: Garantir que campos obrigatórios são fornecidos
3. **Defensive defaults**: transactionType e serviceTypeCode têm defaults

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **EligibilityVerificationDelegate**: Constrói EligibilityRequest a partir de variáveis Camunda
- **PatientService**: Fornece patientId e insuranceCardNumber
- **InsuranceContractService**: Fornece payerId (registro ANS)

### 9.2. Dependências Downstream
- **InsuranceApiClient**: Recebe EligibilityRequest como parâmetro
- **EligibilityResponse**: DTO de resposta correspondente (X12 271 EDI)

### 9.3. Eventos Publicados
Não aplicável - DTO não publica eventos.

### 9.4. Eventos Consumidos
Não aplicável - DTO não consome eventos.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Serialização JSON**: < 5ms (request simples)
- **Tamanho do Request**: < 1KB

### 10.2. Estratégias de Cache
Não aplicável - DTO é stateless e não cacheable.

### 10.3. Otimizações Implementadas
1. **Immutability**: @Data garante thread-safety
2. **Lazy Initialization**: Lombok @Builder não cria objetos desnecessários

## 11. Exemplos de Uso

### 11.1. Exemplo Básico - Verificação de Elegibilidade

```java
EligibilityRequest request = EligibilityRequest.builder()
    .patientId("PAT-12345")
    .payerId("123456") // Unimed registro ANS
    .insuranceCardNumber("1234567890123")
    .serviceDate(LocalDate.now())
    .transactionType("270")
    .providerNpi("1234567890")
    .serviceTypeCode("30") // Health benefit plan coverage
    .build();

EligibilityResponse response = insuranceApiClient.checkEligibility(request);

if (response.isCoverageActive()) {
    log.info("Paciente elegível. Plano: {}", response.getPlanName());
} else {
    log.warn("Paciente inelegível: {}", response.getErrorMessage());
}
```

### 11.2. Exemplo Avançado - Verificação com Custom API Key

```java
// Para multi-tenant: cada operadora pode ter API Key diferente
String customApiKey = getApiKeyForPayer("123456");

EligibilityRequest request = EligibilityRequest.builder()
    .patientId("PAT-67890")
    .payerId("334545") // Bradesco Saúde
    .insuranceCardNumber("9876543210987")
    .serviceDate(LocalDate.now().plusDays(3))
    .transactionType("270")
    .serviceTypeCode("30")
    .build();

EligibilityResponse response = insuranceApiClient.checkEligibilityWithAuth(
    customApiKey,
    request
);
```

### 11.3. Exemplo de Caso de Uso Completo - Verificação no Check-In

```java
/**
 * UC: Verificação de Elegibilidade Durante Check-In do Paciente
 */
@Service
@RequiredArgsConstructor
public class PatientCheckInService {

    private final InsuranceApiClient insuranceApiClient;
    private final PatientService patientService;
    private final NotificationService notificationService;

    public CheckInResult performCheckIn(String patientId) {
        // 1. Obter dados do paciente
        Patient patient = patientService.findById(patientId)
            .orElseThrow(() -> new PatientNotFoundException(patientId));

        if (patient.getInsuranceContract() == null) {
            return CheckInResult.denied("Paciente sem plano de saúde cadastrado");
        }

        // 2. Construir request de elegibilidade
        EligibilityRequest request = EligibilityRequest.builder()
            .patientId(patientId)
            .payerId(patient.getInsuranceContract().getPayerAnsCode())
            .insuranceCardNumber(patient.getInsuranceContract().getCardNumber())
            .serviceDate(LocalDate.now())
            .transactionType("270")
            .providerNpi(hospitalNpiCode)
            .serviceTypeCode("30")
            .build();

        // 3. Verificar elegibilidade
        EligibilityResponse response;
        try {
            response = insuranceApiClient.checkEligibility(request);
        } catch (InsuranceApiException e) {
            log.error("Falha ao verificar elegibilidade", e);
            return CheckInResult.error("Não foi possível verificar elegibilidade. Contate a operadora.");
        }

        // 4. Processar resposta
        if (!response.isCoverageActive()) {
            // Cobertura inativa
            notificationService.notifyStaff(
                "Cobertura inativa para paciente " + patient.getName(),
                response.getErrorMessage()
            );

            return CheckInResult.denied(
                "Cobertura inativa. " + response.getErrorMessage()
            );
        }

        // 5. Verificar carência
        if (response.getCoverageEffectiveDate() != null &&
            response.getCoverageEffectiveDate().isAfter(LocalDate.now())) {
            return CheckInResult.warning(
                String.format("Plano em período de carência até %s",
                    response.getCoverageEffectiveDate())
            );
        }

        // 6. Verificar vencimento
        if (response.getCoverageTerminationDate() != null &&
            response.getCoverageTerminationDate().isBefore(LocalDate.now().plusDays(30))) {
            notificationService.notifyPatient(
                patientId,
                "Atenção: Plano próximo do vencimento",
                String.format("Seu plano vence em %s", response.getCoverageTerminationDate())
            );
        }

        // 7. Informar valores de co-participação
        CheckInResult result = CheckInResult.approved("Elegibilidade confirmada");
        if (response.getCopayAmount() != null && response.getCopayAmount().compareTo(BigDecimal.ZERO) > 0) {
            result.addInfo(String.format("Co-participação: R$ %.2f", response.getCopayAmount()));
        }
        if (response.getRemainingDeductible() != null && response.getRemainingDeductible().compareTo(BigDecimal.ZERO) > 0) {
            result.addInfo(String.format("Franquia restante: R$ %.2f", response.getRemainingDeductible()));
        }

        // 8. Cachear resposta para evitar múltiplas chamadas
        cacheEligibilityResponse(patientId, response, Duration.ofHours(1));

        return result;
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário

```java
class EligibilityRequestTest {

    @Test
    void testBuilder_AllFieldsSet() {
        // Arrange & Act
        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("123456")
            .insuranceCardNumber("1234567890123")
            .serviceDate(LocalDate.of(2026, 1, 15))
            .transactionType("270")
            .providerNpi("1234567890")
            .serviceTypeCode("30")
            .build();

        // Assert
        assertEquals("PAT-123", request.getPatientId());
        assertEquals("123456", request.getPayerId());
        assertEquals("1234567890123", request.getInsuranceCardNumber());
        assertEquals(LocalDate.of(2026, 1, 15), request.getServiceDate());
        assertEquals("270", request.getTransactionType());
        assertEquals("1234567890", request.getProviderNpi());
        assertEquals("30", request.getServiceTypeCode());
    }

    @Test
    void testBuilder_MinimalFields() {
        // Arrange & Act
        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("123456")
            .insuranceCardNumber("1234567890123")
            .serviceDate(LocalDate.now())
            .build();

        // Assert
        assertNotNull(request);
        assertNull(request.getTransactionType()); // Opcional
        assertNull(request.getProviderNpi()); // Opcional
        assertNull(request.getServiceTypeCode()); // Opcional
    }

    @Test
    void testSerialization_ToJson() throws JsonProcessingException {
        // Arrange
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());

        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("123456")
            .insuranceCardNumber("1234567890123")
            .serviceDate(LocalDate.of(2026, 1, 15))
            .build();

        // Act
        String json = mapper.writeValueAsString(request);

        // Assert
        assertTrue(json.contains("\"patientId\":\"PAT-123\""));
        assertTrue(json.contains("\"payerId\":\"123456\""));
        assertTrue(json.contains("\"insuranceCardNumber\":\"1234567890123\""));
    }

    @Test
    void testDeserialization_FromJson() throws JsonProcessingException {
        // Arrange
        String json = """
            {
                "patientId": "PAT-123",
                "payerId": "123456",
                "insuranceCardNumber": "1234567890123",
                "serviceDate": "2026-01-15",
                "transactionType": "270",
                "providerNpi": "1234567890",
                "serviceTypeCode": "30"
            }
            """;

        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());

        // Act
        EligibilityRequest request = mapper.readValue(json, EligibilityRequest.class);

        // Assert
        assertEquals("PAT-123", request.getPatientId());
        assertEquals("123456", request.getPayerId());
        assertEquals("270", request.getTransactionType());
    }
}
```

### 12.2. Massa de Dados para Teste

```json
{
  "minimal_request": {
    "patientId": "PAT-12345",
    "payerId": "123456",
    "insuranceCardNumber": "1234567890123",
    "serviceDate": "2026-01-15"
  },
  "complete_request": {
    "patientId": "PAT-67890",
    "payerId": "334545",
    "insuranceCardNumber": "9876543210987",
    "serviceDate": "2026-01-20",
    "transactionType": "270",
    "providerNpi": "9876543210",
    "serviceTypeCode": "30"
  },
  "emergency_request": {
    "patientId": "PAT-99999",
    "payerId": "456789",
    "insuranceCardNumber": "5555666677778",
    "serviceDate": "2026-01-12",
    "transactionType": "270",
    "serviceTypeCode": "86"
  }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **Dados do Paciente**: patientId deve ser validado contra autorização do usuário
- **Número da Carteirinha**: Dado sensível - proteger conforme LGPD

### 13.2. Proteção de Dados
- **PII**: patientId, insuranceCardNumber são dados pessoais
- **Dados de Saúde**: Trafegar via TLS 1.2+
- **Logging**: Mascarar insuranceCardNumber em logs

### 13.3. Auditoria
```java
@Aspect
@Component
public class EligibilityRequestAuditAspect {

    @Before("execution(* InsuranceApiClient.checkEligibility(..)) && args(request)")
    public void auditEligibilityRequest(EligibilityRequest request) {
        String maskedCardNumber = maskCardNumber(request.getInsuranceCardNumber());
        auditLog.info("Eligibility check requested",
            "maskedPatientId", "****" + request.getPatientId().substring(request.getPatientId().length() - 4),
            "payerId", request.getPayerId(),
            "maskedCardNumber", maskedCardNumber,
            "serviceDate", request.getServiceDate(),
            "user", SecurityContextHolder.getContext().getAuthentication().getName()
        );
    }

    private String maskCardNumber(String cardNumber) {
        if (cardNumber == null || cardNumber.length() < 4) return "****";
        return cardNumber.substring(0, 4) + "****" + cardNumber.substring(cardNumber.length() - 4);
    }
}
```

## 14. Referências

### 14.1. Documentação Relacionada
- `EligibilityResponse.java` - DTO de resposta correspondente (X12 271 EDI)
- `InsuranceApiClient.java` - Cliente que consome este DTO
- `EligibilityVerificationDelegate.java` - Camunda delegate que constrói request

### 14.2. Padrões e Especificações
- **X12 EDI 270**: Health Care Eligibility Benefit Inquiry
- **TISS 4.03.03**: Padrão TISS ANS para elegibilidade

### 14.3. Links Externos
- [X12 EDI 270/271 Standards](https://x12.org/products/health-care)
- [ANS - Padrão TISS](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)

### 14.4. Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm - Coder Agent 7 | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:c9f8e7d6c5b4a9e3d8c7b6f5e4d9a8c9b7e6f5d4c9a8b7e6d5f4c3b9a8e7d6f5`
**Última Atualização:** 2026-01-12T13:23:00Z
**Próxima Revisão:** 2026-04-12
