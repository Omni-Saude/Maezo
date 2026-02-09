# RN - RegistrarProcedimentoDelegate

**ID:** RN-CLINICAL-008
**Camada:** Delegates (Procedure Registration)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** HIGH
**BPMN Reference:** `${registrarProcedimentoDelegate}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável por registrar procedimentos clínicos realizados durante o atendimento no sistema TASY ERP. Valida códigos TUSS/CBHPM, vincula procedimentos ao atendimento e paciente, e determina requisitos de cobrança e autorização prévia.

### 1.2 Objetivo
- Validar códigos de procedimento (TUSS/CBHPM)
- Registrar procedimento no TASY ERP
- Vincular procedimento a atendimento e paciente
- Registrar médico executor e data/hora
- Capturar detalhes específicos do procedimento
- Validar requisitos de cobrança
- Verificar necessidade de autorização prévia

### 1.3 Contexto no Fluxo de Negócio
Este delegate é executado durante o atendimento clínico sempre que um procedimento é realizado. Os dados registrados são essenciais para codificação e faturamento posterior.

---

## 2. Regras de Negócio

### RN-CLINICAL-008.1: Validação de Código TUSS/CBHPM
**Descrição:** Valida formato e estrutura do código de procedimento

**Formato Aceito:**
- **TUSS:** 8 dígitos (ex: `30101018`)
- **CBHPM:** 8 dígitos (ex: `31001153`)

**Validação:**
```java
private static final String TUSS_CODE_PATTERN = "^\\d{8}$"; // 8 digits
private static final String CBHPM_CODE_PATTERN = "^\\d{8}$"; // 8 digits

String cleanCode = procedureCode.replaceAll("[^0-9]", "");

if (!cleanCode.matches(TUSS_CODE_PATTERN) && !cleanCode.matches(CBHPM_CODE_PATTERN)) {
    throw new BpmnError("INVALID_PROCEDURE_CODE",
        "Procedure code must be 8 digits (TUSS/CBHPM): " + procedureCode);
}
```

**Tratamento de Formatação:**
- Remove caracteres não-numéricos (pontos, hífens)
- Aceita: `30101018`, `3010-10-18`, `30.10.10.18`
- Valida apenas dígitos limpos

---

### RN-CLINICAL-008.2: Campos Obrigatórios
**Descrição:** Valida presença de todos campos obrigatórios

**Campos Requeridos:**
- `encounter_id`: ID do atendimento
- `procedure_code`: Código TUSS/CBHPM
- `procedure_description`: Descrição do procedimento
- `performing_physician_id`: ID do médico executor

**Validação:**
```java
String encounterId = getRequiredVariable(execution, "encounter_id", String.class);
String procedureCode = getRequiredVariable(execution, "procedure_code", String.class);
String procedureDescription = getRequiredVariable(execution, "procedure_description", String.class);
String performingPhysicianId = getRequiredVariable(execution, "performing_physician_id", String.class);
```

---

### RN-CLINICAL-008.3: Campos Opcionais com Defaults
**Descrição:** Atribui valores padrão para campos opcionais

**Campos Opcionais:**
- `procedure_date`: Data de realização (default: `LocalDateTime.now()`)
- `laterality`: Lateralidade (LEFT, RIGHT, BILATERAL) - default: `null`
- `quantity`: Quantidade realizada (default: `1`)
- `procedure_notes`: Notas clínicas (default: `null`)

**Aplicação de Defaults:**
```java
LocalDateTime procedureDate = getVariable(execution, "procedure_date", LocalDateTime.class);
if (procedureDate == null) {
    procedureDate = LocalDateTime.now();
}

Integer quantity = getVariable(execution, "quantity", Integer.class, 1);
```

---

### RN-CLINICAL-008.4: Registro no TASY ERP
**Descrição:** Cria registro de procedimento no sistema TASY

**⚠️ Implementação Atual - Stub Mode:**
```java
private String registerProcedureInTASY(Map<String, Object> procedureData) {
    // ⚠️ TASY Integration Stub - Replace with real API after HUMANA-003
    // FAIL-OPEN STRATEGY: Generate simulated ID to allow process to continue
    String procedureId = "PROC-" + System.currentTimeMillis();

    log.warn("⚠️ TASY stub active - procedure registration simulated: {}", procedureId);

    return procedureId; // Fail-open: allows process to continue
}
```

**Implementação de Produção (Planejada):**
```java
// Production implementation (awaiting TASY API endpoint):
try {
    TasyProcedureRequest request = new TasyProcedureRequest(procedureData);
    TasyProcedureResponse response = tasyClient.registerProcedure(request, tasyApiKey);
    return response.getProcedureId();
} catch (TasyApiException e) {
    log.error("TASY API error - falling back to local ID generation", e);
    return "PROC-LOCAL-" + UUID.randomUUID().toString();
}
```

**Estratégia Fail-Open:** Permite processo continuar mesmo sem integração TASY ativa

---

### RN-CLINICAL-008.5: Determinação de Cobrabilidade
**Descrição:** Determina se o procedimento é cobrável ao convênio

**⚠️ Implementação Atual - Stub Mode:**
```java
private boolean determineBillability(String procedureCode) {
    // ⚠️ TASY Integration Stub - Replace with real billability check after HUMANA-003
    // FAIL-OPEN STRATEGY: Assume billable (true) to allow process to continue
    log.warn("⚠️ TASY stub active - assuming procedure {} is billable", procedureCode);

    return true; // Fail-open: allows billing process to continue
}
```

**Implementação de Produção (Planejada):**
```java
// Production implementation (awaiting TASY billability endpoint):
try {
    BillabilityResponse response = tasyClient.checkBillability(procedureCode, patientInsurance);
    return response.isBillable();
} catch (TasyApiException e) {
    log.error("TASY billability check failed - defaulting to billable", e);
    return true; // Fail-open: assume billable
}
```

**Critérios de Cobrabilidade:**
- Procedimento coberto pelo convênio do paciente
- Não excede limite de autorizações
- Não é procedimento administrativo/interno

---

### RN-CLINICAL-008.6: Verificação de Autorização Prévia
**Descrição:** Verifica se procedimento requer autorização prévia do convênio

**⚠️ Implementação Atual - Stub Mode:**
```java
private boolean checkAuthorizationRequirement(String procedureCode) {
    // ⚠️ TASY Integration Stub - Replace with real auth check after HUMANA-003
    // FAIL-OPEN STRATEGY: Assume NO authorization required (false) to avoid blocking
    log.warn("⚠️ TASY stub active - assuming procedure {} needs NO prior auth", procedureCode);

    return false;
}
```

**Implementação de Produção (Planejada):**
```java
// Production implementation (awaiting payer contract integration):
try {
    AuthorizationRequirement authReq = tasyClient.checkAuthRequirement(procedureCode, payerId);
    return authReq.isRequired();
} catch (TasyApiException e) {
    log.error("TASY authorization check failed - assuming no auth required", e);
    return false; // Fail-open: assume no auth required
}
```

**Procedimentos que Tipicamente Requerem Autorização:**
- Cirurgias eletivas
- Procedimentos de alta complexidade
- Tratamentos prolongados (quimioterapia, radioterapia)
- Próteses e órteses (OPME)

---

### RN-CLINICAL-008.7: Atualização de Lista de Procedimentos do Atendimento
**Descrição:** Adiciona procedimento à lista de procedimentos do atendimento

**Ação:**
```java
List<String> encounterProcedures = (List<String>) execution.getVariable("encounter_procedures");
if (encounterProcedures != null) {
    encounterProcedures.add(procedureId);
    setVariable(execution, "encounter_procedures", encounterProcedures);
}
```

**Utilidade:** Rastreamento de todos procedimentos realizados durante o atendimento

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `encounter_id` | String | ID do atendimento | "ENC-12345" |
| `procedure_code` | String | Código TUSS/CBHPM | "30101018" |
| `procedure_description` | String | Descrição do procedimento | "Consulta médica" |
| `performing_physician_id` | String | ID do médico executor | "DR-456" |

### 3.2 Variáveis de Entrada (Opcionais)
| Variável | Tipo | Descrição | Padrão |
|----------|------|-----------|---------|
| `procedure_date` | LocalDateTime | Data de realização | `LocalDateTime.now()` |
| `laterality` | String | Lateralidade (LEFT/RIGHT/BILATERAL) | `null` |
| `quantity` | Integer | Quantidade | `1` |
| `procedure_notes` | String | Notas clínicas | `null` |

### 3.3 Variáveis de Saída (Status)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `procedure_registered` | Boolean | Procedimento registrado com sucesso | PROCESS |
| `procedure_id` | String | ID do procedimento gerado | PROCESS |

### 3.4 Variáveis de Saída (Dados)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `procedure_code` | String | Código TUSS/CBHPM | PROCESS |
| `procedure_description` | String | Descrição do procedimento | PROCESS |
| `procedure_date` | String | Data de realização | PROCESS |
| `procedure_quantity` | Integer | Quantidade | PROCESS |
| `procedure_laterality` | String | Lateralidade | PROCESS |

### 3.5 Variáveis de Saída (Cobrança)
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `procedure_billable` | Boolean | Procedimento é cobrável | PROCESS |
| `procedure_authorization_required` | Boolean | Requer autorização prévia | PROCESS |

### 3.6 Variáveis de Erro
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `procedure_registration_error` | String | Mensagem de erro |

---

## 4. Códigos TUSS e CBHPM

### 4.1 Exemplos de Códigos TUSS
| Código TUSS | Descrição | Tipo |
|-------------|-----------|------|
| `10101012` | Consulta médica em consultório (no horário normal ou preestabelecido) | Consulta |
| `20101007` | Eletrocardiograma convencional | Exame |
| `30101018` | Tomografia computadorizada de crânio | Exame |
| `40201028` | Anestesia geral | Anestesia |
| `31201016` | Colecistectomia videolaparoscópica | Cirurgia |

### 4.2 Formato de Código
**Estrutura TUSS:** 8 dígitos
- Dígitos 1-2: Grupo
- Dígitos 3-4: Subgrupo
- Dígitos 5-6: Tipo
- Dígitos 7-8: Sequencial

**Exemplo:** `30101018`
- `30`: Procedimentos cirúrgicos
- `10`: Cirurgias do aparelho digestivo
- `10`: Colecistectomia
- `18`: Variante (videolaparoscópica)

---

## 5. Tratamento de Erros

### 5.1 BpmnErrors
| Código | Descrição | Ação |
|--------|-----------|------|
| `INVALID_PROCEDURE_CODE` | Código de procedimento inválido | Retornar erro ao chamador |

### 5.2 Exceções Técnicas
```java
catch (Exception e) {
    log.error("Procedure registration failed - Process: {}, Error: {}",
        processInstanceId, e.getMessage(), e);

    setVariable(execution, "procedure_registered", false);
    setVariable(execution, "procedure_registration_error", e.getMessage());

    throw new RuntimeException("Failed to register procedure", e);
}
```

---

## 6. Conformidade e Auditoria

### 6.1 Regulamentações
- **ANS RN 338/2013:** Tabela TUSS
- **CFM:** Registro de procedimentos médicos
- **CBHPM:** Classificação Brasileira Hierarquizada de Procedimentos Médicos
- **LGPD:** Privacidade de dados de procedimentos

### 6.2 Logs de Auditoria
```
INFO: Executing RegistrarProcedimentoDelegate - Process: {id}, Activity: {activity}
INFO: Registering procedure - EncounterId: {id}, Code: {code}, Description: {desc}, Physician: {id}
INFO: Procedure registered in TASY - ProcedureId: {id}, EncounterId: {id}, Code: {code}
WARN: ⚠️ TASY stub active - procedure registration simulated: {id}
INFO: Procedure registration completed - ProcedureId: {id}, Billable: {status}, AuthorizationRequired: {status}
```

---

## 7. Dependências

### 7.1 Clientes
- `TasyClient`: Integração com TASY ERP (quando disponível)

### 7.2 Configuração
- `tasy.api-key`: Chave de API do TASY

### 7.3 Delegates Relacionados
- (Downstream) Delegates de codificação que usam procedimentos
- (Downstream) Delegates de faturamento para cobrança

---

## 8. Requisitos Não-Funcionais

### 8.1 Performance
- Tempo médio de execução: < 2 segundos
- Timeout: 15 segundos

### 8.2 Idempotência
- **requiresIdempotency()**: `true`
- Previne registros duplicados de procedimentos

### 8.3 Disponibilidade
- Estratégia: **Fail-Open**
- Processo continua mesmo sem TASY disponível
- IDs locais gerados para manter rastreabilidade

---

## 9. Cenários de Teste

### 9.1 Cenário: Registro de Consulta Médica
**Dado:**
- `encounter_id="ENC-12345"`
- `procedure_code="10101012"` (Consulta médica)
- `procedure_description="Consulta médica em consultório"`
- `performing_physician_id="DR-456"`

**Quando:** RegistrarProcedimentoDelegate executado
**Então:**
- `procedure_registered = true`
- `procedure_id` gerado (formato "PROC-XXXXXXXXX")
- `procedure_billable = true`
- `procedure_authorization_required = false`

---

### 9.2 Cenário: Registro de Cirurgia com Lateralidade
**Dado:**
- `procedure_code="31201016"` (Colecistectomia)
- `laterality="RIGHT"`
- `quantity=1`

**Quando:** RegistrarProcedimentoDelegate executado
**Então:**
- Procedimento registrado
- `procedure_laterality = "RIGHT"`
- `procedure_quantity = 1`

---

### 9.3 Cenário: Código de Procedimento Inválido
**Dado:**
- `procedure_code="123"` (apenas 3 dígitos)

**Quando:** RegistrarProcedimentoDelegate executado
**Então:**
- BpmnError `INVALID_PROCEDURE_CODE`
- Mensagem: "Procedure code must be 8 digits (TUSS/CBHPM): 123"

---

### 9.4 Cenário: Múltiplos Procedimentos no Mesmo Atendimento
**Dado:**
- `encounter_procedures` já contém ["PROC-001", "PROC-002"]
- Novo procedimento registrado: "PROC-003"

**Quando:** RegistrarProcedimentoDelegate executado
**Então:**
- `encounter_procedures = ["PROC-001", "PROC-002", "PROC-003"]`

---

## 10. Lateralidade de Procedimentos

| Código | Descrição | Quando Usar |
|--------|-----------|-------------|
| `LEFT` | Esquerdo | Procedimentos unilaterais à esquerda |
| `RIGHT` | Direito | Procedimentos unilaterais à direita |
| `BILATERAL` | Bilateral | Procedimentos realizados em ambos os lados |
| `null` | Não aplicável | Procedimentos sem lateralidade |

**Exemplos:**
- Cirurgia de joelho direito: `RIGHT`
- Cirurgia de catarata bilateral: `BILATERAL`
- Apendicectomia: `null` (não tem lateralidade)

---

## 11. Estratégia Fail-Open

### 11.1 Justificativa
O sistema utiliza estratégia **Fail-Open** para garantir continuidade do atendimento clínico mesmo com falhas de integração:

- ✅ **Atendimento continua:** Procedimento registrado localmente
- ✅ **Rastreabilidade mantida:** IDs locais gerados
- ✅ **Sincronização posterior:** Reconciliação quando TASY disponível
- ⚠️ **Logs de alerta:** Stub mode claramente identificado nos logs

### 11.2 Comportamento
```
STUB MODE ATIVO:
  → Gera ID local: "PROC-{timestamp}"
  → Assume cobrável: true
  → Assume sem autorização: false
  → Processo continua normalmente

PRODUÇÃO:
  → Consulta TASY para ID real
  → Valida cobrabilidade no contrato
  → Verifica autorização no convênio
  → Sincroniza com ERP
```

---

## 12. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/RegistrarProcedimentoDelegate.java`

**Clientes:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/RegistrarProcedimentoDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
