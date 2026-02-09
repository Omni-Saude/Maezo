# Regras Clinicas da Operadora - DMN

## Visao Geral

Este repositorio contem as regras de decisao DMN (Decision Model and Notation) para auditoria clinica de procedimentos medicos sob a perspectiva da **OPERADORA** (plano de saude). As regras implementam criterios de autorizacao baseados nas Diretrizes de Utilizacao Terapeutica (DUT), normas da ANS e protocolos clinicos de sociedades medicas.

**Total de Regras: 936**
**Total de Especialidades: 31**
**TIER-1 Surgical Rules: 145 (2026-02-07)**

As regras seguem o padrao DMN 1.3 e sao executaveis no Camunda 8 Zeebe. Cada regra avalia a indicacao clinica de procedimentos atraves de tabelas de decisao com politica de acerto FIRST (primeira regra correspondente).

## Recent Updates

### 2026-02-07: TIER-1 Surgical Rules Generation
- **145 surgical DMN files** regenerated to TIER-1 quality standards
- **13 surgical specialties** covered with comprehensive clinical logic
- **27,260 lines** of production-ready DMN decision logic
- **100% compliance** with DUT ANS 2024, RN 465/2021, RN 428/2017
- **Surgical input pattern**: diagnosticoConfirmado, estadiamentoTumor, tratamentosPrevios, riscoCirurgico, laudoIndicacao
- **ASA risk classification** validation integrated
- **Prior treatment validation** mandatory for surgical authorizations
- See [SURGICAL_GENERATION_REPORT.md](SURGICAL_GENERATION_REPORT.md) for complete details

### Proposito

O objetivo destas regras e automatizar a avaliacao de solicitacoes de autorizacao medica, verificando:

- **Indicacoes clinicas** - Criterios que justificam a realizacao do procedimento
- **Contraindicacoes** - Condicoes que impedem a autorizacao
- **Documentacao necessaria** - Exames e laudos requeridos
- **Conformidade regulatoria** - Alinhamento com DUT/ANS

### Perspectiva: Operadora vs Hospital

| Aspecto | Operadora (este repositorio) | Hospital |
|---------|------------------------------|----------|
| Foco | Autorizacao clinica | Faturamento |
| Objetivo | Aprovar/reprovar procedimentos | Validar cobranca |
| Base normativa | DUT, protocolos clinicos | TISS, regras contratuais |
| Output principal | Aprovado/Reprovado/Pendente | Prosseguir/Bloquear/Alertar |

## Estrutura do Repositorio

```
regras-clinicas-operadora/
├── _index.json                    # Indice geral de especialidades
├── README.md                      # Este arquivo
│
├── alergia-e-imunologia/          # 15 regras
│   └── {codigo-tuss}/
│       ├── regra.dmn.xml
│       └── metadata.json
│
├── anatomia-patologica/           # 183 regras
├── anestesiologia/                # 15 regras
├── aparelho-digestivo/            # 26 regras
├── cabeca-e-pescoco-cirurgia/     # 11 regras
├── cardiologia/                   # 17 regras
├── cirurgia-geral/                # 5 regras
├── cirurgia-plastica/             # 3 regras
├── cirurgia-toracica/             # 11 regras
├── cirurgia-vascular/             # 8 regras
├── coluna-vertebral/              # 24 regras
├── consulta/                      # 4 regras
├── dermatologia/                  # 37 regras
├── exames-de-imagem/              # 46 regras
├── fisioterapia/                  # 52 regras
├── genetica/                      # 91 regras
├── ginecologia-e-obstetricia/     # 32 regras
├── hemoterapia/                   # 81 regras
├── mastologia/                    # 18 regras
├── medicina-nuclear/              # 43 regras
├── nefrologia/                    # 8 regras
├── neurologia-neurocirurgia/      # 20 regras
├── nutrologia/                    # 7 regras
├── oftalmologia/                  # 48 regras
├── oncologia/                     # 5 regras
├── ortopedia/                     # 10 regras
├── otorrinolaringologia/          # 25 regras
├── pneumologia/                   # 15 regras
├── radioterapia/                  # 25 regras
├── terapia-da-dor-e-acupuntura/   # 24 regras
└── urologia/                      # 34 regras
```

### Nomenclatura de Diretorios

Cada procedimento e organizado por seu **codigo TUSS** (Terminologia Unificada da Saude Suplementar):

```
{especialidade}/{codigo-tuss}/
├── regra.dmn.xml      # Tabela de decisao DMN
└── metadata.json      # Metadados do procedimento
```

**Exemplo:**
```
mastologia/30602149/
├── regra.dmn.xml      # Mastectomia Radical
└── metadata.json      # Metadados com inputs, outputs, referencias
```

## Categorias de Regras por Especialidade

### Especialidades Clinicas

| Especialidade | Regras | Descricao | Exemplos de Procedimentos |
|---------------|--------|-----------|---------------------------|
| **Alergia e Imunologia** | 15 | Testes alergicos, imunoterapia | Testes cutaneos, dessensibilizacao |
| **Anatomia Patologica** | 183 | Exames histopatologicos e citologicos | Biopsias, imunohistoquimica |
| **Anestesiologia** | 15 | Bloqueios e anestesias | Peridural, raquianestesia |
| **Aparelho Digestivo** | 26 | Cirurgias e procedimentos GI | Endoscopia, colonoscopia |
| **Cardiologia** | 17 | Procedimentos cardiovasculares | CDI, marca-passo, cateterismo |
| **Dermatologia** | 37 | Procedimentos dermatologicos | Biopsias de pele, fototerapia |
| **Genetica** | 91 | Testes geneticos e moleculares | NGS, sequenciamento, FISH |
| **Hemoterapia** | 81 | Transfusoes e afereses | Plasmaferese, transfusao |
| **Medicina Nuclear** | 43 | Cintilografias e PET-CT | PET-CT, cintilografia osso |
| **Nefrologia** | 8 | Procedimentos renais | Hemodialise, biopsia renal |
| **Pneumologia** | 15 | Procedimentos pulmonares | Broncoscopia, biopsia |

### Especialidades Cirurgicas

| Especialidade | Regras | Descricao | Exemplos de Procedimentos |
|---------------|--------|-----------|---------------------------|
| **Cabeca e Pescoco** | 11 | Cirurgias de cabeca/pescoco | Tireoidectomia, parotidectomia |
| **Cirurgia Geral** | 5 | Cirurgias abdominais gerais | Colecistectomia, apendicectomia |
| **Cirurgia Plastica** | 3 | Procedimentos reconstrutivos | Reconstrucao mamaria |
| **Cirurgia Toracica** | 11 | Cirurgias pulmonares | Lobectomia, resseccao |
| **Cirurgia Vascular** | 8 | Cirurgias vasculares | Endarterectomia, bypass |
| **Coluna Vertebral** | 24 | Cirurgias de coluna | Artrodese, discectomia |
| **Ginecologia e Obstetricia** | 32 | Procedimentos ginecologicos | Histerectomia, curetagem |
| **Mastologia** | 18 | Cirurgias mamarias | Mastectomia, quadrantectomia |
| **Neurologia/Neurocirurgia** | 20 | Cirurgias neurologicas | Craniotomia, DBS |
| **Oftalmologia** | 48 | Cirurgias oculares | Catarata, vitrectomia |
| **Ortopedia** | 10 | Cirurgias ortopedicas | Artroplastia, artroscopia |
| **Otorrinolaringologia** | 25 | Cirurgias ORL | Septoplastia, amigdalectomia |
| **Urologia** | 34 | Procedimentos urologicos | Prostatectomia, nefrectomia |

### Terapias e Tratamentos

| Especialidade | Regras | Descricao | Exemplos de Procedimentos |
|---------------|--------|-----------|---------------------------|
| **Exames de Imagem** | 46 | Diagnostico por imagem | RM, TC, mamografia |
| **Fisioterapia** | 52 | Reabilitacao fisica | Cinesioterapia, hidroterapia |
| **Nutrologia** | 7 | Terapia nutricional | Nutricao enteral/parenteral |
| **Oncologia** | 5 | Tratamentos oncologicos | Quimioterapia, imunoterapia |
| **Radioterapia** | 25 | Tratamentos radioterapicos | IMRT, braquiterapia |
| **Terapia da Dor/Acupuntura** | 24 | Tratamento da dor | Bloqueios, acupuntura |
| **Consulta** | 4 | Consultas medicas | Primeira consulta, retorno |

## Formato das Regras DMN

### Estrutura XML Padronizada

Todas as regras seguem o padrao DMN 1.3 com a seguinte estrutura:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             id="Definitions_{TUSS_CODE}"
             name="{Nome do Procedimento}"
             targetNamespace="http://camunda.org/schema/1.0/dmn">
  <!--
    TUSS {CODIGO} - {Nome do Procedimento}
    Versao: 2.0.0 (YYYY-MM-DD)

    Indicacoes:
    - Criterio 1 para aprovacao
    - Criterio 2 para aprovacao

    Contraindicacoes:
    - Condicao 1 para reprovacao
    - Condicao 2 para reprovacao

    Nota: Informacoes adicionais relevantes
  -->
  <decision id="Decision_{TUSS_CODE}" name="Auditoria de {Procedimento}">
    <decisionTable id="DecisionTable_{TUSS_CODE}" hitPolicy="FIRST">
      <!-- Inputs -->
      <input id="Input_1" label="Label do Input">
        <inputExpression id="InputExpression_1" typeRef="boolean">
          <text>nomeVariavelCamelCase</text>
        </inputExpression>
      </input>

      <!-- Outputs -->
      <output id="Output_1" label="Resultado" name="resultado" typeRef="string"/>
      <output id="Output_2" label="Observacao" name="observacao" typeRef="string"/>

      <!-- Regras de Contraindicacao (primeiro) -->
      <rule id="Rule_Contraindicacao_1">
        <description>Descricao da contraindicacao</description>
        <inputEntry><text>false</text></inputEntry>
        <outputEntry><text>"Reprovado"</text></outputEntry>
        <outputEntry><text>"Justificativa da reprovacao"</text></outputEntry>
      </rule>

      <!-- Regras de Aprovacao -->
      <rule id="Rule_Aprovado">
        <description>Criterios atendidos</description>
        <inputEntry><text>true</text></inputEntry>
        <outputEntry><text>"Aprovado"</text></outputEntry>
        <outputEntry><text>"Justificativa da aprovacao"</text></outputEntry>
      </rule>

      <!-- Fallback -->
      <rule id="Rule_Fallback">
        <description>Caso requer analise manual</description>
        <inputEntry><text>-</text></inputEntry>
        <outputEntry><text>"Pendente"</text></outputEntry>
        <outputEntry><text>"Requer analise por auditor medico"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>
```

### Politica de Acerto (Hit Policy)

Todas as regras utilizam `hitPolicy="FIRST"`:

- A primeira regra que corresponder aos inputs e executada
- Regras sao avaliadas na ordem definida (contraindicacoes primeiro)
- Ultima regra deve ser fallback para casos nao previstos

### Convencao de Inputs

Todos os inputs seguem a convencao **camelCase**:

| Padrao | Exemplo |
|--------|---------|
| Diagnosticos | `diagnosticoMalignidadeConfirmado` |
| Laudos | `laudoHistopatologicoAnexado` |
| Condicoes | `expectativaVidaSuperior1Ano` |
| Historicos | `historicoClinico` |
| Validacoes | `cidCompativelCancerMama` |

### Outputs Padronizados

| Output | Tipo | Descricao |
|--------|------|-----------|
| `resultado` | string | Decisao principal da regra |
| `observacao` | string | Justificativa detalhada |

### Valores de Resultado

| Valor | Descricao | Acao Requerida |
|-------|-----------|----------------|
| `Aprovado` | Procedimento autorizado | Liberacao automatica |
| `Reprovado` | Procedimento negado | Comunicar motivo ao prestador |
| `Pendente` | Aguarda informacoes | Solicitar documentacao adicional |

### Estrutura de Metadados (metadata.json)

```json
{
  "tussCode": "30602149",
  "procedure": "Mastectomia Radical ou Radical Modificada",
  "specialty": "Mastologia",
  "version": "2.0.0",
  "createdAt": "2026-02-05T00:00:00Z",
  "updatedAt": "2026-02-05T00:00:00Z",
  "hitPolicy": "FIRST",
  "inputs": [
    {
      "name": "diagnosticoMalignidadeConfirmado",
      "type": "boolean",
      "label": "Diagnostico de Malignidade Confirmado"
    }
  ],
  "outputs": [
    {
      "name": "resultado",
      "type": "string",
      "values": ["Aprovado", "Reprovado", "Pendente"]
    }
  ],
  "bundledProcedures": ["30602130"],
  "bundleNote": "Linfadenectomia axilar inclusa",
  "references": [
    "Consenso Brasileiro de Mastologia 2023",
    "NCCN Guidelines"
  ],
  "changelog": [
    {
      "version": "2.0.0",
      "date": "2026-02-05",
      "changes": "Migrado para nova estrutura"
    }
  ]
}
```

## Conformidade Regulatoria

### ANS - Agencia Nacional de Saude Suplementar

| Normativo | Descricao | Aplicacao |
|-----------|-----------|-----------|
| **RN 465/2021** | Rol de Procedimentos e Eventos em Saude | Cobertura obrigatoria |
| **RN 469/2021** | Atualizacao do Rol | Novos procedimentos |
| **RN 428/2017** | Atualizacoes do Rol | Procedimentos vigentes |
| **RN 259/2011** | Garantia de atendimento | Prazos maximos |
| **RN 171/2008** | Prazos de autorizacao | Tempos de resposta |

### DUT - Diretrizes de Utilizacao Terapeutica

As DUT estabelecem criterios de indicacao para procedimentos especificos:

| Categoria | Descricao | Exemplos |
|-----------|-----------|----------|
| **Procedimentos** | Criterios para cirurgias e procedimentos | Mastectomia, artroplastia |
| **Exames** | Indicacoes para exames diagnosticos | PET-CT, RM |
| **Terapias** | Protocolos para tratamentos | Quimioterapia, radioterapia |

### TUSS - Terminologia Unificada da Saude Suplementar

Todas as regras sao identificadas pelo codigo TUSS:

| Faixa TUSS | Categoria |
|------------|-----------|
| 10xxxxxx | Consultas |
| 20xxxxxx | Exames e diagnosticos |
| 30xxxxxx | Procedimentos cirurgicos |
| 40xxxxxx | Exames de imagem e laboratoriais |
| 50xxxxxx | Outros procedimentos |

### Protocolos Clinicos de Referencia

| Especialidade | Sociedade/Protocolo |
|---------------|---------------------|
| Cardiologia | SBCCV, SOBRAC, ACC/AHA/ESC Guidelines |
| Mastologia | Consenso Brasileiro de Mastologia, NCCN |
| Oncologia | NCCN, ESMO Guidelines |
| Ortopedia | SBOT, AAOS Guidelines |
| Radiologia | CBR, ACR Guidelines |
| Anestesiologia | SBA Guidelines |

### Classificacao de Indicacoes (Cardiologia)

Para procedimentos cardiologicos, as regras utilizam a classificacao padrao:

| Classe | Descricao | Resultado |
|--------|-----------|-----------|
| **Classe I** | Indicacao consensual, beneficio comprovado | Aprovado |
| **Classe IIa** | Indicacao aceitavel, evidencia favoravel | Aprovado |
| **Classe IIb** | Indicacao possivel, evidencia limitada | Aprovado (com ressalvas) |
| **Classe III** | Nao indicado, sem beneficio ou risco | Reprovado |

## Uso das Regras

### Integracao com Camunda 8 Zeebe

As regras sao executadas como Decision Tables no Camunda 8:

```bash
# Avaliar uma decisao de autorizacao
zbctl evaluate decision \
  --decisionId "Decision_30602149" \
  --variables '{
    "diagnosticoMalignidadeConfirmado": true,
    "laudoHistopatologicoAnexado": true,
    "solicitouLinfadenectomiaAxilar": false,
    "cidCompativelCancerMama": true
  }'
```

### Exemplo de Resposta

```json
{
  "decisionId": "Decision_30602149",
  "decisionName": "Auditoria de Mastectomia Radical",
  "result": {
    "resultado": "Aprovado",
    "observacao": "Aprovado - Mastectomia radical em conformidade com criterios clinicos. Diagnostico de malignidade confirmado."
  }
}
```

### Fluxo de Autorizacao

```
[Solicitacao de Autorizacao]
        │
        ▼
[Validacao TISS/Dados Basicos]
        │
        ▼
[Camunda 8 Zeebe]
        │
        ▼
[DMN Decision Engine - Regras Clinicas]
        │
        ├─── Aprovado → [Liberacao Automatica]
        │
        ├─── Pendente → [Solicitar Documentacao]
        │                       │
        │                       ▼
        │               [Nova Avaliacao]
        │
        └─── Reprovado → [Comunicar Negativa]
                              │
                              ▼
                        [Possibilidade de Recurso]
```

### Tipos de Autorizacao

| Tipo | Descricao | Regras Aplicaveis |
|------|-----------|-------------------|
| **Automatica** | Liberacao sem analise manual | Procedimentos de baixo risco |
| **Depende de Regras** | Avaliacao por DMN | Maioria dos procedimentos |
| **Manual** | Analise por auditor | Casos complexos, oncologia |

## Estatisticas

### Resumo por Especialidade

| Especialidade | Total de Regras | % do Total |
|---------------|-----------------|------------|
| Anatomia Patologica | 183 | 19.6% |
| Genetica | 91 | 9.7% |
| Hemoterapia | 81 | 8.7% |
| Fisioterapia | 52 | 5.6% |
| Oftalmologia | 48 | 5.1% |
| Exames de Imagem | 46 | 4.9% |
| Medicina Nuclear | 43 | 4.6% |
| Dermatologia | 37 | 4.0% |
| Urologia | 34 | 3.6% |
| Ginecologia e Obstetricia | 32 | 3.4% |
| Aparelho Digestivo | 26 | 2.8% |
| Radioterapia | 25 | 2.7% |
| Otorrinolaringologia | 25 | 2.7% |
| Terapia da Dor/Acupuntura | 24 | 2.6% |
| Coluna Vertebral | 24 | 2.6% |
| Neurologia/Neurocirurgia | 20 | 2.1% |
| Mastologia | 18 | 1.9% |
| Cardiologia | 17 | 1.8% |
| Pneumologia | 15 | 1.6% |
| Anestesiologia | 15 | 1.6% |
| Alergia e Imunologia | 15 | 1.6% |
| Cirurgia Toracica | 11 | 1.2% |
| Cabeca e Pescoco | 11 | 1.2% |
| Ortopedia | 10 | 1.1% |
| Nefrologia | 8 | 0.9% |
| Cirurgia Vascular | 8 | 0.9% |
| Nutrologia | 7 | 0.7% |
| Oncologia | 5 | 0.5% |
| Cirurgia Geral | 5 | 0.5% |
| Consulta | 4 | 0.4% |
| Cirurgia Plastica | 3 | 0.3% |
| **Total** | **936** | **100%** |

### Distribuicao por Tipo de Procedimento

| Tipo | Regras | Descricao |
|------|--------|-----------|
| Cirurgico | ~350 | Procedimentos invasivos |
| Diagnostico | ~300 | Exames e testes |
| Terapeutico | ~200 | Tratamentos e terapias |
| Consulta | ~86 | Consultas e avaliacoes |

### Complexidade das Regras

| Complexidade | Criterios | % Regras |
|--------------|-----------|----------|
| **Baixa** | 2-3 inputs, autorizacao automatica | ~30% |
| **Media** | 4-6 inputs, logica condicional | ~50% |
| **Alta** | 7+ inputs, multiplas classes | ~20% |

## Manutencao

### Adicionando Novas Regras

1. **Criar diretorio do procedimento:**
   ```bash
   mkdir -p {especialidade}/{codigo-tuss}
   ```

2. **Criar arquivo DMN:**
   - Usar template padrao
   - Documentar indicacoes e contraindicacoes no comentario XML
   - Seguir convencao de inputs (camelCase)
   - Incluir regra de fallback

3. **Criar metadata.json:**
   - Documentar inputs e outputs
   - Incluir referencias normativas
   - Registrar changelog

4. **Atualizar indice:**
   - Incrementar contagem em `_index.json`

5. **Criar testes:**
   - Adicionar testes em `/tests/dmn/regras-clinicas-operadora/`

### Validacao de Regras

```bash
# Validar XML de todas as regras
find . -name "regra.dmn.xml" -exec xmllint --noout {} \;

# Verificar hitPolicy FIRST em todas as regras
grep -r "hitPolicy=" --include="*.xml" . | grep -v "FIRST"

# Contar regras por especialidade
for dir in */; do
  count=$(find "$dir" -name "regra.dmn.xml" | wc -l)
  echo "$dir: $count"
done

# Verificar inputs em camelCase
grep -r "<text>[a-z]" --include="*.xml" . | head -20
```

### Checklist de Qualidade

- [ ] HitPolicy = FIRST
- [ ] Inputs em camelCase
- [ ] Output `resultado` com valores padrao (Aprovado/Reprovado/Pendente)
- [ ] Contraindicacoes primeiro na ordem das regras
- [ ] Regra de fallback no final
- [ ] Comentario XML com indicacoes/contraindicacoes
- [ ] Metadata.json completo
- [ ] Referencias normativas documentadas

### Versionamento

As regras seguem versionamento semantico (SemVer):

| Tipo | Descricao | Exemplo |
|------|-----------|---------|
| **MAJOR** | Mudanca incompativel | Novo input obrigatorio |
| **MINOR** | Nova funcionalidade | Nova regra de classe |
| **PATCH** | Correcao | Ajuste de texto |

## Integracao com Sistemas

### Sistemas de Origem de Dados

| Sistema | Dados | Uso na Regra |
|---------|-------|--------------|
| Prontuario Eletronico | Diagnosticos, CIDs | Validacao de indicacao |
| LIS (Laboratorio) | Resultados de exames | Criterios de aprovacao |
| PACS (Imagens) | Laudos radiologicos | Documentacao comprobatoria |
| Sistema de Autorizacao | Historico de procedimentos | Verificacao de duplicidade |

### Fluxo de Dados

```
[Prestador - Guia TISS]
        │
        ▼
[Portal de Autorizacao]
        │
        ├─── Validacao Cadastral
        │
        ├─── Verificacao de Cobertura
        │
        ▼
[Motor de Regras DMN]
        │
        ├─── Carregar regra por codigo TUSS
        │
        ├─── Avaliar inputs clinicos
        │
        └─── Retornar resultado + observacao
                │
                ▼
        [Sistema de Autorizacao]
                │
                ├─── Aprovado → Senha de autorizacao
                │
                ├─── Pendente → Pendencia de documentacao
                │
                └─── Reprovado → Negativa fundamentada
```

## Glossario

| Termo | Definicao |
|-------|-----------|
| **ANS** | Agencia Nacional de Saude Suplementar - orgao regulador |
| **CAVD** | Cardiomiopatia Arritmogenica do Ventriculo Direito |
| **CDI** | Cardioversor-Desfibrilador Implantavel |
| **CID-10** | Classificacao Internacional de Doencas, 10a revisao |
| **CMH** | Cardiomiopatia Hipertrofica |
| **DUT** | Diretrizes de Utilizacao Terapeutica |
| **FV** | Fibrilacao Ventricular |
| **Glosa** | Negativa de pagamento por parte da operadora |
| **Histopatologico** | Exame microscopico de tecido para diagnostico |
| **LGPD** | Lei Geral de Protecao de Dados |
| **MSC** | Morte Subita Cardiaca |
| **OPME** | Orteses, Proteses e Materiais Especiais |
| **RMC** | Ressonancia Magnetica Cardiaca |
| **ROL** | Rol de Procedimentos e Eventos em Saude da ANS |
| **SB** | Sindrome de Brugada |
| **SQTLc** | Sindrome do QT Longo Congenito |
| **TISS** | Troca de Informacao em Saude Suplementar |
| **TUSS** | Terminologia Unificada da Saude Suplementar |
| **TV** | Taquicardia Ventricular |
| **TVS** | Taquicardia Ventricular Sustentada |
| **TVNS** | Taquicardia Ventricular Nao Sustentada |
| **TVPC** | Taquicardia Ventricular Polimorfica Catecolaminergica |
| **VE** | Ventriculo Esquerdo |

## Exemplos de Regras por Especialidade

### Cardiologia - CDI (30904161)

**Indicacoes (Classe I e IIa):**
- Sobrevivente de parada cardiaca por TV/FV
- CMH com fatores de risco para MSC
- CAVD com doenca extensa

**Contraindicacoes (Classe III):**
- Expectativa de vida inferior a 1 ano
- Paciente assintomatico sem fatores de risco

### Mastologia - Mastectomia Radical (30602149)

**Indicacoes:**
- Neoplasia maligna da mama confirmada (CID C50.x)
- Laudo histopatologico anexado

**Contraindicacoes:**
- Ausencia de diagnostico de malignidade
- CID incompativel com cancer de mama
- Cobranca separada de linfadenectomia (inclusa)

### Exames de Imagem - Mamografia (40808041)

**Indicacoes:**
- Pedido medico presente
- Rastreamento ou investigacao clinica

**Contraindicacoes:**
- Paciente gestante (exceto urgencia clinica justificada)

## Suporte

### Documentacao Relacionada

- `../regras-administrativas-hospital/` - Regras de faturamento hospitalar
- `/docs/clinical-alerts/` - Alertas clinicos de seguranca
- `/tests/dmn/` - Testes automatizados das regras

### Contato

- **Equipe de Auditoria Medica**: Duvidas sobre criterios clinicos
- **Equipe de Regulacao**: Duvidas sobre normas ANS
- **Equipe de TI**: Suporte tecnico e integracao

---

**Versao**: 2.0.0
**Ultima Atualizacao**: 2026-02-06
**Padrao DMN**: 1.3
**Motor de Execucao**: Camunda 8 Zeebe
**Total de Regras**: 936
**Total de Especialidades**: 31
