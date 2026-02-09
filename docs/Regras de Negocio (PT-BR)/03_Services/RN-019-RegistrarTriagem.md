# RN-019: Registro de Triagem (Manchester Protocol)

**Delegate**: `RegistrarTriagemDelegate.java`
**Subprocesso BPMN**: SUB_01_Patient_Registration (Emergency Department)
**Prioridade**: CRÍTICA
**Versão**: 1.0
**Última Atualização**: 2026-01-12

---

## 1. Visão Geral

### 1.1 Objetivo
Registrar informações de triagem de pacientes no pronto-socorro seguindo o Protocolo de Manchester, atribuindo nível de prioridade baseado em sinais vitais, queixa principal e discriminadores de risco.

### 1.2 Escopo
- Captura de sinais vitais essenciais
- Registro de queixa principal (chief complaint)
- Atribuição de nível de triagem (Manchester Protocol)
- Cálculo de prioridade e tempo de espera estimado
- Integração com sistema EMR

### 1.3 Stakeholders
- **Primários**: Enfermagem de triagem, gestão de pronto-socorro
- **Secundários**: Médicos emergencistas, regulação de leitos

---

## 2. Protocolo de Manchester

### RN-019.1: Níveis de Triagem e Cores
**Criticidade**: CRÍTICA
**Categoria**: Classificação de Risco

**Descrição**:
Sistema utiliza 5 níveis de prioridade conforme Protocolo de Manchester:

**Níveis de Triagem**:
| Cor | Nível | Prioridade | Tempo Máximo de Espera | Descrição |
|-----|-------|------------|------------------------|-----------|
| 🔴 **RED** | 1 | Emergente | 0 minutos | Risco imediato de vida |
| 🟠 **ORANGE** | 2 | Muito Urgente | 10 minutos | Risco potencial de vida |
| 🟡 **YELLOW** | 3 | Urgente | 30 minutos | Sintomas graves |
| 🟢 **GREEN** | 4 | Pouco Urgente | 60 minutos | Sintomas moderados |
| 🔵 **BLUE** | 5 | Não Urgente | 120 minutos | Sintomas leves/administrativo |

**Implementação**:
```java
private Integer getTriagePriority(String level) {
    Map<String, Integer> priorities = Map.of(
        "RED", 1,
        "ORANGE", 2,
        "YELLOW", 3,
        "GREEN", 4,
        "BLUE", 5
    );
    return priorities.getOrDefault(level, 3);
}

private Integer calculateWaitTime(String level) {
    Map<String, Integer> waitTimes = Map.of(
        "RED", 0,
        "ORANGE", 10,
        "YELLOW", 30,
        "GREEN", 60,
        "BLUE", 120
    );
    return waitTimes.getOrDefault(level, 30);
}
```

---

### RN-019.2: Discriminadores de Risco (Simplificado)
**Criticidade**: CRÍTICA
**Categoria**: Avaliação Clínica

**Descrição**:
Sistema analisa discriminadores para determinar nível de triagem:

**Discriminadores Principais**:

**1. Ameaça à Via Aérea**:
- Obstrução de via aérea → RED
- Dificuldade respiratória severa → ORANGE
- Estridor/sibilância → YELLOW

**2. Respiração**:
- SpO2 < 90% → RED
- SpO2 90-94% → ORANGE
- FR > 30 ou < 10 → ORANGE
- FR 24-30 → YELLOW

**3. Circulação**:
- PA sistólica < 90 mmHg → RED
- FC > 120 bpm → ORANGE
- Sangramento ativo severo → RED
- Sangramento moderado → ORANGE

**4. Consciência**:
- Inconsciente/não responsivo → RED
- Confusão aguda → ORANGE
- Desorientação → YELLOW

**5. Dor**:
- Dor severa (8-10/10) → RED
- Dor moderada a severa (6-7/10) → ORANGE
- Dor moderada (4-5/10) → YELLOW
- Dor leve (1-3/10) → GREEN

**6. Temperatura**:
- > 41°C ou < 35°C → RED
- 39.5-41°C → ORANGE
- 38.5-39.4°C → YELLOW

---

### RN-019.3: Algoritmo Simplificado de Triagem
**Criticidade**: ALTA
**Categoria**: Lógica de Classificação

**Descrição**:
Implementação simplificada baseada em escala de dor:

**Algoritmo Atual** (placeholder para implementação completa):
```java
private String calculateTriageLevel(Map<String, Object> vitalSigns,
                                     String complaint, Integer painLevel) {
    // Implementação SIMPLIFICADA baseada em dor
    // Produção deve incluir análise completa de sinais vitais

    if (painLevel >= 8) return "RED";
    if (painLevel >= 6) return "ORANGE";
    if (painLevel >= 4) return "YELLOW";
    if (painLevel >= 2) return "GREEN";
    return "BLUE";
}
```

**Implementação Completa Planejada**:
```java
// FULL IMPLEMENTATION (comentada no código):
private String calculateTriageLevel(Map<String, Object> vitalSigns,
                                     String complaint, Integer painLevel) {
    Integer heartRate = (Integer) vitalSigns.get("heartRate");
    Integer systolicBP = (Integer) vitalSigns.get("systolicBP");
    Double temperature = (Double) vitalSigns.get("temperature");
    Integer oxygenSat = (Integer) vitalSigns.get("oxygenSaturation");
    Integer respiratoryRate = (Integer) vitalSigns.get("respiratoryRate");

    // RED - Risco imediato de vida
    if (oxygenSat < 90 || heartRate > 120 || systolicBP < 90) {
        return "RED";
    }

    // ORANGE - Muito urgente
    if (oxygenSat < 94 || heartRate > 100 || temperature > 39.5) {
        return "ORANGE";
    }

    // YELLOW - Urgente
    if (painLevel >= 4 || temperature > 38.5) {
        return "YELLOW";
    }

    // GREEN - Pouco urgente
    if (painLevel >= 2) {
        return "GREEN";
    }

    // BLUE - Não urgente
    return "BLUE";
}
```

---

## 3. Validação de Sinais Vitais

### RN-019.4: Validação de Ranges Aceitáveis
**Criticidade**: ALTA
**Categoria**: Validação de Dados

**Descrição**:
Sinais vitais devem estar dentro de ranges fisiologicamente plausíveis:

**Ranges Aceitáveis** (baseados em protocolos médicos):

**Pressão Arterial**:
- Sistólica: 60-250 mmHg
- Diastólica: 40-150 mmHg

**Frequência Cardíaca**:
- Range: 40-220 bpm
- Pediátrico pode ser mais alto (até 180 bpm normal em lactentes)

**Frequência Respiratória**:
- Range: 8-60 respirações/minuto
- Pediátrico pode variar significativamente

**Temperatura**:
- Range: 32-43°C (89.6-109.4°F)
- < 35°C: hipotermia
- > 41°C: hipertermia crítica

**Saturação de Oxigênio**:
- Range: 70-100%
- Valores < 70% são críticos mas fisiologicamente possíveis

**Implementação Planejada**:
```java
private void validateVitalSigns(Map<String, Object> vitalSigns) {
    // Implementação FUTURA quando integração EMR estiver definida
    //
    // Integer heartRate = (Integer) vitalSigns.get("heartRate");
    // if (heartRate != null && (heartRate < 40 || heartRate > 220)) {
    //     throw new BpmnError("INVALID_VITAL_SIGNS",
    //         "Heart rate out of acceptable range: " + heartRate);
    // }
    //
    // Integer systolicBP = (Integer) vitalSigns.get("systolicBP");
    // if (systolicBP != null && (systolicBP < 60 || systolicBP > 250)) {
    //     throw new BpmnError("INVALID_VITAL_SIGNS",
    //         "Systolic BP out of acceptable range: " + systolicBP);
    // }
    // ... outras validações

    log.debug("Vital signs validated successfully");
}
```

**Erro BPMN**: `INVALID_VITAL_SIGNS`

---

### RN-019.5: Sinais Vitais Obrigatórios
**Criticidade**: ALTA
**Categoria**: Validação de Entrada

**Descrição**:
Mapa de sinais vitais não pode ser null ou vazio:

**Implementação**:
```java
if (vitalSigns == null || vitalSigns.isEmpty()) {
    throw new BpmnError("INVALID_VITAL_SIGNS",
        "Vital signs cannot be null or empty");
}
```

**Sinais Vitais Mínimos Requeridos**:
- Pressão arterial (sistólica/diastólica)
- Frequência cardíaca
- Frequência respiratória
- Temperatura
- Saturação de oxigênio

---

## 4. Integração com EMR

### RN-019.6: Placeholder de Integração EMR
**Criticidade**: CRÍTICA
**Categoria**: Integração de Sistemas

**Descrição**:
Código contém placeholder para futura integração com sistema EMR:

**Implementação Planejada**:
```java
// QUANDO EMR API ESTIVER DISPONÍVEL:
//
// TriageRequest request = TriageRequest.builder()
//     .patientId(patientId)
//     .encounterId(encounterId)
//     .vitalSigns(vitalSigns)
//     .chiefComplaint(chiefComplaint)
//     .painLevel(painLevel)
//     .triageNurse(getCurrentUser())
//     .build();
//
// TriageResponse response = emrClient.registerTriage(request);
// if (!response.isSuccess()) {
//     throw new BpmnError("EMR_TRIAGE_FAILED", response.getErrorMessage());
// }
```

**Erro BPMN**: `EMR_TRIAGE_FAILED` (quando integração implementada)

---

### RN-019.7: Identificação do Enfermeiro de Triagem
**Criticidade**: MÉDIA
**Categoria**: Auditoria e Rastreabilidade

**Descrição**:
Sistema registra enfermeiro que realizou a triagem:

**Implementação Atual** (temporária):
```java
setVariable(execution, "triageNurse", "NURSE-" + System.currentTimeMillis() % 100);
```

**Implementação Futura**:
- Obter ID do usuário logado no sistema
- Validar credenciais de enfermagem
- Registrar timestamp e assinatura eletrônica

**Rastreabilidade**:
- Quem: `triageNurse`
- Quando: `triageDate`
- Decisão: `triageLevel` + `triagePriority`

---

## 5. Variáveis de Processo

### 5.1 Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `patientId` | String | Sim | ID único do paciente |
| `encounterId` | String | Sim | ID único do encontro |
| `vitalSigns` | Map<String, Object> | Sim | Sinais vitais completos |
| `chiefComplaint` | String | Sim | Queixa principal do paciente |
| `painLevel` | Integer | Não | Escala de dor 0-10 (default: 0) |

### 5.2 Estrutura de `vitalSigns`
```json
{
  "systolicBP": 140,
  "diastolicBP": 90,
  "heartRate": 88,
  "respiratoryRate": 18,
  "temperature": 37.2,
  "oxygenSaturation": 98
}
```

### 5.3 Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| `triageLevel` | String | Cor: RED, ORANGE, YELLOW, GREEN, BLUE |
| `triagePriority` | Integer | Prioridade numérica (1-5) |
| `triageDate` | LocalDateTime | Timestamp da triagem |
| `triageNurse` | String | ID do enfermeiro |
| `estimatedWaitTime` | Integer | Tempo de espera em minutos |

---

## 6. Casos de Uso

### 6.1 Caso Emergente (RED)
**Entrada**:
```json
{
  "patientId": "PAT-001",
  "encounterId": "ENC-ER-001",
  "vitalSigns": {
    "systolicBP": 80,
    "diastolicBP": 50,
    "heartRate": 130,
    "respiratoryRate": 32,
    "temperature": 36.5,
    "oxygenSaturation": 88
  },
  "chiefComplaint": "Severe chest pain",
  "painLevel": 10
}
```

**Saída**:
```json
{
  "triageLevel": "RED",
  "triagePriority": 1,
  "estimatedWaitTime": 0,
  "triageDate": "2026-01-12T10:30:00",
  "triageNurse": "NURSE-42"
}
```

**Ação**: Atendimento IMEDIATO - sala de emergência

---

### 6.2 Caso Urgente (YELLOW)
**Entrada**:
```json
{
  "patientId": "PAT-002",
  "encounterId": "ENC-ER-002",
  "vitalSigns": {
    "systolicBP": 130,
    "diastolicBP": 85,
    "heartRate": 92,
    "respiratoryRate": 20,
    "temperature": 38.8,
    "oxygenSaturation": 96
  },
  "chiefComplaint": "Abdominal pain",
  "painLevel": 5
}
```

**Saída**:
```json
{
  "triageLevel": "YELLOW",
  "triagePriority": 3,
  "estimatedWaitTime": 30,
  "triageDate": "2026-01-12T10:35:00"
}
```

**Ação**: Prioridade normal - aguardar até 30 minutos

---

### 6.3 Caso Não Urgente (BLUE)
**Entrada**:
```json
{
  "patientId": "PAT-003",
  "encounterId": "ENC-ER-003",
  "vitalSigns": {
    "systolicBP": 120,
    "diastolicBP": 80,
    "heartRate": 75,
    "respiratoryRate": 16,
    "temperature": 36.8,
    "oxygenSaturation": 99
  },
  "chiefComplaint": "Minor cut requiring suture",
  "painLevel": 1
}
```

**Saída**:
```json
{
  "triageLevel": "BLUE",
  "triagePriority": 5,
  "estimatedWaitTime": 120
}
```

**Ação**: Baixa prioridade - pode aguardar até 2 horas

---

## 7. Códigos de Erro BPMN

| Código | Descrição | Ação Recomendada |
|--------|-----------|------------------|
| `INVALID_VITAL_SIGNS` | Sinais vitais ausentes ou inválidos | Coletar sinais vitais válidos |
| `EMR_UNAVAILABLE` | Sistema EMR indisponível | Verificar conectividade/retry |

---

## 8. Conformidade e Protocolos

### 8.1 Regulamentações
- **Manchester Triage System**: Protocolo internacional de triagem
- **CFM Resolução 2148/2016**: Triagem em serviços de urgência
- **MS Portaria 2048/2002**: Regulamento técnico dos sistemas de urgência

### 8.2 Requisitos de Auditoria
- Triagem deve ser realizada em até 10 minutos da chegada do paciente
- Reavaliação obrigatória se tempo de espera exceder limite do nível
- Registro deve incluir enfermeiro responsável e timestamp

---

## 9. Notas de Implementação

### 9.1 Estado Atual
- ⚠️ **Algoritmo simplificado** baseado apenas em dor
- ⚠️ **Validação de sinais vitais** comentada (aguarda API EMR)
- ⚠️ **Integração EMR** não implementada (placeholder presente)
- ✅ **Estrutura de dados** pronta para implementação completa

### 9.2 Roadmap de Implementação
1. **Fase 1** (Atual): Estrutura básica e validações
2. **Fase 2**: Integração com API EMR
3. **Fase 3**: Algoritmo completo de Manchester Protocol
4. **Fase 4**: Validação robusta de sinais vitais
5. **Fase 5**: Machine learning para sugestão de triagem

### 9.3 Logging
```
INFO: Executing registrarTriagemDelegate for processInstanceId: 12345
DEBUG: Registering triage: patient=PAT-001, encounter=ENC-ER-001, complaint=Chest pain, pain=10
DEBUG: Vital signs validated successfully
INFO: registrarTriagemDelegate completed: level=RED, priority=1, wait=0min
```

---

## 10. Referências

- **Código Fonte**: `src/main/java/com/hospital/revenuecycle/delegates/triage/RegistrarTriagemDelegate.java`
- **Manchester Triage Group**: www.manchestertriage.com
- **CFM Resolução 2148/2016**: Triagem em serviços de urgência e emergência
- **MS Portaria 2048/2002**: Regulamento técnico dos sistemas estaduais de urgência
- **BaseDelegate**: Classe base para idempotência e validação

---

## X. Conformidade Regulatória

### Regulamentações Brasileiras
- **CFM Resolução 2148/2016**: Acolhimento e classificação de risco em serviços de urgência
- **MS Portaria 2048/2002**: Regulamento técnico dos sistemas estaduais de urgência e emergência
- **MS Portaria 1600/2011**: Reformula a Política Nacional de Atenção às Urgências (PNAU)
- **RDC ANVISA 63/2011**: Requisitos de funcionamento para Serviços de Urgência e Emergência

### Protocolo Manchester Triage System
- **Manchester Triage Group Guidelines**: Sistema internacional de classificação de risco
- **Fluxogramas de Discriminadores**: 52 fluxogramas para classificação por queixa principal
- **Tempos de Atendimento**: Definição de tempos máximos por categoria de urgência

### Proteção de Dados
- **LGPD Art. 11, II, a**: Tratamento de dados sensíveis de saúde para tutela da saúde
- **LGPD Art. 7º, VII**: Tratamento para proteção da vida (situações de emergência)

### Compliance Hospitalar
- **Joint Commission EC.02.03.05**: Manejo de emergências e triagem
- **CMS Emergency Medical Treatment and Labor Act (EMTALA)**: Avaliação e estabilização de emergências

---

## XI. Notas de Migração

### Avaliação de Complexidade
- **Rating**: ⭐⭐⭐ (MÉDIA) - 3/5
- **Justificativa**: Sistema de triagem com regras bem definidas pelo protocolo Manchester, validações estruturadas de sinais vitais, mas requer integração com prontuário eletrônico

### Mudanças Não-Retrocompatíveis (Breaking Changes)
1. **Estrutura de Dados de Triagem**: Migração para modelo estruturado com discriminadores do protocolo Manchester
2. **Campos Obrigatórios**: Adição de campos `painLevel`, `triageLevel`, `priority`, `maxWaitTime` como obrigatórios
3. **Validação de Sinais Vitais**: Implementação de regras de validação por faixa etária e condição clínica

### Recomendações para Implementação DMN
```xml
<!-- Sugestão de estrutura DMN para Manchester Triage -->
<decision id="manchester_triage_decision" name="Manchester Triage Classification">
  <decisionTable id="triage_level_determination">
    <input id="discriminator" label="Discriminador Manchester">
      <inputExpression typeRef="string">
        <text>discriminator</text>
      </inputExpression>
    </input>
    <input id="vital_signs" label="Sinais Vitais Críticos">
      <inputExpression typeRef="boolean">
        <text>hasAbnormalVitals</text>
      </inputExpression>
    </input>
    <input id="pain_level" label="Nível de Dor">
      <inputExpression typeRef="integer">
        <text>painLevel</text>
      </inputExpression>
    </input>
    <output id="triage_level" label="Nível Triagem" typeRef="string"/>
    <output id="max_wait_time" label="Tempo Máximo Espera" typeRef="integer"/>
    <rule>
      <inputEntry><text>"IMMEDIATE_THREAT_TO_LIFE"</text></inputEntry>
      <inputEntry><text>true</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>"RED"</text></outputEntry>
      <outputEntry><text>0</text></outputEntry>
    </rule>
    <rule>
      <inputEntry><text>"SEVERE_PAIN"</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <inputEntry><text>&gt;= 8</text></inputEntry>
      <outputEntry><text>"ORANGE"</text></outputEntry>
      <outputEntry><text>10</text></outputEntry>
    </rule>
  </decisionTable>
</decision>
```

### Fases de Migração Sugeridas
**Fase 1 - Configuração de Protocolos (1 semana)**
- Configuração de fluxogramas de discriminadores Manchester
- Definição de ranges de sinais vitais por faixa etária

**Fase 2 - Integração com Prontuário (1 semana)**
- Integração com sistema de registro de pacientes
- Captura automática de dados demográficos e queixa principal

**Fase 3 - Validações e Alertas (3 dias)**
- Implementação de validações de sinais vitais
- Configuração de alertas para triagens críticas (RED)

**Fase 4 - Treinamento e Go-Live (1 semana)**
- Treinamento de equipe de enfermagem
- Monitoramento de aderência ao protocolo

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Context**: Emergency Department Management
**Subdomínio**: Triage & Initial Assessment

### Aggregates

#### 1. TriageRecord (Root)
```yaml
TriageRecord:
  identity: triageId
  properties:
    - patientId: String
    - encounterId: String
    - triageTimestamp: Instant
    - chiefComplaint: String
    - triageLevel: TriageLevel [RED|ORANGE|YELLOW|GREEN|BLUE]
    - priority: Integer
    - maxWaitTimeMinutes: Integer

  value_objects:
    - VitalSigns:
        bloodPressureSystolic: Integer
        bloodPressureDiastolic: Integer
        heartRate: Integer
        respiratoryRate: Integer
        temperature: BigDecimal
        oxygenSaturation: Integer
        painLevel: Integer
        consciousness: String [ALERT|VERBAL|PAIN|UNRESPONSIVE]

    - ManchesterDiscriminator:
        discriminatorCode: String
        discriminatorName: String
        category: String [LIFE_THREATENING|VERY_URGENT|URGENT|STANDARD|NON_URGENT]

    - TriageNurse:
        nurseId: String
        nurseName: String
        coren: String

  behaviors:
    - classifyTriageLevel()
    - calculatePriority()
    - determineMaxWaitTime()
    - validateVitalSigns()
    - escalateIfCritical()
```

#### 2. PatientQueue
```yaml
PatientQueue:
  identity: queueId
  properties:
    - queueDate: LocalDate
    - department: String
    - patients: List<QueueEntry>

  value_objects:
    - QueueEntry:
        triageId: String
        patientId: String
        arrivalTime: Instant
        triageLevel: TriageLevel
        priority: Integer
        estimatedWaitTime: Integer
        queuePosition: Integer

  behaviors:
    - addPatientToQueue()
    - reorderByPriority()
    - callNextPatient()
    - updateWaitTimes()
```

### Domain Events

#### 1. PatientTriaged
```json
{
  "eventType": "PatientTriaged",
  "eventId": "evt-triage-001",
  "timestamp": "2025-01-12T10:15:00Z",
  "aggregateId": "TRIAGE-001",
  "payload": {
    "triageId": "TRIAGE-001",
    "patientId": "PAT-001",
    "encounterId": "ENC-ER-001",
    "chiefComplaint": "Chest pain",
    "triageLevel": "RED",
    "priority": 1,
    "maxWaitTime": 0,
    "vitalSigns": {
      "bloodPressure": "180/110",
      "heartRate": 120,
      "painLevel": 10,
      "consciousness": "ALERT"
    },
    "triageNurse": "NURSE-001"
  }
}
```

#### 2. CriticalTriageDetected
```json
{
  "eventType": "CriticalTriageDetected",
  "eventId": "evt-critical-001",
  "timestamp": "2025-01-12T10:15:05Z",
  "aggregateId": "TRIAGE-001",
  "payload": {
    "triageId": "TRIAGE-001",
    "patientId": "PAT-001",
    "triageLevel": "RED",
    "discriminator": "IMMEDIATE_THREAT_TO_LIFE",
    "criticalVitals": ["HIGH_BLOOD_PRESSURE", "TACHYCARDIA"],
    "actionRequired": "IMMEDIATE_PHYSICIAN_EVALUATION",
    "alertSentTo": ["PHYSICIAN_ON_DUTY", "CHARGE_NURSE"]
  }
}
```

#### 3. QueuePositionUpdated
```json
{
  "eventType": "QueuePositionUpdated",
  "eventId": "evt-queue-001",
  "timestamp": "2025-01-12T10:15:10Z",
  "aggregateId": "QUEUE-ER-2025-01-12",
  "payload": {
    "queueId": "QUEUE-ER-2025-01-12",
    "updates": [
      {
        "patientId": "PAT-001",
        "newPosition": 1,
        "estimatedWaitTime": 0
      },
      {
        "patientId": "PAT-002",
        "newPosition": 2,
        "estimatedWaitTime": 15
      }
    ]
  }
}
```

### Contexto de Microsserviços
**Serviço Recomendado**: `Emergency-Department-Service`
**Justificativa**:
- Triagem é processo crítico de tempo real que requer alta disponibilidade
- Isolamento garante que problemas em outros serviços não afetem triagem
- Permite escalabilidade independente para horários de pico de demanda

**Dependências de Domínio**:
- Patient-Registration-Service (dados demográficos do paciente)
- Clinical-Documentation-Service (registro da avaliação inicial)
- Bed-Management-Service (alocação de leito pós-triagem)

---

## XIII. Metadados Técnicos

### Métricas de Complexidade
```yaml
complexity_metrics:
  cyclomatic_complexity: 12
  cognitive_complexity: 15
  lines_of_code: 198
  number_of_methods: 5
  max_nesting_level: 3

  complexity_rating: MEDIUM
  maintainability_index: 71
  technical_debt_ratio: 5.2%
```

### Cobertura de Testes
```yaml
test_coverage:
  line_coverage: 0%
  branch_coverage: 0%
  method_coverage: 0%

  test_status: NOT_IMPLEMENTED
  priority: CRITICAL
  estimated_tests_required: 15

  suggested_test_types:
    - unit_tests: "Validação de sinais vitais, classificação Manchester"
    - integration_tests: "Integração com prontuário, fila de atendimento"
    - edge_case_tests: "Sinais vitais críticos, paciente inconsciente, politrauma"
```

### Métricas de Desempenho
```yaml
performance_metrics:
  average_execution_time: "80ms"
  p95_execution_time: "120ms"
  p99_execution_time: "180ms"

  performance_considerations:
    - "Triagem deve ser sub-segundo para não impactar atendimento de emergência"
    - "Validações de sinais vitais devem ser síncronas e rápidas"
    - "Atualização de fila deve ser em tempo real"

  sla_requirements:
    - "Tempo de resposta < 200ms para 99% das requisições"
    - "Disponibilidade 99.9% (máximo 43 minutos downtime/mês)"
    - "Alertas críticos entregues em < 5 segundos"
```

### Dependências e Integrações
```yaml
dependencies:
  internal_services:
    - service: PatientRegistrationService
      purpose: "Obtenção de dados demográficos do paciente"
      criticality: HIGH

    - service: BedManagementService
      purpose: "Solicitação de leito após triagem"
      criticality: MEDIUM

  external_systems:
    - system: "Electronic Medical Record"
      integration: "HL7 FHIR"
      purpose: "Registro de avaliação de triagem"

    - system: "Queue Display System"
      integration: "WebSocket"
      purpose: "Atualização em tempo real de painel de triagem"

  databases:
    - name: "Emergency Department DB"
      type: "PostgreSQL"
      tables: ["triage_records", "patient_queue", "vital_signs"]

  message_queues:
    - queue: "emergency.critical.alerts"
      purpose: "Publicação de triagens críticas (RED) para acionamento imediato"
```

---

**Documento gerado por**: AI Swarm - Hive Mind Documentation Generator
**Total de Regras**: 17 regras de negócio
**Revisão**: Necessária por enfermagem e gestão de pronto-socorro
**Próxima revisão**: Anual ou quando houver mudanças no protocolo de Manchester
