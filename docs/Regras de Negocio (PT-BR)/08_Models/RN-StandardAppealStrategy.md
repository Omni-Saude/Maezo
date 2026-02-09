# RN-StandardAppealStrategy - Estratégia de Recurso Padrão

**Categoria:** Modelo de Domínio - Implementação de Estratégia
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.strategy.StandardAppealStrategy`
**Tipo:** Implementação Concreta de AppealStrategy

---

## Descrição
Implementação padrão da estratégia de recurso para glosas comuns que não requerem documentação clínica especializada. Usada como fallback quando nenhuma estratégia específica é aplicável.

## Características

### Configuração
- **Tipo:** "STANDARD"
- **Documentos Mínimos:** 3
- **Documentação Clínica:** Não obrigatória
- **Spring Component:** "@Component("standardAppeal")"

## Métodos Implementados

### 1. generateDocuments
```java
public List<String> generateDocuments(AppealRequest request)
```

**Comportamento:**
- Gera 1 documento padrão: "STANDARD_DOC_{UUID}"
- Log de debug da geração
- Retorna lista com documento gerado

**Exemplo de Saída:**
```
["STANDARD_DOC_a1b2c3d4-e5f6-7890-abcd-ef1234567890"]
```

### 2. requiresClinicalDocumentation
```java
public boolean requiresClinicalDocumentation()
```
**Retorno:** `false` - Não requer documentação clínica

### 3. getMinimumDocumentCount
```java
public int getMinimumDocumentCount()
```
**Retorno:** `3` - Carta de recurso + documento padrão + documentos administrativos

### 4. getStrategyType
```java
public String getStrategyType()
```
**Retorno:** `"STANDARD"`

## Estrutura de Documentos

### Pacote Completo (3 documentos)
1. **Carta de Recurso** (gerada por `AppealDocumentService`)
2. **Documento Padrão** (gerado por esta estratégia)
3. **Documentos Administrativos** (tracking + checklist)

## Casos de Uso

### Tipos de Glosa Aplicáveis
- Glosas administrativas simples
- Erros de faturamento corrigíveis
- Inconsistências documentais básicas
- Recursos rápidos de revisão

### Aliases Registrados
Estratégia padrão é usada para:
- "COMPREHENSIVE_APPEAL"
- "QUICK_REVIEW_AND_RESUBMIT"
- "AUTHORIZATION_APPEAL"
- "ELIGIBILITY_VERIFICATION_APPEAL"
- "CODING_REVIEW_APPEAL"
- "MODIFIER_CORRECTION_APPEAL"
- "TIMELY_FILING_APPEAL"
- "DUPLICATE_CLAIM_RESOLUTION"
- "STANDARD_APPEAL"

## Regras de Negócio

### RN-STD-APPEAL-001: Fallback Strategy
**Descrição:** Estratégia padrão é usada quando nenhuma específica é encontrada
**Implementação:** `AppealStrategyRegistry.getStrategy()`

### RN-STD-APPEAL-002: Documentação Simplificada
**Descrição:** Recursos padrão não necessitam documentação clínica complexa
**Critério:** `requiresClinicalDocumentation() = false`

### RN-STD-APPEAL-003: Validação Mínima
**Descrição:** Pacote deve conter ao menos 3 documentos
**Componentes:**
- 1 carta de recurso
- 1 documento padrão
- 2 documentos administrativos (tracking + checklist)

## Fluxo de Execução

```
1. AppealDocumentService.prepareAppealPackage()
   ↓
2. AppealStrategyRegistry.getStrategy("STANDARD")
   ↓
3. StandardAppealStrategy.generateDocuments()
   ↓
4. Gera "STANDARD_DOC_{UUID}"
   ↓
5. AppealDocumentService adiciona:
   - Carta de recurso
   - Documento padrão
   - Documentos administrativos
   ↓
6. Validação: documentIds.size() >= 3
```

## Integração

### Injetado Por
- Spring Container como `@Component`
- `AppealStrategyRegistry` como default strategy

### Usado Por
- `AppealDocumentService` - Geração de pacotes
- `AppealStrategyRegistry` - Fallback e aliases
- `PrepareGlosaAppealDelegate` - Preparação BPMN

## Logging

```
DEBUG: Generated standard appeal document
INFO: Appeal package prepared: glosaId={id}, documents=3, complete=true
```

## Testes

**Arquivo:** `PrepareGlosaAppealDelegateTest.java`

Cenários testados:
- Geração de documento padrão
- Contagem mínima de 3 documentos
- Não requer documentação clínica
- Fallback para estratégias não encontradas

## Extensão

### Criar Estratégia Customizada
```java
@Component("customAppeal")
public class CustomAppealStrategy implements AppealStrategy {
    @Override
    public List<String> generateDocuments(AppealRequest request) {
        // Implementação customizada
    }

    @Override
    public String getStrategyType() {
        return "CUSTOM";
    }

    @Override
    public int getMinimumDocumentCount() {
        return 4; // Customizar conforme necessário
    }

    @Override
    public boolean requiresClinicalDocumentation() {
        return false; // ou true
    }
}
```

## Conformidade

- **ANS RN 443/2019:** Suporta prazos de recursos (30 dias)
- **TISS 3.06.00:** Compatível com tipos de recurso TISS
- **Padrão BPMN:** Integrado com workflow Camunda

## Performance

- **Complexidade:** O(1) - geração simples de 1 documento
- **Memória:** Mínima - apenas UUID e string
- **I/O:** Sem acesso externo - geração em memória

## Referências
- `AppealStrategy.java` - Interface base
- `MedicalNecessityAppealStrategy.java` - Estratégia alternativa
- `AppealStrategyRegistry.java` - Gerenciamento
