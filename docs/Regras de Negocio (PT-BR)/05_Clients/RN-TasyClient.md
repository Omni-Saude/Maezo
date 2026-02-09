# RN-TasyClient - Cliente de Integração TASY ERP

## 1. Identificação da Regra
- **ID:** RN-TASY-CLIENT-001
- **Nome:** Cliente Feign de Integração com TASY ERP
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 4
- **Categoria:** Integration Layer / External Client
- **Prioridade:** Crítica
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
O TasyClient é o cliente Feign responsável pela comunicação com o sistema ERP TASY, sistema central do hospital que gerencia dados demográficos de pacientes, procedimentos clínicos, atendimentos, prontuários médicos, encontros clínicos e documentação clínica.

### 2.2. Descrição Técnica
Interface Feign declarativa com mapeamento de endpoints REST para integração síncrona com API TASY v1. Utiliza autenticação via API Key no header X-API-Key e configuração via TasyClientConfig.

### 2.3. Origem do Requisito
- **Funcional:** Necessidade de integração com sistema ERP TASY para acesso a dados clínicos, administrativos e financeiros
- **Regulatório:** RN-453 ANS - Acesso a dados de atendimento para faturamento
- **Técnico:** Arquitetura de microsserviços com integração via REST

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Consulta de dados demográficos de pacientes
- **UC-02**: Recuperação de procedimentos realizados
- **UC-03**: Gestão de encontros clínicos (encounters)
- **UC-04**: Acesso a documentação clínica
- **UC-05**: Gerenciamento de guias/autorizações
- **UC-06**: Validação de códigos de procedimento
- **UC-07**: Consulta de preços contratuais
- **UC-08**: Atualização de status de encontros
- **UC-09**: Gerenciamento de provisões financeiras

### 3.2. Processos BPMN Relacionados
- **Process ID:** revenue-cycle-main
  - **Task:** Consultar Dados TASY
  - **Service Task:** TasyDataRetrievalTask
- **Process ID:** billing-validation
  - **Task:** Validar Procedimentos TASY
  - **Service Task:** TasyProcedureValidationTask
- **Process ID:** claim-generation
  - **Task:** Recuperar Guias TASY
  - **Service Task:** TasyClaimRetrievalTask
- **Process ID:** encounter-management
  - **Task:** Atualizar Status Encontro
  - **Service Task:** TasyEncounterStatusUpdateTask

### 3.3. Entidades Afetadas
- **TasyPatientDTO**: Dados demográficos de pacientes
- **TasyProcedureDTO**: Procedimentos realizados
- **TasyClaimDTO**: Guias e autorizações
- **TasyEncounterDTO**: Encontros clínicos
- **TasyDocumentDTO**: Documentos clínicos

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
SE requisição de dados TASY necessária
ENTÃO invocar método apropriado do TasyClient
COM autenticação via API Key
```

### 4.2. Critérios de Validação
1. **API Key válida**: Header X-API-Key deve conter chave válida configurada
2. **ID válido**: Identificadores (patientId, encounterId, claimId) não podem ser nulos/vazios
3. **Timeout**: Requisições não devem exceder timeouts configurados (5s connect, 10s read)
4. **Response válido**: Resposta deve ser deserializável para DTO apropriado

### 4.3. Ações e Consequências
**QUANDO** método TasyClient invocado:
1. **Validar** parâmetros de entrada
2. **Adicionar** header X-API-Key automaticamente
3. **Executar** chamada HTTP síncrona via Feign
4. **Deserializar** resposta JSON para DTO
5. **Retornar** objeto tipado ou lançar TasyApiException

**SE** erro ocorrer:
- **4xx**: Cliente erro (recurso não encontrado, não autorizado)
- **5xx**: Servidor erro (TASY indisponível)
- **Timeout**: Excedido tempo de espera

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio
Não aplicável - cliente de integração sem cálculos de negócio.

### 5.2. Regras de Arredondamento
Valores monetários retornados (BigDecimal) mantêm precisão sem arredondamento no cliente.

### 5.3. Tratamento de Valores Especiais
- **null**: Aceito para campos opcionais conforme DTOs
- **Strings vazias**: Tratadas como valores válidos se permitido pelo DTO
- **Collections vazias**: Retornadas como List vazia, nunca null

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Campos Mapeados
| Campo TASY | Campo TISS | Guia TISS | Obrigatório |
|------------|------------|-----------|-------------|
| cd_paciente | beneficiario.numeroDaCarteira | Todas | Sim |
| cd_procedimento | procedimento.codigoProcedimento | SP-SADT, Consulta | Sim |
| cd_diagnostico | diagnostico.codigoCID | Internação, SP-SADT | Sim |
| vl_total | valorTotal | Todas | Sim |
| cd_convenio | operadora.codigoNaOperadora | Todas | Sim |
| cd_profissional | contratado.codigoProfissional | Todas | Sim |

### 6.3. Guias Aplicáveis
- **Guia SP-SADT**: Serviços Profissionais / SADT
- **Guia de Consulta**: Consultas médicas
- **Guia de Internação**: Hospitalizações
- **Guia de Honorários**: Honorários médicos

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-453/2020**: Estabelece procedimentos para envio de guias
- **RN-473/2021**: Padrões de interoperabilidade
- **RN-506/2022**: Autorizações e guias eletrônicas

### 7.2. Requisitos LGPD
- **Art. 7º**: Base legal para processamento de dados de saúde
- **Art. 9º**: Consentimento para dados sensíveis (saúde)
- **Art. 46**: Segurança no processamento de dados pessoais
- **Anonimização**: Não aplicável - dados identificados necessários para faturamento

### 7.3. Validações Regulatórias
1. **Autenticação**: API Key obrigatória conforme políticas de segurança
2. **Auditoria**: Todas chamadas logadas via Feign Logger.Level.FULL
3. **Timeout**: Resposta obrigatória em até 10 segundos
4. **Retry**: Gerenciado por camada superior (TasyService)

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio
| Código | Exceção | Causa | Ação |
|--------|---------|-------|------|
| TASY-401 | TasyApiException | API Key inválida/expirada | Renovar credenciais |
| TASY-404 | TasyApiException | Recurso não encontrado | Validar ID fornecido |
| TASY-429 | TasyApiException | Rate limit excedido | Implementar backoff |
| TASY-500 | TasyApiException | Erro interno TASY | Retry com circuit breaker |
| TASY-503 | TasyApiException | Serviço indisponível | Fallback ou DLQ |

### 8.2. Erros Técnicos
| Tipo | Descrição | Tratamento |
|------|-----------|------------|
| FeignException.Timeout | Timeout de conexão/leitura | Retry até 3x |
| RetryableException | Erro temporário | Retry exponencial |
| DecodeException | Erro de deserialização | Log e DLQ |
| IOException | Erro de I/O | Circuit breaker |

### 8.3. Estratégias de Recuperação
1. **Retry**: Gerenciado por TasyService com RetryHandler
2. **Circuit Breaker**: Coordenado por CircuitBreakerCoordinator
3. **Cache**: TasyService implementa caching para reduzir chamadas
4. **DLQ**: Mensagens falhas enviadas para Dead Letter Queue

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **TasyService**: Camada de serviço que envolve TasyClient com resiliência
- **TasyClientConfig**: Configuração Feign (timeouts, logging, error decoder)

### 9.2. Dependências Downstream
- **TASY ERP API**: Sistema externo (https://tasy-api.hospital.com/api/v1)
- **TASY DTOs**: TasyPatientDTO, TasyProcedureDTO, TasyClaimDTO, TasyEncounterDTO, TasyDocumentDTO

### 9.3. Eventos Publicados
Não aplicável - cliente síncrono sem publicação de eventos.

### 9.4. Eventos Consumidos
Não aplicável - cliente síncrono sem consumo de eventos.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Tempo de Resposta**: < 10 segundos (configurado em TasyClientConfig)
- **Timeout de Conexão**: 5 segundos
- **Throughput**: Limitado por rate limit do TASY ERP
- **Concorrência**: Thread-safe (Spring Feign gerencia pool de conexões)

### 10.2. Estratégias de Cache
Implementadas em **TasyService**, não no cliente:
- **Patient cache**: 5 minutos TTL
- **Procedures cache**: 15 minutos TTL
- **Cache invalidation**: Explícita via TasyService.invalidatePatientCache()

### 10.3. Otimizações Implementadas
1. **Connection pooling**: Gerenciado por Spring Cloud OpenFeign
2. **Keep-alive**: Conexões persistentes HTTP/1.1
3. **Compression**: Aceito via header Accept-Encoding (se suportado pelo TASY)
4. **Retry inteligente**: Apenas para operações idempotentes (GET)

## 11. Exemplos de Uso

### 11.1. Exemplo Básico
```java
@Autowired
private TasyClient tasyClient;

@Value("${tasy.api-key}")
private String apiKey;

// Consultar paciente
TasyPatientDTO patient = tasyClient.getPatient("12345", apiKey);

// Consultar procedimentos de atendimento
List<TasyProcedureDTO> procedures = tasyClient.getProcedures("ATD-67890", apiKey);

// Obter encontro clínico
TasyEncounterDTO encounter = tasyClient.getEncounter("ENC-11223", apiKey);
```

### 11.2. Exemplo Avançado
```java
// Fluxo completo de gestão de guia
String claimId = "GUIA-99887";

// 1. Obter detalhes da guia
TasyClaimDTO claim = tasyClient.getClaimDetails(claimId);

// 2. Buscar guias similares para análise
List<TasyClaimDTO> similarClaims = tasyClient.searchSimilarClaims(claimId);

// 3. Validar código de procedimento
boolean isValid = tasyClient.validateProcedureCode(claim.getProcedureCode());

// 4. Se inválido, buscar diagnóstico compatível
if (!isValid) {
    String compatibleDiagnosis = tasyClient.getCompatibleDiagnosis(
        claim.getProcedureCode(),
        claim.getDiagnosisCode()
    );

    // 5. Atualizar diagnóstico
    claim = tasyClient.updateClaimDiagnosis(claimId, compatibleDiagnosis);
}

// 6. Verificar cobertura contratual
boolean hasCoverage = tasyClient.verifyContractCoverage(
    claim.getProcedureCode(),
    claim.getPayerId()
);

// 7. Obter preço contratual
BigDecimal contractedPrice = tasyClient.getContractedPrice(
    claim.getProcedureCode(),
    claim.getPayerId()
);

// 8. Atualizar valor da guia
claim = tasyClient.updateClaimAmount(claimId, contractedPrice);

// 9. Anexar documentação adicional
tasyClient.attachDocumentToClaim(
    claimId,
    "LAUDO_MEDICO",
    "/storage/laudos/12345.pdf"
);

// 10. Reenviar guia com evidências
Map<String, Object> evidence = Map.of(
    "clinical_justification", "Procedimento de emergência",
    "supporting_documents", List.of("laudo_12345.pdf")
);
claim = tasyClient.resubmitClaimWithEvidence(claimId, evidence);
```

### 11.3. Exemplo de Caso de Uso Completo
```java
/**
 * UC: Processamento de Encontro Clínico para Faturamento
 */
@Service
@RequiredArgsConstructor
public class EncounterBillingProcessor {

    private final TasyClient tasyClient;

    @Value("${tasy.api-key}")
    private String apiKey;

    public ClaimGenerationResult processEncounter(String encounterId) {
        // 1. Obter dados do encontro
        TasyEncounterDTO encounter = tasyClient.getEncounter(encounterId, apiKey);

        // 2. Obter documentos clínicos
        List<TasyDocumentDTO> documents = tasyClient.getEncounterDocuments(encounterId, apiKey);

        // 3. Obter procedimentos realizados
        List<TasyProcedureDTO> procedures = tasyClient.getProcedures(encounterId, apiKey);

        // 4. Obter dados do paciente
        TasyPatientDTO patient = tasyClient.getPatient(encounter.getPatientId(), apiKey);

        // 5. Para cada procedimento, validar e precificar
        for (TasyProcedureDTO procedure : procedures) {
            // Validar código TUSS
            boolean isValid = tasyClient.validateProcedureCode(procedure.getTussCode());

            if (!isValid) {
                throw new InvalidProcedureCodeException(procedure.getTussCode());
            }

            // Verificar cobertura contratual
            boolean hasCoverage = tasyClient.verifyContractCoverage(
                procedure.getTussCode(),
                patient.getInsuranceId()
            );

            if (!hasCoverage) {
                throw new NoCoverageException(procedure.getTussCode(), patient.getInsuranceId());
            }

            // Obter preço contratual
            BigDecimal price = tasyClient.getContractedPrice(
                procedure.getTussCode(),
                patient.getInsuranceId()
            );

            // Criar provisão financeira
            Map<String, Object> provisionData = Map.of(
                "encounterId", encounterId,
                "procedureCode", procedure.getTussCode(),
                "amount", price,
                "payerId", patient.getInsuranceId()
            );

            String provisionId = tasyClient.createProvision(provisionData);
        }

        // 6. Atualizar status do encontro para fechamento
        tasyClient.updateEncounterStatus(encounterId, "PENDING_CLOSURE", apiKey);

        return ClaimGenerationResult.success(encounterId, procedures.size());
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário
```java
@ExtendWith(MockitoExtension.class)
class TasyClientTest {

    @Mock
    private TasyClient tasyClient;

    private String apiKey = "test-api-key";

    @Test
    void testGetPatient_Success() {
        // Arrange
        String patientId = "12345";
        TasyPatientDTO expected = TasyPatientDTO.builder()
            .patientId(patientId)
            .name("João Silva")
            .cpf("123.456.789-00")
            .build();

        when(tasyClient.getPatient(patientId, apiKey)).thenReturn(expected);

        // Act
        TasyPatientDTO result = tasyClient.getPatient(patientId, apiKey);

        // Assert
        assertNotNull(result);
        assertEquals(patientId, result.getPatientId());
        assertEquals("João Silva", result.getName());
    }

    @Test
    void testValidateProcedureCode_Valid() {
        // Arrange
        String validCode = "40101010";
        when(tasyClient.validateProcedureCode(validCode)).thenReturn(true);

        // Act
        boolean result = tasyClient.validateProcedureCode(validCode);

        // Assert
        assertTrue(result);
    }

    @Test
    void testGetContractedPrice_ReturnsCorrectPrice() {
        // Arrange
        String procedureCode = "40101010";
        String payerId = "CONV-123";
        BigDecimal expectedPrice = new BigDecimal("150.00");

        when(tasyClient.getContractedPrice(procedureCode, payerId))
            .thenReturn(expectedPrice);

        // Act
        BigDecimal result = tasyClient.getContractedPrice(procedureCode, payerId);

        // Assert
        assertEquals(0, expectedPrice.compareTo(result));
    }
}
```

### 12.2. Cenários de Teste de Integração
```java
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class TasyClientIntegrationTest {

    @Autowired
    private TasyClient tasyClient;

    @Value("${tasy.api-key}")
    private String apiKey;

    @Test
    void testGetPatient_Integration() {
        // Arrange: Mock TASY API response
        stubFor(get(urlEqualTo("/pacientes/12345"))
            .withHeader("X-API-Key", equalTo(apiKey))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("{ \"cd_paciente\": \"12345\", \"nm_paciente\": \"João Silva\" }")));

        // Act
        TasyPatientDTO patient = tasyClient.getPatient("12345", apiKey);

        // Assert
        assertNotNull(patient);
        assertEquals("12345", patient.getPatientId());
    }

    @Test
    void testGetPatient_NotFound() {
        // Arrange: Mock 404 response
        stubFor(get(urlEqualTo("/pacientes/99999"))
            .withHeader("X-API-Key", equalTo(apiKey))
            .willReturn(aResponse()
                .withStatus(404)));

        // Act & Assert
        assertThrows(TasyApiException.class, () -> {
            tasyClient.getPatient("99999", apiKey);
        });
    }
}
```

### 12.3. Massa de Dados para Teste
```json
{
  "valid_patient": {
    "cd_paciente": "12345",
    "nm_paciente": "João Silva",
    "nr_cpf": "12345678900",
    "dt_nascimento": "1980-01-15",
    "cd_convenio": "CONV-123",
    "nm_convenio": "Unimed"
  },
  "valid_procedure": {
    "cd_procedimento": "PROC-001",
    "cd_tuss": "40101010",
    "ds_procedimento": "Consulta médica",
    "vl_unitario": 150.00,
    "qt_procedimento": 1
  },
  "valid_claim": {
    "cd_guia": "GUIA-12345",
    "cd_atendimento": "ATD-67890",
    "cd_paciente": "12345",
    "cd_convenio": "CONV-123",
    "tp_guia": "CONSULTA",
    "ie_status": "ENVIADA",
    "vl_total": 150.00
  }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **Autenticação**: API Key obrigatória via header X-API-Key
- **Autorização**: Gerenciada pelo TASY ERP (não pelo cliente)
- **Criptografia**: HTTPS obrigatório (configurado via base URL https://)

### 13.2. Proteção de Dados
- **Dados em Trânsito**: TLS 1.2+ obrigatório
- **Dados Sensíveis**: Não armazenados pelo cliente (apenas trafegados)
- **Logging**: API Key mascarada em logs (responsabilidade do Feign Logger)

### 13.3. Auditoria
- **Todas as chamadas** são logadas com nível FULL via Feign Logger
- **Request ID**: Gerado automaticamente pelo Feign
- **Timestamps**: Registrados para cada operação
- **User tracking**: Rastreado via contexto de segurança Spring

## 14. Referências

### 14.1. Documentação Relacionada
- `TasyService.java` - Camada de serviço com resiliência
- `TasyClientConfig.java` - Configuração Feign
- `TasyWebClient.java` - Cliente WebClient alternativo (reativo)
- `TASYCodingClient.java` - Cliente para API de codificação médica
- DTOs: `TasyPatientDTO`, `TasyProcedureDTO`, `TasyClaimDTO`, `TasyEncounterDTO`, `TasyDocumentDTO`

### 14.2. Links Externos
- [Spring Cloud OpenFeign](https://spring.io/projects/spring-cloud-openfeign)
- [Feign Documentation](https://github.com/OpenFeign/feign)
- [TASY ERP - Philips](https://www.philips.com.br/healthcare/solutions/tasy)

### 14.3. Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:7f3c8e2a9b1d4f6e8c7a5d3b9f1e4c8a2d6b7f3e9c5a1d8b4f7e3c9a6d2b8f5e`
**Última Atualização:** 2026-01-12T13:06:00Z
**Próxima Revisão:** 2026-04-12
