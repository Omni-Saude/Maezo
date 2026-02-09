# Alertas Clinicos - DMN

## Visao Geral

Este repositorio contem as regras de decisao DMN (Decision Model and Notation) para alertas clinicos e seguranca do paciente. As regras sao projetadas para detectar interacoes medicamentosas, sindromes clinicas, alteracoes laboratoriais criticas, escores de alerta precoce e avaliacoes de risco no contexto hospitalar brasileiro.

**Total de Regras: 265**

As regras seguem o padrao DMN 1.3 e sao executaveis no Camunda 8 Zeebe. Cada regra implementa logica de decisao baseada em tabelas de decisao com politica de acerto FIRST (primeira regra correspondente). As regras utilizam outputs padronizados para garantir consistencia no sistema de alertas.

## Estrutura do Repositorio

```
alertas-clinicos/
├── DDI/              # Interacoes Droga-Droga (50 regras)
│   ├── CONTRAIND/    # Contraindicacoes absolutas
│   ├── BLEED/        # Risco de sangramento
│   ├── HEPATO/       # Hepatotoxicidade
│   ├── NEPHRO/       # Nefrotoxicidade
│   └── QT/           # Prolongamento QT
│
├── DDX/              # Diagnosticos Diferenciais (35 regras)
│   ├── ALLERGY/      # Reacoes alergicas
│   ├── CARDIAC/      # Sindromes cardiacas
│   ├── NEURO/        # Sindromes neurologicas
│   ├── RENAL/        # Sindromes renais
│   └── RESPIRATORY/  # Sindromes respiratorias
│
├── DLI/              # Interacoes Droga-Laboratorio (40 regras)
│   ├── ELECTROLYTE/  # Disturbios eletroliticos
│   ├── HEPATIC/      # Funcao hepatica
│   └── RENAL/        # Funcao renal
│
├── EWS/              # Escores de Alerta Precoce (25 regras)
│   ├── MEWS/         # Modified Early Warning Score
│   ├── NEWS/         # National Early Warning Score
│   ├── PEWS/         # Pediatric Early Warning Score
│   └── qSOFA/        # Quick Sequential Organ Failure Assessment
│
├── LAB/              # Alertas Laboratoriais (34 regras)
│   ├── ELECTRO/      # Painel eletrolitico
│   ├── HEME/         # Painel hematologico
│   ├── RENAL/        # Painel renal
│   ├── CARDIAC/      # Marcadores cardiacos
│   └── GLUC/         # Painel glicemico
│
├── MED/              # Alertas de Medicamentos (25 regras)
│   ├── DOSE/         # Validacao de dose
│   ├── DUPLICATE/    # Duplicidade terapeutica
│   ├── FREQUENCY/    # Frequencia de administracao
│   └── HIGHRISK/     # Medicamentos de alto risco
│
├── RSK/              # Avaliacoes de Risco (20 regras)
│   ├── VTE/          # Risco tromboembolico (Caprini)
│   ├── FALL/         # Risco de queda (Morse)
│   ├── PRESSURE/     # Risco de lesao por pressao (Braden)
│   └── BLEED/        # Risco de sangramento (HAS-BLED)
│
├── SYN/              # Sindromes Clinicas (22 regras)
│   ├── SEPSIS/       # Sepse e choque septico
│   ├── AKI/          # Lesao renal aguda
│   ├── DKA/          # Cetoacidose diabetica
│   ├── MI/           # Infarto agudo do miocardio
│   └── VTE/          # Tromboembolismo venoso
│
├── VIT/              # Sinais Vitais Criticos (20 regras)
│   ├── CRITICAL/     # Valores criticos (HR, BP, RR, SpO2, Temp, GCS)
│
├── docs/             # Documentacao adicional
└── templates/        # Templates de regras
```

## Categorias de Regras

### DDI - Interacoes Droga-Droga (50 regras)

Regras para deteccao de interacoes medicamentosas clinicamente significativas.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| CONTRAIND | 10 | Contraindicacoes absolutas (ex: IMAO + ISRS) |
| BLEED | 10 | Combinacoes que aumentam risco de sangramento (anticoagulantes + AINEs) |
| HEPATO | 10 | Hepatotoxicidade potencializada (ex: paracetamol + isoniazida) |
| NEPHRO | 10 | Nefrotoxicidade acumulada (AINEs + diureticos + IECA) |
| QT | 10 | Prolongamento QT com risco de torsades de pointes |

**Casos de Uso:**
- Alerta critico ao prescrever warfarina + AAS
- Deteccao de "triple whammy" (IECA + diuretico + AINE)
- Prevencao de sindrome serotoninergica (IMAO + ISRS)
- Monitoramento ECG obrigatorio (antiarritmicos + macrolideos)

### DDX - Diagnosticos Diferenciais (35 regras)

Regras para sugestao de diagnosticos diferenciais baseados em apresentacao clinica.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| ALLERGY | 7 | Reacoes de hipersensibilidade (anafilaxia, Stevens-Johnson) |
| CARDIAC | 7 | Sindromes coronarianas, IC descompensada, arritmias |
| NEURO | 7 | AVE, meningite, encefalopatia, crise convulsiva |
| RENAL | 7 | Lesao renal aguda, sindrome nefritica/nefrotica |
| RESPIRATORY | 7 | TEP, pneumonia, DPOC exacerbado, asma grave |

**Casos de Uso:**
- Dor toracica: sugerir IAM, angina, TEP, disseccao aortica
- Febre + cefaleia: sugerir meningite, encefalite, sinusite
- Dispneia aguda: sugerir IC, TEP, pneumonia, pneumotorax
- Oliguria + edema: sugerir IRA, sindrome nefritica

### DLI - Interacoes Droga-Laboratorio (40 regras)

Regras para detectar medicamentos que podem alterar resultados laboratoriais ou requerem ajuste por valores laboratoriais.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| ELECTROLYTE | 15 | Disturbios eletroliticos induzidos por drogas (hipocalemia com diureticos) |
| HEPATIC | 15 | Ajuste de dose em insuficiencia hepatica (Child-Pugh) |
| RENAL | 10 | Ajuste de dose por clearance de creatinina (CKD-EPI) |

**Casos de Uso:**
- Hipocalemia (K+ <3.5) + digoxina: risco de toxicidade digitalica
- Hiponatremia (Na+ <125) + carbamazepina: suspender e investigar SIADH
- Creatinina >2.0 + metformina: suspender (risco de acidose latica)
- TGO/TGP >5x LSN + estatina: suspender e investigar rabdomiolise

### EWS - Escores de Alerta Precoce (25 regras)

Regras para calcular escores de deterioracao clinica e acionar times de resposta rapida.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| MEWS | 7 | Modified Early Warning Score (0-14 pontos) |
| NEWS | 7 | National Early Warning Score (0-20 pontos) |
| PEWS | 6 | Pediatric Early Warning Score (0-18 pontos) |
| qSOFA | 5 | Quick SOFA (0-3 pontos, >= 2 prediz sepse) |

**Casos de Uso:**
- MEWS >=5: acionar time de resposta rapida (MET)
- NEWS >=7: transferir para UTI (risco alto)
- PEWS >=4: reavaliar crianca a cada 1h
- qSOFA >=2: investigar sepse (hemoculturas + lactato)

### LAB - Alertas Laboratoriais (34 regras)

Regras para valores laboratoriais criticos que exigem notificacao imediata.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| ELECTRO | 7 | K+ <2.5 ou >6.5, Na+ <120 ou >160, Ca++ <6.0 ou >13.0 |
| HEME | 7 | Hb <7.0, plaquetas <20k, leucocitos >50k |
| RENAL | 7 | Creatinina >5.0, ureia >200, pH <7.2 |
| CARDIAC | 7 | Troponina >10x LSN, BNP >1000, D-dimero >5000 |
| GLUC | 6 | Glicose <40 ou >600, HbA1c >14%, cetoacidose |

**Casos de Uso:**
- K+ 7.2 mEq/L: notificar medico em 15 min + ECG urgente
- Plaquetas 12.000/mm³: risco hemorragico critico
- Troponina I 50 ng/mL: IAM com supradesnivel de ST
- Glicose 28 mg/dL: hipoglicemia grave (glucagon IM)

### MED - Alertas de Medicamentos (25 regras)

Regras para prevencao de erros de medicacao e promocao do uso seguro.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| DOSE | 7 | Doses fora do intervalo terapeutico (subdose/superdose) |
| DUPLICATE | 6 | Duplicidade terapeutica (2+ medicamentos da mesma classe) |
| FREQUENCY | 6 | Frequencia de administracao inadequada (dose loading, PRN) |
| HIGHRISK | 6 | Medicamentos de alto risco (insulina, heparina, opioides) |

**Casos de Uso:**
- Enoxaparina 120 mg 12/12h em paciente de 50 kg: superdose
- Omeprazol + pantoprazol prescritos simultaneamente: duplicidade
- Gentamicina 8/8h: ajustar para dose unica diaria
- Heparina 50.000 UI: conferir com dupla checagem

### RSK - Avaliacoes de Risco (20 regras)

Regras para estratificacao de risco e implementacao de protocolos preventivos.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| VTE | 5 | Escore de Caprini (0-40+ pontos) para tromboprofilaxia |
| FALL | 5 | Escala de Morse (0-125 pontos) para prevencao de quedas |
| PRESSURE | 5 | Escala de Braden (6-23 pontos) para lesao por pressao |
| BLEED | 5 | Escore HAS-BLED (0-9 pontos) para risco hemorragico |

**Casos de Uso:**
- Caprini >=5: iniciar enoxaparina 40 mg/dia
- Morse >=45: implementar precaucoes de queda (grade, sino, piso)
- Braden <=12: colchao pneumatico + mudanca de decubito 2/2h
- HAS-BLED >=3: cautela com anticoagulacao (considerar alternativas)

### SYN - Sindromes Clinicas (22 regras)

Regras para deteccao precoce de sindromes clinicas que exigem intervencao urgente.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| SEPSIS | 5 | Criterios Sepsis-3 (SOFA, qSOFA, lactato) |
| AKI | 5 | KDIGO (creatinina, debito urinario) |
| DKA | 4 | Cetoacidose diabetica (glicose, pH, cetonas) |
| MI | 4 | Infarto agudo do miocardio (troponina, ECG) |
| VTE | 4 | Tromboembolismo venoso (Wells, D-dimero) |

**Casos de Uso:**
- SOFA >=2 + suspeita infeccao: diagnostico de sepse
- Creatinina subiu 0.4 mg/dL em 48h: AKI estagio 1 (KDIGO)
- Glicose 480 + pH 7.18 + cetonas: DKA grave
- Troponina I positiva + infradesnivelamento ST: IAMSEST

### VIT - Sinais Vitais Criticos (20 regras)

Regras para valores criticos de sinais vitais que exigem intervencao imediata.

| Subcategoria | Regras | Descricao |
|--------------|--------|-----------|
| CRITICAL | 20 | FC <40 ou >140, PAS <80 ou >220, FR <8 ou >35, SpO2 <85%, Temp <35°C ou >40°C, GCS <8 |

**Casos de Uso:**
- FC 28 bpm: bradicardia critica (atropina, marca-passo)
- PAS 260 mmHg: emergencia hipertensiva (nitroprussiato)
- FR 6 irpm: bradipneia critica (ventilar com ambu)
- SpO2 78%: hipoxemia grave (intubar se refrataria)
- GCS 5: coma profundo (proteger via aerea)

## Formato das Regras DMN

### Estrutura XML

Todas as regras seguem o padrao DMN 1.3 com a seguinte estrutura:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  RULE-ID - Nome da Regra
  Versao: 1.0.0
  Categoria: CATEGORIA-SUBCATEGORIA
  Perspectiva: CLINICA (Seguranca do Paciente)

  INDICACOES: Quando gerar alerta
  CONTRAINDICACOES: Quando nao alertar (falsos positivos)
  REFERENCIAS CLINICAS: Guidelines e estudos
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

      <!-- Outputs Padronizados (5) -->
      <output id="Output_1" label="Nivel Alerta" name="nivelAlerta" typeRef="string">
        <outputValues>
          <text>"Alerta", "Atencao", "OK", "Revisar"</text>
        </outputValues>
      </output>
      <output id="Output_2" label="Classificacao" name="classificacaoSindrome" typeRef="string"/>
      <output id="Output_3" label="Protocolo Ativado" name="protocoloAtivado" typeRef="boolean"/>
      <output id="Output_4" label="Acao Requerida" name="acaoRequerida" typeRef="string"/>
      <output id="Output_5" label="Urgencia" name="urgencia" typeRef="string">
        <outputValues>
          <text>"CRITICA", "ALTA", "MEDIA", "BAIXA"</text>
        </outputValues>
      </output>

      <!-- Rules -->
      <rule id="Rule_1">
        <inputEntry><text>condicao</text></inputEntry>
        <outputEntry><text>"Alerta"</text></outputEntry>
        <outputEntry><text>"SINDROME_DETECTADA"</text></outputEntry>
        <outputEntry><text>true</text></outputEntry>
        <outputEntry><text>"ACAO IMEDIATA: [descricao]"</text></outputEntry>
        <outputEntry><text>"CRITICA"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>
```

### Politica de Acerto (Hit Policy)

Todas as regras utilizam `hitPolicy="FIRST"`:
- A primeira regra que corresponder aos inputs e executada
- Regras sao avaliadas na ordem definida (mais grave primeiro)
- Ultima regra deve ser fallback para casos normais

### Outputs Padronizados

Todas as regras de alertas clinicos utilizam 5 outputs:

| Output | Tipo | Valores | Descricao |
|--------|------|---------|-----------|
| `nivelAlerta` | string | Alerta, Atencao, OK, Revisar | Severidade do alerta |
| `classificacaoSindrome` | string | - | Classificacao clinica especifica |
| `protocoloAtivado` | boolean | true/false | Se protocolo clinico foi acionado |
| `acaoRequerida` | string | - | Descricao da acao clinica |
| `urgencia` | string | CRITICA, ALTA, MEDIA, BAIXA | Nivel de urgencia |

### Valores de Nivel de Alerta

| Valor | Descricao | Acao Requerida |
|-------|-----------|----------------|
| `Alerta` | Situacao critica | Notificacao imediata + intervencao obrigatoria |
| `Atencao` | Situacao de risco | Avaliacao medica urgente (< 1h) |
| `OK` | Situacao normal | Nenhuma acao necessaria |
| `Revisar` | Dados incompletos | Validar inputs e reprocessar |

### Valores de Urgencia

| Valor | Descricao | Tempo de Resposta |
|-------|-----------|-------------------|
| `CRITICA` | Risco de morte iminente | Imediato (< 15 min) |
| `ALTA` | Risco de complicacao grave | Urgente (< 1h) |
| `MEDIA` | Risco de complicacao leve | Rotina (< 4h) |
| `BAIXA` | Risco minimo | Monitoramento de rotina |

## Conformidade Regulatoria

### RDC 36/2013 - Seguranca do Paciente

| Artigo | Tema | Aplicacao |
|--------|------|-----------|
| Art. 4º | Nucleo de Seguranca do Paciente | Notificacao de eventos adversos |
| Art. 7º | Protocolos basicos | Identificacao, cirurgia segura, higiene das maos |
| Anexo III | Metas internacionais | 6 metas de seguranca da OMS |

### RDC 302/2005 - Funcionamento de Laboratorios

| Artigo | Tema | Aplicacao |
|--------|------|-----------|
| Art. 153 | Valores criticos | Notificacao imediata ao medico |
| Art. 154 | Prazo de comunicacao | Maximo 1 hora para valores criticos |

### ANS RN 414/2020 - Acreditacao

| Requisito | Descricao | Aplicacao |
|-----------|-----------|-----------|
| Item 3.2.1 | Sistema de alertas | Alertas clinicos automatizados |
| Item 3.2.3 | Interacoes medicamentosas | Checagem automatica de DDI |
| Item 3.3.1 | Escores de deterioracao | EWS implementados |

### CFM Resolucao 2299/2021 - Telemedicina

| Artigo | Tema | Aplicacao |
|--------|------|-----------|
| Art. 6º | Prontuario eletronico | Registro de alertas clinicos |
| Art. 9º | Inteligencia artificial | Transparencia de algoritmos |

## Integracao com Sistemas

### Sistemas de Origem

| Sistema | Dados | Uso |
|---------|-------|-----|
| TASY | Prontuario eletronico | Historico clinico, alergias, comorbidades |
| LIS | Sistema laboratorial | Resultados de exames criticos |
| PACS | Sistema de imagens | Laudos radiologicos |
| CPOE | Prescricao eletronica | Medicamentos prescritos (DDI, dose) |
| Monitorizacao | Sinais vitais | Dados em tempo real (FC, PA, SpO2) |

### Fluxo de Integracao

```
[Evento Clinico: Prescricao/Exame/Sinal Vital]
        │
        ▼
[Camunda 8 Zeebe]
        │
        ▼
[DMN Decision Engine - Avaliacao de Alerta]
        │
        ├─── Alerta + CRITICA → [Notificacao Imediata] → [Time de Resposta Rapida]
        │
        ├─── Atencao + ALTA → [Notificacao Medico] → [Avaliacao < 1h]
        │
        ├─── OK + BAIXA → [Log do Sistema]
        │
        └─── Revisar + MEDIA → [Validacao de Dados]
```

### Integracao FHIR R4

As regras sao invocadas via recursos FHIR:

| Recurso FHIR | Alerta Relacionado | Exemplo |
|--------------|-------------------|---------|
| MedicationRequest | DDI, MED | Prescricao de warfarina + AAS |
| Observation | LAB, VIT | K+ critico, FC <40 bpm |
| DiagnosticReport | DLI, SYN | Lactato elevado (sepse) |
| RiskAssessment | RSK, EWS | MEWS >=5, Caprini >=8 |

## Uso das Regras

### Integracao com Camunda 8 Zeebe

As regras sao executadas como Decision Tables no Camunda 8:

```bash
# Avaliar uma decisao de alerta clinico (Sepse via qSOFA)
zbctl evaluate decision \
  --decisionId "Decision_SYN_SEPSIS_001" \
  --variables '{
    "frequenciaRespiratoria": 26,
    "pressaoSistolica": 95,
    "escalaGlasgow": 13,
    "suspeitaInfeccao": true
  }'
```

### Estrutura de Diretorios por Regra

```
{CATEGORIA}/{SUBCATEGORIA}/{RULE_ID}.dmn
```

Exemplo: `SYN/SYN-SEPSIS/SYN-SEPSIS-001.dmn`

### Exemplo de Response JSON

```json
{
  "nivelAlerta": "Alerta",
  "classificacaoSindrome": "SEPSE",
  "protocoloAtivado": true,
  "acaoRequerida": "ACAO IMEDIATA: Acionar protocolo de sepse. Coletar hemoculturas (2 amostras), dosar lactato, iniciar antibiotico empirico em 1h. Avaliar necessidade de ressuscitacao volemica.",
  "urgencia": "CRITICA"
}
```

## Estatisticas

### Resumo por Categoria

| Categoria | Total de Regras | Subcategorias |
|-----------|-----------------|---------------|
| DDI | 50 | 5 |
| DDX | 35 | 5 |
| DLI | 40 | 3 |
| EWS | 25 | 4 |
| LAB | 34 | 5 |
| MED | 25 | 4 |
| RSK | 20 | 4 |
| SYN | 22 | 5 |
| VIT | 20 | 1 |
| **Total** | **265** | **36** |

### Detalhamento por Subcategoria

#### DDI - Interacoes Droga-Droga
| Subcategoria | Regras |
|--------------|--------|
| CONTRAIND | 10 |
| BLEED | 10 |
| HEPATO | 10 |
| NEPHRO | 10 |
| QT | 10 |

#### DDX - Diagnosticos Diferenciais
| Subcategoria | Regras |
|--------------|--------|
| ALLERGY | 7 |
| CARDIAC | 7 |
| NEURO | 7 |
| RENAL | 7 |
| RESPIRATORY | 7 |

#### DLI - Interacoes Droga-Laboratorio
| Subcategoria | Regras |
|--------------|--------|
| ELECTROLYTE | 15 |
| HEPATIC | 15 |
| RENAL | 10 |

#### EWS - Escores de Alerta Precoce
| Subcategoria | Regras |
|--------------|--------|
| MEWS | 7 |
| NEWS | 7 |
| PEWS | 6 |
| qSOFA | 5 |

#### LAB - Alertas Laboratoriais
| Subcategoria | Regras |
|--------------|--------|
| ELECTRO | 7 |
| HEME | 7 |
| RENAL | 7 |
| CARDIAC | 7 |
| GLUC | 6 |

#### MED - Alertas de Medicamentos
| Subcategoria | Regras |
|--------------|--------|
| DOSE | 7 |
| DUPLICATE | 6 |
| FREQUENCY | 6 |
| HIGHRISK | 6 |

#### RSK - Avaliacoes de Risco
| Subcategoria | Regras |
|--------------|--------|
| VTE | 5 |
| FALL | 5 |
| PRESSURE | 5 |
| BLEED | 5 |

#### SYN - Sindromes Clinicas
| Subcategoria | Regras |
|--------------|--------|
| SEPSIS | 5 |
| AKI | 5 |
| DKA | 4 |
| MI | 4 |
| VTE | 4 |

#### VIT - Sinais Vitais Criticos
| Subcategoria | Regras |
|--------------|--------|
| CRITICAL | 20 |

## Manutencao

### Adicionando Novas Regras

1. **Criar arquivo DMN:**
   ```bash
   touch {CATEGORIA}/{SUBCATEGORIA}/{RULE_ID}.dmn
   ```

2. **Copiar template:**
   - Usar `templates/dmn-rule-template.xml` como base
   - Preencher inputs e os 5 outputs padronizados
   - Documentar indicacoes clinicas e contraindicacoes
   - Adicionar referencias (guidelines, estudos)

3. **Validar outputs obrigatorios:**
   - `nivelAlerta` (Alerta, Atencao, OK, Revisar)
   - `classificacaoSindrome` (string)
   - `protocoloAtivado` (boolean)
   - `acaoRequerida` (string)
   - `urgencia` (CRITICA, ALTA, MEDIA, BAIXA)

4. **Criar testes:**
   - Adicionar testes em `/tests/dmn/`
   - Validar cenarios clinicos reais

### Validacao

```bash
# Validar XML das regras
find alertas-clinicos/ -name "*.dmn" -exec xmllint --noout {} \;

# Validar hitPolicy="FIRST"
grep -r 'hitPolicy="FIRST"' alertas-clinicos/ | wc -l  # Deve retornar 265

# Executar testes
pytest tests/dmn/alertas_clinicos/ -v

# Verificar estrutura
find alertas-clinicos/ -type f -name "*.dmn" | wc -l  # Deve retornar 265
```

### Convencoes de Nomenclatura

| Elemento | Padrao | Exemplo |
|----------|--------|---------|
| Categoria | MAIUSCULAS (3 letras) | DDI, LAB, VIT |
| Subcategoria | MAIUSCULAS | BLEED, ELECTRO, CRITICAL |
| Rule ID | CATEGORIA-SUBCATEGORIA-NNN | SYN-SEPSIS-001 |
| Arquivo DMN | {RULE_ID}.dmn | SYN-SEPSIS-001.dmn |

### Versionamento

As regras seguem versionamento semantico (SemVer):
- **MAJOR**: Mudanca incompativel (remover output obrigatorio)
- **MINOR**: Nova funcionalidade (nova regra na tabela)
- **PATCH**: Correcao de bug (ajuste de threshold clinico)

## Glossario

| Termo | Definicao |
|-------|-----------|
| AKI | Acute Kidney Injury (Lesao Renal Aguda) |
| DDI | Drug-Drug Interaction (Interacao Droga-Droga) |
| DLI | Drug-Lab Interaction (Interacao Droga-Laboratorio) |
| DKA | Diabetic Ketoacidosis (Cetoacidose Diabetica) |
| EWS | Early Warning Score (Escore de Alerta Precoce) |
| KDIGO | Kidney Disease: Improving Global Outcomes |
| MEWS | Modified Early Warning Score |
| NEWS | National Early Warning Score |
| PEWS | Pediatric Early Warning Score |
| qSOFA | Quick Sequential Organ Failure Assessment |
| SOFA | Sequential Organ Failure Assessment |
| TEP | Tromboembolismo Pulmonar |
| VTE | Venous Thromboembolism (Tromboembolismo Venoso) |

## Suporte

### Documentacao Relacionada

- `docs/RULE_CREATION_GUIDE.md` - Guia de criacao de novas regras
- `docs/CLINICAL_ALERTS_STRATEGY.md` - Estrategia de alertas clinicos
- `templates/dmn-rule-template.xml` - Template DMN padrao
- `templates/metadata-schema.json` - Schema de metadados

### Contato

- **Equipe de Seguranca do Paciente**: Duvidas sobre criterios clinicos
- **Equipe de Compliance**: Duvidas regulatorias (ANVISA, ANS)
- **Equipe de TI**: Suporte tecnico e integracao

---

**Versao**: 1.0.0
**Ultima Atualizacao**: 2026-02-06
**Padrao DMN**: 1.3
**Motor de Execucao**: Camunda 8 Zeebe
**Outputs Padronizados**: 5 (nivelAlerta, classificacaoSindrome, protocoloAtivado, acaoRequerida, urgencia)
