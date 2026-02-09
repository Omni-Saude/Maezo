# RN-AppealDocumentService - Serviço de Documentação de Recursos

**Categoria:** Modelo de Domínio - Serviço
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.AppealDocumentService`
**Tipo:** Service Component

---

## Descrição
Serviço responsável por orquestrar a preparação completa de pacotes de recurso de glosa, coordenando múltiplas estratégias e fontes de documentação.

## Responsabilidades

1. **Coordenação de Estratégias:** Seleciona e executa estratégia apropriada
2. **Geração de Documentos:** Cria carta de recurso base
3. **Coleta Clínica:** Busca documentação de prontuários eletrônicos
4. **Documentação Administrativa:** Gera documentos de tracking e checklist
5. **Validação:** Verifica completude do pacote final

## Estrutura

```java
@Slf4j
@Service
public class AppealDocumentService {
    private static final DateTimeFormatter DATE_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final AppealStrategyRegistry strategyRegistry;

    @Autowired
    public AppealDocumentService(AppealStrategyRegistry strategyRegistry) {
        this.strategyRegistry = strategyRegistry;
    }
}
```

## Métodos Principais

### 1. prepareAppealPackage
```java
public AppealPackage prepareAppealPackage(AppealRequest request)
```

**Descrição:** Método principal que orquestra toda preparação do pacote

**Parâmetros:**
- `AppealRequest request` - Dados da glosa e estratégia

**Retorno:**
- `AppealPackage` - Pacote completo com todos os documentos

**Fluxo:**
1. Gera carta de recurso (sempre obrigatória)
2. Seleciona estratégia via `strategyRegistry`
3. Gera documentos específicos da estratégia
4. Coleta documentação clínica (se necessário)
5. Gera documentos administrativos
6. Define contagem mínima de documentos
7. Valida completude do pacote

**Exemplo:**
```java
AppealRequest request = AppealRequest.builder()
    .glosaId("GLOSA-001")
    .appealStrategy("MEDICAL_NECESSITY")
    .encounterId("ENC-001")
    .build();

AppealPackage pkg = appealDocumentService.prepareAppealPackage(request);
```

### 2. generateAppealLetter (private)
```java
private String generateAppealLetter(AppealRequest request)
```

**Descrição:** Gera identificador para carta de recurso base

**Formato:** `"APPEAL_LETTER_{glosaId}_{timestamp}"`

**Exemplo:**
- Input: glosaId = "GLOSA-2024-001"
- Output: `"APPEAL_LETTER_GLOSA-2024-001_2024-01-12 14:30:00"`

**Regra:** Timestamp usa formato `yyyy-MM-dd HH:mm:ss`

### 3. collectClinicalDocumentation (private)
```java
private List<String> collectClinicalDocumentation(AppealRequest request)
```

**Descrição:** Coleta documentação clínica do prontuário eletrônico

**Condição:** Executado apenas se `encounterId != null`

**Formato:** `"CLINICAL_RECORDS_{encounterId}"`

**Exemplo:**
- Input: encounterId = "ENC-2024-001"
- Output: `["CLINICAL_RECORDS_ENC-2024-001"]`

**Integração:** Futura integração com EHR/EMR systems

### 4. generateAdministrativeDocuments (private)
```java
private List<String> generateAdministrativeDocuments(AppealRequest request)
```

**Descrição:** Gera documentos administrativos de tracking e checklist

**Saída:** Lista com 2 documentos:
1. **Tracking Form:** `"APPEAL_TRACKING_{glosaId}"`
2. **Checklist:** `"APPEAL_CHECKLIST_{glosaId}"`

**Exemplo:**
```java
[
    "APPEAL_TRACKING_GLOSA-2024-001",
    "APPEAL_CHECKLIST_GLOSA-2024-001"
]
```

## Regras de Negócio

### RN-APPEAL-DOC-001: Sequência de Geração
**Descrição:** Documentos devem ser gerados em ordem específica
**Ordem:**
1. Carta de recurso (base)
2. Documentos da estratégia
3. Documentação clínica (condicional)
4. Documentos administrativos

### RN-APPEAL-DOC-002: Carta de Recurso Obrigatória
**Descrição:** Todo pacote DEVE iniciar com carta de recurso
**Implementação:** Primeiro `builder.addDocument(appealLetter)`

### RN-APPEAL-DOC-003: Documentação Clínica Condicional
**Descrição:** Documentos clínicos só são coletados se estratégia requerer
**Critério:** `strategy.requiresClinicalDocumentation() == true`

### RN-APPEAL-DOC-004: Documentos Administrativos Sempre
**Descrição:** Tracking e checklist são sempre incluídos
**Quantidade:** 2 documentos (TRACKING + CHECKLIST)

### RN-APPEAL-DOC-005: Validação de Estratégia
**Descrição:** Se estratégia não encontrada, usa estratégia padrão
**Implementação:** `AppealStrategyRegistry` faz fallback para StandardAppealStrategy

### RN-APPEAL-DOC-006: Timestamp Padronizado
**Descrição:** Todos os timestamps usam formato `yyyy-MM-dd HH:mm:ss`
**Constante:** `DATE_FORMATTER`

## Fluxo Detalhado

```
┌─ prepareAppealPackage(request) ─────────────────────┐
│                                                       │
│ 1. Log: "Preparing appeal package for glosa: {id}"  │
│    ↓                                                  │
│ 2. Cria Builder                                      │
│    builder = AppealPackage.builder()                 │
│    builder.appealStrategy(request.getAppealStrategy())│
│    ↓                                                  │
│ 3. Gera Carta de Recurso                            │
│    appealLetter = generateAppealLetter(request)      │
│    builder.addDocument(appealLetter)                 │
│    ↓                                                  │
│ 4. Seleciona Estratégia                             │
│    strategy = strategyRegistry.getStrategy(...)      │
│    ↓                                                  │
│ 5. Gera Documentos da Estratégia                    │
│    strategyDocs = strategy.generateDocuments(request)│
│    strategyDocs.forEach(builder::addDocument)        │
│    ↓                                                  │
│ 6. Coleta Documentação Clínica (se necessário)      │
│    if (strategy.requiresClinicalDocumentation()) {   │
│        clinicalDocs = collectClinicalDocumentation() │
│        clinicalDocs.forEach(builder::addDocument)    │
│    }                                                  │
│    ↓                                                  │
│ 7. Gera Documentos Administrativos                  │
│    adminDocs = generateAdministrativeDocuments()     │
│    adminDocs.forEach(builder::addDocument)           │
│    ↓                                                  │
│ 8. Define Contagem Mínima                           │
│    builder.minimumDocumentCount(                     │
│        strategy.getMinimumDocumentCount())           │
│    ↓                                                  │
│ 9. Build e Log                                       │
│    appealPackage = builder.build()                   │
│    log.info("Appeal package prepared: ...")          │
│    ↓                                                  │
│ 10. Retorna AppealPackage                           │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Integração com Estratégias

### Standard Appeal (3 documentos mínimos)
```
Carta de Recurso (1)
  + Documento Padrão (1)
  + Admin (Tracking + Checklist) (2)
= 4 documentos total (>= 3 mínimo) ✓
```

### Medical Necessity Appeal (6 documentos mínimos)
```
Carta de Recurso (1)
  + Justificativa Médica (1)
  + Declaração Médico (1)
  + Diretrizes Clínicas (1)
  + Documentos Clínicos (1+)
  + Admin (Tracking + Checklist) (2)
= 7+ documentos total (>= 6 mínimo) ✓
```

## Dependências

### Injeção de Dependências
```java
@Autowired
public AppealDocumentService(AppealStrategyRegistry strategyRegistry) {
    this.strategyRegistry = strategyRegistry;
}
```

### Services Relacionados
- `AppealStrategyRegistry` - Gerencia estratégias
- `ClinicalDocumentCollector` (futuro) - Coleta docs de EHR
- `DocumentStorageService` (futuro) - Armazena PDFs

### Integração Externa (Futura)
- **EHR/EMR System:** Buscar prontuários
- **Document Storage:** S3, Azure Blob, etc.
- **PDF Generator:** Renderizar cartas e documentos

## Logging

### Níveis de Log
```java
// INFO: Início e fim do processamento
log.info("Preparing appeal package for glosa: {}", request.getGlosaId());
log.info("Appeal package prepared: glosaId={}, documents={}, complete={}",
    request.getGlosaId(),
    appealPackage.getDocumentIds().size(),
    appealPackage.isComplete());

// DEBUG: Detalhes internos
log.debug("Generated appeal letter: {}", documentId);
log.debug("Collected clinical documentation: {}", clinicalDoc);
log.debug("Generated administrative documents: {}", documents);
```

## Tratamento de Erros

### Possíveis Exceções
- **IllegalArgumentException:** Campos obrigatórios ausentes em request
- **StrategyNotFoundException:** Estratégia não registrada (usa default)
- **DocumentGenerationException:** Falha na geração de documento
- **EHRIntegrationException:** Falha ao buscar docs clínicos

### Exemplo de Tratamento
```java
try {
    AppealPackage pkg = appealDocumentService.prepareAppealPackage(request);
    if (!pkg.isComplete()) {
        throw new AppealIncompleteException("Pacote incompleto");
    }
} catch (AppealIncompleteException e) {
    log.error("Failed to prepare complete appeal package", e);
    // Compensação ou retry
}
```

## Testes

**Arquivo:** `PrepareGlosaAppealDelegateTest.java`

### Cenários Testados
1. **Estratégia Standard:**
   - Gera 4 documentos (carta + padrão + 2 admin)
   - Não coleta documentação clínica
   - Pacote completo (4 >= 3)

2. **Estratégia Medical Necessity:**
   - Gera 7+ documentos
   - Coleta documentação clínica
   - Pacote completo (7 >= 6)

3. **Validação:**
   - Documentos únicos
   - Ordem correta
   - Completude do pacote

## Performance

- **Complexidade:** O(n) onde n = número de documentos
- **I/O:** Possível acesso a EHR (rede)
- **Memória:** Lista de strings (leve)
- **Paralelização:** Futura - gerar docs em paralelo

## Melhores Práticas

### Uso Recomendado
```java
// ✓ BOM: Validar request antes
if (request.getGlosaId() == null) {
    throw new IllegalArgumentException("glosaId obrigatório");
}
AppealPackage pkg = appealDocumentService.prepareAppealPackage(request);

// ✓ BOM: Validar resultado
if (!pkg.isComplete()) {
    log.warn("Pacote incompleto: {} docs", pkg.getDocumentIds().size());
}

// ✗ RUIM: Não validar entrada
AppealPackage pkg = appealDocumentService.prepareAppealPackage(request);
// NullPointerException possível
```

## Extensibilidade

### Adicionar Nova Fonte de Documentos
```java
private List<String> collectImagingDocumentation(AppealRequest request) {
    // Buscar imagens do PACS
    if (request.getImagingStudyId() != null) {
        return pacsIntegrationService.getStudyImages(
            request.getImagingStudyId());
    }
    return Collections.emptyList();
}
```

### Adicionar Validação Customizada
```java
private void validateAppealPackage(AppealPackage pkg) {
    // Validações específicas de negócio
    if (pkg.getDocumentIds().stream().noneMatch(id -> id.contains("LETTER"))) {
        throw new IllegalStateException("Carta de recurso ausente");
    }
}
```

## Conformidade

- **ANS RN 443/2019:** Geração de documentação regulamentada
- **TISS 3.06.00:** Documentos compatíveis com padrão TISS
- **ISO 9001:** Processo documentado e rastreável

## Referências
- `AppealRequest.java` - Entrada
- `AppealPackage.java` - Saída
- `AppealStrategyRegistry.java` - Gerenciador de estratégias
- `PrepareGlosaAppealDelegate.java` - Chamador BPMN
