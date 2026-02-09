# RN - PACSIntegrationDelegate

**ID:** RN-CLINICAL-006
**Camada:** Delegates (Imaging Integration)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** HIGH
**BPMN Reference:** `${pacsIntegrationDelegate}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável pela integração com PACS (Picture Archiving and Communication System) usando recursos HL7 FHIR ImagingStudy. Recupera estudos de imagem, valida completude de laudos, extrai metadados para cobrança e gera URLs para visualização clínica.

### 1.2 Objetivo
- Recuperar estudos de imagem via FHIR ImagingStudy
- Validar se todos estudos possuem laudos finais
- Extrair metadados de modalidades e séries para cobrança
- Gerar URLs de visualização DICOM
- Calcular estatísticas de estudos e instâncias
- Validar integridade de dados DICOM

### 1.3 Contexto no Fluxo de Negócio
Este delegate integra dados de imagens médicas ao prontuário clínico, permitindo validação de completude de documentação e fornecendo dados essenciais para codificação e cobrança de exames de imagem.

---

## 2. Regras de Negócio

### RN-CLINICAL-006.1: Verificação de Existência de Estudos
**Descrição:** Verifica se o atendimento possui estudos de imagem

**Condição:**
```java
List<PACSStudyDTO> studies = pacsService.getStudiesByEncounter(encounterId);

if (studies.isEmpty()) {
    setVariable(execution, "has_imaging_orders", false);
    setVariable(execution, "pacs_all_final", true); // Sem estudos = completo
    return;
}
```

**Impacto:** Se não há estudos, delegate finaliza rapidamente sem erro

---

### RN-CLINICAL-006.2: Validação de Status Final
**Descrição:** Verifica se todos os estudos possuem laudos finais

**Condição:**
```java
boolean allFinal = studies.stream()
    .allMatch(study -> "available".equalsIgnoreCase(study.getStatus())
            && "final".equalsIgnoreCase(study.getReportStatus()));
```

**Critérios Duplos:**
1. **Status do Estudo:** `available` (imagens disponíveis)
2. **Status do Laudo:** `final` (laudo finalizado)

**Ambos devem ser verdadeiros para considerar estudo completo**

---

### RN-CLINICAL-006.3: Extração de Modalidades
**Descrição:** Identifica modalidades de imagem utilizadas

**Modalidades DICOM Suportadas:**
- `CT`: Tomografia Computadorizada
- `MR`: Ressonância Magnética
- `XR`: Raio-X
- `US`: Ultrassom
- `MG`: Mamografia
- `PT`: PET (Tomografia por Emissão de Pósitrons)
- `NM`: Medicina Nuclear
- `CR`: Radiografia Computadorizada
- `DX`: Radiografia Digital

**Extração:**
```java
List<String> modalities = studies.stream()
    .map(PACSStudyDTO::getModality)
    .distinct()
    .collect(Collectors.toList());
```

**Utilidade:** Codificação de procedimentos por modalidade para cobrança

---

### RN-CLINICAL-006.4: Geração de URLs de Visualização
**Descrição:** Gera URLs para visualização de estudos em viewer DICOM

**Ação:**
```java
Map<String, String> viewerUrls = new HashMap<>();
for (PACSStudyDTO study : studies) {
    String viewerUrl = pacsService.getStudyViewerUrl(study.getId());
    viewerUrls.put(study.getId(), viewerUrl);
}
```

**Exemplo de URL:**
```
https://pacs.hospital.com/viewer?studyUID=1.2.840.113619.2.55.1234567890
```

**Utilidade:**
- Revisão clínica rápida
- Auditoria médica
- Segundo parecer

---

### RN-CLINICAL-006.5: Cálculo de Séries e Instâncias
**Descrição:** Calcula total de séries e instâncias DICOM

**Cálculo:**
```java
int totalSeries = studies.stream()
    .mapToInt(study -> study.getNumberOfSeries() != null ? study.getNumberOfSeries() : 0)
    .sum();

int totalInstances = studies.stream()
    .mapToInt(study -> study.getNumberOfInstances() != null ? study.getNumberOfInstances() : 0)
    .sum();
```

**Definições DICOM:**
- **Study:** Estudo completo (ex: CT de Tórax)
- **Series:** Série de imagens (ex: fase arterial)
- **Instance:** Imagem individual (arquivo DICOM)

**Exemplo:**
- 1 Study (CT Tórax)
  - 3 Series (sem contraste, fase arterial, fase venosa)
    - 150 Instances (50 imagens por série)

---

### RN-CLINICAL-006.6: Estatísticas de Status
**Descrição:** Calcula quantidade de estudos por status

**Cálculo:**
```java
long availableStudies = studies.stream()
    .filter(study -> "available".equalsIgnoreCase(study.getStatus()))
    .count();

long pendingStudies = studies.stream()
    .filter(study -> !"available".equalsIgnoreCase(study.getStatus()))
    .count();
```

**Status DICOM Possíveis:**
- `available`: Estudo disponível
- `registered`: Registrado mas não iniciado
- `in-progress`: Em andamento
- `cancelled`: Cancelado
- `entered-in-error`: Erro de registro

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `encounter_id` | String | ID do atendimento | "ENC-12345" |

### 3.2 Variáveis de Saída (Status)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `has_imaging_orders` | Boolean | Atendimento possui estudos de imagem | PROCESS |
| `pacs_all_final` | Boolean | Todos laudos finais | PROCESS |

### 3.3 Variáveis de Saída (Dados)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `pacs_studies` | List<Map> | Metadados dos estudos | PROCESS |
| `pacs_modalities` | List<String> | Modalidades utilizadas | PROCESS |
| `pacs_viewer_urls` | Map<String,String> | URLs de visualização | PROCESS |

### 3.4 Variáveis de Saída (Estatísticas)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `pacs_study_count` | Integer | Total de estudos | PROCESS |
| `pacs_total_series` | Integer | Total de séries | PROCESS |
| `pacs_total_instances` | Integer | Total de instâncias | PROCESS |
| `pacs_available_studies` | Long | Estudos disponíveis | PROCESS |
| `pacs_pending_studies` | Long | Estudos pendentes | PROCESS |

### 3.5 Variáveis de Erro
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `pacs_integration_error` | String | Mensagem de erro |

---

## 4. Estrutura de Dados

### 4.1 Study Metadata (pacs_studies)
```json
{
  "study_id": "STUDY-123",
  "study_uid": "1.2.840.113619.2.55.1234567890",
  "modality": "CT",
  "description": "CT Chest with contrast",
  "status": "available",
  "report_status": "final",
  "started": "2026-01-12T09:00:00",
  "number_of_series": 3,
  "number_of_instances": 150,
  "interpreting_radiologist": "Dr. Radiologista"
}
```

### 4.2 Viewer URLs (pacs_viewer_urls)
```json
{
  "STUDY-123": "https://pacs.hospital.com/viewer?studyUID=1.2.840.113619.2.55.1234567890",
  "STUDY-456": "https://pacs.hospital.com/viewer?studyUID=1.2.840.113619.2.55.0987654321"
}
```

---

## 5. Integrações

### 5.1 PACSService
**Métodos:**
- `getStudiesByEncounter(encounterId)`: Recupera estudos do atendimento
- `getStudyViewerUrl(studyId)`: Gera URL de visualização
- `isImagingComplete(encounterId)`: Verifica se todos estudos estão completos

**DTOs:**
- `PACSStudyDTO`: Estudo de imagem (FHIR ImagingStudy)
- `PACSSeriesDTO`: Série de imagens

---

### 5.2 FHIR ImagingStudy Resource

```json
{
  "resourceType": "ImagingStudy",
  "id": "STUDY-123",
  "status": "available",
  "modality": [{
    "system": "http://dicom.nema.org/resources/ontology/DCM",
    "code": "CT"
  }],
  "subject": {
    "reference": "Patient/PAT-12345"
  },
  "started": "2026-01-12T09:00:00Z",
  "numberOfSeries": 3,
  "numberOfInstances": 150,
  "series": [{
    "uid": "1.2.840.113619.2.55.1234567890.1",
    "modality": {
      "code": "CT"
    },
    "numberOfInstances": 50
  }]
}
```

---

### 5.3 DICOM Standards
**Compliance:**
- DICOM PS3.3 Information Object Definitions
- DICOM PS3.4 Service Class Specifications
- DICOM PS3.10 Media Storage and File Format

**Study Instance UID:**
- Formato: OID (Object Identifier)
- Exemplo: `1.2.840.113619.2.55.1234567890`
- Único globalmente

---

## 6. Tratamento de Erros

### 6.1 Fallback para Viewer URL
```java
try {
    String viewerUrl = pacsService.getStudyViewerUrl(study.getId());
    viewerUrls.put(study.getId(), viewerUrl);
} catch (Exception e) {
    log.warn("Failed to get viewer URL for study: {}", study.getId(), e);
    // Continua sem bloquear o processo
}
```

### 6.2 Exceções Técnicas
```java
catch (Exception e) {
    log.error("PACS integration failed - Process: {}, Error: {}",
        processInstanceId, e.getMessage(), e);

    setVariable(execution, "pacs_integration_error", e.getMessage());
    setVariable(execution, "pacs_all_final", false);

    throw new RuntimeException("Failed to integrate with PACS", e);
}
```

---

## 7. Conformidade e Auditoria

### 7.1 Regulamentações
- **DICOM Standard:** Padrão de imagens médicas
- **HL7 FHIR R4:** ImagingStudy resource
- **ANS:** Documentação de exames de imagem para cobrança
- **LGPD:** Privacidade de imagens médicas

### 7.2 Logs de Auditoria
```
INFO: Executing PACSIntegrationDelegate - Process: {id}, Activity: {activity}
INFO: Retrieving PACS imaging studies for encounter: {id}
INFO: Retrieved {count} PACS imaging studies for encounter: {id}
INFO: PACS report status - EncounterId: {id}, AllFinal: {status}
INFO: PACS integration completed - EncounterId: {id}, Studies: {count}, AllFinal: {status}, Modalities: {list}
```

---

## 8. Dependências

### 8.1 Serviços
- `PACSService`: Integração com sistema de imagens

### 8.2 DTOs
- `PACSStudyDTO`: Estudo de imagem
- `PACSSeriesDTO`: Série de imagens

### 8.3 Delegates Relacionados
- `CompletenessCheckDelegate`: Valida completude de laudos
- `FinalizarAtendimentoDelegate`: Verifica se todos laudos estão finais

---

## 9. Requisitos Não-Funcionais

### 9.1 Performance
- Tempo médio de execução: < 3 segundos
- Timeout: 20 segundos

### 9.2 Idempotência
- **requiresIdempotency()**: `false`
- Operação de leitura, naturalmente idempotente

### 9.3 Disponibilidade
- Dependência: PACS (uptime > 99%)

---

## 10. Cenários de Teste

### 10.1 Cenário: Sem Estudos de Imagem
**Dado:** Atendimento sem pedidos de imagem
**Quando:** PACSIntegrationDelegate executado
**Então:**
- `has_imaging_orders = false`
- `pacs_all_final = true`
- `pacs_study_count = 0`

---

### 10.2 Cenário: Estudos com Laudos Finais
**Dado:**
- 2 estudos de imagem (CT + MR)
- Ambos com status `available` e report `final`

**Quando:** PACSIntegrationDelegate executado
**Então:**
- `has_imaging_orders = true`
- `pacs_all_final = true`
- `pacs_study_count = 2`
- `pacs_modalities = ["CT", "MR"]`
- `pacs_viewer_urls` com 2 URLs

---

### 10.3 Cenário: Laudos Pendentes
**Dado:**
- 1 estudo com report_status `preliminary`

**Quando:** PACSIntegrationDelegate executado
**Então:**
- `has_imaging_orders = true`
- `pacs_all_final = false`
- Bloqueia finalização do atendimento

---

### 10.4 Cenário: Estudo Complexo (CT Tórax)
**Dado:**
- 1 estudo CT
- 3 séries (sem contraste, arterial, venosa)
- 150 instâncias (50 por série)

**Quando:** PACSIntegrationDelegate executado
**Então:**
- `pacs_study_count = 1`
- `pacs_total_series = 3`
- `pacs_total_instances = 150`

---

## 11. Matriz de Status

| Status Estudo | Status Laudo | Final? | Permite Finalização? | Descrição |
|---------------|--------------|--------|---------------------|-----------|
| `available` | `final` | ✅ | ✅ | Estudo completo com laudo final |
| `available` | `preliminary` | ❌ | ❌ | Imagens ok, laudo preliminar |
| `in-progress` | N/A | ❌ | ❌ | Aquisição em andamento |
| `registered` | N/A | ❌ | ❌ | Registrado mas não iniciado |
| `cancelled` | N/A | N/A | ⚠️ | Estudo cancelado |

**Ambos devem estar completos:**
- ✅ Status = `available` **E** Report = `final`

---

## 12. Modalidades DICOM

| Código | Modalidade | Exemplo |
|--------|------------|---------|
| CT | Computed Tomography | CT Tórax, CT Crânio |
| MR | Magnetic Resonance | RM Joelho, RM Coluna |
| XR | X-Ray | Raio-X Tórax PA/Perfil |
| US | Ultrasound | US Abdome Total |
| MG | Mammography | Mamografia Bilateral |
| PT | PET | PET-CT Oncológico |
| NM | Nuclear Medicine | Cintilografia Óssea |
| CR | Computed Radiography | Raio-X Digital |
| DX | Digital Radiography | Raio-X Digital Direto |

---

## 13. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/PACSIntegrationDelegate.java`

**Serviços:**
- `/src/main/java/com/hospital/revenuecycle/service/PACSService.java`

**DTOs:**
- `/src/main/java/com/hospital/revenuecycle/integration/pacs/dto/PACSStudyDTO.java`
- `/src/main/java/com/hospital/revenuecycle/integration/pacs/dto/PACSSeriesDTO.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/PACSIntegrationDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
