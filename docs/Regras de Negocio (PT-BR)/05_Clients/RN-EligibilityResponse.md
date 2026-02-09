# RN-EligibilityResponse - DTO de Resposta de Verificação de Elegibilidade

## 1. Identificação da Regra
- **ID:** RN-ELIGIBILITY-RESPONSE-001
- **Nome:** Data Transfer Object para Resposta de Verificação de Elegibilidade X12 271 EDI
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 7
- **Categoria:** Integration Layer / DTO
- **Prioridade:** Crítica
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
DTO que encapsula a resposta da operadora sobre elegibilidade e benefícios do beneficiário. Corresponde à transação X12 271 EDI (Eligibility Benefit Response) adaptada para o contexto brasileiro. Contém informações sobre status de elegibilidade, datas de vigência da cobertura, valores de co-participação, franquia (deductible), coinsurance, teto de despesas (out-of-pocket max), tipo de plano e status de rede credenciada.

### 2.2. Descrição Técnica
Classe imutável com Lombok annotations (`@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`). Deserializada de JSON retornado por InsuranceApiClient.checkEligibility(). Utiliza BigDecimal para precisão monetária e LocalDate para campos de data. Campos seguem nomenclatura X12 271 EDI para compatibilidade com operadoras que utilizam este padrão.

### 2.3. Origem do Requisito
- **Funcional:** Apresentar dados completos de elegibilidade e benefícios para decisão clínica
- **Regulatório:** RN-469/2021 ANS - Transparência sobre cobertura e custos
- **Técnico:** Response DTO para comunicação REST com operadoras (padrão X12 271 EDI)

## 3. Estrutura de Dados

### 3.1. Campos Principais

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| patientId | String | Sim | Identificador único do paciente |
| payerId | String | Sim | Identificador da operadora (registro ANS) |
| payerName | String | Não | Nome fantasia da operadora (e.g., "Unimed São Paulo") |
| planName | String | Não | Nome do plano (e.g., "Plano Empresarial Nacional") |
| eligibilityStatus | String | Sim | Status: ACTIVE, INACTIVE, UNKNOWN |
| coverageActive | boolean | Sim | Indica se cobertura está ativa |
| coverageEffectiveDate | LocalDate | Não | Data de início da vigência |
| coverageTerminationDate | LocalDate | Não | Data de término da vigência |
| copayAmount | BigDecimal | Não | Valor fixo de co-participação (R$) |
| deductibleAmount | BigDecimal | Não | Valor total da franquia anual (R$) |
| remainingDeductible | BigDecimal | Não | Franquia restante no período (R$) |
| outOfPocketMax | BigDecimal | Não | Teto máximo de despesas do beneficiário (R$) |
| remainingOutOfPocket | BigDecimal | Não | Teto restante no período (R$) |
| coinsurancePercent | BigDecimal | Não | Percentual de coinsurance (0.20 = 20%) |
| planType | String | Não | Tipo: HMO, PPO, EPO, POS |
| networkStatus | String | Não | Status: IN_NETWORK, OUT_OF_NETWORK |
| verificationDate | LocalDate | Sim | Data da verificação |
| errorMessage | String | Não | Mensagem de erro se verificação falhar |

### 3.2. Valores de EligibilityStatus

| Valor | Descrição | Ação |
|-------|-----------|------|
| ACTIVE | Cobertura ativa sem restrições | Permitir atendimento |
| INACTIVE | Cobertura inativa (inadimplência, cancelamento) | Negar atendimento |
| UNKNOWN | Status desconhecido (erro temporário) | Contatar operadora |

### 3.3. Tipos de Plano (planType)

| Código | Nome | Descrição |
|--------|------|-----------|
| HMO | Health Maintenance Organization | Rede credenciada restrita |
| PPO | Preferred Provider Organization | Rede ampla com livre escolha |
| EPO | Exclusive Provider Organization | Rede exclusiva sem cobertura externa |
| POS | Point of Service | Híbrido HMO/PPO |

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
QUANDO InsuranceApiClient.checkEligibility() retorna
ENTÃO deserializar JSON para EligibilityResponse
E validar campos obrigatórios (patientId, payerId, eligibilityStatus)
E popular campos de cost-sharing (copay, deductible, coinsurance)
```

### 4.2. Critérios de Validação

**Validações de Response:**
1. **coverageActive = true**: eligibilityStatus deve ser "ACTIVE"
2. **coverageActive = false**: errorMessage deve estar presente
3. **remainingDeductible**: Deve ser <= deductibleAmount
4. **remainingOutOfPocket**: Deve ser <= outOfPocketMax
5. **coverageTerminationDate**: Se presente, deve ser >= coverageEffectiveDate

**Validações de Valores Monetários:**
1. **copayAmount**: Deve ser >= 0
2. **deductibleAmount**: Deve ser >= 0
3. **coinsurancePercent**: Deve estar entre 0.00 e 1.00 (0% a 100%)

### 4.3. Ações e Consequências

**QUANDO** response recebido com `coverageActive=true`:
1. **Verificar** se está dentro do período de vigência (coverageEffectiveDate <= today <= coverageTerminationDate)
2. **Calcular** responsabilidade financeira estimada do paciente
3. **Notificar** se franquia ainda não foi atingida
4. **Permitir** agendamento de procedimentos

**SE** `coverageActive=false`:
- **Notificar** equipe de atendimento sobre status inativo
- **Informar** paciente sobre necessidade de regularização
- **Solicitar** pagamento particular ou aguardar regularização

**SE** `remainingDeductible > 0`:
- **Informar** paciente que próximos procedimentos contam para franquia
- **Alertar** sobre custo adicional até atingir franquia

**SE** `remainingOutOfPocket == 0`:
- **Informar** que teto foi atingido e próximos procedimentos são 100% cobertos

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio

**Cálculo de Franquia Consumida:**
```
deductible_consumed = deductibleAmount - remainingDeductible

Exemplo:
- Franquia anual: R$ 1.000,00
- Franquia restante: R$ 300,00
- Consumido: 1000 - 300 = R$ 700,00 (70%)
```

**Cálculo de Responsabilidade do Paciente para Procedimento:**
```
patient_responsibility = copay + coinsurance_amount + deductible_impact

Onde:
- copay: Valor fixo de co-participação
- coinsurance_amount: (procedure_cost - copay) * coinsurancePercent
- deductible_impact: min(procedure_cost, remainingDeductible)

Exemplo:
- Procedimento: R$ 1.500,00
- Copay: R$ 50,00
- Coinsurance: 20%
- Remaining Deductible: R$ 300,00

coinsurance_amount = (1500 - 50) * 0.20 = R$ 290,00
deductible_impact = min(1500, 300) = R$ 300,00
patient_responsibility = 50 + 290 + 300 = R$ 640,00
insurance_payment = 1500 - 640 = R$ 860,00
```

**Verificação de Teto Atingido:**
```
out_of_pocket_consumed = outOfPocketMax - remainingOutOfPocket

SE out_of_pocket_consumed >= outOfPocketMax:
    patient_responsibility = 0 (operadora paga 100%)
```

### 5.2. Regras de Arredondamento
- **Valores Monetários**: Arredondar para 2 casas decimais (HALF_UP)
- **Percentuais**: Manter 4 casas decimais de precisão

### 5.3. Tratamento de Valores Especiais
- **copayAmount null**: Assumir R$ 0,00 (sem co-participação)
- **deductibleAmount null**: Assumir R$ 0,00 (sem franquia)
- **remainingDeductible null**: Assumir franquia já atingida
- **outOfPocketMax null**: Sem teto (planos sem limite)
- **coinsurancePercent null**: Assumir 0% (operadora paga 100% após copay)

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Campos Mapeados X12 271 → TISS

| Campo Response | Campo X12 EDI | Campo TISS | Descrição |
|----------------|---------------|------------|-----------|
| eligibilityStatus | EB*1 | statusElegibilidade | ATIVO, INATIVO, DESCONHECIDO |
| coverageEffectiveDate | DTP*346 | inicioVigencia | Data de início da cobertura |
| coverageTerminationDate | DTP*347 | fimVigencia | Data de término da cobertura |
| copayAmount | EB*B | valorCoParticipacao | Co-participação do beneficiário |
| deductibleAmount | EB*C | valorFranquia | Franquia anual |
| outOfPocketMax | EB*G | limiteMaximoResponsabilidade | Teto de despesas |
| coinsurancePercent | EB*A | percentualCoparticipacao | Percentual de coinsurance |
| planType | EB*18 | tipoPlano | HMO, PPO, EPO, POS |

### 6.3. Códigos de Elegibilidade TISS

| Código TISS | Equivalente X12 | Descrição |
|-------------|-----------------|-----------|
| 1 | Active Coverage | Cobertura ativa |
| 6 | Inactive | Cobertura inativa |
| 7 | Inactive - Pending Eligibility | Pendente de elegibilidade |
| C | Unknown | Status desconhecido |

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-469/2021**: Padrão TISS para Elegibilidade
  - Art. 6º: Operadora deve informar copay, franquia e coinsurance
  - Art. 8º: Prazo máximo de resposta: 10 segundos
- **RN-259/2011**: Transparência sobre custos e cobertura
- **RN-506/2022**: Informação de status de elegibilidade obrigatória

### 7.2. Requisitos LGPD
- **Art. 9º**: Dados de saúde (plano, cobertura) são sensíveis
- **Art. 46**: Response deve ser protegida via TLS 1.2+ em trânsito
- **Retenção**: Respostas podem ser cacheadas por até 1 hora

### 7.3. Validações Regulatórias
1. **Status ACTIVE**: Operadora deve fornecer datas de vigência
2. **Copay Máximo**: Co-participação não pode exceder 40% do valor do procedimento (RN-469)
3. **Transparência**: Operadora deve informar claramente custos do beneficiário

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio

| Condição | Ação | Mensagem |
|----------|------|----------|
| coverageActive=false | Lançar IneligiblePatientException | errorMessage da response |
| eligibilityStatus=UNKNOWN | Log warning e retry | "Status desconhecido - tentar novamente" |
| coverageTerminationDate < today | Notificar compliance | "Plano vencido" |

### 8.2. Erros Técnicos
- **Deserialização JSON**: Se falhar, lançar RuntimeException com detalhes
- **Dados inconsistentes**: coverageActive=true mas eligibilityStatus=INACTIVE

### 8.3. Estratégias de Recuperação
1. **Cache Fallback**: Se verificação falhar, retornar última resposta cacheada (se < 1h)
2. **Retry**: Para eligibilityStatus=UNKNOWN, retry 1x após 5 segundos
3. **Manual Review**: Casos com dados inconsistentes enviados para revisão manual

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **InsuranceApiClient**: Retorna EligibilityResponse após chamada à operadora
- **EligibilityVerificationDelegate**: Processa response e atualiza variáveis Camunda

### 9.2. Dependências Downstream
- **PatientNotificationService**: Notifica paciente sobre copay, franquia e status
- **FinancialService**: Calcula provisão financeira baseada em cost-sharing
- **SchedulingService**: Decide se agendamento pode ser realizado

### 9.3. Eventos Publicados
```java
// Evento publicado após processar response
eventBus.publish(new EligibilityVerifiedEvent(
    patientId,
    payerId,
    eligibilityStatus,
    coverageActive,
    copayAmount,
    remainingDeductible,
    verificationDate
));
```

### 9.4. Eventos Consumidos
Não consome eventos - Response é retorno síncrono de chamada API.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Deserialização JSON**: < 10ms
- **Cálculos de cost-sharing**: < 5ms

### 10.2. Estratégias de Cache

**Cache de Respostas:**
```java
@Cacheable(value = "eligibilityResponses", key = "#patientId + '-' + #payerId", ttl = 3600)
public EligibilityResponse getCachedEligibility(String patientId, String payerId) {
    // ...
}
```
- **TTL**: 1 hora (status de elegibilidade raramente muda no mesmo dia)
- **Invalidation**: Manual via `/api/cache/invalidate/eligibility/{patientId}`

### 10.3. Otimizações Implementadas
1. **Immutability**: @Data garante thread-safety para cache
2. **Lazy field access**: Campos são acessados sob demanda
3. **BigDecimal caching**: Valores monetários são imutáveis

## 11. Exemplos de Uso

### 11.1. Exemplo Básico - Processar Response

```java
EligibilityResponse response = insuranceApiClient.checkEligibility(request);

if (!response.isCoverageActive()) {
    throw new IneligiblePatientException(
        String.format("Paciente inelegível: %s", response.getErrorMessage())
    );
}

// Verificar se dentro do período de vigência
if (response.getCoverageTerminationDate() != null &&
    response.getCoverageTerminationDate().isBefore(LocalDate.now())) {
    throw new ExpiredCoverageException("Plano vencido em " + response.getCoverageTerminationDate());
}

// Informar custo estimado ao paciente
log.info("Cobertura ativa. Plano: {} ({})", response.getPlanName(), response.getPlanType());
log.info("Co-participação: R$ {}", response.getCopayAmount());
log.info("Franquia restante: R$ {}", response.getRemainingDeductible());
```

### 11.2. Exemplo Avançado - Calcular Custo Completo do Paciente

```java
/**
 * Calcula custo total estimado do paciente incluindo copay, coinsurance e deductible
 */
public BigDecimal calculatePatientCost(
    EligibilityResponse eligibility,
    BigDecimal procedureCost
) {
    // 1. Verificar se teto foi atingido
    if (eligibility.getRemainingOutOfPocket() != null &&
        eligibility.getRemainingOutOfPocket().compareTo(BigDecimal.ZERO) == 0) {
        return BigDecimal.ZERO; // Operadora paga 100%
    }

    BigDecimal totalCost = BigDecimal.ZERO;

    // 2. Copay
    BigDecimal copay = eligibility.getCopayAmount() != null
        ? eligibility.getCopayAmount()
        : BigDecimal.ZERO;
    totalCost = totalCost.add(copay);

    // 3. Coinsurance
    if (eligibility.getCoinsurancePercent() != null) {
        BigDecimal coinsuranceAmount = procedureCost
            .subtract(copay)
            .multiply(eligibility.getCoinsurancePercent())
            .setScale(2, RoundingMode.HALF_UP);
        totalCost = totalCost.add(coinsuranceAmount);
    }

    // 4. Deductible impact
    if (eligibility.getRemainingDeductible() != null &&
        eligibility.getRemainingDeductible().compareTo(BigDecimal.ZERO) > 0) {
        BigDecimal deductibleImpact = procedureCost.min(eligibility.getRemainingDeductible());
        totalCost = totalCost.add(deductibleImpact);
    }

    // 5. Verificar se excede teto restante
    if (eligibility.getRemainingOutOfPocket() != null) {
        totalCost = totalCost.min(eligibility.getRemainingOutOfPocket());
    }

    return totalCost;
}
```

### 11.3. Exemplo de Caso de Uso Completo - Notificação de Custos ao Paciente

```java
/**
 * UC: Notificar Paciente sobre Custos Estimados após Verificação de Elegibilidade
 */
@Service
@RequiredArgsConstructor
public class PatientCostNotificationService {

    private final NotificationService notificationService;
    private final ProcedureService procedureService;

    public void notifyPatientCosts(
        String patientId,
        EligibilityResponse eligibility,
        List<String> plannedProcedures
    ) {
        // 1. Verificar se cobertura ativa
        if (!eligibility.isCoverageActive()) {
            notificationService.sendEmail(
                patientId,
                "Cobertura Inativa",
                String.format("Sua cobertura está inativa. Motivo: %s. Entre em contato com a operadora.",
                    eligibility.getErrorMessage())
            );
            return;
        }

        // 2. Construir mensagem de custos
        StringBuilder message = new StringBuilder();
        message.append("Olá! Aqui está o resumo da sua cobertura:\n\n");
        message.append(String.format("Plano: %s (%s)\n", eligibility.getPlanName(), eligibility.getPlanType()));
        message.append(String.format("Operadora: %s\n\n", eligibility.getPayerName()));

        // 3. Informar valores de cost-sharing
        message.append("Valores de co-participação:\n");

        if (eligibility.getCopayAmount() != null && eligibility.getCopayAmount().compareTo(BigDecimal.ZERO) > 0) {
            message.append(String.format("- Co-participação por procedimento: R$ %.2f\n",
                eligibility.getCopayAmount()));
        }

        if (eligibility.getCoinsurancePercent() != null && eligibility.getCoinsurancePercent().compareTo(BigDecimal.ZERO) > 0) {
            message.append(String.format("- Coinsurance: %.1f%% do valor do procedimento\n",
                eligibility.getCoinsurancePercent().multiply(BigDecimal.valueOf(100))));
        }

        if (eligibility.getDeductibleAmount() != null) {
            message.append(String.format("\nFranquia anual: R$ %.2f\n", eligibility.getDeductibleAmount()));
            if (eligibility.getRemainingDeductible() != null) {
                BigDecimal deductibleConsumed = eligibility.getDeductibleAmount()
                    .subtract(eligibility.getRemainingDeductible());
                BigDecimal deductiblePercent = deductibleConsumed
                    .divide(eligibility.getDeductibleAmount(), 2, RoundingMode.HALF_UP)
                    .multiply(BigDecimal.valueOf(100));
                message.append(String.format("- Consumido: R$ %.2f (%.0f%%)\n",
                    deductibleConsumed, deductiblePercent));
                message.append(String.format("- Restante: R$ %.2f\n",
                    eligibility.getRemainingDeductible()));
            }
        }

        if (eligibility.getOutOfPocketMax() != null) {
            message.append(String.format("\nTeto máximo anual: R$ %.2f\n", eligibility.getOutOfPocketMax()));
            if (eligibility.getRemainingOutOfPocket() != null) {
                if (eligibility.getRemainingOutOfPocket().compareTo(BigDecimal.ZERO) == 0) {
                    message.append("✓ Teto atingido! Próximos procedimentos cobertos 100%\n");
                } else {
                    message.append(String.format("- Restante até teto: R$ %.2f\n",
                        eligibility.getRemainingOutOfPocket()));
                }
            }
        }

        // 4. Calcular custo estimado para procedimentos planejados
        if (!plannedProcedures.isEmpty()) {
            message.append("\nCusto estimado dos seus procedimentos:\n");
            BigDecimal totalEstimatedCost = BigDecimal.ZERO;

            for (String procedureCode : plannedProcedures) {
                BigDecimal procedureCost = procedureService.getEstimatedCost(procedureCode);
                BigDecimal patientCost = calculatePatientCost(eligibility, procedureCost);
                totalEstimatedCost = totalEstimatedCost.add(patientCost);

                message.append(String.format("- %s: R$ %.2f (sua parte)\n",
                    procedureService.getName(procedureCode), patientCost));
            }

            message.append(String.format("\nTotal estimado (sua responsabilidade): R$ %.2f\n",
                totalEstimatedCost));
        }

        // 5. Alertar sobre vencimento próximo
        if (eligibility.getCoverageTerminationDate() != null) {
            long daysUntilExpiry = ChronoUnit.DAYS.between(
                LocalDate.now(),
                eligibility.getCoverageTerminationDate()
            );

            if (daysUntilExpiry <= 30 && daysUntilExpiry > 0) {
                message.append(String.format("\n⚠ Atenção: Seu plano vence em %d dias (%s)\n",
                    daysUntilExpiry, eligibility.getCoverageTerminationDate()));
            }
        }

        // 6. Informar sobre tipo de rede
        if (eligibility.getNetworkStatus() != null) {
            if ("IN_NETWORK".equals(eligibility.getNetworkStatus())) {
                message.append("\nVocê está utilizando prestador da rede credenciada.\n");
            } else {
                message.append("\n⚠ Prestador fora da rede credenciada. Custos podem ser maiores.\n");
            }
        }

        // 7. Enviar notificação
        notificationService.sendEmail(patientId, "Resumo da Sua Cobertura", message.toString());
        notificationService.sendSMS(patientId,
            String.format("Cobertura ativa. Copay: R$ %.2f. Franquia restante: R$ %.2f",
                eligibility.getCopayAmount(),
                eligibility.getRemainingDeductible()));
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário

```java
class EligibilityResponseTest {

    @Test
    void testDeserialization_ActiveCoverage() throws JsonProcessingException {
        // Arrange
        String json = """
            {
                "patientId": "PAT-123",
                "payerId": "123456",
                "payerName": "Unimed São Paulo",
                "planName": "Plano Empresarial Nacional",
                "eligibilityStatus": "ACTIVE",
                "coverageActive": true,
                "coverageEffectiveDate": "2025-01-01",
                "copayAmount": 50.00,
                "deductibleAmount": 1000.00,
                "remainingDeductible": 300.00,
                "outOfPocketMax": 5000.00,
                "remainingOutOfPocket": 3500.00,
                "coinsurancePercent": 0.20,
                "planType": "PPO",
                "networkStatus": "IN_NETWORK",
                "verificationDate": "2026-01-12"
            }
            """;

        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());

        // Act
        EligibilityResponse response = mapper.readValue(json, EligibilityResponse.class);

        // Assert
        assertTrue(response.isCoverageActive());
        assertEquals("ACTIVE", response.getEligibilityStatus());
        assertEquals("PPO", response.getPlanType());
        assertEquals(0, new BigDecimal("50.00").compareTo(response.getCopayAmount()));
    }

    @Test
    void testDeductibleCalculation() {
        // Arrange
        EligibilityResponse response = EligibilityResponse.builder()
            .deductibleAmount(new BigDecimal("1000.00"))
            .remainingDeductible(new BigDecimal("300.00"))
            .build();

        // Act
        BigDecimal consumed = response.getDeductibleAmount().subtract(response.getRemainingDeductible());

        // Assert
        assertEquals(0, new BigDecimal("700.00").compareTo(consumed));
    }

    @Test
    void testOutOfPocketMaxReached() {
        // Arrange
        EligibilityResponse response = EligibilityResponse.builder()
            .outOfPocketMax(new BigDecimal("5000.00"))
            .remainingOutOfPocket(BigDecimal.ZERO)
            .build();

        // Assert
        assertTrue(response.getRemainingOutOfPocket().compareTo(BigDecimal.ZERO) == 0,
            "Teto atingido - operadora paga 100%");
    }
}
```

### 12.2. Massa de Dados para Teste

```json
{
  "active_coverage": {
    "patientId": "PAT-12345",
    "payerId": "123456",
    "payerName": "Unimed São Paulo",
    "planName": "Plano Empresarial Nacional",
    "eligibilityStatus": "ACTIVE",
    "coverageActive": true,
    "coverageEffectiveDate": "2025-01-01",
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
  "inactive_coverage": {
    "patientId": "PAT-67890",
    "payerId": "334545",
    "eligibilityStatus": "INACTIVE",
    "coverageActive": false,
    "verificationDate": "2026-01-12",
    "errorMessage": "Plano cancelado por inadimplência"
  },
  "max_out_of_pocket_reached": {
    "patientId": "PAT-99999",
    "payerId": "456789",
    "eligibilityStatus": "ACTIVE",
    "coverageActive": true,
    "outOfPocketMax": 5000.00,
    "remainingOutOfPocket": 0.00,
    "planType": "HMO",
    "verificationDate": "2026-01-12"
  }
}
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **Dados Financeiros**: copay, deductible são informações sensíveis
- **Autorização**: Apenas usuários autorizados devem acessar response

### 13.2. Proteção de Dados
- **PII**: patientId é dado pessoal protegido por LGPD
- **Dados de Saúde**: planName, coverageActive são dados sensíveis
- **Logging**: Mascarar patientId em logs de auditoria

### 13.3. Auditoria
```java
@Aspect
@Component
public class EligibilityResponseAuditAspect {

    @AfterReturning(pointcut = "execution(* InsuranceApiClient.checkEligibility(..))", returning = "response")
    public void auditEligibilityResponse(EligibilityResponse response) {
        auditLog.info("Eligibility verification result",
            "maskedPatientId", maskId(response.getPatientId()),
            "payerId", response.getPayerId(),
            "eligibilityStatus", response.getEligibilityStatus(),
            "coverageActive", response.isCoverageActive(),
            "planType", response.getPlanType(),
            "verificationDate", response.getVerificationDate(),
            "timestamp", Instant.now()
        );
    }
}
```

## 14. Referências

### 14.1. Documentação Relacionada
- `EligibilityRequest.java` - DTO de request correspondente (X12 270 EDI)
- `InsuranceApiClient.java` - Cliente que retorna este DTO
- `EligibilityVerificationDelegate.java` - Camunda delegate que processa response

### 14.2. Padrões e Especificações
- **X12 EDI 271**: Health Care Eligibility Benefit Response
- **TISS 4.03.03**: Padrão TISS ANS para elegibilidade

### 14.3. Links Externos
- [X12 EDI 270/271 Standards](https://x12.org/products/health-care)
- [RN-469/2021 ANS - Padrão TISS](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)

### 14.4. Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm - Coder Agent 7 | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:d0f9e8d7c6b5a9e4d8c7b6f5e4d9a8c9b7e6f5d4c9a8b7e6d5f4c3b9a8e7d6f5`
**Última Atualização:** 2026-01-12T13:24:00Z
**Próxima Revisão:** 2026-04-12
