# RN-SearchEvidenceDelegate

**Camunda Delegate:** `searchEvidenceDelegate`
**Categoria:** Gestão de Glosas (Negações) - Busca de Evidências
**Arquivo:** `SearchEvidenceDelegate.java`

## Descrição

Busca documentação clínica e evidências para suportar recursos de glosas. Este delegate recupera documentos do TASY e sistemas de gestão documental, avalia completude da documentação e determina se há evidências suficientes para proceder com recurso.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `encounterId` | String | Sim | Identificador do atendimento no TASY |
| `denialCode` | String | Sim | Código de glosa TISS |
| `denialCategory` | String | Sim | Categoria da negação |
| `procedureCode` | String | Não | Código do procedimento específico |

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `foundDocuments` | List&lt;ClinicalEvidence&gt; | Documentos de evidência encontrados |
| `missingDocuments` | List&lt;String&gt; | Tipos de documentos faltantes |
| `documentationComplete` | Boolean | Se documentação está completa |
| `completenessScore` | Double | Score de completude (0.0-1.0) |
| `sufficientForAppeal` | Boolean | Se há evidência suficiente para recurso |
| `evidenceRecommendations` | List&lt;String&gt; | Recomendações de documentos adicionais |
| `criticalDocumentsMissing` | Boolean | Se faltam documentos críticos |
| `documentCount` | Integer | Total de documentos encontrados |
| `canProceedWithAppeal` | Boolean | Se pode prosseguir com recurso (= sufficientForAppeal) |
| `needsDocumentCollection` | Boolean | Se precisa coletar mais documentos |

## Regras de Negócio

### Tipos de Documentos Clínicos Buscados

| Tipo de Documento | Descrição | Criticidade |
|-------------------|-----------|-------------|
| **AUTHORIZATION_GUIDE** | Guia de Autorização da Operadora | ALTA |
| **MEDICAL_ORDER** | Solicitação Médica | ALTA |
| **MEDICAL_RECORD** | Prontuário Médico | ALTA |
| **CLINICAL_EVOLUTION** | Evolução Médica | MÉDIA |
| **DIAGNOSTIC_REPORT** | Laudo Diagnóstico | MÉDIA |
| **LAB_RESULTS** | Resultados Laboratoriais | MÉDIA |
| **IMAGING_REPORT** | Laudo de Imagem | MÉDIA |
| **CLINICAL_JUSTIFICATION** | Justificativa Clínica | ALTA |
| **CONSENT_FORM** | Termo de Consentimento | BAIXA |
| **DISCHARGE_SUMMARY** | Resumo de Alta | BAIXA |

### Documentos Críticos

Documentos considerados **críticos** (falta impede recurso):
- Guia de Autorização (`AUTHORIZATION_GUIDE`)
- Prontuário Médico (`MEDICAL_RECORD`)

Se qualquer documento crítico estiver faltando:
```
criticalDocumentsMissing = true
sufficientForAppeal = false
```

### Score de Completude

**Fórmula:**
```
completenessScore = (documentos_encontrados / documentos_esperados)
```

**Interpretação:**
- `1.0` (100%): Todos os documentos encontrados
- `0.8-0.99` (80-99%): Documentação quase completa
- `0.5-0.79` (50-79%): Documentação parcial
- `< 0.5` (< 50%): Documentação insuficiente

### Suficiência para Recurso

Uma glosa tem evidência **suficiente para recurso** quando:

1. ✅ Todos os documentos **críticos** foram encontrados
2. ✅ Score de completude ≥ 0.7 (70%)
3. ✅ Documentos são relevantes para a categoria de negação

**Lógica:**
```java
sufficientForAppeal =
    !criticalDocumentsMissing &&
    completenessScore >= 0.7 &&
    !missingDocuments.isEmpty()
```

## Buscas Adicionais por Categoria

### Categoria CLINICAL (Necessidade Médica)

**Documentos Específicos Buscados:**
- Justificativas clínicas para o procedimento
- Notas de evolução médica
- Resultados de exames que justifiquem o procedimento

**Método:** `searchClinicalJustification(encounterId, procedureCode)`

### Categoria AUTHORIZATION (Falta de Autorização)

**Documentos Específicos Buscados:**
- Guias de autorização originais
- Solicitações de autorização
- Correspondências com operadora

**Método:** `retrieveAuthorizationDocuments(encounterId)`

### Categoria CONTRACTUAL (Cobertura)

**Documentos Específicos Buscados:**
- Guias de autorização
- Termos contratuais
- Comunicações prévias

**Método:** `retrieveAuthorizationDocuments(encounterId)`

## Integrações

### EvidenceSearchService

**Método Principal:**
```java
EvidenceSearchResult searchEvidence(
    String encounterId,
    String denialCode,
    String denialCategory
)
```

**Retorno:**
```java
class EvidenceSearchResult {
    List<ClinicalEvidence> foundDocuments;
    List<String> missingDocuments;
    Double completenessScore;
    Boolean sufficientForAppeal;
    List<String> recommendations;
}
```

**Métodos Especializados:**
```java
List<ClinicalEvidence> searchClinicalJustification(
    String encounterId,
    String procedureCode
)

List<ClinicalEvidence> retrieveAuthorizationDocuments(
    String encounterId
)
```

### TASY ERP
- Busca de documentos clínicos associados ao atendimento
- Recuperação de guias de autorização
- Acesso a prontuário eletrônico

### Sistema de Gestão Documental (DMS)
- Busca de documentos digitalizados
- Metadados de documentos
- Links para visualização

## Estrutura de Dados

### ClinicalEvidence

```java
class ClinicalEvidence {
    String documentId;          // ID único do documento
    String documentType;        // Tipo do documento
    String encounterId;         // ID do atendimento
    String title;               // Título/descrição do documento
    LocalDateTime documentDate; // Data do documento
    String author;              // Autor (médico, enfermeiro, etc.)
    String relevance;           // CRITICAL, HIGH, MEDIUM, LOW
    String storageLocation;     // Localização no DMS
    Map<String, Object> metadata; // Metadados adicionais
}
```

### Exemplo de foundDocuments

```json
[
  {
    "documentId": "DOC-12345",
    "documentType": "AUTHORIZATION_GUIDE",
    "encounterId": "ENC-67890",
    "title": "Guia de Autorização - Cirurgia Cardíaca",
    "documentDate": "2025-01-10T08:00:00",
    "author": "SISTEMA_OPERADORA",
    "relevance": "CRITICAL",
    "storageLocation": "/storage/documents/2025/01/DOC-12345.pdf",
    "metadata": {
      "authorizationNumber": "AUTH-99887766",
      "payerId": "OPR-001",
      "validUntil": "2025-02-10"
    }
  },
  {
    "documentId": "DOC-12346",
    "documentType": "MEDICAL_RECORD",
    "encounterId": "ENC-67890",
    "title": "Prontuário Médico Completo",
    "documentDate": "2025-01-10T09:30:00",
    "author": "DR-SILVA-001",
    "relevance": "CRITICAL",
    "storageLocation": "/storage/records/2025/01/DOC-12346.pdf"
  },
  {
    "documentId": "DOC-12347",
    "documentType": "CLINICAL_JUSTIFICATION",
    "encounterId": "ENC-67890",
    "title": "Justificativa de Necessidade Médica",
    "documentDate": "2025-01-10T10:00:00",
    "author": "DR-SILVA-001",
    "relevance": "HIGH",
    "storageLocation": "/storage/justifications/2025/01/DOC-12347.pdf"
  }
]
```

## Exemplo de Fluxo

```
1. Receber solicitação de busca:
   - encounterId: ENC-67890
   - denialCode: 06 (Falta de documentação)
   - denialCategory: DOCUMENTATION

2. Executar busca geral via EvidenceSearchService:
   - searchEvidence(ENC-67890, "06", "DOCUMENTATION")
   - Retorna: 5 documentos encontrados

3. Verificar categoria e executar busca adicional:
   - Categoria não requer busca adicional neste caso

4. Combinar resultados:
   - Total: 5 documentos

5. Verificar documentos críticos:
   - AUTHORIZATION_GUIDE: ✅ Encontrado
   - MEDICAL_RECORD: ✅ Encontrado
   - criticalDocumentsMissing = false

6. Calcular completude:
   - Score: 0.83 (83%)

7. Avaliar suficiência:
   - Críticos OK: ✅
   - Score >= 70%: ✅
   - sufficientForAppeal = true

8. Gerar recomendações:
   - "Consider obtaining discharge summary for complete record"

9. Logar resumo:
   - INFO: "Found 5 documents, completeness: 0.83"
   - INFO: "2 documents of type CRITICAL"

10. Definir variáveis de roteamento:
    - canProceedWithAppeal = true
    - needsDocumentCollection = false

11. Retornar todas as variáveis de output
```

## Logging e Auditoria

### Eventos Logados

**INFO:**
- Início da busca: `"Searching evidence for encounter {} with denial code {} in category {}"`
- Resultado da busca: `"Evidence search completed for encounter {}: found {} documents, completeness score {}, sufficient={}"`
- Resumo por tipo: `"{} documents of type {}"`
- Documentos críticos: `"Found {} critical evidence documents"`

**WARN:**
- Documentação insuficiente: `"Insufficient evidence for appeal. Missing documents: {}"`

**DEBUG:**
- Cada recomendação gerada
- Buscas adicionais realizadas

### Resumo de Documentos

Agrupa documentos por tipo e relata:
```
Evidence document summary:
  2 documents of type AUTHORIZATION_GUIDE
  1 documents of type MEDICAL_RECORD
  2 documents of type CLINICAL_JUSTIFICATION
Found 3 critical evidence documents
```

## Exceções e Erros

**Tratamento:** Não lança exceções BPMN - tratamento graceful

Em caso de falha em buscas adicionais:
```java
log.warn("Error performing additional evidence search: {}", e.getMessage());
// Continua execução mesmo se buscas adicionais falharem
```

**Motivos de Aviso:**
- Busca adicional falhou (não bloqueia processo)
- Nenhum documento encontrado
- Documentos críticos faltando

## Recomendações de Evidências

### Exemplos de Recomendações

```
- "Obtain authorization guide from payer system"
- "Request clinical justification from attending physician"
- "Retrieve lab results supporting medical necessity"
- "Collect imaging reports referenced in medical record"
- "Document clinical evolution notes during hospitalization"
- "Consider obtaining discharge summary for complete record"
```

### Geração de Recomendações

Baseada em:
- Documentos faltantes críticos
- Categoria da negação
- Histórico de casos similares bem-sucedidos

## KPIs e Métricas

- **Taxa de Completude Média**: Por categoria de negação
- **Tempo de Busca**: Performance do delegate
- **Taxa de Documentos Críticos Encontrados**: % de casos com documentos críticos
- **Taxa de Casos Prontos para Recurso**: % com evidência suficiente
- **Documentos Faltantes Mais Comuns**: Para melhoria de processo

## Integração no Processo BPMN

### Variáveis de Roteamento

```xml
<exclusiveGateway id="gateway1" name="Evidência suficiente?" />

<sequenceFlow id="flow1" sourceRef="gateway1" targetRef="applyCorrections">
  <conditionExpression xsi:type="tFormalExpression">
    ${canProceedWithAppeal == true}
  </conditionExpression>
</sequenceFlow>

<sequenceFlow id="flow2" sourceRef="gateway1" targetRef="collectDocuments">
  <conditionExpression xsi:type="tFormalExpression">
    ${needsDocumentCollection == true}
  </conditionExpression>
</sequenceFlow>

<sequenceFlow id="flow3" sourceRef="gateway1" targetRef="escalate">
  <conditionExpression xsi:type="tFormalExpression">
    ${criticalDocumentsMissing == true}
  </conditionExpression>
</sequenceFlow>
```

## Considerações Importantes

1. **Qualidade > Quantidade**: 3 documentos relevantes são melhores que 10 irrelevantes

2. **Documentos Críticos**: Falta de documentos críticos impede recurso - melhor escalonar

3. **Timing**: Buscar evidências cedo no processo evita perda de prazos

4. **Metadados**: Metadados ricos facilitam análise posterior

5. **Auditoria**: Rastreabilidade de quais documentos foram encontrados/usados

6. **Performance**: Busca deve ser rápida - usar índices e cache

## Versionamento

- **Versão Atual:** 1.0.0
- **Última Atualização:** 2025-01-12
- **Autor:** Revenue Cycle Team
- **Dependência:** EvidenceSearchService
