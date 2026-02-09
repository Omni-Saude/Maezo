# RN-TissSubmissionClient - Cliente de Submissão TISS

## Identificação
- **Nome da Classe**: `TissSubmissionClient`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Cliente de Integração com Resiliência
- **Padrão TISS**: 4.0/4.01/4.03.03

## Objetivo
Cliente robusto para submissão de guias TISS às operadoras de saúde, implementando padrões de resiliência (circuit breaker, retry, DLQ) para garantir confiabilidade em ambientes de produção.

## Contexto de Negócio
Submissão de guias TISS é uma operação **crítica** que impacta diretamente o faturamento hospitalar. Este cliente garante:
- **Resiliência**: Recuperação automática de falhas
- **Rastreabilidade**: Logs completos de todas as operações
- **Conformidade**: Validação antes da submissão
- **Auditoria**: Dead Letter Queue para falhas

## Arquitetura de Resiliência

### Padrões Implementados
1. **Circuit Breaker**: Proteção contra falhas em cascata
2. **Retry Handler**: Tentativas automáticas de reenvio
3. **DLQ (Dead Letter Queue)**: Fila de mensagens com falha
4. **Validação Prévia**: Evita submissões inválidas

---

## Regras de Negócio

### RN-TISS-SUB-001: Submissão de Guia TISS
**Descrição**: Submete uma guia TISS validada para a operadora com padrões de resiliência.

**Entradas**:
- `guia`: Objeto TissGuiaDTO completo

**Processamento**:
```
1. Gerar XML da guia (via TissXmlGenerator)
2. Validar XML contra schema TISS
3. SE inválido ENTÃO
     LANÇAR IllegalArgumentException
4. Executar Circuit Breaker:
   4.1. Executar Retry Handler:
        4.1.1. Realizar submissão HTTP
        4.1.2. SE falha ENTÃO retry (até max tentativas)
   4.2. SE circuit aberto ENTÃO falha rápida
5. SE sucesso ENTÃO
     RETORNAR TissSubmissionResponse com protocolo
6. SE falha ENTÃO
     6.1. Adicionar guia à DLQ
     6.2. Logar erro completo
     6.3. LANÇAR exceção
```

**Saídas**:
- `TissSubmissionResponse`:
  - `success`: Indicador de sucesso
  - `protocolNumber`: Número de protocolo da operadora
  - `submissionDate`: Data/hora da submissão
  - `message`: Mensagem de retorno

**Configurações**:
- `tiss.submission.url`: URL do endpoint da operadora
- `tiss.api.key`: Chave de autenticação (opcional)

**Resiliência**:
- **Circuit Name**: "tiss-submission"
- **Retry Strategy**: "tiss-submit-guia"
- **DLQ Queue**: "tiss"

**Regulamentação**: ANS RN 305/2012

---

### RN-TISS-SUB-002: Validação Pré-Submissão
**Descrição**: Valida o XML gerado antes de submeter à operadora.

**Entradas**:
- `xml`: String XML gerado

**Processamento**:
1. Executar `xmlGenerator.validateXml(xml)`
2. SE inválido ENTÃO lançar IllegalArgumentException

**Objetivo**: Evitar tráfego de rede e consumo de recursos com XMLs inválidos.

**Economia**: Reduz custos de API e previne glosas por formatação incorreta.

---

### RN-TISS-SUB-003: Submissão HTTP
**Descrição**: Realiza a submissão HTTP propriamente dita para a operadora.

**Entradas**:
- `xml`: XML validado
- `guiaNumber`: Número da guia (para logging)

**Processamento**:
```
1. Criar headers HTTP:
   - Content-Type: application/xml
   - Accept: application/json
   - X-API-Key: ${tissApiKey} (se configurado)

2. Criar HttpEntity com XML e headers

3. Executar POST para ${tissSubmissionUrl}

4. SE response 2xx E body não nulo ENTÃO
     4.1. Extrair protocolNumber, submissionDate, message
     4.2. RETORNAR TissSubmissionResponse(success=true)
   SENÃO
     4.3. LANÇAR TissSubmissionException
```

**Saídas**:
- `TissSubmissionResponse` em caso de sucesso
- `TissSubmissionException` em caso de falha

**Formato de Resposta Esperado** (JSON):
```json
{
  "protocolNumber": "2024010123456",
  "submissionDate": "2024-01-01T10:30:00Z",
  "message": "Guia recebida com sucesso"
}
```

---

### RN-TISS-SUB-004: Consulta de Status de Submissão
**Descrição**: Verifica o status de processamento de uma guia já submetida.

**Entradas**:
- `protocolNumber`: Número de protocolo retornado na submissão

**Processamento**:
```
1. Executar Circuit Breaker:
   1.1. Executar Retry Handler:
        1.1.1. Criar headers com X-API-Key (se configurado)
        1.1.2. GET ${tissSubmissionUrl}/{protocolNumber}
        1.1.3. Extrair status, processedDate
        1.1.4. RETORNAR TissSubmissionStatus

2. SE falha ENTÃO
     2.1. Logar erro
     2.2. LANÇAR exceção
```

**Saídas**:
- `TissSubmissionStatus`:
  - `protocolNumber`: Número de protocolo
  - `status`: Status atual (RECEIVED, PROCESSING, APPROVED, DENIED)
  - `processedDate`: Data de processamento

**Status Possíveis**:
- `RECEIVED`: Recebida pela operadora
- `PROCESSING`: Em processamento
- `APPROVED`: Aprovada (pagamento autorizado)
- `DENIED`: Negada (glosa)
- `PARTIAL`: Parcialmente aprovada

---

## Padrões de Resiliência Implementados

### Circuit Breaker Coordinator
**Objetivo**: Prevenir sobrecarga em sistemas instáveis.

**Funcionamento**:
```
CLOSED (Normal):
  - Requisições passam normalmente
  - SE taxa de erro > limite ENTÃO transição para OPEN

OPEN (Falha):
  - Requisições falham imediatamente (fail-fast)
  - Após timeout, transição para HALF_OPEN

HALF_OPEN (Teste):
  - Permite 1 requisição de teste
  - SE sucesso ENTÃO CLOSED
  - SE falha ENTÃO OPEN
```

**Configuração**:
- Circuit Name: "tiss-submission"
- Threshold: 50% de erros
- Timeout: 60 segundos

---

### Retry Handler
**Objetivo**: Recuperar automaticamente de falhas transitórias.

**Funcionamento**:
```
1. Executar operação
2. SE falha transitória (timeout, 5xx) ENTÃO
     2.1. Aguardar backoff exponencial
     2.2. Tentar novamente (até max retries)
3. SE falha permanente (4xx) ENTÃO
     3.1. Falhar imediatamente
```

**Configuração**:
- Strategy Name: "tiss-submit-guia", "tiss-check-status"
- Max Retries: 3
- Backoff: 1s, 2s, 4s (exponencial)

**Falhas Transitórias**:
- Network timeout
- HTTP 502, 503, 504
- Connection refused

**Falhas Permanentes**:
- HTTP 400, 401, 403
- XML validation error

---

### DLQ (Dead Letter Queue)
**Objetivo**: Preservar mensagens que falharam para análise e reprocessamento.

**Funcionamento**:
```
QUANDO falha ENTÃO
  1. Serializar guia completa
  2. Adicionar erro e stacktrace
  3. Adicionar timestamp
  4. Gravar em queue "tiss"
  5. Notificar equipe de suporte
```

**Uso da DLQ**:
- Análise de padrões de falha
- Reprocessamento manual
- Auditoria de problemas
- Identificação de bugs

---

## Integrações

### Dependências Internas
1. **TissXmlGenerator**: Geração de XML
2. **RetryHandler**: Estratégia de retry
3. **CircuitBreakerCoordinator**: Proteção de circuito
4. **IntegrationDlqHandler**: Fila de falhas

### Dependências Externas
1. **RestTemplate**: Cliente HTTP
2. **Spring Configuration**: Injeção de propriedades

---

## Configuração

### application.yml
```yaml
tiss:
  submission:
    url: https://operadora.com.br/api/tiss/submit
  api:
    key: ${TISS_API_KEY:}  # Variável de ambiente

circuit-breaker:
  tiss-submission:
    failure-threshold: 50%
    timeout: 60s
    half-open-requests: 1

retry:
  tiss-submit-guia:
    max-attempts: 3
    backoff: exponential
    initial-interval: 1000ms
```

---

## DTOs Internos

### TissSubmissionResponse
**Objetivo**: Resposta de submissão bem-sucedida.

**Campos**:
- `success` (boolean): Indicador de sucesso
- `protocolNumber` (String): Número de protocolo da operadora
- `submissionDate` (String): Data/hora de submissão
- `message` (String): Mensagem de retorno

**Builder**: Lombok @Builder para construção fluente

---

### TissSubmissionStatus
**Objetivo**: Status de processamento de guia.

**Campos**:
- `protocolNumber` (String): Número de protocolo
- `status` (String): Status atual
- `processedDate` (String): Data de processamento

**Builder**: Lombok @Builder

---

### TissSubmissionException
**Objetivo**: Exceção customizada para erros de submissão.

**Hierarquia**: RuntimeException

**Uso**: Lançada quando submissão falha definitivamente.

---

## Segurança

### Autenticação
- **API Key**: Header X-API-Key (configurável)
- **Certificado Digital**: A ser implementado (ICP-Brasil)

### Criptografia
- **TLS 1.2+**: Obrigatório para comunicação
- **XML Signature**: A ser implementado (assinatura digital)

### Auditoria
- **Logs Completos**: Todas as operações são logadas
- **DLQ**: Preserva evidências de falhas
- **Protocolo**: Rastreabilidade completa

---

## Monitoramento

### Métricas Importantes
1. **Taxa de Sucesso**: % de submissões bem-sucedidas
2. **Circuit Breaker State**: Estado atual do circuit breaker
3. **DLQ Size**: Tamanho da fila de falhas
4. **Retry Rate**: Taxa de retentativas
5. **Average Response Time**: Tempo médio de resposta

### Alertas Recomendados
- Circuit breaker OPEN
- DLQ size > 100
- Taxa de sucesso < 95%
- Response time > 10s

---

## Tratamento de Erros

### Cenários de Erro

#### 1. Erro de Validação XML
**Causa**: XML gerado não conforme com schema TISS

**Ação**:
- Logar erro detalhado
- NÃO adicionar à DLQ (erro de código)
- Lançar IllegalArgumentException

**Correção**: Corrigir TissXmlGenerator

---

#### 2. Erro de Rede
**Causa**: Timeout, connection refused

**Ação**:
- Retry automático (até 3 vezes)
- SE todas falharem, adicionar à DLQ
- Logar erro

**Correção**: Verificar conectividade

---

#### 3. Erro HTTP 4xx
**Causa**: Autenticação, formato incorreto

**Ação**:
- NÃO fazer retry (erro permanente)
- Adicionar à DLQ
- Logar erro detalhado

**Correção**: Verificar API key, revisar formato

---

#### 4. Erro HTTP 5xx
**Causa**: Falha no servidor da operadora

**Ação**:
- Retry automático
- Circuit breaker pode abrir
- Adicionar à DLQ se falhar

**Correção**: Aguardar recuperação da operadora

---

## Performance

### Otimizações
1. **Connection Pooling**: RestTemplate com pool configurado
2. **Timeouts**: Read timeout de 30s, connect timeout de 10s
3. **Async**: Considerar submissão assíncrona para lotes

### Benchmarks Esperados
- **Submissão Individual**: < 5s
- **Taxa de Sucesso**: > 95%
- **Circuit Breaker**: < 1% do tempo em OPEN

---

## Próximos Passos

### Fase 1: Certificação Digital
- [ ] Implementar assinatura XML com certificado A3
- [ ] Adicionar timestamp no XML
- [ ] Validar cadeia de certificados

### Fase 2: Lote
- [ ] Implementar submissão de lote de guias
- [ ] Otimizar com processamento paralelo
- [ ] Rate limiting para respeitar limites da operadora

### Fase 3: Múltiplas Operadoras
- [ ] Implementar adaptadores por operadora
- [ ] Configuração dinâmica de endpoints
- [ ] Estratégias de retry customizadas

### Fase 4: Observabilidade
- [ ] Integrar com Prometheus/Grafana
- [ ] Dashboard de monitoramento
- [ ] Alertas automáticos

---

## Referências Técnicas

### Padrões de Resiliência
- **Livro**: "Release It!" - Michael T. Nygard
- **Pattern**: Circuit Breaker (Martin Fowler)
- **Pattern**: Retry with Exponential Backoff

### ANS
- **RN 305/2012**: Padrão TISS
- **Manual TISS 4.0**: Componente de Comunicação

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissSubmissionClient.java`
