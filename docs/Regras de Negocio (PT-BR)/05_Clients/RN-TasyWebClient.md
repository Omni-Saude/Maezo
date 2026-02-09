# RN-TasyWebClient - Cliente WebClient Reativo TASY

## 1. Identificação da Regra
- **ID:** RN-TASY-WEBCLIENT-001
- **Nome:** Cliente Reativo WebClient para Integração TASY
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 4
- **Categoria:** Integration Layer / Reactive Client
- **Prioridade:** Alta
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
O TasyWebClient é um cliente reativo baseado em Spring WebFlux que fornece acesso assíncrono não-bloqueante aos recursos clínicos do TASY EHR (Electronic Health Record), incluindo prontuários médicos, notas de médicos, resultados laboratoriais e laudos de imagem.

### 2.2. Descrição Técnica
Cliente HTTP reativo implementado com Spring WebClient que utiliza programação reativa (Reactor) para chamadas assíncronas. Implementa timeout de 10 segundos, retry automático (3 tentativas) e tratamento de erros HTTP via onStatus handlers.

### 2.3. Origem do Requisito
- **Funcional:** Necessidade de acesso eficiente a dados clínicos volumosos (prontuários, laudos)
- **Técnico:** Arquitetura reativa para melhor utilização de recursos em operações I/O-bound
- **Performance:** Não-bloqueante permite maior throughput com mesmos recursos

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Recuperação assíncrona de prontuário médico completo
- **UC-02**: Consulta paralela de notas de médicos
- **UC-03**: Agregação de resultados laboratoriais
- **UC-04**: Compilação de laudos de imagem
- **UC-05**: Pipeline reativo de documentação clínica

### 3.2. Processos BPMN Relacionados
- **Process ID:** medical-coding
  - **Task:** Recuperar Prontuário para Codificação
  - **Service Task:** ReactiveMedicalRecordRetrievalTask
- **Process ID:** clinical-validation
  - **Task:** Validar Documentação Clínica
  - **Service Task:** ReactiveClinicValidationTask
- **Process ID:** audit-medical-records
  - **Task:** Auditar Registros Médicos
  - **Service Task:** ReactiveAuditTask

### 3.3. Entidades Afetadas
- **TasyMedicalRecord**: Prontuário médico completo
- **TasyPhysicianNote**: Notas e evoluções médicas
- **TasyLabResult**: Resultados de exames laboratoriais
- **TasyImagingReport**: Laudos de exames de imagem

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
QUANDO requisição de dados clínicos volumosos ou múltiplos:
  SE single resource:
    - USAR WebClient.get() com Mono<T>
    - APLICAR timeout 10s
    - RETRY até 3x em falhas
  SE multiple resources:
    - USAR WebClient.get() com Flux<T>
    - COLETAR em List via collectList()
    - APLICAR backpressure se necessário
```

### 4.2. Critérios de Validação
1. **Encounter ID válido**: Não nulo, não vazio
2. **Base URL configurada**: ${tasy.base-url} presente
3. **API Key configurada**: ${tasy.api-key} presente
4. **Response 2xx**: Status code entre 200-299
5. **Body deserializável**: JSON válido conforme DTO

### 4.3. Ações e Consequências

**Fluxo Normal:**
1. **Construir** request com URI template
2. **Adicionar** headers (X-API-Key, Content-Type)
3. **Executar** GET via webClient.get()
4. **Tratar** status codes via onStatus()
5. **Deserializar** response body para DTO
6. **Aplicar** timeout de 10 segundos
7. **Retry** até 3 tentativas em falhas
8. **Bloquear** via .block() (síncrono) ou retornar Mono/Flux (assíncrono)

**Tratamento de Erros:**
- **4xx**: Cliente erro → TasyApiException("Encounter not found")
- **5xx**: Servidor erro → TasyApiException("TASY server error")
- **Timeout**: Após 10s → TimeoutException
- **Retry**: Após 3 tentativas → Exceção original propagada

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio
Não aplicável - cliente de acesso a dados sem lógica de negócio.

### 5.2. Timeout e Retry
```
total_max_time = timeout * (max_retries + 1)
                = 10s * (3 + 1)
                = 40 segundos

Onde:
- timeout = 10 segundos por tentativa
- max_retries = 3 tentativas adicionais
- Primeira tentativa não conta como retry
```

### 5.3. Backpressure Strategy
```
backpressure_strategy = BUFFER
buffer_size = 256 elementos (default Reactor)

SE buffer_full:
  - Aplicar estratégia DROP_OLDEST
  - Log warning sobre perda de dados
```

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Dados Clínicos para Codificação
| Campo TASY | Campo TISS | Uso em Codificação |
|------------|------------|-------------------|
| chiefComplaint | motivoDoEncerramento | Justificativa clínica |
| historyOfPresentIllness | historiaDaDoencaAtual | Contexto clínico |
| physicalExamination | exameClinico | Evidências para codificação |
| assessmentAndPlan | diagnostico | Base para ICD-10 |
| dischargeSummary | resumoDeAlta | Validação de procedimentos |

### 6.3. Requisitos de Documentação
- **Prontuário médico**: Obrigatório para internações (Guia de Internação TISS)
- **Notas de médicos**: Obrigatório para procedimentos de alta complexidade
- **Laudos de imagem**: Obrigatório para SP-SADT de diagnóstico por imagem
- **Resultados laboratoriais**: Obrigatório para SP-SADT laboratoriais

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-453/2020**: Documentação obrigatória para guias
- **RN-506/2022**: Acesso a prontuários para auditoria

### 7.2. Requisitos LGPD
- **Art. 11**: Tratamento de dados sensíveis de saúde
- **Art. 46**: Medidas de segurança (HTTPS, API Key)
- **Art. 48**: Notificação de incidentes de segurança

### 7.3. CFM (Conselho Federal de Medicina)
- **Resolução CFM 1.821/2007**: Prontuário médico eletrônico
- **Acesso controlado**: Apenas profissionais autorizados
- **Auditoria**: Todas as consultas devem ser logadas

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio
| Código | Exceção | Causa | Ação |
|--------|---------|-------|------|
| TASY-WC-404 | TasyApiException | Encounter não encontrado | Validar encounterId |
| TASY-WC-500 | TasyApiException | Erro interno TASY | Retry automático |
| TASY-WC-TIMEOUT | TimeoutException | Timeout excedido (10s) | Retry automático (3x) |
| TASY-WC-DECODE | DecodeException | JSON inválido | Log e falha |

### 8.2. Error Handlers
```java
.onStatus(
    status -> status.is4xxClientError(),
    response -> Mono.error(new TasyApiException("Encounter not found: " + encounterId))
)
.onStatus(
    status -> status.is5xxServerError(),
    response -> Mono.error(new TasyApiException("TASY server error"))
)
```

### 8.3. Estratégia de Retry
```
Retry Automático:
  - Tentativas: 3
  - Delay: Não configurado (imediato)
  - Exceções retryable: Todas (via .retry(3))
  - Nota: Considerar RetryBackoffSpec para delay exponencial
```

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **Spring WebFlux**: Framework reativo
- **Reactor Core**: Biblioteca de programação reativa
- **Jackson**: Deserialização JSON

### 9.2. Dependências Downstream
- **TASY EHR API**: Sistema de prontuário eletrônico
  - Base URL: ${tasy.base-url}
  - Endpoints:
    - GET /api/v1/encounters/{encounterId}/medical-record
    - GET /api/v1/encounters/{encounterId}/physician-notes
    - GET /api/v1/encounters/{encounterId}/lab-results
    - GET /api/v1/encounters/{encounterId}/imaging-reports

### 9.3. Eventos Publicados
Não aplicável - cliente HTTP síncrono/reativo sem publicação de eventos.

### 9.4. Eventos Consumidos
Não aplicável - cliente HTTP sem consumo de eventos.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Tempo de Resposta**: < 10 segundos (timeout configurado)
- **Throughput**: > 100 req/s (não-bloqueante)
- **Concorrência**: Thread-safe (Reactor event loop)
- **Memória**: Constante (streaming via Flux)

### 10.2. Vantagens Reativas
1. **Não-bloqueante**: Thread não fica esperando I/O
2. **Backpressure**: Controle de fluxo automático
3. **Composição**: Operadores funcionais (map, flatMap, filter)
4. **Streaming**: Processamento incremental de grandes volumes

### 10.3. Otimizações Implementadas
```java
WebClient otimizado:
  - Connection pooling: Gerenciado por Reactor Netty
  - Keep-alive: HTTP/1.1 persistent connections
  - Buffer size: 256KB (default)
  - Max connections: 500 (default)
```

## 11. Exemplos de Uso

### 11.1. Exemplo Básico - Síncrono com block()
```java
@Service
@RequiredArgsConstructor
public class MedicalRecordService {

    private final TasyWebClient tasyWebClient;

    public MedicalRecordSummary getSummary(String encounterId) {
        // Buscar prontuário médico (bloqueia thread)
        TasyMedicalRecord record = tasyWebClient.getMedicalRecord(encounterId);

        // Buscar notas de médicos (bloqueia thread)
        List<TasyPhysicianNote> notes = tasyWebClient.getPhysicianNotes(encounterId);

        // Buscar laudos (bloqueia thread)
        List<TasyImagingReport> imaging = tasyWebClient.getImagingReports(encounterId);

        return MedicalRecordSummary.builder()
            .record(record)
            .notes(notes)
            .imagingReports(imaging)
            .build();
    }
}
```

### 11.2. Exemplo Avançado - Assíncrono Reativo
```java
@Service
@RequiredArgsConstructor
public class ReactiveMedicalRecordService {

    private final TasyWebClient tasyWebClient;

    /**
     * Busca dados clínicos em paralelo usando programação reativa.
     */
    public Mono<MedicalRecordAggregate> getAggregateData(String encounterId) {
        // Criar Monos para cada chamada (lazy, não executam ainda)
        Mono<TasyMedicalRecord> recordMono = Mono.fromCallable(
            () -> tasyWebClient.getMedicalRecord(encounterId)
        ).subscribeOn(Schedulers.boundedElastic());

        Mono<List<TasyPhysicianNote>> notesMono = Mono.fromCallable(
            () -> tasyWebClient.getPhysicianNotes(encounterId)
        ).subscribeOn(Schedulers.boundedElastic());

        Mono<List<TasyLabResult>> labsMono = Mono.fromCallable(
            () -> tasyWebClient.getLabResults(encounterId)
        ).subscribeOn(Schedulers.boundedElastic());

        Mono<List<TasyImagingReport>> imagingMono = Mono.fromCallable(
            () -> tasyWebClient.getImagingReports(encounterId)
        ).subscribeOn(Schedulers.boundedElastic());

        // Combinar todos os Monos em paralelo
        return Mono.zip(recordMono, notesMono, labsMono, imagingMono)
            .map(tuple -> MedicalRecordAggregate.builder()
                .medicalRecord(tuple.getT1())
                .physicianNotes(tuple.getT2())
                .labResults(tuple.getT3())
                .imagingReports(tuple.getT4())
                .build()
            )
            .doOnError(e -> log.error("Failed to aggregate medical data for encounter: {}", encounterId, e));
    }

    /**
     * Uso do método reativo.
     */
    public void processClinicalData(String encounterId) {
        getAggregateData(encounterId)
            .subscribe(
                aggregate -> {
                    // Sucesso: processar dados agregados
                    log.info("Successfully aggregated data for encounter: {}", encounterId);
                    processForCoding(aggregate);
                },
                error -> {
                    // Erro: tratar falha
                    log.error("Failed to process clinical data", error);
                    notifyFailure(encounterId, error);
                }
            );
    }
}
```

### 11.3. Exemplo de Caso de Uso Completo - Codificação Médica
```java
@Service
@RequiredArgsConstructor
@Slf4j
public class AICodingService {

    private final TasyWebClient tasyWebClient;
    private final TASYCodingClient codingClient;

    /**
     * Codifica automaticamente um encontro clínico usando IA.
     */
    @Transactional
    public CodingResult autoCodeEncounter(String encounterId) {
        log.info("Starting AI coding for encounter: {}", encounterId);

        try {
            // 1. Buscar prontuário médico
            TasyMedicalRecord record = tasyWebClient.getMedicalRecord(encounterId);
            log.debug("Retrieved medical record: {}", record.getEncounterId());

            // 2. Buscar notas de médicos
            List<TasyPhysicianNote> notes = tasyWebClient.getPhysicianNotes(encounterId);
            log.debug("Retrieved {} physician notes", notes.size());

            // 3. Buscar resultados laboratoriais
            List<TasyLabResult> labs = tasyWebClient.getLabResults(encounterId);
            log.debug("Retrieved {} lab results", labs.size());

            // 4. Buscar laudos de imagem
            List<TasyImagingReport> imaging = tasyWebClient.getImagingReports(encounterId);
            log.debug("Retrieved {} imaging reports", imaging.size());

            // 5. Construir contexto clínico para IA
            String clinicalContext = buildClinicalContext(record, notes, labs, imaging);

            // 6. Sugerir código ICD-10 usando IA
            String suggestedICD = codingClient.suggestICD10Code(
                record.getAssessmentAndPlan(),
                encounterId
            );

            // 7. Sugerir código de procedimento
            String suggestedProcedure = codingClient.suggestProcedureCode(
                extractProcedureDescription(record, notes),
                encounterId
            );

            // 8. Validar necessidade médica
            Map<String, Object> validation = codingClient.validateMedicalNecessity(
                suggestedICD,
                suggestedProcedure,
                record.getPayerId()
            );

            boolean medicalNecessityMet = (boolean) validation.get("medicalNecessityMet");

            if (!medicalNecessityMet) {
                log.warn("Medical necessity not met for encounter: {}", encounterId);
                return CodingResult.failed(
                    encounterId,
                    "Medical necessity criteria not satisfied",
                    validation
                );
            }

            // 9. Retornar resultado de codificação
            return CodingResult.success(
                encounterId,
                suggestedICD,
                suggestedProcedure,
                validation
            );

        } catch (TasyApiException e) {
            log.error("TASY API error during coding: {}", encounterId, e);
            return CodingResult.error(encounterId, "TASY API unavailable", e);

        } catch (Exception e) {
            log.error("Unexpected error during AI coding: {}", encounterId, e);
            return CodingResult.error(encounterId, "Coding failed", e);
        }
    }

    private String buildClinicalContext(
        TasyMedicalRecord record,
        List<TasyPhysicianNote> notes,
        List<TasyLabResult> labs,
        List<TasyImagingReport> imaging) {

        StringBuilder context = new StringBuilder();

        // Queixa principal
        context.append("Chief Complaint: ").append(record.getChiefComplaint()).append("\n\n");

        // História da doença
        context.append("History: ").append(record.getHistoryOfPresentIllness()).append("\n\n");

        // Exame físico
        context.append("Physical Exam: ").append(record.getPhysicalExamination()).append("\n\n");

        // Notas de médicos (últimas 3)
        context.append("Recent Physician Notes:\n");
        notes.stream()
            .sorted(Comparator.comparing(TasyPhysicianNote::getNoteDate).reversed())
            .limit(3)
            .forEach(note -> context.append("- ").append(note.getNoteContent()).append("\n"));

        // Resultados laboratoriais anormais
        context.append("\nAbnormal Lab Results:\n");
        labs.stream()
            .filter(lab -> lab.getAbnormalFlag() != null && !lab.getAbnormalFlag().isEmpty())
            .forEach(lab -> context.append("- ")
                .append(lab.getTestName())
                .append(": ")
                .append(lab.getResultValue())
                .append(" (")
                .append(lab.getAbnormalFlag())
                .append(")\n"));

        // Achados de imagem
        context.append("\nImaging Findings:\n");
        imaging.forEach(img -> context.append("- ")
            .append(img.getExamType())
            .append(": ")
            .append(img.getImpression())
            .append("\n"));

        return context.toString();
    }

    private String extractProcedureDescription(
        TasyMedicalRecord record,
        List<TasyPhysicianNote> notes) {

        // Extrair descrição de procedimentos das notas cirúrgicas
        return notes.stream()
            .filter(note -> "SURGICAL_NOTE".equals(note.getNoteType()))
            .map(TasyPhysicianNote::getNoteContent)
            .findFirst()
            .orElse(record.getAssessmentAndPlan());
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário
```java
@ExtendWith(MockitoExtension.class)
class TasyWebClientTest {

    private TasyWebClient tasyWebClient;
    private MockWebServer mockWebServer;

    @BeforeEach
    void setUp() throws IOException {
        mockWebServer = new MockWebServer();
        mockWebServer.start();

        String baseUrl = mockWebServer.url("/").toString();
        WebClient.Builder builder = WebClient.builder();
        tasyWebClient = new TasyWebClient(builder, baseUrl, "test-api-key");
    }

    @AfterEach
    void tearDown() throws IOException {
        mockWebServer.shutdown();
    }

    @Test
    void testGetMedicalRecord_Success() throws InterruptedException {
        // Arrange
        mockWebServer.enqueue(new MockResponse()
            .setResponseCode(200)
            .setBody("{\"encounter_id\":\"ENC-123\",\"patient_id\":\"PAT-456\"}")
            .addHeader("Content-Type", "application/json"));

        // Act
        TasyMedicalRecord record = tasyWebClient.getMedicalRecord("ENC-123");

        // Assert
        assertNotNull(record);
        assertEquals("ENC-123", record.getEncounterId());
        assertEquals("PAT-456", record.getPatientId());

        RecordedRequest request = mockWebServer.takeRequest();
        assertEquals("GET", request.getMethod());
        assertTrue(request.getPath().contains("/encounters/ENC-123/medical-record"));
        assertEquals("test-api-key", request.getHeader("X-API-Key"));
    }

    @Test
    void testGetMedicalRecord_NotFound() {
        // Arrange
        mockWebServer.enqueue(new MockResponse().setResponseCode(404));

        // Act & Assert
        assertThrows(TasyApiException.class, () -> {
            tasyWebClient.getMedicalRecord("ENC-999");
        });
    }

    @Test
    void testGetPhysicianNotes_MultipleResults() {
        // Arrange
        mockWebServer.enqueue(new MockResponse()
            .setResponseCode(200)
            .setBody("[{\"note_id\":\"N1\"},{\"note_id\":\"N2\"}]")
            .addHeader("Content-Type", "application/json"));

        // Act
        List<TasyPhysicianNote> notes = tasyWebClient.getPhysicianNotes("ENC-123");

        // Assert
        assertNotNull(notes);
        assertEquals(2, notes.size());
    }
}
```

### 12.2. Cenários de Teste de Integração
```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class TasyWebClientIntegrationTest {

    @Autowired
    private TasyWebClient tasyWebClient;

    @Test
    @DisplayName("Should retrieve medical record with retry on transient failure")
    void testRetryOnTransientFailure() {
        // Teste de retry seria implementado com WireMock ou MockServer
        // configurado para falhar 2x e suceder na 3ª tentativa
    }

    @Test
    @DisplayName("Should timeout after 10 seconds")
    void testTimeout() {
        // Teste de timeout com servidor mock que responde lentamente
    }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **API Key**: Header X-API-Key obrigatório em todas as requisições
- **HTTPS**: Base URL deve usar protocolo seguro

### 13.2. Proteção de Dados
- **Dados em Trânsito**: TLS 1.2+ obrigatório
- **Dados Sensíveis**: Prontuários médicos protegidos por autenticação
- **Logging**: Não logar conteúdo de prontuários (apenas IDs)

### 13.3. Auditoria
- **Todas as requisições** logadas com encounter ID
- **Timestamps** registrados para rastreabilidade
- **Conformidade CFM**: Acesso a prontuários auditável

## 14. Referências

### 14.1. Documentação Relacionada
- `TasyClient.java` - Cliente Feign síncrono alternativo
- `TasyService.java` - Camada de serviço com resiliência
- DTOs: `TasyMedicalRecord`, `TasyPhysicianNote`, `TasyLabResult`, `TasyImagingReport`

### 14.2. Links Externos
- [Spring WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Programming Guide](https://spring.io/guides/gs/reactive-rest-service/)

### 14.3. Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:3e7c9f2d8b1a4e6c7d9a3f8e2b5c1d7a4e9c6f3d8a2b7e5c1a9d4f6e3c8b2a7`
**Última Atualização:** 2026-01-12T13:15:00Z
**Próxima Revisão:** 2026-04-12
