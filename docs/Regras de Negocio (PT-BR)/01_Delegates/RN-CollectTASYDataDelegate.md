# RN - CollectTASYDataDelegate

**ID:** RN-CLINICAL-002
**Camada:** Delegates (Clinical Data Collection)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** HIGH
**BPMN Reference:** `${collectTASYData}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável por coletar dados clínicos abrangentes do sistema TASY EHR (Electronic Health Record). Recupera informações de procedimentos, diagnósticos, medicamentos, resultados de laboratório e detalhes do atendimento.

### 1.2 Objetivo
- Extrair dados clínicos completos do TASY
- Consolidar informações para processos de codificação e cobrança
- Suportar múltiplos escopos de coleta de dados (FULL, BASIC, BILLING_ONLY)
- Integrar com APIs TASY, HL7 e FHIR

### 1.3 Contexto no Fluxo de Negócio
Este delegate é executado no início do processo de atendimento clínico, coletando todos os dados necessários do prontuário eletrônico TASY. Os dados coletados alimentam processos downstream de codificação e faturamento.

---

## 2. Regras de Negócio

### RN-CLINICAL-002.1: Escopo de Coleta de Dados
**Descrição:** Define quais dados serão coletados com base no escopo especificado

**Escopos Disponíveis:**
- `FULL`: Coleta completa (procedimentos, diagnósticos, medicamentos, exames)
- `BASIC`: Apenas procedimentos e diagnósticos
- `BILLING_ONLY`: Dados mínimos para faturamento

**Regra:**
```java
String dataScope = getVariableOrDefault(execution, "dataScope", String.class, "FULL");

if ("FULL".equals(dataScope)) {
    medications = collectMedications(encounterId);
    labResults = collectLabResults(encounterId);
}
```

---

### RN-CLINICAL-002.2: Validação de Parâmetros
**Descrição:** Valida IDs de paciente e atendimento antes da coleta

**Condições Obrigatórias:**
- `patientId` não pode ser nulo ou vazio
- `encounterId` não pode ser nulo ou vazio
- `dataScope` deve ser um dos valores válidos: FULL, BASIC, BILLING_ONLY

**Ação se Inválido:**
```java
throw new BpmnError("INVALID_PATIENT_ID", "Patient ID cannot be empty");
throw new BpmnError("INVALID_ENCOUNTER_ID", "Encounter ID cannot be empty");
```

---

### RN-CLINICAL-002.3: Coleta de Dados Clínicos
**Descrição:** Extrai dados demográficos e clínicos do atendimento

**Dados Coletados:**
- ID do paciente e atendimento
- Tipo de atendimento (INPATIENT, OUTPATIENT, EMERGENCY)
- Data de admissão
- Nome do paciente, data de nascimento, sexo
- Queixa principal (chief complaint)
- Médico assistente
- Departamento/especialidade
- Número do leito

**Fonte:** TASY REST API via `TasyWebClient.getMedicalRecord(encounterId)`

---

### RN-CLINICAL-002.4: Coleta de Procedimentos
**Descrição:** Recupera todos procedimentos realizados durante o atendimento

**Dados de Procedimento:**
- ID do procedimento
- Código TUSS (8 dígitos)
- Nome do procedimento
- Data de realização
- Quantidade
- Médico executor

**Exemplo de Código TUSS:**
- `00.66.01.006-2`: Angiografia coronária
- `20.101.01-3`: Eletrocardiograma

**Fonte:** TASY Procedures API via `TasyClient.getProcedures(appointmentId, apiKey)`

---

### RN-CLINICAL-002.5: Coleta de Diagnósticos
**Descrição:** Recupera diagnósticos do atendimento codificados em CID-10

**Dados de Diagnóstico:**
- ID do diagnóstico
- Código CID-10
- Descrição do diagnóstico
- Tipo (PRIMARY, SECONDARY)
- Data do diagnóstico

**Exemplo de Códigos CID-10:**
- `I20.0`: Angina instável
- `E11.9`: Diabetes mellitus tipo 2 sem complicações

---

### RN-CLINICAL-002.6: Coleta de Medicamentos (Escopo FULL)
**Descrição:** Recupera medicamentos administrados durante o atendimento

**Dados de Medicamento:**
- ID do medicamento
- Nome do medicamento
- Dosagem
- Via de administração (ORAL, IV, IM)
- Frequência (DAILY, BID, TID)

**Condição:** Apenas coletado se `dataScope = "FULL"`

---

### RN-CLINICAL-002.7: Coleta de Resultados Laboratoriais (Escopo FULL)
**Descrição:** Recupera resultados de exames laboratoriais

**Dados de Exame:**
- ID do teste
- Nome do teste
- Resultado
- Unidade
- Faixa de referência
- Status (NORMAL, ABNORMAL)

**Fonte:** TASY Lab Results API via `TasyWebClient.getLabResults(encounterId)`

**Condição:** Apenas coletado se `dataScope = "FULL"`

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `patientId` | String | ID do paciente no TASY | "PAT-12345" |
| `encounterId` | String | ID do atendimento | "ENC-67890" |

### 3.2 Variáveis de Entrada (Opcionais)
| Variável | Tipo | Descrição | Padrão |
|----------|------|-----------|---------|
| `dataScope` | String | Escopo da coleta (FULL/BASIC/BILLING_ONLY) | "FULL" |

### 3.3 Variáveis de Saída
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `clinicalData` | Map | Dados clínicos completos | PROCESS |
| `procedures` | List<Map> | Lista de procedimentos | PROCESS |
| `diagnoses` | List<Map> | Lista de diagnósticos | PROCESS |
| `medications` | List<Map> | Lista de medicamentos (FULL) | PROCESS |
| `labResults` | List<Map> | Resultados de exames (FULL) | PROCESS |
| `dataCollectionTimestamp` | LocalDateTime | Timestamp da coleta | PROCESS |
| `dataSource` | String | "TASY_EHR" | PROCESS |

**Importância das Variáveis PROCESS:**
Estas variáveis são utilizadas pelos processos de codificação (`SUB_05_Codificacao_Clinica`) e faturamento (`SUB_04_Faturamento`) para geração de cobrança.

---

## 4. Integrações

### 4.1 TASY REST API
**Endpoint:** `TasyWebClient.getMedicalRecord(encounterId)`
**Finalidade:** Recuperar dados do prontuário eletrônico

### 4.2 TASY Procedures API
**Endpoint:** `TasyClient.getProcedures(appointmentId, apiKey)`
**Finalidade:** Listar procedimentos realizados

### 4.3 TASY Lab Results API
**Endpoint:** `TasyWebClient.getLabResults(encounterId)`
**Finalidade:** Obter resultados de exames laboratoriais

### 4.4 HL7 Interface
**Finalidade:** Dados em tempo real via mensagens HL7

### 4.5 FHIR Endpoints
**Finalidade:** Dados estruturados em formato FHIR R4

---

## 5. Tratamento de Erros

### 5.1 BpmnErrors
| Código | Descrição | Ação |
|--------|-----------|------|
| `INVALID_PATIENT_ID` | Patient ID vazio ou nulo | Retornar erro ao chamador |
| `INVALID_ENCOUNTER_ID` | Encounter ID vazio ou nulo | Retornar erro ao chamador |
| `TASY_DATA_COLLECTION_FAILED` | Falha na coleta de dados do TASY | Log de erro e retry |

### 5.2 Exceções Técnicas
- Log completo de erro com stack trace
- BpmnError lançado para tratamento no BPMN

---

## 6. Conformidade e Auditoria

### 6.1 Regulamentações
- **LGPD:** Coleta apenas de dados necessários, com consentimento
- **CFM:** Acesso seguro ao prontuário eletrônico
- **ANS:** Dados completos para justificativa de cobrança

### 6.2 Logs de Auditoria
```
INFO: Collecting TASY clinical data: patientId={id}, encounterId={id}, scope={scope}
INFO: TASY data collection completed: procedures={count}, diagnoses={count}
ERROR: Failed to collect TASY data: patientId={id}, encounterId={id}
```

---

## 7. Dependências

### 7.1 Clientes de Integração
- `TasyWebClient`: Cliente REST para TASY
- `TasyClient`: Cliente para APIs TASY específicas

### 7.2 Delegates Relacionados
- `RegisterEncounterDelegate`: Registra atendimento antes da coleta
- (Downstream) Delegates de codificação que consomem os dados

---

## 8. Requisitos Não-Funcionais

### 8.1 Performance
- Tempo médio de execução: < 3 segundos (BASIC/BILLING_ONLY)
- Tempo médio de execução: < 8 segundos (FULL)
- Timeout: 30 segundos

### 8.2 Idempotência
- **requiresIdempotency()**: `false`
- Operação de leitura, naturalmente idempotente

### 8.3 Disponibilidade
- Dependência crítica: TASY EHR (uptime > 99%)
- Cache de dados para reduzir carga no TASY

---

## 9. Cenários de Teste

### 9.1 Cenário: Coleta Completa (FULL)
**Dado:** `patientId="PAT-123"`, `encounterId="ENC-456"`, `dataScope="FULL"`
**Quando:** CollectTASYDataDelegate executado
**Então:**
- `clinicalData` populado
- `procedures` com 2+ procedimentos
- `diagnoses` com 2+ diagnósticos
- `medications` coletado
- `labResults` coletado
- `dataSource = "TASY_EHR"`

### 9.2 Cenário: Coleta Básica (BASIC)
**Dado:** `dataScope="BASIC"`
**Quando:** CollectTASYDataDelegate executado
**Então:**
- `procedures` coletado
- `diagnoses` coletado
- `medications` = null (não coletado)
- `labResults` = null (não coletado)

### 9.3 Cenário: Patient ID Inválido
**Dado:** `patientId=""` (vazio)
**Quando:** CollectTASYDataDelegate executado
**Então:**
- BpmnError `INVALID_PATIENT_ID`
- Processo interrompido

---

## 10. Mock Data (Desenvolvimento)

O delegate inclui dados simulados para desenvolvimento/testes quando APIs TASY não estão disponíveis:

**Procedimentos Mock:**
- PROC-001: Angiografia coronária (TUSS 00.66.01.006-2)
- PROC-002: Eletrocardiograma (TUSS 20.101.01-3)

**Diagnósticos Mock:**
- DIAG-001: Angina instável (CID-10 I20.0)
- DIAG-002: Diabetes tipo 2 (CID-10 E11.9)

**Medicamentos Mock:**
- MED-001: Aspirina 100mg ORAL DAILY

**Exames Mock:**
- LAB-001: Troponina = 0.05 ng/mL (ABNORMAL)

---

## 11. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/CollectTASYDataDelegate.java`

**Clientes:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyWebClient.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/CollectTASYDataDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
