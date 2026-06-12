"""
test_rc003_bpmn_workers.py — Integração SP-RC-003 Atendimento Clínico.

Testa o fluxo SP_RC_003_Clinical_Service com workers Python reais contra o CIB Seven.

  Workers externos (exigem worker real ou stub):
    - revenue_cycle.enrich_procedure  → retorna enrichedData, diagnosisCodes, procedureCodes
    - NotificarPendenciaTasy           → stub (notifica pendências no loop de retry)

  Todos os outros tasks são bpmn:task (auto-complete):
    - task_capture_procedure    (captura dados — auto)
    - task_calculate_quantity   (calcula quantidades — auto)
    - task_validate_data        (valida dados clínicos — auto)
    - task_manual_capture       (captura manual — auto)
    - task_escalate_capture     (escala captura — auto)

  Gateways:
    - gateway_completeness: ${completeData == null} → incompleto (default: completo)
    - gateway_validation:   ${dataValidated == false} → inválido (default: válido)

Requer: CIB Seven rodando em http://localhost:8080
"""
from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import CIB7_URL, CIB7_USER, CIB7_PASS
from tests.fixtures.fhir_seed import HAPPY_PATH_IDS
from tests.integration.worker_harness import (
    WorkerHarness,
    cancel_all_active,
    get_process_variables,
    start_process,
    stub_worker,
    trigger_timers,
    wait_for_state,
)

PROCESS_KEY = "SP_RC_003_Clinical_Service"
TIMEOUT = 30.0


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
    cancel_all_active(cib7, PROCESS_KEY)
    yield
    cancel_all_active(cib7, PROCESS_KEY)


# ---------------------------------------------------------------------------
# Worker map factory
# ---------------------------------------------------------------------------

def _build_worker_map(enriched_data: str | None = "dados_enriquecidos_ok") -> dict:
    """
    Monta worker map para SP-RC-003 (versão simplificada).

    Workers externos remanescentes:
      - revenue_cycle.enrich_procedure  → retorna enrichedData, diagnosisCodes, procedureCodes
      - NotificarPendenciaTasy           → stub (notifica pendência, aciona timer PT24H)

    enriched_data=None simula falha de enriquecimento (documentação incompleta).
    """
    enrich_vars = {
        "enrichedData":    enriched_data,   # → completeData via outputParameter
        "diagnosisCodes":  "K80.2",          # → icdCodes
        "procedureCodes":  "40101010",       # → tussCodes
    }
    if enriched_data is None:
        # Retorna enrichedData=null → completeData=null → gateway_completeness toma flow_doc_incomplete
        enrich_vars["enrichedData"] = None

    return {
        "revenue_cycle.enrich_procedure": stub_worker(enrich_vars),
        "NotificarPendenciaTasy":          stub_worker({"notified": True}),
    }


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRC003ClinicalServiceWorkers:
    """
    Integração SP-RC-003.

    Workers externos: enrich_procedure (stub), NotificarPendenciaTasy (stub).
    Todos os outros tasks auto-completam (bpmn:task).
    """

    @pytest.fixture(autouse=True)
    def _pause_competing_workers(self, pause_rc_worker):
        """Garante que o worker RC de produção está pausado durante os testes."""

    def test_happy_path_enrich_complete(self, cib7, require_cib7):
        """
        Happy path: enrich retorna enrichedData não-nulo
        → completeData != null → gateway_completeness toma default (doc_complete)
        → calculate (auto) → validate (auto, dataValidated=null) → gateway_validation toma default (valid)
        → end_success → COMPLETED.
        """
        worker_map = _build_worker_map(enriched_data="dados_enriquecidos_ok")
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "patientId":   HAPPY_PATH_IDS["patient"],
                "encounterId": HAPPY_PATH_IDS["encounter"],
                # Variáveis-fonte para output parameters das bpmn:task (auto-complete):
                "capturedData":      "{}",           # task_capture_procedure → clinicalData
                "captureTimestamp":  "2026-03-18T10:00:00Z",  # task_capture_procedure → timestamp
                "quantities":        "1",             # task_calculate_quantity → procedureQuantities
                "units":             "UN",            # task_calculate_quantity → measurementUnits
                "validationResult":  True,            # task_validate_data → dataValidated
                "validationErrors":  "",              # task_validate_data → errors
            })
            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)

        assert state == "COMPLETED", (
            f"Estado: {state}\n"
            f"Workers executados: {[e['topic'] for e in harness.executed]}\n"
            f"Erros: {harness.errors}"
        )

        executed_topics = {e["topic"] for e in harness.executed}
        assert "revenue_cycle.enrich_procedure" in executed_topics
        assert not harness.errors, f"Erros: {harness.errors}"

    def test_enrich_returns_null_triggers_incomplete_loop(self, cib7, require_cib7):
        """
        Enriquecimento retorna enrichedData=null → completeData=null
        → gateway_completeness toma flow_doc_incomplete
        → NotificarPendenciaTasy → timer PT24H → re-enrich → COMPLETED.

        Usa chamadas REST diretas ao CIB Seven para controle preciso do fluxo,
        evitando problemas de timing com WorkerHarness em dois ciclos.
        """
        import time

        WORKER_ID = "test-loop-direct-worker"

        def _fetch_and_complete(topic: str, variables: dict, timeout_s: float = 15.0) -> bool:
            """Busca a primeira task do tópico para esta instância e completa com as variáveis."""
            cam_vars = {}
            for k, v in variables.items():
                if v is None:
                    cam_vars[k] = {"value": None, "type": "String"}
                elif isinstance(v, bool):
                    cam_vars[k] = {"value": v, "type": "Boolean"}
                elif isinstance(v, float):
                    cam_vars[k] = {"value": v, "type": "Double"}
                else:
                    cam_vars[k] = {"value": str(v), "type": "String"}

            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                r = cib7.post("/external-task/fetchAndLock", json={
                    "workerId": WORKER_ID,
                    "maxTasks": 5,
                    "usePriority": False,
                    "topics": [{
                        "topicName":            topic,
                        "lockDuration":         10_000,
                        "processInstanceIdIn":  [instance_id],
                    }],
                })
                tasks = r.json() if r.status_code == 200 else []
                if tasks:
                    task_id = tasks[0]["id"]
                    cib7.post(
                        f"/external-task/{task_id}/complete",
                        json={"workerId": WORKER_ID, "variables": cam_vars},
                    )
                    return True
                time.sleep(0.5)
            return False

        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":        HAPPY_PATH_IDS["patient"],
            "encounterId":      HAPPY_PATH_IDS["encounter"],
            "capturedData":     "{}",
            "captureTimestamp": "2026-03-18T10:00:00Z",
            "quantities":       "1",
            "units":            "UN",
            "validationResult": True,
            "validationErrors": "",
        })

        # Rodada 1: enrich retorna null → documentação incompleta
        ok = _fetch_and_complete("revenue_cycle.enrich_procedure", {
            "enrichedData":   None,
            "diagnosisCodes": None,
            "procedureCodes": None,
        })
        assert ok, "Enrich task (1ª rodada) não encontrado em 15s"

        # NotificarPendenciaTasy
        ok = _fetch_and_complete("NotificarPendenciaTasy", {"notified": True})
        assert ok, "NotificarPendenciaTasy task não encontrado em 15s"

        # Disparar timer PT24H
        time.sleep(1)
        triggered = trigger_timers(cib7, instance_id, wait_s=10)
        assert triggered > 0, "Nenhum timer PT24H disparado"

        # Rodada 2: enrich retorna dados completos → processo deve completar
        ok = _fetch_and_complete("revenue_cycle.enrich_procedure", {
            "enrichedData":   "dados_enriquecidos_ok",
            "diagnosisCodes": "K80.2",
            "procedureCodes": "40101010",
        })
        assert ok, "Enrich task (2ª rodada) não encontrado em 15s"

        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=30)
        assert state == "COMPLETED", f"Estado inesperado após loop de retry: {state}"

    def test_enrich_worker_executes_with_fhir_ids(self, cib7, require_cib7):
        """
        Verifica que o worker de enriquecimento é chamado com os IDs FHIR corretos.
        O task_capture_procedure (bpmn:task) auto-completa antes do enrich.
        """
        received_vars: list[dict] = []

        from healthcare_platform.shared.workers.base import TaskContext, TaskResult

        def capture_enrich_vars(context: TaskContext) -> TaskResult:
            received_vars.append(dict(context.variables))
            return TaskResult.success({
                "enrichedData":   "dados_ok",
                "diagnosisCodes": "K80.2",
                "procedureCodes": "40101010",
            })

        worker_map = {
            "revenue_cycle.enrich_procedure": capture_enrich_vars,
            "NotificarPendenciaTasy":          stub_worker({"notified": True}),
        }
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "patientId":   HAPPY_PATH_IDS["patient"],
                "encounterId": HAPPY_PATH_IDS["encounter"],
                "capturedData":      "{}",
                "captureTimestamp":  "2026-03-18T10:00:00Z",
                "quantities":        "1",
                "units":             "UN",
                "validationResult":  True,
                "validationErrors":  "",
            })
            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)

        assert state == "COMPLETED", f"Estado: {state} | Erros: {harness.errors}"
        assert len(received_vars) >= 1, "Worker de enriquecimento não foi chamado"
        assert received_vars[0].get("encounterId") == HAPPY_PATH_IDS["encounter"]
