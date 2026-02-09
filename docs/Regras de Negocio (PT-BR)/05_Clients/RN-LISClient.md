# RN-LISClient - Cliente de Integração com Sistema de Informação Laboratorial

## Identificação
- **ID**: RN-LISClient
- **Nome**: LIS (Laboratory Information System) Client
- **Categoria**: Integration/External System
- **Subcategoria**: Laboratory Integration
- **Camada**: Integration Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/lis/LISClient.java`

---

## Descrição

Cliente Feign para integração com o Sistema de Informação Laboratorial (LIS), responsável por gerenciar operações laboratoriais incluindo pedidos de exames, rastreamento de amostras, resultados de testes e geração de relatórios.

**Padrão de Integração**: HL7 FHIR R4
**Recursos FHIR Utilizados**:
- ServiceRequest (pedidos de exames)
- DiagnosticReport (resultados)
- Specimen (amostras biológicas)
- Observation (observações individuais)

---

## Propósito e Objetivo

### Objetivo Principal
Fornecer interface padronizada para comunicação com sistemas LIS externos usando protocolo HL7 FHIR, permitindo consulta de pedidos laboratoriais, resultados de exames e status de amostras necessários para o ciclo de faturamento.

### Problema que Resolve
- **Integração heterogênea**: Padroniza comunicação com diferentes sistemas LIS
- **Rastreabilidade**: Vincula exames laboratoriais a encontros hospitalares
- **Faturamento preciso**: Associa resultados de exames a procedimentos cobráveis
- **Auditoria clínica**: Suporta validação de códigos de procedimentos (TUSS/TISS)

---

## Relacionamento com o Processo BPMN

### Sub-processos Relacionados
1. **Pré-Validação de Prontuário**
   - Verifica se exames laboratoriais foram solicitados
   - Valida se resultados estão disponíveis antes da cobrança

2. **Codificação e Auditoria**
   - Obtém códigos LOINC dos exames realizados
   - Mapeia para códigos TUSS para faturamento
   - Valida coerência entre procedimentos e diagnósticos

3. **Geração de Guia TISS**
   - Inclui exames laboratoriais realizados
   - Anexa resultados quando requerido pela operadora

4. **Análise de Glosa**
   - Verifica se exames glosados foram realmente realizados
   - Fornece evidências (laudos) para recurso

---

## Padrões e Standards

### HL7 FHIR R4 Resources

#### ServiceRequest (Pedido de Exame)
```json
{
  "resourceType": "ServiceRequest",
  "id": "order-12345",
  "status": "active",
  "intent": "order",
  "priority": "routine",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "718-7",
      "display": "Hemoglobin [Mass/volume] in Blood"
    }]
  },
  "subject": {"reference": "Patient/123"},
  "encounter": {"reference": "Encounter/456"},
  "authoredOn": "2024-01-15T08:30:00Z"
}
```

#### DiagnosticReport (Resultado)
```json
{
  "resourceType": "DiagnosticReport",
  "id": "result-67890",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
      "code": "LAB"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "58410-2",
      "display": "Complete blood count (hemogram) panel"
    }]
  },
  "subject": {"reference": "Patient/123"},
  "encounter": {"reference": "Encounter/456"},
  "result": [
    {"reference": "Observation/obs-1"},
    {"reference": "Observation/obs-2"}
  ]
}
```

### LOINC Code Mapping
- **Sistema**: Logical Observation Identifiers Names and Codes
- **URL**: http://loinc.org
- **Uso**: Identificação universal de testes laboratoriais

---

## Operações e Métodos

### 1. getOrdersByEncounter
**Endpoint**: `GET /ServiceRequest?encounter={encounterId}`

**Propósito**: Buscar todos os pedidos laboratoriais de um encontro hospitalar

**Parâmetros**:
- `encounterId`: ID do encontro (atendimento)
- `Authorization`: Bearer token para autenticação

**Retorno**: Lista de LISOrderDTO

**Uso no Ciclo de Receita**:
- Pré-validação: verifica se foram solicitados exames
- Codificação: identifica procedimentos a codificar
- Auditoria: valida coerência clínica

---

### 2. getOrderById
**Endpoint**: `GET /ServiceRequest/{orderId}`

**Propósito**: Obter detalhes específicos de um pedido laboratorial

**Parâmetros**:
- `orderId`: ID do pedido
- `Authorization`: Bearer token

**Retorno**: LISOrderDTO

**Uso no Ciclo de Receita**:
- Investigação de glosas específicas
- Auditoria detalhada de procedimentos

---

### 3. getResultsByOrder
**Endpoint**: `GET /DiagnosticReport?based-on={orderId}`

**Propósito**: Buscar resultados de exames para um pedido específico

**Parâmetros**:
- `orderId`: ID do pedido (ServiceRequest)
- `Authorization`: Bearer token

**Retorno**: Lista de LISResultDTO (DiagnosticReports)

**Uso no Ciclo de Receita**:
- **Faturamento**: Confirma realização do exame
- **Glosa**: Fornece evidência para contestação
- **Auditoria**: Valida necessidade médica

---

### 4. getSpecimensByOrder
**Endpoint**: `GET /Specimen?request={orderId}`

**Propósito**: Obter informações sobre amostras biológicas coletadas

**Parâmetros**:
- `orderId`: ID do pedido
- `Authorization`: Bearer token

**Retorno**: Lista de LISSpecimenDTO

**Uso no Ciclo de Receita**:
- Rastreabilidade: confirma coleta de material
- Auditoria: valida procedimentos de coleta cobrados
- Qualidade: verifica adequação da amostra

---

### 5. getOrdersByPatient
**Endpoint**: `GET /ServiceRequest?patient={patientId}`

**Propósito**: Buscar histórico de exames de um paciente

**Parâmetros**:
- `patientId`: ID do paciente
- `Authorization`: Bearer token

**Retorno**: Lista de LISOrderDTO

**Uso no Ciclo de Receita**:
- Análise de padrões de utilização
- Detecção de exames duplicados
- Validação de cobertura contratual

---

### 6. updateOrderStatus
**Endpoint**: `PATCH /ServiceRequest/{orderId}?status={status}`

**Propósito**: Atualizar status de um pedido

**Parâmetros**:
- `orderId`: ID do pedido
- `status`: Novo status (active, completed, cancelled)
- `Authorization`: Bearer token

**Retorno**: LISOrderDTO atualizado

**Uso no Ciclo de Receita**:
- Cancelamento de exames não autorizados
- Sincronização de status para faturamento

---

### 7. areResultsComplete
**Endpoint**: `GET /DiagnosticReport/encounter/{encounterId}/complete`

**Propósito**: Verificar se todos os resultados de um encontro estão finalizados

**Parâmetros**:
- `encounterId`: ID do encontro
- `Authorization`: Bearer token

**Retorno**: Boolean (true se todos os resultados são finais)

**Uso no Ciclo de Receita**:
- **Gate para Faturamento**: Bloqueia geração de guia se resultados pendentes
- **Qualidade**: Garante completude antes do faturamento
- **SLA**: Monitora tempo de liberação de resultados

---

## Regras de Negócio Implementadas

### RN-LIS-01: Validação de Completude de Resultados
**Descrição**: Antes de gerar guia TISS, todos os resultados laboratoriais devem estar em status "final".

**Implementação**:
```java
boolean allFinal = lisClient.areResultsComplete(encounterId, apiKey);
if (!allFinal) {
    throw new ValidationException("Resultados laboratoriais pendentes");
}
```

**Impacto**:
- Previne faturamento prematuro
- Evita glosas por documentação incompleta
- Melhora qualidade da cobrança

---

### RN-LIS-02: Mapeamento LOINC → TUSS
**Descrição**: Códigos LOINC dos exames devem ser mapeados para códigos TUSS da CBHPM/TISS para faturamento.

**Fluxo**:
1. Obter código LOINC do ServiceRequest
2. Consultar tabela de mapeamento LOINC → TUSS
3. Validar se código TUSS está no contrato
4. Incluir na guia TISS

**Exemplo**:
```
LOINC: 718-7 (Hemoglobin)
  → TUSS: 40304388 (Hemoglobina)
  → Valor Contratual: R$ 2,50
```

---

### RN-LIS-03: Validação de Autorização Prévia
**Descrição**: Exames de alto custo requerem autorização prévia da operadora.

**Implementação**:
```java
if (isHighCostTest(testCode)) {
    if (!hasPreAuthorization(patientId, testCode)) {
        updateOrderStatus(orderId, "cancelled", apiKey);
        notifyDenial("Exame não autorizado pela operadora");
    }
}
```

**Exames Típicos**:
- Exames genéticos
- Painéis moleculares
- Testes de alto custo (> R$ 500)

---

### RN-LIS-04: Prazo de Disponibilidade
**Descrição**: Resultados devem estar disponíveis em prazos definidos por SLA.

**SLA Padrão**:
- Exames urgentes: 4 horas
- Exames de rotina: 24 horas
- Culturas: 48-72 horas

**Impacto no Faturamento**:
- Resultados atrasados podem gerar glosa por "serviço não prestado"
- Monitoramento via `areResultsComplete()`

---

## Tratamento de Erros e Exceções

### Códigos de Status HTTP

| Status | Significado | Ação Recomendada |
|--------|-------------|------------------|
| 200 | OK | Processar resposta |
| 401 | Unauthorized | Renovar token API |
| 404 | Not Found | Verificar se pedido existe no LIS |
| 500 | Server Error | Retry com backoff exponencial |
| 503 | Service Unavailable | LIS indisponível, alertar equipe |

### Tratamento de Dados Ausentes

```java
try {
    List<LISResultDTO> results = lisClient.getResultsByOrder(orderId, apiKey);
    if (results.isEmpty()) {
        log.warn("Nenhum resultado encontrado para pedido {}", orderId);
        // Não bloqueia faturamento se pedido foi cancelado
    }
} catch (FeignException.NotFound e) {
    log.error("Pedido {} não existe no LIS", orderId);
    // Pode indicar inconsistência de dados
}
```

---

## Segurança e Autenticação

### Método de Autenticação
- **Tipo**: Bearer Token (JWT)
- **Header**: `Authorization: Bearer {token}`
- **Configuração**: `lis.api-key` em application.yml

### LGPD e Privacidade
- **Dados Sensíveis**: Resultados de exames são dados de saúde protegidos
- **Controle de Acesso**: Apenas usuários autorizados podem consultar
- **Auditoria**: Todas as requisições devem ser logadas
- **Retenção**: Seguir políticas de retenção de dados do hospital

### Configuração Segura

```yaml
lis:
  base-url: https://lis-api.hospital.com/fhir/R4
  api-key: ${LIS_API_KEY} # Variável de ambiente
  timeout: 30s
  retry:
    max-attempts: 3
    backoff: exponential
```

---

## Dependências e Integrações

### Sistemas Upstream (Fornecem dados ao LIS)
- **HIS/EMR**: Pedidos médicos originais
- **Coleta**: Sistema de coleta de amostras
- **Analisadores**: Equipamentos laboratoriais automatizados

### Sistemas Downstream (Consomem dados do LIS)
1. **Billing Service**: Usa resultados para faturamento
2. **Clinical Audit**: Valida coerência clínica
3. **Quality Management**: Monitora prazos e qualidade

### Dependências Spring
```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
```

---

## Métricas e Monitoramento

### KPIs Recomendados

1. **Tempo de Resposta**: Latência das chamadas API
   - Meta: < 2 segundos (p95)

2. **Taxa de Sucesso**: % de chamadas bem-sucedidas
   - Meta: > 99.5%

3. **Completude de Resultados**: % de encontros com todos os resultados finais
   - Meta: > 95% em 24h após coleta

4. **Taxa de Mapeamento LOINC→TUSS**: % de exames mapeados
   - Meta: 100% para exames cobertos

### Alertas Críticos
- API LIS indisponível por > 5 minutos
- Taxa de erro > 5% em 10 minutos
- Resultados pendentes > 48 horas

---

## Exemplos de Uso

### Exemplo 1: Pré-Validação de Prontuário
```java
@Service
public class PreValidationService {

    @Autowired
    private LISClient lisClient;

    public void validateLabTests(String encounterId) {
        // 1. Buscar pedidos laboratoriais
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(
            encounterId,
            getApiKey()
        );

        if (orders.isEmpty()) {
            // Nenhum exame laboratorial solicitado
            return;
        }

        // 2. Verificar se todos os resultados estão prontos
        boolean allComplete = lisClient.areResultsComplete(encounterId, getApiKey());

        if (!allComplete) {
            throw new ValidationException(
                "Aguardando resultados laboratoriais para faturamento"
            );
        }

        // 3. Validar cada resultado
        for (LISOrderDTO order : orders) {
            List<LISResultDTO> results = lisClient.getResultsByOrder(
                order.getId(),
                getApiKey()
            );

            for (LISResultDTO result : results) {
                if (!"final".equals(result.getStatus())) {
                    throw new ValidationException(
                        "Resultado " + result.getId() + " não está finalizado"
                    );
                }
            }
        }
    }
}
```

### Exemplo 2: Mapeamento para Guia TISS
```java
@Service
public class BillingService {

    @Autowired
    private LISClient lisClient;

    @Autowired
    private CodeMappingService codeMapping;

    public List<GuiaItem> mapLabTestsToBilling(String encounterId) {
        List<GuiaItem> items = new ArrayList<>();

        // 1. Obter pedidos laboratoriais
        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(
            encounterId,
            getApiKey()
        );

        for (LISOrderDTO order : orders) {
            // 2. Obter resultados para confirmar realização
            List<LISResultDTO> results = lisClient.getResultsByOrder(
                order.getId(),
                getApiKey()
            );

            if (results.isEmpty()) {
                // Exame não realizado, não cobrar
                continue;
            }

            // 3. Mapear LOINC → TUSS
            for (String loincCode : order.getTestCodes()) {
                String tissCode = codeMapping.loincToTuss(loincCode);

                if (tissCode != null) {
                    GuiaItem item = new GuiaItem();
                    item.setCodigoTUSS(tissCode);
                    item.setQuantidade(1);
                    item.setDataRealizacao(order.getOccurrenceDateTime());

                    // Anexar resultado se necessário
                    LISResultDTO result = results.get(0);
                    if (result.getPresentedFormUrls() != null) {
                        item.setAnexoLaudo(result.getPresentedFormUrls().get(0));
                    }

                    items.add(item);
                }
            }
        }

        return items;
    }
}
```

### Exemplo 3: Recurso de Glosa
```java
@Service
public class GlosaService {

    @Autowired
    private LISClient lisClient;

    public RecursoDTO buildGlosaAppeal(String glosaId, String orderId) {
        RecursoDTO recurso = new RecursoDTO();

        // 1. Obter detalhes do pedido
        LISOrderDTO order = lisClient.getOrderById(orderId, getApiKey());
        recurso.setPedidoMedico(order);

        // 2. Obter resultados como evidência
        List<LISResultDTO> results = lisClient.getResultsByOrder(
            orderId,
            getApiKey()
        );

        // 3. Anexar laudos
        List<String> anexos = new ArrayList<>();
        for (LISResultDTO result : results) {
            if (result.getPresentedFormUrls() != null) {
                anexos.addAll(result.getPresentedFormUrls());
            }
        }
        recurso.setAnexos(anexos);

        // 4. Buscar amostras para comprovar coleta
        List<LISSpecimenDTO> specimens = lisClient.getSpecimensByOrder(
            orderId,
            getApiKey()
        );
        recurso.setEvidenciaColeta(specimens);

        return recurso;
    }
}
```

---

## Conformidade Regulatória

### HL7 FHIR R4
- **Perfil**: US Core / Brazilian Core (BR-Core)
- **Validação**: Recursos devem passar em validadores FHIR
- **Extensões**: Suporte a extensões brasileiras (CNS, CPF)

### TISS (Troca de Informações na Saúde Suplementar)
- **Mapeamento**: LOINC codes mapeados para TUSS/CBHPM
- **Anexos**: Laudos podem ser anexados em guias TISS quando necessário

### LGPD
- **Minimização**: Buscar apenas dados necessários
- **Consentimento**: Paciente deve consentir acesso a resultados
- **Rastreabilidade**: Logs de acesso para auditoria

---

## Manutenção e Evolução

### Versionamento da API LIS
- **Atual**: FHIR R4
- **Estratégia**: Suportar múltiplas versões com content negotiation
- **Deprecação**: 6 meses de aviso antes de remover versão

### Expansões Futuras
1. **Suporte a HL7 v2**: Integração com LIS legados
2. **DICOM SR**: Laudos estruturados de patologia
3. **Genomics Reporting**: Resultados de testes genéticos (FHIR Genomics IG)

### Testes de Integração
```java
@Test
public void testGetOrdersByEncounter() {
    // Usar WireMock para simular respostas LIS
    stubFor(get(urlPathEqualTo("/ServiceRequest"))
        .withQueryParam("encounter", equalTo("enc-123"))
        .willReturn(aResponse()
            .withStatus(200)
            .withHeader("Content-Type", "application/fhir+json")
            .withBodyFile("lis-orders-response.json")));

    List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(
        "enc-123",
        "Bearer test-token"
    );

    assertNotNull(orders);
    assertFalse(orders.isEmpty());
}
```

---

## Referências Técnicas

1. **HL7 FHIR R4 Specification**: http://hl7.org/fhir/R4/
2. **LOINC Database**: https://loinc.org/
3. **TUSS (Terminologia Unificada da Saúde Suplementar)**: ANS
4. **Spring Cloud OpenFeign**: https://spring.io/projects/spring-cloud-openfeign
5. **FHIR ServiceRequest**: http://hl7.org/fhir/R4/servicerequest.html
6. **FHIR DiagnosticReport**: http://hl7.org/fhir/R4/diagnosticreport.html
7. **FHIR Specimen**: http://hl7.org/fhir/R4/specimen.html

---

## Glossário

- **LIS**: Laboratory Information System - Sistema de Informação Laboratorial
- **LOINC**: Logical Observation Identifiers Names and Codes - Código universal de observações clínicas e laboratoriais
- **FHIR**: Fast Healthcare Interoperability Resources - Padrão de interoperabilidade HL7
- **ServiceRequest**: Recurso FHIR para pedidos de serviço (exames, procedimentos)
- **DiagnosticReport**: Recurso FHIR para relatórios diagnósticos
- **Specimen**: Recurso FHIR para amostras biológicas
- **TUSS**: Terminologia Unificada da Saúde Suplementar (códigos ANS)
- **CBHPM**: Classificação Brasileira Hierarquizada de Procedimentos Médicos

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
