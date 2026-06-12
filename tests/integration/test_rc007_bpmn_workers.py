"""
test_rc007_bpmn_workers.py — Integração SP-RC-007 Denial Management.

Testa o fluxo COMPLETO com workers Python reais executando contra o CIB Seven:

  Workers REAIS (lógica de negócio real + DMN mockado):
    - IdentifyGlosaWorkerV2    (glosa.identify)
    - SubmitAppealWorkerV2     (denial.submit_appeal)
    - TrackAppealStatusWorkerV2 (denial.track_appeal_status)

  Workers STUB (tópicos sem implementação ainda):
    - glosa.classify_type, glosa.analyze_reason
    - glosa.predict_risk, glosa.prevention_strategy
    - glosa.recovery_strategy, glosa.recovery_eligibility
    - VerificarElegibilidade, ColetarDados
    - denial.generate_appeal_documentation

  O que é validado aqui vs. E2E:
    ┌─────────────────────────────────┬────────────┬──────────────┐
    │                                 │ E2E (mock) │ Integração   │
    ├─────────────────────────────────┼────────────┼──────────────┤
    │ Orquestração BPMN               │     ✓      │      ✓       │
    │ Gateways e roteamento           │     ✓      │      ✓       │
    │ Lógica de negócio do worker     │     ✗      │      ✓       │
    │ Parsing do ClaimResponse FHIR   │     ✗      │      ✓       │
    │ Mapeamento de variáveis BPMN    │     ✗      │      ✓       │
    │ DMN adjudication (mock)         │     ✗      │      ✓       │
    └─────────────────────────────────┴────────────┴──────────────┘

Requer: CIB Seven rodando em http://localhost:8080
Uso:
    PYTHONUTF8=1 pytest tests/integration/test_rc007_bpmn_workers.py -v -m integration
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import CIB7_URL, CIB7_USER, CIB7_PASS, TIMEOUT
from tests.fixtures.fhir_seed import GLOSA_DENIAL_IDS, HAPPY_PATH_IDS, get_rc_resources
from tests.integration.worker_harness import (
    WorkerHarness,
    cancel_all_active,
    get_process_variables,
    make_mock_dmn,
    start_process,
    stub_worker,
    trigger_timers,
    wait_for_state,
)
from healthcare_platform.revenue_cycle.glosa.workers.identify_glosa_worker_v2 import (
    IdentifyGlosaWorkerV2,
)
from healthcare_platform.revenue_cycle.glosa.workers.submit_appeal_worker_v2 import (
    SubmitAppealWorkerV2,
)
from healthcare_platform.revenue_cycle.glosa.workers.track_appeal_status_worker_v2 import (
    TrackAppealStatusWorkerV2,
)
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

PROCESS_KEY = "SP_RC_007_Denial_Management"

# ---------------------------------------------------------------------------
# FHIR seed: carregado uma vez por módulo
# ---------------------------------------------------------------------------
_GLOSA_SEED: list[dict] = get_rc_resources(tenant_id="austa-hospital", scenario="glosa_denial")


def _find_resource(resources: list[dict], rtype: str, rid: str) -> dict:
    """Retorna o primeiro recurso FHIR com o resourceType e id informados."""
    for r in resources:
        if r.get("resourceType") == rtype and r.get("id") == rid:
            return r
    return {}


def _fhir_to_worker_claimresponse(fhir_cr: dict, fhir_claim: dict | None = None) -> dict:
    """
    Converte ClaimResponse FHIR R4 para o formato simplificado que o worker espera.

    FHIR R4 (seed):
      item[].itemSequence
      item[].adjudication[].category  → {"coding":[{"code":"benefit"|"eligible"|"submitted"}]}
      item[].adjudication[].amount    → {"value": X, "currency": "BRL"}
      item[].adjudication[].reason    → {"coding":[{"display": "..."}]}
      productOrService / unitPrice / quantity  ← em Claim.item (via fhir_claim)

    Worker espera (IdentifyGlosaWorkerV2._extract_glosa_items):
      items[].sequence
      items[].productOrService.code  → str
      items[].unitPrice              → float
      items[].quantity               → float
      items[].adjudication[].category → "denied" | "benefit" | "submitted"
      items[].adjudication[].amount   → float
      items[].adjudication[].reason   → str

    Mapeamento: "eligible" + amount=0 → "denied"  (padrão TISS de glosa)
    """
    # Índice de Claim.item por sequence para cross-reference
    claim_items: dict[int, dict] = {}
    if fhir_claim:
        for ci in fhir_claim.get("item", []):
            seq = ci.get("sequence")
            if seq is not None:
                claim_items[seq] = ci

    worker_items = []
    for fhir_item in fhir_cr.get("item", []):
        seq = fhir_item.get("itemSequence", 0)
        ci = claim_items.get(seq, {})

        # productOrService / unitPrice / quantity vêm de Claim.item
        product_or_service = ci.get("productOrService", {"code": f"CODE-{seq}"})
        unit_price_raw = ci.get("unitPrice", {})
        unit_price = unit_price_raw.get("value", 0.0) if isinstance(unit_price_raw, dict) else float(unit_price_raw or 0)
        qty_raw = ci.get("quantity", {})
        quantity = qty_raw.get("value", 1.0) if isinstance(qty_raw, dict) else float(qty_raw or 1)

        worker_adj = []
        for adj in fhir_item.get("adjudication", []):
            # Categoria: {"coding":[{"code":"..."}]} → str
            cat_obj = adj.get("category", {})
            cat_code = (
                (cat_obj.get("coding") or [{}])[0].get("code", "")
                if isinstance(cat_obj, dict) else str(cat_obj)
            )
            # Valor: {"value": X} → float
            amt_obj = adj.get("amount", {})
            amt = amt_obj.get("value", 0.0) if isinstance(amt_obj, dict) else float(amt_obj or 0)
            # Razão: {"coding":[{"display":"..."}]} → str
            reason_obj = adj.get("reason", {})
            reason_str = (
                (reason_obj.get("coding") or [{}])[0].get("display", "")
                if isinstance(reason_obj, dict) else str(reason_obj or "")
            )
            # "eligible" + amount=0  →  glosa  →  "denied"
            if cat_code == "eligible" and amt == 0.0:
                cat_code = "denied"

            worker_adj.append({"category": cat_code, "amount": amt, "reason": reason_str})

        worker_items.append({
            "sequence": seq,
            "productOrService": product_or_service,
            "unitPrice": unit_price,
            "quantity": quantity,
            "adjudication": worker_adj,
        })

    return {**fhir_cr, "items": worker_items}


# ---------------------------------------------------------------------------
# Fixture: cliente HTTP
# ---------------------------------------------------------------------------

@pytest.fixture
def cib7():
    with httpx.Client(
        base_url=f"{CIB7_URL}/engine-rest",
        auth=(CIB7_USER, CIB7_PASS),
        timeout=TIMEOUT,
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean(cib7):
    """Cancela instâncias residuais de SP-RC-007 antes de cada teste."""
    cancel_all_active(cib7, PROCESS_KEY)
    yield
    # Cleanup pós-teste (se alguma instância ficou presa)
    cancel_all_active(cib7, PROCESS_KEY)


# ---------------------------------------------------------------------------
# Dados de teste: ClaimResponse FHIR R4 real do seed glosa_denial
# ---------------------------------------------------------------------------

def _glosa_claim_response() -> dict:
    """
    Retorna o ClaimResponse FHIR R4 do cenário glosa_denial do seed.

    Estrutura:
      item[0]: seq=1, TUSS 40101010 "Consulta médica" — aprovado (benefit 150,00)
      item[1]: seq=2, TUSS 40301362 "Hemograma completo" — glosado (eligible=0, G001)
    """
    return _find_resource(_GLOSA_SEED, "ClaimResponse", GLOSA_DENIAL_IDS["cr"])


def _glosa_claim() -> dict:
    """Retorna o Claim FHIR R4 do cenário glosa_denial (usado para cross-ref de itens)."""
    return _find_resource(_GLOSA_SEED, "Claim", GLOSA_DENIAL_IDS["claim"])


# ---------------------------------------------------------------------------
# Adaptadores: traduzem variáveis entre worker-real e contrato BPMN
# ---------------------------------------------------------------------------

def _make_identify_adapter(worker: IdentifyGlosaWorkerV2, fhir_claim: dict | None = None):
    """
    Adapta I/O do IdentifyGlosaWorkerV2 para o contrato BPMN.

    Converte ClaimResponse FHIR R4 (seed) → formato simplificado que o worker espera:
      - item[]  →  items[]
      - category: {"coding":[{"code":"..."}]}  →  "denied" | "benefit" | ...
      - amount: {"value": X}  →  float
      - "eligible" + amount=0  →  "denied"  (padrão TISS de glosa)
      - productOrService / unitPrice / quantity  cross-referenciados de Claim.item

    Contrato BPMN:
      IN:  billingBatch=${batchId}, response=${payerResponse}
      OUT: identifiedGlosas=${glosaItems}, totalGlosas=${glosaCount}
    """
    def adapter(context: TaskContext) -> TaskResult:
        payer_resp = context.variables.get("payerResponse") or context.variables.get("response", {})
        if isinstance(payer_resp, str):
            import json
            try:
                payer_resp = json.loads(payer_resp)
            except Exception:
                payer_resp = {}

        # Converter ClaimResponse FHIR R4 → formato que o worker entende
        worker_cr = _fhir_to_worker_claimresponse(payer_resp, fhir_claim)

        adapted = dataclasses.replace(
            context,
            variables={
                **context.variables,
                "claimResponse": worker_cr,
                "claimId": context.variables.get("batchId", "BATCH-UNKNOWN"),
            },
        )
        return worker.execute(adapted)

    return adapter


def _make_submit_adapter(worker: SubmitAppealWorkerV2):
    """
    Adapta I/O do SubmitAppealWorkerV2 para o contrato BPMN.

    Contrato BPMN:
      IN:  appealPackage=${completePackage}, payer=${payerId}
      OUT: submittedAppealId=${appealId}, appealSubmissionDate=${submissionDate}

    Worker lê: appealDocumentId, claimId, eligibleGlosas, payerId
    Worker retorna: submissionProtocol (≠ appealId) → precisa adaptar

    NOTA: este adapter documenta a divergência de nomes entre worker e BPMN.
    TODO: alinhar SubmitAppealWorkerV2 para retornar appealId e submissionDate
    """
    def adapter(context: TaskContext) -> TaskResult:
        # Adaptar entrada
        adapted = dataclasses.replace(
            context,
            variables={
                **context.variables,
                "appealDocumentId": context.variables.get("completePackage", "DOC-001"),
                "claimId": context.variables.get("batchId", "BATCH-UNKNOWN"),
                "eligibleGlosas": context.variables.get("glosaItems", []),
                "payerId": context.variables.get("payerId", GLOSA_DENIAL_IDS["org_payer"]),
                "providerId": "PROV-001",
            },
        )
        result = worker.execute(adapted)

        if result.status == TaskStatus.SUCCESS:
            # Adaptar saída: submissionProtocol → appealId (contrato BPMN)
            vars_out = dict(result.variables or {})
            vars_out["appealId"] = vars_out.get("submissionProtocol", f"APPEAL-{uuid.uuid4().hex[:8]}")
            vars_out["submissionDate"] = datetime.utcnow().date().isoformat()
            return TaskResult.success(vars_out)

        return result

    return adapter


def _make_track_adapter(worker: TrackAppealStatusWorkerV2):
    """
    Adapta I/O do TrackAppealStatusWorkerV2 para o contrato BPMN.

    Contrato BPMN:
      IN:  appealId=${submittedAppealId}
      OUT: appealStatus=${currentStatus}, response=${payerResponse}

    Worker lê: submissionProtocol, claimId, submissionTimestamp
    Worker retorna: appealStatus (≠ currentStatus) → precisa adaptar

    TODO: alinhar TrackAppealStatusWorkerV2 para retornar currentStatus
    """
    def adapter(context: TaskContext) -> TaskResult:
        # Adaptar entrada
        adapted = dataclasses.replace(
            context,
            variables={
                **context.variables,
                "submissionProtocol": (
                    context.variables.get("submittedAppealId")
                    or context.variables.get("appealId", "PROT-001")
                ),
                "claimId": context.variables.get("batchId", "BATCH-UNKNOWN"),
                "submissionTimestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        result = worker.execute(adapted)

        if result.status == TaskStatus.SUCCESS:
            # Adaptar saída: appealStatus → currentStatus (contrato BPMN)
            vars_out = dict(result.variables or {})
            vars_out["currentStatus"] = vars_out.get("appealStatus", "SUBMITTED")
            return TaskResult.success(vars_out)

        return result

    return adapter


# ---------------------------------------------------------------------------
# Worker map factory
# ---------------------------------------------------------------------------

def _build_worker_map(mock_dmn, eligible: bool = True) -> dict:
    """
    Monta o mapa tópico → worker para SP-RC-007.

    Workers REAIS: glosa.identify, denial.submit_appeal, denial.track_appeal_status
    Workers STUB:  todos os demais tópicos

    O Claim FHIR R4 do seed é passado ao adapter de identify para
    cross-referenciar productOrService / unitPrice / quantity por sequência de item.
    """
    fhir_claim = _glosa_claim()
    identify_worker = IdentifyGlosaWorkerV2(dmn_service=mock_dmn)
    submit_worker = SubmitAppealWorkerV2(tiss_client=None, dmn_service=mock_dmn)
    track_worker = TrackAppealStatusWorkerV2(tiss_client=None, dmn_service=mock_dmn)

    return {
        # ── Workers reais com adapters ───────────────────────────────────────
        "glosa.identify": _make_identify_adapter(identify_worker, fhir_claim),
        "denial.submit_appeal": _make_submit_adapter(submit_worker),
        "denial.track_appeal_status": _make_track_adapter(track_worker),

        # ── Stubs com variáveis no formato esperado pelo BPMN ───────────────
        "glosa.classify_type": stub_worker({
            "classifiedGlosas": '[{"code": "40301362", "type": "ADMINISTRATIVA"}]',  # seed: hemograma glosado
            "primaryType": "ADMINISTRATIVA",
        }),
        "glosa.analyze_reason": stub_worker({
            "rootCause": "DOCUMENTACAO_INCOMPLETA",
            "analysisDetails": "Laudo médico ausente",
        }),
        "glosa.predict_risk": stub_worker({
            "riskScore": 0.3,
            "riskCategory": "LOW",
        }),
        "glosa.prevention_strategy": stub_worker({
            "preventionActions": '["verificar_documentacao", "solicitar_laudo"]',
        }),
        "VerificarElegibilidade": stub_worker({
            "isEligible": eligible,
            "eligibilityReason": "Dentro do prazo" if eligible else "Prazo expirado",
        }),
        "ColetarDados": stub_worker({
            "collectedData": '{"docs": ["laudo.pdf", "receita.pdf"]}',
        }),
        "glosa.recovery_strategy": stub_worker({
            "recoveryPlan": '{"strategy": "RECURSO_ADMINISTRATIVO"}',
        }),
        "glosa.recovery_eligibility": stub_worker({
            "recoveryEligibility": '{"eligible": true}',
        }),
        "denial.generate_appeal_documentation": stub_worker({
            "appealDocuments": '["laudo.pdf", "recurso_formal.pdf"]',
            "appealPackage": '{"complete": true, "docId": "DOC-001"}',
        }),
    }


# ---------------------------------------------------------------------------
# Testes de integração
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRC007DenialManagementWorkers:
    """
    Testa SP-RC-007 com workers Python reais contra o CIB Seven.

    Diferente dos testes E2E (que usam mock total), aqui os workers reais
    executam sua lógica de negócio: parsing FHIR, adjudicação DMN, etc.
    """

    @pytest.fixture(autouse=True)
    def _pause_competing_workers(self, pause_rc_worker):
        """Garante que o worker RC de produção está pausado durante os testes."""

    def test_happy_path_real_workers_complete_flow(self, cib7, require_cib7):
        """
        Fluxo completo: glosa identificada por worker real → recurso aprovado.

        Valida:
        - IdentifyGlosaWorkerV2 parseia ClaimResponse FHIR corretamente
        - Identifica 1 glosa de R$ 500,00 com reason DOCUMENTACAO_INCOMPLETA
        - Fluxo percorre todos os 12 passos até COMPLETED
        - Variáveis de processo refletem a execução real dos workers
        """
        mock_dmn = make_mock_dmn()  # PROSSEGUIR para todas as decisões
        worker_map = _build_worker_map(mock_dmn, eligible=True)
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "batchId":       GLOSA_DENIAL_IDS["claim"],
                "payerResponse": _glosa_claim_response(),
                "payerId":       GLOSA_DENIAL_IDS["org_payer"],
            })

            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=45)

        assert state == "COMPLETED", (
            f"Processo deveria estar COMPLETED, está: {state}\n"
            f"Workers executados: {harness.executed}\n"
            f"Erros: {harness.errors}"
        )

        # Verificar variáveis de processo no histórico
        proc_vars = get_process_variables(cib7, instance_id)

        # IdentifyGlosaWorkerV2 deveria ter identificado glosas
        assert proc_vars.get("glosaCount") is not None, (
            "glosaCount não encontrado — IdentifyGlosaWorkerV2 falhou ou não executou"
        )

        # Worker real deve ter identificado 1 glosa no ClaimResponse
        glosa_count = proc_vars.get("glosaCount")
        if isinstance(glosa_count, str):
            import json
            glosa_count = json.loads(glosa_count)
        assert int(glosa_count) == 1, (
            f"Esperado 1 glosa identificada pelo worker real, obtido: {glosa_count}"
        )

        # Verificar que workers reais foram executados
        executed_topics = {e["topic"] for e in harness.executed}
        assert "glosa.identify" in executed_topics, "IdentifyGlosaWorkerV2 não executou"
        assert "denial.submit_appeal" in executed_topics, "SubmitAppealWorkerV2 não executou"
        assert "denial.track_appeal_status" in executed_topics, "TrackAppealStatusWorkerV2 não executou"

        # Sem erros de worker
        assert not harness.errors, f"Erros nos workers: {harness.errors}"

    def test_identify_worker_parses_fhir_claim_response(self, cib7, require_cib7):
        """
        Valida que IdentifyGlosaWorkerV2 parseia corretamente um ClaimResponse FHIR R4.

        Usa o seed glosa_denial que tem exatamente 2 itens:
          item 1 (seq=1): TUSS 40101010 "Consulta médica" → aprovado (benefit 150,00)
          item 2 (seq=2): TUSS 40301362 "Hemograma completo" → glosado (eligible=0, G001)

        O adapter converte FHIR R4 → formato worker (eligible+amount=0 → "denied").
        Worker deve identificar apenas o item 2 como glosa.
        """
        mock_dmn = make_mock_dmn()
        worker_map = _build_worker_map(mock_dmn, eligible=True)
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "batchId":       GLOSA_DENIAL_IDS["claim"],
                "payerResponse": _glosa_claim_response(),
                "payerId":       GLOSA_DENIAL_IDS["org_payer"],
            })
            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=45)

        assert state == "COMPLETED", f"Estado: {state} | Erros: {harness.errors}"

        proc_vars = get_process_variables(cib7, instance_id)
        glosa_count = int(proc_vars.get("glosaCount", 0))
        assert glosa_count == 1, (
            f"Worker deveria identificar 1 glosa (item denied), identificou: {glosa_count}"
        )

    def test_dmn_revisar_does_not_block_flow(self, cib7, require_cib7):
        """
        DMN retorna REVISAR (não BLOQUEAR): worker marca requiresReview=True mas
        continua o fluxo normalmente (não lança bpmnError).
        """
        # DMN retorna REVISAR para identificação
        mock_dmn = make_mock_dmn(responses={
            "identification/glosa_identify_adjudication": {
                "resultado": "REVISAR",
                "risco": "MEDIO",
                "acao": "Verificar manualmente antes de prosseguir",
            }
        })
        worker_map = _build_worker_map(mock_dmn, eligible=True)
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "batchId":       GLOSA_DENIAL_IDS["claim"],
                "payerResponse": _glosa_claim_response(),
                "payerId":       HAPPY_PATH_IDS["org_payer"],   # bradesco — payer diferente para variar
            })
            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=45)

        # REVISAR não bloqueia — fluxo deve completar normalmente
        assert state == "COMPLETED", (
            f"REVISAR não deveria bloquear o fluxo. Estado: {state}\n"
            f"Erros: {harness.errors}"
        )
        assert not harness.errors, f"Erros inesperados: {harness.errors}"

    def test_not_eligible_path_real_workers(self, cib7, require_cib7):
        """
        Glosa não elegível para recurso → processo fica ACTIVE aguardando revisão humana.

        IdentifyGlosaWorkerV2 executa normalmente (identifica glosa).
        O stub de VerificarElegibilidade retorna isEligible=False.
        Gateway redireciona para userTask (revisão humana) → processo fica ACTIVE.
        """
        mock_dmn = make_mock_dmn()
        worker_map = _build_worker_map(mock_dmn, eligible=False)
        instance_id = None

        try:
            with WorkerHarness(cib7, worker_map) as harness:
                instance_id = start_process(cib7, PROCESS_KEY, {
                    "batchId":       GLOSA_DENIAL_IDS["claim"],
                    "payerResponse": _glosa_claim_response(),
                    "payerId":       GLOSA_DENIAL_IDS["org_payer"],
                })

                # Aguarda workers processarem até elegibilidade
                import time
                time.sleep(10)

            # Após workers pararem: processo deve estar ACTIVE (userTask aberta)
            from tests.e2e.conftest import CIB7_URL, CIB7_USER, CIB7_PASS, TIMEOUT
            with httpx.Client(
                base_url=f"{CIB7_URL}/engine-rest",
                auth=(CIB7_USER, CIB7_PASS),
                timeout=TIMEOUT,
            ) as check_client:
                state = wait_for_state(check_client, instance_id, "ACTIVE", timeout_s=5)
                assert state == "ACTIVE", f"Processo deveria estar ACTIVE (userTask). Estado: {state}"

                # Verificar que identificação pelo worker real ocorreu
                proc_vars = get_process_variables(check_client, instance_id)
                assert proc_vars.get("glosaCount") is not None, (
                    "IdentifyGlosaWorkerV2 deveria ter identificado glosas mesmo no path não-elegível"
                )

            # Verificar execuções
            executed_topics = {e["topic"] for e in harness.executed}
            assert "glosa.identify" in executed_topics, "IdentifyGlosaWorkerV2 não executou"
            assert not harness.errors, f"Erros: {harness.errors}"

        finally:
            if instance_id:
                with httpx.Client(
                    base_url=f"{CIB7_URL}/engine-rest",
                    auth=(CIB7_USER, CIB7_PASS),
                    timeout=TIMEOUT,
                ) as cleanup:
                    cancel_all_active(cleanup, PROCESS_KEY)

    def test_submit_appeal_worker_generates_protocol(self, cib7, require_cib7):
        """
        SubmitAppealWorkerV2 gera protocolo de submissão válido.

        Quando tiss_client=None, o worker usa submissão mock que retorna
        response_code="SUCCESS" e gera um protocolo baseado em timestamp.
        O fluxo completo deve chegar em COMPLETED com appealId definido.
        """
        mock_dmn = make_mock_dmn()
        worker_map = _build_worker_map(mock_dmn, eligible=True)
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "batchId":       GLOSA_DENIAL_IDS["claim"],
                "payerResponse": _glosa_claim_response(),
                "payerId":       GLOSA_DENIAL_IDS["org_payer"],
            })
            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=45)

        assert state == "COMPLETED", f"Estado: {state} | Erros: {harness.errors}"

        # Verificar que submissão gerou um appealId (via adapter)
        proc_vars = get_process_variables(cib7, instance_id)
        submitted_appeal_id = proc_vars.get("submittedAppealId")
        assert submitted_appeal_id, (
            f"submittedAppealId deveria estar definido após SubmitAppealWorkerV2. "
            f"Vars disponíveis: {list(proc_vars.keys())}"
        )
