#!/usr/bin/env python3
"""
Create the 6 missing EWS-qSOFA DMN files
"""
import json
import os
from datetime import datetime

DMN_TEMPLATE = '''<?xml version='1.0' encoding='UTF-8'?>
<!--
  ============================================================================
  {rule_id} - {rule_name}
  ============================================================================
  Versao: 1.0.0 ({date})
  Categoria: CLINICAL_SAFETY
  Perspectiva: HOSPITAL (Clinico)
  ============================================================================
-->
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/"
             xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/" id="Definitions_{rule_id_safe}" name="{rule_name}" targetNamespace="http://camunda.org/schema/1.0/dmn">

  <decision id="Decision_{rule_id_safe}" name="{rule_name}">
    <decisionTable id="DecisionTable_{rule_id_safe}" hitPolicy="FIRST">

      <input id="Input_1" label="Frequencia Respiratoria">
        <inputExpression id="InputExpression_1" typeRef="number">
          <text>frequenciaRespiratoria</text>
        </inputExpression>
      </input>

      <input id="Input_2" label="Pressao Sistolica">
        <inputExpression id="InputExpression_2" typeRef="number">
          <text>pressaoSistolica</text>
        </inputExpression>
      </input>

      <input id="Input_3" label="Alteracao Mental">
        <inputExpression id="InputExpression_3" typeRef="boolean">
          <text>alteracaoMental</text>
        </inputExpression>
      </input>

      <output id="Output_1" label="Resultado" name="resultado" typeRef="string">
        <outputValues><text>"Prosseguir", "Bloquear", "Alertar", "Revisar"</text></outputValues>
      </output>
      <output id="Output_2" label="Observacao" name="observacao" typeRef="string" />
      <output id="Output_3" label="Acao Recomendada" name="acaoRecomendada" typeRef="string" />
      <output id="Output_4" label="Alertas Conformidade" name="alertasConformidade" typeRef="string">
        <outputValues><text>"NENHUM", "DUP", "FREQ", "PRAZO", "DOC", "VALOR", "CRED", "CONTRATO"</text></outputValues>
      </output>
      <output id="Output_5" label="Risco Denial" name="riscoDenial" typeRef="string">
        <outputValues><text>"BAIXO", "MEDIO", "ALTO", "CRITICO"</text></outputValues>
      </output>

      <rule id="Rule_Critico_1">
        <description>qSOFA >= 2 pontos - Alto risco de sepse</description>
        <inputEntry id="InputEntry_C1_1"><text>>= 22</text></inputEntry>
        <inputEntry id="InputEntry_C1_2"><text>&lt;= 100</text></inputEntry>
        <inputEntry id="InputEntry_C1_3"><text>true</text></inputEntry>
        <outputEntry id="OutputEntry_C1_1"><text>"Alertar"</text></outputEntry>
        <outputEntry id="OutputEntry_C1_2"><text>"qSOFA >= 2: Alto risco de sepse. Avaliacao medica urgente necessaria."</text></outputEntry>
        <outputEntry id="OutputEntry_C1_3"><text>"Ativar protocolo de sepse, avaliar imediatamente."</text></outputEntry>
        <outputEntry id="OutputEntry_C1_4"><text>"PRAZO"</text></outputEntry>
        <outputEntry id="OutputEntry_C1_5"><text>"CRITICO"</text></outputEntry>
      </rule>

      <rule id="Rule_Alerta_1">
        <description>qSOFA = 1 ponto - Monitoramento</description>
        <inputEntry id="InputEntry_A1_1"><text>>= 22</text></inputEntry>
        <inputEntry id="InputEntry_A1_2"><text>-</text></inputEntry>
        <inputEntry id="InputEntry_A1_3"><text>-</text></inputEntry>
        <outputEntry id="OutputEntry_A1_1"><text>"Alertar"</text></outputEntry>
        <outputEntry id="OutputEntry_A1_2"><text>"qSOFA = 1: Monitoramento necessario."</text></outputEntry>
        <outputEntry id="OutputEntry_A1_3"><text>"Monitorar sinais vitais, reavaliar em 1-2h."</text></outputEntry>
        <outputEntry id="OutputEntry_A1_4"><text>"NENHUM"</text></outputEntry>
        <outputEntry id="OutputEntry_A1_5"><text>"MEDIO"</text></outputEntry>
      </rule>

      <rule id="Rule_Normal_1">
        <description>qSOFA = 0 - Normal</description>
        <inputEntry id="InputEntry_N1_1"><text>&lt; 22</text></inputEntry>
        <inputEntry id="InputEntry_N1_2"><text>> 100</text></inputEntry>
        <inputEntry id="InputEntry_N1_3"><text>false</text></inputEntry>
        <outputEntry id="OutputEntry_N1_1"><text>"Prosseguir"</text></outputEntry>
        <outputEntry id="OutputEntry_N1_2"><text>"qSOFA = 0: Parametros normais."</text></outputEntry>
        <outputEntry id="OutputEntry_N1_3"><text>"Continuar cuidados de rotina."</text></outputEntry>
        <outputEntry id="OutputEntry_N1_4"><text>"NENHUM"</text></outputEntry>
        <outputEntry id="OutputEntry_N1_5"><text>"BAIXO"</text></outputEntry>
      </rule>

      <rule id="Rule_Fallback_{rule_id_safe}">
        <description>Regra padrao - Requer avaliacao manual</description>
        <inputEntry id="InputEntry_F_1"><text>-</text></inputEntry>
        <inputEntry id="InputEntry_F_2"><text>-</text></inputEntry>
        <inputEntry id="InputEntry_F_3"><text>-</text></inputEntry>
        <outputEntry id="OutputEntry_F_1"><text>"Revisar"</text></outputEntry>
        <outputEntry id="OutputEntry_F_2"><text>"Avaliar criterios qSOFA manualmente."</text></outputEntry>
        <outputEntry id="OutputEntry_F_3"><text>"Revisar sinais vitais e estado mental."</text></outputEntry>
        <outputEntry id="OutputEntry_F_4"><text>"NENHUM"</text></outputEntry>
        <outputEntry id="OutputEntry_F_5"><text>"MEDIO"</text></outputEntry>
      </rule>

    </decisionTable>
  </decision>

  <dmndi:DMNDI>
    <dmndi:DMNDiagram id="DMNDiagram_{rule_id_safe}">
      <dmndi:DMNShape id="DMNShape_Decision_{rule_id_safe}" dmnElementRef="Decision_{rule_id_safe}">
        <dc:Bounds height="80" width="180" x="160" y="100" />
      </dmndi:DMNShape>
    </dmndi:DMNDiagram>
  </dmndi:DMNDI>

</definitions>'''

def main():
    with open('docs/Migration/migration_manifest.json') as f:
        data = json.load(f)

    # Find the missing EWS-qSOFA entries
    qsofa_entries = [e for e in data['entries'] if e.get('rule_id', '').startswith('EWS-qSOFA')]

    print(f"Found {len(qsofa_entries)} EWS-qSOFA entries in manifest")

    created = 0
    for entry in qsofa_entries:
        rule_id = entry.get('rule_id', '')
        new_path = entry.get('new_path', '')
        # Convert platform/ to healthcare_platform/
        actual_path = new_path.replace('platform/', 'healthcare_platform/', 1)

        if os.path.exists(actual_path):
            print(f"  ✓ {rule_id} already exists")
            continue

        rule_id_safe = rule_id.replace('-', '_')
        rule_name = entry.get('rule_name', f'qSOFA Score {rule_id.split("-")[-1]}')

        # Generate DMN content
        dmn_content = DMN_TEMPLATE.format(
            rule_id=rule_id,
            rule_id_safe=rule_id_safe,
            rule_name=rule_name,
            date=datetime.now().strftime('%Y-%m-%d')
        )

        # Ensure directory exists
        os.makedirs(os.path.dirname(actual_path), exist_ok=True)

        # Write file
        with open(actual_path, 'w', encoding='utf-8') as f:
            f.write(dmn_content)

        created += 1
        print(f"  ✓ Created: {rule_id} -> {actual_path}")

    print(f"\n✓ Created {created} missing qSOFA files")

if __name__ == '__main__':
    main()
