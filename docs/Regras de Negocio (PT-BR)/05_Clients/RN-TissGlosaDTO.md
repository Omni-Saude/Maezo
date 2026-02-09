# RN-TissGlosaDTO - DTO de Glosa TISS

## Identificação
- **Nome da Classe**: `TissGlosaDTO`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Data Transfer Object (DTO)
- **Padrão TISS**: Glosa/Negação de Cobrança

## Objetivo
Representar uma glosa (negação ou redução de pagamento) recebida da operadora de saúde, permitindo rastreamento, análise e gestão de recursos/contestações.

## Contexto de Negócio
**Glosa** é a negação total ou parcial do pagamento de uma guia pela operadora de saúde. Tipos de glosa:

### 1. Glosa Técnica
**Causa**: Problemas técnicos ou administrativos
- Falta de autorização prévia
- Documentação incompleta
- Prazo de apresentação expirado
- Dados cadastrais incorretos

**Reversibilidade**: Alta (80-90% com documentação correta)

---

### 2. Glosa Clínica
**Causa**: Divergências clínicas ou auditoria médica
- Procedimento incompatível com diagnóstico
- Quantidade excessiva de procedimentos
- Medicamento não justificado
- Internação com tempo inadequado

**Reversibilidade**: Média (40-60% com justificativa médica)

---

### 3. Glosa por Tabela
**Causa**: Valor cobrado acima da tabela contratual
- Valor do procedimento acima do pactuado
- Taxa administrativa não contratada
- Cobrança de item não previsto

**Reversibilidade**: Baixa (20-30%, depende de contrato)

---

## Campos do DTO

### numeroGuia
**Tipo**: `String`

**Descrição**: Número da guia original que foi glosada (número do prestador).

**Formato**: Alfanumérico, até 20 caracteres

**Obrigatório**: Sim

**Uso**: Relacionar a glosa com a guia original no sistema.

**Exemplo**: "2024010001"

---

### numeroProtocolo
**Tipo**: `String`

**Descrição**: Número de protocolo da glosa atribuído pela operadora.

**Formato**: Alfanumérico, até 30 caracteres

**Obrigatório**: Sim

**Uso**:
- Identificação única da glosa
- Referência em recursos/contestações
- Rastreamento de status

**Exemplo**: "GLOSA-2024-001234"

---

### dataGlosa
**Tipo**: `LocalDate`

**Descrição**: Data em que a glosa foi registrada pela operadora.

**Formato**: ISO 8601 (YYYY-MM-DD)

**Obrigatório**: Sim

**Uso**:
- Contagem de prazos para recurso
- Análise temporal de glosas
- SLA de processamento

**Prazos Legais**:
- Recurso administrativo: 30 dias corridos
- Recurso judicial: Conforme CPC

**Exemplo**: `LocalDate.of(2024, 1, 15)`

---

### codigoGlosa
**Tipo**: `String`

**Descrição**: Código padronizado ANS do motivo da glosa.

**Formato**: Numérico, 2 dígitos

**Obrigatório**: Sim

**Tabela ANS de Códigos de Glosa**:
- **01**: Falta de autorização
- **02**: Procedimento não coberto
- **03**: Carência não cumprida
- **04**: Documento inválido
- **05**: Incompatibilidade CID x procedimento
- **06**: Procedimento excedente
- **07**: Acomodação não contratada
- **08**: Valor cobrado acima da tabela
- **09**: Duplicidade
- **10**: Prazo de apresentação expirado
- **99**: Outros motivos

**Uso**: Análise estatística e categorização de glosas.

**Exemplo**: "01"

---

### descricaoGlosa
**Tipo**: `String`

**Descrição**: Descrição textual detalhada do motivo da glosa.

**Formato**: Texto livre, até 500 caracteres

**Obrigatório**: Sim

**Uso**:
- Compreensão do motivo específico
- Preparação de defesa/recurso
- Treinamento de equipe

**Exemplo**: "Guia apresentada sem autorização prévia. Necessário documento de autorização assinado pelo médico auditor."

---

### procedimentoGlosado
**Tipo**: `String`

**Descrição**: Código TUSS do procedimento que foi glosado (se glosa específica de procedimento).

**Formato**: 8 dígitos numéricos

**Obrigatório**: Não (pode ser glosa de guia inteira)

**Uso**:
- Identificar procedimentos com maior taxa de glosa
- Análise de compatibilidade
- Treinamento de faturistas

**Exemplo**: "10101012"

---

### valorGlosado
**Tipo**: `BigDecimal`

**Descrição**: Valor monetário que foi glosado (negado).

**Formato**: Decimal com 2 casas

**Obrigatório**: Sim

**Validação**: >= 0.00

**Uso**:
- Impacto financeiro de glosas
- Cálculo de taxa de glosa
- Priorização de recursos

**Exemplo**: `new BigDecimal("150.00")`

---

### motivoGlosa
**Tipo**: `String`

**Descrição**: Justificativa detalhada da operadora para a glosa.

**Formato**: Texto livre, até 1000 caracteres

**Obrigatório**: Não

**Diferença de descricaoGlosa**:
- `descricaoGlosa`: Motivo resumido
- `motivoGlosa`: Justificativa completa com detalhes técnicos/clínicos

**Uso**: Preparação de recurso com argumentação específica.

**Exemplo**: "Após análise da documentação clínica, constatou-se que o procedimento 'Ressonância Magnética de Crânio' foi realizado sem justificativa médica adequada. O CID-10 informado (M54.5 - Dor lombar) não justifica o exame solicitado. Necessário apresentar novo laudo médico que relacione o CID com a necessidade do exame."

---

### status
**Tipo**: `String`

**Descrição**: Status atual da glosa no processo de gestão.

**Valores Possíveis**:
- **PENDENTE**: Glosa recebida, aguardando análise
- **EM_RECURSO**: Recurso administrativo em andamento
- **ACEITA**: Glosa aceita pelo hospital (não será contestada)
- **REVERTIDA**: Glosa revertida pela operadora após recurso

**Obrigatório**: Sim

**Transições de Estado**:
```
PENDENTE → EM_RECURSO (quando recurso é protocolado)
PENDENTE → ACEITA (quando decisão é aceitar glosa)
EM_RECURSO → REVERTIDA (quando recurso é aceito)
EM_RECURSO → ACEITA (quando recurso é negado)
```

**Uso**:
- Workflow de gestão de glosas
- Relatórios de performance
- Alertas de SLA

---

## Lombok Annotations

### @Data
Gera automaticamente:
- Getters para todos os campos
- Setters para todos os campos
- `toString()`
- `equals()` e `hashCode()`

---

### @Builder
Permite construção fluente:
```java
TissGlosaDTO glosa = TissGlosaDTO.builder()
    .numeroGuia("2024010001")
    .numeroProtocolo("GLOSA-2024-001234")
    .dataGlosa(LocalDate.now())
    .codigoGlosa("01")
    .descricaoGlosa("Falta de autorização prévia")
    .valorGlosado(new BigDecimal("150.00"))
    .status("PENDENTE")
    .build();
```

---

### @NoArgsConstructor / @AllArgsConstructor
- **NoArgsConstructor**: Construtor sem argumentos (para frameworks)
- **AllArgsConstructor**: Construtor com todos os argumentos

---

## Regras de Negócio

### RN-GLOSA-001: Registro de Glosa
**Descrição**: Registrar uma nova glosa no sistema.

**Entradas**: TissGlosaDTO com dados completos

**Processamento**:
```
1. Validar campos obrigatórios
2. Definir status inicial = "PENDENTE"
3. Calcular data limite para recurso (dataGlosa + 30 dias)
4. Armazenar em banco de dados
5. Notificar equipe de gestão de glosas
```

**Saídas**: Glosa persistida com ID único

---

### RN-GLOSA-002: Análise de Glosa
**Descrição**: Analisar se glosa deve ser aceita ou contestada.

**Critérios de Decisão**:
```
SE valorGlosado < R$ 100 E probabilidadeReverter < 50% ENTÃO
    decisao = ACEITAR (custo de recurso > benefício)
SENÃO SE documentacao_completa E fundamentacao_solida ENTÃO
    decisao = RECURSO
SENÃO
    decisao = ACEITAR
```

---

### RN-GLOSA-003: Recurso Administrativo
**Descrição**: Protocolar recurso contra glosa.

**Entradas**:
- numeroProtocolo
- documentacao_suporte (laudos, autorizações, etc.)
- justificativa_tecnica

**Processamento**:
```
1. Validar prazo (dataAtual <= dataGlosa + 30 dias)
2. Preparar documentação completa
3. Enviar via portal da operadora
4. Atualizar status para "EM_RECURSO"
5. Agendar follow-up (15 dias)
```

---

### RN-GLOSA-004: Reversão de Glosa
**Descrição**: Processar reversão de glosa (recurso aceito).

**Entradas**: numeroProtocolo

**Processamento**:
```
1. Atualizar status para "REVERTIDA"
2. Registrar valor recuperado
3. Criar nova guia de cobrança (re-apresentação)
4. Notificar financeiro
5. Atualizar métricas de glosa
```

---

### RN-GLOSA-005: Aceitação de Glosa
**Descrição**: Aceitar glosa como definitiva.

**Entradas**: numeroProtocolo

**Processamento**:
```
1. Atualizar status para "ACEITA"
2. Registrar perda financeira
3. Atualizar previsão de receita
4. SE glosa técnica ENTÃO
     4.1. Registrar lição aprendida
     4.2. Treinar equipe responsável
5. Notificar financeiro
```

---

## Indicadores de Performance (KPIs)

### Taxa de Glosa
**Fórmula**:
```
Taxa de Glosa (%) = (Valor Total Glosado / Valor Total Faturado) × 100
```

**Meta**: < 5%

**Alerta**: > 10%

---

### Taxa de Reversão
**Fórmula**:
```
Taxa de Reversão (%) = (Glosas Revertidas / Total de Recursos) × 100
```

**Meta**: > 60%

**Benchmark**:
- Excelente: > 70%
- Bom: 50-70%
- Regular: 30-50%
- Ruim: < 30%

---

### Tempo Médio de Recurso
**Fórmula**:
```
Tempo Médio = Σ(data_decisão - data_protocolo) / total_recursos
```

**Meta**: < 30 dias

**SLA Operadora**: Responder em até 30 dias úteis

---

## Integração com Outros Componentes

### TissGlosaHandler
```java
TissGlosaDTO glosa = buildGlosa();
glosaHandler.registerGlosa(glosa);
```

### TissXmlGenerator
```java
// Gerar XML de recurso contra glosa
Map<String, Object> recursoData = Map.of(
    "numeroProtocolo", glosa.getNumeroProtocolo(),
    "justificativa", "...",
    "documentos", [...]
);
String xml = xmlGenerator.generateRecursoGlosa(recursoData);
```

---

## Análise e Relatórios

### Glosas por Código
```sql
SELECT
    codigoGlosa,
    COUNT(*) as quantidade,
    SUM(valorGlosado) as valorTotal
FROM tiss_glosa
WHERE dataGlosa >= '2024-01-01'
GROUP BY codigoGlosa
ORDER BY valorTotal DESC;
```

---

### Top Procedimentos Glosados
```sql
SELECT
    procedimentoGlosado,
    COUNT(*) as quantidade,
    SUM(valorGlosado) as valorTotal,
    AVG(valorGlosado) as valorMedio
FROM tiss_glosa
WHERE procedimentoGlosado IS NOT NULL
GROUP BY procedimentoGlosado
ORDER BY quantidade DESC
LIMIT 10;
```

---

### Taxa de Reversão por Código
```sql
SELECT
    codigoGlosa,
    COUNT(*) as totalGlosas,
    SUM(CASE WHEN status = 'REVERTIDA' THEN 1 ELSE 0 END) as revertidas,
    ROUND(100.0 * SUM(CASE WHEN status = 'REVERTIDA' THEN 1 ELSE 0 END) / COUNT(*), 2) as taxaReversao
FROM tiss_glosa
GROUP BY codigoGlosa
ORDER BY taxaReversao DESC;
```

---

## Prevenção de Glosas

### Checklist Pré-Submissão
- [ ] Autorização prévia anexada
- [ ] CID-10 compatível com procedimento
- [ ] Documentação clínica completa
- [ ] Valores conforme tabela contratual
- [ ] Dados cadastrais atualizados
- [ ] Prazos de apresentação respeitados

---

### Treinamento de Equipe
**Tópicos**:
1. Códigos de glosa mais frequentes
2. Documentação obrigatória por tipo de procedimento
3. Como preencher campos críticos
4. Processo de recurso administrativo

---

## Próximos Passos

### Fase 1: Analytics Avançado
- [ ] Dashboard de glosas em tempo real
- [ ] Predição de glosas com ML
- [ ] Alertas proativos

### Fase 2: Automação
- [ ] Recurso automático para glosas simples
- [ ] Geração automática de justificativas
- [ ] Integração com portal da operadora

### Fase 3: Gestão Proativa
- [ ] Validação pré-submissão
- [ ] Sugestão de correções
- [ ] Score de risco de glosa

---

## Referências

### ANS
- **RN 305/2012**: Padrão TISS
- **Tabela de Códigos de Glosa**: Anexo técnico TISS

### Jurídico
- **Código de Defesa do Consumidor**: Prazos e recursos
- **Lei 9.656/98**: Lei dos Planos de Saúde

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissGlosaDTO.java`
