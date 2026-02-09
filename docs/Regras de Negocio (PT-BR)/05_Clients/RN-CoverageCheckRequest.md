# RN-CoverageCheckRequest - DTO de Requisição de Verificação de Cobertura

## 1. Identificação da Regra
- **ID:** RN-COVERAGE-REQUEST-001
- **Nome:** Data Transfer Object para Requisição de Verificação de Cobertura de Procedimentos
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 7
- **Categoria:** Integration Layer / DTO
- **Prioridade:** Alta
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
DTO utilizado para requisitar verificação de cobertura de procedimentos médicos (códigos TUSS) junto às operadoras de saúde. Permite verificar se procedimentos estão cobertos pelo plano, se requerem autorização prévia, valores de co-participação, e limites de frequência.

### 2.2. Descrição Técnica
Classe imutável com Lombok annotations (`@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`). Serializada para JSON e enviada como body em requisições POST /v1/coverage/check do InsuranceApiClient.

### 2.3. Origem do Requisito
- **Funcional:** Validação de cobertura antes de realizar procedimentos (evitar glosas)
- **Regulatório:** RN-259/2011 ANS - Verificação de cobertura obrigatória do Rol ANS
- **Técnico:** Comunicação REST com APIs de operadoras

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Verificação de Cobertura de Procedimentos TUSS
- **UC-02**: Consulta de Necessidade de Autorização Prévia
- **UC-03**: Validação de Limites de Frequência de Procedimentos
- **UC-04**: Consulta de Valores de Co-participação por Procedimento

### 3.2. Processos BPMN Relacionados
- **Process ID:** pre-authorization
  - **Task:** Consultar Cobertura de Procedimentos
  - **Service Task:** CheckCoverageTask (camundaDelegate: CoverageVerificationDelegate)
- **Process ID:** claim-validation
  - **Task:** Validar Cobertura Antes de Faturamento

### 3.3. Entidades Afetadas
- **CoverageCheckResponse**: Response correspondente com detalhes de cobertura
- **ProcedureCoverage**: Detalhes de cobertura por procedimento individual

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
SE procedimento será realizado
E necessidade de verificar cobertura
ENTÃO construir CoverageCheckRequest
COM patientId, payerId, procedureCodes, serviceDate obrigatórios
```

### 4.2. Critérios de Validação

**Campos Obrigatórios:**
1. **patientId**: Identificador único do paciente (não nulo, não vazio)
2. **payerId**: Identificador da operadora (registro ANS)
3. **procedureCodes**: Lista de códigos TUSS (min: 1, max: 50 procedimentos por request)
4. **serviceDate**: Data prevista do procedimento (não pode ser no passado)

**Campos Opcionais:**
5. **providerNpi**: Código NPI do prestador (recomendado para network status)
6. **placeOfService**: Local do serviço ("Inpatient", "Outpatient", "Emergency")

### 4.3. Ações e Consequências

**QUANDO** CoverageCheckRequest construído:
1. **Validar** patientId não nulo
2. **Validar** payerId não nulo
3. **Validar** procedureCodes lista não vazia
4. **Validar** serviceDate não no passado (> LocalDate.now() - 1 dia)
5. **Serializar** para JSON
6. **Enviar** via InsuranceApiClient.checkCoverage()

**SE** validação falhar:
- Lançar **IllegalArgumentException** com detalhes dos campos inválidos

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio
Não aplicável - DTO não realiza cálculos.

### 5.2. Regras de Arredondamento
Não aplicável.

### 5.3. Tratamento de Valores Especiais
- **procedureCodes vazio**: Lançar exceção - lista deve ter ao menos 1 código
- **serviceDate null**: Assumir data atual (LocalDate.now())
- **providerNpi null**: Operadora pode retornar cobertura genérica (in-network não especificado)
- **placeOfService null**: Assumir "Outpatient" como default

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Campos Mapeados

| Campo DTO | Campo TISS | Tipo | Descrição |
|-----------|------------|------|-----------|
| patientId | beneficiario.numeroDaCarteira | String | Número da carteirinha do beneficiário |
| payerId | operadora.registroANS | String | Registro ANS da operadora (6 dígitos) |
| procedureCodes | procedimento.codigoProcedimento | List<String> | Códigos TUSS dos procedimentos (formato: 8 dígitos) |
| serviceDate | dataExecucao | LocalDate | Data prevista de execução do procedimento |
| providerNpi | contratado.codigoPrestador | String | Código do prestador na operadora |
| placeOfService | tipoAtendimento | String | Tipo de atendimento (Ambulatorial, Hospitalar, Emergência) |

### 6.3. Códigos TUSS Válidos
Procedimentos devem seguir tabela TUSS 4.03.03:
- **Consultas**: 10101012 - 10103093
- **Exames Laboratoriais**: 40301010 - 40316289
- **Exames de Imagem**: 40801004 - 40901300
- **Procedimentos Cirúrgicos**: 30701018 - 31505179
- **Diárias Hospitalares**: 80000007 - 80000120

### 6.4. Mapeamento Place of Service

| Valor DTO | Código TISS | Descrição |
|-----------|-------------|-----------|
| Inpatient | 01 | Internação hospitalar |
| Outpatient | 03 | Atendimento ambulatorial |
| Emergency | 05 | Atendimento de emergência |

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-259/2011**: Cobertura obrigatória do Rol de Procedimentos ANS
  - Procedimentos do Rol devem ter cobertura confirmada
- **RN-469/2021**: Padrão TISS para identificação de procedimentos
  - Códigos TUSS devem seguir tabela oficial atualizada

### 7.2. Requisitos LGPD
- **Art. 7º, I**: Processamento para execução de contrato (verificação de cobertura)
- **Art. 9º**: Dados de saúde (procedimentos) requerem consentimento específico
- **Art. 46**: Dados trafegados via TLS 1.2+

### 7.3. Validações Regulatórias
1. **Procedimentos Rol ANS**: Operadora não pode negar cobertura
2. **Autorização Prévia**: Obrigatória para procedimentos de alta complexidade (Lista ANS)
3. **Prazo de Resposta**: Operadora deve responder em até 10 segundos

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio

| Validação | Exceção | Mensagem |
|-----------|---------|----------|
| patientId null | IllegalArgumentException | "patientId é obrigatório" |
| payerId null | IllegalArgumentException | "payerId é obrigatório" |
| procedureCodes vazio | IllegalArgumentException | "procedureCodes deve conter ao menos 1 código" |
| serviceDate no passado | IllegalArgumentException | "serviceDate não pode ser no passado" |
| procedureCode inválido | IllegalArgumentException | "Código TUSS inválido: {code}" |

### 8.2. Erros Técnicos
- **Serialização JSON**: Se falhar, lançar RuntimeException

### 8.3. Estratégias de Recuperação
1. **Validação pré-envio**: Validar campos antes de construir request
2. **Builder pattern**: Garantir que campos obrigatórios são fornecidos
3. **Defensive copying**: Lista procedureCodes deve ser imutável

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **CoverageVerificationDelegate**: Constrói CoverageCheckRequest a partir de variáveis Camunda
- **PatientService**: Fornece patientId e payerId
- **ProcedureService**: Fornece lista de procedureCodes TUSS

### 9.2. Dependências Downstream
- **InsuranceApiClient**: Recebe CoverageCheckRequest como parâmetro
- **CoverageCheckResponse**: DTO de resposta correspondente

### 9.3. Eventos Publicados
Não aplicável - DTO não publica eventos.

### 9.4. Eventos Consumidos
Não aplicável - DTO não consome eventos.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Serialização JSON**: < 10ms para requests com até 50 procedimentos
- **Tamanho do Request**: < 5KB para permitir transmissão eficiente

### 10.2. Estratégias de Cache
Não aplicável - DTO é stateless e não cacheable.

### 10.3. Otimizações Implementadas
1. **Batch Requests**: Aceitar até 50 procedureCodes em uma única requisição
2. **Lazy Initialization**: Lombok @Builder não cria objetos desnecessários
3. **Immutability**: @Data garante thread-safety

## 11. Exemplos de Uso

### 11.1. Exemplo Básico - Verificação de 1 Procedimento

```java
CoverageCheckRequest request = CoverageCheckRequest.builder()
    .patientId("PAT-12345")
    .payerId("UNIMED-SP-123456")
    .procedureCodes(List.of("10101012")) // Consulta médica
    .serviceDate(LocalDate.now().plusDays(3))
    .providerNpi("1234567890")
    .placeOfService("Outpatient")
    .build();

CoverageCheckResponse response = insuranceApiClient.checkCoverage(request);
```

### 11.2. Exemplo Avançado - Verificação de Múltiplos Procedimentos

```java
// Procedimentos de exames pré-operatórios
List<String> preOpProcedures = List.of(
    "40301010", // Hemograma completo
    "40302156", // Glicemia
    "40318001", // Ureia
    "40318010", // Creatinina
    "40318150", // Sódio
    "40318168", // Potássio
    "40801004", // Raio-X de tórax
    "40601013"  // Eletrocardiograma
);

CoverageCheckRequest request = CoverageCheckRequest.builder()
    .patientId("PAT-67890")
    .payerId("BRADESCO-456789")
    .procedureCodes(preOpProcedures)
    .serviceDate(LocalDate.of(2026, 1, 15))
    .providerNpi("9876543210")
    .placeOfService("Outpatient")
    .build();

CoverageCheckResponse response = insuranceApiClient.checkCoverage(request);

// Analisar cobertura por procedimento
for (String code : preOpProcedures) {
    ProcedureCoverage coverage = response.getProcedureCoverageDetails().get(code);
    if (coverage == null || !coverage.isCovered()) {
        log.warn("Procedimento {} não coberto", code);
    } else if (coverage.isRequiresPriorAuth()) {
        log.info("Procedimento {} requer autorização prévia", code);
    }
}
```

### 11.3. Exemplo de Caso de Uso Completo - Verificação Antes de Cirurgia

```java
/**
 * UC: Verificar Cobertura de Procedimentos Cirúrgicos e Honorários
 */
@Service
@RequiredArgsConstructor
public class SurgicalCoverageService {

    private final InsuranceApiClient insuranceApiClient;

    public SurgicalCoverageResult verifySurgicalCoverage(
        String patientId,
        String payerId,
        String surgeryCode,
        List<String> anesthesiaCodes,
        List<String> surgicalTeamCodes,
        LocalDate scheduledDate
    ) {
        // Consolidar todos os códigos em uma lista
        List<String> allProcedures = new ArrayList<>();
        allProcedures.add(surgeryCode);
        allProcedures.addAll(anesthesiaCodes);
        allProcedures.addAll(surgicalTeamCodes);

        // Construir request
        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId(patientId)
            .payerId(payerId)
            .procedureCodes(allProcedures)
            .serviceDate(scheduledDate)
            .providerNpi("1234567890")
            .placeOfService("Inpatient") // Cirurgia com internação
            .build();

        // Verificar cobertura
        CoverageCheckResponse response = insuranceApiClient.checkCoverage(request);

        // Analisar resultados
        SurgicalCoverageResult result = new SurgicalCoverageResult();
        result.setSurgeryCode(surgeryCode);

        ProcedureCoverage surgeryCoverage = response.getProcedureCoverageDetails().get(surgeryCode);
        if (surgeryCoverage == null || !surgeryCoverage.isCovered()) {
            result.setApproved(false);
            result.setDenialReason("Cirurgia não coberta pelo plano");
            return result;
        }

        if (surgeryCoverage.isRequiresPriorAuth()) {
            result.setRequiresPriorAuth(true);
            result.setAuthorizationRequired("Cirurgia requer autorização prévia");
        }

        // Verificar cobertura de anestesia
        for (String anesthesiaCode : anesthesiaCodes) {
            ProcedureCoverage anesthesiaCoverage = response.getProcedureCoverageDetails().get(anesthesiaCode);
            if (anesthesiaCoverage == null || !anesthesiaCoverage.isCovered()) {
                result.addWarning("Anestesia " + anesthesiaCode + " não coberta");
            }
        }

        // Verificar cobertura de equipe cirúrgica
        for (String teamCode : surgicalTeamCodes) {
            ProcedureCoverage teamCoverage = response.getProcedureCoverageDetails().get(teamCode);
            if (teamCoverage == null || !teamCoverage.isCovered()) {
                result.addWarning("Honorário " + teamCode + " não coberto");
            }
        }

        // Calcular responsabilidade financeira do paciente
        BigDecimal totalCopay = response.getProcedureCoverageDetails().values().stream()
            .map(ProcedureCoverage::getCopay)
            .filter(Objects::nonNull)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        result.setEstimatedPatientCost(totalCopay);
        result.setApproved(true);

        return result;
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário

```java
class CoverageCheckRequestTest {

    @Test
    void testBuilder_AllFieldsSet() {
        // Arrange & Act
        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .procedureCodes(List.of("10101012"))
            .serviceDate(LocalDate.of(2026, 1, 15))
            .providerNpi("1234567890")
            .placeOfService("Outpatient")
            .build();

        // Assert
        assertEquals("PAT-123", request.getPatientId());
        assertEquals("UNIMED-123", request.getPayerId());
        assertEquals(1, request.getProcedureCodes().size());
        assertEquals("10101012", request.getProcedureCodes().get(0));
        assertEquals(LocalDate.of(2026, 1, 15), request.getServiceDate());
        assertEquals("1234567890", request.getProviderNpi());
        assertEquals("Outpatient", request.getPlaceOfService());
    }

    @Test
    void testBuilder_MinimalFields() {
        // Arrange & Act
        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .procedureCodes(List.of("10101012"))
            .serviceDate(LocalDate.now())
            .build();

        // Assert
        assertNotNull(request);
        assertNull(request.getProviderNpi());
        assertNull(request.getPlaceOfService());
    }

    @Test
    void testSerialization_ToJson() throws JsonProcessingException {
        // Arrange
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());

        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .procedureCodes(List.of("10101012", "40301010"))
            .serviceDate(LocalDate.of(2026, 1, 15))
            .build();

        // Act
        String json = mapper.writeValueAsString(request);

        // Assert
        assertTrue(json.contains("\"patientId\":\"PAT-123\""));
        assertTrue(json.contains("\"procedureCodes\":[\"10101012\",\"40301010\"]"));
    }

    @Test
    void testDeserialization_FromJson() throws JsonProcessingException {
        // Arrange
        String json = """
            {
                "patientId": "PAT-123",
                "payerId": "UNIMED-123",
                "procedureCodes": ["10101012"],
                "serviceDate": "2026-01-15",
                "providerNpi": "1234567890",
                "placeOfService": "Outpatient"
            }
            """;

        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());

        // Act
        CoverageCheckRequest request = mapper.readValue(json, CoverageCheckRequest.class);

        // Assert
        assertEquals("PAT-123", request.getPatientId());
        assertEquals("UNIMED-123", request.getPayerId());
        assertEquals(1, request.getProcedureCodes().size());
    }
}
```

### 12.2. Massa de Dados para Teste

```json
{
  "minimal_request": {
    "patientId": "PAT-12345",
    "payerId": "UNIMED-SP-123456",
    "procedureCodes": ["10101012"],
    "serviceDate": "2026-01-15"
  },
  "complete_request": {
    "patientId": "PAT-67890",
    "payerId": "BRADESCO-456789",
    "procedureCodes": ["40301010", "40302156", "40801004"],
    "serviceDate": "2026-01-20",
    "providerNpi": "9876543210",
    "placeOfService": "Outpatient"
  },
  "surgical_request": {
    "patientId": "PAT-99999",
    "payerId": "SULAMERICA-111222",
    "procedureCodes": ["30701018", "30801025", "31001036"],
    "serviceDate": "2026-02-01",
    "providerNpi": "1112223334",
    "placeOfService": "Inpatient"
  }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **Dados do Paciente**: patientId deve ser validado contra banco de dados antes de enviar request
- **Autorização**: Usuário deve ter permissão para consultar cobertura do paciente

### 13.2. Proteção de Dados
- **PII**: patientId é dado pessoal - deve ser protegido conforme LGPD
- **Dados de Saúde**: procedureCodes são dados sensíveis - trafegar via TLS 1.2+
- **Logging**: Mascarar patientId em logs (mostrar apenas últimos 4 dígitos)

### 13.3. Auditoria
```java
@Aspect
@Component
public class CoverageRequestAuditAspect {

    @Before("execution(* InsuranceApiClient.checkCoverage(..)) && args(request)")
    public void auditCoverageRequest(CoverageCheckRequest request) {
        String maskedPatientId = maskPatientId(request.getPatientId());
        auditLog.info("Coverage check requested",
            "maskedPatientId", maskedPatientId,
            "payerId", request.getPayerId(),
            "procedureCount", request.getProcedureCodes().size(),
            "serviceDate", request.getServiceDate(),
            "user", SecurityContextHolder.getContext().getAuthentication().getName()
        );
    }

    private String maskPatientId(String patientId) {
        if (patientId == null || patientId.length() < 4) return "****";
        return "****" + patientId.substring(patientId.length() - 4);
    }
}
```

## 14. Referências

### 14.1. Documentação Relacionada
- `CoverageCheckResponse.java` - DTO de resposta correspondente
- `InsuranceApiClient.java` - Cliente que consome este DTO
- `ProcedureCoverage.java` - Nested class com detalhes de cobertura

### 14.2. Links Externos
- [TUSS 4.03.03 - Tabela de Procedimentos](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)
- [RN-259/2011 ANS - Rol de Procedimentos](https://www.gov.br/ans/pt-br/arquivos/assuntos/consumidor/o-que-seu-plano-deve-cobrir/RN259_RolProcedimentos.pdf)

### 14.3. Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm - Coder Agent 7 | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:a7e9f6d5c4b8a3e7d9c6b5f4e3d8a7c9b6e5f4d3c9a8b7e6d5f4c3b9a8e7d6f5`
**Última Atualização:** 2026-01-12T13:21:00Z
**Próxima Revisão:** 2026-04-12
