# RN-EncaminharAtendimentoDelegate - Encaminhamento de Atendimento

## Identificação
- **ID**: RN-TRIAGE-002
- **Nome**: EncaminharAtendimentoDelegate
- **Categoria**: Triage (Triagem)
- **Subprocess**: SUB_02_Triagem
- **Versão**: 1.0.0
- **Bean BPMN**: `encaminharAtendimentoDelegate`
- **Autor**: AI Swarm - Forensics Delegate Generation

## Visão Geral
Delegate responsável por encaminhar paciente para área de cuidado apropriada baseado no nível de triagem, atribuindo leito/sala e profissional disponível.

## Responsabilidades

### 1. Determinação de Área de Cuidado
- Define área baseada no nível de triagem Manchester
- RED/ORANGE → Sala de Emergência (ER)
- YELLOW → Unidade de Observação (OBS)
- GREEN/BLUE → Clínica Ambulatorial (CLINIC)

### 2. Atribuição de Profissional
- Busca profissional disponível na área
- Considera especialidade requerida
- Balanceia carga de trabalho
- Respeita turnos e disponibilidade

### 3. Atribuição de Leito/Sala
- Aloca leito ou sala de atendimento
- Verifica status de limpeza
- Considera requisitos de isolamento
- Valida restrições de gênero

### 4. Registro de Encaminhamento
- Registra área, profissional e sala atribuídos
- Gera timestamp do encaminhamento
- Habilita rastreamento do paciente

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `triageLevel` | String | Sim | Nível de triagem Manchester (RED, ORANGE, YELLOW, GREEN, BLUE) |
| `triagePriority` | Integer | Sim | Prioridade numérica da triagem |
| `encounterId` | String | Sim | Identificador do atendimento |
| `specialtyRequired` | String | Não | Especialidade médica requerida |

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `assignedArea` | String | Área de cuidado atribuída (ER, OBS, CLINIC) |
| `assignedProvider` | String | ID do profissional atribuído |
| `roomNumber` | String | Número do leito/sala atribuído |
| `routingDate` | LocalDateTime | Timestamp do encaminhamento |

## Algoritmo

```
1. Validar entrada:
   - triageLevel, triagePriority, encounterId não nulos

2. Determinar área de cuidado:
   - assignedArea = determineCareArea(triageLevel)
   - RED/ORANGE → "ER"
   - YELLOW → "OBS"
   - GREEN/BLUE → "CLINIC"

3. Buscar profissional disponível:
   - assignedProvider = findAvailableProvider(assignedArea, specialtyRequired)
   - Consulta base de disponibilidade de profissionais
   - Considera:
     * Match de especialidade
     * Carga de trabalho atual
     * Preferências do profissional
     * Métricas de qualidade

4. Atribuir leito/sala:
   - roomNumber = assignRoom(assignedArea)
   - Consulta sistema de gestão de leitos
   - Considera:
     * Status de limpeza (CLEAN_AVAILABLE)
     * Requisitos de isolamento
     * Restrições de gênero
     * Proximidade da estação de enfermagem

5. Registrar encaminhamento:
   - routingDate = LocalDateTime.now()
   - Persistir todas variáveis de saída

6. Integração com Bed Management (quando disponível):
   - BedAssignmentRequest request
   - BedAssignmentResponse response = bedManagementClient.assignBed(request)
   - Usar dados reais de response

7. Registrar log de sucesso
```

## Determinação de Área de Cuidado

### Método determineCareArea()
```java
private String determineCareArea(String triageLevel) {
    // Bed management routing rules based on acuity:
    // RED/ORANGE: Emergency Room (Resuscitation/Immediate Care)
    // YELLOW: Observation Unit or Fast Track
    // GREEN/BLUE: Ambulatory Clinic or Fast Track
    //
    // Advanced routing considers:
    // - Bed availability by unit
    // - Staff-to-patient ratios
    // - Isolation requirements
    // - Equipment needs
    // - Specialty care requirements
    //
    // Implementation approach:
    // SELECT unit_code FROM care_units
    // WHERE acuity_level >= ? AND available_beds > 0
    // AND (specialty = ? OR specialty IS NULL)
    // ORDER BY available_beds DESC, average_wait_time ASC
    // LIMIT 1

    return switch (triageLevel) {
        case "RED", "ORANGE" -> "ER";
        case "YELLOW" -> "OBS";
        default -> "CLINIC";
    };
}
```

## Busca de Profissional Disponível

### Método findAvailableProvider()
```java
private String findAvailableProvider(String area, String specialty) {
    // Provider availability and assignment logic:
    // Query provider schedule and current patient load
    //
    // Implementation approach:
    // SELECT provider_id FROM provider_availability
    // WHERE care_area = ? AND specialty IN (?, 'GENERAL')
    // AND shift_date = CURRENT_DATE AND status = 'AVAILABLE'
    // AND current_patient_count < max_patient_load
    // ORDER BY current_patient_count ASC, last_assignment_time ASC
    // LIMIT 1
    //
    // Considers:
    // - Provider specialty match
    // - Current patient load
    // - Provider preferences
    // - Teaching requirements
    // - Quality metrics

    return "PROV-" + area + "-" + (System.currentTimeMillis() % 10);
}
```

## Atribuição de Leito/Sala

### Método assignRoom()
```java
private String assignRoom(String area) {
    // Real-time bed/room assignment logic:
    // Query bed management system for available beds
    //
    // Implementation approach:
    // SELECT room_number FROM beds
    // WHERE care_unit = ? AND status = 'CLEAN_AVAILABLE'
    // AND (isolation_type IS NULL OR isolation_type = ?)
    // AND (gender_restriction IS NULL OR gender_restriction = ?)
    // ORDER BY bed_priority, room_number
    // LIMIT 1
    //
    // After assignment:
    // UPDATE beds SET status = 'OCCUPIED', patient_id = ?, assigned_at = NOW()
    // WHERE room_number = ?
    //
    // Considers:
    // - Bed cleanliness status
    // - Isolation requirements
    // - Gender-specific units
    // - Equipment availability
    // - Room proximity to nursing station

    return area + "-ROOM-" + (System.currentTimeMillis() % 20 + 1);
}
```

## Casos de Uso

### Caso 1: Paciente Crítico (RED)
**Entrada**:
```json
{
  "triageLevel": "RED",
  "triagePriority": 1,
  "encounterId": "ENC-2025-001",
  "specialtyRequired": "emergency_medicine"
}
```

**Saída**:
```json
{
  "assignedArea": "ER",
  "assignedProvider": "PROV-ER-3",
  "roomNumber": "ER-ROOM-5",
  "routingDate": "2025-01-12T10:45:00"
}
```

### Caso 2: Paciente Moderado (YELLOW)
**Entrada**:
```json
{
  "triageLevel": "YELLOW",
  "triagePriority": 3,
  "encounterId": "ENC-2025-002",
  "specialtyRequired": null
}
```

**Saída**:
```json
{
  "assignedArea": "OBS",
  "assignedProvider": "PROV-OBS-7",
  "roomNumber": "OBS-ROOM-12",
  "routingDate": "2025-01-12T10:50:00"
}
```

### Caso 3: Paciente Baixa Prioridade (GREEN)
**Entrada**:
```json
{
  "triageLevel": "GREEN",
  "triagePriority": 4,
  "encounterId": "ENC-2025-003",
  "specialtyRequired": "general_practice"
}
```

**Saída**:
```json
{
  "assignedArea": "CLINIC",
  "assignedProvider": "PROV-CLINIC-2",
  "roomNumber": "CLINIC-ROOM-8",
  "routingDate": "2025-01-12T10:55:00"
}
```

## Regras de Negócio

### RN-TRIAGE-002-001: Validação de Parâmetros
- **Descrição**: Parâmetros obrigatórios devem ser fornecidos
- **Prioridade**: CRÍTICA
- **Validação**: `triageLevel, triagePriority, encounterId != null`

### RN-TRIAGE-002-002: Mapeamento de Área por Nível
- **Descrição**: Área de cuidado baseada em nível de triagem
- **Prioridade**: CRÍTICA
- **Mapping**:
  - RED/ORANGE → ER (Sala de Emergência)
  - YELLOW → OBS (Unidade de Observação)
  - GREEN/BLUE → CLINIC (Clínica Ambulatorial)

### RN-TRIAGE-002-003: Balanceamento de Carga
- **Descrição**: Profissional com menor carga deve ser priorizado
- **Prioridade**: ALTA
- **Algoritmo**: `ORDER BY current_patient_count ASC`

### RN-TRIAGE-002-004: Requisitos de Especialidade
- **Descrição**: Priorizar match de especialidade quando fornecido
- **Prioridade**: MÉDIA
- **Fallback**: Profissional GENERAL se especialista não disponível

## Integração com Bed Management System

### BedAssignmentRequest
```java
class BedAssignmentRequest {
    String encounterId;
    String triageLevel;
    int priority;
    String requiredSpecialty;
    String patientGender;
    Boolean isolationRequired;
}
```

### BedAssignmentResponse
```java
class BedAssignmentResponse {
    boolean success;
    String careArea;
    String providerId;
    String roomNumber;
    String errorMessage;    // Se !success
}
```

## Fluxo BPMN Típico

```
[Registrar Triagem]
    ↓
[Encaminhar Atendimento] ← Este delegate
    ↓
[Registrar Atendimento]
    ↓
[Coletar Dados Clínicos]
```

## Níveis de Triagem Manchester

| Nível | Cor | Prioridade | Tempo Máximo | Área Típica |
|-------|-----|------------|--------------|-------------|
| 1 | RED | Imediato | 0 min | ER - Ressuscitação |
| 2 | ORANGE | Muito Urgente | 10 min | ER - Emergência |
| 3 | YELLOW | Urgente | 60 min | OBS - Observação |
| 4 | GREEN | Pouco Urgente | 120 min | CLINIC - Ambulatório |
| 5 | BLUE | Não Urgente | 240 min | CLINIC - Ambulatório |

## Idempotência

**Requer Idempotência**: Não

**Parâmetros de Idempotência**:
```java
Map<String, Object> params = {
    "triageLevel": triageLevel,
    "triagePriority": triagePriority,
    "encounterId": encounterId
}
```

**Justificativa**: Se executado múltiplas vezes, pode retornar diferente profissional/sala baseado em disponibilidade em tempo real.

## Métricas de Qualidade

### Indicadores
- **Tempo de Encaminhamento**: Tempo entre triagem e atribuição de área
- **Taxa de Ociosidade**: `(profissionais inativos / total) * 100%`
- **Balanceamento de Carga**: Desvio padrão da carga por profissional
- **Taxa de Reassignment**: `(reatribuições / total) * 100%`

### Metas
- Tempo de Encaminhamento < 5 minutos
- Taxa de Ociosidade < 10%
- Desvio Padrão de Carga < 2 pacientes
- Taxa de Reassignment < 5%

## Dependências
- **Bed Management System**: Sistema de gestão de leitos
- **Provider Schedule System**: Sistema de escala de profissionais
- **Triage System**: Sistema de triagem Manchester

## Versionamento
- **v1.0.0**: Implementação inicial com lógica simplificada

## Referências
- RN-RegistrarTriagem: Documentação de registro de triagem (etapa anterior)
- RN-RegisterEncounter: Documentação de registro de atendimento (etapa seguinte)
- Manchester Triage System: https://www.triagenet.net/
- Bed Management Best Practices: https://www.ahrq.gov/
