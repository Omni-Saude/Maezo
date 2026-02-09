# RN-AppealPackage - Pacote de Recurso

**Categoria:** Modelo de Domínio - Resultado
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.AppealPackage`
**Tipo:** DTO de Saída

---

## Descrição
Objeto que representa um pacote completo de recurso de glosa, contendo todos os documentos gerados e metadados de validação. Resultado do processamento por `AppealDocumentService`.

## Estrutura

```java
@Data
@Builder
public class AppealPackage {
    @Singular("addDocument")
    private List<String> documentIds;
    private boolean complete;
    private String appealStrategy;
    private int minimumDocumentCount;
}
```

## Atributos

### documentIds
- **Tipo:** List<String>
- **Descrição:** Lista de identificadores únicos dos documentos gerados
- **Builder:** Usa `@Singular("addDocument")` para adição individual
- **Exemplo:**
```java
[
  "APPEAL_LETTER_GLOSA-001_2024-01-12 14:30:00",
  "STANDARD_DOC_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "CLINICAL_RECORDS_ENC-2024-001",
  "APPEAL_TRACKING_GLOSA-001",
  "APPEAL_CHECKLIST_GLOSA-001"
]
```

### complete
- **Tipo:** boolean
- **Descrição:** Flag calculada indicando se o pacote está completo
- **Cálculo:** `documentIds.size() >= minimumDocumentCount`
- **Uso:** Validação antes de submissão

### appealStrategy
- **Tipo:** String
- **Descrição:** Estratégia usada para gerar o pacote
- **Valores:** "STANDARD", "MEDICAL_NECESSITY", etc.
- **Rastreabilidade:** Permite auditoria de qual estratégia foi aplicada

### minimumDocumentCount
- **Tipo:** int
- **Descrição:** Número mínimo de documentos para completude
- **Origem:** `AppealStrategy.getMinimumDocumentCount()`
- **Valores Típicos:**
  - Standard: 3
  - Medical Necessity: 6

## Métodos

### isComplete()
```java
public boolean isComplete() {
    return documentIds != null
        && !documentIds.isEmpty()
        && documentIds.size() >= minimumDocumentCount;
}
```

**Descrição:** Valida se o pacote contém documentos suficientes

**Regras:**
- documentIds não pode ser null
- Lista não pode estar vazia
- Quantidade deve ser >= minimumDocumentCount

**Exemplo:**
```java
AppealPackage pkg = // ...
if (pkg.isComplete()) {
    submitAppeal(pkg);
} else {
    log.error("Pacote incompleto: {} documentos, mínimo {}",
        pkg.getDocumentIds().size(),
        pkg.getMinimumDocumentCount());
}
```

## Regras de Negócio

### RN-APPEAL-PKG-001: Validação de Completude
**Descrição:** Pacote só pode ser submetido se completo
**Fórmula:** `documentIds.size() >= minimumDocumentCount`
**Implementação:** `isComplete()` method

### RN-APPEAL-PKG-002: Documentos Obrigatórios
**Descrição:** Todo pacote deve conter ao menos:
- 1 carta de recurso
- Documentos específicos da estratégia
- Documentos administrativos (tracking + checklist)

### RN-APPEAL-PKG-003: Rastreabilidade
**Descrição:** appealStrategy deve ser persistida para auditoria
**Uso:** Análise de efetividade de estratégias

### RN-APPEAL-PKG-004: Unicidade de Documentos
**Descrição:** documentIds devem ser únicos (sem duplicatas)
**Validação:** Usar Set para verificar unicidade se necessário

### RN-APPEAL-PKG-005: Ordem de Documentos
**Descrição:** Documentos são adicionados em ordem específica:
1. Carta de recurso (sempre primeiro)
2. Documentos da estratégia
3. Documentos clínicos (se aplicável)
4. Documentos administrativos (tracking, checklist)

## Construção via Builder

### Exemplo Básico
```java
AppealPackage pkg = AppealPackage.builder()
    .appealStrategy("STANDARD")
    .minimumDocumentCount(3)
    .addDocument("APPEAL_LETTER_001")
    .addDocument("STANDARD_DOC_uuid1")
    .addDocument("APPEAL_TRACKING_001")
    .build();
```

### Construção no AppealDocumentService
```java
public AppealPackage prepareAppealPackage(AppealRequest request) {
    AppealPackage.AppealPackageBuilder builder = AppealPackage.builder();
    builder.appealStrategy(request.getAppealStrategy());

    // 1. Carta de recurso
    String appealLetter = generateAppealLetter(request);
    builder.addDocument(appealLetter);

    // 2. Documentos da estratégia
    AppealStrategy strategy = strategyRegistry.getStrategy(request.getAppealStrategy());
    List<String> strategyDocs = strategy.generateDocuments(request);
    strategyDocs.forEach(builder::addDocument);

    // 3. Documentos clínicos (se necessário)
    if (strategy.requiresClinicalDocumentation()) {
        List<String> clinicalDocs = collectClinicalDocumentation(request);
        clinicalDocs.forEach(builder::addDocument);
    }

    // 4. Documentos administrativos
    List<String> adminDocs = generateAdministrativeDocuments(request);
    adminDocs.forEach(builder::addDocument);

    // 5. Definir contagem mínima
    builder.minimumDocumentCount(strategy.getMinimumDocumentCount());

    return builder.build();
}
```

## Uso no Sistema

### Fluxo de Processamento
```
1. AppealDocumentService.prepareAppealPackage(request)
   ↓
2. Builder acumula documentIds via addDocument()
   ↓
3. Define appealStrategy e minimumDocumentCount
   ↓
4. Build() cria AppealPackage imutável
   ↓
5. isComplete() valida completude
   ↓
6. Se completo: Processo BPMN continua
   Se incompleto: Erro ou compensação
```

### Integração com BPMN
```java
// No PrepareGlosaAppealDelegate
AppealPackage appealPackage = appealDocumentService.prepareAppealPackage(request);

// Armazena no processo
execution.setVariable("appealPackage", appealPackage);
execution.setVariable("appealDocuments", appealPackage.getDocumentIds());
execution.setVariable("appealComplete", appealPackage.isComplete());

// Gateway XOR decision
if (!appealPackage.isComplete()) {
    throw new BpmnError("APPEAL_INCOMPLETE",
        "Pacote de recurso está incompleto");
}
```

## Validação e Tratamento de Erros

### Validação Pré-Submissão
```java
public void validateForSubmission(AppealPackage pkg) {
    if (!pkg.isComplete()) {
        throw new AppealIncompleteException(
            String.format("Pacote incompleto: %d documentos, mínimo %d",
                pkg.getDocumentIds().size(),
                pkg.getMinimumDocumentCount()));
    }

    if (pkg.getDocumentIds().isEmpty()) {
        throw new IllegalStateException("Nenhum documento no pacote");
    }

    if (pkg.getAppealStrategy() == null) {
        throw new IllegalStateException("Estratégia não definida");
    }
}
```

### Logging
```java
log.info("Appeal package prepared: glosaId={}, documents={}, complete={}",
    request.getGlosaId(),
    appealPackage.getDocumentIds().size(),
    appealPackage.isComplete());

if (!appealPackage.isComplete()) {
    log.warn("Appeal package incomplete: {} documents, minimum {}",
        appealPackage.getDocumentIds().size(),
        appealPackage.getMinimumDocumentCount());
}
```

## Exemplos de Pacotes

### Exemplo 1: Recurso Padrão (Completo)
```java
AppealPackage {
    documentIds: [
        "APPEAL_LETTER_GLOSA-001_2024-01-12 14:30:00",
        "STANDARD_DOC_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "APPEAL_TRACKING_GLOSA-001",
        "APPEAL_CHECKLIST_GLOSA-001"
    ],
    complete: true,  // 4 >= 3
    appealStrategy: "STANDARD",
    minimumDocumentCount: 3
}
```

### Exemplo 2: Recurso de Necessidade Médica (Completo)
```java
AppealPackage {
    documentIds: [
        "APPEAL_LETTER_GLOSA-002_2024-01-12 15:00:00",
        "MEDICAL_NECESSITY_JUSTIFICATION_uuid1",
        "PHYSICIAN_STATEMENT_uuid2",
        "CLINICAL_GUIDELINES_uuid3",
        "CLINICAL_RECORDS_ENC-2024-001",
        "APPEAL_TRACKING_GLOSA-002",
        "APPEAL_CHECKLIST_GLOSA-002"
    ],
    complete: true,  // 7 >= 6
    appealStrategy: "MEDICAL_NECESSITY",
    minimumDocumentCount: 6
}
```

### Exemplo 3: Pacote Incompleto
```java
AppealPackage {
    documentIds: [
        "APPEAL_LETTER_GLOSA-003_2024-01-12 16:00:00",
        "STANDARD_DOC_uuid"
    ],
    complete: false,  // 2 < 3
    appealStrategy: "STANDARD",
    minimumDocumentCount: 3
}
```

## Serialização

### JSON Example
```json
{
  "documentIds": [
    "APPEAL_LETTER_GLOSA-001_2024-01-12 14:30:00",
    "STANDARD_DOC_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "APPEAL_TRACKING_GLOSA-001",
    "APPEAL_CHECKLIST_GLOSA-001"
  ],
  "complete": true,
  "appealStrategy": "STANDARD",
  "minimumDocumentCount": 3
}
```

## Performance

- **Imutabilidade:** Builder pattern garante thread-safety após construção
- **Memória:** Lista de strings (referências leves)
- **Validação:** O(1) - apenas comparação de size
- **Adição de Documentos:** O(1) amortizado (ArrayList)

## Testes

**Arquivo:** `PrepareGlosaAppealDelegateTest.java`

Cenários testados:
- Criação de pacote completo (STANDARD)
- Criação de pacote completo (MEDICAL_NECESSITY)
- Validação de completude
- Contagem de documentos
- Estratégia aplicada corretamente

## Integração com Outros Componentes

### Usado Por
- `PrepareGlosaAppealDelegate` - Armazena em BPMN variables
- `AppealSubmissionService` - Submete pacote para operadora
- `AppealTrackingService` - Rastreia status do recurso

### Relacionado Com
- `AppealRequest` - Entrada para geração
- `AppealStrategy` - Define minimumDocumentCount
- `AppealDocumentService` - Gera o pacote

## Conformidade

- **ANS RN 443/2019:** Documenta completude do recurso
- **TISS 3.06.00:** IDs de documentos rastreáveis
- **ISO 9001:** Rastreabilidade de processo

## Melhorias Futuras

### Possíveis Extensões
```java
public class AppealPackage {
    // ... campos existentes

    // Metadados adicionais
    private LocalDateTime generatedAt;
    private String generatedBy;
    private Map<String, DocumentMetadata> documentMetadata;
    private List<ValidationWarning> warnings;

    // Validação avançada
    public List<String> getMissingDocuments() {
        // Retorna tipos de documentos esperados mas ausentes
    }

    public double getCompletenessScore() {
        // Retorna score 0.0-1.0 baseado em completude
    }
}
```

## Referências
- `AppealDocumentService.java` - Gerador
- `AppealStrategy.java` - Define minimumDocumentCount
- `PrepareGlosaAppealDelegate.java` - Usuário principal
- `AppealRequest.java` - Entrada relacionada
