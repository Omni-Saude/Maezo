# RN-TASYCodingClient - Cliente de Codificação Médica IA

## 1. Identificação da Regra
- **ID:** RN-TASY-CODING-CLIENT-001
- **Nome:** Cliente Feign de Codificação Médica com IA
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 4
- **Categoria:** Integration Layer / AI Coding
- **Prioridade:** Crítica
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
O TASYCodingClient fornece integração com sistema de codificação médica com IA que oferece:
- Sugestões automáticas de códigos ICD-10/ICD-11
- Sugestões de códigos de procedimentos CPT/TUSS
- Cálculo e validação de DRG (Diagnosis Related Groups)
- Auditoria de codificação e verificação de conformidade
- Validação de necessidade médica

### 2.2. Descrição Técnica
Interface Feign Cliente para API de codificação TASY com endpoints para sugestão de códigos baseada em IA, validação de necessidade médica, cálculo de DRG, auditoria abrangente e autocorreção de erros comuns.

### 2.3. Origem do Requisito
- **Funcional:** Automação de codificação médica para reduzir tempo e erros
- **Regulatório:** RN-453 ANS - Codificação correta obrigatória para faturamento
- **Técnico:** Integração com ML models para sugestão inteligente de códigos

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Sugestão automática de código ICD-10 baseado em diagnóstico clínico
- **UC-02**: Sugestão de código de procedimento baseado em descrição
- **UC-03**: Validação de necessidade médica entre diagnóstico e procedimento
- **UC-04**: Cálculo de DRG com MS-DRG Grouper
- **UC-05**: Auditoria abrangente de códigos contra regras de pagadores
- **UC-06**: Autocorreção de erros de codificação usando ML
- **UC-07**: Validação de combinações de códigos (incompatibilidades)

### 3.2. Processos BPMN Relacionados
- **Process ID:** medical-coding
  - **Task:** Codificar Diagnóstico com IA
  - **Service Task:** AIDiagnosisCodingTask
- **Process ID:** procedure-coding
  - **Task:** Codificar Procedimento com IA
  - **Service Task:** AIProcedureCodingTask
- **Process ID:** drg-calculation
  - **Task:** Calcular DRG
  - **Service Task:** DRGCalculationTask
- **Process ID:** coding-audit
  - **Task:** Auditar Codificação
  - **Service Task:** CodingAuditTask

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
PARA codificação automática:
  SE diagnóstico clínico disponível:
    - CHAMAR suggestICD10Code(diagnosis, encounterId)
    - RETORNAR código ICD-10 sugerido
  
  SE descrição de procedimento disponível:
    - CHAMAR suggestProcedureCode(procedure, encounterId)
    - RETORNAR código CPT/TUSS sugerido
  
  APÓS codificação:
    - VALIDAR necessidade médica via validateMedicalNecessity()
    - SE não atender critérios:
      - MARCAR para revisão manual
      - REGISTRAR violação
```

### 4.2. Endpoints e Métodos

#### suggestICD10Code()
```java
@PostMapping("/icd10/suggest")
String suggestICD10Code(
    @RequestParam("diagnosis") String diagnosis,
    @RequestParam("encounterId") String encounterId
)
```
- **Entrada**: Descrição clínica do diagnóstico, ID do encontro
- **Saída**: Código ICD-10 sugerido (ex: "E11.9" - Diabetes tipo 2 sem complicações)
- **ML Model**: NLP transformer treinado em milhões de prontuários
- **Confiança**: > 85% para sugestão automática, < 85% requer revisão

#### suggestProcedureCode()
```java
@PostMapping("/procedure/suggest")
String suggestProcedureCode(
    @RequestParam("procedure") String procedure,
    @RequestParam("encounterId") String encounterId
)
```
- **Entrada**: Descrição do procedimento realizado
- **Saída**: Código CPT/TUSS (ex: "40101010" - Consulta em consultório)
- **Validação**: Verifica compatibilidade com terminologia TUSS

#### validateMedicalNecessity()
```java
@GetMapping("/validate/medical-necessity")
Map<String, Object> validateMedicalNecessity(
    @RequestParam("icdCode") String icdCode,
    @RequestParam("procedureCode") String procedureCode,
    @RequestParam("payerId") String payerId
)
```
- **Entrada**: ICD-10, procedimento, pagador
- **Saída**: 
  ```json
  {
    "medicalNecessityMet": true/false,
    "confidence": 0.92,
    "payer_rules_applied": ["LCD_12345", "NCD_67890"],
    "justification": "Procedimento é medicamente necessário para o diagnóstico",
    "violations": []
  }
  ```

#### calculateDRG()
```java
@PostMapping("/drg/calculate")
Map<String, Object> calculateDRG(@RequestBody Map<String, Object> request)
```
- **Entrada**:
  ```json
  {
    "principal_diagnosis": "E11.9",
    "secondary_diagnoses": ["I10", "N18.3"],
    "procedures": ["40101010"],
    "age": 65,
    "gender": "M",
    "discharge_status": "HOME"
  }
  ```
- **Saída**:
  ```json
  {
    "drg_code": "637",
    "drg_description": "Diabetes com MCC",
    "relative_weight": 1.2345,
    "geometric_mean_los": 4.5,
    "estimated_reimbursement": 15000.00
  }
  ```

#### performCodingAudit()
```java
@PostMapping("/audit/comprehensive")
Map<String, Object> performCodingAudit(@RequestBody Map<String, Object> auditRequest)
```
- **Entrada**:
  ```json
  {
    "encounter_id": "ENC-123",
    "icd_codes": ["E11.9", "I10"],
    "procedure_codes": ["40101010"],
    "payer_id": "CONV-123"
  }
  ```
- **Saída**:
  ```json
  {
    "audit_status": "PASSED|FAILED|WARNINGS",
    "violations": [
      {
        "code": "ICD-SPECIFICITY",
        "severity": "WARNING",
        "message": "Use código mais específico para E11.9",
        "suggested_fix": "E11.65 - Diabetes tipo 2 com complicação renal"
      }
    ],
    "compliance_score": 0.95
  }
  ```

## 5. Mapeamento TISS/ANS

### 5.1. Versão TISS: 4.03.03

### 5.2. Campos de Codificação Mapeados
| Método | Campo TISS | Guia TISS | Validação |
|--------|------------|-----------|-----------|
| suggestICD10Code | diagnostico.codigoCID | Internação, SP-SADT | Obrigatório |
| suggestProcedureCode | procedimento.codigoProcedimento | Todas | Obrigatório |
| calculateDRG | drg.codigo | Internação | Se aplicável |
| validateMedicalNecessity | justificativa | Todas | Se negado |

### 5.3. Requisitos ANS de Codificação
- **RN-453**: Códigos válidos conforme terminologia TUSS
- **RN-338**: Diagnóstico compatível com procedimento
- **RN-305**: DRG calculado corretamente para internações

## 6. Compliance e Regulamentação

### 6.1. Normas de Codificação
- **CID-10**: Classificação Internacional de Doenças (OMS)
- **TUSS**: Terminologia Unificada da Saúde Suplementar (ANS)
- **CBHPM**: Classificação Brasileira Hierarquizada de Procedimentos Médicos (AMB/CFM)
- **MS-DRG**: Medicare Severity Diagnosis Related Groups

### 6.2. Validações Regulatórias
1. **Especificidade**: Código deve ser mais específico possível (evitar .9 quando possível)
2. **Necessidade Médica**: Procedimento deve ser justificado pelo diagnóstico
3. **Combinações Válidas**: Códigos não podem ser mutuamente exclusivos
4. **Regras do Pagador**: LCD (Local Coverage Determination) e NCD (National Coverage Determination)

### 6.3. Auditoria e Rastreabilidade
- **Todas as sugestões de IA** logadas com confiança e contexto
- **Decisões de autocorreção** auditáveis
- **Violações de codificação** rastreadas para melhoria contínua do modelo

## 7. Tratamento de Erros e Exceções

### 7.1. Exceções de Negócio
| Código | Exceção | Causa | Ação |
|--------|---------|-------|------|
| CODING-001 | InvalidDiagnosisException | Diagnóstico inválido/vazio | Revisar entrada |
| CODING-002 | NoSuggestionAvailableException | IA não conseguiu sugerir código | Codificação manual |
| CODING-003 | MedicalNecessityViolation | Necessidade médica não atendida | Adicionar justificativa clínica |
| CODING-004 | DRGCalculationFailedException | Falha no cálculo de DRG | Verificar dados de entrada |
| CODING-005 | CombinationInvalidException | Combinação de códigos inválida | Revisar códigos |

### 7.2. Estratégias de Fallback
1. **Sugestão com baixa confiança** (< 85%): Enviar para revisão manual
2. **Erro de API**: Usar codificação manual tradicional
3. **Timeout**: Retry até 3x, depois fallback

## 8. Performance e Otimização

### 8.1. Requisitos de Performance
- **Latência de Sugestão**: < 2 segundos (inferência de modelo)
- **Latência de Validação**: < 1 segundo (regras determinísticas)
- **Latência de DRG**: < 5 segundos (cálculo complexo)
- **Throughput**: > 50 sugestões/segundo

### 8.2. Otimizações de IA
1. **Model Caching**: Modelo carregado em memória (warm start)
2. **Batch Inference**: Processar múltiplos diagnósticos em lote
3. **Feature Caching**: Contexto de encontro cacheado
4. **Quantização**: Modelo quantizado para reduzir latência

## 9. Exemplos de Uso

### 9.1. Exemplo Básico - Codificação com IA
```java
@Service
@RequiredArgsConstructor
public class AICodingService {
    
    private final TASYCodingClient codingClient;
    
    public CodingResult codeEncounter(String encounterId, String diagnosis, String procedure) {
        // 1. Sugerir código ICD-10
        String icdCode = codingClient.suggestICD10Code(diagnosis, encounterId);
        
        // 2. Sugerir código de procedimento
        String procedureCode = codingClient.suggestProcedureCode(procedure, encounterId);
        
        // 3. Validar necessidade médica
        Map<String, Object> validation = codingClient.validateMedicalNecessity(
            icdCode, procedureCode, "CONV-123"
        );
        
        boolean isValid = (boolean) validation.get("medicalNecessityMet");
        
        return new CodingResult(icdCode, procedureCode, isValid, validation);
    }
}
```

### 9.2. Exemplo Avançado - Pipeline Completo
```java
@Service
@RequiredArgsConstructor
@Slf4j
public class CompleteCodingPipeline {
    
    private final TASYCodingClient codingClient;
    private final TasyWebClient tasyWebClient;
    
    @Transactional
    public CompleteCodingResult processEncounter(String encounterId) {
        // 1. Buscar prontuário
        TasyMedicalRecord record = tasyWebClient.getMedicalRecord(encounterId);
        
        // 2. Sugestão de código primário
        String primaryICD = codingClient.suggestICD10Code(
            record.getAssessmentAndPlan(), encounterId
        );
        
        // 3. Buscar procedimentos realizados
        List<TasyPhysicianNote> notes = tasyWebClient.getPhysicianNotes(encounterId);
        String procedureDescription = extractProcedureFromNotes(notes);
        
        String procedureCode = codingClient.suggestProcedureCode(
            procedureDescription, encounterId
        );
        
        // 4. Validar necessidade médica
        Map<String, Object> medicalNecessity = codingClient.validateMedicalNecessity(
            primaryICD, procedureCode, record.getPayerId()
        );
        
        if (!(boolean) medicalNecessity.get("medicalNecessityMet")) {
            log.warn("Medical necessity not met for {}: {}", encounterId, medicalNecessity);
            return CompleteCodingResult.failed(medicalNecessity);
        }
        
        // 5. Calcular DRG (se internação)
        Map<String, Object> drgResult = null;
        if ("INPATIENT".equals(record.getEncounterType())) {
            Map<String, Object> drgRequest = buildDRGRequest(record, primaryICD, procedureCode);
            drgResult = codingClient.calculateDRG(drgRequest);
        }
        
        // 6. Auditoria abrangente
        Map<String, Object> auditRequest = Map.of(
            "encounter_id", encounterId,
            "icd_codes", List.of(primaryICD),
            "procedure_codes", List.of(procedureCode),
            "payer_id", record.getPayerId()
        );
        
        Map<String, Object> auditResult = codingClient.performCodingAudit(auditRequest);
        
        // 7. Auto-correção se violações encontradas
        List<Map<String, Object>> violations = 
            (List<Map<String, Object>>) auditResult.get("violations");
        
        if (!violations.isEmpty()) {
            log.info("Found {} coding violations, attempting auto-correction", violations.size());
            
            Map<String, String> corrections = codingClient.autoCorrectCodes(violations);
            
            if (!corrections.isEmpty()) {
                primaryICD = corrections.getOrDefault("primary_diagnosis", primaryICD);
                procedureCode = corrections.getOrDefault("procedure_code", procedureCode);
                
                // Re-auditar após correção
                auditRequest = Map.of(
                    "encounter_id", encounterId,
                    "icd_codes", List.of(primaryICD),
                    "procedure_codes", List.of(procedureCode),
                    "payer_id", record.getPayerId()
                );
                auditResult = codingClient.performCodingAudit(auditRequest);
            }
        }
        
        return CompleteCodingResult.builder()
            .encounterId(encounterId)
            .primaryDiagnosis(primaryICD)
            .procedureCode(procedureCode)
            .medicalNecessityValidation(medicalNecessity)
            .drgResult(drgResult)
            .auditResult(auditResult)
            .autoCorrectionsApplied(violations.size() > 0)
            .build();
    }
}
```

## 10. Testes e Validação

### 10.1. Cenários de Teste
```java
@SpringBootTest
class TASYCodingClientTest {
    
    @Autowired
    private TASYCodingClient codingClient;
    
    @Test
    void testSuggestICD10_DiabetesType2() {
        String icdCode = codingClient.suggestICD10Code(
            "Paciente com diabetes mellitus tipo 2 não controlado", 
            "ENC-123"
        );
        
        assertTrue(icdCode.startsWith("E11")); // Grupo E11 = Diabetes tipo 2
        assertNotEquals("E11.9", icdCode); // Deve ser mais específico
    }
    
    @Test
    void testValidateMedicalNecessity_Valid() {
        Map<String, Object> result = codingClient.validateMedicalNecessity(
            "E11.65",  // Diabetes tipo 2 com complicação renal
            "40301010", // Consulta em nefrologia
            "CONV-123"
        );
        
        assertTrue((boolean) result.get("medicalNecessityMet"));
        assertTrue((double) result.get("confidence") > 0.8);
    }
    
    @Test
    void testCalculateDRG_DiabetesWithComplications() {
        Map<String, Object> request = Map.of(
            "principal_diagnosis", "E11.65",
            "secondary_diagnoses", List.of("I10", "N18.3"),
            "procedures", List.of(),
            "age", 65,
            "gender", "M",
            "discharge_status", "HOME"
        );
        
        Map<String, Object> result = codingClient.calculateDRG(request);
        
        assertNotNull(result.get("drg_code"));
        assertTrue((double) result.get("relative_weight") > 1.0); // Com complicações
    }
}
```

## 14. Referências

### 14.1. Documentação Relacionada
- `TasyClient.java` - Cliente base TASY
- `TasyWebClient.java` - Cliente reativo para dados clínicos
- DTOs de codificação: `CodingAuditResult`, `DRGSuggestion`, `CodeValidationResult`

### 14.2. Padrões de Codificação
- [CID-10 (ICD-10)](https://www.who.int/standards/classifications/classification-of-diseases)
- [TUSS - ANS](http://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar)
- [MS-DRG](https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/ms-drg-classifications-and-software)

### 14.3. Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:5f8d2c9e1b3a7d4f6c9e2a8b5d1c7f3e9a6d2b8f4c7e1a9d5b3f8c2e6a4d7b1`
**Última Atualização:** 2026-01-12T13:20:00Z
**Próxima Revisão:** 2026-04-12
