# RN-TissGuiaDTO - DTO de Guia TISS

## Identificação
- **Nome da Classe**: `TissGuiaDTO`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Data Transfer Object (DTO)
- **Padrão TISS**: 3.05.00 - Guia SP/SADT
- **Anotações XML**: JAXB para marshalling/unmarshalling

## Objetivo
Representar estruturalmente uma Guia TISS (Autorização/Cobrança) em formato orientado a objetos, mapeando diretamente para XML através de anotações JAXB.

## Contexto de Negócio
Uma Guia TISS é o documento central para:
- **Autorização**: Solicitar autorização prévia da operadora
- **Cobrança**: Enviar cobrança de serviços prestados
- **Auditoria**: Rastreabilidade completa do atendimento

Este DTO modela especificamente **Guia SP/SADT** (Serviço Profissional / Serviço Auxiliar de Diagnóstico e Terapia), utilizada para:
- Consultas médicas
- Exames laboratoriais
- Exames de imagem
- Procedimentos ambulatoriais
- Terapias

---

## Estrutura Hierárquica

### Classe Principal: TissGuiaDTO

**Anotações JAXB**:
- `@XmlRootElement(name = "guiaSPSADT")`: Define como elemento raiz XML
- `@XmlAccessorType(XmlAccessType.FIELD)`: Acesso via campos

**Componentes**:
1. **CabecalhoGuia**: Identificação da guia
2. **DadosBeneficiario**: Informações do paciente
3. **DadosSolicitante**: Médico solicitante
4. **DadosExecutante**: Prestador que executou o serviço
5. **ProcedimentosExecutados**: Lista de procedimentos realizados
6. **ValorTotal**: Totalização de valores

---

## Classes Internas (DTOs Aninhados)

### 1. CabecalhoGuia
**Descrição**: Cabeçalho com identificação e datas da guia.

**Campos**:
- `numeroGuiaPrestador` (String): Número único da guia no sistema do prestador
- `numeroGuiaOperadora` (String): Número da guia atribuído pela operadora (pré-autorização)
- `dataAutorizacao` (LocalDate): Data da autorização prévia
- `dataEmissao` (LocalDate): Data de emissão da guia

**Anotações**:
- `@XmlElement`: Cada campo é um elemento XML
- `@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`: Lombok

**Validações de Negócio**:
- `numeroGuiaPrestador` deve ser único no sistema
- `dataAutorizacao` <= `dataEmissao` (autorização antes da emissão)

**Exemplo XML**:
```xml
<cabecalhoGuia>
  <numeroGuiaPrestador>2024010001</numeroGuiaPrestador>
  <numeroGuiaOperadora>OP123456</numeroGuiaOperadora>
  <dataAutorizacao>2024-01-01</dataAutorizacao>
  <dataEmissao>2024-01-02</dataEmissao>
</cabecalhoGuia>
```

---

### 2. DadosBeneficiario
**Descrição**: Identificação completa do beneficiário (paciente).

**Campos**:
- `numeroCarteira` (String): Número da carteira do plano de saúde (15 dígitos)
- `nomeBeneficiario` (String): Nome completo do beneficiário
- `cpf` (String): CPF do beneficiário (11 dígitos)
- `dataNascimento` (LocalDate): Data de nascimento

**Validações de Negócio**:
- `numeroCarteira` deve ter exatamente 15 dígitos
- `cpf` deve ser válido (algoritmo de validação)
- `dataNascimento` < dataAtual (não pode ser futuro)
- Idade calculada: dataAtual - dataNascimento

**Uso**:
- Elegibilidade: Verificar se beneficiário está ativo
- Carência: Verificar se cumpriu período de carência
- Faixa Etária: Validações específicas (pediatria, geriatria)

**Exemplo XML**:
```xml
<dadosBeneficiario>
  <numeroCarteira>123456789012345</numeroCarteira>
  <nomeBeneficiario>João da Silva</nomeBeneficiario>
  <cpf>12345678901</cpf>
  <dataNascimento>1980-05-15</dataNascimento>
</dadosBeneficiario>
```

---

### 3. DadosSolicitante
**Descrição**: Médico ou profissional que solicitou o procedimento.

**Campos**:
- `codigoProfissional` (String): Código interno do profissional
- `nomeProfissional` (String): Nome completo do profissional
- `numeroConselho` (String): Número do conselho profissional (CRM, CRO, etc.)

**Validações de Negócio**:
- Profissional deve estar ativo no sistema
- `numeroConselho` deve estar válido no conselho respectivo
- Especialidade do solicitante deve ser compatível com o procedimento

**Uso**:
- Auditoria: Rastreabilidade da solicitação
- Pagamento: Distribuição de honorários (se aplicável)
- Regulação: Validação de competência técnica

**Exemplo XML**:
```xml
<dadosSolicitante>
  <codigoProfissional>MED001</codigoProfissional>
  <nomeProfissional>Dr. Carlos Mendes</nomeProfissional>
  <numeroConselho>CRM-SP 123456</numeroConselho>
</dadosSolicitante>
```

---

### 4. DadosExecutante
**Descrição**: Prestador (hospital, clínica, laboratório) que executou o serviço.

**Campos**:
- `codigoPrestador` (String): Código do prestador no sistema da operadora
- `cnpj` (String): CNPJ do prestador (14 dígitos)
- `nomeContratado` (String): Razão social do prestador

**Validações de Negócio**:
- Prestador deve ter contrato ativo com a operadora
- `cnpj` deve ser válido
- Credenciamento deve estar vigente

**Uso**:
- Pagamento: Identificação de quem receberá o pagamento
- Auditoria: Rastreabilidade de onde o serviço foi executado
- Qualidade: Avaliação de prestadores

**Exemplo XML**:
```xml
<dadosExecutante>
  <codigoPrestador>HOSP001</codigoPrestador>
  <cnpj>12345678000190</cnpj>
  <nomeContratado>Hospital Example S.A.</nomeContratado>
</dadosExecutante>
```

---

### 5. ProcedimentosExecutados
**Descrição**: Container para lista de procedimentos realizados.

**Campos**:
- `procedimentos` (List<Procedimento>): Lista de procedimentos

**Anotação**:
- `@XmlElement(name = "procedimento")`: Cada item da lista é um elemento `<procedimento>`

**Validações de Negócio**:
- Deve conter pelo menos 1 procedimento
- Soma dos valores dos procedimentos = valorTotal

**Exemplo XML**:
```xml
<procedimentosExecutados>
  <procedimento>
    ...
  </procedimento>
  <procedimento>
    ...
  </procedimento>
</procedimentosExecutados>
```

---

### 6. Procedimento
**Descrição**: Representa um procedimento individual executado.

**Campos**:
- `dataExecucao` (LocalDate): Data em que o procedimento foi executado
- `codigoTabela` (String): Tabela de referência (ex: "22" = TUSS)
- `codigoProcedimento` (String): Código do procedimento na tabela (8 dígitos)
- `descricaoProcedimento` (String): Descrição textual do procedimento
- `quantidadeExecutada` (Integer): Quantidade de vezes que foi executado
- `valorUnitario` (BigDecimal): Valor unitário do procedimento
- `valorTotal` (BigDecimal): Valor total (quantidadeExecutada × valorUnitario)

**Validações de Negócio**:
- `dataExecucao` deve estar dentro do período de vigência da autorização
- `codigoProcedimento` deve existir na tabela especificada
- `valorTotal` = `quantidadeExecutada` × `valorUnitario`
- Procedimento deve ser compatível com diagnóstico (CID-10)

**Tabelas de Procedimento**:
- **22**: TUSS (Terminologia Unificada da Saúde Suplementar) - ANS
- **18**: CBHPM (Classificação Brasileira Hierarquizada de Procedimentos Médicos) - AMB/CFM
- **19**: SIMPRO (Sistema Integrado de Procedimentos)

**Exemplo XML**:
```xml
<procedimento>
  <dataExecucao>2024-01-03</dataExecucao>
  <codigoTabela>22</codigoTabela>
  <codigoProcedimento>10101012</codigoProcedimento>
  <descricaoProcedimento>Consulta médica em consultório</descricaoProcedimento>
  <quantidadeExecutada>1</quantidadeExecutada>
  <valorUnitario>150.00</valorUnitario>
  <valorTotal>150.00</valorTotal>
</procedimento>
```

---

### 7. ValorTotal
**Descrição**: Totalização de valores da guia.

**Campos**:
- `valorProcedimentos` (BigDecimal): Soma dos valores de procedimentos
- `valorTaxasAlugueis` (BigDecimal): Taxas e aluguéis de equipamentos
- `valorMateriais` (BigDecimal): Materiais utilizados
- `valorMedicamentos` (BigDecimal): Medicamentos administrados
- `valorGeral` (BigDecimal): Valor total geral da guia

**Fórmula**:
```
valorGeral = valorProcedimentos
           + valorTaxasAlugueis
           + valorMateriais
           + valorMedicamentos
```

**Validações de Negócio**:
- Todos os valores devem ser >= 0
- `valorGeral` deve ser a soma exata dos demais
- Precisão de 2 casas decimais

**Exemplo XML**:
```xml
<valorTotal>
  <valorProcedimentos>150.00</valorProcedimentos>
  <valorTaxasAlugueis>0.00</valorTaxasAlugueis>
  <valorMateriais>50.00</valorMateriais>
  <valorMedicamentos>0.00</valorMedicamentos>
  <valorGeral>200.00</valorGeral>
</valorTotal>
```

---

## Marshalling e Unmarshalling XML

### Marshalling (Objeto → XML)
**Descrição**: Converter TissGuiaDTO para String XML.

**Código Exemplo**:
```java
JAXBContext context = JAXBContext.newInstance(TissGuiaDTO.class);
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, true);

StringWriter writer = new StringWriter();
marshaller.marshal(guiaDTO, writer);
String xml = writer.toString();
```

**Uso**: Geração de XML para submissão à operadora.

---

### Unmarshalling (XML → Objeto)
**Descrição**: Converter String XML para TissGuiaDTO.

**Código Exemplo**:
```java
JAXBContext context = JAXBContext.newInstance(TissGuiaDTO.class);
Unmarshaller unmarshaller = context.createUnmarshaller();

StringReader reader = new StringReader(xml);
TissGuiaDTO guia = (TissGuiaDTO) unmarshaller.unmarshal(reader);
```

**Uso**: Processar XMLs recebidos da operadora (retornos, glosas).

---

## Validações de Integridade

### Validações de Campo

#### numeroCarteira
```java
@Pattern(regexp = "\\d{15}")
@NotNull
private String numeroCarteira;
```

#### cpf
```java
@CPF // Bean Validation customizado
@NotNull
private String cpf;
```

#### dataExecucao
```java
@PastOrPresent
@NotNull
private LocalDate dataExecucao;
```

#### valorTotal (Procedimento)
```java
@DecimalMin("0.00")
@Digits(integer = 10, fraction = 2)
@NotNull
private BigDecimal valorTotal;
```

---

### Validações de Negócio (Customizadas)

#### Consistência de Valores
```java
public void validate() {
    BigDecimal somaValores = valorTotal.getValorProcedimentos()
        .add(valorTotal.getValorTaxasAlugueis())
        .add(valorTotal.getValorMateriais())
        .add(valorTotal.getValorMedicamentos());

    if (!somaValores.equals(valorTotal.getValorGeral())) {
        throw new ValidationException("Valor geral não corresponde à soma dos valores");
    }
}
```

---

#### Consistência de Datas
```java
public void validate() {
    if (cabecalho.getDataAutorizacao().isAfter(cabecalho.getDataEmissao())) {
        throw new ValidationException("Data de autorização não pode ser após emissão");
    }
}
```

---

## Builders e Criação de Instâncias

### Lombok @Builder
Todas as classes internas usam `@Builder` para construção fluente.

**Exemplo**:
```java
TissGuiaDTO guia = TissGuiaDTO.builder()
    .cabecalho(CabecalhoGuia.builder()
        .numeroGuiaPrestador("2024010001")
        .numeroGuiaOperadora("OP123456")
        .dataAutorizacao(LocalDate.of(2024, 1, 1))
        .dataEmissao(LocalDate.of(2024, 1, 2))
        .build())
    .beneficiario(DadosBeneficiario.builder()
        .numeroCarteira("123456789012345")
        .nomeBeneficiario("João da Silva")
        .cpf("12345678901")
        .dataNascimento(LocalDate.of(1980, 5, 15))
        .build())
    .procedimentos(ProcedimentosExecutados.builder()
        .procedimentos(List.of(
            Procedimento.builder()
                .dataExecucao(LocalDate.of(2024, 1, 3))
                .codigoTabela("22")
                .codigoProcedimento("10101012")
                .descricaoProcedimento("Consulta médica")
                .quantidadeExecutada(1)
                .valorUnitario(new BigDecimal("150.00"))
                .valorTotal(new BigDecimal("150.00"))
                .build()
        ))
        .build())
    .valorTotal(ValorTotal.builder()
        .valorProcedimentos(new BigDecimal("150.00"))
        .valorTaxasAlugueis(BigDecimal.ZERO)
        .valorMateriais(BigDecimal.ZERO)
        .valorMedicamentos(BigDecimal.ZERO)
        .valorGeral(new BigDecimal("150.00"))
        .build())
    .build();
```

---

## Integração com Outros Componentes

### TissXmlGenerator
```java
TissGuiaDTO guia = buildGuia();
String xml = tissXmlGenerator.generateXml(guia);
```

### TissSubmissionClient
```java
TissGuiaDTO guia = buildGuia();
TissSubmissionResponse response = submissionClient.submitGuia(guia);
```

### TissSchemaValidator
```java
String xml = marshallToXml(guia);
boolean valid = schemaValidator.validateXml(xml, "SADT-SP");
```

---

## Tipos de Guia TISS

### Guias Implementadas
- ✅ **SP/SADT**: Serviço Profissional / SADT (esta classe)

### Guias Planejadas
- ⚠️ **Consulta**: Consultas médicas (similar a SP/SADT)
- ⚠️ **Internação**: Resumo de internação hospitalar
- ⚠️ **Urgência/Emergência**: Atendimento de urgência
- ⚠️ **Tratamento Odontológico**: Procedimentos odontológicos
- ⚠️ **Honorários Individuais**: Honorários médicos
- ⚠️ **Solicitação de Autorização**: Pré-autorização

**Recomendação**: Criar classes específicas para cada tipo ou usar herança/composição.

---

## Próximos Passos

### Fase 1: Validações Completas
- [ ] Implementar Bean Validation completa
- [ ] Adicionar validações de negócio
- [ ] Criar validador customizado

### Fase 2: Outros Tipos de Guia
- [ ] Criar TissGuiaInternacaoDTO
- [ ] Criar TissGuiaConsultaDTO
- [ ] Criar TissGuiaUrgenciaDTO

### Fase 3: Mapeamento Automático
- [ ] Integrar com MapStruct
- [ ] Converter de entidades JPA automaticamente
- [ ] Converter para entidades JPA

### Fase 4: Auditoria
- [ ] Adicionar campos de auditoria (createdAt, updatedAt)
- [ ] Implementar versionamento
- [ ] Rastreabilidade de mudanças

---

## Referências

### ANS
- **Manual TISS**: Componente Organizacional
- **Guia SP/SADT**: Especificação completa

### JAXB
- **Tutorial**: https://docs.oracle.com/javase/tutorial/jaxb/
- **Spec**: https://jakarta.ee/specifications/xml-binding/

### Lombok
- **Builder**: https://projectlombok.org/features/Builder
- **Data**: https://projectlombok.org/features/Data

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissGuiaDTO.java`
