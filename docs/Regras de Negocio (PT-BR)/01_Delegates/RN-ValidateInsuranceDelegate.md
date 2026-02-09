# RN-ValidateInsuranceDelegate - Validação de Seguro de Saúde

## Identificação
- **ID**: RN-ELIG-002
- **Nome**: ValidateInsuranceDelegate
- **Categoria**: Elegibilidade
- **Versão**: 1.0.0
- **Bean BPMN**: `validateInsuranceDelegate`

## Visão Geral
Delegate responsável por validar a elegibilidade do seguro de saúde do paciente, verificando se a cobertura está ativa e se o plano é válido para a data de serviço.

## Responsabilidades

### 1. Validação de Elegibilidade
- Verifica elegibilidade do paciente junto à operadora
- Valida número da carteirinha do plano
- Confirma cobertura ativa para data de serviço
- Obtém status de elegibilidade atualizado

### 2. Verificação de Cobertura
- Valida se plano está ativo
- Verifica validade temporal da cobertura
- Confirma dados da operadora (payer)
- Valida relação paciente-plano

### 3. Tratamento de Erros
- Lança erro BPMN se cobertura inativa
- Registra detalhes da validação
- Propaga informações para etapas subsequentes

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `patient_id` | String | Sim | Identificador único do paciente |
| `payer_id` | String | Sim | Identificador da operadora de saúde |
| `insurance_card_number` | String | Sim | Número da carteirinha do plano |
| `service_date` | LocalDate | Não | Data do serviço (default: hoje) |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `insurance_valid` | Boolean | `true` se seguro é válido para data de serviço |
| `coverage_active` | Boolean | `true` se cobertura está ativa |
| `eligibility_status` | String | Status de elegibilidade retornado pela operadora |
| `payer_name` | String | Nome da operadora de saúde |

## Erros BPMN

| Código | Mensagem | Causa | Ação |
|--------|----------|-------|------|
| `INSURANCE_INACTIVE` | Insurance not active | Cobertura do plano está inativa | Solicitar outro plano ou pagamento particular |

## Algoritmo de Validação

```
1. Validar parâmetros de entrada:
   - patient_id não pode ser nulo
   - payer_id não pode ser nulo
   - insurance_card_number não pode ser nulo

2. Obter service_date:
   - Se não fornecido, usar data atual (LocalDate.now())

3. Consultar elegibilidade via EligibilityVerificationService:
   - verifyEligibility(patientId, payerId, insuranceCardNumber, serviceDate)
   - Retorna objeto EligibilityResponse

4. Validar status da cobertura:
   - isInsuranceValid(eligibilityResponse, serviceDate)
   - Retorna true/false

5. Verificar cobertura ativa:
   - Se coverage_active == false:
     → throw BpmnError("INSURANCE_INACTIVE")

6. Persistir resultados:
   - insurance_valid
   - coverage_active
   - eligibility_status
   - payer_name
```

## Integração com EligibilityVerificationService

### Método de Verificação
```java
EligibilityResponse eligibility =
    eligibilityService.verifyEligibility(
        patientId,
        payerId,
        insuranceCardNumber,
        serviceDate
    );
```

### Validação de Seguro
```java
boolean insuranceValid =
    eligibilityService.isInsuranceValid(
        eligibility,
        serviceDate
    );
```

## Estrutura de EligibilityResponse

```java
class EligibilityResponse {
    boolean coverageActive;      // Cobertura está ativa?
    String eligibilityStatus;    // Status detalhado
    String payerName;            // Nome da operadora
    LocalDate coverageStartDate; // Data de início da cobertura
    LocalDate coverageEndDate;   // Data de fim da cobertura
    List<CoverageBenefit> benefits; // Benefícios cobertos
}
```

## Casos de Uso

### Caso 1: Validação Bem-Sucedida
**Entrada**:
```json
{
  "patient_id": "PAT-12345",
  "payer_id": "UNIMED-SP",
  "insurance_card_number": "123456789012345",
  "service_date": "2025-12-25"
}
```

**Saída**:
```json
{
  "insurance_valid": true,
  "coverage_active": true,
  "eligibility_status": "ACTIVE",
  "payer_name": "Unimed São Paulo"
}
```

### Caso 2: Cobertura Inativa
**Entrada**:
```json
{
  "patient_id": "PAT-67890",
  "payer_id": "BRADESCO-SAUDE",
  "insurance_card_number": "987654321098765",
  "service_date": "2025-12-25"
}
```

**Erro BPMN**:
```
BpmnError("INSURANCE_INACTIVE", "Insurance not active")
```

**Log**:
```
Insurance validation successful - PatientId: PAT-67890
```

### Caso 3: Validação com Data Padrão
**Entrada**:
```json
{
  "patient_id": "PAT-11111",
  "payer_id": "AMIL",
  "insurance_card_number": "111222333444555"
  // service_date não fornecido
}
```

**Comportamento**:
- service_date será definido como `LocalDate.now()`
- Validação procede normalmente com data atual

## Regras de Negócio

### RN-ELIG-002-001: Validação de Parâmetros
- **Descrição**: Parâmetros obrigatórios devem ser fornecidos
- **Prioridade**: CRÍTICA
- **Validação**: `patient_id != null && payer_id != null && insurance_card_number != null`

### RN-ELIG-002-002: Cobertura Ativa Obrigatória
- **Descrição**: Cobertura deve estar ativa para prosseguir
- **Prioridade**: CRÍTICA
- **Ação**: Se `coverage_active == false`, lançar erro BPMN

### RN-ELIG-002-003: Data de Serviço Padrão
- **Descrição**: Se data de serviço não fornecida, usar data atual
- **Prioridade**: MÉDIA
- **Implementação**: `service_date = LocalDate.now()`

## Integrações

### EligibilityVerificationService (Interno)
- **Método**: `verifyEligibility(patientId, payerId, insuranceCardNumber, serviceDate)`
- **Retorno**: `EligibilityResponse`
- **Método**: `isInsuranceValid(eligibility, serviceDate)`
- **Retorno**: `boolean`

### Integração com Operadoras (X12 270/271)
- **Protocolo**: X12 EDI 270 (Eligibility Inquiry) / 271 (Eligibility Response)
- **Timeout**: 30 segundos
- **Retry**: 3 tentativas com backoff exponencial
- **Fallback**: Consultar cache de elegibilidade se operadora indisponível

## Idempotência

**Requer Idempotência**: Não

**Parâmetros de Idempotência**:
```java
Map<String, Object> params = {
    "patient_id": patientId,
    "payer_id": payerId
}
```

**Justificativa**: Validação de elegibilidade é operação read-only e pode ser executada múltiplas vezes sem efeitos colaterais.

## Conformidade Regulatória

### TISS 4.0 (ANS)
- Valida carteirinha conforme padrão TISS
- Verifica elegibilidade antes de gerar guia

### LGPD
- Não registra dados sensíveis em logs
- Apenas IDs são persistidos

## Métricas e KPIs

### Indicadores de Performance
- **Taxa de Sucesso de Validação**: `(validações bem-sucedidas / total) * 100%`
- **Taxa de Coberturas Inativas**: `(INSURANCE_INACTIVE errors / total) * 100%`
- **Tempo Médio de Resposta**: `AVG(response_time_ms)`

### Metas
- Taxa de Sucesso > 95%
- Taxa de Coberturas Inativas < 5%
- Tempo Médio de Resposta < 2 segundos

## Dependências
- `EligibilityVerificationService`: Serviço de verificação de elegibilidade
- Integração X12 270/271 com operadoras
- Cache de elegibilidade (Redis/Hazelcast)

## Tratamento de Timeout

Se integração com operadora falhar:
1. Consultar cache de elegibilidade
2. Se cache válido (< 24h), usar dados em cache
3. Se cache expirado, lançar erro técnico para retry

## Versionamento
- **v1.0.0**: Implementação inicial com X12 270/271

## Referências
- TISS 4.0: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar
- X12 270/271: https://x12.org/products/eligibility-inquiry-and-response-270-271
- RN-ELG-VerifyPatientEligibility: Documentação de verificação de elegibilidade de paciente
- RN-ELG-CheckCoverage: Documentação de verificação de cobertura
