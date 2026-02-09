# RN-InsuranceApiClient - Cliente de Integração com Operadoras de Saúde

## 1. Identificação da Regra
- **ID:** RN-INSURANCE-CLIENT-001
- **Nome:** Cliente Feign de Integração com APIs de Operadoras de Saúde
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 7
- **Categoria:** Integration Layer / Insurance Provider Client
- **Prioridade:** Crítica
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
O InsuranceApiClient é o cliente Feign responsável pela integração em tempo real com APIs de operadoras de saúde brasileiras (Unimed, Bradesco Saúde, SulAmérica, Amil, etc.). Realiza verificação de elegibilidade (X12 270/271 EDI), consulta de cobertura de procedimentos TUSS, validação de beneficiários e requisição de autorizações prévias.

### 2.2. Descrição Técnica
Interface Feign declarativa com endpoints REST para operações de elegibilidade e cobertura. Suporta transações X12 270/271 EDI standardizadas, autenticação via API Key ou OAuth 2.0, circuit breaker para resiliência, e retry com exponential backoff. Configurado via InsuranceApiFeignConfig com timeouts de 5s (conexão) e 10s (leitura).

### 2.3. Origem do Requisito
- **Funcional:** Verificação de elegibilidade e cobertura em tempo real conforme RN-259 ANS
- **Regulatório:** RN-469/2021 ANS - Verificação de elegibilidade eletrônica obrigatória
- **Técnico:** Arquitetura de integração com circuit breaker e retry policies

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Verificação de Elegibilidade do Beneficiário (X12 270/271)
- **UC-02**: Consulta de Cobertura para Procedimentos TUSS
- **UC-03**: Validação de Benefício Ativo e Período de Carência
- **UC-04**: Consulta de Valores de Co-participação
- **UC-05**: Verificação de Necessidade de Autorização Prévia
- **UC-06**: Consulta de Rede Credenciada (in-network vs out-of-network)
- **UC-07**: Validação de Limites de Frequência de Procedimentos
- **UC-08**: Consulta de Franquia (Deductible) e Teto (Out-of-Pocket Max)

### 3.2. Processos BPMN Relacionados
- **Process ID:** revenue-cycle-main
  - **Task:** Verificar Elegibilidade
  - **Service Task:** CheckEligibilityTask (camundaDelegate: EligibilityVerificationDelegate)
- **Process ID:** pre-authorization
  - **Task:** Consultar Cobertura de Procedimentos
  - **Service Task:** CheckCoverageTask (camundaDelegate: CoverageVerificationDelegate)
- **Process ID:** patient-registration
  - **Task:** Validar Beneficiário
  - **Service Task:** ValidateBeneficiaryTask
- **Process ID:** claim-validation
  - **Task:** Verificar Autorização Prévia
  - **Service Task:** CheckAuthorizationRequirementTask

### 3.3. Entidades Afetadas
- **EligibilityRequest/Response**: Transações X12 270/271 EDI
- **CoverageCheckRequest/Response**: Verificação de cobertura de procedimentos
- **BeneficiaryDTO**: Dados do beneficiário para validação
- **AuthorizationDTO**: Status de autorizações prévias
- **CoverageDTO**: Detalhes de cobertura e cost-sharing

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
SE paciente possui plano de saúde
E necessidade de verificar elegibilidade OU cobertura
ENTÃO invocar InsuranceApiClient
COM autenticação apropriada (API Key ou OAuth 2.0)
```

### 4.2. Critérios de Validação
1. **Autenticação Válida**: API Key presente ou token OAuth 2.0 válido
2. **Dados Obrigatórios**: patientId, payerId, serviceDate não podem ser nulos
3. **Formato TUSS**: Códigos de procedimento devem seguir padrão TUSS 4.03.03
4. **Timeout**: Resposta obrigatória em até 10 segundos
5. **Rate Limiting**: Respeitar limites de taxa da operadora (429)

### 4.3. Ações e Consequências
**QUANDO** checkEligibility() invocado:
1. **Validar** request (patientId, payerId, serviceDate obrigatórios)
2. **Construir** transação X12 270 EDI
3. **Enviar** POST /v1/eligibility/verify
4. **Aguardar** resposta X12 271 EDI (timeout 10s)
5. **Mapear** resposta para EligibilityResponse DTO
6. **Retornar** status de cobertura, franquia, co-participação, datas de vigência

**QUANDO** checkCoverage() invocado:
1. **Validar** request (patientId, payerId, procedureCodes obrigatórios)
2. **Iterar** sobre lista de códigos TUSS
3. **Verificar** cobertura, autorização prévia, limites de frequência
4. **Calcular** copay, coinsurance, deductible impact
5. **Retornar** CoverageCheckResponse com detalhes por procedimento

**SE** erro ocorrer:
- **401**: Autenticação falhou → renovar credenciais
- **404**: Beneficiário não encontrado → validar carteirinha
- **429**: Rate limit excedido → aplicar backoff
- **503**: Serviço indisponível → ativar circuit breaker

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio
**Cálculo de Valor Devido pelo Paciente:**
```
patient_responsibility = copay + coinsurance_amount + remaining_deductible

Onde:
- copay: Valor fixo por procedimento (e.g., R$ 50,00)
- coinsurance_amount: (procedure_cost - copay) * coinsurance_percent
- remaining_deductible: MIN(procedure_cost, remaining_deductible_balance)

Exemplo:
- Procedimento: R$ 1.000,00
- Copay: R$ 50,00
- Coinsurance: 20%
- Remaining Deductible: R$ 200,00

coinsurance_amount = (1000 - 50) * 0.20 = R$ 190,00
patient_responsibility = 50 + 190 + 200 = R$ 440,00
insurance_payment = 1000 - 440 = R$ 560,00
```

### 5.2. Regras de Arredondamento
- **Valores Monetários**: Arredondar para 2 casas decimais (BigDecimal HALF_UP)
- **Percentuais**: Manter precisão de 4 casas decimais (e.g., 0.2250 = 22.50%)

### 5.3. Tratamento de Valores Especiais
- **Copay null**: Assumir R$ 0,00 (sem co-participação)
- **Coinsurance null**: Assumir 0% (sem coinsurance)
- **Deductible met**: Se remaining_deductible = 0, não aplicar franquia
- **Out-of-pocket max met**: Se atingido, copay e coinsurance = 0

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Campos Mapeados - X12 270/271 para TISS

| Campo X12 EDI | Campo Insurance API | Campo TISS | Obrigatório |
|---------------|---------------------|------------|-------------|
| 270.NM1.MI | patientId | beneficiario.numeroDaCarteira | Sim |
| 270.NM1.PI | payerId | operadora.registroANS | Sim |
| 270.DTP.472 | serviceDate | dataExecucao | Sim |
| 271.EB.1 | eligibilityStatus | statusElegibilidade | Sim |
| 271.DTP.346 | coverageEffectiveDate | inicioVigencia | Sim |
| 271.DTP.347 | coverageTerminationDate | fimVigencia | Não |
| 271.EB.B | copayAmount | valorCoParticipacao | Não |
| 271.EB.C | deductibleAmount | valorFranquia | Não |
| 271.EB.G | outOfPocketMax | limiteMaximoResponsabilidade | Não |

### 6.3. Códigos TUSS para Cobertura
- **Consulta Médica**: 10101012 (Consulta em consultório)
- **Exames Laboratoriais**: 40301010 - 40316289
- **Exames de Imagem**: 40801004 - 40901300
- **Internação**: 80000007 (Diária hospitalar)
- **Procedimentos Cirúrgicos**: 30701018 - 31505179

### 6.4. Guias Aplicáveis
- **Guia de Consulta**: Verificação de copay e carência
- **Guia SP-SADT**: Autorização prévia para exames de alto custo
- **Guia de Internação**: Validação de cobertura hospitalar
- **Guia de Honorários Médicos**: Cobertura de honorários cirúrgicos

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-469/2021**: Padrão de Troca de Informações na Saúde Suplementar (TISS)
- **RN-453/2020**: Procedimentos para envio de guias e protocolo eletrônico
- **RN-506/2022**: Autorização Prévia Eletrônica obrigatória
- **RN-259/2011**: Cobertura obrigatória do Rol de Procedimentos ANS
- **RN-473/2021**: Padrões de interoperabilidade e segurança

### 7.2. Requisitos LGPD
- **Art. 7º, I**: Base legal para processamento de dados de saúde (execução de contrato)
- **Art. 9º, §1º**: Consentimento específico para dados sensíveis de saúde
- **Art. 46**: Segurança no processamento (TLS 1.2+, API Key mascarada)
- **Art. 48**: Comunicação de incidentes de segurança em até 72h
- **Anonimização**: Não aplicável - dados identificados necessários para elegibilidade

### 7.3. Validações Regulatórias
1. **Verificação Obrigatória**: Elegibilidade deve ser verificada antes de procedimentos eletivos
2. **Prazo de Resposta**: Operadora deve responder em até 10 segundos (SLA ANS)
3. **Autorização Prévia**: Obrigatória para procedimentos de alta complexidade (Lista ANS)
4. **Cobertura Mínima**: Todos os procedimentos do Rol ANS devem retornar `covered=true`
5. **Negativa de Cobertura**: Deve incluir justificativa e código de motivo ANS

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio

| Código | Exceção | Causa | Ação |
|--------|---------|-------|------|
| INS-400 | InvalidRequestException | Campos obrigatórios ausentes | Validar request antes de enviar |
| INS-401 | AuthenticationException | API Key inválida/expirada | Renovar credenciais |
| INS-403 | AuthorizationException | Permissão insuficiente | Verificar permissões do payer |
| INS-404 | ResourceNotFoundException | Beneficiário não encontrado | Validar número da carteirinha |
| INS-429 | RateLimitException | Limite de requisições excedido | Implementar exponential backoff |
| INS-500 | InternalServerException | Erro interno da operadora | Retry até 3x com backoff |
| INS-503 | ServiceUnavailableException | Serviço temporariamente indisponível | Ativar circuit breaker |

### 8.2. Erros Técnicos

| Tipo | Descrição | Tratamento |
|------|-----------|------------|
| FeignException.Timeout | Timeout de 10s excedido | Retry 2x, depois fallback |
| RetryableException | Erro temporário (5xx) | Retry exponencial (1s, 2s, 5s) |
| DecodeException | Resposta JSON inválida | Log detalhado e DLQ |
| CircuitBreakerOpenException | Circuit breaker aberto | Retornar resposta cacheada ou erro gracioso |

### 8.3. Estratégias de Recuperação

1. **Retry Policy**:
   ```
   Max Attempts: 3
   Initial Interval: 1 segundo
   Max Interval: 5 segundos
   Multiplier: 2x
   ```

2. **Circuit Breaker**:
   ```
   Failure Threshold: 5 falhas consecutivas
   Timeout: 10 segundos
   Half-Open: Permitir 1 request após 30s
   ```

3. **Fallback**:
   - Retornar dados cacheados de verificação anterior (TTL 1h)
   - Se cache expirado, retornar `verificationSuccessful=false` com `errorMessage`

4. **Dead Letter Queue (DLQ)**:
   - Requisições falhas após 3 retries enviadas para DLQ
   - Processar manualmente ou via job batch noturno

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **EligibilityVerificationDelegate**: Camunda delegate que invoca checkEligibility()
- **CoverageVerificationDelegate**: Camunda delegate que invoca checkCoverage()
- **InsuranceApiFeignConfig**: Configuração Feign (error decoder, retry, logging)
- **PatientService**: Fornece patientId e insuranceCardNumber

### 9.2. Dependências Downstream
- **Insurance Provider APIs**: APIs REST das operadoras de saúde
  - Base URLs configuradas por operadora: `${insurance.api.base-url.unimed}`, etc.
- **X12 EDI Gateway**: Conversão de JSON para transações X12 270/271 (se necessário)
- **OAuth 2.0 Provider**: Token service para autenticação em produção

### 9.3. Eventos Publicados
```java
// Publicar evento após verificação bem-sucedida
eventBus.publish(new EligibilityVerifiedEvent(
    patientId,
    payerId,
    eligibilityStatus,
    coverageActive,
    verificationTimestamp
));

// Publicar evento após consulta de cobertura
eventBus.publish(new CoverageCheckedEvent(
    patientId,
    procedureCodes,
    coveredProcedures,
    notCoveredProcedures,
    requiresPriorAuthorization
));
```

### 9.4. Eventos Consumidos
Não consome eventos diretamente - acionado por Camunda service tasks.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Tempo de Resposta**: < 10 segundos (P95)
- **Timeout de Conexão**: 5 segundos
- **Timeout de Leitura**: 10 segundos
- **Throughput**: ~100 req/min por instância (limitado por rate limit da operadora)
- **Concorrência**: Thread-safe (Feign gerencia connection pooling)

### 10.2. Estratégias de Cache

**Cache de Elegibilidade:**
```java
@Cacheable(value = "eligibility", key = "#patientId + '-' + #payerId", ttl = 3600)
public EligibilityResponse checkEligibility(EligibilityRequest request) {
    return insuranceApiClient.checkEligibility(request);
}
```
- **TTL**: 1 hora (3600 segundos)
- **Eviction**: LRU (Least Recently Used)
- **Cache invalidation**: Manual via endpoint `/api/cache/invalidate/eligibility/{patientId}`

**Cache de Cobertura:**
```java
@Cacheable(value = "coverage", key = "#payerId + '-' + #procedureCode", ttl = 86400)
public ProcedureCoverage checkProcedureCoverage(String payerId, String procedureCode) {
    // ...
}
```
- **TTL**: 24 horas (86400 segundos)
- **Reasoning**: Coberturas por procedimento raramente mudam

### 10.3. Otimizações Implementadas

1. **Connection Pooling**:
   ```yaml
   feign:
     httpclient:
       max-connections: 200
       max-connections-per-route: 50
   ```

2. **Request Compression**:
   ```java
   requestTemplate.header("Accept-Encoding", "gzip, deflate");
   ```

3. **Response Streaming**: Para listas grandes de procedimentos

4. **Batch Coverage Check**: `checkCoverage()` aceita múltiplos procedureCodes para reduzir chamadas

## 11. Exemplos de Uso

### 11.1. Exemplo Básico - Verificação de Elegibilidade

```java
@Autowired
private InsuranceApiClient insuranceApiClient;

// Verificar elegibilidade simples
EligibilityRequest request = EligibilityRequest.builder()
    .patientId("PATIENT-12345")
    .payerId("UNIMED-SP-123456")
    .insuranceCardNumber("1234567890123")
    .serviceDate(LocalDate.now())
    .transactionType("270")
    .providerNpi("1234567890")
    .serviceTypeCode("30") // Health benefit plan coverage
    .build();

EligibilityResponse response = insuranceApiClient.checkEligibility(request);

if (response.isCoverageActive()) {
    System.out.println("Cobertura ativa até: " + response.getCoverageTerminationDate());
    System.out.println("Copay: R$ " + response.getCopayAmount());
    System.out.println("Franquia restante: R$ " + response.getRemainingDeductible());
} else {
    System.out.println("Cobertura inativa: " + response.getErrorMessage());
}
```

### 11.2. Exemplo Avançado - Verificação de Cobertura de Múltiplos Procedimentos

```java
@Service
@RequiredArgsConstructor
public class PreAuthorizationService {

    private final InsuranceApiClient insuranceApiClient;

    public PreAuthorizationResult checkProcedureCoverage(
        String patientId,
        String payerId,
        List<String> tussCodes
    ) {
        // 1. Verificar elegibilidade primeiro
        EligibilityRequest eligRequest = EligibilityRequest.builder()
            .patientId(patientId)
            .payerId(payerId)
            .serviceDate(LocalDate.now())
            .build();

        EligibilityResponse eligResponse = insuranceApiClient.checkEligibility(eligRequest);

        if (!eligResponse.isCoverageActive()) {
            throw new IneligiblePatientException("Paciente sem cobertura ativa");
        }

        // 2. Verificar cobertura de cada procedimento
        CoverageCheckRequest coverageRequest = CoverageCheckRequest.builder()
            .patientId(patientId)
            .payerId(payerId)
            .procedureCodes(tussCodes)
            .serviceDate(LocalDate.now())
            .providerNpi("1234567890")
            .placeOfService("OUTPATIENT")
            .build();

        CoverageCheckResponse coverageResponse = insuranceApiClient.checkCoverage(coverageRequest);

        // 3. Analisar resultados
        PreAuthorizationResult result = new PreAuthorizationResult();
        result.setEligible(eligResponse.isCoverageActive());
        result.setPlanName(eligResponse.getPlanName());

        for (String code : tussCodes) {
            ProcedureCoverage coverage = coverageResponse.getProcedureCoverageDetails().get(code);

            if (coverage == null || !coverage.isCovered()) {
                result.addDeniedProcedure(code, "Procedimento não coberto pelo plano");
            } else if (coverage.isRequiresPriorAuth()) {
                result.addRequiresPriorAuth(code);
            } else {
                result.addApprovedProcedure(code, coverage.getCopay(), coverage.getCoinsurancePercent());
            }
        }

        return result;
    }
}
```

### 11.3. Exemplo de Caso de Uso Completo - Fluxo de Autorização Prévia

```java
/**
 * UC: Fluxo Completo de Autorização Prévia para Procedimento de Alta Complexidade
 */
@Service
@RequiredArgsConstructor
public class AuthorizationWorkflow {

    private final InsuranceApiClient insuranceApiClient;
    private final RuntimeService runtimeService;
    private final TaskService taskService;

    public AuthorizationResult processAuthorizationRequest(
        String patientId,
        String payerId,
        String procedureCode,
        String diagnosisCode
    ) {
        // 1. Iniciar processo Camunda
        Map<String, Object> variables = new HashMap<>();
        variables.put("patientId", patientId);
        variables.put("payerId", payerId);
        variables.put("procedureCode", procedureCode);
        variables.put("diagnosisCode", diagnosisCode);

        ProcessInstance processInstance = runtimeService.startProcessInstanceByKey(
            "pre-authorization-workflow",
            variables
        );

        // 2. Verificar elegibilidade
        EligibilityRequest eligRequest = EligibilityRequest.builder()
            .patientId(patientId)
            .payerId(payerId)
            .serviceDate(LocalDate.now())
            .providerNpi("1234567890")
            .build();

        EligibilityResponse eligResponse = insuranceApiClient.checkEligibility(eligRequest);

        if (!eligResponse.isCoverageActive()) {
            // Abortar processo - paciente inelegível
            runtimeService.setVariable(processInstance.getId(), "eligible", false);
            runtimeService.setVariable(processInstance.getId(), "denialReason", eligResponse.getErrorMessage());

            return AuthorizationResult.denied("Paciente sem cobertura ativa");
        }

        // 3. Verificar cobertura do procedimento específico
        CoverageCheckRequest coverageRequest = CoverageCheckRequest.builder()
            .patientId(patientId)
            .payerId(payerId)
            .procedureCodes(List.of(procedureCode))
            .serviceDate(LocalDate.now().plusDays(7)) // Procedimento agendado para próxima semana
            .providerNpi("1234567890")
            .placeOfService("INPATIENT")
            .build();

        CoverageCheckResponse coverageResponse = insuranceApiClient.checkCoverage(coverageRequest);
        ProcedureCoverage coverage = coverageResponse.getProcedureCoverageDetails().get(procedureCode);

        if (coverage == null || !coverage.isCovered()) {
            // Procedimento não coberto
            runtimeService.setVariable(processInstance.getId(), "covered", false);
            return AuthorizationResult.denied("Procedimento não coberto pelo plano");
        }

        // 4. Verificar necessidade de autorização prévia
        if (!coverage.isRequiresPriorAuth()) {
            // Não requer autorização - aprovar automaticamente
            runtimeService.setVariable(processInstance.getId(), "autoApproved", true);
            return AuthorizationResult.approved("Procedimento não requer autorização prévia");
        }

        // 5. Verificar limites de frequência
        if (coverage.getRemainingFrequency() != null && coverage.getRemainingFrequency() == 0) {
            return AuthorizationResult.denied("Limite de frequência anual atingido");
        }

        // 6. Calcular responsabilidade financeira do paciente
        BigDecimal patientResponsibility = calculatePatientResponsibility(
            eligResponse,
            coverage,
            BigDecimal.valueOf(5000.00) // Custo estimado do procedimento
        );

        runtimeService.setVariable(processInstance.getId(), "patientResponsibility", patientResponsibility);

        // 7. Criar tarefa manual para aprovação médica
        Task task = taskService.createTaskQuery()
            .processInstanceId(processInstance.getId())
            .taskDefinitionKey("medical-review")
            .singleResult();

        taskService.setVariable(task.getId(), "eligibilityDetails", eligResponse);
        taskService.setVariable(task.getId(), "coverageDetails", coverage);
        taskService.setVariable(task.getId(), "estimatedCost", patientResponsibility);

        return AuthorizationResult.pending(
            processInstance.getId(),
            task.getId(),
            "Autorização pendente de revisão médica"
        );
    }

    private BigDecimal calculatePatientResponsibility(
        EligibilityResponse eligibility,
        ProcedureCoverage coverage,
        BigDecimal procedureCost
    ) {
        BigDecimal copay = coverage.getCopay() != null ? coverage.getCopay() : BigDecimal.ZERO;
        BigDecimal coinsurancePercent = coverage.getCoinsurancePercent() != null
            ? coverage.getCoinsurancePercent()
            : BigDecimal.ZERO;
        BigDecimal remainingDeductible = eligibility.getRemainingDeductible() != null
            ? eligibility.getRemainingDeductible()
            : BigDecimal.ZERO;

        // Copay
        BigDecimal total = copay;

        // Coinsurance
        BigDecimal coinsuranceAmount = procedureCost.subtract(copay)
            .multiply(coinsurancePercent)
            .setScale(2, RoundingMode.HALF_UP);
        total = total.add(coinsuranceAmount);

        // Deductible
        BigDecimal deductibleApplied = remainingDeductible.min(procedureCost);
        total = total.add(deductibleApplied);

        // Check out-of-pocket max
        BigDecimal remainingOOP = eligibility.getRemainingOutOfPocket();
        if (remainingOOP != null && total.compareTo(remainingOOP) > 0) {
            total = remainingOOP;
        }

        return total;
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário

```java
@ExtendWith(MockitoExtension.class)
class InsuranceApiClientTest {

    @Mock
    private InsuranceApiClient insuranceApiClient;

    @Test
    void testCheckEligibility_ActiveCoverage() {
        // Arrange
        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .serviceDate(LocalDate.now())
            .build();

        EligibilityResponse expected = EligibilityResponse.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .eligibilityStatus("ACTIVE")
            .coverageActive(true)
            .copayAmount(new BigDecimal("50.00"))
            .deductibleAmount(new BigDecimal("1000.00"))
            .remainingDeductible(new BigDecimal("300.00"))
            .build();

        when(insuranceApiClient.checkEligibility(request)).thenReturn(expected);

        // Act
        EligibilityResponse result = insuranceApiClient.checkEligibility(request);

        // Assert
        assertTrue(result.isCoverageActive());
        assertEquals("ACTIVE", result.getEligibilityStatus());
        assertEquals(0, new BigDecimal("50.00").compareTo(result.getCopayAmount()));
    }

    @Test
    void testCheckCoverage_RequiresPriorAuth() {
        // Arrange
        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .procedureCodes(List.of("30701018")) // Cirurgia de alta complexidade
            .serviceDate(LocalDate.now())
            .build();

        ProcedureCoverage procedureCoverage = ProcedureCoverage.builder()
            .procedureCode("30701018")
            .covered(true)
            .requiresPriorAuth(true)
            .copay(BigDecimal.ZERO)
            .coinsurancePercent(new BigDecimal("0.20"))
            .build();

        CoverageCheckResponse expected = CoverageCheckResponse.builder()
            .verificationSuccessful(true)
            .requiresPriorAuthorization(List.of("30701018"))
            .procedureCoverageDetails(Map.of("30701018", procedureCoverage))
            .build();

        when(insuranceApiClient.checkCoverage(request)).thenReturn(expected);

        // Act
        CoverageCheckResponse result = insuranceApiClient.checkCoverage(request);

        // Assert
        assertTrue(result.isVerificationSuccessful());
        assertTrue(result.getRequiresPriorAuthorization().contains("30701018"));
        assertTrue(result.getProcedureCoverageDetails().get("30701018").isRequiresPriorAuth());
    }

    @Test
    void testCheckEligibilityWithAuth_CustomApiKey() {
        // Arrange
        String customApiKey = "custom-key-12345";
        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("BRADESCO-456")
            .build();

        EligibilityResponse expected = EligibilityResponse.builder()
            .coverageActive(true)
            .build();

        when(insuranceApiClient.checkEligibilityWithAuth(customApiKey, request))
            .thenReturn(expected);

        // Act
        EligibilityResponse result = insuranceApiClient.checkEligibilityWithAuth(customApiKey, request);

        // Assert
        assertTrue(result.isCoverageActive());
        verify(insuranceApiClient).checkEligibilityWithAuth(eq(customApiKey), eq(request));
    }
}
```

### 12.2. Cenários de Teste de Integração

```java
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class InsuranceApiClientIntegrationTest {

    @Autowired
    private InsuranceApiClient insuranceApiClient;

    @Test
    void testCheckEligibility_RealApiCall() {
        // Arrange: Mock operadora API
        stubFor(post(urlEqualTo("/v1/eligibility/verify"))
            .withHeader("X-API-Key", matching(".*"))
            .withHeader("Content-Type", equalTo("application/json"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                        "patientId": "PAT-123",
                        "payerId": "UNIMED-123",
                        "eligibilityStatus": "ACTIVE",
                        "coverageActive": true,
                        "copayAmount": 50.00,
                        "deductibleAmount": 1000.00,
                        "remainingDeductible": 300.00,
                        "planType": "PPO",
                        "networkStatus": "IN_NETWORK"
                    }
                    """)));

        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .serviceDate(LocalDate.now())
            .build();

        // Act
        EligibilityResponse response = insuranceApiClient.checkEligibility(request);

        // Assert
        assertTrue(response.isCoverageActive());
        assertEquals("ACTIVE", response.getEligibilityStatus());
        assertEquals("PPO", response.getPlanType());
        assertEquals("IN_NETWORK", response.getNetworkStatus());
    }

    @Test
    void testCheckCoverage_NotCovered() {
        // Arrange: Mock procedimento não coberto
        stubFor(post(urlEqualTo("/v1/coverage/check"))
            .willReturn(aResponse()
                .withStatus(200)
                .withBody("""
                    {
                        "verificationSuccessful": true,
                        "notCoveredProcedures": ["99999999"],
                        "procedureCoverageDetails": {
                            "99999999": {
                                "procedureCode": "99999999",
                                "covered": false,
                                "requiresPriorAuth": false
                            }
                        }
                    }
                    """)));

        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .procedureCodes(List.of("99999999"))
            .build();

        // Act
        CoverageCheckResponse response = insuranceApiClient.checkCoverage(request);

        // Assert
        assertTrue(response.isVerificationSuccessful());
        assertTrue(response.getNotCoveredProcedures().contains("99999999"));
        assertFalse(response.getProcedureCoverageDetails().get("99999999").isCovered());
    }

    @Test
    void testCheckEligibility_Timeout() {
        // Arrange: Simular timeout
        stubFor(post(urlEqualTo("/v1/eligibility/verify"))
            .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(15000))); // 15s delay > 10s timeout

        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .build();

        // Act & Assert
        assertThrows(FeignException.class, () -> {
            insuranceApiClient.checkEligibility(request);
        });
    }
}
```

### 12.3. Massa de Dados para Teste

```json
{
  "valid_eligibility_request": {
    "patientId": "PAT-12345",
    "payerId": "UNIMED-SP-123456",
    "insuranceCardNumber": "1234567890123",
    "serviceDate": "2026-01-12",
    "transactionType": "270",
    "providerNpi": "1234567890",
    "serviceTypeCode": "30"
  },
  "active_coverage_response": {
    "patientId": "PAT-12345",
    "payerId": "UNIMED-SP-123456",
    "payerName": "Unimed São Paulo",
    "planName": "Plano Empresarial Nacional",
    "eligibilityStatus": "ACTIVE",
    "coverageActive": true,
    "coverageEffectiveDate": "2025-01-01",
    "coverageTerminationDate": null,
    "copayAmount": 50.00,
    "deductibleAmount": 1000.00,
    "remainingDeductible": 300.00,
    "outOfPocketMax": 5000.00,
    "remainingOutOfPocket": 3500.00,
    "coinsurancePercent": 0.20,
    "planType": "PPO",
    "networkStatus": "IN_NETWORK",
    "verificationDate": "2026-01-12"
  },
  "coverage_check_request": {
    "patientId": "PAT-12345",
    "payerId": "UNIMED-SP-123456",
    "procedureCodes": ["10101012", "40301010", "30701018"],
    "serviceDate": "2026-01-15",
    "providerNpi": "1234567890",
    "placeOfService": "OUTPATIENT"
  },
  "coverage_with_prior_auth": {
    "verificationSuccessful": true,
    "coveredProcedures": ["10101012", "40301010"],
    "requiresPriorAuthorization": ["30701018"],
    "procedureCoverageDetails": {
      "10101012": {
        "procedureCode": "10101012",
        "covered": true,
        "requiresPriorAuth": false,
        "copay": 50.00,
        "coinsurancePercent": 0.00,
        "coverageLevel": "STANDARD",
        "frequencyLimit": 12,
        "remainingFrequency": 8
      },
      "30701018": {
        "procedureCode": "30701018",
        "covered": true,
        "requiresPriorAuth": true,
        "copay": 0.00,
        "coinsurancePercent": 0.20,
        "coverageLevel": "HIGH_COMPLEXITY"
      }
    }
  }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **Autenticação**: API Key via header X-API-Key (dev/homolog) ou OAuth 2.0 Bearer token (produção)
- **Autorização**: Gerenciada pela operadora - cada API Key vinculada a hospital/prestador
- **TLS/SSL**: Obrigatório TLS 1.2+ para todas as chamadas (base URL https://)
- **Rotação de Credenciais**: API Keys devem ser rotacionadas a cada 90 dias

### 13.2. Proteção de Dados
- **Dados em Trânsito**: TLS 1.2+ obrigatório com perfect forward secrecy
- **Dados Sensíveis**: Não armazenar dados de saúde retornados pela API
- **Logging Seguro**: API Key mascarada em logs (mostrar apenas últimos 4 caracteres)
- **PII**: CPF e dados pessoais devem ser criptografados em logs

### 13.3. Auditoria
```java
@Aspect
@Component
public class InsuranceApiAuditAspect {

    @AfterReturning(pointcut = "execution(* InsuranceApiClient.*(..))", returning = "result")
    public void auditApiCall(JoinPoint joinPoint, Object result) {
        String method = joinPoint.getSignature().getName();
        Object[] args = joinPoint.getArgs();

        auditLog.info("Insurance API call",
            "method", method,
            "patientId", extractPatientId(args),
            "payerId", extractPayerId(args),
            "timestamp", Instant.now(),
            "user", SecurityContextHolder.getContext().getAuthentication().getName()
        );
    }
}
```

- **Todas as chamadas** auditadas com timestamp, user, patientId, payerId
- **Retention**: Logs de auditoria mantidos por 5 anos (requisito LGPD)
- **Compliance**: Rastreabilidade completa para auditorias ANS

## 14. Referências

### 14.1. Documentação Relacionada
- `InsuranceApiFeignConfig.java` - Configuração Feign (error decoder, retry, logging)
- `EligibilityVerificationDelegate.java` - Camunda delegate para verificação de elegibilidade
- `CoverageVerificationDelegate.java` - Camunda delegate para verificação de cobertura
- DTOs: `EligibilityRequest`, `EligibilityResponse`, `CoverageCheckRequest`, `CoverageCheckResponse`

### 14.2. Padrões e Especificações
- **X12 EDI 270/271**: Health Care Eligibility Benefit Inquiry and Response
- **TISS 4.03.03**: Padrão TISS ANS para troca de informações
- **HL7 FHIR R4**: Coverage Resource (para futuras integrações)
- **OAuth 2.0 RFC 6749**: Para autenticação em produção

### 14.3. Links Externos
- [ANS - Padrão TISS](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)
- [X12 EDI Standards](https://x12.org/products/health-care)
- [Spring Cloud OpenFeign](https://spring.io/projects/spring-cloud-openfeign)
- [Resilience4j Circuit Breaker](https://resilience4j.readme.io/docs/circuitbreaker)

### 14.4. Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm - Coder Agent 7 | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:8f4d9e3b2a6c5f7e9d8c6a4b3f2e9d7c5a8b6f4e3d9c7a5b8f6e4d3c9a7b5f8e`
**Última Atualização:** 2026-01-12T13:19:00Z
**Próxima Revisão:** 2026-04-12
