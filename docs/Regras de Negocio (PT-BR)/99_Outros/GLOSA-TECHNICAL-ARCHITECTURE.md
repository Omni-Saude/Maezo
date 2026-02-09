# Arquitetura Técnica: Sistema de Gestão de Glosas (GLOSA Module)

**Data**: 2026-01-24
**Versão**: 1.0.0
**Escopo**: Arquitetura de integração, padrões de design e mapeamento técnico

---

## PARTE 1: ARQUITETURA DE COMPONENTES

### 1.1 Stack Técnico

```
┌─────────────────────────────────────────────────────────────────┐
│                      BPMN Engine (Camunda 7)                    │
├─────────────────────────────────────────────────────────────────┤
│  Java Service Tasks (JavaDelegate)                              │
│  ├─ IdentifyGlosaDelegate                                       │
│  ├─ ApplyCorrectionsDelegate                                    │
│  ├─ CreateProvisionDelegate                                     │
│  └─ SearchEvidenceDelegate                                      │
├─────────────────────────────────────────────────────────────────┤
│  Spring Framework (Injeção de Dependências)                     │
│  ├─ @Component, @Service, @Repository                           │
│  ├─ Spring Data JPA (Persistência)                              │
│  └─ Spring Boot (Auto-configuration)                            │
├─────────────────────────────────────────────────────────────────┤
│  Integração Externa                                             │
│  ├─ TASY ERP (REST Client)                                      │
│  ├─ TISS Validation (REST Client)                               │
│  ├─ Kafka (Event Publishing)                                    │
│  └─ Database (JDBC/JPA)                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Linguagens e Frameworks

```
Linguagem: Java 11+
Framework: Spring Boot 2.x / Spring 6.x
Workflow: Camunda BPM 7.x
ORM: Hibernate + Spring Data JPA
Logging: SLF4J + Logback
Build: Maven 3.6+
Testing: JUnit 5, Mockito, Testcontainers

Dependências Principais:
├─ org.springframework.boot:spring-boot-starter-web
├─ org.springframework.boot:spring-boot-starter-data-jpa
├─ org.camunda.bpm.springboot:camunda-bpm-spring-boot-starter
├─ org.camunda.bpm:camunda-engine-dmn-bom (optional)
├─ com.fasterxml.jackson.core:jackson-databind (JSON)
└─ org.projectlombok:lombok (Code generation)
```

### 1.3 Padrões de Design Implementados

```
Pattern 1: Strategy Pattern
  Classe: CorrectionStrategyRegistry, CorrectionStrategy interface
  Uso: Seleção dinâmica de estratégia de correção por denialCode
  Benefício: Extensibilidade (fácil adicionar novos códigos TISS)

Pattern 2: Template Method Pattern
  Classe: BaseDelegate
  Uso: Estrutura comum para todos os delegates
  Benefício: Logging, error handling, variable management centralizado

Pattern 3: Dependency Injection
  Framework: Spring Framework
  Uso: Injeção de TasyClient, StrategyRegistry em delegates
  Benefício: Testabilidade, flexibilidade de configuração

Pattern 4: Repository Pattern
  Classe: GlosasRepository, ProvisionsRepository (JPA)
  Uso: Abstração de acesso a dados
  Benefício: Independência de banco de dados

Pattern 5: Event Sourcing
  Implementação: Kafka
  Uso: Publicação de eventos (ProvisionCreated, etc)
  Benefício: Desacoplamento, auditoria de eventos
```

---

## PARTE 2: ESTRUTURA DE CLASSES E PACOTES

### 2.1 Estrutura de Pacotes

```
com.hospital.revenuecycle/
├─ delegates/
│  ├─ BaseDelegate (classe abstrata)
│  ├─ glosa/
│  │  ├─ IdentifyGlosaDelegate
│  │  ├─ ApplyCorrectionsDelegate
│  │  ├─ CreateProvisionDelegate
│  │  ├─ SearchEvidenceDelegate
│  │  ├─ EscalateDelegate
│  │  ├─ LegalReferralDelegate
│  │  ├─ RegisterLossDelegate
│  │  ├─ RegisterRecoveryDelegate
│  │  └─ correction/
│  │     ├─ CorrectionStrategy (interface)
│  │     ├─ CorrectionStrategyRegistry
│  │     ├─ CorrectionResult (data class)
│  │     ├─ DuplicateResolutionStrategy
│  │     ├─ AuthorizationAppealStrategy
│  │     ├─ CodeCorrectionStrategy
│  │     ├─ PriceAdjustmentStrategy
│  │     ├─ DocumentationAttachmentStrategy
│  │     └─ DiagnosisCorrectionStrategy
│  └─ (outros módulos)
│
├─ service/
│  ├─ glosa/
│  │  ├─ GlosaAnalysisService
│  │  ├─ FinancialProvisionService
│  │  ├─ EvidenceSearchService
│  │  └─ GlosaCorrectionOrchestrator
│  └─ (outros serviços)
│
├─ repository/
│  ├─ GlosasRepository (JPA)
│  ├─ ProvisionsRepository (JPA)
│  ├─ CorrectionHistoryRepository (JPA)
│  └─ (outros repositories)
│
├─ domain/
│  ├─ entity/
│  │  ├─ Glosa
│  │  ├─ Provision
│  │  ├─ CorrectionHistory
│  │  ├─ AnalysisResult
│  │  └─ JournalEntry
│  ├─ event/
│  │  ├─ GlosaIdentifiedEvent
│  │  ├─ CorrectionAppliedEvent
│  │  └─ ProvisionCreatedEvent
│  └─ exception/
│     ├─ GlosaProcessingException
│     ├─ InvalidDenialCodeException
│     └─ CorrectionFailedException
│
├─ integration/
│  ├─ tasy/
│  │  ├─ TasyClient (HTTP client)
│  │  ├─ TasyClientConfig
│  │  ├─ TasyClaimDTO
│  │  └─ TasyApiException
│  ├─ tiss/
│  │  ├─ TissClient
│  │  ├─ TissValidator
│  │  └─ TissDTO
│  ├─ kafka/
│  │  ├─ GlosaEventPublisher
│  │  └─ FinancialEventPublisher
│  └─ (outros integradores)
│
├─ controller/
│  ├─ GlosaController (REST endpoints)
│  └─ ProvisionController
│
└─ config/
   ├─ CamundaConfiguration
   ├─ DataSourceConfiguration
   ├─ KafkaConfiguration
   └─ IntegrationConfiguration
```

### 2.2 Classe BaseDelegate

```java
@Slf4j
public abstract class BaseDelegate implements JavaDelegate {

    @Override
    public final void execute(DelegateExecution execution) throws Exception {
        try {
            log.info("Starting {} for processInstanceId: {}",
                getOperationName(), execution.getProcessInstanceId());

            // Template Method Pattern
            executeBusinessLogic(execution);

            log.info("Completed {} successfully", getOperationName());
        } catch (BpmnError e) {
            log.error("BPMN Error in {}: {}", getOperationName(), e.getMessage());
            throw e;
        } catch (Exception e) {
            log.error("Unexpected error in {}: {}", getOperationName(), e.getMessage(), e);
            throw new BpmnError("EXECUTION_FAILED", e.getMessage());
        }
    }

    // Métodos de suporte
    protected <T> T getRequiredVariable(DelegateExecution execution,
                                       String name, Class<T> type) { ... }
    protected <T> T getVariable(DelegateExecution execution,
                               String name, Class<T> type, T defaultValue) { ... }
    protected void setVariable(DelegateExecution execution,
                              String name, Object value) { ... }

    // Métodos abstratos para subclasses
    protected abstract void executeBusinessLogic(DelegateExecution execution) throws Exception;
    public abstract String getOperationName();
    protected abstract Map<String, Object> extractInputParameters(DelegateExecution execution);
    public boolean requiresIdempotency() { return false; }
}
```

### 2.3 Classes de Entidade Principais

```java
@Entity
@Table(name = "glosas")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Glosa {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String glosaId;

    private String claimId;
    private String payerId;
    private BigDecimal originalAmount;
    private BigDecimal glosaAmount;
    private String glosaType;      // FULL_DENIAL, PARTIAL_DENIAL, UNDERPAYMENT, OVERPAYMENT
    private String denialCode;     // TISS code 01-99
    private String denialReason;
    private String status;         // IDENTIFIED, ANALYZED, CORRECTED, PROVISIONED, APPEALED

    @CreationTimestamp
    private LocalDateTime createdAt;
    @UpdateTimestamp
    private LocalDateTime updatedAt;

    // Relacionamentos
    @OneToOne(mappedBy = "glosa")
    private Provision provision;

    @OneToMany(mappedBy = "glosa")
    private List<CorrectionHistory> corrections;
}

@Entity
@Table(name = "glosa_provisions")
@Data
public class Provision {
    @Id
    private String provisionId;

    @OneToOne
    @JoinColumn(name = "glosa_id")
    private Glosa glosa;

    private BigDecimal provisionAmount;
    private String accountingPeriod;  // YYYY-MM

    @Enumerated(EnumType.STRING)
    private ERPIntegrationStatus erpStatus;
    private String erpProvisionId;

    @CreationTimestamp
    private LocalDateTime createdAt;

    @OneToMany(mappedBy = "provision")
    private List<JournalEntry> journalEntries;
}

@Entity
@Table(name = "journal_entries")
@Data
public class JournalEntry {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String journalEntryId;

    @ManyToOne
    @JoinColumn(name = "provision_id")
    private Provision provision;

    private String accountCode;     // 6301 ou 2101
    private BigDecimal debit;
    private BigDecimal credit;
    private String period;          // YYYY-MM
    private String reference;       // PROV-... para rastreabilidade

    @CreationTimestamp
    private LocalDateTime createdAt;
}
```

---

## PARTE 3: FLUXO DE DADOS ENTRE COMPONENTES

### 3.1 Diagrama de Sequência: Identificação de Glosa

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. BPMN Engine publica evento "ProcessPaymentResponse"          │
└─────────────┬───────────────────────────────────────────────────┘
              │ variáveis: claimId, expectedAmount, paymentReceived
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. IdentifyGlosaDelegate.execute()                              │
│    ├─ getRequiredVariable("claimId")                            │
│    ├─ getRequiredVariable("expectedAmount")                     │
│    ├─ getRequiredVariable("paymentReceived")                    │
│    ├─ extractAmount() → normaliza para BigDecimal               │
│    ├─ validateAmounts()                                         │
│    ├─ calcularGlosaAmount()                                     │
│    ├─ aplicarToleranciadeArredondamento()                       │
│    ├─ classifyGlosaType()                                       │
│    └─ setVariable(glosaIdentified, glosaAmount, glosaType)     │
└─────────────┬───────────────────────────────────────────────────┘
              │ saída: glosaIdentified=true, glosaAmount=XXX, glosaType="PARTIAL_DENIAL"
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. BPMN Engine continua fluxo baseado em glosaType             │
│    IF glosaType == "FULL_DENIAL":                               │
│       → RouteToSeniorAppealsTeam                                │
│    ELSE IF glosaType == "PARTIAL_DENIAL":                       │
│       → RouteToGeneralAppealsTeam                               │
│    ELSE:                                                        │
│       → END_PROCESS                                             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Diagrama de Sequência: Aplicação de Correções

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ApplyCorrectionsDelegate.execute()                           │
│    getRequiredVariable("claimId")                               │
│    getRequiredVariable("denialCode")  ← "05" (Valor > Contratado)
│    getRequiredVariable("denialCategory")                        │
│    getVariable("foundDocuments")      ← opcional                │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Lookup Strategy                                              │
│    strategyRegistry.findStrategy("05")                          │
│    → Optional<PriceAdjustmentStrategy>                          │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓ SE NOT FOUND → createFailureResult()
┌─────────────────────────────────────────────────────────────────┐
│ 3. Execute Strategy                                             │
│    TasyClient.getClaimDetails("CLM-001")                        │
│    → TasyClaimDTO {claimId, claimNumber, totalAmount, ...}     │
│                                                                 │
│    convertClaimDtoToMap(claimDto)                               │
│    → Map<String, Object> {claimId, procedureCode, ...}         │
│                                                                 │
│    strategy.applyCorrection(claimId, "05", claimData, docs)    │
│    └─ PriceAdjustmentStrategy.applyCorrection()                │
│       ├─ getContractedPrice(payerId, procedureCode)            │
│       ├─ IF claimData.totalAmount > contractedPrice:           │
│       │    updateClaimAmount(claimId, contractedPrice)         │
│       │    return CorrectionResult(                            │
│       │      success=true,                                     │
│       │      readyForResubmission=true,                        │
│       │      correctionType="PRICE_ADJUSTMENT"                 │
│       │    )                                                    │
│       └─ ELSE: readyForResubmission=true,                      │
│           correctionType="PRICE_VALIDATION"                    │
└─────────────┬───────────────────────────────────────────────────┘
              │ result: CorrectionResult
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Set Output Variables                                         │
│    setVariable(correctionApplied, result.success)              │
│    setVariable(correctionType, result.correctionType)          │
│    setVariable(readyForResubmission, result.readyForResubmission)
│    setVariable(correctionDetails, result.details)              │
│    setVariable(correctedClaimId, result.correctedClaimId)      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Diagrama de Sequência: Criação de Provisão

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CreateProvisionDelegate.execute()                            │
│    getRequiredVariable("glosaId")        ← "GLO-001"            │
│    getRequiredVariable("glosaAmount")    ← 5000.00 (Double)     │
│    getVariable("accountingPeriod")       ← opcional             │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Cálculo e Geração de ID                                      │
│    provisionAmount = calculateProvisionAmount(5000.00)          │
│    → 5000.00 (100% conservador)                                 │
│                                                                 │
│    accountingPeriod = accountingPeriod ?: "2026-01" (padrão)   │
│                                                                 │
│    provisionId = "PROV-" + glosaId + "-" + System.currentTimeMillis()
│    → "PROV-GLO-001-1738108800000"                               │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Operações de Banco de Dados                                  │
│    createProvisionRecord()                                      │
│    INSERT INTO glosa_provisions VALUES (...)                    │
│                                                                 │
│    createJournalEntries()                                       │
│    INSERT INTO journal_entries (6301, 5000, 0, ...)  -- Débito  │
│    INSERT INTO journal_entries (2101, 0, 5000, ...)  -- Crédito │
│                                                                 │
│    updateGlosaStatus("GLO-001", "PROVISIONED")                  │
│    UPDATE glosas SET status = ... WHERE glosa_id = ...         │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Integração ERP (Assíncrona)                                  │
│    integrateWithERP(provisionId, glosaId, provisionAmount)     │
│    → Enfileirar para processamento posterior (quando disponível) │
│                                                                 │
│    POST /api/v1/provisions (assincrono)                         │
│    payload: {provisionId, glosaId, amount, period, entries}    │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Notificação Kafka                                            │
│    notifyFinancialControllers(provisionId, glosaId, amount)    │
│                                                                 │
│    Kafka Topic: "financial-provisions"                          │
│    Event: {                                                     │
│      eventType: "ProvisionCreated",                             │
│      provisionId: "PROV-GLO-001-...",                           │
│      glosaId: "GLO-001",                                        │
│      amount: 5000.00,                                           │
│      period: "2026-01",                                         │
│      createdAt: "2026-01-24T10:30:00Z"                          │
│    }                                                            │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Set Output Variables                                         │
│    setVariable("provisionId", "PROV-GLO-001-...")              │
│    setVariable("provisionAmount", 5000.00)                      │
│    setVariable("provisionCreated", true)                        │
│    setVariable("provisionDate", LocalDateTime.now())            │
│    setVariable("accountingPeriod", "2026-01")                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## PARTE 4: INTEGRAÇÕES TÉCNICAS DETALHADAS

### 4.1 Integração TASY ERP (REST Client)

```java
@Component
public class TasyClient {

    private final RestTemplate restTemplate;
    private final TasyClientConfig config;

    // Operações de Leitura
    public TasyClaimDTO getClaimDetails(String claimId) {
        // GET /claims/{claimId}
        return restTemplate.getForObject(
            config.getBaseUrl() + "/claims/" + claimId,
            TasyClaimDTO.class
        );
    }

    public List<TasyClaimDTO> searchSimilarClaims(String claimId) {
        // GET /claims/search/similar?claimId={claimId}
        return Arrays.asList(restTemplate.getForObject(
            config.getBaseUrl() + "/claims/search/similar?claimId=" + claimId,
            TasyClaimDTO[].class
        ));
    }

    public BigDecimal getContractedPrice(String payerId, String procedureCode) {
        // GET /pricing/{payerId}/{procedureCode}
        PriceDTO priceDto = restTemplate.getForObject(
            config.getBaseUrl() + "/pricing/" + payerId + "/" + procedureCode,
            PriceDTO.class
        );
        return priceDto.getContractedPrice();
    }

    // Operações de Escrita
    public void updateClaimAmount(String claimId, BigDecimal newAmount) {
        // PATCH /claims/{claimId}/amount
        UpdateAmountRequest request = new UpdateAmountRequest(newAmount);
        restTemplate.patchForObject(
            config.getBaseUrl() + "/claims/" + claimId + "/amount",
            request,
            Void.class
        );
    }

    public void updateClaimDiagnosis(String claimId, String diagnosisCode) {
        // PATCH /claims/{claimId}/diagnosis
        UpdateDiagnosisRequest request = new UpdateDiagnosisRequest(diagnosisCode);
        restTemplate.patchForObject(
            config.getBaseUrl() + "/claims/" + claimId + "/diagnosis",
            request,
            Void.class
        );
    }

    public void updateClaimAuthorization(String claimId, String authNumber) {
        // PATCH /claims/{claimId}/authorization
        UpdateAuthRequest request = new UpdateAuthRequest(authNumber);
        restTemplate.patchForObject(
            config.getBaseUrl() + "/claims/" + claimId + "/authorization",
            request,
            Void.class
        );
    }

    public void resubmitClaim(String claimId) {
        // POST /claims/{claimId}/resubmit
        restTemplate.postForObject(
            config.getBaseUrl() + "/claims/" + claimId + "/resubmit",
            null,
            Void.class
        );
    }
}

// Configuração
@Configuration
@ConfigurationProperties(prefix = "tasy.client")
public class TasyClientConfig {
    private String baseUrl;          // http://tasy.hospital.local:8080/api/v1
    private String username;
    private String password;
    private int connectionTimeout;   // ms
    private int readTimeout;         // ms
    // getters/setters
}
```

### 4.2 Integração TISS (Validação)

```java
@Component
public class TissClient {

    public boolean validateProcedureCode(String procedureCode) {
        // Valida contra Tabela TISS de códigos TUSS
        // Usa library TISS ou chamada REST a serviço externo
        // Retorna true se código é válido
    }

    public boolean validateDiagnosisCompatibility(String procedureCode, String diagnosisCode) {
        // Valida compatibilidade entre procedimento (TUSS) e diagnóstico (CID-10)
        // Retorna true se compatível
    }

    public List<String> getCompatibleDiagnosis(String procedureCode) {
        // Retorna lista de CID-10 compatíveis com o procedimento
    }

    public String getDenialCodeDescription(String code) {
        // Retorna descrição textual do código de negação TISS
    }
}
```

### 4.3 Integração Kafka (Event Publishing)

```java
@Component
public class GlosaEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;

    public void publishProvisionCreatedEvent(
        String provisionId,
        String glosaId,
        BigDecimal amount,
        String period
    ) {
        ProvisionCreatedEvent event = ProvisionCreatedEvent.builder()
            .eventType("ProvisionCreated")
            .provisionId(provisionId)
            .glosaId(glosaId)
            .amount(amount)
            .accountingPeriod(period)
            .createdAt(LocalDateTime.now())
            .build();

        try {
            String messageJson = objectMapper.writeValueAsString(event);
            kafkaTemplate.send("financial-provisions", provisionId, messageJson);
        } catch (JsonProcessingException e) {
            log.error("Error serializing event: {}", e.getMessage());
        }
    }

    public void publishCorrectionAppliedEvent(
        String glosaId,
        String correctionType,
        Map<String, Object> details
    ) {
        CorrectionAppliedEvent event = CorrectionAppliedEvent.builder()
            .eventType("CorrectionApplied")
            .glosaId(glosaId)
            .correctionType(correctionType)
            .details(details)
            .appliedAt(LocalDateTime.now())
            .build();

        // Publish to Kafka...
    }
}

// Consumers (listeners)
@Component
public class FinancialProvisionListener {

    @KafkaListener(topics = "financial-provisions", groupId = "finance-group")
    public void handleProvisionCreated(String message) {
        // Receber e processar evento ProvisionCreated
        // ex: enviar email, atualizar dashboard, etc
    }
}
```

### 4.4 Integração com Banco de Dados (JPA Repositories)

```java
@Repository
public interface GlosasRepository extends JpaRepository<Glosa, String> {

    List<Glosa> findByClaimId(String claimId);
    List<Glosa> findByStatus(String status);
    List<Glosa> findByGlosaTypeAndCreatedAtBetween(
        String glosaType,
        LocalDateTime start,
        LocalDateTime end
    );

    @Query("SELECT g FROM Glosa g WHERE g.glosaAmount >= :minAmount " +
           "AND g.status = 'IDENTIFIED'")
    List<Glosa> findHighValueUnanalyedGlosas(@Param("minAmount") BigDecimal minAmount);
}

@Repository
public interface ProvisionsRepository extends JpaRepository<Provision, String> {

    Optional<Provision> findByGlosaId(String glosaId);
    List<Provision> findByAccountingPeriod(String period);

    @Query("SELECT SUM(p.provisionAmount) FROM Provision p " +
           "WHERE p.accountingPeriod = :period")
    BigDecimal getTotalProvisionedAmount(@Param("period") String period);
}

// Serviço que usa repositories
@Service
public class ProvisioningService {

    @Autowired
    private ProvisionsRepository provisionsRepository;

    @Autowired
    private GlosasRepository glosasRepository;

    @Transactional
    public Provision createProvisioning(String glosaId, BigDecimal amount, String period) {
        // Verificar idempotência
        Optional<Provision> existing = provisionsRepository.findByGlosaId(glosaId);
        if (existing.isPresent()) {
            return existing.get();
        }

        // Criar nova provisão
        Provision provision = Provision.builder()
            .provisionId("PROV-" + glosaId + "-" + System.currentTimeMillis())
            .glosa(glosasRepository.findById(glosaId).orElseThrow())
            .provisionAmount(amount)
            .accountingPeriod(period)
            .erpStatus(ERPIntegrationStatus.PENDING)
            .build();

        return provisionsRepository.save(provision);
    }
}
```

---

## PARTE 5: TRATAMENTO DE ERROS E EXCEÇÕES

### 5.1 Hierarquia de Exceções

```java
// Raiz
public class GlosaProcessingException extends RuntimeException {
    private String errorCode;
    private LocalDateTime timestamp;
    public GlosaProcessingException(String errorCode, String message) { ... }
}

// Específicas
public class InvalidDenialCodeException extends GlosaProcessingException {
    public InvalidDenialCodeException(String code) {
        super("INVALID_DENIAL_CODE", "Unknown denial code: " + code);
    }
}

public class CorrectionFailedException extends GlosaProcessingException {
    public CorrectionFailedException(String glosaId, String strategy, Throwable cause) {
        super("CORRECTION_FAILED", "Strategy " + strategy + " failed for " + glosaId);
    }
}

public class TasyIntegrationException extends GlosaProcessingException {
    public TasyIntegrationException(String message, Throwable cause) {
        super("TASY_INTEGRATION_ERROR", message);
    }
}

public class ProvisioningException extends GlosaProcessingException {
    public ProvisioningException(String glosaId, String message) {
        super("PROVISIONING_FAILED", "Provisioning failed for " + glosaId + ": " + message);
    }
}
```

### 5.2 Global Exception Handler (Spring MVC)

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(GlosaProcessingException.class)
    public ResponseEntity<ErrorResponse> handleGlosaException(
        GlosaProcessingException ex
    ) {
        ErrorResponse errorResponse = ErrorResponse.builder()
            .errorCode(ex.getErrorCode())
            .message(ex.getMessage())
            .timestamp(LocalDateTime.now())
            .build();

        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorResponse);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGenericException(Exception ex) {
        ErrorResponse errorResponse = ErrorResponse.builder()
            .errorCode("INTERNAL_ERROR")
            .message("An unexpected error occurred")
            .timestamp(LocalDateTime.now())
            .build();

        log.error("Unhandled exception: {}", ex.getMessage(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorResponse);
    }
}
```

---

## PARTE 6: TESTES E QUALIDADE DE CÓDIGO

### 6.1 Estrutura de Testes

```
src/test/java/com/hospital/revenuecycle/
├─ unit/
│  ├─ delegates/
│  │  ├─ IdentifyGlosaDelegateTest
│  │  ├─ ApplyCorrectionsDelegateTest
│  │  └─ CreateProvisionDelegateTest
│  ├─ service/
│  │  ├─ FinancialProvisionServiceTest
│  │  └─ GlosaCorrectionOrchestratorTest
│  └─ correction/
│     ├─ PriceAdjustmentStrategyTest
│     ├─ DocumentationAttachmentStrategyTest
│     └─ CorrectionStrategyRegistryTest
│
├─ integration/
│  ├─ TasyClientIntegrationTest
│  ├─ KafkaIntegrationTest
│  └─ ProvisioningIntegrationTest
│
├─ bpmn/
│  ├─ GlosaProcessTest
│  └─ AppealsProcessTest
│
└─ fixtures/
   ├─ GlosaTestData
   ├─ ClaimTestData
   └─ MockTasyResponse
```

### 6.2 Exemplo de Teste Unitário

```java
@DisplayName("IdentifyGlosaDelegateTest")
class IdentifyGlosaDelegateTest {

    private IdentifyGlosaDelegate delegate;
    private DelegateExecution execution;

    @BeforeEach
    void setup() {
        delegate = new IdentifyGlosaDelegate();
        execution = mock(DelegateExecution.class);
    }

    @Test
    @DisplayName("Should identify full denial when payment is zero")
    void shouldIdentifyFullDenial() throws Exception {
        // Arrange
        String claimId = "CLM-001";
        BigDecimal expectedAmount = new BigDecimal("5000.00");
        BigDecimal paymentReceived = BigDecimal.ZERO;

        when(execution.getVariable("claimId")).thenReturn(claimId);
        when(execution.getVariable("expectedAmount")).thenReturn(expectedAmount);
        when(execution.getVariable("paymentReceived")).thenReturn(paymentReceived);

        // Act
        delegate.execute(execution);

        // Assert
        verify(execution).setVariable("glosaIdentified", true);
        verify(execution).setVariable("glosaAmount", expectedAmount);
        verify(execution).setVariable("glosaType", "FULL_DENIAL");
    }

    @Test
    @DisplayName("Should classify underpayment when 50-99% paid")
    void shouldClassifyUnderpayment() throws Exception {
        // Arrange
        BigDecimal expectedAmount = new BigDecimal("1000.00");
        BigDecimal paymentReceived = new BigDecimal("750.00");  // 75%

        when(execution.getVariable("claimId")).thenReturn("CLM-002");
        when(execution.getVariable("expectedAmount")).thenReturn(expectedAmount);
        when(execution.getVariable("paymentReceived")).thenReturn(paymentReceived);

        // Act
        delegate.execute(execution);

        // Assert
        ArgumentCaptor<String> typeCaptor = ArgumentCaptor.forClass(String.class);
        verify(execution).setVariable(eq("glosaType"), typeCaptor.capture());
        assertEquals("UNDERPAYMENT", typeCaptor.getValue());
    }

    @Test
    @DisplayName("Should return NO_GLOSA when within tolerance")
    void shouldReturnNoGlosaWithinTolerance() throws Exception {
        // Arrange
        BigDecimal expectedAmount = new BigDecimal("1000.00");
        BigDecimal paymentReceived = new BigDecimal("1009.50");  // 0.95% difference

        when(execution.getVariable("claimId")).thenReturn("CLM-003");
        when(execution.getVariable("expectedAmount")).thenReturn(expectedAmount);
        when(execution.getVariable("paymentReceived")).thenReturn(paymentReceived);

        // Act
        delegate.execute(execution);

        // Assert
        verify(execution).setVariable("glosaIdentified", false);
        verify(execution).setVariable("glosaType", "NO_GLOSA");
    }
}
```

### 6.3 Métricas de Qualidade

```yaml
Requisitos de Cobertura:
  - Cobertura de Linha: ≥ 80%
  - Cobertura de Branch: ≥ 75%
  - Complexidade Ciclomática: ≤ 10 (por método)

Verificações de Qualidade:
  - SonarQube: Nota ≥ A
  - Checkstyle: Sem violações críticas
  - Spotbugs: Sem bugs críticos
  - PMD: Sem problemas de design

Testes:
  - Testes Unitários: JUnit 5 + Mockito
  - Testes de Integração: TestContainers + Spring Test
  - Testes BPMN: Camunda Process Engine Testing
  - Testes API: RestAssured + MockMvc
```

---

## PARTE 7: DEPLOYMENT E CONFIGURAÇÃO

### 7.1 Configuração por Ambiente

```yaml
# application-dev.properties
spring.datasource.url=jdbc:mysql://localhost:3306/glosa_dev
spring.datasource.username=dev
spring.datasource.password=dev123

tasy.client.baseUrl=http://localhost:8080/api/v1
tasy.client.connectionTimeout=5000
tasy.client.readTimeout=10000

kafka.bootstrap.servers=localhost:9092
kafka.topics.financial-provisions=financial-provisions-dev

camunda.bpm.database.schema-update=true

# application-prod.properties
spring.datasource.url=jdbc:mysql://prod-db:3306/glosa
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=5

tasy.client.baseUrl=http://tasy-prod:8080/api/v1
tasy.client.connectionTimeout=3000
tasy.client.readTimeout=15000

kafka.bootstrap.servers=kafka-prod-1:9092,kafka-prod-2:9092,kafka-prod-3:9092
kafka.topics.financial-provisions=financial-provisions

camunda.bpm.database.schema-update=false
```

### 7.2 Dockerfile

```dockerfile
FROM openjdk:11-jre-slim

WORKDIR /app

COPY target/glosa-module-1.0.0.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", \
  "-Dspring.profiles.active=prod", \
  "-Xmx512m", \
  "-XX:+UseG1GC", \
  "-jar", "app.jar"]
```

---

## CONCLUSÃO

A arquitetura técnica do módulo GLOSA é construída sobre princípios sólidos de:

1. **Separação de Responsabilidades**: Delegates para orquestração BPMN, Services para lógica de negócio, Repositories para persistência
2. **Extensibilidade**: Strategy Pattern permite adicionar novos códigos TISS sem modificar código existente
3. **Testabilidade**: Injeção de dependências, mocks e testes unitários abrangentes
4. **Conformidade**: Integração com TISS, ANS e padrões contábeis
5. **Performance**: Operações assíncronas (Kafka, ERP), índices de banco de dados, cache quando apropriado
6. **Auditoria**: Logging completo, eventos Kafka, rastreabilidade de todas operações

---

**Documento Técnico Completo**
Data: 2026-01-24
Próxima Revisão: 2026-04-24
Criticidade: ALTA
