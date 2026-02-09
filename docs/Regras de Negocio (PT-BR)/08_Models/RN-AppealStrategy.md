# RN-AppealStrategy - Estratégia de Recurso

**Categoria:** Modelo de Domínio - Recurso de Glosa
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.strategy.AppealStrategy`
**Tipo:** Interface Strategy Pattern

---

## Descrição
Interface que define o contrato para diferentes estratégias de preparação de recursos de glosa. Implementa o padrão Strategy para permitir múltiplos tipos de recursos (médico, administrativo, técnico).

## Estrutura

### Interface Strategy
```java
public interface AppealStrategy {
    List<String> generateDocuments(AppealRequest request);
    boolean requiresClinicalDocumentation();
    int getMinimumDocumentCount();
    String getStrategyType();
}
```

## Métodos da Interface

### 1. generateDocuments
**Entrada:**
- `AppealRequest request` - Solicitação de recurso com detalhes da glosa

**Saída:**
- `List<String>` - Lista de identificadores de documentos gerados

**Regra:**
- Gera documentação específica para o tipo de estratégia
- Cada estratégia determina quais documentos são necessários

### 2. requiresClinicalDocumentation
**Saída:**
- `boolean` - true se documentação clínica é obrigatória

**Regra:**
- Estratégias de necessidade médica requerem documentação clínica
- Estratégias administrativas podem não requerer

### 3. getMinimumDocumentCount
**Saída:**
- `int` - Número mínimo de documentos para validação

**Regra:**
- Define quantos documentos são necessários para completude
- Usado para validação do pacote de recurso

### 4. getStrategyType
**Saída:**
- `String` - Código identificador da estratégia

**Regra:**
- Retorna identificador único (ex: "STANDARD", "MEDICAL_NECESSITY")
- Usado para registro e seleção de estratégia

## Implementações Conhecidas

1. **StandardAppealStrategy** - Recursos padrão (3 documentos mínimos)
2. **MedicalNecessityAppealStrategy** - Necessidade médica (6 documentos mínimos)
3. Outras estratégias (técnica, administrativa, híbrida)

## Regras de Negócio

### RN-APPEAL-STRATEGY-001: Seleção de Estratégia
**Descrição:** Sistema deve selecionar estratégia apropriada baseada no tipo de glosa
**Implementação:** `AppealStrategyRegistry`

### RN-APPEAL-STRATEGY-002: Documentação Mínima
**Descrição:** Cada estratégia define seu requisito mínimo de documentos
**Valores:**
- Standard: 3 documentos (carta + documento estratégia + admin)
- Medical Necessity: 6 documentos (carta + 3 docs estratégia + clínico + admin)

### RN-APPEAL-STRATEGY-003: Documentação Clínica Condicional
**Descrição:** Documentação clínica é obrigatória apenas para certas estratégias
**Critério:** Definido por `requiresClinicalDocumentation()`

## Integração

### Services que Utilizam
- `AppealDocumentService` - Coordena geração de documentos
- `AppealStrategyRegistry` - Gerencia registro de estratégias
- `PrepareGlosaAppealDelegate` - Delega BPMN que usa estratégias

### Delegates Relacionados
- `PrepareGlosaAppealDelegate` - Prepara pacote de recurso
- `CompensateAppealDelegate` - Compensação de recursos

## Padrões de Design

- **Strategy Pattern:** Encapsula algoritmos de geração de documentos
- **Registry Pattern:** Gerenciado por `AppealStrategyRegistry`
- **Factory Pattern:** Estratégias criadas via Spring DI

## Extensibilidade

Para adicionar nova estratégia:
1. Implementar interface `AppealStrategy`
2. Anotar com `@Component` para Spring DI
3. Definir `getStrategyType()` único
4. Registrar em `AppealStrategyRegistry`

## Conformidade Regulatória

- **ANS RN 443/2019:** Suporta prazos e requisitos de recursos
- **TISS 3.06.00:** Alinhado com tipos de recurso TISS
- **RDC 82/2003:** Documentação clínica quando necessário

## Referências
- `AppealRequest.java` - Objeto de entrada
- `AppealPackage.java` - Resultado da estratégia
- `AppealStrategyRegistry.java` - Gerenciamento de estratégias
