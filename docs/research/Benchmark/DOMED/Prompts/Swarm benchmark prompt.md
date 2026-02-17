
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 9 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --use-vectors \
  --use-learning \
  --objective " SWARM O: COLLECTION WORKERS V1.5→V2 | 48 workers | 12 DMN | 2 BPMN | 65% code reduction

MEMORY: collection-workers-refactoring-strategy, phase-3-final-summary, swarm-M-completion
WORKSPACE: /Users/rodrigo/claude-projects/Ochestrator-CIB7-OP/Healthcare-Orchest-CIB7
DURATION: 20-25h | PYTHON: 3.11

PRIMARY DELIVERABLES:
1. 48 collection workers refactored to BaseExternalTaskWorker pattern (avg 70 lines, down from 200)
2. 12 new DMN tables in healthcare_platform/revenue_cycle/dmn/collection_operations/
3. healthcare_platform/revenue_cycle/bpmn/SP-RC-009_Collection_Management.bpmn (expanded)
4. healthcare_platform/revenue_cycle/bpmn/SP-RC-010_Payment_Reconciliation.bpmn (NEW)
5. .swarm/dmn-extraction-report.md
6. .swarm/swarm-O-verification-report.txt
7. .swarm/swarm-O-completion-report.md

━━━ ANTI-PATTERNS TO ELIMINATE (4 categories) ━━━
❌AP1: HARDCODED_RULES (73% workers) → DMN tables
  Signature: WEIGHT=0.4, if score>=80, threshold<1000, rates={}, PERCENTAGE=
❌AP2: EMBEDDED_WORKFLOW (58% workers) → BPMN orchestration  
  Signature: try X→fallback Y, for step in [A,B,C], if fail_retry, sequential_validation
❌AP3: COMPLEX_CONDITIONALS (52% workers) → DMN decision logic
  Signature: if/elif chains, _calculate_*_score(), bracket_logic(amount<1000), nested_conditions
❌AP4: EMBEDDED_DECISION_TABLES (42% workers) → DMN federation
  Signature: type_scores={}, mappings={}, LOOKUP_TABLE={}, priority_map={}

ANTI-PATTERNS TO AVOID (from memory pattern-queen-as-coder-prevention):
❌ Queen coding directly — DELEGATE to specialist agents
❌ Batch updates — each agent works on specific subset
❌ Skip verification — Tier 4 MUST validate all changes
❌ Manual grep commands — use workspace tools and code analysis

━━━ V2 PATTERN (from Swarm M) ━━━
@worker(topic='collection.X')
class XWorker(BaseWorker):
  def __init__(self): super().__init__(); self.dmn_service=FederatedDMNService()
  @property operation_name(self)->str: return _('X')
  async def execute_task(self, task_variables: dict)->dict:
    result = self.dmn_service.evaluate(tenant_id=get_required_tenant(), category='collection_operations', table_name='Y', inputs={...})
    return {...}
TARGET: <80 lines (avg 70), 0 helper methods, 0 constants, 100% DMN-driven

━━━ PHASE O1: DMN EXTRACTION (2 agents, parallel) ━━━
O1A: Workers 1-24 | O1B: Workers 25-48
OUTPUT: .swarm/dmn-extraction-{1-24|25-48}.json
SCAN FOR: AP1 (WEIGHT, thresholds), AP2 (try/fallback), AP3 (if/elif, _calc_), AP4 (dicts)
JSON SCHEMA: {workers_analyzed:int, anti_patterns_found:{AP1:[{worker,line,code,dmn_table}], AP2:[], AP3:[], AP4:[]}, dmn_tables_needed:[{name,inputs,outputs,hit_policy}]}

━━━ PHASE O2: DMN CREATION (1 agent) ━━━
O2: CREATE 12 DMN in healthcare_platform/revenue_cycle/dmn/collection_operations/
1. priority_scoring.dmn | IN: amount,days_overdue,payer_default_rate,claim_type | OUT: priority_score,priority_level | HIT: COLLECT
2. aging_buckets.dmn | IN: days_overdue | OUT: aging_bucket | HIT: FIRST
3. payment_plan_eligibility.dmn | IN: amount_due,payer_history_score,days_overdue | OUT: eligible,plan_tier,max_installments | HIT: FIRST
4. legal_escalation_criteria.dmn | IN: amount_due,days_overdue,collection_attempts,payer_type | OUT: escalate_to_legal,urgency_level,reason_code | HIT: FIRST
5. write_off_thresholds.dmn | IN: amount,days_overdue,collection_cost,recovery_probability | OUT: write_off_approved,reason_code,requires_manager_approval | HIT: FIRST
6. currency_conversion_rules.dmn | IN: source_currency,target_currency,conversion_date | OUT: exchange_rate,rate_source | HIT: FIRST
7. contractual_adjustment_rules.dmn | IN: payer_contract_id,procedure_code,billed_amount | OUT: adjustment_amount,adjustment_reason,final_amount | HIT: COLLECT
8. penalty_calculation.dmn | IN: days_overdue,amount_due,payer_type | OUT: penalty_amount,penalty_rate,penalty_type | HIT: FIRST
9. discrepancy_tolerance.dmn | IN: expected_amount,received_amount,payment_type | OUT: within_tolerance,tolerance_percentage,action,variance | HIT: FIRST
10. collection_strategy.dmn | IN: priority,days_overdue,amount,payer_profile | OUT: strategy,contact_frequency,escalation_path | HIT: FIRST
11. payment_type_classification.dmn | IN: payment_method | OUT: payment_category,processing_days,requires_manual_review | HIT: FIRST
12. overpayment_handling.dmn | IN: overpayment_amount,payer_type,relationship_status | OUT: action,processing_priority,approval_required | HIT: FIRST
VALIDATE: xmllint --noout *.dmn
NAMESPACE: http://healthcare.platform/dmn/collection_operations

━━━ PHASE O3: BPMN ORCHESTRATION (1 agent) ━━━
O3A: EXPAND healthcare_platform/revenue_cycle/bpmn/SP-RC-009_Collection_Management.bpmn
  ADD: 6 service tasks (prioritize_collection, generate_collection_letter, schedule_collection_call, escalate_to_legal, write_off_bad_debt, negotiate_payment_plan)
  ADD: Gateways (priority routing, escalation decision, write-off approval)
  ADD: Timers (retry intervals, escalation timeout), Error boundaries (PAYMENT_NOT_FOUND, LEGAL_ESCALATION_REQUIRED, WRITE_OFF_REJECTED)
  ENSURE: 100% BPMNDI coverage

O3B: CREATE healthcare_platform/revenue_cycle/bpmn/SP-RC-010_Payment_Reconciliation.bpmn
  FLOW: Start→classify_payment_type→[parallel: detect_duplicate + auto_matching]→[gateway: match?]→YES[apply_adjustments→calculate_net→persist]|NO[flag_discrepancies→manual_task]→check_overpayment→reconcile_monthly→End
  SERVICE TASKS: 8 topics (collection.*)
  ERROR BOUNDARIES: DUPLICATE_PAYMENT, OVERPAYMENT_DETECTED, RECONCILIATION_FAILED
  TIMER BOUNDARIES: 24h manual matching, 48h discrepancy review
  ENSURE: 100% BPMNDI coverage

VALIDATE: xmllint --noout SP-RC-*.bpmn

━━━ PHASE O4: V2 MIGRATION (4 agents, parallel - IMPROVED SPLIT) ━━━
COMMON CONTEXT (ALL AGENTS):
  BASE: from healthcare_platform.revenue_cycle.collection.workers.base import BaseWorker, worker
  DMN: from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
  TENANT: from healthcare_platform.shared.multi_tenant.context import get_required_tenant
  I18N: from healthcare_platform.shared.i18n import _
  LOG: from healthcare_platform.shared.observability.logging import get_logger
  
  TRANSFORMATION STEPS:
  1. class XWorker: → class XWorker(BaseWorker):
  2. TOPIC='collection.X' → @worker(topic='collection.X')
  3. __init__: add super().__init__()
  4. Add @property operation_name()->str: return _('...')
  5. execute() → execute_task()
  6. DELETE: AP1 constants, AP3 helper methods, AP4 dicts
  7. REPLACE logic with: dmn_service.evaluate(tenant_id=get_required_tenant(), category='collection_operations', table_name='X', inputs={...})
  8. TARGET: <80 lines

O4A: Workers 1-12 (alert_anomalies→classify_payment_type)
O4B: Workers 13-24 (convert_currency→match_by_invoice)
O4C: Workers 25-36 (match_by_protocol→write_off_bad_debt)
O4D: Workers 37-48 (calculate_write_off_threshold→calculate_interest)

PER WORKER:
  READ: .swarm/dmn-extraction-*.json for anti-pattern locations
  APPLY: 8-step transformation
  MAP TO DMN: Use extraction report table_name mapping
  VALIDATE: python3.11 -m py_compile {file}
  CHECK: wc -l {file} → <80

━━━ PHASE O5: VERIFICATION (1 agent) ━━━
O5: OUTPUT .swarm/swarm-O-verification-report.txt

V1: PATTERN | grep -l 'BaseWorker' */workers/*_worker.py | wc -l → 48 | grep -l '@worker' */workers/*_worker.py | wc -l → 48 | grep -c 'TOPIC = ' */workers/*_worker.py → 0
V2: ANTI-PATTERNS | grep -r 'WEIGHT = ' */workers/ → 0 | grep -r 'def _calculate_' */workers/ → 0 | grep -r '= {.*:.*}' */workers/ → minimal
V3: SIZE | wc -l */workers/*_worker.py | tail -1 | awk '{print \$1/48}' → <80
V4: IMPORTS | python -c 'from healthcare_platform.revenue_cycle.collection import *' → exit 0 | grep -c FederatedDMNService */workers/*_worker.py → 48
V5: SYNTAX | find */workers -name '*_worker.py' -exec python3.11 -m py_compile {} \\; 2>&1 → 0 errors
V6: DMN | find dmn/collection_operations -name '*.dmn' | wc -l → 12 | for f in dmn/collection_operations/*.dmn; do xmllint --noout \$f; done → 0 errors
V7: BPMN | xmllint --noout bpmn/SP-RC-009*.bpmn → 0 | xmllint --noout bpmn/SP-RC-010*.bpmn → 0 | grep -c 'camunda:topic=\"collection\\.' bpmn/SP-RC-*.bpmn → >14
V8: TESTS | pytest tests/revenue_cycle/collection/ --collect-only 2>&1 | grep -c 'ModuleNotFoundError' → 0
V9: EXECUTION (EXIT CRITERIA) | pytest tests/revenue_cycle/collection/ -v --tb=short → PASS_RATE >95%
V10: SCOPE | git diff healthcare_platform/revenue_cycle/{billing,glosa,coding,production} → 0 changes

━━━ EXIT CRITERIA (13 checks) ━━━
✅ 48 workers: BaseWorker + @worker + execute_task + operation_name
✅ 0 anti-patterns: AP1(0 WEIGHT) + AP2(0 try/fallback) + AP3(0 _calc_) + AP4(0 dicts)
✅ <80 lines avg (target 70, 65% reduction from 200)
✅ 12 DMN files valid XML in collection_operations/
✅ 2 BPMN files: SP-RC-009 expanded + SP-RC-010 new, 100% BPMNDI
✅ 0 import errors (python -c test)
✅ 0 syntax errors (py_compile)
✅ 48 FederatedDMNService calls
✅ 48 get_required_tenant calls
✅ >95% test pass rate (CRITICAL)
✅ ~150+ tests collected
✅ No scope creep (billing/glosa/coding/production unchanged)
✅ All verification commands PASS

ROLLBACK (if pass_rate <90%): git stash → git restore collection/ dmn/collection_operations/ bpmn/SP-RC-*.bpmn → .swarm/swarm-O-rollback-report.md → memory:swarm-O-failure

DELIVERABLES: 48 workers refactored, 12 DMN files, 2 BPMN files, dmn-extraction-report.md, verification-report.txt, completion-report.md"
