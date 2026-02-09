# RN-PACSClient - Cliente de Integração com Sistema PACS

## Identificação
- **ID**: RN-PACSClient
- **Nome**: PACS (Picture Archiving and Communication System) Client
- **Categoria**: Integration/External System
- **Subcategoria**: Medical Imaging Integration
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/pacs/PACSClient.java`

---

## Descrição

Cliente Feign para integração com o Sistema de Arquivamento e Comunicação de Imagens (PACS), responsável por gerenciar estudos de imagem médica, incluindo radiografias, tomografias, ressonâncias e ultrassons. Utiliza padrões DICOM e HL7 FHIR para interoperabilidade.

**Padrão de Integração**: HL7 FHIR R4 + DICOM
**Recursos FHIR Utilizados**:
- ImagingStudy (estudos de imagem)
- ImagingSeries (séries de imagens)
- DocumentReference (relatórios radiológicos)

**Padrões DICOM**:
- Study Instance UID
- Series Instance UID
- Modality (CT, MR, XR, US, etc.)

---

## Propósito e Objetivo

### Objetivo Principal
Fornecer interface padronizada para consulta de estudos de imagem médica, necessários para validação de procedimentos diagnósticos e faturamento de exames de radiologia no ciclo de receita hospitalar.

### Problema que Resolve
- **Integração com radiologia**: Vincula exames de imagem a encontros hospitalares
- **Comprovação de realização**: Evidências para faturamento e auditoria
- **Acesso a laudos**: Recuperação de relatórios radiológicos para recursos de glosa
- **Rastreabilidade DICOM**: Identificação única de estudos e séries

---

## Relacionamento com o Processo BPMN

### Sub-processos Relacionados

1. **Pré-Validação de Prontuário**
   - Verifica se exames de imagem foram realizados
   - Valida disponibilidade de laudos radiológicos

2. **Codificação e Auditoria**
   - Confirma procedimentos radiológicos para faturamento
   - Valida coerência entre pedido médico e exame realizado

3. **Geração de Guia TISS**
   - Inclui procedimentos de imagem realizados
   - Anexa laudos quando exigido pela operadora

4. **Análise de Glosa**
   - Fornece evidências de realização (imagens disponíveis no PACS)
   - Acesso a laudos para contestação de glosas

---

## Padrões e Standards

### HL7 FHIR R4 ImagingStudy

```json
{
  "resourceType": "ImagingStudy",
  "id": "study-12345",
  "identifier": [
    {
      "system": "urn:dicom:uid",
      "value": "urn:oid:1.2.840.113619.2.55.3.1234567890.123"
    }
  ],
  "status": "available",
  "subject": {
    "reference": "Patient/123456"
  },
  "encounter": {
    "reference": "Encounter/enc-789"
  },
  "started": "2024-01-15T10:00:00Z",
  "modality": [
    {
      "system": "http://dicom.nema.org/resources/ontology/DCM",
      "code": "CT",
      "display": "Computed Tomography"
    }
  ],
  "description": "CT Abdomen with contrast",
  "numberOfSeries": 3,
  "numberOfInstances": 250,
  "procedureCode": [
    {
      "coding": [
        {
          "system": "http://www.ans.gov.br/tiss",
          "code": "40801403",
          "display": "Tomografia computadorizada do abdômen superior"
        }
      ]
    }
  ]
}
```

### DICOM Standards
- **Study Instance UID**: Identificador único global do estudo
- **Series Instance UID**: Identificador único de cada série
- **Modalities**: CT, MR, XR, US, CR, DX, MG, NM, PT, etc.

---

## Operações e Métodos

### 1. getStudiesByEncounter
**Endpoint**: `GET /ImagingStudy?encounter={encounterId}`

**Propósito**: Buscar todos os estudos de imagem de um encontro hospitalar

**Parâmetros**:
- `encounterId`: ID do encontro (atendimento)
- `Authorization`: Bearer token

**Retorno**: List<PACSStudyDTO>

**Uso no Ciclo de Receita**:
- Pré-validação: confirma realização de exames de imagem
- Faturamento: lista procedimentos radiológicos a cobrar
- Auditoria: valida coerência clínica

---

### 2. getStudyById
**Endpoint**: `GET /ImagingStudy/{studyId}`

**Propósito**: Obter detalhes específicos de um estudo de imagem

**Parâmetros**:
- `studyId`: ID do estudo
- `Authorization`: Bearer token

**Retorno**: PACSStudyDTO

**Uso**:
- Detalhamento para recurso de glosa
- Validação de características do estudo (modalidade, séries, imagens)

---

### 3. getStudySeries
**Endpoint**: `GET /ImagingStudy/{studyId}/series`

**Propósito**: Obter todas as séries de um estudo (detalhamento das aquisições)

**Parâmetros**:
- `studyId`: ID do estudo
- `Authorization`: Bearer token

**Retorno**: List<PACSSeriesDTO>

**Uso**:
- Validação técnica de protocolos de aquisição
- Faturamento de séries adicionais (ex: com e sem contraste)

---

### 4. updateStudyStatus
**Endpoint**: `PATCH /ImagingStudy/{studyId}?status={status}`

**Propósito**: Atualizar status de um estudo

**Parâmetros**:
- `studyId`: ID do estudo
- `status`: Novo status (AVAILABLE, UNAVAILABLE, CANCELLED)
- `Authorization`: Bearer token

**Retorno**: PACSStudyDTO atualizado

**Uso**:
- Cancelamento de exames não autorizados
- Sincronização de status para faturamento

---

### 5. getStudiesByPatient
**Endpoint**: `GET /ImagingStudy?patient={patientId}`

**Propósito**: Buscar histórico de exames de imagem de um paciente

**Parâmetros**:
- `patientId`: ID do paciente
- `Authorization`: Bearer token

**Retorno**: List<PACSStudyDTO>

**Uso**:
- Histórico radiológico do paciente
- Detecção de exames duplicados
- Análise de utilização de imagem

---

### 6. getStudyViewerUrl
**Endpoint**: `GET /ImagingStudy/{studyId}/viewer-url`

**Propósito**: Obter URL do visualizador DICOM para o estudo

**Parâmetros**:
- `studyId`: ID do estudo
- `Authorization**: Bearer token

**Retorno**: String (URL do visualizador web)

**Uso**:
- Link direto para visualização de imagens
- Integração com prontuário eletrônico
- Anexo em recursos de glosa (acesso a imagens)

**Exemplo de URL**:
```
https://pacs-viewer.hospital.com/viewer?studyUID=1.2.840.113619.2.55.3.1234567890.123
```

---

## Regras de Negócio Implementadas

### RN-PACS-01: Validação de Status para Faturamento
**Descrição**: Apenas estudos com status "available" podem ser faturados.

**Implementação**:
```java
public boolean isStudyBillable(PACSStudyDTO study) {
    if (!"available".equals(study.getStatus())) {
        log.info("Estudo {} não faturável: status={}", study.getId(), study.getStatus());
        return false;
    }

    // Validar que há laudo finalizado
    if (study.getReportStatus() == null || !"final".equals(study.getReportStatus())) {
        log.warn("Estudo {} sem laudo final", study.getId());
        return false;
    }

    return true;
}
```

---

### RN-PACS-02: Mapeamento de Modalidade para TUSS
**Descrição**: Modalidades DICOM devem ser mapeadas para códigos TUSS para faturamento.

**Tabela de Mapeamento**:
| Modalidade DICOM | Descrição | Exemplo TUSS |
|------------------|-----------|--------------|
| CT | Tomografia Computadorizada | 40801XXX |
| MR | Ressonância Magnética | 40901XXX |
| XR | Radiografia | 40101XXX |
| US | Ultrassom | 41001XXX |
| MG | Mamografia | 41101XXX |
| NM | Medicina Nuclear | 41201XXX |

**Implementação**:
```java
public String mapModalityToTUSSCategory(String modality) {
    switch (modality) {
        case "CT":
            return "408"; // Tomografia
        case "MR":
            return "409"; // Ressonância
        case "XR":
        case "CR":
        case "DX":
            return "401"; // Radiografia
        case "US":
            return "410"; // Ultrassom
        case "MG":
            return "411"; // Mamografia
        case "NM":
        case "PT":
            return "412"; // Medicina Nuclear
        default:
            throw new CodeMappingException("Modalidade não mapeada: " + modality);
    }
}
```

---

### RN-PACS-03: Validação de Laudo Radiológico
**Descrição**: Estudos devem ter laudo radiológico antes de serem faturados.

**Implementação**:
```java
@Service
public class RadiologyReportValidationService {

    public void validateReportAvailability(PACSStudyDTO study) {
        // Verificar se há laudo
        if (study.getReportText() == null || study.getReportText().isEmpty()) {
            throw new ValidationException(
                "Estudo " + study.getId() + " sem laudo radiológico"
            );
        }

        // Verificar status do laudo
        if (!"final".equals(study.getReportStatus())) {
            throw new ValidationException(
                "Laudo não finalizado: " + study.getReportStatus()
            );
        }

        // Verificar se há médico laudante
        if (study.getInterpretingRadiologist() == null) {
            throw new ValidationException(
                "Laudo sem médico radiologista identificado"
            );
        }
    }
}
```

---

### RN-PACS-04: Exames com Contraste
**Descrição**: Exames realizados com contraste devem ter código específico e acréscimo no valor.

**Implementação**:
```java
@Service
public class ContrastEnhancedExamService {

    public GuiaItem processContrastExam(PACSStudyDTO study, String baseCode) {
        GuiaItem item = new GuiaItem();

        // Verificar descrição do estudo para identificar contraste
        boolean hasContrast = study.getDescription() != null &&
            study.getDescription().toLowerCase().contains("contrast");

        if (hasContrast) {
            // Usar código TUSS específico para exame com contraste
            String contrastCode = getContrastEnhancedCode(baseCode);
            item.setCodigoTUSS(contrastCode);

            // Pode haver acréscimo no valor
            BigDecimal baseValue = contratoService.getValor(baseCode, operadoraId);
            BigDecimal contrastSupplement = baseValue.multiply(BigDecimal.valueOf(0.3)); // 30%
            item.setValorUnitario(baseValue.add(contrastSupplement));
        } else {
            item.setCodigoTUSS(baseCode);
            item.setValorUnitario(contratoService.getValor(baseCode, operadoraId));
        }

        return item;
    }
}
```

---

### RN-PACS-05: Séries Adicionais
**Descrição**: Estudos com múltiplas séries podem gerar cobrança adicional.

**Implementação**:
```java
public List<GuiaItem> processStudySeries(PACSStudyDTO study) {
    List<GuiaItem> items = new ArrayList<>();

    // Item principal (estudo)
    GuiaItem mainItem = new GuiaItem();
    mainItem.setCodigoTUSS(getStudyTUSSCode(study));
    items.add(mainItem);

    // Verificar se há séries adicionais cobráveis
    List<PACSSeriesDTO> series = pacsClient.getStudySeries(study.getId(), apiKey);

    // Exemplo: CT com séries pré e pós-contraste
    boolean hasPreContrast = series.stream()
        .anyMatch(s -> s.getDescription().contains("pre-contrast"));
    boolean hasPostContrast = series.stream()
        .anyMatch(s -> s.getDescription().contains("post-contrast"));

    if (hasPreContrast && hasPostContrast) {
        // Adicionar item para série adicional
        GuiaItem additionalSeries = new GuiaItem();
        additionalSeries.setCodigoTUSS(getAdditionalSeriesCode(study.getModality()));
        items.add(additionalSeries);
    }

    return items;
}
```

---

## Integração DICOM

### Study Instance UID
```java
// Exemplo de Study Instance UID DICOM
String studyInstanceUID = "1.2.840.113619.2.55.3.1234567890.123";

// Usar para queries DICOM nativas se necessário
DicomQuery query = new DicomQuery();
query.setStudyInstanceUID(studyInstanceUID);
query.setQueryLevel(QueryLevel.STUDY);
```

### Modalidades DICOM Padrão
```java
public enum DicomModality {
    CT("Computed Tomography"),
    MR("Magnetic Resonance"),
    XR("X-Ray"),
    US("Ultrasound"),
    CR("Computed Radiography"),
    DX("Digital Radiography"),
    MG("Mammography"),
    NM("Nuclear Medicine"),
    PT("PET Scan"),
    RF("Radioflurescence"),
    SC("Secondary Capture");

    private final String description;

    DicomModality(String description) {
        this.description = description;
    }
}
```

---

## Tratamento de Erros

### Códigos de Status HTTP

| Status | Significado | Ação |
|--------|-------------|------|
| 200 | OK | Processar resposta |
| 401 | Unauthorized | Renovar token |
| 404 | Not Found | Estudo não existe no PACS |
| 500 | Server Error | Retry com backoff |
| 503 | Service Unavailable | PACS indisponível |

---

## Segurança e Compliance

### DICOM Security
- **Encryption**: TLS 1.2+ para transferência
- **Authentication**: OAuth 2.0 / SAML
- **Audit Logs**: Registro de acesso a imagens (DICOM Audit Trail)

### LGPD
- **Dados Sensíveis**: Imagens médicas são dados de saúde protegidos
- **Anonimização**: Remover metadados identificadores quando necessário
- **Auditoria**: Log de todos os acessos

---

## Métricas e Monitoramento

### KPIs Recomendados

1. **Tempo de Resposta**: Latência das queries
   - Meta: < 3 segundos (p95)

2. **Disponibilidade PACS**: Uptime do sistema
   - Meta: > 99.9%

3. **Taxa de Estudos com Laudo**: % de estudos laudados
   - Meta: > 95% em 24h

4. **Taxa de Mapeamento Modalidade→TUSS**: % de modalidades mapeadas
   - Meta: 100%

---

## Exemplos de Uso

### Exemplo 1: Processar Estudos de Imagem para Faturamento
```java
@Service
public class ImagingBillingService {

    public List<GuiaItem> processImagingStudies(String encounterId, String operadoraId) {
        List<GuiaItem> items = new ArrayList<>();

        // Obter estudos do encontro
        List<PACSStudyDTO> studies = pacsClient.getStudiesByEncounter(encounterId, apiKey);

        for (PACSStudyDTO study : studies) {
            // Validar se é faturável
            if (!isStudyBillable(study)) {
                continue;
            }

            // Mapear estudo para código TUSS
            String tissCode = mapStudyToTUSS(study);

            GuiaItem item = new GuiaItem();
            item.setCodigoTUSS(tissCode);
            item.setDataRealizacao(study.getStarted().toLocalDate());
            item.setQuantidade(1);
            item.setValorUnitario(contratoService.getValor(tissCode, operadoraId));

            // Anexar link do visualizador se operadora exigir
            if (contratoService.exigeAnexoImagem(operadoraId, tissCode)) {
                String viewerUrl = pacsClient.getStudyViewerUrl(study.getId(), apiKey);
                item.setAnexoImagem(viewerUrl);
            }

            items.add(item);
        }

        return items;
    }

    private String mapStudyToTUSS(PACSStudyDTO study) {
        // Lógica de mapeamento baseada em modalidade e descrição
        // Exemplo simplificado
        if ("CT".equals(study.getModality())) {
            if (study.getDescription().contains("abdomen")) {
                return "40801403"; // TC abdômen superior
            } else if (study.getDescription().contains("chest")) {
                return "40801144"; // TC tórax
            }
        }

        throw new CodeMappingException("Estudo não mapeado: " + study.getDescription());
    }
}
```

---

### Exemplo 2: Validação Pré-Faturamento de Imagens
```java
@Service
public class ImagingValidationService {

    public ValidationResult validateImagingStudies(String encounterId) {
        ValidationResult result = new ValidationResult();

        List<PACSStudyDTO> studies = pacsClient.getStudiesByEncounter(encounterId, apiKey);

        for (PACSStudyDTO study : studies) {
            // Validar status
            if (!"available".equals(study.getStatus())) {
                result.addWarning(
                    "Estudo " + study.getId() + " não disponível: " + study.getStatus()
                );
            }

            // Validar laudo
            if (study.getReportStatus() == null || !"final".equals(study.getReportStatus())) {
                result.addError(
                    "Estudo " + study.getId() + " sem laudo final"
                );
            }

            // Validar radiologista
            if (study.getInterpretingRadiologist() == null) {
                result.addError(
                    "Estudo " + study.getId() + " sem radiologista identificado"
                );
            }

            // Validar mapeamento TUSS
            try {
                mapStudyToTUSS(study);
            } catch (CodeMappingException e) {
                result.addError(
                    "Estudo não pode ser mapeado para TUSS: " + study.getDescription()
                );
            }
        }

        return result;
    }
}
```

---

## Conformidade Regulatória

### DICOM Standards
- **NEMA PS3**: Digital Imaging and Communications in Medicine
- **Study/Series/Instance hierarchy**: Estrutura padrão DICOM

### HL7 FHIR R4
- **ImagingStudy Resource**: http://hl7.org/fhir/R4/imagingstudy.html

### TISS/ANS
- **Codificação**: Procedimentos radiológicos devem usar códigos TUSS da CBHPM
- **Anexos**: Laudos radiológicos podem ser exigidos em guias

---

## Referências Técnicas

1. **FHIR ImagingStudy**: http://hl7.org/fhir/R4/imagingstudy.html
2. **DICOM Standards**: https://www.dicomstandard.org/
3. **DICOM Modalities**: http://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.3.html
4. **Spring Cloud OpenFeign**: https://spring.io/projects/spring-cloud-openfeign

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
