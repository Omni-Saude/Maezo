# RN-SERVICE-001: Serviço de Codificação Médica (CodingService)

## I. Identificação

| Campo | Valor |
|-------|-------|
| **ID da Regra** | RN-SERVICE-001 |
| **Nome** | Serviço de Codificação Médica (CodingService) |
| **Tipo** | Serviço de Domínio - Camada de Aplicação |
| **Versão** | 1.0.0 |
| **Data de Criação** | 2026-01-12 |
| **Última Atualização** | 2026-01-12 |
| **Status** | Ativo |
| **Camada** | Service Layer |

## II. Descrição da Regra

### Objetivo
Prover funcionalidades completas de codificação médica incluindo:
- Atribuição e validação de códigos ICD-10/ICD-11
- Atribuição de códigos de procedimento CPT/TUSS
- Cálculo de DRG (Diagnosis Related Group)
- Auditoria de códigos e conformidade regulatória
- Sugestões de codificação assistidas por IA

### Contexto de Negócio
A codificação médica precisa é fundamental para:
- Garantir reembolso adequado por operadoras
- Evitar glosas por códigos incorretos ou incompatíveis
- Cumprir requisitos regulatórios da ANS e TISS
- Otimizar revenue cycle através de DRG correto

## III. Regras de Negócio Detalhadas

### 1. Atribuição de Códigos de Diagnóstico (assignDiagnosisCodes)

**Entradas:**
- `List<String> diagnoses`: Lista de descrições clínicas de diagnósticos
- `String encounterId`: Identificador do atendimento para contexto

**Processamento:**
1. Para cada diagnóstico clínico:
   - Chama API TASY para sugestão IA de código ICD-10
   - Valida formato do código (Pattern: `^[A-Z]\d{2}\.\d$`)
   - Se inválido, gera código fallback baseado em hash do diagnóstico
   - Armazena mapeamento diagnóstico -> ICD-10

**Saídas:**
- `Map<String, String>`: Mapa de diagnóstico para código ICD-10 atribuído

**Regras de Validação:**
- Código ICD-10 deve seguir formato letra + 2 dígitos + ponto + 1 dígito
- Se API TASY falhar, usa fallback local (circuit breaker)
- Logs de warning para códigos com formato inválido

### 2. Atribuição de Códigos de Procedimento (assignProcedureCodes)

**Entradas:**
- `List<String> procedures`: Lista de descrições de procedimentos realizados
- `String encounterId`: Identificador do atendimento

**Processamento:**
1. Para cada procedimento:
   - Chama API TASY para sugestão de código
   - Valida se é formato TUSS (`^\d\.\d{2}\.\d{2}\.\d{2}-\d$`) ou CPT (`^\d{5}$`)
   - Se inválido, gera código TUSS fallback
   - Armazena mapeamento procedimento -> código

**Saídas:**
- `Map<String, String>`: Mapa de procedimento para código TUSS/CPT

**Tabela de Códigos TUSS (Exemplos):**
| Código | Descrição |
|--------|-----------|
| 4.03.01.01-0 | Consulta em consultório |
| 4.07.01.02-1 | Radiografia de tórax |
| 4.11.01.03-2 | Exames laboratoriais básicos |

### 3. Auditoria de Códigos (auditCodes)

**Entradas:**
- `List<String> icdCodes`: Códigos ICD diagnósticos
- `List<String> procedureCodes`: Códigos de procedimentos
- `String payerId`: Identificador da operadora (regras específicas)

**Processamento:**

**3.1 Validação de Formato**
- ICD-10: Verifica pattern regex
- TUSS/CPT: Verifica pattern regex
- **Violação:** Severity HIGH se formato inválido

**3.2 Verificação de Necessidade Médica**
- Para cada código de procedimento:
  - Verifica se existe diagnóstico (ICD) que suporta o procedimento
  - Usa matriz de necessidade médica (produção: banco de dados)
- **Violação CRITICAL:** Procedimento sem diagnóstico de suporte

**3.3 Verificação de Regras da Operadora**
- Consulta regras específicas do `payerId`
- Valida compatibilidade com contrato
- Verifica procedimentos cobertos

**3.4 Detecção de Códigos Duplicados**
- Identifica códigos ICD repetidos
- **Warning:** Duplicatas detectadas

**3.5 Detecção de Códigos Não-Especificados**
- Códigos terminando em `.9` são não-especificados
- **Warning:** "Considere código mais específico"

**3.6 Cálculo de Pontuação de Risco**
```
Risk Score = (CRITICAL violations × 25) +
             (HIGH violations × 15) +
             (MEDIUM violations × 10) +
             (LOW violations × 5) +
             (warnings × 2)
Max: 100
```

**Saídas:**
- `CodingAuditResult`:
  - `auditPassed`: boolean
  - `violations`: Lista de violações com tipo, código, mensagem, severidade
  - `warnings`: Lista de avisos
  - `riskScore`: Pontuação 0-100
  - `totalCodesAudited`: Contagem total

### 4. Auto-Correção de Códigos (autoCorrectCodes)

**Entradas:**
- `List<Map<String, Object>> violations`: Violações da auditoria
- `boolean autoApprove`: Se deve aplicar correções automaticamente

**Tipos de Correções:**

| Tipo de Violação | Ação de Correção |
|------------------|------------------|
| FORMAT_ERROR | Converte para maiúsculas e remove espaços |
| SPECIFICITY_ERROR | Substitui `.9` por `.0` (mais específico) |
| INCOMPATIBLE_CODES | Usa ML para sugerir código compatível |
| MISSING_MODIFIER | Adiciona modificador requerido ao código |

**Saídas:**
- `Map<String, String>`: Mapa de código original -> código corrigido

### 5. Cálculo de DRG (calculateDRG)

**Entradas:**
- `List<String> diagnoses`: Diagnósticos clínicos
- `List<String> procedures`: Procedimentos realizados
- `List<String> comorbidities`: Comorbidades do paciente
- `int patientAge`: Idade do paciente

**Processamento:**

**5.1 Extração de Diagnóstico Principal**
- Primeiro diagnóstico da lista

**5.2 Mapeamento de DRG Base**
```java
DIAGNOSIS_TO_DRG = {
  "J18": "DRG-193",  // Pneumonia
  "I21": "DRG-280",  // Infarto Agudo do Miocárdio
  "I50": "DRG-291",  // Insuficiência Cardíaca
  "N18": "DRG-682",  // Doença Renal Crônica
  "E11": "DRG-637"   // Diabetes Tipo 2
}
```

**5.3 Aplicação de Modificadores MCC/CC**
- **MCC (Major Complication/Comorbidity):**
  - Insuficiência respiratória
  - Choque séptico
  - Adiciona sufixo `-MCC` ao DRG
- **CC (Complication/Comorbidity):**
  - Qualquer comorbidade
  - Adiciona sufixo `-CC` ao DRG

**5.4 Geração de DRGs Alternativos**
- Se DRG termina com `-MCC`: sugere `-CC` e sem sufixo
- Se DRG termina com `-CC`: sugere sem sufixo

**5.5 Cálculo de Confiança**
```
confidence = 0.7 (base)
+ 0.15 (se códigos são específicos, não terminam em .9)
+ 0.10 (se comorbidades documentadas)
Max: 1.0
```

**5.6 Estimativa de Reembolso**
```java
Reembolso estimado por DRG:
- DRG-193: R$ 5.500,00   (Pneumonia)
- DRG-280: R$ 12.000,00  (IAM)
- DRG-291: R$ 7.800,00   (IC)
- DRG-682: R$ 6.200,00   (DRC)
- default: R$ 4.500,00
```

**Saídas:**
- `DRGSuggestion`:
  - `suggestedDRG`: DRG calculado
  - `confidence`: 0.0-1.0
  - `alternativeDRGs`: Lista de alternativas
  - `estimatedReimbursement`: Valor estimado
  - `hasMCC`: boolean
  - `hasCC`: boolean

### 6. Validação de Combinações de Códigos (validateCodeCombinations)

**Validações:**

**6.1 Validação de Formato**
- ICD-10: Pattern `^[A-Z]\d{2}\.\d$`
- TUSS: Pattern `^\d\.\d{2}\.\d{2}\.\d{2}-\d$`
- CPT: Pattern `^\d{5}$`

**6.2 Necessidade Médica**
- Cada procedimento deve ter diagnóstico que o justifique

**6.3 Incompatibilidades Conhecidas**
```java
INCOMPATIBLE_CODE_PAIRS = {
  "J18.9": ["4.03.01.01-0"], // Pneumonia incompatível com checkup de rotina
  "I21.0": ["4.01.01.01-0"]  // IAM incompatível com procedimento menor
}
```

**Saídas:**
- `CodeValidationResult`:
  - `valid`: boolean
  - `errors`: Lista de mensagens de erro
  - `diagnosisCodesValidated`: Contagem
  - `procedureCodesValidated`: Contagem

## IV. Fluxo de Processamento

```
1. assignDiagnosisCodes()
   ↓
2. assignProcedureCodes()
   ↓
3. validateCodeCombinations()
   ↓
4. auditCodes()
   ↓
5. autoCorrectCodes() (se violações)
   ↓
6. calculateDRG()
```

## V. Integrações Externas

### TASY ERP (TASYCodingClient)
- `suggestICD10Code()`: Sugestão IA de código ICD-10
- `suggestProcedureCode()`: Sugestão IA de código TUSS/CPT
- API com circuit breaker e retry

### Resiliência
- **Circuit Breaker:** Abre após 5 falhas consecutivas
- **Retry:** 3 tentativas com backoff exponencial
- **Fallback:** Geração local de códigos baseada em hash

## VI. Tratamento de Erros

| Erro | Handling |
|------|----------|
| API TASY indisponível | Circuit breaker -> Fallback local |
| Formato de código inválido | Warning log + uso de fallback |
| Violação crítica de auditoria | Retorna auditPassed=false com detalhes |
| Códigos incompatíveis | Erro específico com códigos envolvidos |

## VII. Performance e Cache

- **Cache de Validação:** `@Cacheable(value = "code-validation")`
  - Key: `diagnosisCodes + procedureCodes`
  - Evita revalidações desnecessárias
- **Cache de DRG:** `@Cacheable(value = "drg-cache")`
  - Key: `diagnoses + procedures`
  - Reduz chamadas ao grouper

## VIII. Logging e Auditoria

**Níveis de Log:**
- **INFO:** Início/fim de operações principais
- **DEBUG:** Detalhes de atribuição de códigos
- **WARN:** Formatos inválidos, fallback usage
- **ERROR:** Falhas em integrações externas

**Métricas Rastreadas:**
- Quantidade de códigos atribuídos
- Taxa de violações de auditoria
- Risk score médio
- Taxa de uso de fallback

## IX. Testes e Qualidade

### Cenários de Teste Críticos
1. **Teste de Atribuição:** Verifica códigos ICD-10 corretos
2. **Teste de Auditoria:** Valida detecção de violações
3. **Teste de DRG:** Verifica cálculo correto com MCC/CC
4. **Teste de Fallback:** Simula falha TASY, verifica fallback
5. **Teste de Auto-Correção:** Valida correções aplicadas

### Cobertura de Testes
- Target: 90%+ cobertura de linhas
- Testes parametrizados para múltiplos cenários

## X. Conformidade Regulatória

### ANS (Agência Nacional de Saúde Suplementar)
- **RN 395/2016:** Códigos devem seguir TUSS
- **RN 438/2018:** Obrigatoriedade de padrão TISS para troca de informações
- **RN 465/2021:** Atualização de tabelas TUSS

### TISS (Troca de Informações de Saúde Suplementar)
- **Versão:** Componente Organizacional 3.05.00
- **Tabelas Utilizadas:**
  - Tabela 19: Tabela de Terminologia de Materiais Especiais (OPME)
  - Tabela 20: Tabela de Terminologia Unificada da Saúde Suplementar (TUSS)
  - Tabela 22: Tabela de Terminologia de Procedimentos

### LGPD (Lei Geral de Proteção de Dados)
- **Art. 11:** Dados de saúde são dados sensíveis
- **Requisito:** Logs de auditoria não devem conter dados pessoais identificáveis
- **Implementação:** PatientId é pseudonimizado nos logs

## XI. Notas de Migração

### Camunda 7 → Camunda 8
**Impacto:** MÉDIO
- Atualmente: Serviço chamado por JavaDelegate em Camunda 7
- Migração: Converter para Camunda 8 Job Worker
- **Ações:**
  1. Criar `CodingServiceWorker` implementando `JobHandler`
  2. Registrar worker no `ZeebeClient`
  3. Adaptar mapeamento de variáveis para formato Zeebe

### Microservices
**Recomendação:** Extrair para microserviço "Coding Service"
- **Vantagens:**
  - Escalabilidade independente (codificação é CPU-intensive)
  - Deploy independente de atualizações TUSS
  - Reutilização por múltiplos contextos (billing, denials, etc.)
- **Desafios:**
  - Latência de rede para chamadas síncronas
  - Necessidade de API gateway
- **Estratégia:** Começar com extrair lógica de DRG grouper

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Nome:** Medical Coding Context

### Aggregates
- **Coding Assignment Aggregate:**
  - Root: `CodingAssignment`
  - Entities: `DiagnosisCode`, `ProcedureCode`
  - Value Objects: `ICD10Code`, `TUSSCode`, `DRGCode`

- **Coding Audit Aggregate:**
  - Root: `CodingAudit`
  - Entities: `AuditViolation`, `AuditWarning`
  - Value Objects: `RiskScore`, `ViolationSeverity`

### Domain Events
- `DiagnosisCodesAssignedEvent`
- `ProcedureCodesAssignedEvent`
- `CodingAuditCompletedEvent`
- `CodesAutoCorrectedEvent`
- `DRGCalculatedEvent`

### Services (Domain)
- `CodingAssignmentService`: Atribuição de códigos
- `CodingAuditService`: Auditoria e validação
- `DRGCalculationService`: Cálculo de DRG

### Integration Points
- **Upstream:** TASY ERP (Fornecedor de contexto clínico)
- **Downstream:** Billing Context, Denials Context

## XIII. Metadados Técnicos

| Métrica | Valor |
|---------|-------|
| **Linhas de Código** | 610 |
| **Complexidade Ciclomática** | 42 (Alta - múltiplos branches) |
| **Cobertura de Testes** | 87% |
| **Dependências Externas** | TASYCodingClient |
| **Performance Esperada** | < 500ms para assignDiagnosisCodes |
| **Throughput** | 100 req/s (com cache) |
| **SLA** | 99.5% uptime |

### Padrões de Design Utilizados
- **Strategy Pattern:** Diferentes estratégias de correção de códigos
- **Circuit Breaker Pattern:** Resiliência em chamadas TASY
- **Repository Pattern:** Acesso a dados de códigos (implícito via TASY)
- **Fallback Pattern:** Geração local quando API externa falha

## XIV. Referências

### Documentação Técnica
- Padrão TISS v3.05.00 - ANS
- ICD-10 Brazilian Version - Ministério da Saúde
- MS-DRG Grouper Documentation - CMS (adaptado para contexto brasileiro)

### Código Fonte
- Arquivo: `src/main/java/com/hospital/revenuecycle/service/CodingService.java`
- Client: `src/main/java/com/hospital/revenuecycle/integration/tasy/TASYCodingClient.java`
- DTOs: `src/main/java/com/hospital/revenuecycle/integration/tasy/dto/`

### Testes
- Unit: `src/test/java/com/hospital/revenuecycle/unit/services/CodingServiceTest.java`
- Integration: `src/test/java/com/hospital/revenuecycle/integration/CodingServiceIntegrationTest.java`

---

**Última Revisão:** 2026-01-12
**Revisado Por:** Hive Mind Analyst Agent
**Aprovação:** Pendente Arquiteto de Sistema