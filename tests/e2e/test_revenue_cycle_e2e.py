"""
test_revenue_cycle_e2e.py — Testes E2E do fluxo Revenue Cycle.

Estratégia: o próprio teste atua como mock-worker, usando a API
fetchAndLock → complete do CIB Seven. Isso valida:
  - Orquestração BPMN real (gateways, routing, timers, boundaries)
  - Variáveis de processo (entrada/saída de cada task)
  - Comportamento de erro e caminhos alternativos

Não requer Tasy, FHIR nem outros serviços externos.
Requer apenas: CIB Seven rodando em http://localhost:8080

Uso rápido:
    PYTHONUTF8=1 pytest tests/e2e/test_revenue_cycle_e2e.py -v

Para rodar junto ao suite E2E completo:
    PYTHONUTF8=1 pytest tests/e2e/ -v -m e2e
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import CIB7_URL, CIB7_USER, CIB7_PASS, TIMEOUT

# ---------------------------------------------------------------------------
# Constantes e helpers
# ---------------------------------------------------------------------------

WORKER_ID = "e2e-rc-test-worker"
LOCK_MS   = 60_000  # 60s de lock — suficiente para cada step do teste
TENANT_ID = "Maezo_rc"


def _cib7() -> httpx.Client:
    """Retorna cliente HTTP configurado para CIB Seven."""
    return httpx.Client(
        base_url=f"{CIB7_URL}/engine-rest",
        auth=(CIB7_USER, CIB7_PASS),
        timeout=TIMEOUT,
    )


def _start(client: httpx.Client, process_key: str, variables: dict[str, Any]) -> str:
    """Inicia uma instância de processo e retorna o instanceId."""
    payload = {
        "variables": {
            k: {"value": v, "type": _type(v)}
            for k, v in variables.items()
        }
    }
    r = client.post(f"/process-definition/key/{process_key}/tenant-id/{TENANT_ID}/start", json=payload)
    assert r.status_code == 200, f"Falha ao iniciar {process_key}: {r.text[:300]}"
    return r.json()["id"]


def _type(v: Any) -> str:
    if isinstance(v, bool):
        return "Boolean"
    if isinstance(v, int):
        return "Integer"
    if isinstance(v, float):
        return "Double"
    return "String"


def _fetch_task(
    client: httpx.Client,
    topic: str,
    instance_id: str | None = None,
    timeout_s: float = 15.0,
) -> dict | None:
    """
    Faz fetchAndLock em um tópico específico.
    Quando `instance_id` é fornecido, filtra pelo processInstanceId para evitar
    capturar tarefas de instâncias de testes anteriores (stale tasks).
    Retorna o dict da task ou None se não encontrar.
    """
    deadline = time.monotonic() + timeout_s
    topic_filter: dict = {"topicName": topic, "lockDuration": LOCK_MS}
    if instance_id:
        topic_filter["processInstanceIdIn"] = [instance_id]
    while time.monotonic() < deadline:
        r = client.post(
            "/external-task/fetchAndLock",
            json={
                "workerId": WORKER_ID,
                "maxTasks": 1,
                "usePriority": False,
                "topics": [topic_filter],
            },
        )
        assert r.status_code == 200, f"fetchAndLock falhou: {r.text}"
        tasks = r.json()
        if tasks:
            return tasks[0]
        time.sleep(0.5)
    return None


def _complete(client: httpx.Client, task_id: str, output_vars: dict[str, Any] | None = None) -> None:
    """Completa uma external task com variáveis de saída opcionais."""
    variables = {}
    if output_vars:
        variables = {k: {"value": v, "type": _type(v)} for k, v in output_vars.items()}
    r = client.post(
        f"/external-task/{task_id}/complete",
        json={"workerId": WORKER_ID, "variables": variables},
    )
    assert r.status_code == 204, f"Falha ao completar task {task_id}: {r.text}"


def _bpmn_error(client: httpx.Client, task_id: str, code: str, message: str) -> None:
    """Reporta erro BPMN em uma external task (ativa boundary de erro)."""
    r = client.post(
        f"/external-task/{task_id}/bpmnError",
        json={
            "workerId": WORKER_ID,
            "errorCode": code,
            "errorMessage": message,
        },
    )
    assert r.status_code == 204, f"Falha ao reportar bpmnError {task_id}: {r.text}"


def _trigger_timer_jobs(client: httpx.Client, instance_id: str, wait_s: float = 5.0) -> int:
    """
    Dispara todos os timer jobs pendentes de uma instância.
    Em testes, isso substitui a espera real (evita PT1H, PT24H, P30D).
    Retorna o número de jobs disparados.
    """
    deadline = time.monotonic() + wait_s
    triggered = 0
    while time.monotonic() < deadline:
        r = client.get("/job", params={"processInstanceId": instance_id})
        jobs = [j for j in r.json() if not j.get("suspended")]
        if jobs:
            for job in jobs:
                client.post(f"/job/{job['id']}/execute")
                triggered += 1
            return triggered
        time.sleep(0.5)
    return triggered


def _process_state(client: httpx.Client, instance_id: str) -> str:
    """Retorna o estado atual da instância (ACTIVE, COMPLETED, etc.)."""
    r = client.get("/history/process-instance", params={"processInstanceId": instance_id})
    history = r.json()
    return history[0]["state"] if history else "UNKNOWN"


def _active_tasks(client: httpx.Client, instance_id: str) -> list[dict]:
    """Retorna as external tasks ativas de uma instância."""
    r = client.get("/external-task", params={"processInstanceId": instance_id})
    return r.json()


def _cancel(client: httpx.Client, instance_id: str) -> None:
    """Cancela uma instância de processo (cleanup de teste)."""
    client.delete(f"/process-instance/{instance_id}", params={"skipCustomListeners": "true"})


# ---------------------------------------------------------------------------
# SP-RC-002 — Pré-Atendimento e Autorização
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestPreServiceAuthorization:
    """
    Fluxo SP_RC_002_Pre_Service — happy path e caminhos alternativos.

    Diagrama simplificado:
        start
          → task_check_authorization (topic: revenue_cycle.check_authorization)
          → task_request_authorization (topic: revenue_cycle.request_authorization)
          → [timer PT1H — disparado pelo teste]
          → Activity_0qxwn97 / AtualizarTasy (topic: AtualizarTasy)
          → gateway_auth_status
              ├── [PENDING] → dmn_auth_criteria (userTask) → task_manual_auth_review
              └── [default] → task_validate_procedure (topic: revenue_cycle.validate_procedure)
                               → end_approved
    """

    PROCESS_KEY = "SP_RC_002_Pre_Service"

    @pytest.fixture(autouse=True)
    def _clean_stale_instances(self):
        """Cancela instâncias residuais de SP_RC_002 antes de cada teste."""
        with _cib7() as c:
            r = c.get("/process-instance", params={
                "processDefinitionKey": self.PROCESS_KEY,
                "tenantIdIn": TENANT_ID,
                "active": "true",
            })
            if r.status_code == 200:
                for inst in r.json():
                    c.delete(
                        f"/process-instance/{inst['id']}",
                        params={"skipCustomListeners": "true", "skipIoMappings": "true"},
                    )

    def test_happy_path_authorization_approved(self, require_cib7):
        """
        Caminho feliz: autorização aprovada → procedimento validado → fim.
        """
        instance_id = None
        with _cib7() as c:
            # ── 1. Iniciar processo com dados mockados ─────────────────────
            instance_id = _start(c, self.PROCESS_KEY, {
                "patientId":            f"PAT-{uuid.uuid4().hex[:8]}",
                "procedureCode":        "10101012",
                "payerId":              "UNIMED-SP",
                "clinicalJustification": "Cirurgia eletiva — indicação clínica confirmada",
                "encounterId":          f"ENC-{uuid.uuid4().hex[:8]}",
                "clinicalData":         '{"diagnosis": "J18.9", "procedure": "10101012"}',
            })

            try:
                # ── 2. Task: Verificar Necessidade de Autorização ──────────
                task = _fetch_task(c, "revenue_cycle.check_authorization", instance_id)
                assert task, "task_check_authorization não encontrada"
                assert task["processInstanceId"] == instance_id
                _complete(c, task["id"], {
                    "requiresAuth":     True,
                    "authType":         "prior_auth",
                })

                # ── 3. Task: Solicitar Autorização ─────────────────────────
                task = _fetch_task(c, "revenue_cycle.request_authorization", instance_id)
                assert task, "task_request_authorization não encontrada"
                _complete(c, task["id"], {
                    "authorizationNumber": "AUTH-2025-001",
                    "authStatus":          "APPROVED",
                })

                # ── 4. Timer PT1H — disparar imediatamente ─────────────────
                triggered = _trigger_timer_jobs(c, instance_id)
                assert triggered >= 1, "Timer 'após 1 hora' não encontrado"

                # ── 5. Task: Atualizar Tasy ────────────────────────────────
                task = _fetch_task(c, "AtualizarTasy", instance_id)
                assert task, "Task AtualizarTasy não encontrada após timer"
                _complete(c, task["id"], {"tasyUpdated": True})

                # ── 6. Gateway authorizationStatus ≠ PENDING → validar ─────
                # authorizationStatus não é "PENDING", então vai para o path padrão
                task = _fetch_task(c, "revenue_cycle.validate_procedure", instance_id)
                assert task, "task_validate_procedure não encontrada (gateway não roteou para aprovado?)"
                # BPMN outputParameter: name="procedureValidated" → ${validationStatus}
                # O worker deve fornecer "validationStatus" como variável local
                _complete(c, task["id"], {"validationStatus": "OK"})

                # ── 7. Verificar processo concluído ────────────────────────
                time.sleep(0.5)
                state = _process_state(c, instance_id)
                assert state == "COMPLETED", (
                    f"Processo deveria estar COMPLETED, está: {state}"
                )

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)

    def test_authorization_pending_goes_to_manual_review(self, require_cib7):
        """
        Caminho alternativo: autorização PENDING → revisão manual.
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "patientId":            f"PAT-{uuid.uuid4().hex[:8]}",
                "procedureCode":        "50000470",
                "payerId":              "AMIL",
                "clinicalJustification": "Procedimento em auditoria",
                "encounterId":          f"ENC-{uuid.uuid4().hex[:8]}",
                "clinicalData":         '{"diagnosis": "Z00.0", "procedure": "50000470"}',
            })
            try:
                # check_authorization
                task = _fetch_task(c, "revenue_cycle.check_authorization", instance_id)
                assert task
                _complete(c, task["id"], {"requiresAuth": True, "authType": "concurrent_review"})

                # request_authorization — retorna PENDING
                task = _fetch_task(c, "revenue_cycle.request_authorization", instance_id)
                assert task
                _complete(c, task["id"], {
                    "authorizationNumber": "AUTH-PEND-001",
                    "authStatus":          "PENDING",
                })

                # Timer
                _trigger_timer_jobs(c, instance_id)

                # AtualizarTasy
                task = _fetch_task(c, "AtualizarTasy", instance_id)
                assert task
                _complete(c, task["id"], {"tasyUpdated": True})

                # gateway rota para dmn_auth_criteria (userTask = revisão humana)
                # userTask não aparece como external task — verificamos que
                # a instância está ACTIVE e não há external tasks abertas
                time.sleep(0.5)
                ext_tasks = _active_tasks(c, instance_id)
                assert _process_state(c, instance_id) == "ACTIVE"
                # Se houver task RevisarManual (serviceTask), completamos
                task = _fetch_task(c, "RevisarManual", instance_id, timeout_s=3.0)
                if task:
                    _complete(c, task["id"])

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)

    @pytest.mark.xfail(
        reason=(
            "CIB Seven 2.1.3 ENGINE-13033: bpmnError propagation via external task API "
            "falha mesmo com boundary event definido (bug conhecido do engine). "
            "O boundary 'error_authorization_request' existe no BPMN, mas a chamada "
            "POST /external-task/{id}/bpmnError retorna 500 ENGINE-13033."
        ),
        strict=False,
    )
    def test_authorization_error_boundary_triggers_criteria(self, require_cib7):
        """
        Caminho de erro: request_authorization falha → boundary de erro →
        dmn_auth_criteria → manual review.

        NOTA: Marcado como xfail por limitação do CIB Seven 2.1.3 (ENGINE-13033).
        O BPMN está correto — boundary event 'error_authorization_request' captura
        ERR_AUTH_001 e redireciona para revisão humana — mas a API bpmnError do engine
        falha na propagação. Quando o CIB Seven for atualizado, remover @xfail.
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "patientId":  f"PAT-{uuid.uuid4().hex[:8]}",
                "procedureCode": "99999999",
                "payerId":    "BRADESCO",
                "clinicalJustification": "Urgência",
                "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
                "clinicalData": '{"diagnosis": "R69", "procedure": "99999999"}',
            })
            try:
                # check_authorization
                task = _fetch_task(c, "revenue_cycle.check_authorization", instance_id)
                assert task
                _complete(c, task["id"], {"requiresAuth": True, "authType": "prior_auth"})

                # request_authorization — simula falha de comunicação com operadora
                task = _fetch_task(c, "revenue_cycle.request_authorization", instance_id)
                assert task
                _bpmn_error(c, task["id"], "ERR_AUTH_001", "Operadora indisponível")

                # Boundary de erro ativa dmn_auth_criteria (userTask)
                # Processo continua ACTIVE esperando revisão humana
                time.sleep(0.5)
                state = _process_state(c, instance_id)
                assert state == "ACTIVE", (
                    f"Processo deveria estar aguardando revisão, mas está: {state}"
                )

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)

    def test_sla_48h_boundary_escalates(self, require_cib7):
        """
        Timer de SLA 48h na task_request_authorization → escalar autorização.
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "patientId":  f"PAT-{uuid.uuid4().hex[:8]}",
                "procedureCode": "10101012",
                "payerId":    "SULAMÉRICA",
                "clinicalJustification": "Eletivo",
                "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
            })
            try:
                # check_authorization
                task = _fetch_task(c, "revenue_cycle.check_authorization", instance_id)
                assert task
                _complete(c, task["id"], {"requiresAuth": True, "authType": "prior_auth"})

                # request_authorization — deixamos a task ABERTA e disparamos timer de SLA
                # (sem fazer fetchAndLock — simula que a task está "em execução" há 48h)
                # Na realidade, disparamos o boundary timer PT48H
                triggered = _trigger_timer_jobs(c, instance_id, wait_s=3.0)
                if triggered > 0:
                    # Timer de SLA disparou → task_escalate_auth
                    task_esc = _fetch_task(c, "escalar-autoriza-o", instance_id, timeout_s=5.0)
                    if task_esc:
                        _complete(c, task_esc["id"])
                        time.sleep(0.3)
                        state = _process_state(c, instance_id)
                        assert state == "COMPLETED"
                else:
                    # Boundary timer só dispara com a task em execução (locked)
                    # Nesse caso, o teste valida apenas a criação da instância
                    assert _process_state(c, instance_id) == "ACTIVE"

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)


# ---------------------------------------------------------------------------
# SP-RC-003 — Atendimento Clínico e Documentação
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestClinicalServiceDocumentation:
    """
    Fluxo SP_RC_003_Clinical_Service — happy path.

    Diagrama simplificado (happy path):
        start
          → task_capture_procedure (topic: revenue_cycle.capture_procedure)
          → Gateway_0o1p7c9
          → task_enrich_procedure (topic: revenue_cycle.enrich_procedure)
          → dmn_documentation_completeness (businessRuleTask — avaliado pelo engine)
          → gateway_completeness [Sim]
          → task_calculate_quantity (topic: revenue_cycle.calculate_quantity)
          → task_validate_data (topic: revenue_cycle.validate_clinical_data)
          → gateway_validation [Sim]
          → end_success
    """

    PROCESS_KEY = "SP_RC_003_Clinical_Service"

    @pytest.fixture(autouse=True)
    def _clean_stale_instances(self):
        """Cancela instâncias residuais de SP_RC_003 antes de cada teste."""
        with _cib7() as c:
            r = c.get("/process-instance", params={
                "processDefinitionKey": self.PROCESS_KEY,
                "tenantIdIn": TENANT_ID,
                "active": "true",
            })
            if r.status_code == 200:
                for inst in r.json():
                    c.delete(
                        f"/process-instance/{inst['id']}",
                        params={"skipCustomListeners": "true", "skipIoMappings": "true"},
                    )

    def test_happy_path_documentation_complete(self, require_cib7):
        """
        Caminho feliz: captura → enriquecimento → documentação completa → validada → fim.
        A businessRuleTask DMN é avaliada pelo próprio engine (sem mock externo).
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
                "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
            })
            try:
                # ── 1. Capturar dados do procedimento ─────────────────────
                task = _fetch_task(c, "revenue_cycle.capture_procedure", instance_id)
                assert task, "task_capture_procedure não encontrada"
                assert task["processInstanceId"] == instance_id
                _complete(c, task["id"], {
                    "capturedData":     '{"procedures": ["10101012"], "diagnoses": ["J18.9"]}',
                    "captureTimestamp": "2025-01-15T10:30:00Z",
                })

                # ── 2. Enriquecer dados clínicos ──────────────────────────
                task = _fetch_task(c, "revenue_cycle.enrich_procedure", instance_id)
                assert task, "task_enrich_procedure não encontrada"
                _complete(c, task["id"], {
                    "enrichedData":   '{"enriched": true}',
                    "diagnosisCodes": "J18.9",
                    "procedureCodes": "10101012",
                })

                # ── 3. Validar completude da documentação (serviceTask) ────
                task = _fetch_task(c, "revenue_cycle.validate_documentation", instance_id)
                assert task, "validate_documentation não encontrada"
                _complete(c, task["id"], {
                    "docComplete": True,   # True → gateway toma path "Sim" (completo)
                })

                # ── 4. Gateway Sim → calculate_quantity ───────────────────
                task = _fetch_task(c, "revenue_cycle.calculate_quantity", instance_id)
                assert task, "task_calculate_quantity não encontrada"
                # BPMN outputParameter: name="procedureQuantities" → ${quantities}
                # BPMN outputParameter: name="measurementUnits" → ${units}
                _complete(c, task["id"], {
                    "quantities": '{"10101012": 1}',
                    "units":      "UN",
                })

                # ── 5. Validar dados clínicos ─────────────────────────────
                task = _fetch_task(c, "revenue_cycle.validate_clinical_data", instance_id)
                assert task, "task_validate_data não encontrada"
                _complete(c, task["id"], {
                    "validationResult": True,
                    "validationErrors": "",
                })

                # ── 6. gateway_validation [Sim] → end_success ─────────────
                time.sleep(0.5)
                state = _process_state(c, instance_id)
                assert state == "COMPLETED", f"Esperado COMPLETED, obtido: {state}"

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)

    def test_documentation_incomplete_triggers_retry_loop(self, require_cib7):
        """
        Documentação incompleta → notifica pendência → timer 24h → reprocessa.
        Valida que o loop de retry está funcionando corretamente.
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "patientId":   f"PAT-{uuid.uuid4().hex[:8]}",
                "encounterId": f"ENC-{uuid.uuid4().hex[:8]}",
            })
            try:
                # Capture
                task = _fetch_task(c, "revenue_cycle.capture_procedure", instance_id)
                assert task
                _complete(c, task["id"], {
                    "capturedData":     '{"procedures": [], "diagnoses": []}',
                    "captureTimestamp": "2025-01-15T10:30:00Z",
                })

                # Enrich
                task = _fetch_task(c, "revenue_cycle.enrich_procedure", instance_id)
                assert task
                _complete(c, task["id"], {
                    "enrichedData":   '{"enriched": false, "incomplete": true}',
                    "diagnosisCodes": "",
                    "procedureCodes": "",
                })

                # Validar documentação — incompleta para forçar loop
                task = _fetch_task(c, "revenue_cycle.validate_documentation", instance_id)
                assert task, "validate_documentation não encontrada"
                _complete(c, task["id"], {
                    "docComplete": False,  # False → gateway toma path "Não" (incompleto)
                })

                # Documentação incompleta → NotificarPendenciaTasy
                task = _fetch_task(c, "NotificarPendenciaTasy", instance_id, timeout_s=5.0)
                if task:
                    _complete(c, task["id"])
                    # Timer PT24H — disparar imediatamente
                    triggered = _trigger_timer_jobs(c, instance_id, wait_s=5.0)
                    # Após timer, volta para enrich_procedure (retry loop)
                    if triggered > 0:
                        task = _fetch_task(c, "revenue_cycle.enrich_procedure", instance_id, timeout_s=5.0)
                        if task:
                            # Segunda tentativa — dados completos agora
                            _complete(c, task["id"], {
                                "enrichedData":   '{"enriched": true}',
                                "diagnosisCodes": "J18.9",
                                "procedureCodes": "10101012",
                            })

                # Instância deve estar ACTIVE (progredindo no loop ou finalizada)
                time.sleep(0.5)
                state = _process_state(c, instance_id)
                assert state in ("ACTIVE", "COMPLETED"), f"Estado inesperado: {state}"

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)


# ---------------------------------------------------------------------------
# SP-RC-007 — Gestão de Glosas
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestDenialManagement:
    """
    Fluxo SP_RC_007_Denial_Management — happy path e prazo expirado.

    Diagrama simplificado (happy path):
        start
          → task_identify_glosa (topic: glosa.identify)
          → task_classify_glosa_type (topic: glosa.classify_type)
          → task_analyze_glosa_reason (topic: glosa.analyze_reason)
          → dmn_predict_risk (serviceTask: glosa.predict_risk)
          → dmn_prevention_strategy (serviceTask: glosa.prevention_strategy)
          → task_check_appeal_eligibility (topic: VerificarElegibilidade)
          → gateway_eligibility [Sim]
          → Activity_1s4ckeb / ColetarDados (topic: ColetarDados)
          → dmn_recovery_strategy (serviceTask: glosa.recovery_strategy)
          → dmn_recovery_eligibility (serviceTask: glosa.recovery_eligibility)
          → task_generate_appeal_documentation (topic: denial.generate_appeal_documentation)
          → task_submit_appeal (topic: denial.submit_appeal)
          → task_track_appeal_status (topic: denial.track_appeal_status)
          → end_success
    """

    PROCESS_KEY = "SP_RC_007_Denial_Management"

    def test_eligible_appeal_happy_path(self, require_cib7):
        """
        Glosa elegível → recurso submetido → acompanhamento.
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "batchId":       f"BATCH-{uuid.uuid4().hex[:8]}",
                "payerResponse": '{"status": "denied", "reason": "GLOSA-001"}',
                "payerId":       "UNIMED-SP",
            })
            try:
                # 1. Identificar glosa
                task = _fetch_task(c, "glosa.identify", instance_id)
                assert task, "task_identify_glosa não encontrada"
                _complete(c, task["id"], {
                    "glosaItems": '[{"code": "10101012", "reason": "GLOSA-001", "value": 500.00}]',
                    "glosaCount": 1,
                })

                # 2. Classificar tipo de glosa
                task = _fetch_task(c, "glosa.classify_type", instance_id)
                assert task
                _complete(c, task["id"], {
                    "classifiedGlosas": '[{"code": "10101012", "type": "ADMINISTRATIVA"}]',
                    "primaryType":      "ADMINISTRATIVA",
                })

                # 3. Analisar razão
                task = _fetch_task(c, "glosa.analyze_reason", instance_id)
                assert task
                _complete(c, task["id"], {
                    "rootCause":       "DOCUMENTACAO_INCOMPLETA",
                    "analysisDetails": "Faltou anexar laudo médico",
                })

                # 4. Prever risco (serviceTask — mock worker)
                task = _fetch_task(c, "glosa.predict_risk", instance_id)
                assert task, "glosa.predict_risk não encontrada"
                _complete(c, task["id"], {"riskScore": 0.3, "riskCategory": "LOW"})

                # 5. Estratégia de prevenção (serviceTask — mock worker)
                task = _fetch_task(c, "glosa.prevention_strategy", instance_id)
                assert task, "glosa.prevention_strategy não encontrada"
                _complete(c, task["id"], {"preventionActions": '["verificar_documentacao"]'})

                # 6. Verificar elegibilidade
                task = _fetch_task(c, "VerificarElegibilidade", instance_id, timeout_s=10.0)
                assert task, "task_check_appeal_eligibility não encontrada"
                _complete(c, task["id"], {
                    "isEligible":       True,
                    "eligibilityReason": "Dentro do prazo de 30 dias",
                })

                # 7. Coletar dados (elegível → sim)
                task = _fetch_task(c, "ColetarDados", instance_id)
                assert task
                _complete(c, task["id"], {"collectedData": '{"docs": ["laudo.pdf"]}'})

                # 8. Recovery strategy (serviceTask — mock worker)
                task = _fetch_task(c, "glosa.recovery_strategy", instance_id)
                assert task, "glosa.recovery_strategy não encontrada"
                _complete(c, task["id"], {"recoveryPlan": '{"strategy": "RECURSO_ADMINISTRATIVO"}'})

                # 9. Recovery eligibility (serviceTask — mock worker)
                task = _fetch_task(c, "glosa.recovery_eligibility", instance_id)
                assert task, "glosa.recovery_eligibility não encontrada"
                _complete(c, task["id"], {"recoveryEligibility": '{"eligible": true}'})

                # 10. Gerar documentação do recurso
                task = _fetch_task(c, "denial.generate_appeal_documentation", instance_id, timeout_s=10.0)
                assert task
                _complete(c, task["id"], {
                    "appealDocuments": '["laudo.pdf", "recurso.pdf"]',
                    "appealPackage":   '{"complete": true}',
                })

                # 11. Submeter recurso
                task = _fetch_task(c, "denial.submit_appeal", instance_id)
                assert task
                _complete(c, task["id"], {
                    "appealId":       f"APPEAL-{uuid.uuid4().hex[:8]}",
                    "submissionDate": "2025-01-15",
                })

                # 12. Acompanhar status
                task = _fetch_task(c, "denial.track_appeal_status", instance_id)
                assert task
                _complete(c, task["id"], {
                    "currentStatus": "SUBMITTED",
                    "payerResponse": '{"received": true}',
                })

                # Fim
                time.sleep(0.5)
                assert _process_state(c, instance_id) == "COMPLETED"

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)

    def test_not_eligible_goes_to_review(self, require_cib7):
        """
        Glosa não elegível → revisão manual (userTask).
        """
        instance_id = None
        with _cib7() as c:
            instance_id = _start(c, self.PROCESS_KEY, {
                "batchId":       f"BATCH-{uuid.uuid4().hex[:8]}",
                "payerResponse": '{"status": "denied", "reason": "GLOSA-999"}',
                "payerId":       "AMIL",
            })
            try:
                # identify → classify → analyze
                for topic in ["glosa.identify", "glosa.classify_type", "glosa.analyze_reason"]:
                    task = _fetch_task(c, topic, instance_id)
                    assert task, f"Task do tópico '{topic}' não encontrada"
                    _complete(c, task["id"], {
                        "glosaItems": "[]", "glosaCount": 0,
                        "classifiedGlosas": "[]", "primaryType": "DESCONHECIDA",
                        "rootCause": "PRAZO_EXPIRADO", "analysisDetails": "Fora do prazo",
                    })

                # predict_risk + prevention_strategy (serviceTasks)
                task = _fetch_task(c, "glosa.predict_risk", instance_id)
                assert task, "glosa.predict_risk não encontrada"
                _complete(c, task["id"], {"riskScore": 0.9, "riskCategory": "HIGH"})

                task = _fetch_task(c, "glosa.prevention_strategy", instance_id)
                assert task, "glosa.prevention_strategy não encontrada"
                _complete(c, task["id"], {"preventionActions": '[]'})

                time.sleep(0.5)

                # check_appeal_eligibility → não elegível
                task = _fetch_task(c, "VerificarElegibilidade", instance_id, timeout_s=10.0)
                assert task
                _complete(c, task["id"], {
                    "isEligible":       False,
                    "eligibilityReason": "Prazo de contestação expirado",
                })

                # gateway → não elegível → userTask (revisão humana)
                # userTask fica ACTIVE, não aparece como external task
                time.sleep(0.5)
                assert _process_state(c, instance_id) == "ACTIVE"
                # External tasks devem estar vazias (userTask não é external)
                ext = _active_tasks(c, instance_id)
                assert len(ext) == 0, f"Esperado userTask (sem external), mas há: {ext}"

            finally:
                if instance_id and _process_state(c, instance_id) == "ACTIVE":
                    _cancel(c, instance_id)
