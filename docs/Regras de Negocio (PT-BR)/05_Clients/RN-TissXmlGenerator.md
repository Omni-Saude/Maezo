# RN-TissXmlGenerator - Gerador de XML TISS

## Identificação
- **Nome da Classe**: `TissXmlGenerator`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Gerador/Builder de XML
- **Padrão TISS**: 3.05.00 (compatibilidade 4.0 planejada)

## Objetivo
Gerar XMLs conforme o padrão TISS da ANS para diferentes tipos de guias (SADT-SP, Internação, Glosa) e validar a estrutura gerada antes da submissão.

## Contexto de Negócio
O padrão TISS exige XMLs rigidamente estruturados com namespaces, versões e elementos específicos. Este gerador garante:
- **Conformidade**: XML conforme schemas ANS
- **Rastreabilidade**: Logs de geração
- **Modularidade**: Métodos para cada tipo de guia
- **Validação**: Checagem básica antes de submissão

---

## Constantes

### TISS_VERSION
**Valor**: "3.05.00"

**Descrição**: Versão do padrão TISS utilizada na geração dos XMLs.

**Atualização**: Deve ser atualizada quando migrar para TISS 4.0+

---

### XML_HEADER
**Valor**: `<?xml version="1.0" encoding="UTF-8"?>`

**Descrição**: Header padrão XML com declaração de versão e encoding.

---

## Regras de Negócio

### RN-TISS-XML-001: Geração de Guia SADT-SP
**Descrição**: Gera XML de Guia de Serviço Profissional/Serviço Auxiliar de Diagnóstico e Terapia.

**Entradas**:
- `guiaData` (Map<String, Object>): Dados da guia

**Campos Requeridos**:
```
- registroANS: Registro da operadora na ANS (default: "123456")
- numeroGuia: Número da guia do prestador (default: "0001")
- guiaOperadora: Número da guia da operadora (default: "OP0001")
- dataAutorizacao: Data de autorização (default: "2024-01-01")
- carteirinha: Número da carteira do beneficiário (15 dígitos)
- nomeBeneficiario: Nome completo do beneficiário
- codigoProcedimento: Código TUSS do procedimento (8 dígitos)
- valorProcedimento: Valor do procedimento (decimal)
- valorTotal: Valor total da guia
```

**Processamento**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tissGuiaSP_SADT xmlns="http://www.ans.gov.br/padroes/tiss/schemas" versao="3.05.00">
  <cabecalhoGuia>
    <registroANS>{registroANS}</registroANS>
    <numeroGuiaPrestador>{numeroGuia}</numeroGuiaPrestador>
  </cabecalhoGuia>
  <dadosAutorizacao>
    <numeroGuiaOperadora>{guiaOperadora}</numeroGuiaOperadora>
    <dataAutorizacao>{dataAutorizacao}</dataAutorizacao>
  </dadosAutorizacao>
  <dadosBeneficiario>
    <numeroCarteira>{carteirinha}</numeroCarteira>
    <nomeBeneficiario>{nomeBeneficiario}</nomeBeneficiario>
  </dadosBeneficiario>
  <procedimentosExecutados>
    <procedimentoExecutado>
      <codigoProcedimento>{codigoProcedimento}</codigoProcedimento>
      <valorProcedimento>{valorProcedimento}</valorProcedimento>
    </procedimentoExecutado>
  </procedimentosExecutados>
  <valorTotal>
    <valorProcedimentos>{valorTotal}</valorProcedimentos>
  </valorTotal>
</tissGuiaSP_SADT>
```

**Saídas**:
- String XML formatado

**Tipo de Guia**: SADT-SP (Consultas, exames, procedimentos ambulatoriais)

**Regulamentação**: ANS Manual TISS - Guia SP/SADT

---

### RN-TISS-XML-002: Geração de Guia de Internação
**Descrição**: Gera XML de Resumo de Internação (alta hospitalar).

**Entradas**:
- `guiaData` (Map<String, Object>): Dados da internação

**Campos Requeridos**:
```
- registroANS: Registro da operadora na ANS
- numeroGuia: Número da guia do prestador
- dataInternacao: Data de início da internação
- dataAlta: Data de fim da internação
- tipoInternacao: Tipo (1=Clínica, 2=Cirúrgica, 3=Obstétrica, etc.)
- carteirinha: Número da carteira do beneficiário
- nomeBeneficiario: Nome completo do beneficiário
- codigoProcedimento: Código TUSS principal (ex: 30101012)
- valorProcedimento: Valor total da internação
- valorTotal: Valor total (procedimentos + taxas + materiais)
```

**Processamento**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tissGuiaResumoInternacao xmlns="http://www.ans.gov.br/padroes/tiss/schemas" versao="3.05.00">
  <cabecalhoGuia>
    <registroANS>{registroANS}</registroANS>
    <numeroGuiaPrestador>{numeroGuia}</numeroGuiaPrestador>
  </cabecalhoGuia>
  <dadosInternacao>
    <dataInicioInternacao>{dataInternacao}</dataInicioInternacao>
    <dataFimInternacao>{dataAlta}</dataFimInternacao>
    <tipoInternacao>{tipoInternacao}</tipoInternacao>
  </dadosInternacao>
  <dadosBeneficiario>
    <numeroCarteira>{carteirinha}</numeroCarteira>
    <nomeBeneficiario>{nomeBeneficiario}</nomeBeneficiario>
  </dadosBeneficiario>
  <procedimentosExecutados>
    <procedimentoExecutado>
      <codigoProcedimento>{codigoProcedimento}</codigoProcedimento>
      <valorProcedimento>{valorProcedimento}</valorProcedimento>
    </procedimentoExecutado>
  </procedimentosExecutados>
  <valorTotal>
    <valorProcedimentos>{valorTotal}</valorProcedimentos>
  </valorTotal>
</tissGuiaResumoInternacao>
```

**Saídas**:
- String XML formatado

**Tipos de Internação**:
- 1: Clínica
- 2: Cirúrgica
- 3: Obstétrica
- 4: Traumatológica
- 5: Psiquiátrica

**Regulamentação**: ANS Manual TISS - Resumo de Internação

---

### RN-TISS-XML-003: Geração de XML de Glosa
**Descrição**: Gera XML de notificação de glosa (auditoria/negação) recebida da operadora.

**Entradas**:
- `glosaData` (Map<String, Object>): Dados da glosa

**Campos Requeridos**:
```
- guiaOperadora: Número da guia da operadora
- numeroGuia: Número da guia do prestador
- codigoGlosa: Código da glosa (tabela ANS)
- descricaoGlosa: Descrição do motivo (ex: "Falta de autorização")
- valorGlosado: Valor negado
- valorLiberado: Valor aprovado para pagamento
```

**Processamento**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tissGlosa xmlns="http://www.ans.gov.br/padroes/tiss/schemas" versao="3.05.00">
  <identificacaoGuia>
    <numeroGuiaOperadora>{guiaOperadora}</numeroGuiaOperadora>
    <numeroGuiaPrestador>{numeroGuia}</numeroGuiaPrestador>
  </identificacaoGuia>
  <motivoGlosa>
    <codigoGlosa>{codigoGlosa}</codigoGlosa>
    <descricaoGlosa>{descricaoGlosa}</descricaoGlosa>
  </motivoGlosa>
  <valorGlosado>{valorGlosado}</valorGlosado>
  <valorLiberado>{valorLiberado}</valorLiberado>
</tissGlosa>
```

**Saídas**:
- String XML formatado

**Códigos de Glosa Comuns**:
- 01: Falta de autorização prévia
- 02: Procedimento não coberto pelo plano
- 03: Carência não cumprida
- 04: Documento inválido ou incompleto
- 05: Incompatibilidade CID x procedimento

**Uso**: Processar glosas recebidas via XML da operadora

---

### RN-TISS-XML-004: Geração de Lote de Guias
**Descrição**: Gera XML de lote com múltiplas guias para submissão em batch.

**Entradas**:
- `guiasBatch` (List<Map<String, Object>>): Lista de guias

**Campos por Guia**:
```
- tipoGuia: "SADT-SP" ou "INTERNACAO"
- ... demais campos conforme tipo
```

**Processamento**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tissLoteGuias xmlns="http://www.ans.gov.br/padroes/tiss/schemas" versao="3.05.00">
  <cabecalhoLote>
    <registroANS>123456</registroANS>
    <numeroLote>0001</numeroLote>
    <dataEnvio>2024-01-01</dataEnvio>
  </cabecalhoLote>
  <guias>
    <guia>{XML da guia 1}</guia>
    <guia>{XML da guia 2}</guia>
    ...
  </guias>
  <totalGuias>{guiasBatch.size()}</totalGuias>
</tissLoteGuias>
```

**Saídas**:
- String XML formatado com múltiplas guias

**Benefícios**:
- Submissão em massa mais eficiente
- Redução de overhead de rede
- Processamento otimizado na operadora

**Limites**:
- Máximo de guias por lote: Varia por operadora (típico: 100-500)

---

### RN-TISS-XML-005: Geração a partir de TissGuiaDTO
**Descrição**: Gera XML a partir de objeto TissGuiaDTO (usado por TissSubmissionClient).

**Entradas**:
- `guia` (TissGuiaDTO): Objeto DTO completo

**Processamento**:
```
1. Extrair numeroGuiaPrestador do cabecalho
2. Criar map com campos essenciais:
   - numeroGuia: guia.getCabecalho().getNumeroGuiaPrestador()
   - registroANS: "123456" (default)
3. Chamar generateGuiaSadtSp(map)
4. RETORNAR XML gerado
```

**Saídas**:
- String XML formatado

**Limitação Atual**: Assume sempre tipo SADT-SP. Deve ser expandido para:
- Detectar tipo de guia automaticamente
- Mapear todos os campos do DTO
- Suportar Internação, Urgência/Emergência, etc.

---

### RN-TISS-XML-006: Validação de XML
**Descrição**: Valida estrutura básica do XML gerado antes de submissão.

**Entradas**:
- `xml` (String): XML a validar

**Processamento**:
```
1. SE xml é null OU vazio ENTÃO RETORNAR false

2. SE xml NÃO contém "<?xml" ENTÃO RETORNAR false

3. SE xml NÃO contém namespace ANS ENTÃO RETORNAR false
   Namespace: "http://www.ans.gov.br/padroes/tiss/schemas"

4. RETORNAR true
```

**Saídas**:
- boolean: true se válido, false caso contrário

**Validações Básicas**:
- ✅ Presença de declaração XML
- ✅ Namespace ANS correto
- ❌ Validação de schema XSD (não implementado)
- ❌ Validação de dados obrigatórios (não implementado)

**Próximos Passos**:
- Implementar validação contra schema XSD
- Validar presença de campos obrigatórios
- Validar tipos de dados (datas, decimais)

---

## Helpers e Utilitários

### getOrDefault
**Descrição**: Extrai valor de map com fallback para default.

**Assinatura**:
```java
private Object getOrDefault(Map<String, Object> map, String key, Object defaultValue)
```

**Uso**: Garantir que campos sempre tenham valor (mesmo que padrão).

---

## Namespace e Schemas TISS

### Namespace Oficial
```
xmlns="http://www.ans.gov.br/padroes/tiss/schemas"
```

**Descrição**: Namespace XML obrigatório para validação pela ANS.

---

### Schema XSD
**Localização**: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar/padrao-tiss

**Arquivos**:
- `tissV3_05_00.xsd`: Schema principal TISS 3.05.00
- `tissV4_00.xsd`: Schema TISS 4.0 (versão atual)

**Validação**: Usar TissSchemaValidator para validar contra XSD

---

## Migração para TISS 4.0

### Mudanças Principais
1. **Namespace**: Permanece o mesmo
2. **Versão**: Atualizar para "4.00.00" ou superior
3. **Novos Campos**:
   - CID-10 obrigatório em mais contextos
   - Campos de auditoria expandidos
   - Novos tipos de guia

### Checklist de Migração
- [ ] Atualizar constante TISS_VERSION
- [ ] Revisar todos os métodos de geração
- [ ] Adicionar campos obrigatórios do TISS 4.0
- [ ] Atualizar schemas XSD
- [ ] Testes de compatibilidade com operadoras

---

## Exemplos de Uso

### Exemplo 1: Geração de SADT-SP
```java
TissXmlGenerator generator = new TissXmlGenerator();

Map<String, Object> dados = Map.of(
    "numeroGuia", "2024010001",
    "registroANS", "417173",
    "carteirinha", "123456789012345",
    "nomeBeneficiario", "João da Silva",
    "codigoProcedimento", "10101012",
    "valorProcedimento", "150.00",
    "valorTotal", "150.00"
);

String xml = generator.generateGuiaSadtSp(dados);
```

---

### Exemplo 2: Geração de Internação
```java
Map<String, Object> dados = Map.of(
    "numeroGuia", "INT2024010001",
    "dataInternacao", "2024-01-01",
    "dataAlta", "2024-01-05",
    "tipoInternacao", "2", // Cirúrgica
    "valorTotal", "5000.00"
);

String xml = generator.generateGuiaInternacao(dados);
```

---

### Exemplo 3: Validação
```java
String xml = generator.generateGuiaSadtSp(dados);

if (generator.validateXml(xml)) {
    // Prosseguir com submissão
} else {
    throw new IllegalArgumentException("XML inválido");
}
```

---

## Tratamento de Dados

### Valores Padrão
Quando campos não são fornecidos, o gerador usa valores padrão seguros:
- `registroANS`: "123456"
- `numeroGuia`: "0001"
- `guiaOperadora`: "OP0001"
- `dataAutorizacao`: "2024-01-01"

**⚠️ ATENÇÃO**: Valores padrão são apenas para testes. Em produção, **todos** os campos devem vir preenchidos.

---

### Formatação de Valores

#### Datas
**Formato**: "YYYY-MM-DD" (ISO 8601)

**Exemplo**: "2024-01-15"

---

#### Valores Monetários
**Formato**: String decimal com 2 casas

**Exemplo**: "150.00", "5000.50"

**⚠️ ATENÇÃO**: ANS exige ponto como separador decimal, não vírgula.

---

#### Códigos de Procedimento
**Formato**: 8 dígitos numéricos

**Exemplo**: "10101012", "30405052"

**Tabela**: TUSS (Terminologia Unificada da Saúde Suplementar)

---

## Performance

### Otimizações Atuais
- **StringBuilder**: Concatenação eficiente de strings
- **Métodos Específicos**: Geração direta sem templates

### Otimizações Futuras
- [ ] Template Engine (Velocity, Freemarker)
- [ ] Caching de estruturas XML comuns
- [ ] Geração paralela de lotes
- [ ] Streaming para XMLs muito grandes

---

## Testes

### Casos de Teste Recomendados
1. ✅ Geração com dados completos
2. ✅ Geração com valores padrão
3. ✅ Validação de XML válido
4. ✅ Validação de XML inválido
5. ⚠️ Validação contra schema XSD (pendente)
6. ⚠️ Geração de lote com 100+ guias (pendente)

---

## Próximos Passos

### Fase 1: Validação Rigorosa
- [ ] Integrar com TissSchemaValidator
- [ ] Validar contra XSD em todos os métodos
- [ ] Validar campos obrigatórios

### Fase 2: TISS 4.0 Completo
- [ ] Migrar para versão 4.00.00
- [ ] Implementar novos tipos de guia
- [ ] Adicionar campos obrigatórios

### Fase 3: Template Engine
- [ ] Migrar para Velocity/Freemarker
- [ ] Criar templates XSD-compliant
- [ ] Facilitar manutenção

### Fase 4: Performance
- [ ] Benchmark de geração
- [ ] Otimizar para lotes grandes
- [ ] Implementar caching

---

## Referências

### ANS
- **Manual TISS**: Componente Organizacional e Transacional
- **Download**: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar/padrao-tiss

### XML
- **W3C XML Spec**: https://www.w3.org/TR/xml/
- **XML Schema**: https://www.w3.org/TR/xmlschema11-1/

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissXmlGenerator.java`
