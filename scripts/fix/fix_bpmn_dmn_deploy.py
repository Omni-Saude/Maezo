#!/usr/bin/env python3
"""
MAEZO — Fix BPMN + DMN para deploy no CIB Seven / Camunda 7.x

Baseado em: docs/CorrecoesGerais.md + modelo.dmn (referencia)

BPMN fixes:
  1. Adiciona xmlns:camunda no <bpmn:definitions> se ausente
  2. Adiciona camunda:historyTimeToLive="30" em <bpmn:process> que nao tem
  3. Remove referencias orfas no BPMNDiagram (BPMNEdge/BPMNShape sem elemento)
  4. Adiciona default flow em exclusiveGateway com multiplos outgoing e sem default
  5. Remove atributo sourceRef_hint invalido de BPMNEdge
  6. Corrige timerEventDefinition vazio (adiciona timeCycle default)
  7. Converte <externalTask> invalido para formato Camunda correto
  8. Adiciona camunda:type="external" em serviceTask sem atributos de execucao
  9. Converte <bpmn:task> generico para <bpmn:manualTask>
 10. Corrige sequenceFlow com IDs duplicados
 11. Move <bpmn:error>/<bpmn:message> que aparecem fora do <bpmn:process>

DMN fixes (baseado no modelo.dmn):
 12. Adiciona xmlns:camunda="http://camunda.org/schema/1.0/dmn"
 13. Adiciona namespaces faltantes (xmlns:dmndi, xmlns:dc, xmlns:di)
 14. Renomeia targetNamespace para namespace (DMN 1.3 spec)
 15. Adiciona camunda:historyTimeToLive="180" em <decision> que nao tem
 16. Garante secao DMNDI no final (se ausente)

Uso:
  python3 scripts/fix/fix_bpmn_dmn_deploy.py                    # aplica fixes
  python3 scripts/fix/fix_bpmn_dmn_deploy.py --dry-run          # mostra o que mudaria
  python3 scripts/fix/fix_bpmn_dmn_deploy.py --bpmn-only        # so BPMN
  python3 scripts/fix/fix_bpmn_dmn_deploy.py --dmn-only         # so DMN
"""

import argparse
import re
import sys
from pathlib import Path

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"

def ok(msg):    print(f"{GREEN}  ok{NC} {msg}")
def warn(msg):  print(f"{YELLOW}  !!{NC} {msg}")
def err(msg):   print(f"{RED}FAIL{NC} {msg}")
def log(msg):   print(f"{BLUE}[fix]{NC} {msg}")


# =============================================================================
# BPMN FIXES
# =============================================================================

CAMUNDA_BPMN_NS = 'http://camunda.org/schema/1.0/bpmn'


def fix_bpmn_camunda_ns(content: str) -> tuple[str, bool]:
    """Adiciona xmlns:camunda no <bpmn:definitions> se ausente."""
    if 'xmlns:camunda=' in content:
        return content, False

    pattern = r'(<bpmn:definitions\b[^>]*?)(\s+id=)'
    replacement = f'\\1 xmlns:camunda="{CAMUNDA_BPMN_NS}"\\2'
    new_content, count = re.subn(pattern, replacement, content, count=1)

    if count == 0:
        pattern2 = r'(<definitions\b[^>]*?)(\s+id=)'
        replacement2 = f'\\1 xmlns:camunda="{CAMUNDA_BPMN_NS}"\\2'
        new_content, count = re.subn(pattern2, replacement2, content, count=1)

    return new_content, count > 0


def fix_bpmn_ttl(content: str) -> tuple[str, bool]:
    """Adiciona camunda:historyTimeToLive='30' em <bpmn:process> que nao tem."""
    if 'historyTimeToLive' in content:
        return content, False

    # [^>]* apos isExecutable permite outros atributos (ex: camunda:versionTag) antes do >
    pattern = r'(<bpmn:process\b[^>]*isExecutable="true"[^>]*)(>)'
    replacement = r'\1 camunda:historyTimeToLive="30"\2'
    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        pattern2 = r'(<process\b[^>]*isExecutable="true"[^>]*)(>)'
        new_content, count = re.subn(pattern2, replacement, content)

    return new_content, count > 0


def fix_bpmn_orphan_refs(content: str) -> tuple[str, bool, int]:
    """Remove referencias orfas no BPMNDiagram."""
    all_ids = set(re.findall(r'\bid="([^"]+)"', content))

    removed = 0
    def remove_orphan_edge(m):
        nonlocal removed
        if m.group(1) not in all_ids:
            removed += 1
            return ''
        return m.group(0)

    content = re.sub(
        r'<bpmndi:BPMNEdge\s+id="[^"]*"\s+bpmnElement="([^"]*)"[^>]*>.*?</bpmndi:BPMNEdge>\s*',
        remove_orphan_edge,
        content,
        flags=re.DOTALL,
    )

    def remove_orphan_shape(m):
        nonlocal removed
        if m.group(1) not in all_ids:
            removed += 1
            return ''
        return m.group(0)

    content = re.sub(
        r'<bpmndi:BPMNShape\s+id="[^"]*"\s+bpmnElement="([^"]*)"[^>]*>.*?</bpmndi:BPMNShape>\s*',
        remove_orphan_shape,
        content,
        flags=re.DOTALL,
    )

    return content, removed > 0, removed


def fix_bpmn_gateway_defaults(content: str) -> tuple[str, bool, int]:
    """Adiciona default flow em exclusiveGateway sem default."""
    fixed_count = 0

    # (?:"[^"]*"|'[^']*'|[^>"']) impede backtracking catastrofico
    gw_pattern = re.compile(
        r'(<bpmn:exclusiveGateway\s+(?:"[^"]*"|\'[^\']*\'|[^>"\'  ])*>)'
        r'(.*?)'
        r'(</bpmn:exclusiveGateway>)',
        re.DOTALL,
    )

    def fix_gateway(m):
        nonlocal fixed_count
        open_tag = m.group(1)
        body = m.group(2)
        close_tag = m.group(3)

        if 'default=' in open_tag:
            return m.group(0)

        outgoing = re.findall(r'<bpmn:outgoing>([^<]+)</bpmn:outgoing>', body)
        if len(outgoing) < 2:
            return m.group(0)

        default_flow = outgoing[-1]
        new_open_tag = open_tag[:-1] + f' default="{default_flow}">'
        fixed_count += 1
        return f'{new_open_tag}{body}{close_tag}'

    new_content = gw_pattern.sub(fix_gateway, content)

    if fixed_count > 0:
        for m in gw_pattern.finditer(new_content):
            open_tag = m.group(1)
            default_match = re.search(r'default="([^"]*)"', open_tag)
            if default_match:
                default_flow_id = default_match.group(1)
                flow_pattern = re.compile(
                    rf'(<bpmn:sequenceFlow\s+(?:"[^"]*"|\'[^\']*\'|[^>"\'  ])*id="{re.escape(default_flow_id)}"(?:"[^"]*"|\'[^\']*\'|[^>"\'  ])*>)\s*'
                    rf'<bpmn:conditionExpression[^<]*(?:<!\[CDATA\[.*?\]\]>)?[^<]*</bpmn:conditionExpression>\s*',
                    re.DOTALL,
                )
                new_content = flow_pattern.sub(r'\1\n    ', new_content)

    return new_content, fixed_count > 0, fixed_count


def fix_bpmn_sourceref_hint(content: str) -> tuple[str, bool, int]:
    """Remove atributo sourceRef_hint invalido de BPMNEdge."""
    pattern = r'\s+sourceRef_hint="[^"]*"'
    new_content, count = re.subn(pattern, '', content)
    return new_content, count > 0, count


def fix_bpmn_empty_timer(content: str) -> tuple[str, bool, int]:
    """Corrige timerEventDefinition vazio — adiciona timeCycle diario."""
    pattern = r'<bpmn:timerEventDefinition\s+id="([^"]*)"(\s*)/>'

    def add_timer_cycle(m):
        timer_id = m.group(1)
        return (
            f'<bpmn:timerEventDefinition id="{timer_id}">\n'
            f'          <bpmn:timeCycle xsi:type="bpmn:tFormalExpression">0 0 6 * * ?</bpmn:timeCycle>\n'
            f'        </bpmn:timerEventDefinition>'
        )

    new_content, count = re.subn(pattern, add_timer_cycle, content)
    return new_content, count > 0, count


def fix_bpmn_external_task_element(content: str) -> tuple[str, bool, int]:
    """Converte <externalTask topic="X"/> para camunda:type/topic no serviceTask pai."""
    pattern = re.compile(
        r'(<bpmn:serviceTask\s+[^>]*?)(>)\s*'
        r'<bpmn:extensionElements>\s*'
        r'<externalTask\s+topic="([^"]*)"\s*/>\s*'
        r'</bpmn:extensionElements>',
        re.DOTALL,
    )

    fixed = 0

    def convert(m):
        nonlocal fixed
        open_attrs = m.group(1)
        topic = m.group(3)
        open_attrs = re.sub(r'\s*implementation="external"', '', open_attrs)
        fixed += 1
        return f'{open_attrs} camunda:type="external" camunda:topic="{topic}">'

    new_content = pattern.sub(convert, content)
    return new_content, fixed > 0, fixed


def fix_bpmn_bare_service_task(content: str) -> tuple[str, bool, int]:
    """Adiciona camunda:type='external' em serviceTask sem atributos de execucao."""
    fixed = 0

    def fix_task(m):
        nonlocal fixed
        tag = m.group(0)

        exec_attrs = [
            'camunda:type=', 'camunda:class=', 'camunda:delegateExpression=',
            'camunda:expression=', 'implementation=',
        ]
        if any(attr in tag for attr in exec_attrs):
            return tag

        name_match = re.search(r'name="([^"]*)"', tag)
        if name_match:
            name = name_match.group(1).replace('&#10;', ' ').strip()
            topic = re.sub(r'[^a-zA-Z0-9]+', '-', name).strip('-').lower()
        else:
            id_match = re.search(r'id="([^"]*)"', tag)
            topic = id_match.group(1).lower().replace('_', '-') if id_match else 'generic-task'

        fixed += 1
        return tag[:-1] + f' camunda:type="external" camunda:topic="{topic}">'

    new_content = re.sub(
        r'<bpmn:serviceTask\s+[^/]*?>',
        fix_task,
        content,
    )

    return new_content, fixed > 0, fixed


def fix_bpmn_bare_task(content: str) -> tuple[str, bool, int]:
    """Converte <bpmn:task> (generico) para <bpmn:manualTask>."""
    count = content.count('<bpmn:task ')
    if count == 0:
        return content, False, 0

    content = content.replace('<bpmn:task ', '<bpmn:manualTask ')
    content = content.replace('</bpmn:task>', '</bpmn:manualTask>')
    return content, True, count


def fix_bpmn_bare_business_rule_task(content: str) -> tuple[str, bool, int]:
    """Converte businessRuleTask sem decisionRef para external task."""
    fixed = 0

    def fix_brt(m):
        nonlocal fixed
        tag = m.group(0)
        if 'camunda:decisionRef=' in tag or 'camunda:type=' in tag:
            return tag

        name_match = re.search(r'name="([^"]*)"', tag)
        if name_match:
            name = name_match.group(1).replace('&#10;', ' ').strip()
            topic = 'dmn.' + re.sub(r'[^a-zA-Z0-9]+', '-', name).strip('-').lower()
        else:
            id_match = re.search(r'id="([^"]*)"', tag)
            topic = 'dmn.' + (id_match.group(1).lower().replace('_', '-') if id_match else 'generic')

        fixed += 1
        # Converter para serviceTask external (que o worker pode processar)
        new_tag = tag.replace('bpmn:businessRuleTask', 'bpmn:serviceTask')
        return new_tag[:-1] + f' camunda:type="external" camunda:topic="{topic}">'

    new_content = re.sub(
        r'<bpmn:businessRuleTask\s+[^/]*?>',
        fix_brt,
        content,
    )
    # Tambem fechar tags
    if fixed > 0:
        new_content = new_content.replace('</bpmn:businessRuleTask>', '</bpmn:serviceTask>')

    return new_content, fixed > 0, fixed


def fix_bpmn_duplicate_flow_ids(content: str) -> tuple[str, bool, int]:
    """Corrige sequenceFlow com IDs duplicados."""
    flow_ids = re.findall(r'<bpmn:sequenceFlow\s+id="([^"]*)"', content)
    seen = {}
    duplicates = set()
    for fid in flow_ids:
        seen[fid] = seen.get(fid, 0) + 1
        if seen[fid] > 1:
            duplicates.add(fid)

    if not duplicates:
        return content, False, 0

    fixed = 0
    for dup_id in duplicates:
        counter = [0]

        def rename_dup(m, _dup_id=dup_id):
            nonlocal fixed
            counter[0] += 1
            if counter[0] == 1:
                return m.group(0)
            new_id = f'{_dup_id}_{counter[0]}'
            fixed += 1
            return m.group(0).replace(f'id="{_dup_id}"', f'id="{new_id}"', 1)

        content = re.sub(
            rf'<bpmn:sequenceFlow\s+id="{re.escape(dup_id)}"[^>]*(?:/>|>)',
            rename_dup,
            content,
        )

    return content, fixed > 0, fixed


def _insert_before_diagram(content: str, elements_block: str) -> str:
    """Insere elementos ANTES do <bpmndi:BPMNDiagram> (posicao correta no XSD)."""
    if '<bpmndi:BPMNDiagram' in content:
        return content.replace(
            '<bpmndi:BPMNDiagram',
            f'{elements_block}\n\n  <bpmndi:BPMNDiagram',
            1,
        )
    # Fallback: antes do </bpmn:definitions>
    return content.replace(
        '</bpmn:definitions>',
        f'{elements_block}\n</bpmn:definitions>',
    )


def fix_bpmn_error_message_order(content: str) -> tuple[str, bool, int]:
    """Move <bpmn:error>/<bpmn:message>/<bpmn:signal> para entre </bpmn:process> e <bpmndi:BPMNDiagram>.

    BPMN XSD sequence: rootElement* (process, error, message, signal) -> BPMNDiagram*
    Todos os rootElements devem vir ANTES do BPMNDiagram.
    Camunda Modeler coloca error/message/signal DEPOIS do process, ANTES do diagram.
    """
    changed = False
    total_moved = 0

    # Caso 1: entre </bpmn:collaboration> e <bpmn:process>
    pattern1 = re.compile(
        r'(</bpmn:collaboration>)\s*'
        r'((?:\s*<bpmn:(?:error|message|signal)\s[^>]*/>\s*)+)'
        r'(\s*<bpmn:process\b)',
        re.DOTALL,
    )
    match = pattern1.search(content)
    if match:
        elements_block = match.group(2).strip()
        count = len(re.findall(r'<bpmn:(?:error|message|signal)\s', elements_block))
        content = pattern1.sub(r'\1\3', content)
        content = _insert_before_diagram(content, f'  {elements_block}')
        changed = True
        total_moved += count

    # Caso 2: logo apos <bpmn:definitions...> e antes de <bpmn:process> (sem collaboration)
    pattern2 = re.compile(
        r'(>)\s*'
        r'((?:\s*(?:<!--[^>]*-->\s*)*<bpmn:(?:error|message|signal)\s[^>]*/>\s*)+)'
        r'(\s*<bpmn:process\b)',
        re.DOTALL,
    )
    match = pattern2.search(content)
    if match and '</bpmn:collaboration>' not in content[:match.start() + 50]:
        elements_block = match.group(2).strip()
        elements_only = '\n  '.join(
            line.strip() for line in elements_block.split('\n')
            if line.strip().startswith('<bpmn:')
        )
        count = len(re.findall(r'<bpmn:(?:error|message|signal)\s', elements_only))
        if count > 0:
            content = pattern2.sub(r'\1\3', content, count=1)
            content = _insert_before_diagram(content, f'  {elements_only}')
            changed = True
            total_moved += count

    # Caso 3: elementos DEPOIS do </bpmndi:BPMNDiagram> (bug de fix anterior)
    pattern3 = re.compile(
        r'(</bpmndi:BPMNDiagram>)\s*'
        r'((?:\s*<bpmn:(?:error|message|signal)\s[^>]*/>\s*)+)'
        r'(\s*</bpmn:definitions>)',
        re.DOTALL,
    )
    match = pattern3.search(content)
    if match:
        elements_block = match.group(2).strip()
        count = len(re.findall(r'<bpmn:(?:error|message|signal)\s', elements_block))
        # Remover de posicao errada
        content = pattern3.sub(r'\1\3', content)
        # Inserir na posicao correta (antes do diagram)
        content = _insert_before_diagram(content, f'  {elements_block}')
        changed = True
        total_moved += count

    return content, changed, total_moved


def fix_bpmn_child_element_order(content: str) -> tuple[str, bool, int]:
    """Reordena filhos de flow elements: incoming/outgoing devem vir ANTES de eventDefinition.

    BPMN 2.0 XSD sequence: FlowNode(incoming*, outgoing*) -> CatchEvent(eventDefinition*)
    CIB Seven valida estritamente esta ordem.
    """
    fixed = 0

    # Pattern: encontra blocos onde eventDefinition vem antes de incoming/outgoing
    # dentro de qualquer elemento (startEvent, endEvent, intermediateEvent, boundaryEvent, etc.)
    event_types = (
        'startEvent', 'endEvent',
        'intermediateCatchEvent', 'intermediateThrowEvent',
        'boundaryEvent',
    )

    for etype in event_types:
        # Captura a tag completa: <bpmn:startEvent ...> ... </bpmn:startEvent>
        tag_pattern = re.compile(
            rf'(<bpmn:{etype}\b[^>]*>)(.*?)(</bpmn:{etype}>)',
            re.DOTALL,
        )

        def reorder_children(m):
            nonlocal fixed
            open_tag = m.group(1)
            body = m.group(2)
            close_tag = m.group(3)

            # Separar incoming/outgoing e eventDefinitions
            incoming_outgoing = re.findall(
                r'\s*<bpmn:(?:incoming|outgoing)>[^<]*</bpmn:(?:incoming|outgoing)>',
                body,
            )
            event_defs = re.findall(
                r'\s*<bpmn:\w+EventDefinition[^>]*(?:/>|>.*?</bpmn:\w+EventDefinition>)',
                body,
                re.DOTALL,
            )

            if not incoming_outgoing or not event_defs:
                return m.group(0)

            # Verificar se ja esta na ordem correta
            # TODOS incoming/outgoing devem vir ANTES de TODOS eventDefinitions
            last_io_pos = max(body.find(io.strip()) for io in incoming_outgoing)
            first_ed_pos = min(body.find(ed.strip()) for ed in event_defs)

            if last_io_pos < first_ed_pos:
                return m.group(0)  # Ja na ordem correta

            # Remover incoming/outgoing e eventDefs do body
            new_body = body
            for io in incoming_outgoing:
                new_body = new_body.replace(io.strip(), '', 1)
            for ed in event_defs:
                new_body = new_body.replace(ed.strip(), '', 1)

            # Limpar linhas vazias extras
            new_body = re.sub(r'\n\s*\n\s*\n', '\n', new_body)

            # Reconstruir: incoming/outgoing primeiro, depois eventDefinitions, depois o resto
            indent = '      '
            io_block = '\n'.join(f'{indent}{io.strip()}' for io in incoming_outgoing)
            ed_block = '\n'.join(f'{indent}{ed.strip()}' for ed in event_defs)

            fixed += 1
            return f'{open_tag}\n{io_block}\n{ed_block}{new_body}{close_tag}'

        content = tag_pattern.sub(reorder_children, content)

    return content, fixed > 0, fixed


def fix_bpmn_nested_process(content: str) -> tuple[str, bool, int]:
    """Converte <bpmn:process> aninhados dentro de outro process para <bpmn:subProcess>.

    BPMN nao permite processos aninhados. Quando um <bpmn:process> aparece dentro de
    outro <bpmn:process>, deve ser convertido para <bpmn:subProcess>.
    """
    # Encontrar processes aninhados: um <bpmn:process que aparece ANTES do </bpmn:process> do pai
    # Estrategia: encontrar <bpmn:process> que NAO sao filhos diretos de <bpmn:definitions>
    processes = list(re.finditer(r'<bpmn:process\s', content))
    if len(processes) <= 1:
        return content, False, 0

    fixed = 0
    # O primeiro process e o principal; os demais sao aninhados
    for proc_match in processes[1:]:
        pos = proc_match.start()
        # Verificar se estamos dentro de outro process (nao fechado)
        before = content[:pos]
        opens = len(re.findall(r'<bpmn:process\s', before))
        closes = before.count('</bpmn:process>')
        if opens > closes:
            # Aninhado - converter esta ocorrencia
            # Encontrar o ID para remover isExecutable e historyTimeToLive
            tag_end = content.index('>', pos)
            tag = content[pos:tag_end + 1]
            new_tag = tag.replace('<bpmn:process', '<bpmn:subProcess')
            new_tag = re.sub(r'\s*isExecutable="[^"]*"', '', new_tag)
            new_tag = re.sub(r'\s*camunda:historyTimeToLive="[^"]*"', '', new_tag)
            content = content[:pos] + new_tag + content[tag_end + 1:]
            fixed += 1

    if fixed > 0:
        content = content.replace('</bpmn:process>', '</bpmn:subProcess>', fixed)

    return content, fixed > 0, fixed


def fix_bpmn_empty_subprocess(content: str) -> tuple[str, bool, int]:
    """Adiciona startEvent + endEvent em subProcess vazio (sem startEvent)."""
    fixed = 0

    def _make_internal_flow(sub_id):
        start_id = f'StartEvent_{sub_id}'
        end_id = f'EndEvent_{sub_id}'
        flow_id = f'Flow_internal_{sub_id}'
        return (
            f'\n      <bpmn:startEvent id="{start_id}" name="Start">'
            f'\n        <bpmn:outgoing>{flow_id}</bpmn:outgoing>'
            f'\n      </bpmn:startEvent>'
            f'\n      <bpmn:endEvent id="{end_id}" name="End">'
            f'\n        <bpmn:incoming>{flow_id}</bpmn:incoming>'
            f'\n      </bpmn:endEvent>'
            f'\n      <bpmn:sequenceFlow id="{flow_id}" sourceRef="{start_id}" targetRef="{end_id}" />'
        )

    # Caso 1: self-closing subProcess (<bpmn:subProcess ... />)
    def expand_self_closing(m):
        nonlocal fixed
        tag = m.group(0)
        id_match = re.search(r'id="([^"]*)"', tag)
        sub_id = id_match.group(1) if id_match else f'sub_{fixed}'
        # Converter self-closing para open+content+close
        open_tag = tag[:-2] + '>'
        internal = _make_internal_flow(sub_id)
        fixed += 1
        return f'{open_tag}{internal}\n    </bpmn:subProcess>'

    content = re.sub(
        r'<bpmn:subProcess\b[^>]*/\s*>',
        expand_self_closing,
        content,
    )

    # Caso 2: subProcess com open/close mas sem startEvent
    def add_internal_flow(m):
        nonlocal fixed
        open_tag = m.group(1)
        body = m.group(2)
        close_tag = m.group(3)

        if '<bpmn:startEvent' in body:
            return m.group(0)

        id_match = re.search(r'id="([^"]*)"', open_tag)
        sub_id = id_match.group(1) if id_match else f'sub_{fixed}'
        internal = _make_internal_flow(sub_id)
        fixed += 1
        return f'{open_tag}{body}{internal}\n    {close_tag}'

    content = re.sub(
        r'(<bpmn:subProcess\b[^>]*>)(.*?)(</bpmn:subProcess>)',
        add_internal_flow,
        content,
        flags=re.DOTALL,
    )

    return content, fixed > 0, fixed


def fix_bpmn_gateway_missing_condition(content: str) -> tuple[str, bool, int]:
    """Adiciona conditionExpression em flows de exclusiveGateway sem condicao.

    Exclusive gateways requerem condicao em TODOS os outgoing flows exceto o default.
    """
    fixed = 0

    # Encontrar todos os exclusive gateways com default
    for gw_match in re.finditer(
        r'<bpmn:exclusiveGateway\s+[^>]*default="([^"]*)"[^>]*>',
        content,
    ):
        default_flow = gw_match.group(1)
        # Pegar todos os outgoing
        gw_end = content.index('</bpmn:exclusiveGateway>', gw_match.start())
        gw_body = content[gw_match.start():gw_end]
        outgoing = re.findall(r'<bpmn:outgoing>([^<]+)</bpmn:outgoing>', gw_body)

        for flow_id in outgoing:
            if flow_id == default_flow:
                continue
            # Verificar se o sequenceFlow ja tem conditionExpression
            flow_pattern = re.compile(
                rf'(<bpmn:sequenceFlow\s+[^>]*id="{re.escape(flow_id)}"[^>]*/?>)',
            )
            flow_match = flow_pattern.search(content)
            if not flow_match:
                continue

            flow_tag = flow_match.group(1)
            # Verificar se ja tem conditionExpression (inline ou como child)
            if flow_tag.endswith('/>'):
                # Self-closing - nao tem filhos, precisa de condicao
                # Extrair nome do flow para gerar condicao
                name_match = re.search(r'name="([^"]*)"', flow_tag)
                condition_hint = name_match.group(1) if name_match else 'true'
                # Determinar se xsi prefix esta disponivel
                has_xsi = 'xmlns:xsi=' in content
                xsi_attr = ' xsi:type="bpmn:tFormalExpression"' if has_xsi else ''
                new_flow = flow_tag[:-2] + '>\n'
                new_flow += f'      <bpmn:conditionExpression{xsi_attr}>${{true}}</bpmn:conditionExpression>\n'
                new_flow += '    </bpmn:sequenceFlow>'
                content = content.replace(flow_tag, new_flow)
                fixed += 1
            else:
                # Tag aberta - verificar se tem conditionExpression como filho
                flow_end_pos = content.find('</bpmn:sequenceFlow>', flow_match.start())
                if flow_end_pos == -1:
                    continue
                flow_block = content[flow_match.start():flow_end_pos]
                if 'conditionExpression' not in flow_block:
                    has_xsi = 'xmlns:xsi=' in content
                    xsi_attr = ' xsi:type="bpmn:tFormalExpression"' if has_xsi else ''
                    insert_pos = flow_end_pos
                    condition = f'\n      <bpmn:conditionExpression{xsi_attr}>${{true}}</bpmn:conditionExpression>\n    '
                    content = content[:insert_pos] + condition + content[insert_pos:]
                    fixed += 1

    return content, fixed > 0, fixed


def fix_bpmn_empty_link_event_name(content: str) -> tuple[str, bool, int]:
    """Preenche linkEventDefinition com name vazio usando o name do evento pai.

    BPMN requer que link events com mesmo name sejam pareados (throw->catch).
    Se name="" o engine rejeita por duplicidade.
    """
    fixed = 0

    def fill_link_name(m):
        nonlocal fixed
        event_tag = m.group(1)
        body = m.group(2)
        close_tag = m.group(3)

        if 'linkEventDefinition' not in body or 'name=""' not in body:
            return m.group(0)

        # Extrair name do evento pai
        name_match = re.search(r'name="([^"]*)"', event_tag)
        if not name_match:
            return m.group(0)

        event_name = name_match.group(1)
        # Limpar para gerar link name valido
        link_name = re.sub(r'[^a-zA-Z0-9_]', '_', event_name).strip('_')
        if not link_name:
            return m.group(0)

        body = body.replace(
            'linkEventDefinition',
            'linkEventDefinition',
        )
        # Substituir name="" por name="link_name" no linkEventDefinition
        body = re.sub(
            r'(<bpmn:linkEventDefinition\s+[^>]*?)name=""',
            rf'\1name="{link_name}"',
            body,
        )
        fixed += 1
        return f'{event_tag}{body}{close_tag}'

    for etype in ('intermediateThrowEvent', 'intermediateCatchEvent'):
        content = re.sub(
            rf'(<bpmn:{etype}\b[^>]*>)(.*?)(</bpmn:{etype}>)',
            fill_link_name,
            content,
            flags=re.DOTALL,
        )

    return content, fixed > 0, fixed


def fix_bpmn_files(src_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Corrige todos os BPMN files."""
    bpmn_files = sorted(src_dir.rglob("*.bpmn"))
    fixed = 0
    skipped = 0

    for f in bpmn_files:
        content = f.read_text(encoding="utf-8")
        file_changed = False
        details = []

        # Fix 0: xmlns:camunda (DEVE ser primeiro)
        content, changed = fix_bpmn_camunda_ns(content)
        if changed:
            file_changed = True
            details.append("xmlns:camunda")

        # Fix 1: historyTimeToLive
        content, changed = fix_bpmn_ttl(content)
        if changed:
            file_changed = True
            details.append("TTL")

        # Fix 2: orphan diagram refs
        content, changed, count = fix_bpmn_orphan_refs(content)
        if changed:
            file_changed = True
            details.append(f"orphans:{count}")

        # Fix 3: gateway defaults
        content, changed, count = fix_bpmn_gateway_defaults(content)
        if changed:
            file_changed = True
            details.append(f"defaults:{count}")

        # Fix 4: sourceRef_hint
        content, changed, count = fix_bpmn_sourceref_hint(content)
        if changed:
            file_changed = True
            details.append(f"srcHint:{count}")

        # Fix 5: empty timer
        content, changed, count = fix_bpmn_empty_timer(content)
        if changed:
            file_changed = True
            details.append(f"timer:{count}")

        # Fix 6: <externalTask> element invalido
        content, changed, count = fix_bpmn_external_task_element(content)
        if changed:
            file_changed = True
            details.append(f"extTask:{count}")

        # Fix 7: bare serviceTask sem atributos de execucao
        content, changed, count = fix_bpmn_bare_service_task(content)
        if changed:
            file_changed = True
            details.append(f"bareSvc:{count}")

        # Fix 8: <bpmn:task> generico -> manualTask
        content, changed, count = fix_bpmn_bare_task(content)
        if changed:
            file_changed = True
            details.append(f"task->manual:{count}")

        # Fix 8b: businessRuleTask sem decisionRef -> external task
        content, changed, count = fix_bpmn_bare_business_rule_task(content)
        if changed:
            file_changed = True
            details.append(f"bareBRT:{count}")

        # Fix 9: duplicate flow IDs
        content, changed, count = fix_bpmn_duplicate_flow_ids(content)
        if changed:
            file_changed = True
            details.append(f"dupFlow:{count}")

        # Fix 10: error/message element order
        content, changed, count = fix_bpmn_error_message_order(content)
        if changed:
            file_changed = True
            details.append(f"elemOrder:{count}")

        # Fix 11: child element order (incoming/outgoing before eventDefinition)
        content, changed, count = fix_bpmn_child_element_order(content)
        if changed:
            file_changed = True
            details.append(f"childOrder:{count}")

        # Fix 12: nested <bpmn:process> -> <bpmn:subProcess>
        content, changed, count = fix_bpmn_nested_process(content)
        if changed:
            file_changed = True
            details.append(f"nestedProc:{count}")

        # Fix 13: empty subProcess without startEvent
        content, changed, count = fix_bpmn_empty_subprocess(content)
        if changed:
            file_changed = True
            details.append(f"emptySubProc:{count}")

        # Fix 14: gateway outgoing flow without condition
        content, changed, count = fix_bpmn_gateway_missing_condition(content)
        if changed:
            file_changed = True
            details.append(f"gwCondition:{count}")

        # Fix 15: empty link event definition name
        content, changed, count = fix_bpmn_empty_link_event_name(content)
        if changed:
            file_changed = True
            details.append(f"linkName:{count}")

        if file_changed:
            rel = f.relative_to(src_dir)
            if dry_run:
                warn(f"[DRY-RUN] {rel} ({', '.join(details)})")
            else:
                f.write_text(content, encoding="utf-8")
                ok(f"{rel} ({', '.join(details)})")
            fixed += 1
        else:
            skipped += 1

    return fixed, skipped


# =============================================================================
# DMN FIXES (baseado no modelo.dmn)
# =============================================================================

REQUIRED_DMN_NS = {
    'xmlns:dmndi': 'https://www.omg.org/spec/DMN/20191111/DMNDI/',
    'xmlns:dc': 'http://www.omg.org/spec/DMN/20180521/DC/',
    'xmlns:di': 'http://www.omg.org/spec/DMN/20180521/DI/',
}

CAMUNDA_DMN_NS = 'http://camunda.org/schema/1.0/dmn'


def fix_dmn_single_quotes(content: str) -> tuple[str, bool]:
    """Converte atributos XML com aspas simples para aspas duplas.

    Necessario para que os outros fixes (TTL, unique IDs) funcionem,
    pois usam regex com aspas duplas.
    """
    # Converter ='value' para ="value" em tags XML
    new_content = re.sub(r"='([^']*?)'", r'="\1"', content)
    return new_content, new_content != content


def fix_dmn_xml_entities(content: str) -> tuple[str, bool, int]:
    """Escapa caracteres XML invalidos dentro de <text> elements.

    FEEL expressions como < 60.0 e textos como M&M precisam ter
    < e & escapados para &lt; e &amp; em XML valido.
    """
    fixed = 0

    def escape_text(m):
        nonlocal fixed
        text = m.group(1)
        original = text
        # Escapar & que nao sao ja entidades XML
        text = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', text)
        # Escapar < que nao e parte de tag XML (dentro de <text> nunca deve haver tags)
        text = text.replace('<', '&lt;')
        if text != original:
            fixed += 1
        return f'<text>{text}</text>'

    new_content = re.sub(r'<text>(.*?)</text>', escape_text, content, flags=re.DOTALL)
    return new_content, fixed > 0, fixed


def fix_dmn_output_names(content: str) -> tuple[str, bool, int]:
    """Adiciona name= em <output> que tem label= mas nao tem name=.

    CIB Seven requer name= para determinar o nome da variavel de saida.
    """
    fixed = 0

    def add_name(m):
        nonlocal fixed
        tag = m.group(0)
        if 'name=' in tag:
            return tag
        # Extrair label para usar como name
        label_match = re.search(r'label="([^"]*)"', tag)
        if not label_match:
            return tag
        label = label_match.group(1)
        # Sanitizar label para nome de variavel (camelCase simples)
        name = re.sub(r'[^a-zA-Z0-9_]', '', label)
        if not name:
            return tag
        fixed += 1
        return tag.replace(f'label="{label}"', f'label="{label}" name="{name}"')

    new_content = re.sub(r'<output\s+[^/]*?/>', add_name, content)
    return new_content, fixed > 0, fixed


def fix_dmn_values_text_wrapper(content: str) -> tuple[str, bool, int]:
    """Envolve conteudo de <outputValues>/<inputValues> em <text> se ausente.

    DMN requer: <outputValues><text>"A", "B"</text></outputValues>
    Alguns arquivos tem: <outputValues>"A", "B"</outputValues> (sem <text>)
    """
    fixed = 0

    def wrap_text(m):
        nonlocal fixed
        tag_open = m.group(1)
        content_inner = m.group(2)
        tag_close = m.group(3)
        fixed += 1
        return f'{tag_open}<text>{content_inner}</text>{tag_close}'

    new_content = re.sub(
        r'(<(?:output|input)Values[^>]*>)(?!\s*<text>)([^<]+)(</(?:output|input)Values>)',
        wrap_text,
        content,
    )
    return new_content, fixed > 0, fixed


def fix_dmn_namespaces(content: str) -> tuple[str, bool]:
    """Aplica todos os fixes DMN baseados no modelo.dmn."""
    changed = False

    # 0. Corrigir DC namespace errado (DD/20100524 -> DMN/20180521)
    if 'DD/20100524/DC' in content:
        content = content.replace(
            'http://www.omg.org/spec/DD/20100524/DC/',
            'http://www.omg.org/spec/DMN/20180521/DC/',
        )
        changed = True

    # 1. Adicionar xmlns:camunda se ausente
    if 'xmlns:camunda=' not in content:
        pattern = r'(<definitions\b[^>]*?)(\s+id=)'
        replacement = f'\\1\n             xmlns:camunda="{CAMUNDA_DMN_NS}"\\2'
        new_content = re.sub(pattern, replacement, content, count=1)
        if new_content != content:
            content = new_content
            changed = True

    # 2. Adicionar namespaces faltantes
    for attr, uri in REQUIRED_DMN_NS.items():
        if attr not in content:
            pattern = r'(<definitions\b[^>]*?)(\s+id=)'
            replacement = f'\\1\n             {attr}="{uri}"\\2'
            new_content = re.sub(pattern, replacement, content, count=1)
            if new_content != content:
                content = new_content
                changed = True

    # 3. Renomear targetNamespace para namespace (DMN 1.3 spec, como no modelo.dmn)
    if 'targetNamespace=' in content:
        content = content.replace('targetNamespace=', 'namespace=')
        changed = True

    # 4. Se nao tem namespace=, adicionar
    if ' namespace=' not in content:
        pattern = r'(<definitions\b[^>]*?)(>)'
        replacement = f'\\1\n             namespace="{CAMUNDA_DMN_NS}"\\2'
        content = re.sub(pattern, replacement, content, count=1)
        changed = True

    # 5. Adicionar camunda:historyTimeToLive="180" em <decision> que nao tem
    if 'historyTimeToLive' not in content:
        pattern = r'(<decision\s+id="[^"]*"[^>]*?)(>)'
        replacement = r'\1 camunda:historyTimeToLive="180"\2'
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            content = new_content
            changed = True

    # 6. Garantir secao DMNDI existe
    if '<dmndi:DMNDI' not in content and '</definitions>' in content:
        dec_match = re.search(r'<decision\s+id="([^"]*)"', content)
        if dec_match:
            dec_id = dec_match.group(1)
            dmndi_block = f"""
  <dmndi:DMNDI>
    <dmndi:DMNDiagram id="DMNDiagram_{dec_id}">
      <dmndi:DMNShape id="DMNShape_{dec_id}" dmnElementRef="{dec_id}">
        <dc:Bounds height="80" width="180" x="160" y="100" />
      </dmndi:DMNShape>
    </dmndi:DMNDiagram>
  </dmndi:DMNDI>
"""
            content = content.replace(
                '</definitions>',
                f'{dmndi_block}</definitions>',
            )
            changed = True

    return content, changed


def fix_dmn_unique_ids(content: str) -> tuple[str, bool, int]:
    """Prefixa IDs internos com sufixo do decision ID para evitar colisoes em batch deploy.

    Quando multiplos DMN sao deployados juntos, IDs como Input_1, Rule_Fallback,
    InputEntry_F_1 etc. colidem. Solucao: prefixar com identificador unico do arquivo.
    """
    dec_match = re.search(r'<decision\s+id="([^"]*)"', content)
    if not dec_match:
        return content, False, 0

    dec_id = dec_match.group(1)
    suffix = dec_id.replace('Decision_', '').replace('decision_', '')

    # IDs que NAO devem ser renomeados (sao de nivel superior)
    defs_match = re.search(r'<definitions[^>]*\bid="([^"]*)"', content)
    defs_id = defs_match.group(1) if defs_match else ''
    dt_match = re.search(r'<decisionTable[^>]*\bid="([^"]*)"', content)
    dt_id = dt_match.group(1) if dt_match else ''

    preserve_ids = {defs_id, dec_id, dt_id}
    # Preservar dmnElementRef values (referenciam o decision ID que ja e unico)
    for m in re.finditer(r'dmnElementRef="([^"]*)"', content):
        preserve_ids.add(m.group(1))

    # Encontrar TODOS os IDs no arquivo
    all_ids = re.findall(r'\bid="([^"]*)"', content)
    renamed = 0

    for old_id in set(all_ids):
        if old_id in preserve_ids:
            continue
        # Idempotencia: se ja contem o sufixo, skip
        if suffix in old_id:
            continue
        new_id = f'{old_id}_{suffix}'
        content = content.replace(f'"{old_id}"', f'"{new_id}"')
        renamed += 1

    return content, renamed > 0, renamed


def fix_dmn_empty_decision_table(content: str) -> tuple[str, bool, int]:
    """Adiciona input/output/rule minimos em decisionTable sem <input>/<output>.

    Alguns arquivos DMN sao stubs com apenas uma <rule> contendo <description>
    mas sem inputs/outputs. CIB Seven requer ao menos 1 input e 1 output.
    """
    if '<input' in content:
        return content, False, 0

    # Verificar se tem decisionTable sem input
    dt_match = re.search(r'(<decisionTable\b[^>]*>)(.*?)(</decisionTable>)', content, re.DOTALL)
    if not dt_match:
        return content, False, 0

    body = dt_match.group(2)
    if '<input' in body:
        return content, False, 0

    # Extrair description da rule existente (se houver)
    desc = ''
    desc_match = re.search(r'<description>(.*?)</description>', body, re.DOTALL)
    if desc_match:
        desc = desc_match.group(1).strip()

    # Gerar IDs unicos baseados no decision ID
    dec_match = re.search(r'<decision\s+id="([^"]*)"', content)
    prefix = dec_match.group(1) if dec_match else 'stub'

    minimal = f"""
      <input id="Input_{prefix}" label="Trigger">
        <inputExpression id="InputExpr_{prefix}" typeRef="string">
          <text>trigger</text>
        </inputExpression>
      </input>
      <output id="Output_{prefix}" label="Resultado" name="resultado" typeRef="string"/>
      <rule id="Rule_{prefix}">
        <description>{desc}</description>
        <inputEntry id="IE_{prefix}"><text>-</text></inputEntry>
        <outputEntry id="OE_{prefix}"><text>"REVISAR"</text></outputEntry>
      </rule>"""

    # Substituir o body do decisionTable
    new_dt = dt_match.group(1) + minimal + '\n    ' + dt_match.group(3)
    new_content = content[:dt_match.start()] + new_dt + content[dt_match.end():]

    return new_content, True, 1


def fix_dmn_entry_count_mismatch(content: str) -> tuple[str, bool, int]:
    """Corrige regras DMN com numero errado de inputEntry/outputEntry.

    Processa CADA <decisionTable> independentemente para suportar DRDs
    com multiplas tabelas (cada uma com seu proprio numero de inputs/outputs).
    """
    fixed = 0

    def fix_decision_table(dt_match):
        nonlocal fixed
        dt_content = dt_match.group(0)

        num_inputs = len(re.findall(r'<input\b', dt_content))
        num_outputs = len(re.findall(r'<output\b', dt_content))

        if num_inputs == 0 or num_outputs == 0:
            return dt_content

        def fix_rule(m):
            nonlocal fixed
            rule = m.group(0)
            ie_matches = list(re.finditer(r'<inputEntry[^>]*>.*?</inputEntry>', rule, re.DOTALL))
            oe_matches = list(re.finditer(r'<outputEntry[^>]*>.*?</outputEntry>', rule, re.DOTALL))
            ie_count = len(ie_matches)
            oe_count = len(oe_matches)

            if ie_count == num_inputs and oe_count == num_outputs:
                return rule

            new_rule = rule
            rule_changed = False
            dec_match2 = re.search(r'id="([^"]*)"', rule)
            rule_id = dec_match2.group(1) if dec_match2 else 'rule'

            if ie_count > num_inputs:
                for extra in ie_matches[num_inputs:]:
                    new_rule = new_rule.replace(extra.group(0), '', 1)
                rule_changed = True
            elif ie_count < num_inputs:
                first_oe = oe_matches[0] if oe_matches else None
                if first_oe:
                    insert_before = first_oe.group(0)
                    for i in range(num_inputs - ie_count):
                        wildcard = f'<inputEntry id="IE_auto_{rule_id}_{i}"><text>-</text></inputEntry>\n        '
                        new_rule = new_rule.replace(insert_before, wildcard + insert_before, 1)
                rule_changed = True

            if oe_count > num_outputs:
                oe2 = list(re.finditer(r'<outputEntry[^>]*>.*?</outputEntry>', new_rule, re.DOTALL))
                for extra in oe2[num_outputs:]:
                    new_rule = new_rule.replace(extra.group(0), '', 1)
                rule_changed = True
            elif oe_count < num_outputs:
                close_pos = new_rule.rfind('</rule>')
                for i in range(num_outputs - oe_count):
                    empty = f'<outputEntry id="OE_auto_{rule_id}_{i}"><text>""</text></outputEntry>\n        '
                    new_rule = new_rule[:close_pos] + empty + new_rule[close_pos:]
                    close_pos += len(empty)
                rule_changed = True

            if rule_changed:
                new_rule = re.sub(r'\n\s*\n\s*\n', '\n', new_rule)
                fixed += 1
            return new_rule

        return re.sub(r'<rule\b.*?</rule>', fix_rule, dt_content, flags=re.DOTALL)

    content = re.sub(
        r'<decisionTable\b.*?</decisionTable>',
        fix_decision_table,
        content,
        flags=re.DOTALL,
    )
    return content, fixed > 0, fixed


def fix_dmn_duplicate_ids(content: str) -> tuple[str, bool, int]:
    """Desduplicar IDs repetidos dentro de um mesmo arquivo DMN.

    IDs XML devem ser unicos. Quando fix_dmn_unique_ids renomeia IDs genericos
    como '_' para '_suffix', multiplas ocorrencias do mesmo ID original ficam
    com o mesmo novo ID. Este fix adiciona um contador para torna-los unicos.
    """
    all_ids = re.findall(r'\bid="([^"]*)"', content)
    seen = {}
    duplicates = {}
    for id_val in all_ids:
        seen[id_val] = seen.get(id_val, 0) + 1
        if seen[id_val] > 1:
            duplicates[id_val] = seen[id_val]

    if not duplicates:
        return content, False, 0

    fixed = 0
    for dup_id, count in duplicates.items():
        # Renomear cada ocorrencia apos a primeira
        counter = [0]
        def rename_dup(m):
            counter[0] += 1
            if counter[0] == 1:
                return m.group(0)  # Manter a primeira ocorrencia
            new_id = f'{dup_id}_{counter[0]}'
            return m.group(0).replace(f'"{dup_id}"', f'"{new_id}"')

        content = re.sub(
            rf'\bid="{re.escape(dup_id)}"',
            rename_dup,
            content,
        )
        fixed += count - 1

    return content, fixed > 0, fixed


def fix_dmn_files(src_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Corrige todos os DMN files."""
    dmn_files = sorted(src_dir.rglob("*.dmn"))
    fixed = 0
    skipped = 0

    for f in dmn_files:
        try:
            content = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = f.read_text(encoding="latin-1")

        file_changed = False
        details = []

        # Fix 0: normalizar aspas simples para duplas (pre-requisito)
        content, changed = fix_dmn_single_quotes(content)
        if changed:
            file_changed = True
            details.append("quotes")

        # Fix 1: namespaces, TTL, DMNDI, DC namespace
        new_content, changed = fix_dmn_namespaces(content)
        if changed:
            content = new_content
            file_changed = True
            details.append("ns")

        # Fix 2: escapar XML entities em <text> (< e &)
        content, changed, count = fix_dmn_xml_entities(content)
        if changed:
            file_changed = True
            details.append(f"entities:{count}")

        # Fix 3: envolver outputValues/inputValues em <text> se faltando
        content, changed, count = fix_dmn_values_text_wrapper(content)
        if changed:
            file_changed = True
            details.append(f"valuesWrap:{count}")

        # Fix 4: adicionar name= em outputs sem name
        content, changed, count = fix_dmn_output_names(content)
        if changed:
            file_changed = True
            details.append(f"outName:{count}")

        # Fix 5: unique IDs (evitar colisoes em batch deploy)
        content, changed, count = fix_dmn_unique_ids(content)
        if changed:
            file_changed = True
            details.append(f"ids:{count}")

        # Fix 6: preencher decisionTable vazio (sem input/output)
        content, changed, count = fix_dmn_empty_decision_table(content)
        if changed:
            file_changed = True
            details.append(f"emptyDT:{count}")

        # Fix 7: corrigir input/output entry count mismatch
        content, changed, count = fix_dmn_entry_count_mismatch(content)
        if changed:
            file_changed = True
            details.append(f"entryMismatch:{count}")

        # Fix 8: desduplicar IDs repetidos dentro do arquivo
        content, changed, count = fix_dmn_duplicate_ids(content)
        if changed:
            file_changed = True
            details.append(f"dupIds:{count}")

        if file_changed:
            if dry_run:
                warn(f"[DRY-RUN] {f.relative_to(src_dir)} ({', '.join(details)})")
            else:
                f.write_text(content, encoding="utf-8")
                ok(f"{f.relative_to(src_dir)} ({', '.join(details)})")
            fixed += 1
        else:
            skipped += 1

    return fixed, skipped


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Fix BPMN/DMN for CIB Seven deploy")
    parser.add_argument("--dry-run", action="store_true", help="Mostra mudancas sem aplicar")
    parser.add_argument("--bpmn-only", action="store_true")
    parser.add_argument("--dmn-only", action="store_true")
    parser.add_argument("--src-dir", default="src/healthcare_platform",
                        help="Diretorio raiz dos fontes")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    if not src_dir.exists():
        err(f"Diretorio nao encontrado: {src_dir}")
        sys.exit(1)

    if args.dry_run:
        log("Modo DRY-RUN — nenhum arquivo sera modificado")

    do_bpmn = not args.dmn_only
    do_dmn = not args.bpmn_only

    total_fixed = 0

    if do_bpmn:
        log("Corrigindo BPMN (xmlns + TTL + orphans + defaults + serviceTask + timer + order)...")
        fixed, skipped = fix_bpmn_files(src_dir, args.dry_run)
        log(f"BPMN: {fixed} corrigidos, {skipped} ja OK")
        total_fixed += fixed

    if do_dmn:
        log("Corrigindo DMN (xmlns:camunda + namespace + historyTimeToLive + DMNDI)...")
        fixed, skipped = fix_dmn_files(src_dir, args.dry_run)
        log(f"DMN: {fixed} corrigidos, {skipped} ja OK")
        total_fixed += fixed

    print()
    if total_fixed > 0:
        action = "precisam de fix" if args.dry_run else "corrigidos"
        log(f"Total: {total_fixed} arquivos {action}")
    else:
        log("Nenhum arquivo precisou de correcao")


if __name__ == "__main__":
    main()
