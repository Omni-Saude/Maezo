# Regras Administrativas Hospitalares - DMN

## Visao Geral

Este repositorio contem as regras de decisao DMN (Decision Model and Notation) para gestao do ciclo de receita hospitalar. As regras sao projetadas para automatizar a validacao de faturamento, conformidade regulatoria, prevencao de glosas e gestao de recebiveis no contexto da saude suplementar brasileira.

**Total de Regras: 202**

As regras seguem o padrao DMN 1.3 e sao executaveis no Camunda 8 Zeebe. Cada regra implementa logica de decisao baseada em tabelas de decisao com politica de acerto FIRST (primeira regra correspondente).

## Estrutura do Repositorio

```
regras-administrativas-hospital/
├── AUTH/              # Regras de Autorizacao (38 regras)
│   ├── APPEAL/        # Recursos de autorizacao
│   ├── CODING/        # Codificacao de procedimentos
│   ├── DOCUMENTATION/ # Documentacao requerida
│   ├── EXTENSION/     # Prorrogacao de autorizacoes
│   ├── PREAUTH/       # Pre-autorizacao
│   ├── TIMING/        # Prazos de autorizacao
│   └── URGENCY/       # Autorizacoes de urgencia
│
├── BILL/              # Regras de Faturamento (43 regras)
│   ├── BUNDLE/        # Pacotes de procedimentos
│   ├── BUNDLE-EXT/    # Pacotes estendidos
│   ├── MATERIAL/      # Validacao de materiais
│   ├── MED/           # Medicamentos de alto custo
│   ├── MODIFIER/      # Modificadores de procedimento
│   ├── OPME/          # Orteses, proteses e materiais
│   ├── QUANTITY/      # Validacao de quantidades
│   ├── SPECIALTY/     # Especialidades medicas
│   ├── TIME/          # Validacao temporal
│   └── UPCODE/        # Prevencao de upcoding
│
├── COMP/              # Regras de Conformidade (43 regras)
│   ├── ACCRED/        # Acreditacao hospitalar
│   ├── ANS/           # Conformidade ANS
│   ├── AUDIT/         # Auditoria interna
│   ├── COUNCIL/       # Conselhos profissionais
│   ├── DEADLINE/      # Prazos regulatorios
│   ├── INTL/          # Pacientes internacionais
│   ├── LGPD/          # Protecao de dados
│   └── TISS/          # Padrao TISS
│
├── DENY/              # Regras de Prevencao de Glosas (51 regras)
│   ├── APPEAL/        # Recursos e reclamacoes
│   ├── DUPLICATE/     # Duplicidade de cobranca
│   ├── MEDICAL/       # Necessidade medica
│   ├── MISSING/       # Documentacao faltante
│   ├── PAYER/         # Padroes por operadora
│   ├── PREDICT/       # Previsao de glosas
│   └── TIMING/        # Prazos de apresentacao
│
├── RECV/              # Regras de Recebiveis (27 regras)
│   ├── AGED/          # Aging de recebiveis
│   ├── GLOSA/         # Gestao de glosas
│   ├── NEGO/          # Negociacao de dividas
│   ├── PARTIAL/       # Pagamentos parciais
│   ├── PROVISION/     # Provisoes (CPC 25)
│   ├── REWORK/        # Retrabalho de contas
│   └── WRITEOFF/      # Baixa de incobraveis
│
├── docs/              # Documentacao adicional
└── templates/         # Templates de regras
```

## Categorias de Regras

### AUTH - Autorizacao (38 regras)

Regras para validacao e gestao do fluxo de autorizacoes medicas.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| APPEAL | 5 | Recursos contra negativas de autorizacao |
| CODING | 5 | Validacao de codigos CID-10 e TUSS |
| DOCUMENTATION | 5 | Documentacao exigida para autorizacao |
| EXTENSION | 8 | Prorrogacao de autorizacoes (urgencia, UTI, oncologia, transplante, tratamento cronico, pediatria) |
| PREAUTH | 5 | Fluxos de pre-autorizacao |
| TIMING | 5 | Validacao de prazos de autorizacao |
| URGENCY | 5 | Autorizacoes de urgencia e emergencia |

**Casos de Uso:**
- Validacao de prorrogacao de internacao em UTI
- Autorizacao de procedimentos oncologicos
- Gestao de autorizacoes para transplantes
- Controle de prazo de validade de autorizacoes

### BILL - Faturamento (43 regras)

Regras para validacao do faturamento hospitalar.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| BUNDLE | 5 | Pacotes de procedimentos (cirurgias, diarias) |
| BUNDLE-EXT | 5 | Pacotes estendidos (cardiaca, ortopedia, oncologia, maternidade) |
| MATERIAL | 5 | Validacao de materiais hospitalares |
| MED | 3 | Medicamentos de alto custo e controlados |
| MODIFIER | 5 | Modificadores de procedimento (bilateral, multiplo) |
| OPME | 3 | Orteses, proteses e materiais especiais |
| QUANTITY | 5 | Validacao de quantidades faturadas |
| SPECIALTY | 2 | Especialidades (hiperbarica, PET-CT) |
| TIME | 5 | Validacao temporal de procedimentos |
| UPCODE | 5 | Prevencao de upcoding (superfaturamento) |

**Casos de Uso:**
- Validacao de pacotes cirurgicos
- Controle de quantidade de materiais por procedimento
- Prevencao de cobranca duplicada de OPME
- Verificacao de modificadores de procedimento

### COMP - Conformidade (43 regras)

Regras de conformidade regulatoria e normativa.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| ACCRED | 10 | Acreditacao hospitalar (ONA, JCI, VISA, CNES, ISO) |
| ANS | 5 | Conformidade com normas ANS e ROL |
| AUDIT | 5 | Auditoria interna e externa |
| COUNCIL | 5 | Conselhos profissionais (CRM, COREN, CRF, CREFITO, CRP) |
| DEADLINE | 5 | Prazos regulatorios e legais |
| INTL | 3 | Pacientes internacionais e turismo medico |
| LGPD | 5 | Lei Geral de Protecao de Dados (Lei 13.709/2018) |
| TISS | 5 | Padrao TISS de comunicacao |

**Casos de Uso:**
- Validacao de cobertura conforme ROL ANS
- Verificacao de cumprimento da LGPD
- Controle de certificacoes e acreditacoes
- Validacao de registro profissional

### DENY - Prevencao de Glosas (51 regras)

Regras para prevencao e gestao de glosas (negativas de pagamento).

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| APPEAL | 6 | Gestao de recursos contra glosas |
| DUPLICATE | 7 | Prevencao de cobranca duplicada |
| MEDICAL | 7 | Validacao de necessidade medica |
| MISSING | 7 | Documentacao faltante ou incompleta |
| PAYER | 10 | Regras especificas por operadora (Unimed, Bradesco, SulAmerica, Porto Seguro, etc.) |
| PREDICT | 7 | Previsao de risco de glosa |
| TIMING | 7 | Prazos de apresentacao de contas |

**Casos de Uso:**
- Prevencao de glosas por duplicidade
- Validacao de justificativa medica
- Controle de prazo de 180 dias para apresentacao
- Gestao de recursos em segunda instancia

### RECV - Recebiveis (27 regras)

Regras para gestao de contas a receber e provisoes.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| AGED | 3 | Aging de recebiveis por faixa de vencimento |
| GLOSA | 4 | Gestao de valores glosados |
| NEGO | 8 | Negociacao de dividas e acordos |
| PARTIAL | 2 | Pagamentos parciais |
| PROVISION | 4 | Provisoes para perdas (CPC 25) |
| REWORK | 4 | Retrabalho e reapresentacao de contas |
| WRITEOFF | 2 | Baixa de incobraveis |

**Casos de Uso:**
- Classificacao de aging de recebiveis
- Calculo de provisao para perdas conforme CPC 25
- Gestao de acordos de pagamento
- Controle de reapresentacao de contas glosadas

## Formato das Regras DMN

### Estrutura XML

Todas as regras seguem o padrao DMN 1.3 com a seguinte estrutura:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  ============================================================================
  RULE-ID - Nome da Regra
  ============================================================================
  Versao: 1.0.0
  Categoria: CATEGORIA-SUBCATEGORIA
  Perspectiva: HOSPITAL (Prestador)

  INDICACOES: Quando prosseguir com o faturamento
  CONTRAINDICACOES: Quando bloquear o faturamento
  REFERENCIAS NORMATIVAS: Legislacao aplicavel
  ============================================================================
-->
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             id="Definitions_RULE_ID"
             name="Nome da Regra"
             targetNamespace="http://camunda.org/schema/1.0/dmn">

  <decision id="Decision_RULE_ID" name="Descricao">
    <decisionTable id="DecisionTable_RULE_ID" hitPolicy="FIRST">
      <!-- Inputs -->
      <input id="Input_1" label="Label">
        <inputExpression typeRef="tipo">
          <text>variavel</text>
        </inputExpression>
      </input>

      <!-- Outputs -->
      <output id="Output_1" label="Resultado" name="resultado" typeRef="string">
        <outputValues><text>"Prosseguir", "Bloquear", "Alertar", "Revisar"</text></outputValues>
      </output>

      <!-- Rules -->
      <rule id="Rule_1">
        <inputEntry><text>condicao</text></inputEntry>
        <outputEntry><text>"resultado"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>
```

### Politica de Acerto (Hit Policy)

Todas as regras utilizam `hitPolicy="FIRST"`:
- A primeira regra que corresponder aos inputs e executada
- Regras sao avaliadas na ordem definida
- Ultima regra deve ser fallback para casos nao previstos

### Outputs Padronizados

| Output | Tipo | Descricao |
|--------|------|-----------|
| `resultado` | string | Decisao da regra |
| `observacao` | string | Mensagem explicativa |
| `prazoStatus` | string | Status do prazo regulatorio |
| `diasRestantes` | number | Dias restantes para acao |

### Valores de Resultado

| Valor | Descricao | Acao Requerida |
|-------|-----------|----------------|
| `Prosseguir` | Aprovado para faturamento | Nenhuma - seguir fluxo normal |
| `Bloquear` | Bloqueado - requer correcao | Corrigir antes de faturar |
| `Alertar` | Alerta - verificar antes de prosseguir | Revisar e confirmar |
| `Revisar` | Revisao manual necessaria | Encaminhar para analise |

### Valores de Prazo Status

| Valor | Descricao | Significado |
|-------|-----------|-------------|
| `DENTRO_PRAZO` | Dentro do prazo regulatorio | OK - sem urgencia |
| `ALERTA_PROXIMIDADE` | Proximo do vencimento | Atencao - priorizar |
| `PRAZO_EXCEDIDO` | Prazo expirado | Critico - risco de perda |

## Conformidade Regulatoria

### ANS - Agencia Nacional de Saude Suplementar

| Normativo | Descricao | Aplicacao |
|-----------|-----------|-----------|
| RN 465/2021 | Rol de Procedimentos e Eventos em Saude | Cobertura obrigatoria |
| RN 469/2021 | Atualizacao do Rol | Novos procedimentos |
| RN 395/2016 | Portabilidade de Carencias | Migracao entre planos |
| RN 412/2016 | Contratacao de Planos | Clausulas contratuais |
| RN 424/2017 | Cobertura Assistencial | Abrangencia geografica |
| RN 171/2008 | Prazos de Autorizacao | Tempos maximos |

### LGPD - Lei Geral de Protecao de Dados (Lei 13.709/2018)

| Artigo | Tema | Aplicacao |
|--------|------|-----------|
| Art. 7 | Bases legais de tratamento | Consentimento e execucao contratual |
| Art. 11 | Dados sensiveis de saude | Tratamento especial |
| Art. 18 | Direitos dos titulares | Acesso, correcao, exclusao |
| Art. 48 | Notificacao de incidentes | Comunicacao a ANPD |

### TISS - Troca de Informacao em Saude Suplementar

| Versao | Componente | Aplicacao |
|--------|------------|-----------|
| 4.01.00 | Padrao atual | Formato obrigatorio |
| Guia SADT | Servicos Auxiliares | Exames e terapias |
| Guia Internacao | Hospitalizacao | Diarias e procedimentos |
| Guia Honorarios | Profissionais | Pagamento medico |

### CPC 25 - Provisoes, Passivos e Ativos Contingentes

| Conceito | Descricao | Aplicacao |
|----------|-----------|-----------|
| Provisao | Passivo de prazo/valor incerto | Glosas provaveis |
| Passivo contingente | Obrigacao possivel | Glosas possiveis |
| Ativo contingente | Direito possivel | Recuperacao de glosas |
| Reversao | Anulacao de provisao | Recebimento de valor glosado |

### Conselhos Profissionais

| Conselho | Profissional | Validacao |
|----------|--------------|-----------|
| CRM | Medicos | Registro ativo |
| COREN | Enfermeiros | Categoria/registro |
| CRF | Farmaceuticos | Habilitacao |
| CREFITO | Fisioterapeutas | Especialidade |
| CRP | Psicologos | Registro ativo |

## Uso das Regras

### Integracao com Camunda 8 Zeebe

As regras sao executadas como Decision Tables no Camunda 8:

```bash
# Avaliar uma decisao
zbctl evaluate decision \
  --decisionId "Decision_COMP_ANS_001" \
  --variables '{"dentroDoRolANS": true, "cobertoContrato": true, "indicacaoClinicaValida": true}'
```

### Estrutura de Diretorios por Regra

```
{CATEGORIA}/{SUBCATEGORIA}/{RULE_ID}/
├── regra.dmn.xml      # Tabela de decisao DMN
└── metadata.json      # Metadados da regra
```

### Exemplo de Metadata JSON

```json
{
  "ruleId": "COMP-ANS-001",
  "ruleName": "Cobertura ROL ANS (RN 465/2021)",
  "version": "1.0.0",
  "category": "COMP",
  "subcategory": "ANS",
  "perspective": "HOSPITAL",
  "description": "Valida se procedimento esta dentro do ROL ANS",
  "inputs": [
    {
      "name": "dentroDoRolANS",
      "type": "boolean",
      "description": "Procedimento consta no ROL ANS vigente"
    }
  ],
  "outputs": [
    {
      "name": "resultado",
      "type": "string",
      "values": ["Prosseguir", "Bloquear", "Alertar", "Revisar"]
    }
  ],
  "regulations": [
    {
      "code": "RN-465-2021",
      "name": "Rol de Procedimentos",
      "source": "ANS"
    }
  ]
}
```

## Estatisticas

### Resumo por Categoria

| Categoria | Total de Regras | Subcategorias |
|-----------|-----------------|---------------|
| AUTH | 38 | 7 |
| BILL | 43 | 10 |
| COMP | 43 | 8 |
| DENY | 51 | 7 |
| RECV | 27 | 7 |
| **Total** | **202** | **39** |

### Detalhamento por Subcategoria

#### AUTH - Autorizacao
| Subcategoria | Regras |
|--------------|--------|
| EXTENSION | 8 |
| PREAUTH | 5 |
| TIMING | 5 |
| DOCUMENTATION | 5 |
| CODING | 5 |
| APPEAL | 5 |
| URGENCY | 5 |

#### BILL - Faturamento
| Subcategoria | Regras |
|--------------|--------|
| BUNDLE | 5 |
| BUNDLE-EXT | 5 |
| MATERIAL | 5 |
| MED | 3 |
| MODIFIER | 5 |
| OPME | 3 |
| QUANTITY | 5 |
| SPECIALTY | 2 |
| TIME | 5 |
| UPCODE | 5 |

#### COMP - Conformidade
| Subcategoria | Regras |
|--------------|--------|
| ACCRED | 10 |
| ANS | 5 |
| AUDIT | 5 |
| COUNCIL | 5 |
| DEADLINE | 5 |
| INTL | 3 |
| LGPD | 5 |
| TISS | 5 |

#### DENY - Prevencao de Glosas
| Subcategoria | Regras |
|--------------|--------|
| APPEAL | 6 |
| DUPLICATE | 7 |
| MEDICAL | 7 |
| MISSING | 7 |
| PAYER | 10 |
| PREDICT | 7 |
| TIMING | 7 |

#### RECV - Recebiveis
| Subcategoria | Regras |
|--------------|--------|
| AGED | 3 |
| GLOSA | 4 |
| NEGO | 8 |
| PARTIAL | 2 |
| PROVISION | 4 |
| REWORK | 4 |
| WRITEOFF | 2 |

## Manutencao

### Adicionando Novas Regras

1. **Criar diretorio da regra:**
   ```bash
   mkdir -p {CATEGORIA}/{SUBCATEGORIA}/{RULE_ID}
   ```

2. **Criar arquivo DMN:**
   - Copiar template de `templates/dmn-rule-template.xml`
   - Preencher inputs, outputs e regras
   - Documentar indicacoes e contraindicacoes

3. **Criar metadata JSON:**
   - Usar schema de `templates/metadata-schema.json`
   - Documentar inputs, outputs e regulamentacoes

4. **Atualizar indice:**
   - Adicionar entrada em `HOSPITAL_RULES_INDEX.json`

5. **Criar testes:**
   - Adicionar testes em `/tests/dmn/`

### Validacao

```bash
# Validar XML das regras
find . -name "regra.dmn.xml" -exec xmllint --noout {} \;

# Executar testes
pytest tests/dmn/ -v

# Verificar estrutura
find . -type d -name "*-*-*" | wc -l  # Deve retornar 202
```

### Convencoes de Nomenclatura

| Elemento | Padrao | Exemplo |
|----------|--------|---------|
| Categoria | MAIUSCULAS (3-4 letras) | AUTH, BILL, COMP |
| Subcategoria | MAIUSCULAS | APPEAL, BUNDLE |
| Rule ID | CATEGORIA-SUBCATEGORIA-NNN | COMP-ANS-001 |
| Arquivo DMN | regra.dmn.xml | - |
| Metadata | metadata.json | - |

### Versionamento

As regras seguem versionamento semantico (SemVer):
- **MAJOR**: Mudanca incompativel (novo output obrigatorio)
- **MINOR**: Nova funcionalidade (nova regra na tabela)
- **PATCH**: Correcao de bug (ajuste de texto)

## Integracao com Sistemas

### Sistemas de Origem

| Sistema | Dados | Uso |
|---------|-------|-----|
| TASY | Prontuario eletronico | Dados clinicos |
| LIS | Laboratorio | Resultados de exames |
| PACS | Imagens | Laudos radiologicos |
| Farmacia | Medicamentos | Prescricoes |
| Faturamento | Contas | Valores e procedimentos |

### Fluxo de Integracao

```
[Evento de Faturamento]
        │
        ▼
[Camunda 8 Zeebe]
        │
        ▼
[DMN Decision Engine]
        │
        ├─── Prosseguir → [Faturar para Operadora]
        │
        ├─── Alertar → [Revisao Humana] → [Decisao]
        │
        ├─── Bloquear → [Correcao] → [Resubmeter]
        │
        └─── Revisar → [Analise Especializada]
```

## Glossario

| Termo | Definicao |
|-------|-----------|
| ANS | Agencia Nacional de Saude Suplementar |
| CID-10 | Classificacao Internacional de Doencas, 10a revisao |
| DUT | Diretrizes de Utilizacao Terapeutica |
| Glosa | Negativa de pagamento por parte da operadora |
| LGPD | Lei Geral de Protecao de Dados |
| OPME | Orteses, Proteses e Materiais Especiais |
| ROL | Rol de Procedimentos e Eventos em Saude |
| TISS | Troca de Informacao em Saude Suplementar |
| TUSS | Terminologia Unificada da Saude Suplementar |

## Suporte

### Documentacao Relacionada

- `docs/RULE_CREATION_GUIDE.md` - Guia de criacao de novas regras
- `docs/HOSPITAL_RULES_BLUEPRINT.md` - Estrategia de regras
- `templates/dmn-rule-template.xml` - Template DMN padrao
- `templates/metadata-schema.json` - Schema de metadados

### Contato

- **Equipe de Faturamento**: Duvidas sobre regras de billing
- **Equipe de Compliance**: Duvidas regulatorias
- **Equipe de TI**: Suporte tecnico e integracao

---

**Versao**: 1.0.0
**Ultima Atualizacao**: 2026-02-06
**Padrao DMN**: 1.3
**Motor de Execucao**: Camunda 8 Zeebe
