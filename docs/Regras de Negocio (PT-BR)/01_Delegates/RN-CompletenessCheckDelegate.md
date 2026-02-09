# RN - CompletenessCheckDelegate

**ID:** RN-CLINICAL-003
**Camada:** Delegates (Documentation Validation)
**Subprocess:** SUB_03_Atendimento_Clinico
**Prioridade:** HIGH
**BPMN Reference:** `${completenessCheckDelegate}`

---

## 1. Visão Geral

### 1.1 Descrição
Delegate responsável por verificar a completude da documentação clínica antes do fechamento do atendimento. Valida que todos os documentos obrigatórios estão presentes, incluindo integração com LIS (Laboratory Information System) e PACS (Picture Archiving and Communication System).

### 1.2 Objetivo
- Verificar presença de documentos clínicos obrigatórios
- Validar completude de resultados laboratoriais (LIS)
- Confirmar finalização de laudos de imagem (PACS)
- Calcular score de completude (0-100%)
- Listar documentos faltantes

### 1.3 Contexto no Fluxo de Negócio
Este delegate é executado antes de finalizar o atendimento clínico, garantindo que toda documentação necessária para cobrança e auditoria está completa. Impede fechamento prematuro de atendimentos com documentação incompleta.

---

## 2. Regras de Negócio

### RN-CLINICAL-003.1: Documentos Obrigatórios por Tipo de Atendimento
**Descrição:** Define quais documentos são obrigatórios baseado no tipo de atendimento

**Documentos Sempre Obrigatórios:**
- Nota de evolução (`PROGRESS_NOTE`) - mínimo 1
- Sumário de alta (`DISCHARGE_SUMMARY`)

**Documentos Obrigatórios para INPATIENT:**
- Nota de admissão (`ADMISSION_NOTE`)

**Documentos Condicionais:**
- Nota operatória (`OPERATIVE_NOTE`) - se `is_surgical = true`
- Nota de consulta (`CONSULTATION_NOTE`) - se `has_consultations = true`

**Regra de Validação:**
```java
if ("INPATIENT".equalsIgnoreCase(encounterType)) {
    if (!hasDocumentType(documents, DOC_TYPE_ADMISSION)) {
        missingDocuments.add("Admission Note");
    }
}
```

---

### RN-CLINICAL-003.2: Validação de Resultados Laboratoriais (LIS)
**Descrição:** Verifica se todos os exames laboratoriais possuem resultados finais

**Condição de Verificação:**
```java
boolean hasLabOrders = getVariable(execution, "has_lab_orders", Boolean.class, false);
if (hasLabOrders) {
    boolean labResultsComplete = lisService.areResultsComplete(encounterId);
}
```

**Critério de Completude:**
- Todos os pedidos de exame devem ter resultados finais
- Integração com LIS via `LISService`

**Ação se Incompleto:**
- Adiciona "Complete Lab Results" à lista de documentos faltantes
- Reduz score de completude

---

### RN-CLINICAL-003.3: Validação de Laudos de Imagem (PACS)
**Descrição:** Verifica se todos os estudos de imagem possuem laudos finais

**Condição de Verificação:**
```java
boolean hasImagingOrders = getVariable(execution, "has_imaging_orders", Boolean.class, false);
if (hasImagingOrders) {
    boolean imagingComplete = pacsService.isImagingComplete(encounterId);
}
```

**Critério de Completude:**
- Todos os estudos devem ter status `available`
- Todos os laudos devem ter status `final`
- Integração com PACS via `PACSService`

**Ação se Incompleto:**
- Adiciona "Complete Imaging Reports" à lista de documentos faltantes
- Reduz score de completude

---

### RN-CLINICAL-003.4: Cálculo de Score de Completude
**Descrição:** Calcula percentual de completude da documentação

**Fórmula:**
```java
int completed = totalRequired - missingDocuments.size();
int completenessScore = (totalRequired > 0) ? (completed * 100 / totalRequired) : 100;
```

**Interpretação:**
- 100%: Documentação completa
- 80-99%: Documentação quase completa
- < 80%: Documentação significativamente incompleta

**Total de Documentos Requeridos:**
- Base: 2 (progress note + discharge summary)
- +1 se INPATIENT (admission note)
- +1 se `hasLabOrders` (lab results)
- +1 se `hasImagingOrders` (imaging reports)
- +1 se `isSurgical` (operative note)
- +1 se `hasConsultations` (consultation note)

---

### RN-CLINICAL-003.5: Lista de Documentos Faltantes
**Descrição:** Identifica especificamente quais documentos estão faltando

**Documentos Rastreados:**
- "Admission Note"
- "Progress Note"
- "Discharge Summary"
- "Complete Lab Results"
- "Complete Imaging Reports"
- "Operative Note"
- "Consultation Note"

**Utilidade:** Permite comunicação clara ao médico sobre o que falta documentar

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada (Obrigatórias)
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| `encounter_id` | String | ID do atendimento | "ENC-12345" |

### 3.2 Variáveis de Entrada (Opcionais)
| Variável | Tipo | Descrição | Padrão |
|----------|------|-----------|---------|
| `encounter_type` | String | Tipo de atendimento | "OUTPATIENT" |
| `has_lab_orders` | Boolean | Possui pedidos de exame | false |
| `has_imaging_orders` | Boolean | Possui pedidos de imagem | false |
| `is_surgical` | Boolean | Caso cirúrgico | false |
| `has_consultations` | Boolean | Possui interconsultas | false |

### 3.3 Variáveis de Saída
| Variável | Tipo | Descrição | Escopo |
|----------|------|-----------|--------|
| `documentation_complete` | Boolean | Documentação 100% completa | PROCESS |
| `missing_documents` | List<String> | Lista de documentos faltantes | PROCESS |
| `completeness_score` | Integer | Score de completude (0-100) | PROCESS |
| `total_required_documents` | Integer | Total de documentos requeridos | PROCESS |
| `completed_documents` | Integer | Documentos presentes | PROCESS |

### 3.4 Variáveis de Erro
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `completeness_check_error` | String | Mensagem de erro |

---

## 4. Integrações

### 4.1 TasyClient
**Método:** `getEncounterDocuments(encounterId, apiKey)`
**Finalidade:** Recuperar lista de documentos do atendimento

**Retorno:** `List<TasyDocumentDTO>` com:
- `documentType`: Tipo do documento
- `documentDate`: Data de criação
- `status`: Status do documento

---

### 4.2 LISService (Laboratory Information System)
**Método:** `areResultsComplete(encounterId)`
**Finalidade:** Verificar se todos exames laboratoriais têm resultados finais

**Critério:** Todos pedidos devem ter status `final`, `amended`, ou `corrected`

---

### 4.3 PACSService (Picture Archiving System)
**Método:** `isImagingComplete(encounterId)`
**Finalidade:** Verificar se todos estudos de imagem têm laudos finais

**Critério:**
- Status do estudo: `available`
- Status do laudo: `final`

---

## 5. Tratamento de Erros

### 5.1 Exceções Técnicas
- Log completo de erro
- Define `documentation_complete = false`
- Define `completeness_check_error` com mensagem
- Re-lança `RuntimeException`

**Exemplo:**
```
ERROR: Documentation completeness check failed - Process: {id}, Error: {message}
```

---

## 6. Conformidade e Auditoria

### 6.1 Regulamentações
- **CFM:** Resolução sobre completude do prontuário eletrônico
- **ANS:** Documentação obrigatória para auditoria de contas
- **ISO 9001:** Gestão de qualidade em documentação clínica

### 6.2 Logs de Auditoria
```
INFO: Checking documentation completeness - EncounterId: {id}, Type: {type}
INFO: Retrieved {count} documents for encounter: {id}
INFO: Lab results completeness - EncounterId: {id}, Complete: {status}
INFO: Imaging completeness - EncounterId: {id}, Complete: {status}
INFO: Documentation completeness check completed - EncounterId: {id}, Complete: {status}, Score: {score}%, Missing: {list}
```

---

## 7. Dependências

### 7.1 Serviços
- `TasyClient`: Acesso a documentos do TASY
- `LISService`: Integração com sistema laboratorial
- `PACSService`: Integração com sistema de imagens

### 7.2 DTOs
- `TasyDocumentDTO`: Representa documento clínico do TASY

### 7.3 Delegates Relacionados
- `CloseEncounterDelegate`: Usa resultado da validação para permitir fechamento
- `FinalizarAtendimentoDelegate`: Validação prévia ao encerramento

---

## 8. Requisitos Não-Funcionais

### 8.1 Performance
- Tempo médio de execução: < 2 segundos
- Timeout: 15 segundos

### 8.2 Idempotência
- **requiresIdempotency()**: `false`
- Operação de leitura, naturalmente idempotente

### 8.3 Disponibilidade
- Dependências: TASY, LIS, PACS (uptime > 99%)

---

## 9. Cenários de Teste

### 9.1 Cenário: Documentação Completa - OUTPATIENT
**Dado:**
- `encounter_type="OUTPATIENT"`
- Progress Note presente
- Discharge Summary presente
- Sem pedidos de exame/imagem

**Quando:** CompletenessCheckDelegate executado
**Então:**
- `documentation_complete = true`
- `completeness_score = 100`
- `missing_documents = []`

---

### 9.2 Cenário: Documentação Incompleta - INPATIENT
**Dado:**
- `encounter_type="INPATIENT"`
- Falta Admission Note
- Discharge Summary presente

**Quando:** CompletenessCheckDelegate executado
**Então:**
- `documentation_complete = false`
- `completeness_score = 66` (2 de 3 documentos)
- `missing_documents = ["Admission Note"]`

---

### 9.3 Cenário: Exames Laboratoriais Pendentes
**Dado:**
- `has_lab_orders = true`
- `lisService.areResultsComplete(id)` retorna false

**Quando:** CompletenessCheckDelegate executado
**Então:**
- `documentation_complete = false`
- `missing_documents` contém "Complete Lab Results"
- Score reduzido proporcionalmente

---

### 9.4 Cenário: Caso Cirúrgico sem Nota Operatória
**Dado:**
- `is_surgical = true`
- Falta Operative Note

**Quando:** CompletenessCheckDelegate executado
**Então:**
- `documentation_complete = false`
- `missing_documents` contém "Operative Note"

---

## 10. Matriz de Documentos Obrigatórios

| Tipo de Atendimento | Admission Note | Progress Note | Discharge Summary | Operative Note | Consultation Note | Lab Results | Imaging Reports |
|---------------------|----------------|---------------|-------------------|----------------|-------------------|-------------|-----------------|
| OUTPATIENT          | ❌             | ✅            | ✅                | Condicional    | Condicional       | Condicional | Condicional     |
| INPATIENT           | ✅             | ✅            | ✅                | Condicional    | Condicional       | Condicional | Condicional     |
| EMERGENCY           | ❌             | ✅            | ✅                | Condicional    | Condicional       | Condicional | Condicional     |
| AMBULATORY          | ❌             | ✅            | ✅                | ❌             | Condicional       | Condicional | Condicional     |

**Legenda:**
- ✅ = Sempre obrigatório
- ❌ = Não obrigatório
- Condicional = Depende de flags (`is_surgical`, `has_consultations`, `has_lab_orders`, etc.)

---

## 11. Arquivos Relacionados

**Implementação:**
- `/src/main/java/com/hospital/revenuecycle/delegates/clinical/CompletenessCheckDelegate.java`

**Serviços:**
- `/src/main/java/com/hospital/revenuecycle/service/LISService.java`
- `/src/main/java/com/hospital/revenuecycle/service/PACSService.java`

**Clientes:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`

**DTOs:**
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/dto/TasyDocumentDTO.java`

**Testes:**
- `/src/test/java/com/hospital/revenuecycle/unit/delegates/clinical/CompletenessCheckDelegateTest.java`

---

**Última Atualização:** 2026-01-12
**Versão:** 1.0
**Autor:** Revenue Cycle Development Team
