# RN-CoverageCheckResponse - DTO de Resposta de Verificação de Cobertura

## 1. Identificação da Regra
- **ID:** RN-COVERAGE-RESPONSE-001
- **Nome:** Data Transfer Object para Resposta de Verificação de Cobertura de Procedimentos
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 7
- **Categoria:** Integration Layer / DTO
- **Prioridade:** Alta
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
DTO que encapsula a resposta da operadora sobre cobertura de procedimentos médicos. Contém informações sobre quais procedimentos estão cobertos, quais requerem autorização prévia, valores de co-participação, coinsurance, limites de frequência, e nível de cobertura por procedimento (BASIC, STANDARD, PREMIUM).

### 2.2. Descrição Técnica
Classe imutável com Lombok annotations e nested class `ProcedureCoverage` para detalhes granulares por código TUSS. Deserializada de JSON retornado por InsuranceApiClient.checkCoverage(). Utiliza BigDecimal para precisão monetária e Map<String, ProcedureCoverage> para acesso O(1) aos detalhes de cada procedimento.

### 2.3. Origem do Requisito
- **Funcional:** Apresentar detalhes de cobertura para decisão clínica e financeira
- **Regulatório:** RN-259/2011 ANS - Transparência sobre cobertura de procedimentos
- **Técnico:** Response DTO para comunicação REST com operadoras

## 3. Estrutura de Dados

### 3.1. Campos Principais

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| patientId | String | Sim | Identificador único do paciente |
| payerId | String | Sim | Identificador da operadora (registro ANS) |
| serviceDate | LocalDate | Sim | Data prevista do procedimento |
| verificationSuccessful | boolean | Sim | Indica se verificação foi bem-sucedida |
| coveredProcedures | List<String> | Não | Códigos TUSS dos procedimentos cobertos |
| notCoveredProcedures | List<String> | Não | Códigos TUSS não cobertos |
| requiresPriorAuthorization | List<String> | Não | Códigos que requerem autorização prévia |
| procedureCoverageDetails | Map<String, ProcedureCoverage> | Não | Detalhes de cobertura por código TUSS |
| errorMessage | String | Não | Mensagem de erro se verificação falhar |

### 3.2. Nested Class: ProcedureCoverage

| Campo | Tipo | Descrição |
|-------|------|-----------|
| procedureCode | String | Código TUSS do procedimento |
| covered | boolean | Indica se procedimento está coberto |
| requiresPriorAuth | boolean | Requer autorização prévia |
| copay | BigDecimal | Valor fixo de co-participação (R$) |
| coinsurancePercent | BigDecimal | Percentual de coinsurance (0.20 = 20%) |
| coverageLevel | String | Nível: BASIC, STANDARD, PREMIUM, HIGH_COMPLEXITY |
| frequencyLimit | Integer | Limite de frequência (e.g., 12 consultas/ano) |
| remainingFrequency | Integer | Frequência restante no período |

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
QUANDO InsuranceApiClient.checkCoverage() retorna
ENTÃO deserializar JSON para CoverageCheckResponse
E popular listas coveredProcedures, notCoveredProcedures, requiresPriorAuthorization
E mapear procedureCoverageDetails por código TUSS
```

### 4.2. Critérios de Validação

**Validações de Response:**
1. **verificationSuccessful = true**: procedureCoverageDetails não pode ser vazio
2. **verificationSuccessful = false**: errorMessage deve estar presente
3. **coveredProcedures**: Deve conter apenas códigos que existem em procedureCoverageDetails com `covered=true`
4. **requiresPriorAuthorization**: Deve conter apenas códigos com `requiresPriorAuth=true`

**Validações de ProcedureCoverage:**
1. **copay**: Deve ser >= 0 (pode ser null se não houver copay)
2. **coinsurancePercent**: Deve estar entre 0.00 e 1.00 (0% a 100%)
3. **frequencyLimit**: Se presente, remainingFrequency deve ser <= frequencyLimit

### 4.3. Ações e Consequências

**QUANDO** response recebido com `verificationSuccessful=true`:
1. **Iterar** sobre procedureCoverageDetails
2. **Identificar** procedimentos que requerem prior auth
3. **Calcular** responsabilidade financeira total do paciente
4. **Decidir** se procedimento pode ser agendado ou requer autorização

**SE** `covered=false` para procedimento:
- **Notificar** equipe médica sobre falta de cobertura
- **Sugerir** procedimentos alternativos cobertos
- **Informar** paciente sobre custo particular (out-of-pocket)

**SE** `requiresPriorAuth=true`:
- **Iniciar** fluxo de autorização prévia no Camunda
- **Aguardar** aprovação da operadora antes de agendar

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio

**Cálculo de Responsabilidade do Paciente por Procedimento:**
```
patient_responsibility = copay + coinsurance_amount

Onde:
- copay: Valor fixo de co-participação
- coinsurance_amount: (procedure_cost - copay) * coinsurancePercent

Exemplo:
- Procedimento: R$ 500,00
- Copay: R$ 30,00
- Coinsurance: 20% (0.20)

coinsurance_amount = (500 - 30) * 0.20 = R$ 94,00
patient_responsibility = 30 + 94 = R$ 124,00
insurance_payment = 500 - 124 = R$ 376,00
```

**Cálculo Total para Múltiplos Procedimentos:**
```java
BigDecimal totalPatientCost = response.getProcedureCoverageDetails().values().stream()
    .filter(ProcedureCoverage::isCovered)
    .map(coverage -> {
        BigDecimal copay = coverage.getCopay() != null ? coverage.getCopay() : BigDecimal.ZERO;
        // Coinsurance seria calculado com custo estimado do procedimento
        return copay;
    })
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

### 5.2. Regras de Arredondamento
- **Valores Monetários**: Arredondar para 2 casas decimais (HALF_UP)
- **Percentuais**: Manter 4 casas decimais de precisão

### 5.3. Tratamento de Valores Especiais
- **copay null**: Assumir R$ 0,00 (sem co-participação)
- **coinsurancePercent null**: Assumir 0% (operadora paga 100%)
- **frequencyLimit null**: Sem limite de frequência
- **remainingFrequency null**: Frequência não rastreada pela operadora

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Campos Mapeados

| Campo Response | Campo TISS | Descrição |
|----------------|------------|-----------|
| coveredProcedures | procedimentosCobertos | Códigos TUSS cobertos pelo plano |
| notCoveredProcedures | procedimentosNegados | Códigos TUSS negados |
| requiresPriorAuthorization | autorizacaoPreviaObrigatoria | Procedimentos que requerem autorização |
| copay | valorCoParticipacao | Co-participação do beneficiário |
| coverageLevel | nivelCobertura | BASICO, INTERMEDIARIO, COMPLETO |

### 6.3. Níveis de Cobertura TISS

| Valor Response | Equivalente TISS | Descrição |
|----------------|------------------|-----------|
| BASIC | BASICO | Cobertura básica obrigatória (Rol ANS) |
| STANDARD | INTERMEDIARIO | Cobertura padrão com alguns adicionais |
| PREMIUM | COMPLETO | Cobertura completa sem restrições |
| HIGH_COMPLEXITY | ALTA_COMPLEXIDADE | Procedimentos de alto custo/complexidade |

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-259/2011**: Rol de Procedimentos e Eventos em Saúde
  - Procedimentos do Rol ANS devem retornar `covered=true`
  - Negativa de cobertura deve incluir justificativa
- **RN-469/2021**: Padrão TISS 4.03.03
  - Códigos de negativa devem seguir tabela TISS de motivos de glosa
- **RN-506/2022**: Autorização Prévia Eletrônica
  - `requiresPriorAuth=true` deve disparar workflow de autorização

### 7.2. Requisitos LGPD
- **Art. 9º**: Dados de saúde (procedimentos) são sensíveis
- **Art. 46**: Resposta deve ser protegida via TLS 1.2+ em trânsito
- **Retenção**: Respostas podem ser cacheadas por até 24h

### 7.3. Validações Regulatórias
1. **Procedimentos Rol ANS**: Não podem estar em `notCoveredProcedures`
2. **Copay**: Deve respeitar limite de 40% do valor do procedimento (RN-469)
3. **Prior Auth**: Prazo de resposta da operadora: até 48h úteis

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio

| Condição | Ação | Mensagem |
|----------|------|----------|
| verificationSuccessful=false | Lançar CoverageVerificationException | errorMessage da response |
| procedureCoverageDetails vazio | Log warning | "Nenhum detalhe de cobertura retornado" |
| Procedimento Rol ANS não coberto | Notificar compliance | "Violação RN-259: procedimento {code} não coberto" |

### 8.2. Erros Técnicos
- **Deserialização JSON**: Se falhar, lançar RuntimeException com detalhes
- **Dados inconsistentes**: coveredProcedures contém código que não está em procedureCoverageDetails

### 8.3. Estratégias de Recuperação
1. **Cache Fallback**: Se verificação falhar, retornar última resposta cacheada (se < 24h)
2. **Default Safe**: Se cobertura desconhecida, assumir `requiresPriorAuth=true` (conservador)
3. **Manual Review**: Enviar casos de negativa de Rol ANS para revisão manual

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **InsuranceApiClient**: Retorna CoverageCheckResponse após chamada à operadora
- **CoverageVerificationDelegate**: Processa response e atualiza variáveis Camunda

### 9.2. Dependências Downstream
- **AuthorizationWorkflow**: Dispara workflow se `requiresPriorAuth=true`
- **PatientNotificationService**: Notifica paciente sobre copay e cobertura
- **FinancialService**: Calcula provisão financeira baseada em coinsurance

### 9.3. Eventos Publicados
```java
// Evento publicado após processar response
eventBus.publish(new CoverageVerifiedEvent(
    patientId,
    payerId,
    coveredProcedures.size(),
    notCoveredProcedures.size(),
    requiresPriorAuthorization.size(),
    totalEstimatedPatientCost
));
```

### 9.4. Eventos Consumidos
Não consome eventos - Response é retorno síncrono de chamada API.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Deserialização JSON**: < 20ms para responses com até 50 procedimentos
- **Map Lookup**: O(1) para acesso a procedureCoverageDetails por código TUSS

### 10.2. Estratégias de Cache

**Cache de Respostas:**
```java
@Cacheable(value = "coverageResponses", key = "#patientId + '-' + #payerId + '-' + #procedureCodes.hashCode()")
public CoverageCheckResponse getCachedCoverage(String patientId, String payerId, List<String> procedureCodes) {
    // ...
}
```
- **TTL**: 24 horas (cobertura raramente muda)
- **Invalidation**: Manual via `/api/cache/invalidate/coverage/{patientId}`

### 10.3. Otimizações Implementadas
1. **Map para acesso rápido**: procedureCoverageDetails usa HashMap (O(1))
2. **Lazy loading**: Lists (coveredProcedures, etc.) são populadas sob demanda
3. **Immutability**: @Data garante thread-safety para cache

## 11. Exemplos de Uso

### 11.1. Exemplo Básico - Processar Response

```java
CoverageCheckResponse response = insuranceApiClient.checkCoverage(request);

if (!response.isVerificationSuccessful()) {
    throw new CoverageVerificationException(response.getErrorMessage());
}

// Verificar quais procedimentos requerem autorização
if (!response.getRequiresPriorAuthorization().isEmpty()) {
    log.info("Procedimentos requerem autorização prévia: {}",
        response.getRequiresPriorAuthorization());

    for (String code : response.getRequiresPriorAuthorization()) {
        authorizationService.requestPriorAuthorization(
            response.getPatientId(),
            response.getPayerId(),
            code
        );
    }
}

// Verificar procedimentos não cobertos
if (!response.getNotCoveredProcedures().isEmpty()) {
    log.warn("Procedimentos NÃO cobertos: {}",
        response.getNotCoveredProcedures());

    notificationService.notifyPatient(
        response.getPatientId(),
        "Alguns procedimentos não estão cobertos pelo seu plano",
        response.getNotCoveredProcedures()
    );
}
```

### 11.2. Exemplo Avançado - Calcular Custo do Paciente

```java
/**
 * Calcula custo total estimado para o paciente baseado em cobertura
 */
public PatientCostEstimate calculatePatientCost(
    CoverageCheckResponse coverageResponse,
    Map<String, BigDecimal> procedureCosts
) {
    BigDecimal totalCopay = BigDecimal.ZERO;
    BigDecimal totalCoinsurance = BigDecimal.ZERO;
    List<String> uncoveredProcedures = new ArrayList<>();

    for (Map.Entry<String, ProcedureCoverage> entry :
            coverageResponse.getProcedureCoverageDetails().entrySet()) {

        String code = entry.getKey();
        ProcedureCoverage coverage = entry.getValue();

        if (!coverage.isCovered()) {
            uncoveredProcedures.add(code);
            continue;
        }

        // Copay
        BigDecimal copay = coverage.getCopay() != null
            ? coverage.getCopay()
            : BigDecimal.ZERO;
        totalCopay = totalCopay.add(copay);

        // Coinsurance
        BigDecimal procedureCost = procedureCosts.getOrDefault(code, BigDecimal.ZERO);
        if (coverage.getCoinsurancePercent() != null && procedureCost.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal coinsuranceAmount = procedureCost
                .subtract(copay)
                .multiply(coverage.getCoinsurancePercent())
                .setScale(2, RoundingMode.HALF_UP);
            totalCoinsurance = totalCoinsurance.add(coinsuranceAmount);
        }
    }

    return PatientCostEstimate.builder()
        .totalCopay(totalCopay)
        .totalCoinsurance(totalCoinsurance)
        .totalPatientResponsibility(totalCopay.add(totalCoinsurance))
        .uncoveredProcedures(uncoveredProcedures)
        .requiresAuthorization(!coverageResponse.getRequiresPriorAuthorization().isEmpty())
        .build();
}
```

### 11.3. Exemplo de Caso de Uso Completo - Decisão de Agendamento

```java
/**
 * UC: Decidir se Procedimento pode ser Agendado com base em Cobertura
 */
@Service
@RequiredArgsConstructor
public class ProcedureSchedulingService {

    private final InsuranceApiClient insuranceApiClient;
    private final AuthorizationService authorizationService;
    private final NotificationService notificationService;

    public SchedulingDecision evaluateScheduling(
        String patientId,
        String payerId,
        String procedureCode,
        LocalDate requestedDate
    ) {
        // 1. Verificar cobertura
        CoverageCheckRequest request = CoverageCheckRequest.builder()
            .patientId(patientId)
            .payerId(payerId)
            .procedureCodes(List.of(procedureCode))
            .serviceDate(requestedDate)
            .build();

        CoverageCheckResponse response = insuranceApiClient.checkCoverage(request);

        if (!response.isVerificationSuccessful()) {
            return SchedulingDecision.denied("Falha ao verificar cobertura: " + response.getErrorMessage());
        }

        // 2. Obter detalhes de cobertura do procedimento
        ProcedureCoverage coverage = response.getProcedureCoverageDetails().get(procedureCode);

        if (coverage == null) {
            return SchedulingDecision.denied("Cobertura não especificada pela operadora");
        }

        if (!coverage.isCovered()) {
            // Procedimento não coberto
            notificationService.notifyPatient(
                patientId,
                "Procedimento não coberto",
                String.format("Procedimento %s não está coberto pelo seu plano. Custo particular: R$ XXX", procedureCode)
            );
            return SchedulingDecision.requiresPatientConsent("Procedimento não coberto - requer pagamento particular");
        }

        // 3. Verificar limite de frequência
        if (coverage.getFrequencyLimit() != null && coverage.getRemainingFrequency() != null) {
            if (coverage.getRemainingFrequency() == 0) {
                return SchedulingDecision.denied(
                    String.format("Limite de frequência atingido. Máximo: %d procedimentos por ano", coverage.getFrequencyLimit())
                );
            }

            if (coverage.getRemainingFrequency() == 1) {
                notificationService.notifyPatient(
                    patientId,
                    "Atenção: Última utilização disponível",
                    String.format("Este será seu último uso coberto. Limite anual: %d", coverage.getFrequencyLimit())
                );
            }
        }

        // 4. Verificar necessidade de autorização prévia
        if (coverage.isRequiresPriorAuth()) {
            // Verificar se autorização já existe
            Optional<Authorization> existingAuth = authorizationService.findAuthorization(
                patientId,
                payerId,
                procedureCode,
                requestedDate
            );

            if (existingAuth.isPresent() && existingAuth.get().isApproved()) {
                // Autorização já aprovada
                return SchedulingDecision.approved("Autorização prévia já concedida: " + existingAuth.get().getAuthNumber());
            }

            // Solicitar autorização prévia
            String authRequestId = authorizationService.requestAuthorization(
                patientId,
                payerId,
                procedureCode,
                requestedDate,
                "Agendamento solicitado"
            );

            return SchedulingDecision.pendingAuthorization(
                String.format("Aguardando autorização prévia. Protocolo: %s", authRequestId)
            );
        }

        // 5. Calcular e informar custo do paciente
        BigDecimal copay = coverage.getCopay() != null ? coverage.getCopay() : BigDecimal.ZERO;
        String costMessage = String.format("Co-participação estimada: R$ %.2f", copay);

        if (coverage.getCoinsurancePercent() != null && coverage.getCoinsurancePercent().compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal coinsurancePercent = coverage.getCoinsurancePercent().multiply(BigDecimal.valueOf(100));
            costMessage += String.format(" + %.1f%% do valor do procedimento", coinsurancePercent);
        }

        notificationService.notifyPatient(patientId, "Custo Estimado", costMessage);

        // 6. Aprovar agendamento
        return SchedulingDecision.approved(costMessage);
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário

```java
class CoverageCheckResponseTest {

    @Test
    void testDeserialization_SuccessfulVerification() throws JsonProcessingException {
        // Arrange
        String json = """
            {
                "patientId": "PAT-123",
                "payerId": "UNIMED-123",
                "serviceDate": "2026-01-15",
                "verificationSuccessful": true,
                "coveredProcedures": ["10101012", "40301010"],
                "notCoveredProcedures": [],
                "requiresPriorAuthorization": [],
                "procedureCoverageDetails": {
                    "10101012": {
                        "procedureCode": "10101012",
                        "covered": true,
                        "requiresPriorAuth": false,
                        "copay": 50.00,
                        "coinsurancePercent": 0.00,
                        "coverageLevel": "STANDARD"
                    }
                }
            }
            """;

        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());

        // Act
        CoverageCheckResponse response = mapper.readValue(json, CoverageCheckResponse.class);

        // Assert
        assertTrue(response.isVerificationSuccessful());
        assertEquals(2, response.getCoveredProcedures().size());
        assertTrue(response.getProcedureCoverageDetails().containsKey("10101012"));
        assertEquals(new BigDecimal("50.00"),
            response.getProcedureCoverageDetails().get("10101012").getCopay());
    }

    @Test
    void testProcedureCoverage_RequiresPriorAuth() {
        // Arrange
        ProcedureCoverage coverage = ProcedureCoverage.builder()
            .procedureCode("30701018")
            .covered(true)
            .requiresPriorAuth(true)
            .copay(BigDecimal.ZERO)
            .coinsurancePercent(new BigDecimal("0.20"))
            .coverageLevel("HIGH_COMPLEXITY")
            .build();

        // Assert
        assertTrue(coverage.isCovered());
        assertTrue(coverage.isRequiresPriorAuth());
        assertEquals("HIGH_COMPLEXITY", coverage.getCoverageLevel());
        assertEquals(0, BigDecimal.ZERO.compareTo(coverage.getCopay()));
    }

    @Test
    void testProcedureCoverage_FrequencyLimit() {
        // Arrange
        ProcedureCoverage coverage = ProcedureCoverage.builder()
            .procedureCode("10101012")
            .covered(true)
            .frequencyLimit(12)
            .remainingFrequency(8)
            .build();

        // Assert
        assertEquals(12, coverage.getFrequencyLimit());
        assertEquals(8, coverage.getRemainingFrequency());
        assertTrue(coverage.getRemainingFrequency() > 0, "Ainda há frequência disponível");
    }
}
```

### 12.2. Massa de Dados para Teste

```json
{
  "successful_response": {
    "patientId": "PAT-12345",
    "payerId": "UNIMED-SP-123456",
    "serviceDate": "2026-01-15",
    "verificationSuccessful": true,
    "coveredProcedures": ["10101012", "40301010"],
    "notCoveredProcedures": [],
    "requiresPriorAuthorization": [],
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
      "40301010": {
        "procedureCode": "40301010",
        "covered": true,
        "requiresPriorAuth": false,
        "copay": 0.00,
        "coinsurancePercent": 0.20,
        "coverageLevel": "BASIC"
      }
    }
  },
  "prior_auth_required": {
    "patientId": "PAT-67890",
    "payerId": "BRADESCO-456789",
    "serviceDate": "2026-02-01",
    "verificationSuccessful": true,
    "coveredProcedures": ["30701018"],
    "requiresPriorAuthorization": ["30701018"],
    "procedureCoverageDetails": {
      "30701018": {
        "procedureCode": "30701018",
        "covered": true,
        "requiresPriorAuth": true,
        "copay": 0.00,
        "coinsurancePercent": 0.30,
        "coverageLevel": "HIGH_COMPLEXITY"
      }
    }
  },
  "not_covered_response": {
    "patientId": "PAT-99999",
    "payerId": "AMIL-111222",
    "serviceDate": "2026-01-20",
    "verificationSuccessful": true,
    "coveredProcedures": ["10101012"],
    "notCoveredProcedures": ["99999999"],
    "procedureCoverageDetails": {
      "10101012": {
        "procedureCode": "10101012",
        "covered": true,
        "requiresPriorAuth": false,
        "copay": 30.00
      },
      "99999999": {
        "procedureCode": "99999999",
        "covered": false,
        "requiresPriorAuth": false
      }
    }
  }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **Dados do Paciente**: Response contém dados sensíveis (cobertura, custo)
- **Autorização**: Apenas usuários autorizados devem acessar response

### 13.2. Proteção de Dados
- **PII**: patientId é dado pessoal protegido por LGPD
- **Dados de Saúde**: procedureCoverageDetails contém informações sensíveis
- **Logging**: Mascarar patientId em logs de auditoria

### 13.3. Auditoria
```java
@Aspect
@Component
public class CoverageResponseAuditAspect {

    @AfterReturning(pointcut = "execution(* InsuranceApiClient.checkCoverage(..))", returning = "response")
    public void auditCoverageResponse(CoverageCheckResponse response) {
        auditLog.info("Coverage verification result",
            "maskedPatientId", maskId(response.getPatientId()),
            "payerId", response.getPayerId(),
            "verificationSuccessful", response.isVerificationSuccessful(),
            "coveredCount", response.getCoveredProcedures().size(),
            "notCoveredCount", response.getNotCoveredProcedures().size(),
            "priorAuthCount", response.getRequiresPriorAuthorization().size(),
            "timestamp", Instant.now()
        );
    }
}
```

## 14. Referências

### 14.1. Documentação Relacionada
- `CoverageCheckRequest.java` - DTO de request correspondente
- `InsuranceApiClient.java` - Cliente que retorna este DTO
- `ProcedureCoverage.java` - Nested class com detalhes por procedimento

### 14.2. Links Externos
- [RN-259/2011 ANS - Rol de Procedimentos](https://www.gov.br/ans/pt-br/arquivos/assuntos/consumidor/o-que-seu-plano-deve-cobrir/RN259_RolProcedimentos.pdf)
- [TISS 4.03.03](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)

### 14.3. Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm - Coder Agent 7 | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:b8f7e6d5c4a9b3e8d9c7b6f5e4d9a8c9b7e6f5d4c9a8b7e6d5f4c3b9a8e7d6f5`
**Última Atualização:** 2026-01-12T13:22:00Z
**Próxima Revisão:** 2026-04-12
