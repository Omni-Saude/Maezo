# RN-SchedulingClientConfig - Configuração do Cliente de Agendamento

**Categoria**: Configuração
**Prioridade**: Alta
**Status**: Implementado
**Versão**: 1.0.0

---

## 1. VISÃO GERAL

### 1.1 Propósito
Classe de configuração Spring para o `SchedulingClient` Feign, responsável por:
- Interceptação de requisições HTTP
- Injeção automática de headers FHIR
- Autenticação via Bearer Token
- Configuração de formato de dados (FHIR JSON)

### 1.2 Localização
```
Arquivo: src/main/java/com/hospital/revenuecycle/integration/scheduling/SchedulingClientConfig.java
Pacote: com.hospital.revenuecycle.integration.scheduling
```

---

## 2. ESPECIFICAÇÃO TÉCNICA

### 2.1 Código
```java
package com.hospital.revenuecycle.integration.scheduling;

import feign.RequestInterceptor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SchedulingClientConfig {

    @Value("${scheduling.api-key}")
    private String schedulingApiKey;

    @Bean
    public RequestInterceptor schedulingRequestInterceptor() {
        return requestTemplate -> {
            requestTemplate.header("Authorization", "Bearer " + schedulingApiKey);
            requestTemplate.header("Accept", "application/fhir+json");
            requestTemplate.header("Content-Type", "application/fhir+json");
        };
    }
}
```

---

## 3. REGRAS DE NEGÓCIO

### RN-SCHED-CFG-001: Interceptação de Requisições
**Descrição**: Intercepta todas as requisições do SchedulingClient
**Objetivo**: Adicionar headers obrigatórios automaticamente

**Headers Injetados**:
1. **Authorization**: `Bearer {api-key}`
   - Autenticação no sistema de agendamento
   - Token carregado de `scheduling.api-key`

2. **Accept**: `application/fhir+json`
   - Indica que o cliente aceita respostas em formato FHIR JSON
   - Padrão HL7 FHIR R4

3. **Content-Type**: `application/fhir+json`
   - Define formato do payload enviado
   - Necessário para POST/PATCH de recursos FHIR

---

### RN-SCHED-CFG-002: Gerenciamento de API Key
**Descrição**: Carrega API key de configuração externa
**Fonte**: `application.yml` ou variável de ambiente

**Configuração**:
```yaml
# application.yml
scheduling:
  api-key: ${SCHEDULING_API_KEY:default-key-for-dev}
  base-url: https://scheduling-api.hospital.com/fhir/R4
```

**Validações**:
- API key não pode ser nula ou vazia
- Deve ser carregada de fonte segura (não hardcoded)
- Suporte a diferentes ambientes (dev, staging, prod)

---

### RN-SCHED-CFG-003: Formato FHIR JSON
**Descrição**: Garante comunicação no formato FHIR JSON
**Padrão**: HL7 FHIR R4

**Características**:
- Serialização/deserialização de recursos FHIR
- Suporte a extensões FHIR
- Validação de estrutura conforme perfil FHIR

**Exemplo de Payload FHIR JSON**:
```json
{
  "resourceType": "Appointment",
  "id": "12345",
  "status": "booked",
  "start": "2026-01-15T09:00:00Z",
  "end": "2026-01-15T09:30:00Z",
  "participant": [
    {
      "actor": {
        "reference": "Patient/67890",
        "display": "João Silva"
      },
      "status": "accepted"
    }
  ]
}
```

---

## 4. CONFIGURAÇÃO POR AMBIENTE

### 4.1 Desenvolvimento
```yaml
scheduling:
  api-key: dev-api-key-12345
  base-url: https://dev-scheduling.hospital.com/fhir/R4
  timeout:
    connect: 10000
    read: 15000
```

### 4.2 Staging
```yaml
scheduling:
  api-key: ${SCHEDULING_API_KEY}  # Vault/Secret Manager
  base-url: https://staging-scheduling.hospital.com/fhir/R4
  timeout:
    connect: 5000
    read: 10000
```

### 4.3 Produção
```yaml
scheduling:
  api-key: ${SCHEDULING_API_KEY}  # Vault/Secret Manager
  base-url: https://scheduling-api.hospital.com/fhir/R4
  timeout:
    connect: 3000
    read: 8000
  retry:
    max-attempts: 3
    backoff: 1000
```

---

## 5. SEGURANÇA

### 5.1 Proteção de API Key
**Práticas Recomendadas**:
- ❌ **NUNCA** hardcode a API key no código
- ✅ Usar variáveis de ambiente
- ✅ Integrar com Secret Manager (AWS Secrets Manager, Azure Key Vault)
- ✅ Rotacionar periodicamente
- ✅ Monitorar uso e detectar anomalias

### 5.2 Exemplo com AWS Secrets Manager
```java
@Configuration
public class SchedulingClientConfig {

    @Autowired
    private SecretsManagerClient secretsManager;

    @Bean
    public RequestInterceptor schedulingRequestInterceptor() {
        String apiKey = getSecretValue("scheduling/api-key");

        return requestTemplate -> {
            requestTemplate.header("Authorization", "Bearer " + apiKey);
            requestTemplate.header("Accept", "application/fhir+json");
            requestTemplate.header("Content-Type", "application/fhir+json");
        };
    }

    private String getSecretValue(String secretName) {
        GetSecretValueRequest request = GetSecretValueRequest.builder()
            .secretId(secretName)
            .build();
        GetSecretValueResponse response = secretsManager.getSecretValue(request);
        return response.secretString();
    }
}
```

---

## 6. INTERCEPTAÇÃO AVANÇADA

### 6.1 Logging de Requisições
```java
@Bean
public RequestInterceptor schedulingRequestInterceptor() {
    return requestTemplate -> {
        // Headers obrigatórios
        requestTemplate.header("Authorization", "Bearer " + schedulingApiKey);
        requestTemplate.header("Accept", "application/fhir+json");
        requestTemplate.header("Content-Type", "application/fhir+json");

        // Headers adicionais
        requestTemplate.header("X-Request-ID", UUID.randomUUID().toString());
        requestTemplate.header("X-Client-Version", "1.0.0");

        // Log
        log.debug("Scheduling request: {} {}",
            requestTemplate.method(),
            requestTemplate.url()
        );
    };
}
```

### 6.2 Tratamento de Erros
```java
@Bean
public ErrorDecoder schedulingErrorDecoder() {
    return (methodKey, response) -> {
        if (response.status() == 401) {
            log.error("Unauthorized: Invalid API key for scheduling system");
            return new UnauthorizedException("Invalid API key");
        }
        if (response.status() == 404) {
            log.warn("Resource not found in scheduling system");
            return new ResourceNotFoundException("Appointment not found");
        }
        return new FeignException.FeignServerException(
            response.status(),
            "Scheduling API error",
            response.request(),
            response.body()
        );
    };
}
```

---

## 7. TIMEOUTS E RETRY

### 7.1 Configuração de Timeouts
```yaml
feign:
  client:
    config:
      scheduling-client:
        connectTimeout: 5000  # 5 segundos
        readTimeout: 10000    # 10 segundos
        loggerLevel: BASIC
```

### 7.2 Política de Retry
```java
@Bean
public Retryer schedulingRetryer() {
    return new Retryer.Default(
        1000L,  // período inicial
        5000L,  // período máximo
        3       // máximo de tentativas
    );
}
```

---

## 8. MONITORAMENTO

### 8.1 Métricas
```java
@Bean
public MeterRegistry schedulingMetrics() {
    return new SimpleMeterRegistry();
}

@Around("execution(* com.hospital.revenuecycle.integration.scheduling.SchedulingClient.*(..))")
public Object monitorSchedulingCalls(ProceedingJoinPoint joinPoint) throws Throwable {
    Timer.Sample sample = Timer.start(meterRegistry);
    try {
        Object result = joinPoint.proceed();
        sample.stop(Timer.builder("scheduling.api.call")
            .tag("method", joinPoint.getSignature().getName())
            .tag("status", "success")
            .register(meterRegistry));
        return result;
    } catch (Exception e) {
        sample.stop(Timer.builder("scheduling.api.call")
            .tag("method", joinPoint.getSignature().getName())
            .tag("status", "error")
            .register(meterRegistry));
        throw e;
    }
}
```

---

## 9. TESTES

### 9.1 Teste de Configuração
```java
@SpringBootTest
public class SchedulingClientConfigTest {

    @Autowired
    private RequestInterceptor schedulingRequestInterceptor;

    @Test
    public void testInterceptorAddsHeaders() {
        RequestTemplate template = new RequestTemplate();
        schedulingRequestInterceptor.apply(template);

        assertTrue(template.headers().containsKey("Authorization"));
        assertTrue(template.headers().containsKey("Accept"));
        assertTrue(template.headers().containsKey("Content-Type"));

        assertEquals("application/fhir+json",
            template.headers().get("Accept").iterator().next());
    }
}
```

### 9.2 Teste de API Key
```java
@Test
public void testApiKeyLoaded() {
    assertNotNull(schedulingApiKey);
    assertFalse(schedulingApiKey.isEmpty());
    assertTrue(schedulingApiKey.startsWith("Bearer ")
        || !schedulingApiKey.equals("default-key-for-dev"));
}
```

---

## 10. TROUBLESHOOTING

### 10.1 Problemas Comuns

**Erro 401 Unauthorized**:
- Verificar se API key está correta
- Validar formato do header Authorization
- Confirmar que token não expirou

**Erro 415 Unsupported Media Type**:
- Verificar header `Content-Type: application/fhir+json`
- Validar formato do payload FHIR

**Timeout**:
- Aumentar valores de `connectTimeout` e `readTimeout`
- Verificar latência de rede
- Implementar circuit breaker

---

## 11. INTEGRAÇÃO COM OUTROS COMPONENTES

### 11.1 Relacionamento
```
SchedulingClientConfig
  ├── SchedulingClient (aplica interceptor)
  ├── FeignClientConfiguration (base)
  └── SecurityManager (gerencia API keys)
```

### 11.2 Dependências
- Spring Cloud OpenFeign
- Spring Boot Configuration Processor
- Feign Core

---

## 12. REFERÊNCIAS

### 12.1 Documentação
- Spring Cloud OpenFeign: https://spring.io/projects/spring-cloud-openfeign
- HL7 FHIR Media Types: https://hl7.org/fhir/http.html#mime-type

### 12.2 Documentos Relacionados
- `RN-SchedulingClient.md`: Cliente principal
- `RN-AppointmentDTO.md`: Estrutura de dados
- Security Guidelines: Práticas de segurança

---

**Última Atualização**: 2026-01-12
**Responsável**: Equipe de Integração
**Revisores**: Arquitetura, Segurança
