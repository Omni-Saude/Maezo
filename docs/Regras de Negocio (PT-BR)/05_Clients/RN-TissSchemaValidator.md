# RN-TissSchemaValidator - Validador de Schema TISS

## Identificação
- **Nome da Classe**: `TissSchemaValidator`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Validador XML/XSD
- **Padrão TISS**: 3.05.00 (configurável)

## Objetivo
Validar XMLs TISS contra schemas XSD oficiais da ANS, garantindo conformidade estrutural completa antes da submissão às operadoras.

## Contexto de Negócio
A ANS fornece schemas XSD (.xsd files) que definem rigorosamente a estrutura de cada tipo de guia TISS. Validação contra esses schemas é **crítica** para:
- **Prevenir Glosas**: XML inválido é automaticamente rejeitado
- **Conformidade Legal**: Obrigatório pela ANS
- **Economia**: Evita custos de resubmissão
- **Auditoria**: Demonstra boa-fé em auditorias

---

## Atributos

### tissSchema
**Tipo**: `javax.xml.validation.Schema`

**Descrição**: Schema XSD carregado para validação.

**Inicialização**: Via método `loadSchemas(String path)`

---

### schemaVersion
**Tipo**: `String`

**Valor Padrão**: "3.05.00"

**Descrição**: Versão do schema TISS carregado.

---

### schemaPath
**Tipo**: `String`

**Descrição**: Caminho do diretório contendo arquivos XSD.

---

## Regras de Negócio

### RN-TISS-VAL-001: Carregamento de Schemas
**Descrição**: Carrega schemas XSD da ANS a partir do filesystem.

**Entradas**:
- `path` (String): Caminho para diretório com XSDs

**Processamento**:
```
1. Criar SchemaFactory para W3C XML Schema
   factory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI)

2. Definir caminho do schema principal
   schemaFile = new File(path + "/tissV3_05_00.xsd")

3. SE schemaFile NÃO existe ENTÃO
     3.1. CRIAR schema vazio (para testes)
     3.2. ATRIBUIR a this.tissSchema
   SENÃO
     3.3. CARREGAR schema do arquivo
     3.4. ATRIBUIR a this.tissSchema

4. ARMAZENAR path em this.schemaPath
```

**Saídas**:
- `tissSchema` carregado e pronto para validação

**Exceções**:
- `Exception`: Se falha ao carregar schema

**Schema Principal**: `tissV3_05_00.xsd`

**Schemas Adicionais** (importados automaticamente):
- Tipos comuns
- Definições de elementos
- Restrições de formato

**Localização Oficial**:
- Download: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar/padrao-tiss
- Arquivo: Pacote "Padrões TISS Vigentes"

---

### RN-TISS-VAL-002: Obter Schema Carregado
**Descrição**: Retorna o schema XSD carregado.

**Entradas**: Nenhuma

**Processamento**:
```
RETORNAR this.tissSchema
```

**Saídas**:
- `Schema`: Objeto schema carregado

**Uso**: Validadores externos podem reutilizar o schema.

---

### RN-TISS-VAL-003: Obter Versão do Schema
**Descrição**: Retorna a versão do schema TISS carregado.

**Entradas**: Nenhuma

**Processamento**:
```
RETORNAR this.schemaVersion
```

**Saídas**:
- `String`: Versão (ex: "3.05.00", "4.00.00")

**Uso**: Logging, auditoria, compatibilidade.

---

### RN-TISS-VAL-004: Validação Simples de XML
**Descrição**: Valida XML contra schema TISS com retorno booleano.

**Entradas**:
- `xml` (String): Conteúdo XML a validar
- `guiaType` (String): Tipo de guia (ex: "SADT-SP", "INTERNACAO")

**Processamento**:
```
1. SE tissSchema é null ENTÃO
     LANÇAR IllegalStateException("Schema not loaded")

2. CRIAR Validator a partir do schema
   validator = tissSchema.newValidator()

3. TENTAR:
     3.1. VALIDAR XML
          validator.validate(new StreamSource(new StringReader(xml)))
     3.2. RETORNAR true
   CAPTURAR Exception:
     3.3. LOGAR erro: "TISS validation failed for {guiaType}: {message}"
     3.4. RETORNAR false
```

**Saídas**:
- `boolean`: true se válido, false se inválido

**Logging**:
- Erros de validação são impressos em stderr
- Incluem tipo de guia e mensagem de erro

**Uso Típico**:
```java
if (!validator.validateXml(xml, "SADT-SP")) {
    throw new ValidationException("XML inválido");
}
```

---

### RN-TISS-VAL-005: Validação Detalhada de XML
**Descrição**: Valida XML com retorno de objeto contendo detalhes completos de erro.

**Entradas**:
- `xml` (String): Conteúdo XML a validar
- `guiaType` (String): Tipo de guia

**Processamento**:
```
1. CRIAR ValidationResult vazio
   result = new ValidationResult()
   result.setGuiaType(guiaType)

2. SE tissSchema é null ENTÃO
     2.1. result.setValid(false)
     2.2. result.addError("Schema not loaded")
     2.3. RETORNAR result

3. CRIAR Validator a partir do schema
   validator = tissSchema.newValidator()

4. TENTAR:
     4.1. VALIDAR XML
          validator.validate(new StreamSource(new StringReader(xml)))
     4.2. result.setValid(true)
   CAPTURAR Exception:
     4.3. result.setValid(false)
     4.4. result.addError(e.getMessage())

5. RETORNAR result
```

**Saídas**:
- `ValidationResult`: Objeto com status e lista de erros

**Vantagens sobre Validação Simples**:
- ✅ Lista de TODOS os erros (não apenas o primeiro)
- ✅ Contexto de erro (linha, coluna)
- ✅ Mensagens detalhadas
- ✅ Tipo de guia associado

**Uso Típico**:
```java
ValidationResult result = validator.validateXmlDetailed(xml, "SADT-SP");
if (!result.isValid()) {
    for (String error : result.getErrors()) {
        log.error("Validation error: {}", error);
    }
}
```

---

## DTOs Internos

### ValidationResult
**Descrição**: Resultado de validação detalhada.

**Campos**:
- `valid` (boolean): Indica se XML é válido
- `guiaType` (String): Tipo de guia validada
- `errors` (List<String>): Lista de mensagens de erro

**Métodos**:
- `isValid()`: Retorna status de validade
- `setValid(boolean)`: Define status
- `getGuiaType()`: Retorna tipo de guia
- `setGuiaType(String)`: Define tipo
- `getErrors()`: Retorna lista de erros
- `addError(String)`: Adiciona um erro à lista

**Inicialização**:
```java
ValidationResult result = new ValidationResult();
result.setGuiaType("SADT-SP");
result.setValid(false);
result.addError("Campo obrigatório 'numeroCarteira' ausente");
```

---

## Erros Comuns de Validação

### 1. Namespace Incorreto
**Mensagem**: "Namespace 'xxx' não corresponde ao esperado"

**Causa**: XML usa namespace diferente do schema

**Correção**: Garantir namespace `http://www.ans.gov.br/padroes/tiss/schemas`

---

### 2. Elemento Obrigatório Ausente
**Mensagem**: "Elemento 'xxx' é obrigatório mas não foi encontrado"

**Causa**: Campo obrigatório não incluído no XML

**Correção**: Adicionar elemento faltante

**Exemplo**: `<numeroCarteira>` é obrigatório em `<dadosBeneficiario>`

---

### 3. Tipo de Dado Incorreto
**Mensagem**: "Valor 'xxx' não é válido para tipo 'yyy'"

**Causa**: Dado não corresponde ao tipo XSD

**Exemplos**:
- Data em formato incorreto (usar "YYYY-MM-DD")
- Decimal com vírgula (usar ponto)
- String onde se espera número

**Correção**: Ajustar formato do dado

---

### 4. Valor Fora do Range
**Mensagem**: "Valor 'xxx' fora do range permitido"

**Causa**: Valor numérico ou string maior/menor que permitido

**Exemplos**:
- Número de carteira com menos de 15 dígitos
- Código de procedimento com formato inválido

**Correção**: Validar dados de entrada

---

### 5. Sequência de Elementos Incorreta
**Mensagem**: "Elemento 'xxx' não permitido nesta posição"

**Causa**: Ordem dos elementos XML não corresponde ao schema

**Correção**: Reordenar elementos conforme XSD

**⚠️ IMPORTANTE**: Schema XSD define ordem **exata** dos elementos

---

## Schemas XSD Oficiais ANS

### Estrutura de Diretório
```
schemas/
├── tissV3_05_00.xsd          # Schema principal
├── tipos_comuns.xsd          # Tipos base
├── elementos_comuns.xsd      # Elementos reutilizáveis
├── guias/
│   ├── guia_sadt_sp.xsd     # SADT-SP específico
│   ├── guia_internacao.xsd  # Internação específico
│   └── ...
└── lotes/
    └── lote_guias.xsd        # Lotes
```

### Download
**URL**: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar/padrao-tiss

**Arquivo**: "Padrões TISS Vigentes - Componente de Comunicação"

**Atualização**: Verificar publicações ANS semestralmente

---

## Performance

### Caching de Schema
**Problema**: Carregar schema a cada validação é lento

**Solução**: Carregar schema uma vez na inicialização
```java
@PostConstruct
public void init() throws Exception {
    validator.loadSchemas("/path/to/schemas");
}
```

### Validações em Paralelo
**Cenário**: Validar lote de 100+ guias

**Solução**: Usar streams paralelas
```java
boolean allValid = xmlList.parallelStream()
    .allMatch(xml -> validator.validateXml(xml, "SADT-SP"));
```

### Reutilização de Validator
**⚠️ ATENÇÃO**: `Validator` não é thread-safe

**Solução**: Criar novo Validator por thread
```java
Validator validator = tissSchema.newValidator();
validator.validate(...);
```

---

## Testes

### Casos de Teste

#### 1. Schema Não Carregado
```java
TissSchemaValidator validator = new TissSchemaValidator();
// Não chamar loadSchemas()

boolean result = validator.validateXml("<xml>...</xml>", "SADT-SP");
// Deve lançar IllegalStateException
```

---

#### 2. XML Válido
```java
validator.loadSchemas("/path/to/schemas");
String validXml = generator.generateGuiaSadtSp(validData);

boolean result = validator.validateXml(validXml, "SADT-SP");
// result == true
```

---

#### 3. XML Inválido - Namespace Errado
```java
String invalidXml = "<guia xmlns=\"http://wrong.namespace\">...</guia>";

boolean result = validator.validateXml(invalidXml, "SADT-SP");
// result == false
```

---

#### 4. Validação Detalhada
```java
ValidationResult result = validator.validateXmlDetailed(invalidXml, "SADT-SP");

assertFalse(result.isValid());
assertTrue(result.getErrors().size() > 0);
assertEquals("SADT-SP", result.getGuiaType());
```

---

## Integração com TissXmlGenerator

### Fluxo Completo
```java
// 1. Gerar XML
TissXmlGenerator generator = new TissXmlGenerator();
String xml = generator.generateGuiaSadtSp(data);

// 2. Validar XML
TissSchemaValidator validator = new TissSchemaValidator();
validator.loadSchemas("/path/to/schemas");

ValidationResult result = validator.validateXmlDetailed(xml, "SADT-SP");

// 3. Processar resultado
if (result.isValid()) {
    submissionClient.submitGuia(xml);
} else {
    for (String error : result.getErrors()) {
        log.error("Validation error: {}", error);
    }
    throw new ValidationException("XML inválido");
}
```

---

## Configuração

### application.yml
```yaml
tiss:
  schema:
    path: /opt/hospital/schemas/tiss
    version: 3.05.00
  validation:
    enabled: true
    fail-on-error: true
```

### Bean Configuration
```java
@Configuration
public class TissConfig {

    @Value("${tiss.schema.path}")
    private String schemaPath;

    @Bean
    public TissSchemaValidator tissSchemaValidator() throws Exception {
        TissSchemaValidator validator = new TissSchemaValidator();
        validator.loadSchemas(schemaPath);
        return validator;
    }
}
```

---

## Migrações de Versão

### Migração 3.05.00 → 4.00.00

**Mudanças no Schema**:
1. Namespace permanece o mesmo
2. Novos elementos obrigatórios
3. Tipos de dados expandidos
4. Novos códigos de validação

**Checklist**:
- [ ] Baixar schemas 4.00.00 da ANS
- [ ] Atualizar schemaPath
- [ ] Atualizar schemaVersion para "4.00.00"
- [ ] Re-testar todos os XMLs existentes
- [ ] Ajustar TissXmlGenerator para novos campos

**Compatibilidade**: TISS 3.x e 4.x **não** são compatíveis. Migração requer:
- Atualização de todos os XMLs
- Revalidação completa
- Possível necessidade de manter dual-mode temporariamente

---

## Próximos Passos

### Fase 1: Validação em Tempo Real
- [ ] Integrar com TissXmlGenerator automaticamente
- [ ] Lançar exceção específica para erros de validação
- [ ] Criar TissValidationException customizada

### Fase 2: Relatórios Detalhados
- [ ] Gerar relatório HTML de erros
- [ ] Destacar linhas/colunas com erro
- [ ] Sugerir correções

### Fase 3: Validação Assíncrona
- [ ] Validar em background
- [ ] Notificar via callback
- [ ] Otimizar para grandes volumes

### Fase 4: Cache Inteligente
- [ ] Cachear schemas compilados
- [ ] Hot-reload de schemas atualizados
- [ ] Monitorar mudanças no filesystem

---

## Monitoramento

### Métricas Importantes
1. **Validation Rate**: Quantas validações/segundo
2. **Validation Success Rate**: % de XMLs válidos
3. **Average Validation Time**: Tempo médio de validação
4. **Schema Load Time**: Tempo de carregamento inicial

### Alertas Recomendados
- Schema não carregado na inicialização
- Validation success rate < 90%
- Validation time > 1s

---

## Referências

### ANS
- **Padrão TISS**: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar/padrao-tiss
- **Schemas XSD**: Incluídos no pacote de download

### XML Schema (W3C)
- **Spec**: https://www.w3.org/TR/xmlschema11-1/
- **Tutorial**: https://www.w3schools.com/xml/schema_intro.asp

### Java XML Validation
- **javax.xml.validation**: https://docs.oracle.com/javase/8/docs/api/javax/xml/validation/package-summary.html

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissSchemaValidator.java`
