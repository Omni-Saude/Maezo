# RN-LISResultDTO - Resultado Laboratorial (FHIR DiagnosticReport)

## Identificação
- **ID**: RN-LISResultDTO
- **Nome**: LIS Result Data Transfer Object
- **Categoria**: Integration/Data Model
- **Subcategoria**: HL7 FHIR DTO
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/lis/dto/LISResultDTO.java`

---

## Descrição

Objeto de transferência de dados que representa o resultado de um exame laboratorial seguindo o padrão HL7 FHIR R4 DiagnosticReport. Este DTO encapsula os resultados dos testes, observações individuais, interpretações e laudos gerados pelo LIS.

**Recurso FHIR**: DiagnosticReport
**URL FHIR**: http://hl7.org/fhir/R4/diagnosticreport.html

---

## Estrutura de Dados

### Atributos

```java
@Data
public class LISResultDTO {
    private String id;                          // ID único do resultado
    private String identifier;                  // Identificador de negócio
    private String status;                      // Status do resultado
    private String category;                    // Categoria (laboratory)
    private String code;                        // Código LOINC do teste
    private String patientId;                   // Referência ao paciente
    private String encounterId;                 // Referência ao encontro
    private String orderId;                     // Referência ao pedido (ServiceRequest)
    private LocalDateTime effectiveDateTime;    // Data/hora da observação
    private LocalDateTime issued;               // Data/hora de liberação
    private String performerId;                 // Profissional que realizou
    private List<ObservationDTO> observations;  // Observações individuais
    private String conclusion;                  // Conclusão textual
    private String interpretationCode;          // Código de interpretação (N/A/H/L)
    private List<String> presentedFormUrls;     // URLs dos laudos em PDF
}
```

---

## Mapeamento FHIR DiagnosticReport

### Exemplo JSON FHIR
```json
{
  "resourceType": "DiagnosticReport",
  "id": "report-67890",
  "identifier": [
    {
      "system": "http://hospital.com/lis/reports",
      "value": "RESULT-2024-005678"
    }
  ],
  "status": "final",
  "category": [
    {
      "coding": [
        {
          "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
          "code": "LAB",
          "display": "Laboratory"
        }
      ]
    }
  ],
  "code": {
    "coding": [
      {
        "system": "http://loinc.org",
        "code": "24331-1",
        "display": "Lipid panel - Serum or Plasma"
      }
    ]
  },
  "subject": {
    "reference": "Patient/123456"
  },
  "encounter": {
    "reference": "Encounter/enc-789"
  },
  "effectiveDateTime": "2024-01-15T09:30:00Z",
  "issued": "2024-01-15T14:20:00Z",
  "performer": [
    {
      "reference": "Practitioner/biomedico-123"
    }
  ],
  "result": [
    {
      "reference": "Observation/obs-cholesterol"
    },
    {
      "reference": "Observation/obs-hdl"
    },
    {
      "reference": "Observation/obs-ldl"
    }
  ],
  "conclusion": "Dislipidemia leve. Valores de LDL acima do recomendado.",
  "conclusionCode": [
    {
      "coding": [
        {
          "system": "http://snomed.info/sct",
          "code": "166830008",
          "display": "Serum cholesterol raised"
        }
      ]
    }
  ],
  "presentedForm": [
    {
      "contentType": "application/pdf",
      "url": "https://lis-storage.hospital.com/reports/report-67890.pdf"
    }
  ]
}
```

---

## Atributos Detalhados

### 1. id
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Identificador único do resultado no LIS
- **Exemplo**: `"report-67890"`
- **Uso**: Rastreamento e referência cruzada

### 2. identifier
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Identificador de negócio do resultado
- **Exemplo**: `"RESULT-2024-005678"`
- **Uso**: Impressão em laudos, referência humana

### 3. status
- **Tipo**: String (Enum)
- **Obrigatório**: Sim
- **Valores Possíveis**:
  - `registered` - Registrado, coleta realizada
  - `partial` - Resultado parcial disponível
  - `preliminary` - Resultado preliminar (pode mudar)
  - `final` - Resultado final (liberado)
  - `amended` - Resultado alterado após liberação
  - `corrected` - Resultado corrigido (erro anterior)
  - `cancelled` - Resultado cancelado
  - `entered-in-error` - Entrada errônea

**Regras de Faturamento**:
```java
public boolean canBeBilled(LISResultDTO result) {
    return Set.of("final", "amended", "corrected").contains(result.getStatus());
}
```

**Importância Crítica**:
- Apenas resultados `final`, `amended` ou `corrected` devem ser faturados
- `preliminary` indica que exame ainda não foi validado/liberado
- `cancelled` não deve gerar cobrança

---

### 4. category
- **Tipo**: String (CodeableConcept)
- **Obrigatório**: Sim
- **Valor Esperado**: `"laboratory"`
- **Sistema**: http://terminology.hl7.org/CodeSystem/v2-0074

**Validação**:
```java
if (!"laboratory".equals(result.getCategory())) {
    log.warn("Categoria inesperada em LIS: {}", result.getCategory());
}
```

---

### 5. code (LOINC)
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Código LOINC do teste/painel realizado
- **Sistema**: http://loinc.org
- **Exemplos**:
  - `24331-1` - Lipid panel
  - `58410-2` - Complete blood count (hemogram)
  - `24323-8` - Comprehensive metabolic panel

**Uso no Faturamento**:
```java
String tissCode = codeMapper.loincToTiss(result.getCode());
BigDecimal valor = contratoService.getValorExame(tissCode, operadoraId);
```

---

### 6. patientId
- **Tipo**: String
- **Obrigatório**: Sim
- **Formato**: `"Patient/{id}"`
- **Exemplo**: `"Patient/123456"`
- **Validação**: Deve corresponder ao paciente do encontro

---

### 7. encounterId
- **Tipo**: String
- **Obrigatório**: Sim (crítico para faturamento)
- **Formato**: `"Encounter/{id}"`
- **Exemplo**: `"Encounter/enc-789"`

**Importância**:
- Vincula resultado ao episódio de cuidado
- Necessário para incluir na guia TISS correta
- Valida que exame foi realizado durante internação/consulta

---

### 8. orderId
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Referência ao pedido original (ServiceRequest)
- **Formato**: `"ServiceRequest/order-12345"`

**Uso**:
- Rastreabilidade: vincula resultado ao pedido médico
- Validação: garante que exame foi solicitado
- Auditoria: comprova necessidade clínica

**Validação**:
```java
// RN-LISRESULT-01: Resultado deve ter pedido correspondente
LISOrderDTO order = lisClient.getOrderById(result.getOrderId(), apiKey);
if (order == null) {
    throw new ValidationException("Resultado sem pedido: " + result.getId());
}
```

---

### 9. effectiveDateTime
- **Tipo**: LocalDateTime
- **Obrigatório**: Sim
- **Descrição**: Data/hora da coleta ou observação
- **Formato ISO**: `2024-01-15T09:30:00`

**Uso**:
- Data de realização para faturamento
- Validação de vigência de plano de saúde
- Cálculo de SLA (tempo até liberação)

---

### 10. issued
- **Tipo**: LocalDateTime
- **Obrigatório**: Sim
- **Descrição**: Data/hora de liberação do resultado
- **Formato ISO**: `2024-01-15T14:20:00`

**Métricas de Qualidade**:
```java
Duration turnaroundTime = Duration.between(
    result.getEffectiveDateTime(),
    result.getIssued()
);

// Alertar se TAT (Turnaround Time) > SLA
if (turnaroundTime.toHours() > 24) {
    qualityAlert("Resultado liberado após SLA: " + result.getId());
}
```

---

### 11. performerId
- **Tipo**: String
- **Obrigatório**: Sim
- **Descrição**: Profissional que realizou/validou o exame
- **Formato**: `"Practitioner/{id}"`
- **Exemplo**: `"Practitioner/biomedico-123"`

**Validações Regulatórias**:
- Biomédico/Farmacêutico deve ter registro ativo (CRBM/CRF)
- Necessário para auditoria ANS/Conselhos
- Responsabilidade técnica pelo resultado

---

### 12. observations
- **Tipo**: List<ObservationDTO>
- **Obrigatório**: Não (mas geralmente presente)
- **Descrição**: Lista de observações individuais (valores de testes)

**Estrutura de Observation**:
```java
public class ObservationDTO {
    private String id;
    private String code;           // LOINC code
    private String display;         // Nome do teste
    private String value;           // Valor medido
    private String unit;            // Unidade (mg/dL, g/L, etc.)
    private String interpretation;  // N, A, H, L
    private String referenceRange;  // Valores de referência
    private String status;          // final, preliminary
}
```

**Exemplo**:
```json
{
  "code": "2093-3",
  "display": "Cholesterol [Mass/volume] in Serum or Plasma",
  "value": "220",
  "unit": "mg/dL",
  "interpretation": "H",
  "referenceRange": "< 200 mg/dL"
}
```

---

### 13. conclusion
- **Tipo**: String
- **Obrigatório**: Não
- **Descrição**: Texto livre com conclusão/interpretação do resultado
- **Exemplo**: `"Dislipidemia leve. Valores de LDL acima do recomendado."`

**Uso**:
- Anexo em guia TISS se operadora exigir laudo
- Suporte a recurso de glosa
- Documentação clínica

---

### 14. interpretationCode
- **Tipo**: String (Enum)
- **Obrigatório**: Não
- **Valores**:
  - `N` - Normal
  - `A` - Abnormal (anormal)
  - `H` - High (alto)
  - `L` - Low (baixo)
  - `HH` - Critically high (criticamente alto)
  - `LL` - Critically low (criticamente baixo)

**Uso em Auditoria**:
```java
// RN-LISRESULT-02: Resultados críticos devem ter notificação médica
if (Set.of("HH", "LL").contains(result.getInterpretationCode())) {
    notificationService.sendCriticalResultAlert(
        result.getOrderId(),
        result.getPatientId(),
        result.getId()
    );
}
```

---

### 15. presentedFormUrls
- **Tipo**: List<String>
- **Obrigatório**: Não
- **Descrição**: URLs de laudos em formato PDF ou imagem
- **Exemplo**: `["https://lis-storage.hospital.com/reports/report-67890.pdf"]`

**Uso**:
1. **Recurso de Glosa**: Anexar laudo como evidência
2. **Auditoria Externa**: Operadora pode solicitar laudos
3. **Prontuário Eletrônico**: Integração com EMR

**Configuração de Acesso**:
```java
// URLs devem ser temporárias (presigned) ou requerer autenticação
if (result.getPresentedFormUrls() != null) {
    for (String url : result.getPresentedFormUrls()) {
        String presignedUrl = s3Service.generatePresignedUrl(url, Duration.ofHours(24));
        anexosGuia.add(presignedUrl);
    }
}
```

---

## Regras de Negócio

### RN-LISRESULT-01: Resultado Sem Pedido Correspondente
**Descrição**: Todo resultado deve ter um pedido (ServiceRequest) correspondente.

**Validação**:
```java
@Service
public class ResultValidationService {

    public void validateResultHasOrder(LISResultDTO result) {
        if (result.getOrderId() == null || result.getOrderId().isEmpty()) {
            throw new ValidationException(
                "Resultado " + result.getId() + " sem referência a pedido"
            );
        }

        try {
            LISOrderDTO order = lisClient.getOrderById(result.getOrderId(), apiKey);
            if (order == null) {
                throw new ValidationException(
                    "Pedido " + result.getOrderId() + " não encontrado para resultado " + result.getId()
                );
            }
        } catch (FeignException.NotFound e) {
            throw new ValidationException(
                "Pedido " + result.getOrderId() + " não existe no LIS"
            );
        }
    }
}
```

---

### RN-LISRESULT-02: Resultados Críticos
**Descrição**: Resultados com interpretação HH ou LL (criticamente alto/baixo) devem gerar notificação imediata ao médico solicitante.

**Implementação**:
```java
@Service
public class CriticalResultNotificationService {

    public void processCriticalResult(LISResultDTO result) {
        if (!Set.of("HH", "LL").contains(result.getInterpretationCode())) {
            return; // Não é crítico
        }

        // Obter médico solicitante
        LISOrderDTO order = lisClient.getOrderById(result.getOrderId(), apiKey);
        String medicoId = order.getOrderingProviderId();

        // Enviar notificação
        notificationService.sendUrgent(
            medicoId,
            "Resultado Crítico",
            String.format(
                "Paciente %s - Resultado crítico no exame %s: %s",
                result.getPatientId(),
                result.getCode(),
                getCriticalValuesDescription(result)
            )
        );

        // Registrar log de auditoria
        auditService.logCriticalResultNotification(
            result.getId(),
            medicoId,
            LocalDateTime.now()
        );
    }

    private String getCriticalValuesDescription(LISResultDTO result) {
        return result.getObservations().stream()
            .filter(obs -> Set.of("HH", "LL").contains(obs.getInterpretation()))
            .map(obs -> obs.getDisplay() + ": " + obs.getValue() + " " + obs.getUnit())
            .collect(Collectors.joining(", "));
    }
}
```

---

### RN-LISRESULT-03: Validação de Status para Faturamento
**Descrição**: Apenas resultados com status "final", "amended" ou "corrected" podem ser faturados.

**Implementação**:
```java
public class BillingEligibilityService {

    private static final Set<String> BILLABLE_STATUSES =
        Set.of("final", "amended", "corrected");

    public boolean isResultBillable(LISResultDTO result) {
        // Verificar status
        if (!BILLABLE_STATUSES.contains(result.getStatus())) {
            log.info("Resultado {} não faturável: status={}",
                result.getId(), result.getStatus());
            return false;
        }

        // Verificar se há data de realização
        if (result.getEffectiveDateTime() == null) {
            log.warn("Resultado {} sem data de realização", result.getId());
            return false;
        }

        // Verificar se resultado foi emitido
        if (result.getIssued() == null) {
            log.warn("Resultado {} não foi emitido ainda", result.getId());
            return false;
        }

        return true;
    }
}
```

---

### RN-LISRESULT-04: Anexo de Laudos em Guia TISS
**Descrição**: Operadoras podem exigir anexo de laudos para determinados exames.

**Implementação**:
```java
@Service
public class ReportAttachmentService {

    public void attachReportsToGuia(GuiaTISS guia, List<LISResultDTO> results) {
        for (LISResultDTO result : results) {
            if (requiresAttachment(result.getCode(), guia.getOperadoraId())) {
                if (result.getPresentedFormUrls() != null && !result.getPresentedFormUrls().isEmpty()) {
                    String reportUrl = result.getPresentedFormUrls().get(0);

                    // Gerar URL temporária (24h)
                    String presignedUrl = generatePresignedUrl(reportUrl);

                    guia.addAnexo(new AnexoTISS(
                        result.getCode(),
                        "application/pdf",
                        presignedUrl,
                        "Laudo Laboratorial"
                    ));
                } else {
                    log.warn("Laudo obrigatório não encontrado para exame: {}", result.getCode());
                    guia.addPendencia("Laudo não disponível: " + result.getCode());
                }
            }
        }
    }

    private boolean requiresAttachment(String loincCode, String operadoraId) {
        // Consultar regras contratuais
        return contratoService.exigeAnexoLaudo(operadoraId, loincCode);
    }
}
```

---

## Análise de Turnaround Time (TAT)

### Cálculo de TAT
**Definição**: Tempo entre coleta (effectiveDateTime) e liberação (issued)

```java
@Service
public class TATAnalysisService {

    public Duration calculateTAT(LISResultDTO result) {
        return Duration.between(
            result.getEffectiveDateTime(),
            result.getIssued()
        );
    }

    public TATMetrics analyzeTATForEncounter(String encounterId) {
        List<LISResultDTO> results = lisClient.getResultsByEncounter(encounterId);

        TATMetrics metrics = new TATMetrics();
        List<Duration> tats = new ArrayList<>();

        for (LISResultDTO result : results) {
            Duration tat = calculateTAT(result);
            tats.add(tat);

            // Alertar se TAT > SLA
            Duration sla = getSLAForTest(result.getCode());
            if (tat.compareTo(sla) > 0) {
                metrics.addSLAViolation(result.getCode(), tat, sla);
            }
        }

        metrics.setAverageTAT(calculateAverage(tats));
        metrics.setMedianTAT(calculateMedian(tats));
        metrics.setMaxTAT(Collections.max(tats));

        return metrics;
    }

    private Duration getSLAForTest(String loincCode) {
        // SLAs típicos
        Map<String, Duration> slas = Map.of(
            "718-7", Duration.ofHours(4),    // Hemoglobina: 4h
            "2951-2", Duration.ofHours(24),  // Sódio: 24h
            "600-7", Duration.ofHours(72)    // Cultura de bactérias: 72h
        );
        return slas.getOrDefault(loincCode, Duration.ofHours(24));
    }
}
```

---

## Exemplos de Uso

### Exemplo 1: Processar Resultados para Faturamento
```java
@Service
public class LabResultBillingService {

    public List<GuiaItem> processResults(String encounterId, String operadoraId) {
        List<GuiaItem> items = new ArrayList<>();

        // 1. Obter todos os resultados do encontro
        List<LISResultDTO> results = getResultsForEncounter(encounterId);

        for (LISResultDTO result : results) {
            // 2. Validar se é faturável
            if (!isResultBillable(result)) {
                continue;
            }

            // 3. Mapear LOINC → TUSS
            String tissCode = codeMapper.loincToTiss(result.getCode());

            // 4. Obter valor contratual
            BigDecimal valor = contratoService.getValorExame(tissCode, operadoraId);

            // 5. Criar item de guia
            GuiaItem item = new GuiaItem();
            item.setCodigoTUSS(tissCode);
            item.setQuantidade(1);
            item.setValorUnitario(valor);
            item.setDataRealizacao(result.getEffectiveDateTime().toLocalDate());

            // 6. Anexar laudo se necessário
            if (requiresAttachment(result.getCode(), operadoraId)) {
                if (result.getPresentedFormUrls() != null && !result.getPresentedFormUrls().isEmpty()) {
                    item.setAnexoLaudo(result.getPresentedFormUrls().get(0));
                }
            }

            items.add(item);
        }

        return items;
    }

    private List<LISResultDTO> getResultsForEncounter(String encounterId) {
        // Obter pedidos do encontro
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(encounterId, apiKey);

        // Para cada pedido, obter resultados
        return orders.stream()
            .flatMap(order -> lisClient.getResultsByOrder(order.getId(), apiKey).stream())
            .collect(Collectors.toList());
    }
}
```

---

### Exemplo 2: Validação de Completude de Resultados
```java
@Service
public class ResultCompletenessService {

    public CompletenessReport checkCompleteness(String encounterId) {
        CompletenessReport report = new CompletenessReport();

        // Obter pedidos
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(encounterId, apiKey);

        for (LISOrderDTO order : orders) {
            // Obter resultados do pedido
            List<LISResultDTO> results = lisClient.getResultsByOrder(order.getId(), apiKey);

            if (results.isEmpty()) {
                report.addMissingResult(order.getId(), "Nenhum resultado encontrado");
                continue;
            }

            // Verificar status dos resultados
            for (LISResultDTO result : results) {
                if ("preliminary".equals(result.getStatus())) {
                    report.addPendingResult(result.getId(), "Resultado preliminar");
                } else if ("partial".equals(result.getStatus())) {
                    report.addPendingResult(result.getId(), "Resultado parcial");
                } else if ("final".equals(result.getStatus())) {
                    report.addCompletedResult(result.getId());
                }
            }
        }

        return report;
    }
}
```

---

## Referências Técnicas

1. **FHIR DiagnosticReport**: http://hl7.org/fhir/R4/diagnosticreport.html
2. **FHIR Observation**: http://hl7.org/fhir/R4/observation.html
3. **LOINC**: https://loinc.org/
4. **HL7 Diagnostic Service Section**: http://terminology.hl7.org/CodeSystem/v2-0074

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
