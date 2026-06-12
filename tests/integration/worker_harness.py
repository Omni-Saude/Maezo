"""
WorkerHarness — infraestrutura para testes de integração com workers reais.

Executa workers Python reais contra o CIB Seven em uma thread de background.
O harness faz fetchAndLock, chama worker.execute(context), e reporta o
resultado de volta ao engine (complete/bpmnError/failure).

Uso:
    worker_map = {
        "glosa.identify": IdentifyGlosaWorkerV2(dmn_service=mock_dmn),
        "glosa.classify_type": stub_worker({"classifiedGlosas": "[]", "primaryType": "ADMINISTRATIVA"}),
    }
    with WorkerHarness(client, worker_map) as harness:
        instance_id = _start(client, "SP_RC_007_Denial_Management", {...})
        state = wait_for_state(client, instance_id, "COMPLETED", timeout_s=30)
        assert state == "COMPLETED"
"""
from __future__ import annotations

import dataclasses
import json
import threading
import time
from typing import Any, Callable

import httpx

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

HARNESS_WORKER_ID = "integration-test-harness"
LOCK_MS = 30_000  # 30s lock — suficiente para execução de worker em teste


def _type_of(v: Any) -> str:
    if isinstance(v, bool):
        return "Boolean"
    if isinstance(v, int):
        return "Integer"
    if isinstance(v, float):
        return "Double"
    return "String"


def _serialize_value(v: Any) -> Any:
    """Converte listas/dicts para JSON string (Camunda aceita String)."""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def _to_camunda_vars(variables: dict[str, Any]) -> dict:
    return {
        k: {"value": _serialize_value(v), "type": _type_of(v)}
        for k, v in variables.items()
    }


def _from_camunda_vars(raw: dict) -> dict[str, Any]:
    """Converte variáveis do formato Camunda para dict Python.
    Tenta fazer parse de strings JSON automaticamente.
    """
    result = {}
    for k, vobj in raw.items():
        val = vobj.get("value")
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass
        result[k] = val
    return result


# ---------------------------------------------------------------------------
# WorkerHarness
# ---------------------------------------------------------------------------

class WorkerHarness:
    """
    Roda workers V2 contra o CIB Seven em uma thread de background.

    worker_map: dict[topic → callable(TaskContext) → TaskResult]
        O callable pode ser um worker real (BaseExternalTaskWorker) passado como
        instância (usa .execute(context)), ou qualquer função compatível.

    NOTA: o harness cria seu próprio httpx.Client interno para o thread de
    background. httpx.Client não é thread-safe — compartilhar o mesmo client
    com o thread principal causa falhas intermitentes em testes.
    """

    def __init__(
        self,
        client: httpx.Client,
        worker_map: dict[str, Any],  # topic → worker_instance | callable
        instance_ids: list[str] | None = None,  # filtrar por instância (opcional)
    ):
        # client é usado apenas para extrair base_url/auth — não compartilhado com o thread
        self._base_url = str(client.base_url)
        self._auth = client.auth
        self._timeout = client.timeout
        self._worker_map = worker_map
        self._instance_ids = instance_ids
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._harness_client: httpx.Client | None = None
        self.executed: list[dict] = []   # tarefas executadas com sucesso
        self.errors: list[dict] = []     # erros de worker

    # ── ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop.clear()
        # Cliente dedicado ao thread de background (thread-safety via isolamento)
        self._harness_client = httpx.Client(
            base_url=self._base_url,
            auth=self._auth,
            timeout=self._timeout,
        )
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        if self._harness_client:
            self._harness_client.close()
            self._harness_client = None

    def __enter__(self) -> "WorkerHarness":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    # ── polling loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        topics: list[dict] = []
        for topic in self._worker_map:
            entry: dict = {"topicName": topic, "lockDuration": LOCK_MS}
            if self._instance_ids:
                entry["processInstanceIdIn"] = self._instance_ids
            topics.append(entry)

        while not self._stop.is_set():
            try:
                r = self._harness_client.post(
                    "/external-task/fetchAndLock",
                    json={
                        "workerId": HARNESS_WORKER_ID,
                        "maxTasks": 10,
                        "usePriority": False,
                        "topics": topics,
                    },
                )
                tasks = r.json() if r.status_code == 200 else []
            except Exception:
                tasks = []

            for raw_task in tasks:
                self._dispatch(raw_task)

            if not tasks:
                time.sleep(0.2)

    def _dispatch(self, raw_task: dict) -> None:
        topic = raw_task.get("topicName", "")
        worker = self._worker_map.get(topic)
        if worker is None:
            return

        variables = _from_camunda_vars(raw_task.get("variables", {}))
        context = TaskContext(
            task_id=raw_task["id"],
            process_instance_id=raw_task["processInstanceId"],
            tenant_id=raw_task.get("tenantId") or "HOSPITAL_A",
            variables=variables,
            worker_id=HARNESS_WORKER_ID,
        )

        try:
            # Suporte a instâncias de worker (com .execute()) ou callables diretos
            if hasattr(worker, "execute"):
                result = worker.execute(context)
            else:
                result = worker(context)

            self.executed.append({
                "topic": topic,
                "task_id": raw_task["id"],
                "instance_id": raw_task["processInstanceId"],
                "status": result.status.value,
                "vars": list((result.variables or {}).keys()),
            })
        except Exception as exc:
            result = TaskResult.failure(str(exc))
            self.errors.append({"topic": topic, "error": str(exc)})

        self._report(raw_task["id"], result)

    def _report(self, task_id: str, result: TaskResult) -> None:
        cam_vars = _to_camunda_vars(result.variables or {})

        if result.status == TaskStatus.SUCCESS:
            self._harness_client.post(
                f"/external-task/{task_id}/complete",
                json={"workerId": HARNESS_WORKER_ID, "variables": cam_vars},
            )
        elif result.status == TaskStatus.BPMN_ERROR:
            self._harness_client.post(
                f"/external-task/{task_id}/bpmnError",
                json={
                    "workerId": HARNESS_WORKER_ID,
                    "errorCode": result.error_code or "ERR_UNKNOWN",
                    "errorMessage": result.error_message or "",
                    "variables": cam_vars,
                },
            )
        else:
            self._harness_client.post(
                f"/external-task/{task_id}/failure",
                json={
                    "workerId": HARNESS_WORKER_ID,
                    "errorMessage": result.error_message or "Worker failure",
                    "retries": 0,
                    "retryTimeout": 0,
                },
            )


# ---------------------------------------------------------------------------
# Helpers reutilizáveis
# ---------------------------------------------------------------------------

def wait_for_state(
    client: httpx.Client,
    instance_id: str,
    expected: str = "COMPLETED",
    timeout_s: float = 30.0,
) -> str:
    """Aguarda um processo atingir o estado esperado. Retorna o estado final."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(
            "/history/process-instance",
            params={"processInstanceId": instance_id},
        )
        hist = r.json()
        if hist:
            state = hist[0].get("state", "UNKNOWN")
            if state == expected or state in (
                "EXTERNALLY_TERMINATED",
                "INTERNALLY_TERMINATED",
            ):
                return state
        time.sleep(0.3)
    return "TIMEOUT"


def get_process_variables(client: httpx.Client, instance_id: str) -> dict[str, Any]:
    """Retorna todas as variáveis de uma instância de processo (histórico)."""
    r = client.get(
        "/history/variable-instance",
        params={"processInstanceId": instance_id},
    )
    if r.status_code != 200:
        return {}
    return {
        item["name"]: item.get("value")
        for item in r.json()
    }


def start_process(
    client: httpx.Client,
    process_key: str,
    variables: dict[str, Any],
) -> str:
    """Inicia uma instância de processo e retorna o instanceId."""
    payload = {
        "variables": {
            k: {"value": _serialize_value(v), "type": _type_of(v)}
            for k, v in variables.items()
        }
    }
    r = client.post(f"/process-definition/key/{process_key}/start", json=payload)
    assert r.status_code == 200, f"Falha ao iniciar {process_key}: {r.text[:300]}"
    return r.json()["id"]


def cancel_instance(client: httpx.Client, instance_id: str) -> None:
    """Cancela uma instância de processo (cleanup de teste)."""
    client.delete(
        f"/process-instance/{instance_id}",
        params={"skipCustomListeners": "true", "skipIoMappings": "true"},
    )


def cancel_all_active(client: httpx.Client, process_key: str) -> int:
    """Cancela todas as instâncias ativas de um processo. Retorna quantas foram canceladas."""
    r = client.get(
        "/process-instance",
        params={"processDefinitionKey": process_key, "active": "true"},
    )
    if r.status_code != 200:
        return 0
    count = 0
    for inst in r.json():
        cancel_instance(client, inst["id"])
        count += 1
    return count


def trigger_timers(
    client: httpx.Client,
    instance_id: str,
    wait_s: float = 5.0,
) -> int:
    """Dispara todos os timer jobs pendentes de uma instância."""
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


# ---------------------------------------------------------------------------
# Stub worker factory
# ---------------------------------------------------------------------------

def stub_worker(output_vars: dict[str, Any]) -> Callable[[TaskContext], TaskResult]:
    """Cria um worker stub que sempre retorna SUCCESS com variáveis fixas."""
    def _worker(context: TaskContext) -> TaskResult:
        return TaskResult.success(output_vars)
    return _worker


def make_mock_dmn(responses: dict[str, dict] | None = None):
    """
    Cria um mock de FederatedDMNService com respostas configuráveis.

    responses: dict mapping decision_key → result dict
    Default para qualquer chave não mapeada: {"resultado": "PROSSEGUIR", "risco": "BAIXO", "acao": "OK"}
    """
    from unittest.mock import MagicMock

    default = {"resultado": "PROSSEGUIR", "risco": "BAIXO", "acao": "OK"}
    configured = responses or {}

    def _evaluate(tenant_id: str, category: str, table_name: str, inputs: dict) -> dict:
        override = configured.get(table_name, {})
        return {**default, **override}

    mock = MagicMock()
    mock.evaluate.side_effect = _evaluate
    return mock
