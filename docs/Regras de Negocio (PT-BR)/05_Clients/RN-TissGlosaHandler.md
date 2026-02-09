# RN-TissGlosaHandler - Gerenciador de Glosas TISS

## Identificação
- **Nome da Classe**: `TissGlosaHandler`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Handler/Service de Gestão de Glosas
- **Pattern**: In-Memory Store com ConcurrentHashMap

## Objetivo
Gerenciar o ciclo de vida completo de glosas TISS, desde o registro até a resolução, fornecendo rastreabilidade, análise estatística e suporte ao processo de recursos/contestações.

## Contexto de Negócio
Gestão eficaz de glosas é **crítica** para a saúde financeira hospitalar:
- **Impacto Financeiro**: Glosas representam 5-15% do faturamento
- **Recuperação**: 40-70% das glosas podem ser revertidas com gestão adequada
- **Compliance**: Rastreabilidade é obrigatória para auditorias
- **Melhoria Contínua**: Análise de padrões previne glosas futuras

---

## Atributos

### glosaStore
**Tipo**: `Map<String, TissGlosaDTO>`

**Implementação**: `ConcurrentHashMap<>()`

**Descrição**: Armazenamento principal de glosas indexado por numeroProtocolo.

**Thread-Safety**: Sim (ConcurrentHashMap é thread-safe)

**Uso**: Acesso rápido O(1) a qualquer glosa por protocolo.

---

### guiaGlosaIndex
**Tipo**: `Map<String, List<String>>`

**Implementação**: `ConcurrentHashMap<>()`

**Descrição**: Índice secundário: numeroGuia → List<numeroProtocolo>

**Thread-Safety**: Sim

**Uso**: Buscar todas as glosas de uma guia específica.

**Estrutura**:
```
{
  "2024010001": ["GLOSA-001", "GLOSA-002"],
  "2024010002": ["GLOSA-003"]
}
```

---

## Regras de Negócio

### RN-GLOSA-HANDLER-001: Registro de Glosa
**Descrição**: Registrar uma nova glosa no sistema e atualizar índices.

**Assinatura**:
```java
public void registerGlosa(TissGlosaDTO glosa)
```

**Entradas**:
- `glosa` (TissGlosaDTO): Glosa completa a registrar

**Processamento**:
```
1. ADICIONAR glosa ao glosaStore:
   glosaStore.put(glosa.getNumeroProtocolo(), glosa)

2. ATUALIZAR índice guiaGlosaIndex:
   2.1. OBTER lista de protocolos da guia (ou criar vazia)
        guiaGlosaIndex.computeIfAbsent(glosa.getNumeroGuia(), k -> new ArrayList<>())
   2.2. ADICIONAR numeroProtocolo à lista
        lista.add(glosa.getNumeroProtocolo())

3. LOGAR warning:
   "Registered TISS glosa for guia {numeroGuia}: {descricao} - R$ {valor}"
```

**Saídas**: Glosa armazenada e indexada

**Complexidade**: O(1) amortizado

**Thread-Safety**: Sim (computeIfAbsent é atômico)

**Log Exemplo**:
```
WARN  - Registered TISS glosa for guia 2024010001: Falta de autorização prévia - R$ 150.00
```

**Uso**:
```java
TissGlosaDTO glosa = TissGlosaDTO.builder()
    .numeroGuia("2024010001")
    .numeroProtocolo("GLOSA-2024-001234")
    .valorGlosado(new BigDecimal("150.00"))
    .descricaoGlosa("Falta de autorização prévia")
    .status("PENDENTE")
    .build();

glosaHandler.registerGlosa(glosa);
```

---

### RN-GLOSA-HANDLER-002: Buscar Glosas por Guia
**Descrição**: Retorna todas as glosas associadas a uma guia específica.

**Assinatura**:
```java
public List<TissGlosaDTO> getGlosasByGuia(String numeroGuia)
```

**Entradas**:
- `numeroGuia` (String): Número da guia

**Processamento**:
```
1. OBTER lista de protocolos do índice:
   protocolos = guiaGlosaIndex.getOrDefault(numeroGuia, Collections.emptyList())

2. CRIAR lista de glosas vazia:
   glosas = new ArrayList<>()

3. PARA CADA protocolo EM protocolos:
   3.1. OBTER glosa do store:
        glosa = glosaStore.get(protocolo)
   3.2. SE glosa != null ENTÃO
        glosas.add(glosa)

4. RETORNAR glosas
```

**Saídas**:
- `List<TissGlosaDTO>`: Lista de glosas (vazia se nenhuma encontrada)

**Complexidade**: O(n) onde n = número de glosas da guia

**Uso**:
```java
List<TissGlosaDTO> glosas = glosaHandler.getGlosasByGuia("2024010001");
for (TissGlosaDTO glosa : glosas) {
    System.out.println("Glosa: " + glosa.getDescricaoGlosa());
}
```

---

### RN-GLOSA-HANDLER-003: Buscar Glosa por Protocolo
**Descrição**: Retorna uma glosa específica pelo número de protocolo.

**Assinatura**:
```java
public TissGlosaDTO getGlosa(String numeroProtocolo)
```

**Entradas**:
- `numeroProtocolo` (String): Número de protocolo da glosa

**Processamento**:
```
1. RETORNAR glosaStore.get(numeroProtocolo)
```

**Saídas**:
- `TissGlosaDTO`: Glosa encontrada ou `null` se não existe

**Complexidade**: O(1)

**Uso**:
```java
TissGlosaDTO glosa = glosaHandler.getGlosa("GLOSA-2024-001234");
if (glosa != null) {
    System.out.println("Valor glosado: " + glosa.getValorGlosado());
}
```

---

### RN-GLOSA-HANDLER-004: Atualizar Status de Glosa
**Descrição**: Atualiza o status de uma glosa (ex: PENDENTE → EM_RECURSO).

**Assinatura**:
```java
public void updateGlosaStatus(String numeroProtocolo, String newStatus)
```

**Entradas**:
- `numeroProtocolo` (String): Número de protocolo da glosa
- `newStatus` (String): Novo status ("PENDENTE", "EM_RECURSO", "ACEITA", "REVERTIDA")

**Processamento**:
```
1. OBTER glosa do store:
   glosa = glosaStore.get(numeroProtocolo)

2. SE glosa != null ENTÃO
   2.1. ATUALIZAR status:
        glosa.setStatus(newStatus)
   2.2. LOGAR info:
        "Updated glosa {protocolo} status to: {status}"
```

**Saídas**: Status atualizado in-place

**Complexidade**: O(1)

**Log Exemplo**:
```
INFO  - Updated glosa GLOSA-2024-001234 status to: EM_RECURSO
```

**Uso**:
```java
// Protocolar recurso
glosaHandler.updateGlosaStatus("GLOSA-2024-001234", "EM_RECURSO");

// Glosa revertida após recurso
glosaHandler.updateGlosaStatus("GLOSA-2024-001234", "REVERTIDA");
```

---

### RN-GLOSA-HANDLER-005: Calcular Total Glosado por Guia
**Descrição**: Soma o valor total glosado de uma guia.

**Assinatura**:
```java
public BigDecimal calculateTotalGlosa(String numeroGuia)
```

**Entradas**:
- `numeroGuia` (String): Número da guia

**Processamento**:
```
1. OBTER todas as glosas da guia:
   glosas = getGlosasByGuia(numeroGuia)

2. CALCULAR soma usando stream:
   total = glosas.stream()
       .map(TissGlosaDTO::getValorGlosado)
       .reduce(BigDecimal.ZERO, BigDecimal::add)

3. RETORNAR total
```

**Saídas**:
- `BigDecimal`: Valor total glosado (0 se nenhuma glosa)

**Complexidade**: O(n) onde n = número de glosas da guia

**Uso**:
```java
BigDecimal totalGlosado = glosaHandler.calculateTotalGlosa("2024010001");
System.out.println("Total glosado da guia: R$ " + totalGlosado);
```

---

### RN-GLOSA-HANDLER-006: Buscar Glosas por Status
**Descrição**: Retorna todas as glosas com um status específico.

**Assinatura**:
```java
public List<TissGlosaDTO> getGlosasByStatus(String status)
```

**Entradas**:
- `status` (String): Status desejado

**Processamento**:
```
1. FILTRAR glosaStore por status:
   glosas = glosaStore.values().stream()
       .filter(glosa -> status.equals(glosa.getStatus()))
       .toList()

2. RETORNAR glosas
```

**Saídas**:
- `List<TissGlosaDTO>`: Lista de glosas com o status (vazia se nenhuma)

**Complexidade**: O(n) onde n = total de glosas

**Uso**:
```java
// Glosas pendentes de análise
List<TissGlosaDTO> pendentes = glosaHandler.getGlosasByStatus("PENDENTE");

// Glosas em recurso
List<TissGlosaDTO> emRecurso = glosaHandler.getGlosasByStatus("EM_RECURSO");

// Glosas revertidas (sucesso!)
List<TissGlosaDTO> revertidas = glosaHandler.getGlosasByStatus("REVERTIDA");
```

---

### RN-GLOSA-HANDLER-007: Estatísticas de Glosas
**Descrição**: Retorna estatísticas agregadas de glosas.

**Assinatura**:
```java
public Map<String, Object> getGlosaStatistics()
```

**Entradas**: Nenhuma

**Processamento**:
```
1. CRIAR mapa de contagem por status:
   statusCounts = new HashMap<>()

2. INICIALIZAR contador de valor total:
   totalGlosado = BigDecimal.ZERO

3. PARA CADA glosa EM glosaStore.values():
   3.1. INCREMENTAR contador do status:
        statusCounts.merge(glosa.getStatus(), 1L, Long::sum)
   3.2. SOMAR valor:
        totalGlosado = totalGlosado.add(glosa.getValorGlosado())

4. RETORNAR Map.of(
     "totalGlosas", glosaStore.size(),
     "totalValorGlosado", totalGlosado,
     "statusCounts", statusCounts
   )
```

**Saídas**:
- `Map<String, Object>`: Estatísticas completas

**Estrutura de Retorno**:
```json
{
  "totalGlosas": 150,
  "totalValorGlosado": 45000.00,
  "statusCounts": {
    "PENDENTE": 50,
    "EM_RECURSO": 30,
    "ACEITA": 40,
    "REVERTIDA": 30
  }
}
```

**Complexidade**: O(n) onde n = total de glosas

**Uso**:
```java
Map<String, Object> stats = glosaHandler.getGlosaStatistics();
System.out.println("Total de glosas: " + stats.get("totalGlosas"));
System.out.println("Valor total glosado: R$ " + stats.get("totalValorGlosado"));

@SuppressWarnings("unchecked")
Map<String, Long> statusCounts = (Map<String, Long>) stats.get("statusCounts");
System.out.println("Pendentes: " + statusCounts.get("PENDENTE"));
```

---

### RN-GLOSA-HANDLER-008: Limpar Glosas Resolvidas
**Descrição**: Remove glosas com status final (ACEITA ou REVERTIDA) do armazenamento.

**Assinatura**:
```java
public void clearResolvedGlosas()
```

**Entradas**: Nenhuma

**Processamento**:
```
1. CRIAR lista de protocolos a remover:
   toRemove = new ArrayList<>()

2. PARA CADA entry EM glosaStore.entrySet():
   2.1. OBTER status da glosa:
        status = entry.getValue().getStatus()
   2.2. SE status == "ACEITA" OU status == "REVERTIDA" ENTÃO
        toRemove.add(entry.getKey())

3. PARA CADA protocolo EM toRemove:
   3.1. glosaStore.remove(protocolo)

4. LOGAR info:
   "Cleared {count} resolved glosas"
```

**Saídas**: Glosas resolvidas removidas

**Complexidade**: O(n) onde n = total de glosas

**Log Exemplo**:
```
INFO  - Cleared 45 resolved glosas
```

**Uso**:
```java
// Executar limpeza mensal
glosaHandler.clearResolvedGlosas();
```

**⚠️ ATENÇÃO**:
- Considerar arquivamento antes de remover
- Manter registros para auditoria
- Implementar backup antes de limpar

---

## KPIs e Métricas

### Taxa de Glosa Instantânea
```java
public double calculateGlosaRate(BigDecimal totalFaturado) {
    BigDecimal totalGlosado = glosaStore.values().stream()
        .map(TissGlosaDTO::getValorGlosado)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

    return totalGlosado.divide(totalFaturado, 4, RoundingMode.HALF_UP)
        .multiply(new BigDecimal("100"))
        .doubleValue();
}
```

---

### Taxa de Reversão
```java
public double calculateReversionRate() {
    long totalRecursos = getGlosasByStatus("EM_RECURSO").size()
                       + getGlosasByStatus("REVERTIDA").size()
                       + getGlosasByStatus("ACEITA").size();

    if (totalRecursos == 0) return 0.0;

    long revertidas = getGlosasByStatus("REVERTIDA").size();

    return (100.0 * revertidas) / totalRecursos;
}
```

---

## Performance e Escalabilidade

### Limitações Atuais
1. **In-Memory**: Dados perdidos em restart
2. **Sem Persistência**: Não sobrevive a falhas
3. **Memória Limitada**: Não escala para milhões de glosas

### Recomendações

#### Fase 1: Persistência
```java
@Entity
@Table(name = "tiss_glosa")
public class TissGlosaEntity {
    @Id
    private String numeroProtocolo;
    // ... demais campos
}

@Repository
public interface TissGlosaRepository extends JpaRepository<TissGlosaEntity, String> {
    List<TissGlosaEntity> findByNumeroGuia(String numeroGuia);
    List<TissGlosaEntity> findByStatus(String status);
}
```

---

#### Fase 2: Cache
```java
@Cacheable("glosas")
public TissGlosaDTO getGlosa(String numeroProtocolo) {
    return glosaRepository.findById(numeroProtocolo).orElse(null);
}

@CacheEvict(value = "glosas", key = "#numeroProtocolo")
public void updateGlosaStatus(String numeroProtocolo, String newStatus) {
    // ...
}
```

---

#### Fase 3: Paginação
```java
public Page<TissGlosaDTO> getGlosasByStatus(String status, Pageable pageable) {
    return glosaRepository.findByStatus(status, pageable);
}
```

---

## Thread-Safety

### Operações Thread-Safe
✅ `registerGlosa()` - ConcurrentHashMap.put() é thread-safe
✅ `getGlosa()` - Leitura é thread-safe
✅ `getGlosasByGuia()` - Leitura com iteração é thread-safe

### Operações com Race Condition Potencial
⚠️ `updateGlosaStatus()` - Múltiplas threads atualizando mesma glosa
⚠️ `clearResolvedGlosas()` - Iteração + remoção pode ter issues

### Sincronização Recomendada
```java
public synchronized void updateGlosaStatus(String numeroProtocolo, String newStatus) {
    TissGlosaDTO glosa = glosaStore.get(numeroProtocolo);
    if (glosa != null) {
        glosa.setStatus(newStatus);
        log.info("Updated glosa {} status to: {}", numeroProtocolo, newStatus);
    }
}
```

---

## Integração com Workflow

### Fluxo Completo de Gestão de Glosa
```java
// 1. Receber glosa da operadora
TissGlosaDTO glosa = parseGlosaFromXml(xml);
glosaHandler.registerGlosa(glosa);

// 2. Análise automática
if (shouldAppeal(glosa)) {
    glosaHandler.updateGlosaStatus(glosa.getNumeroProtocolo(), "EM_RECURSO");
    protocolRecurso(glosa);
} else {
    glosaHandler.updateGlosaStatus(glosa.getNumeroProtocolo(), "ACEITA");
    registrarPerda(glosa);
}

// 3. Resultado do recurso
if (recursoAceito) {
    glosaHandler.updateGlosaStatus(glosa.getNumeroProtocolo(), "REVERTIDA");
    registrarRecuperacao(glosa);
}

// 4. Limpeza periódica (mensal)
glosaHandler.clearResolvedGlosas();
```

---

## Próximos Passos

### Fase 1: Persistência
- [ ] Criar entidade JPA TissGlosaEntity
- [ ] Implementar repository Spring Data
- [ ] Migrar de in-memory para banco

### Fase 2: Auditoria
- [ ] Adicionar campos createdAt, updatedAt
- [ ] Registrar histórico de mudanças de status
- [ ] Implementar versionamento

### Fase 3: Workflow Automatizado
- [ ] Integrar com Camunda BPMN
- [ ] Criar process "Gestão de Glosas"
- [ ] Automatizar decisões simples

### Fase 4: Analytics
- [ ] Dashboard de glosas em tempo real
- [ ] Predição de reversibilidade com ML
- [ ] Alertas proativos de glosas anormais

---

## Referências

### Design Patterns
- **Repository Pattern**: Para persistência
- **Cache-Aside**: Para otimização de leitura
- **Event Sourcing**: Para auditoria completa

### Frameworks
- **Spring Data JPA**: Persistência
- **Spring Cache**: Caching
- **Camunda**: Workflow automation

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissGlosaHandler.java`
