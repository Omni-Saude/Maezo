# Regras de Negócio: ValidateCodesDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/coding/ValidateCodesDelegate.java`
> **Categoria:** CODING (Codificação Médica - Validação)
> **Total de Regras:** 14

## 📋 Sumário Executivo

O delegate ValidateCodesDelegate é responsável por validação abrangente de códigos médicos (ICD-10 e TUSS) antes da submissão de contas hospitalares. Esta validação multi-camadas combina validações programáticas de formato, regras de negócio específicas de cada sistema de codificação, e validação avançada via CodingService com IA.

A validação garante conformidade com padrões brasileiros de codificação (TUSS para procedimentos e ICD-10 para diagnósticos), verifica compatibilidade entre códigos diagnósticos e procedimentos, e identifica potenciais problemas de necessidade médica antes da auditoria de convênios. O processo utiliza tanto validações estruturais (formato, capítulos válidos) quanto validações semânticas (compatibilidade clínica, necessidade médica).

## 📜 Catálogo de Regras

### RN-COD-VAL-001: Validação de Presença de Códigos

**Descrição:** Garante que ao menos um código (diagnóstico ou procedimento) foi fornecido para validação antes de prosseguir.

**Lógica:**
```
SE (procedureCodes é nulo OU vazio)
  E (diagnosisCodes é nulo OU vazio)
ENTÃO lançar BpmnError "VALIDATION_FAILED"
  - Mensagem: "No codes provided for validation"
  - Interromper processo
SENÃO prosseguir com validação
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| procedureCodes | List&lt;String&gt; | Ao menos 1 lista não-vazia | ["4.03.01.19-0"] |
| diagnosisCodes | List&lt;String&gt; | Ao menos 1 lista não-vazia | ["J18.9"] |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: executeBusinessLogic
- Linhas: 78-82

---

### RN-COD-VAL-002: Validação de Formato TUSS

**Descrição:** Valida formato estrutural de códigos TUSS (Terminologia Unificada da Saúde Suplementar) conforme padrão ANS brasileiro.

**Lógica:**
```
FORMATO TUSS: 4.XX.XX.XX-X
  - Deve começar com "4." (procedimentos)
  - Duas sequências de 2 dígitos
  - Dígito verificador após hífen

REGEX: ^\\d\\.\\d{2}\\.\\d{2}\\.\\d{2}-\\d$

PARA CADA código em procedureCodes:
  SE código não match regex
  ENTÃO adicionar erro:
    "Invalid TUSS code format at index {i}: '{code}'. Expected format: 4.XX.XX.XX-X"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| procedureCode | String | Padrão TUSS | "4.03.01.19-0" |
| TUSS_CODE_PATTERN | String | Regex fixo | "^\\d\\.\\d{2}\\.\\d{2}\\.\\d{2}-\\d$" |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateProcedureCodes
- Linhas: 141-159, constante linha 58

---

### RN-COD-VAL-003: Validação de Formato ICD-10

**Descrição:** Valida formato estrutural de códigos ICD-10 (Classificação Internacional de Doenças) conforme padrão OMS.

**Lógica:**
```
FORMATO ICD-10: A00.0
  - Letra maiúscula A-Z (capítulo)
  - 2 dígitos (categoria)
  - Ponto decimal
  - 1 dígito (subcategoria)

REGEX: ^[A-Z]\\d{2}\\.\\d$

PARA CADA código em diagnosisCodes:
  SE código não match regex
  ENTÃO adicionar erro:
    "Invalid ICD-10 code format at index {i}: '{code}'. Expected format: A00.0"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| diagnosisCode | String | Padrão ICD-10 | "J18.9" |
| ICD10_CODE_PATTERN | String | Regex fixo | "^[A-Z]\\d{2}\\.\\d$" |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateDiagnosisCodes
- Linhas: 171-189, constante linha 59

---

### RN-COD-VAL-004: Validação de Capítulo TUSS

**Descrição:** Valida que códigos TUSS pertencem a capítulos válidos da tabela ANS (01-99) e que procedimentos começam com "4".

**Lógica:**
```
EXTRAIR componentes do código TUSS:
  - Código: "4.03.01.19-0"
  - Prefixo: "4" (tipo procedimento)
  - Capítulo: "03" (segunda parte)
  - Procedimento: "01"
  - Item: "19"
  - Dígito verificador: "0"

VALIDAÇÕES:
1. SE prefixo != "4"
   ENTÃO erro: "Procedure codes must start with '4.'"

2. SE capítulo < 01 OU capítulo > 99
   ENTÃO erro: "Invalid TUSS chapter. Chapter must be 01-99"

3. SE dígito verificador < 0 OU > 9
   ENTÃO erro: "Invalid TUSS check digit"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| chapter | String | "01" a "99" | "03" |
| checkDigit | Integer | 0-9 | 0 |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateTUSSCodeRules
- Linhas: 202-237

---

### RN-COD-VAL-005: Validação de Capítulo ICD-10

**Descrição:** Valida que códigos ICD-10 pertencem a capítulos válidos (A-Z) e que categoria numérica está no range 00-99.

**Lógica:**
```
EXTRAIR componentes do código ICD-10:
  - Código: "J18.9"
  - Capítulo: "J" (letra)
  - Categoria: "18" (números)
  - Subcategoria: "9" (após ponto)

VALIDAÇÕES:
1. SE capítulo < 'A' OU capítulo > 'Z'
   ENTÃO erro: "Chapter letter must be A-Z"

2. SE categoria < 00 OU categoria > 99
   ENTÃO erro: "Invalid ICD-10 category. Category must be 00-99"

3. SE capítulo = 'U' (códigos especiais)
   ENTÃO validar uso para propósitos especiais

4. SE subcategoria não é dígito
   ENTÃO erro: "Fifth character must be digit"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| chapter | Character | A-Z | 'J' |
| category | Integer | 00-99 | 18 |
| subcategory | Character | 0-9 | '9' |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateICD10CodeRules
- Linhas: 254-301

---

### RN-COD-VAL-006: Validação de Códigos Vazios

**Descrição:** Detecta e reporta códigos nulos ou vazios (após trim) nas listas de entrada.

**Lógica:**
```
PARA CADA código em procedureCodes:
  SE código é nulo OU código.trim() está vazio
  ENTÃO adicionar erro:
    "Procedure code at index {i} is empty"

PARA CADA código em diagnosisCodes:
  SE código é nulo OU código.trim() está vazio
  ENTÃO adicionar erro:
    "Diagnosis code at index {i} is empty"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| code | String | Não-nulo, não-vazio | "J18.9" |
| index | Integer | Posição na lista | 0 |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Métodos: validateProcedureCodes (linhas 145-148), validateDiagnosisCodes (linhas 175-178)

---

### RN-COD-VAL-007: Validação via CodingService (IA)

**Descrição:** Executa validação avançada através do CodingService que utiliza IA para verificações complexas (existência em tabelas, status, restrições clínicas).

**Lógica:**
```
EXECUTAR CodingService.validateCodeCombinations():
  - diagnosisCodes: Lista de ICD-10
  - procedureCodes: Lista de TUSS

VALIDAÇÕES REALIZADAS pela IA:
  1. Código existe na tabela de referência
  2. Código está ativo (não deprecado)
  3. Código é billable (não é header)
  4. Lateralidade requerida (7th character)
  5. Restrições de idade/gênero
  6. Período de validade do código

RETORNAR CodeValidationResult:
  - isValid: Boolean
  - errors: Lista de erros encontrados
  - warnings: Lista de avisos
  - medicallyNecessary: Boolean
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| diagnosisCodes | List&lt;String&gt; | Validados estruturalmente | ["J18.9"] |
| procedureCodes | List&lt;String&gt; | Validados estruturalmente | ["4.03.01.19-0"] |
| serviceValidation | CodeValidationResult | Retorno do serviço | {...} |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: executeBusinessLogic
- Linhas: 107-113

---

### RN-COD-VAL-008: Validação de Compatibilidade Código-Diagnóstico

**Descrição:** Verifica se procedimentos têm diagnósticos compatíveis que justifiquem medicamente a realização.

**Lógica:**
```
SE há procedureCodes E há diagnosisCodes
ENTÃO para cada procedureCode:
  - Verificar compatibilidade com diagnoses
  - Basear em:
    * Diretrizes de necessidade médica
    * Políticas de cobertura de convênios
    * Critérios de adequação clínica

  SE nenhuma compatibilidade encontrada
  ENTÃO adicionar warning:
    "Procedure code '{code}' may not be compatible with provided diagnoses. Medical necessity review required."

VALIDAR regras específicas:
  - Procedimentos cirúrgicos (capítulo 30-39) requerem diagnóstico primário
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| procedureCode | String | TUSS validado | "4.03.01.19-0" |
| diagnosisCodes | List&lt;String&gt; | ICD-10 validados | ["J18.9"] |
| hasCompatibleDiagnosis | Boolean | Resultado da verificação | true |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateCodeCompatibility
- Linhas: 318-350

---

### RN-COD-VAL-009: Validação de Necessidade Médica

**Descrição:** Verifica se há justificativa de diagnóstico adequada para procedimentos realizados (medical necessity).

**Lógica:**
```
VERIFICAR compatibilidade entre procedimento e diagnósticos:
  - Consultar crosswalk CPT-to-ICD-10
  - Verificar LCD/NCD (políticas de cobertura)
  - Aplicar critérios de adequação clínica

COMPATIBILIDADE determinada por:
  1. Diretrizes de necessidade médica
  2. Políticas de cobertura do convênio
  3. Regras de adequação clínica

RETORNAR hasCompatibleDiagnosis:
  - true: Ao menos 1 diagnóstico justifica procedimento
  - false: Nenhum diagnóstico adequado encontrado
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| procedureCode | String | Código TUSS | "4.03.01.19-0" |
| diagnosisCodes | List&lt;String&gt; | Lista ICD-10 | ["J18.9", "I10"] |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: checkProcedureDiagnosisCompatibility
- Linhas: 359-379

---

### RN-COD-VAL-010: Validação de Procedimentos Cirúrgicos

**Descrição:** Aplica regras específicas para procedimentos cirúrgicos de alta complexidade que exigem diagnóstico primário.

**Lógica:**
```
EXTRAIR capítulo TUSS:
  - Código: "4.33.01.19-0"
  - Capítulo: "33" (terceiro e quarto dígitos)

SE capítulo >= 30 E capítulo <= 39 (procedimentos cirúrgicos)
ENTÃO:
  - Requerer ao menos 1 diagnóstico presente
  - SE diagnosisCodes está vazio
    ENTÃO erro: "Surgical procedure '{code}' requires primary diagnosis"

CAPÍTULOS 30-39: Alta complexidade cirúrgica
  - Requerem justificativa diagnóstica obrigatória
  - Não podem ser realizados sem diagnóstico de suporte
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| chapter | Integer | 30-39 para cirúrgicos | 33 |
| diagnosisCodes | List&lt;String&gt; | Obrigatório não-vazio | ["J18.9"] |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateProcedureDiagnosisRules
- Linhas: 388-414

---

### RN-COD-VAL-011: Validação de Completude de Diagnóstico

**Descrição:** Verifica se há diagnósticos suficientes e específicos para justificar os procedimentos realizados.

**Lógica:**
```
VALIDAÇÕES:

1. Presença de Diagnóstico
   SE há procedureCodes E diagnosisCodes está vazio
   ENTÃO erro: "Procedures require at least one diagnosis code for medical necessity"

2. Especificidade de Códigos
   CONTAR códigos não-específicos (terminam em .9)

   SE nonSpecificCount > diagnosisCodes.size() / 2
   ENTÃO warning:
     "Too many non-specific diagnosis codes ({count} of {total}).
      More specific diagnosis codes recommended for claim approval."

EXEMPLO:
  - Total diagnoses: 4
  - Non-specific (.9): 3
  - 3 > 4/2 → Warning gerado
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| diagnosisCodes | List&lt;String&gt; | Requerido se procedimentos | ["J18.9", "I10"] |
| nonSpecificCount | Long | Calculado | 1 |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: validateDiagnosisCompleteness
- Linhas: 426-448

---

### RN-COD-VAL-012: Armazenamento de Resultados de Validação

**Descrição:** Persiste todos os resultados da validação em escopo PROCESS para uso downstream por audit, billing e submission.

**Lógica:**
```
DETERMINAR codesValid:
  - SE validationErrors está vazio
    ENTÃO codesValid = true
  - SENÃO codesValid = false

ARMAZENAR em escopo PROCESS:
  - codesValid: Boolean (passou validação?)
  - validationErrors: List de mensagens de erro
  - validationWarnings: List de avisos do CodingService
  - medicallyNecessary: Boolean (necessidade médica OK?)
  - validationMethod: "AI_COMPREHENSIVE" (rastreabilidade)
  - totalCodesValidated: Contagem total de códigos
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| codesValid | Boolean | Escopo: Process | true |
| validationErrors | List&lt;String&gt; | Escopo: Process | [] |
| validationWarnings | List&lt;String&gt; | Escopo: Process | ["Non-specific code"] |
| medicallyNecessary | Boolean | Escopo: Process | true |
| validationMethod | String | Fixo | "AI_COMPREHENSIVE" |
| totalCodesValidated | Integer | Escopo: Process | 5 |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: executeBusinessLogic
- Linhas: 116-125

---

### RN-COD-VAL-013: Logging de Validação

**Descrição:** Registra logs informativos e de advertência sobre o resultado da validação para monitoramento e auditoria.

**Lógica:**
```
SE codesValid = true
ENTÃO emitir log INFO:
  - "Code validation successful: all {count} codes are valid and compatible"
  - Incluir contagem total de códigos validados

SENÃO emitir log WARNING:
  - "Code validation failed with {errorCount} errors: {errors}"
  - Incluir lista completa de erros
  - Incluir contagem de erros
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| codesValid | Boolean | Resultado | true |
| totalCodes | Integer | procedure + diagnosis | 5 |
| errorCount | Integer | validationErrors.size() | 0 |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: executeBusinessLogic
- Linhas: 126-132

---

### RN-COD-VAL-014: Idempotência de Validação

**Descrição:** Define validação como operação read-only naturalmente idempotente, podendo ser executada múltiplas vezes sem efeitos colaterais.

**Lógica:**
```
OPERAÇÃO: Somente leitura
  - Não modifica dados de conta
  - Não altera códigos
  - Não persiste estado interno
  - Pode ser re-executada sem impacto

RETORNO: requiresIdempotency() = false
  (validação é naturalmente idempotente)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| requiresIdempotency | Boolean | Sempre false | false |

**Rastreabilidade:**
- Arquivo: ValidateCodesDelegate.java
- Método: requiresIdempotency
- Linhas: 512-514

---

## 📊 Métricas e Monitoramento

**Operação:** validate_codes
**Idempotência:** Não requerida (naturalmente idempotente - read-only)
**Escopo de Variáveis:** PROCESS (compartilhadas com audit, billing, submission)
**Validação IA:** CodingService.validateCodeCombinations()

## 🔗 Integrações

- **CodingService:** Validação avançada com IA (existência, status, restrições)
- **TUSS Reference Table:** Validação de códigos de procedimentos ANS
- **ICD-10-CM Reference:** Validação de códigos de diagnóstico
- **LCD/NCD Policies:** Políticas de cobertura local e nacional
- **CPT-to-ICD-10 Crosswalk:** Compatibilidade procedimento-diagnóstico
- **Medicare CCI Edits:** Iniciativa de codificação correta

## 📝 Observações Técnicas

1. **Validação Multi-Camada:**
   - Camada 1: Formato estrutural (regex)
   - Camada 2: Regras de negócio (capítulos, dígitos)
   - Camada 3: IA (existência, status, compatibilidade)

2. **Padrões de Formato:**
   - TUSS: `4.XX.XX.XX-X` (procedimentos ANS)
   - ICD-10: `A00.0` (padrão OMS)

3. **Capítulos TUSS:**
   - Prefixo "4": Procedimentos
   - Capítulos 01-99: Categorias ANS
   - Capítulos 30-39: Alta complexidade cirúrgica

4. **Capítulos ICD-10:**
   - A-Z: Capítulos de doenças
   - U: Códigos para propósitos especiais
   - Categorias 00-99 por capítulo

5. **Códigos Não-Específicos:**
   - Terminam em `.9` (unspecified)
   - > 50% gera warning de especificidade
   - Podem reduzir reembolso

6. **Validações Avançadas (via IA):**
   - Existência em tabela de referência
   - Status ativo/billable
   - Lateralidade (7th character extension)
   - Restrições idade/gênero
   - Período de validade

7. **Medical Necessity:**
   - Verificada via crosswalk CPT-ICD-10
   - Baseada em LCD/NCD
   - Critérios clínicos de adequação

8. **DMN Integration:** Comentado para integração futura (linhas 470-504)

---

## X. Conformidade Regulatória

### Normativas ANS
- **RN 305/2012:** Padronização de terminologia médica (Arts. 8-12)
- **RN 443/2019:** Padrão TISS para codificação de procedimentos (Anexo II)
- **RN 465/2021:** Atualização de tabelas de terminologia (TUSS, CBHPM)
- **RN 500/2022:** Regras de preenchimento de guias (Arts. 24-27)

### Padrão TISS (Versão 4.02.02)
- **Componente:** Guia de Serviço Profissional / SADT
- **Campo 37:** Tabela de código (TUSS/CBHPM)
- **Campo 38:** Código do procedimento
- **Campo 24:** Código CID-10 (Diagnóstico)
- **Validação:** Existência, formato, status ativo/billable

### ICD-10-CM (CMS Guidelines 2024)
- **Chapter Structure:** Validação de categorias por capítulo (00-99)
- **7th Character Extensions:** Obrigatoriedade de lateralidade (A, D, S)
- **Placeholder 'X':** Uso correto em códigos de 6-7 caracteres
- **Unspecified Codes (.9):** Alerta para especificidade insuficiente
- **Excludes1/Excludes2:** Validação de códigos mutuamente exclusivos

### LGPD (Lei 13.709/2018)
- **Art. 6º, V:** Transparência na validação de dados de saúde
- **Art. 11, II, 'a':** Dados sensíveis de saúde - exatidão obrigatória
- **Art. 18, II:** Acesso aos dados de validação pelo titular
- **Art. 46:** Responsabilidade solidária por inexatidão de códigos

### SOX (Sarbanes-Oxley)
- **Section 302:** Controles de validação para integridade financeira
- **Section 404:** Auditoria de processos de codificação
- **Section 409:** Divulgação de falhas de validação

### CMS-1500 / UB-04 Compliance
- **CMS-1500 Box 21:** ICD Indicator e formatos válidos
- **CMS-1500 Box 24D:** CPT/HCPCS codes com modificadores
- **UB-04 FL67:** Principal diagnosis code (validação de especificidade)
- **LCD/NCD Compliance:** Medical necessity via crosswalk CPT-ICD

---

## XI. Notas de Migração

### Complexidade de Migração
**Rating:** 🟢 MÉDIO (6/10)

**Justificativa:**
- Validação determinística (regras claras)
- Tabelas de referência estáveis (TUSS, CID-10)
- Integração com DMN já projetada (linhas 470-504)

### Mudanças Incompatíveis (Breaking Changes)
1. **Tabelas de Referência:** Necessita versionamento trimestral (ICD-10-CM, TUSS)
2. **Extensões ICD-10:** 7th character obrigatório para capítulos S, T, V-Y
3. **Medical Necessity:** Crosswalk CPT-ICD requer base de LCD/NCD atualizada
4. **Formato de Violações:** Nova estrutura JSON para detalhamento

### Migração para DMN
**Candidato:** ✅ SIM (ALTA PRIORIDADE)

```yaml
dmn_migration:
  decision_tables:
    - decision_id: "icd10-format-validation"
      decision_name: "Validação de Formato ICD-10"
      inputs:
        - icdCode: String
        - chapter: String (00-99)
      outputs:
        - isValid: Boolean
        - violationType: String
        - requiredExtension: String
      rules:
        - "Capítulos S/T requerem 7th character (A/D/S)"
        - "Placeholder 'X' obrigatório para códigos 6-7 chars"
        - "Formato: Letra + 2 dígitos + ponto + 1-4 caracteres"

    - decision_id: "code-specificity-check"
      decision_name: "Verificação de Especificidade"
      inputs:
        - codeString: String
        - percentageUnspecified: Float
      outputs:
        - specificityLevel: String (HIGH/MEDIUM/LOW)
        - requiresWarning: Boolean
      rules:
        - "Códigos terminando em .9 = LOW"
        - "> 50% códigos .9 = Warning obrigatório"

    - decision_id: "medical-necessity-validation"
      decision_name: "Validação de Necessidade Médica"
      inputs:
        - cptCode: String
        - icdCodes: List<String>
        - serviceDate: Date
      outputs:
        - isMedicallyNecessary: Boolean
        - lcdReference: String
        - failureReason: String
      data_sources:
        - cpt_icd_crosswalk
        - lcd_ncd_database
```

### Fases de Implementação
**Fase 1 - Core Validation (Sprint 7):**
- Validação de formato ICD-10/CPT
- Verificação de existência em tabelas TUSS/CBHPM
- Detecção de códigos não-específicos (.9)

**Fase 2 - DMN Integration (Sprint 8):**
- Migração de regras de validação para DMN
- Integração com Camunda Decision Engine
- Versionamento de decision tables

**Fase 3 - Medical Necessity (Sprint 9):**
- Crosswalk CPT-ICD-10
- LCD/NCD validation
- Regras de idade/gênero/lateralidade

### Dependências Críticas
```yaml
dependencies:
  reference_tables:
    - icd10_cm_codes (CMS - atualização anual Oct 1)
    - tuss_procedures (ANS - atualização trimestral)
    - cbhpm_codes (AMB - atualização anual)
    - cpt_codes (AMA - atualização anual Jan 1)

  external_services:
    - CMS ICD-10 API (validação oficial)
    - ANS Web Service (status TUSS)
    - LCD/NCD Database (CMS Contractor)

  dmn_tables:
    - icd10-format-validation.dmn
    - code-specificity-check.dmn
    - medical-necessity-validation.dmn
```

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Contexto:** Medical Coding & Billing Compliance

**Subdomínio:** Code Validation (Core Domain)

**Responsabilidades:**
- Validação de formato e existência de códigos médicos
- Verificação de especificidade e medical necessity
- Detecção de incompatibilidades (idade, gênero, lateralidade)

### Aggregates e Entidades

```yaml
aggregate: CodeValidation
  root_entity: CodeValidationResult
    properties:
      - validationId: UUID
      - claimId: UUID
      - validatedAt: Instant
      - overallStatus: ValidationStatus (PASSED/FAILED/WARNING)
      - violationCount: Integer
      - criticalViolationCount: Integer

  value_objects:
    - CodeViolation:
        - violationType: ViolationType
        - severity: Severity (CRITICAL/HIGH/MEDIUM/LOW)
        - affectedCode: String
        - description: String
        - suggestedFix: String?

    - ValidationContext:
        - patientAge: Integer
        - patientGender: Gender
        - serviceDate: LocalDate
        - insurancePlan: String

  entities:
    - ValidatedCode:
        - codeId: UUID
        - codeType: CodeType (ICD10/CPT/TUSS)
        - codeValue: String
        - isValid: Boolean
        - violations: List<CodeViolation>
```

### Domain Events

```json
{
  "domain_events": [
    {
      "event": "CodeValidationCompleted",
      "triggers": ["Validação finalizada para um claim"],
      "payload": {
        "validationId": "uuid",
        "claimId": "uuid",
        "overallStatus": "enum",
        "violationCount": "integer",
        "criticalViolations": "array"
      },
      "subscribers": [
        "AutoCorrectDelegate",
        "BillingService",
        "AuditService"
      ]
    },
    {
      "event": "CriticalViolationDetected",
      "triggers": ["Violação crítica encontrada"],
      "payload": {
        "validationId": "uuid",
        "violationType": "enum",
        "affectedCode": "string",
        "severity": "CRITICAL"
      },
      "subscribers": [
        "CodingTeamNotification",
        "ClaimHoldService"
      ]
    },
    {
      "event": "SpecificityWarningRaised",
      "triggers": ["> 50% códigos não-específicos"],
      "payload": {
        "claimId": "uuid",
        "unspecifiedPercentage": "float",
        "affectedCodes": "array"
      },
      "subscribers": [
        "QualityDashboard",
        "CodingEducationService"
      ]
    }
  ]
}
```

### Invariantes do Domínio
1. **Format Validity:** Todos os códigos devem ter formato válido (regex)
2. **Table Existence:** Código deve existir em tabela de referência ativa
3. **Medical Necessity:** Procedimentos requerem diagnóstico compatível (LCD/NCD)
4. **Specificity Threshold:** > 50% códigos .9 = Warning obrigatório

### Viabilidade para Microserviço
**Candidato:** ✅ SIM

**Justificativa:**
- Responsabilidade clara: validação de códigos médicos
- Pode escalar independentemente (alto volume de validações)
- Estado isolado (tabelas de referência locais)
- Comunicação via eventos (CodeValidationCompleted)

**Integração:**
```yaml
microservice: code-validation-service
  api:
    - POST /validations/validate-claim
    - GET /validations/{id}/results
    - GET /reference-tables/version

  events_published:
    - CodeValidationCompleted
    - CriticalViolationDetected
    - SpecificityWarningRaised

  events_subscribed:
    - ClaimSubmitted (from ClaimService)
    - ReferenceTableUpdated (from ConfigService)

  data_sources:
    - icd10_cm_codes (local cache)
    - tuss_procedures (local cache)
    - lcd_ncd_rules (replicated)
```

---

## XIII. Metadados Técnicos

### Complexidade e Esforço

```yaml
complexity_metrics:
  cyclomatic_complexity: 18  # Alto
  cognitive_complexity: 25   # Alto (múltiplas validações)
  lines_of_code: ~600

  time_estimates:
    implementation: 4 dias
    testing: 3 dias
    dmn_migration: 3 dias
    reference_tables_setup: 2 dias
    documentation: 1 dia
    total: 13 dias (~2.5 sprints)
```

### Cobertura de Testes

```yaml
test_coverage_targets:
  unit_tests: 90%
  integration_tests: 80%

  critical_test_scenarios:
    - icd10_format_validation
    - cpt_format_validation
    - tuss_existence_check
    - unspecified_code_detection
    - medical_necessity_crosswalk
    - age_gender_restrictions
    - laterality_7th_character
    - placeholder_x_usage
    - multiple_violations_aggregate
    - dmn_decision_integration
```

### Performance e SLA

```yaml
performance_requirements:
  single_code_validation: <50ms (p95)
  full_claim_validation: <500ms (p95)
  batch_validation_throughput: >200 claims/seg

  availability: 99.9%

  resource_limits:
    cpu: 2 cores
    memory: 4 GB
    reference_table_cache: 500 MB
```

### Dependências e Integrações

```yaml
dependencies:
  internal_services:
    - AutoCorrectDelegate (correções)
    - MedicalNecessityService (LCD/NCD)
    - CodingStandardsService (TUSS/CBHPM)

  external_services:
    - CMS ICD-10 API
    - ANS Web Service (TUSS)
    - AMA CPT API

  databases:
    - code_validations (PostgreSQL)
    - reference_tables_cache (Redis)
    - violation_history (TimescaleDB)

  dmn_engines:
    - camunda_decision_engine (validações)
```

### Monitoramento e Observabilidade

```yaml
metrics:
  business:
    - validation_pass_rate
    - violation_distribution_by_type
    - unspecified_code_percentage
    - medical_necessity_failure_rate

  technical:
    - validation_latency_p50_p95_p99
    - reference_table_cache_hit_rate
    - dmn_decision_evaluation_time
    - error_rate_by_code_type

  alerts:
    - validation_pass_rate < 80% (1h window)
    - critical_violations > 10% (1h window)
    - reference_table_cache_miss > 5%
    - validation_latency_p95 > 500ms
```

---

**Última Atualização:** 2025-01-12
**Versão do Documento:** 2.0
**Status de Conformidade:** ✅ Completo (X-XIII)
