#!/usr/bin/env python3
"""
DMN TIER-1 Quality Generator for Ginecologia e Obstetricia
Generates standardized DMN files with 5 inputs, 3 outputs, FIRST hitPolicy
"""

import json

# Template for TIER-1 DMN
DMN_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/" xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/" xmlns:biodi="http://bpmn.io/schema/dmn/biodi/2.0" id="Definitions_{tuss_code}" name="{tuss_code}_{proc_slug}" namespace="http://camunda.org/schema/1.0/dmn" exporter="Camunda Modeler" exporterVersion="5.0.0">
  <!--
    TUSS {tuss_code} - {proc_name}
    Versao: 3.0.0 (2026-02-07)

    Indicacoes Clinicas (DUT/ANS):
{clinical_indications}

    Contraindicacoes:
{contraindications}

    Referencias:
    - ANS RN 465/2021 - Rol de Procedimentos
    - FEBRASGO - {febrasgo_ref}
    - DUT/ANS 2024
  -->
  <decision id="Decision_{tuss_code}" name="{proc_name}">
    <decisionTable id="DecisionTable_{tuss_code}" hitPolicy="FIRST">
      <!-- INPUTS: 5 entradas padronizadas para ginecologia -->
      <input id="Input_1" label="Diagnóstico Principal (CID-10)">
        <inputExpression id="InputExpression_1" typeRef="string">
          <text>diagnosticoPrincipal</text>
        </inputExpression>
      </input>
      <input id="Input_2" label="Estadiamento FIGO">
        <inputExpression id="InputExpression_2" typeRef="string">
          <text>estadiamentoFIGO</text>
        </inputExpression>
      </input>
      <input id="Input_3" label="Idade Gestacional (semanas)">
        <inputExpression id="InputExpression_3" typeRef="string">
          <text>idadeGestacional</text>
        </inputExpression>
      </input>
      <input id="Input_4" label="Paciente Gestante">
        <inputExpression id="InputExpression_4" typeRef="boolean">
          <text>gestante</text>
        </inputExpression>
      </input>
      <input id="Input_5" label="Laudo Ginecológico Anexo">
        <inputExpression id="InputExpression_5" typeRef="boolean">
          <text>laudoGinecologico</text>
        </inputExpression>
      </input>

      <!-- OUTPUTS: 3 saídas obrigatórias -->
      <output id="Output_1" name="resultado" typeRef="string" />
      <output id="Output_2" name="observacao" typeRef="string" />
      <output id="Output_3" name="fundamentacao" typeRef="string" />

      <!-- CONTRAINDICATIONS -->
{contraindication_rules}

      <!-- APPROVALS: Indicações clínicas -->
{approval_rules}

      <!-- FALLBACK RULE -->
      <rule id="Rule_Fallback_{tuss_code}">
        <description>Regra padrão - Análise manual necessária</description>
        <inputEntry id="InputEntry_Fallback_1">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_Fallback_2">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_Fallback_3">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_Fallback_4">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_Fallback_5">
          <text>-</text>
        </inputEntry>
        <outputEntry id="OutputEntry_Fallback_1">
          <text>"Pendente"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_Fallback_2">
          <text>"Caso nao se enquadra em criterios pre-definidos"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_Fallback_3">
          <text>"Requer analise manual conforme DUT/ANS 2024"</text>
        </outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>
'''

# Rule templates
CONTRA_GESTANTE = '''      <rule id="Rule_Contraindicacao_{tuss}_Gestante">
        <description>Reprovado - Paciente gestante</description>
        <inputEntry id="InputEntry_1_1">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_2_1">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_3_1">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_4_1">
          <text>true</text>
        </inputEntry>
        <inputEntry id="InputEntry_5_1">
          <text>-</text>
        </inputEntry>
        <outputEntry id="OutputEntry_1_1">
          <text>"Reprovado"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_2_1">
          <text>"{obs}"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_3_1">
          <text>"FEBRASGO - {fund}"</text>
        </outputEntry>
      </rule>
'''

CONTRA_LAUDO = '''      <rule id="Rule_Contraindicacao_{tuss}_SemLaudo">
        <description>Reprovado - Laudo ginecológico obrigatório</description>
        <inputEntry id="InputEntry_1_2">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_2_2">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_3_2">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_4_2">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_5_2">
          <text>false</text>
        </inputEntry>
        <outputEntry id="OutputEntry_1_2">
          <text>"Reprovado"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_2_2">
          <text>"Laudo especializado obrigatorio"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_3_2">
          <text>"ANS RN 465/2021 - Documentacao medica obrigatoria"</text>
        </outputEntry>
      </rule>
'''

APPROVAL_CID = '''      <rule id="Rule_Aprovado_{tuss}_{rule_id}">
        <description>Aprovado - {desc}</description>
        <inputEntry id="InputEntry_1_{idx}">
          <text>"{cid}"</text>
        </inputEntry>
        <inputEntry id="InputEntry_2_{idx}">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_3_{idx}">
          <text>-</text>
        </inputEntry>
        <inputEntry id="InputEntry_4_{idx}">
          <text>{gestante_req}</text>
        </inputEntry>
        <inputEntry id="InputEntry_5_{idx}">
          <text>true</text>
        </inputEntry>
        <outputEntry id="OutputEntry_1_{idx}">
          <text>"Aprovado"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_2_{idx}">
          <text>"Indicacao: {obs}"</text>
        </outputEntry>
        <outputEntry id="OutputEntry_3_{idx}">
          <text>"DUT/ANS 2024 - {fund}"</text>
        </outputEntry>
      </rule>
'''

# Procedure definitions (TUSS codes to process - excluding the 5 already done)
PROCEDURES = {
    "31303153": {
        "name": "Traquelectomia",
        "slug": "Traquelectomia",
        "febrasgo": "Manual de Oncologia Ginecológica",
        "indications": "    - Câncer cervical estádio IA1-IA2 (FIGO)\n    - Desejo de preservação da fertilidade\n    - Lesões NIC II/III persistentes",
        "contraindications": "    - Gestação em curso\n    - Estádio IB ou superior\n    - Invasão parametrial",
        "gestante_contra": ("Contraindicacao: Gestacao em curso", "Procedimento oncologico cervical contraindicado durante gestacao"),
        "approvals": [
            ("CancerCervicalIA1", "N84.1", "Cancer cervical estadio IA1", "Indicacao Classe I para cancer cervical precoce", "false", 3),
            ("NIC3", "D06.9", "Lesao pre-maligna NIC III persistente", "NIC III refrataria a tratamento conservador", "false", 4)
        ]
    },
    "31303188": {
        "name": "Histeroscopia com ressectoscopio para miomectomia polipectomia metroplastia endometrectomia e resseccao de sinequias",
        "slug": "Histeroscopia_ressectoscopio",
        "febrasgo": "Manual de Histeroscopia",
        "indications": "    - Miomas submucosos\n    - Pólipos endometriais sintomáticos\n    - Septo uterino\n    - Sinéquias intrauterinas\n    - Endométrio espessado",
        "contraindications": "    - Infecção pélvica ativa\n    - Câncer endometrial confirmado\n    - Gestação em curso\n    - Sangramento ativo grave",
        "gestante_contra": ("Contraindicacao: Gestacao em curso", "Procedimento intrauterino invasivo contraindicado durante gestacao"),
        "approvals": [
            ("MiomaSubmucoso", "D25.0", "Mioma submucoso", "Indicacao Classe I para mioma submucoso sintomatico", "false", 3),
            ("PolipoEndometrial", "N84.0", "Polipo endometrial sintomatico", "Polipectomia histeroscopica indicada", "false", 4),
            ("SeptoUterino", "Q51.3", "Septo uterino", "Metroplastia histeroscopica indicada", "false", 5)
        ]
    },
    "31303293": {
        "name": "Implante de dispositivo intrauterino DIU",
        "slug": "Implante_DIU",
        "febrasgo": "Manual de Contracepção",
        "indications": "    - Contracepção de longa duração\n    - Menorragia (DIU hormonal)\n    - Nuliparidade não é contraindicação",
        "contraindications": "    - Gestação confirmada ou suspeita\n    - Infecção pélvica ativa\n    - Câncer endometrial ou cervical ativo\n    - Malformação uterina grave",
        "gestante_contra": ("Contraindicacao: Gestacao confirmada", "DIU contraindicado durante gestacao - risco de aborto"),
        "approvals": [
            ("Contracepcao", "Z30.0", "Contracepcao de longa duracao", "Indicacao Classe I para contracepcao reversivel", "false", 3),
            ("Menorragia", "N92.0", "Menorragia - DIU hormonal", "DIU hormonal indicado para sangramento excessivo", "false", 4)
        ]
    },
    "31303307": {
        "name": "Retirada de DIU por Histeroscopia",
        "slug": "Retirada_DIU_histeroscopia",
        "febrasgo": "Manual de Histeroscopia",
        "indications": "    - DIU sem fios visíveis\n    - DIU migrado\n    - DIU fragmentado\n    - Falha de remoção ambulatorial",
        "contraindications": "    - Gestação com DIU tópico (remoção sem histeroscopia)\n    - Infecção pélvica grave não controlada",
        "gestante_contra": ("Contraindicacao: Gestacao com DIU migrado", "Requer avaliacao obst especializada antes de histeroscopia"),
        "approvals": [
            ("DIUSemFios", "Z97.5", "DIU sem fios visiveis ao especulo", "Histeroscopia indicada para DIU nao-localizado", "-", 3),
            ("DIUMigrado", "T83.3", "DIU migrado ou fragmentado", "Remocao por histeroscopia indicada", "-", 4)
        ]
    },
    "31303374": {
        "name": "Retirada de DIU Hormonal",
        "slug": "Retirada_DIU_hormonal",
        "febrasgo": "Manual de Contracepção",
        "indications": "    - Término do prazo de uso (5 anos)\n    - Efeitos adversos\n    - Desejo de gestação\n    - Troca por outro método",
        "contraindications": "    - Nenhuma contraindicação absoluta para remoção",
        "gestante_contra": ("Contraindicacao: Gestacao com DIU topico requer remocao precoce", "Remocao em gestacao inicial reduz risco de aborto"),
        "approvals": [
            ("TerminoPrazo", "Z30.5", "Termino do prazo de uso do DIU", "Remocao indicada apos 5 anos", "-", 3),
            ("DesejoGestacao", "Z30.2", "Desejo de gestacao", "Remocao de DIU para concepcao", "-", 4)
        ]
    },
    "31303382": {
        "name": "Retirada de DIU Nao Hormonal",
        "slug": "Retirada_DIU_nao_hormonal",
        "febrasgo": "Manual de Contracepção",
        "indications": "    - Término do prazo de uso (10 anos para cobre)\n    - Efeitos adversos (sangramento, cólicas)\n    - Desejo de gestação\n    - Troca por outro método",
        "contraindications": "    - Nenhuma contraindicação absoluta para remoção",
        "gestante_contra": ("Contraindicacao: Gestacao com DIU topico requer remocao precoce", "Remocao em gestacao inicial reduz risco de aborto"),
        "approvals": [
            ("TerminoPrazo", "Z30.5", "Termino do prazo de uso do DIU", "Remocao indicada apos 10 anos (cobre)", "-", 3),
            ("EfeitosAdversos", "N93.8", "Sangramento excessivo com DIU", "Remocao por intolerancia", "-", 4)
        ]
    },
    "31304010": {
        "name": "Esterilizacao feminina laqueadura tubarica convencional",
        "slug": "Laqueadura_convencional",
        "febrasgo": "Manual de Planejamento Familiar",
        "indications": "    - Idade >= 25 anos ou >= 2 filhos vivos (Lei 9263/96)\n    - Capacidade civil plena\n    - Consentimento informado documentado\n    - Prazo mínimo de 60 dias desde manifestação",
        "contraindications": "    - Idade < 25 anos sem 2 filhos vivos\n    - Ausência de consentimento documentado\n    - Durante parto cesariana sem justificativa médica (exceto risco)\n    - Puerpério até 42 dias sem risco materno",
        "gestante_contra": ("Contraindicacao: Laqueadura durante parto sem justificativa clinica", "Lei 9263/96 restringe laqueadura no parto salvo risco materno"),
        "approvals": [
            ("Criterios Legal", "Z30.2", "Criterios da Lei 9263/96 atendidos", "Idade>=25 ou >=2 filhos vivos + 60 dias", "false", 3),
            ("RiscoMaterno", "O99.8", "Risco materno que justifica esterilizacao", "Excecao legal para laqueadura no parto", "-", 4)
        ]
    },
    "31304052": {
        "name": "Esterilizacao feminina laqueadura tubarica laparoscopica",
        "slug": "Laqueadura_laparoscopica",
        "febrasgo": "Manual de Planejamento Familiar",
        "indications": "    - Mesmos critérios da laqueadura convencional (Lei 9263/96)\n    - Preferência por via minimamente invasiva\n    - Ausência de contraindicações à laparoscopia",
        "contraindications": "    - Mesmas da laqueadura convencional\n    - Aderências pélvicas extensas\n    - Contraindicações ao pneumoperitônio",
        "gestante_contra": ("Contraindicacao: Gestacao em curso", "Laqueadura somente apos parto, respeitando Lei 9263/96"),
        "approvals": [
            ("CriteriosLegal", "Z30.2", "Criterios da Lei 9263/96 atendidos", "Idade>=25 ou >=2 filhos vivos + 60 dias", "false", 3)
        ]
    },
    "31305016": {
        "name": "Ooforectomia uni ou bilateral ou ooforoplastia uni ou bilateral",
        "slug": "Ooforectomia",
        "febrasgo": "Manual de Oncologia Ginecológica",
        "indications": "    - Cistos ovarianos complexos ou > 5cm persistentes\n    - Câncer de ovário confirmado\n    - Endometriose ovariana grave\n    - Torção ovariana\n    - Profilaxia em portadoras de mutação BRCA1/BRCA2",
        "contraindications": "    - Gestação (ooforectomia bilateral)\n    - Condições clínicas graves",
        "gestante_contra": ("Contraindicacao: Gestacao - ooforectomia bilateral", "Ooforectomia bilateral compromete gestacao"),
        "approvals": [
            ("CistoOvariano", "N83.2", "Cisto ovariano complexo persistente", "Indicacao para resseccao cirurgica", "-", 3),
            ("CancerOvario", "C56", "Cancer de ovario", "Ooforectomia indicada", "false", 4),
            ("Endometriose", "N80.1", "Endometriose ovariana grave", "Resseccao indicada para endometrioma", "-", 5)
        ]
    },
    "31305032": {
        "name": "Ooforectomia laparoscopica uni ou bilateral ou ooforoplastia uni ou bilateral",
        "slug": "Ooforectomia_laparoscopica",
        "febrasgo": "Manual de Cirurgia Minimamente Invasiva",
        "indications": "    - Mesmas indicações da ooforectomia convencional\n    - Preferência por via minimamente invasiva",
        "contraindications": "    - Mesmas da ooforectomia convencional\n    - Contraindicações à laparoscopia",
        "gestante_contra": ("Contraindicacao: Gestacao - ooforectomia bilateral", "Ooforectomia bilateral compromete gestacao"),
        "approvals": [
            ("CistoOvariano", "N83.2", "Cisto ovariano complexo persistente", "Resseccao laparoscopica indicada", "-", 3),
            ("Endometriose", "N80.1", "Endometriose ovariana grave", "Via laparoscopica preferencial", "-", 4)
        ]
    },
}

# Complete the dictionary with all remaining procedures (continued due to length)
PROCEDURES_PART2 = {
    "31306020": {
        "name": "Correcao de enterocele",
        "slug": "Correcao_enterocele",
        "febrasgo": "Manual de Uroginecologia",
        "indications": "    - Enterocele sintomática (abaulamento vaginal posterior)\n    - Prolapso de cúpula vaginal\n    - Falha de tratamento conservador",
        "contraindications": "    - Gestação\n    - Infecção pélvica ativa",
        "gestante_contra": ("Contraindicacao: Gestacao", "Cirurgia de prolapso contraindicada durante gestacao"),
        "approvals": [
            ("Enterocele", "N81.5", "Enterocele sintomatica", "Correcao cirurgica indicada", "false", 3)
        ]
    },
    "31307027": {
        "name": "Prolapso de cupula vaginal",
        "slug": "Correcao_prolapso_cupula",
        "febrasgo": "Manual de Uroginecologia",
        "indications": "    - Prolapso de cúpula vaginal pós-histerectomia\n    - Estádio II ou superior (POP-Q)\n    - Sintomas associados",
        "contraindications": "    - Gestação\n    - Infecção ativa",
        "gestante_contra": ("Contraindicacao: Gestacao", "Cirurgia de prolapso contraindicada durante gestacao"),
        "approvals": [
            ("ProlapsoCapula", "N99.3", "Prolapso de cupula vaginal pos-histerectomia", "Correcao cirurgica indicada", "false", 3)
        ]
    },
    "31309038": {
        "name": "Assistencia ao trabalho de parto",
        "slug": "Assistencia_parto",
        "febrasgo": "Manual de Assistência ao Parto",
        "indications": "    - Trabalho de parto ativo (>= 4cm dilatação)\n    - Gestação >= 37 semanas (termo)\n    - Vitalidade fetal adequada",
        "contraindications": "    - Gestação < 37 semanas sem indicação obstétrica\n    - Contraindicações ao parto vaginal",
        "gestante_contra": ("Aprovacao: Gestacao a termo em trabalho de parto", "Assistencia ao parto indicada"),
        "approvals": [
            ("TrabalhoPartoTermo", "O80", "Trabalho de parto a termo", "Assistencia obstetrica indicada", "true", 3),
            ("PartoNormal", "O80.0", "Parto normal espontaneo", "Assistencia profissional obrigatoria", "true", 4)
        ]
    },
    "31309062": {
        "name": "Curetagem pos abortamento",
        "slug": "Curetagem_pos_aborto",
        "febrasgo": "Manual de Urgências Obstétricas",
        "indications": "    - Aborto incompleto\n    - Restos placentários pós-parto\n    - Sangramento uterino anormal pós-aborto",
        "contraindications": "    - Perfuração uterina\n    - Infecção grave não controlada",
        "gestante_contra": ("Indicacao: Abortamento incompleto requer curetagem", "Procedimento para finalizacao de aborto incompleto"),
        "approvals": [
            ("AbortoIncompleto", "O03.4", "Aborto incompleto", "Curetagem indicada", "false", 3),
            ("RestosOvulares", "O08.1", "Restos ovulares pos-aborto", "Curetagem indicada", "false", 4)
        ]
    },
    "31309097": {
        "name": "Maturação cervical para indução de abortamento ou de trabalho de parto",
        "slug": "Maturacao_cervical",
        "febrasgo": "Manual de Assistência Pré-Natal",
        "indications": "    - Indução de parto com colo desfavorável (Bishop < 6)\n    - Gestação prolongada (> 41 semanas)\n    - Indicações obstétricas para indução",
        "contraindications": "    - Contraindicações ao parto vaginal\n    - Placenta prévia\n    - Cesárea anterior clássica",
        "gestante_contra": ("Indicacao: Gestacao com indicacao de inducao", "Maturacao cervical facilita inducao segura"),
        "approvals": [
            ("InducaoParto", "O61.0", "Inducao de parto com colo desfavoravel", "Maturacao cervical indicada", "true", 3),
            ("GestacaoProlongada", "O48", "Gestacao prolongada > 41 semanas", "Inducao com maturacao indicada", "true", 4)
        ]
    },
    "40201155": {
        "name": "Histeroscopia diagnostica com biopsia",
        "slug": "Histeroscopia_diagnostica",
        "febrasgo": "Manual de Histeroscopia",
        "indications": "    - Sangramento uterino anormal pós-menopausa\n    - Espessamento endometrial (> 5mm pós-menopausa)\n    - Suspeita de pólipo ou mioma\n    - Investigação de infertilidade",
        "contraindications": "    - Infecção pélvica ativa\n    - Gestação confirmada\n    - Câncer cervical avançado",
        "gestante_contra": ("Contraindicacao: Gestacao", "Histeroscopia contraindicada durante gestacao"),
        "approvals": [
            ("SangramentoPosmenopausa", "N95.0", "Sangramento pos-menopausa", "Histeroscopia diagnostica indicada", "false", 3),
            ("EspessamentoEndometrial", "N85.0", "Espessamento endometrial > 5mm pos-menopausa", "Biopsia guiada por histeroscopia indicada", "false", 4)
        ]
    },
    "40901254": {
        "name": "US Obstetrica com translucencia nucal",
        "slug": "USG_translucencia_nucal",
        "febrasgo": "Manual de Medicina Fetal",
        "indications": "    - Rastreio de cromossomopatias no 1º trimestre\n    - Idade gestacional 11-13 semanas + 6 dias\n    - Comprimento cabeça-nádegas 45-84mm",
        "contraindications": "    - Idade gestacional fora da janela (< 11 ou > 14 semanas)",
        "gestante_contra": ("Indicacao: Gestacao 11-13+6 semanas", "Translucencia nucal para rastreio de cromossomopatias"),
        "approvals": [
            ("Rastreio1Trimestre", "Z36.0", "Rastreio pre-natal 1o trimestre (11-13+6 sem)", "Translucencia nucal indicada", "true", 3)
        ]
    },
    "40901262": {
        "name": "US - Obstétrica morfológica",
        "slug": "USG_morfologica",
        "febrasgo": "Manual de Medicina Fetal",
        "indications": "    - Rastreio de malformações no 2º trimestre\n    - Idade gestacional 20-24 semanas (ideal)\n    - Avaliação anatômica fetal detalhada",
        "contraindications": "    - Nenhuma contraindicação absoluta",
        "gestante_contra": ("Indicacao: Gestacao 20-24 semanas", "USG morfologica para rastreio de malformacoes"),
        "approvals": [
            ("Rastreio2Trimestre", "Z36.0", "Rastreio pre-natal 2o trimestre (20-24 sem)", "USG morfologica indicada", "true", 3)
        ]
    },
    "40901300": {
        "name": "US - Transvaginal (útero, ovário, anexos e vagina)",
        "slug": "USG_transvaginal",
        "febrasgo": "Manual de Ultrassonografia",
        "indications": "    - Sangramento uterino anormal\n    - Dor pélvica\n    - Massas anexiais\n    - Avaliação endometrial\n    - Gestação inicial (< 10 semanas)",
        "contraindications": "    - Nenhuma contraindicação absoluta\n    - Relativa: virgens ou estenose vaginal",
        "gestante_contra": ("Indicacao: Gestacao inicial ou sintomas pelvicos", "USG transvaginal segura na gestacao"),
        "approvals": [
            ("SangramentoAnormal", "N93.9", "Sangramento uterino anormal", "USG transvaginal indicada", "-", 3),
            ("DorPelvica", "N94.8", "Dor pelvica a esclarecer", "USG transvaginal indicada", "-", 4),
            ("GestacaoInicial", "Z34.0", "Gestacao inicial < 10 semanas", "USG transvaginal para datacao", "true", 5)
        ]
    },
    "40901505": {
        "name": "Perfil biofisico fetal",
        "slug": "Perfil_biofisico_fetal",
        "febrasgo": "Manual de Medicina Fetal",
        "indications": "    - Gestação de alto risco >= 32 semanas\n    - Suspeita de sofrimento fetal\n    - Restrição de crescimento intrauterino\n    - Oligodrâmnio",
        "contraindications": "    - Gestação < 32 semanas (teste menos confiável)",
        "gestante_contra": ("Indicacao: Gestacao >= 32 semanas de alto risco", "Perfil biofisico para avaliacao de vitalidade"),
        "approvals": [
            ("AltoRisco", "O09.9", "Gestacao de alto risco >= 32 semanas", "Perfil biofisico indicado", "true", 3),
            ("RCIU", "O36.5", "Restricao de crescimento intrauterino", "Perfil biofisico para vigilancia", "true", 4)
        ]
    },
    "41301099": {
        "name": "Coleta de material para colpocitologia oncotica",
        "slug": "Coleta_Papanicolau",
        "febrasgo": "Manual de Prevenção do Câncer Cervical",
        "indications": "    - Rastreio câncer cervical (25-64 anos)\n    - Periodicidade: anual nos 2 primeiros anos, depois trienal se negativos\n    - Mulheres sexualmente ativas",
        "contraindications": "    - Menstruação (aguardar)\n    - Infecção vaginal ativa (tratar primeiro)\n    - Gestação não é contraindicação",
        "gestante_contra": ("Indicacao: Gestante pode realizar Papanicolau", "Rastreio seguro durante gestacao"),
        "approvals": [
            ("Rastreio2564", "Z12.4", "Rastreio cancer cervical (25-64 anos)", "Colpocitologia indicada", "-", 3)
        ]
    },
    "41301102": {
        "name": "Colposcopia",
        "slug": "Colposcopia",
        "febrasgo": "Manual de Colposcopia",
        "indications": "    - Citologia anormal (ASC-US, LSIL, HSIL, AGC)\n    - Teste HPV positivo\n    - Lesão cervical visível\n    - Sangramento pós-coito",
        "contraindications": "    - Nenhuma contraindicação absoluta\n    - Gestação não contraindica, mas biópsia deve ser cautelosa",
        "gestante_contra": ("Indicacao: Gestante com citologia alterada pode realizar", "Colposcopia segura, biopsia criterios"),
        "approvals": [
            ("CitologiaAnormal", "R87.6", "Citologia cervical anormal", "Colposcopia indicada", "-", 3),
            ("HPVpositivo", "B97.7", "Teste HPV positivo", "Colposcopia indicada", "-", 4)
        ]
    },
    "41301374": {
        "name": "Vulvoscopia",
        "slug": "Vulvoscopia",
        "febrasgo": "Manual de Patologia do Trato Genital Inferior",
        "indications": "    - Lesões vulvares suspeitas\n    - Prurido vulvar persistente\n    - Líquen escleroso\n    - Neoplasia intraepitelial vulvar (VIN)",
        "contraindications": "    - Nenhuma contraindicação absoluta",
        "gestante_contra": ("Indicacao: Gestante com lesao vulvar pode realizar", "Vulvoscopia segura durante gestacao"),
        "approvals": [
            ("LesaoVulvar", "N90.8", "Lesao vulvar suspeita", "Vulvoscopia indicada", "-", 3),
            ("LiquenEscleroso", "L90.0", "Liquen escleroso vulvar", "Vulvoscopia para avaliacao", "-", 4)
        ]
    },
}

# Merge both dictionaries
PROCEDURES.update(PROCEDURES_PART2)

def generate_dmn(tuss_code, proc_data):
    """Generate TIER-1 DMN file for a procedure"""
    
    # Build contraindication rules
    contra_rules = []
    
    # Gestante contraindication (if applicable)
    if "gestante_contra" in proc_data:
        obs, fund = proc_data["gestante_contra"]
        contra_rules.append(CONTRA_GESTANTE.format(
            tuss=tuss_code,
            obs=obs,
            fund=fund
        ))
    
    # Laudo obrigatório
    contra_rules.append(CONTRA_LAUDO.format(tuss=tuss_code))
    
    # Build approval rules
    approval_rules = []
    for rule_id, cid, desc, obs, fund, gestante_req, idx in [(a[0], a[1], a[2], a[3], a[4], a[5]) for a in proc_data.get("approvals", [])]:
        approval_rules.append(APPROVAL_CID.format(
            tuss=tuss_code,
            rule_id=rule_id,
            desc=desc,
            cid=cid,
            gestante_req=gestante_req,
            obs=obs,
            fund=fund,
            idx=idx
        ))
    
    # Generate final DMN
    dmn_content = DMN_TEMPLATE.format(
        tuss_code=tuss_code,
        proc_name=proc_data["name"],
        proc_slug=proc_data["slug"],
        febrasgo_ref=proc_data["febrasgo"],
        clinical_indications=proc_data["indications"],
        contraindications=proc_data["contraindications"],
        contraindication_rules="\n".join(contra_rules),
        approval_rules="\n".join(approval_rules)
    )
    
    return dmn_content

# Main execution
if __name__ == "__main__":
    import os
    
    generated_count = 0
    for tuss_code, proc_data in sorted(PROCEDURES.items()):
        dmn_file_path = f"{tuss_code}/regra.dmn.xml"
        
        # Generate DMN
        dmn_content = generate_dmn(tuss_code, proc_data)
        
        # Write to file
        with open(dmn_file_path, 'w', encoding='utf-8') as f:
            f.write(dmn_content)
        
        generated_count += 1
        print(f"✓ Generated {tuss_code} - {proc_data['name']}")
    
    print(f"\n✅ Generated {generated_count} TIER-1 DMN files successfully!")
