# RN-MedicalNecessityAppealStrategy - Estratégia de Recurso por Necessidade Médica

**Categoria:** Modelo de Domínio - Estratégia Clínica
**Arquivo:** `com.hospital.revenuecycle.domain.appeal.strategy.MedicalNecessityAppealStrategy`
**Tipo:** Implementação Especializada de AppealStrategy

---

## Descrição
Estratégia específica para recursos de glosa relacionados a necessidade médica (medical necessity). Gera documentação clínica completa incluindo justificativas médicas, declarações de médicos e referências a diretrizes clínicas.

## Características

### Configuração
- **Tipo:** "MEDICAL_NECESSITY"
- **Documentos Mínimos:** 6
- **Documentação Clínica:** Obrigatória
- **Spring Component:** "@Component("medicalNecessityAppeal")"

## Métodos Implementados

### 1. generateDocuments
```java
public List<String> generateDocuments(AppealRequest request)
```

**Comportamento:**
Gera 3 documentos específicos de necessidade médica:

1. **Justificativa de Necessidade Médica**
   - ID: "MEDICAL_NECESSITY_JUSTIFICATION_{UUID}"
   - Contém argumentação clínica para o procedimento

2. **Declaração do Médico**
   - ID: "PHYSICIAN_STATEMENT_{UUID}"
   - Atestado do médico responsável

3. **Diretrizes Clínicas**
   - ID: "CLINICAL_GUIDELINES_{UUID}"
   - Referências a protocolos e evidências médicas

**Exemplo de Saída:**
```
[
  "MEDICAL_NECESSITY_JUSTIFICATION_a1b2c3d4-...",
  "PHYSICIAN_STATEMENT_e5f6g7h8-...",
  "CLINICAL_GUIDELINES_i9j0k1l2-..."
]
```

### 2. requiresClinicalDocumentation
```java
public boolean requiresClinicalDocumentation()
```
**Retorno:** `true` - Documentação clínica é obrigatória

### 3. getMinimumDocumentCount
```java
public int getMinimumDocumentCount()
```
**Retorno:** `6` - Carta + 3 docs estratégia + clínico + admin

### 4. getStrategyType
```java
public String getStrategyType()
```
**Retorno:** `"MEDICAL_NECESSITY"`

## Estrutura de Documentos

### Pacote Completo (6+ documentos)
1. **Carta de Recurso** (AppealDocumentService)
2. **Justificativa de Necessidade Médica** (generateJustification)
3. **Declaração do Médico** (generatePhysicianStatement)
4. **Diretrizes Clínicas** (generateClinicalGuidelines)
5. **Documentação Clínica** (collectClinicalDocumentation)
   - Prontuários médicos
   - Exames laboratoriais
   - Imagens médicas
   - Histórico do paciente
6. **Documentos Administrativos** (tracking + checklist)

## Casos de Uso

### Tipos de Glosa Aplicáveis
- Glosa por falta de necessidade médica
- Procedimento considerado "não coberto"
- Recusa por "experimental ou investigacional"
- Negativa de autorização prévia
- Internação considerada desnecessária
- Nível de cuidado questionado

### Critérios de Necessidade Médica
Documentação deve demonstrar:
- Condição médica do paciente
- Indicação clínica do procedimento
- Evidências científicas de eficácia
- Ausência de alternativas menos invasivas
- Conformidade com protocolos clínicos

## Regras de Negócio

### RN-MED-APPEAL-001: Documentação Clínica Obrigatória
**Descrição:** Recursos de necessidade médica DEVEM incluir prontuários clínicos
**Implementação:** `requiresClinicalDocumentation() = true`
**Validação:** `AppealDocumentService.collectClinicalDocumentation()`

### RN-MED-APPEAL-002: Declaração Médica
**Descrição:** Declaração do médico responsável é obrigatória
**Conteúdo Mínimo:**
- Identificação do médico (CRM)
- Diagnóstico do paciente
- Justificativa clínica do procedimento
- Data e assinatura

### RN-MED-APPEAL-003: Diretrizes Clínicas
**Descrição:** Recurso deve referenciar protocolos médicos reconhecidos
**Fontes Aceitas:**
- Sociedades médicas especializadas
- Protocolos hospitalares aprovados
- Diretrizes internacionais (WHO, AHA, ACC, etc.)
- Literatura médica peer-reviewed

### RN-MED-APPEAL-004: Pacote Mínimo 6 Documentos
**Descrição:** Validação de completude exige ao menos 6 documentos
**Fórmula:** `documentIds.size() >= getMinimumDocumentCount()`

### RN-MED-APPEAL-005: Evidência Baseada
**Descrição:** Argumentação deve ser baseada em evidências científicas
**Níveis de Evidência:**
- Nível 1: Meta-análises e ensaios clínicos randomizados
- Nível 2: Estudos de coorte
- Nível 3: Estudos de caso-controle
- Nível 4: Séries de casos
- Nível 5: Opinião de especialista

## Fluxo de Execução

```
1. AppealDocumentService.prepareAppealPackage()
   ↓
2. AppealStrategyRegistry.getStrategy("MEDICAL_NECESSITY")
   ↓
3. MedicalNecessityAppealStrategy.generateDocuments()
   ↓
4. Gera 3 documentos:
   - generateJustification() → UUID_JUSTIFICATION
   - generatePhysicianStatement() → UUID_STATEMENT
   - generateClinicalGuidelines() → UUID_GUIDELINES
   ↓
5. collectClinicalDocumentation()
   - Busca prontuário por encounterId
   - Adiciona CLINICAL_RECORDS_{encounterId}
   ↓
6. generateAdministrativeDocuments()
   - APPEAL_TRACKING_{glosaId}
   - APPEAL_CHECKLIST_{glosaId}
   ↓
7. Validação: documentIds.size() >= 6
```

## Integração

### Services Dependentes
- `AppealDocumentService` - Coordena geração
- `ClinicalDocumentCollector` - Coleta prontuários
- `EHRIntegrationService` - Acesso ao prontuário eletrônico

### Dados Clínicos Necessários
- `request.encounterId` - Identificação do atendimento
- `request.providerId` - Médico responsável
- `request.glosaDetails` - Detalhes da negativa

## Aliases e Mapeamento

Registrado em `AppealStrategyRegistry` como:
- "MEDICAL_NECESSITY" (principal)
- "MEDICAL_NECESSITY_APPEAL" (alias)

## Logging

```
DEBUG: Generating medical necessity documents
DEBUG: Generated medical necessity justification
DEBUG: Generated physician statement
DEBUG: Generated clinical guidelines reference
DEBUG: Generated 3 medical necessity documents
INFO: Appeal package prepared: glosaId={id}, documents=6+, complete=true
```

## Testes

**Arquivo:** `PrepareGlosaAppealDelegateTest.java`

Cenários testados:
- Geração de 3 documentos específicos
- Obrigatoriedade de documentação clínica
- Contagem mínima de 6 documentos
- Validação de completude do pacote

## Conformidade Regulatória

### ANS RN 443/2019
- Art. 3º: Prazos para recursos de necessidade médica
- Art. 4º: Documentação comprobatória obrigatória
- Art. 5º: Avaliação técnica por profissional habilitado

### CFM Resolução 1246/1988
- Prontuário médico obrigatório
- Assinatura e carimbo do médico
- Dados clínicos completos

### TISS 3.06.00
- Guia SP/SADT com justificativa clínica
- Campos de indicação clínica preenchidos
- Anexos clínicos obrigatórios

### Lei 13.003/2014 (Lei da Transparência)
- Operadora deve informar critérios de necessidade médica
- Paciente tem direito a segunda opinião médica

## Performance

- **Complexidade:** O(1) para geração de IDs
- **I/O:** Possível acesso ao EHR para documentos clínicos
- **Memória:** 3 strings UUID + lista de documentos clínicos

## Melhores Práticas

### Documentação Clínica
- Incluir resultados de exames relevantes
- Anexar laudos de especialistas
- Referenciar protocolos institucionais
- Documentar tentativas de tratamentos alternativos

### Justificativa Médica
- Descrever condição clínica do paciente
- Explicar indicação do procedimento
- Citar evidências científicas
- Demonstrar urgência/necessidade

### Diretrizes Clínicas
- Usar protocolos da sociedade médica especializada
- Citar guidelines internacionais quando aplicável
- Incluir referências bibliográficas
- Demonstrar conformidade com padrão de cuidado

## Extensão

### Adicionar Estratégia Clínica Customizada
```java
@Component("criticalCareAppeal")
public class CriticalCareAppealStrategy extends MedicalNecessityAppealStrategy {
    @Override
    public List<String> generateDocuments(AppealRequest request) {
        List<String> docs = super.generateDocuments(request);
        // Adicionar documentos específicos de UTI
        docs.add(generateICUJustification(request));
        docs.add(generateSeverityScores(request));
        return docs;
    }

    @Override
    public int getMinimumDocumentCount() {
        return 8; // Maior devido a complexidade
    }
}
```

## Referências
- `AppealStrategy.java` - Interface base
- `StandardAppealStrategy.java` - Estratégia alternativa
- `ClinicalDocumentCollector.java` - Coleta de documentos clínicos
- `AppealRequest.java` - Dados de entrada
