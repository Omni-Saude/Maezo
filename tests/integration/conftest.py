"""
conftest.py — Fixtures compartilhadas para testes de integração com workers reais.

Reutiliza as mesmas configurações de ambiente do conftest E2E.
"""
from __future__ import annotations

import os
import subprocess

import httpx
import pytest

CIB7_URL = os.getenv("E2E_CIB7_URL", "http://localhost:8080")
CIB7_USER = os.getenv("E2E_CIB7_USER", "admin")
CIB7_PASS = os.getenv("E2E_CIB7_PASS", "admin")

# Container do worker RC de produção (compete com o harness de integração)
RC_WORKER_CONTAINER = os.getenv("MAEZO_RC_WORKER_CONTAINER", "maezo-workers-workers_rc-1")

# Tópicos usados pelos testes de integração RC que o worker de produção também serve
_RC_INTEGRATION_TOPICS = [
    "revenue_cycle.capture_procedure",
    "revenue_cycle.enrich_procedure",
    "revenue_cycle.calculate_quantity",
    "revenue_cycle.validate_documentation",
    "revenue_cycle.validate_clinical_data",
    "revenue_cycle.check_authorization",
    "revenue_cycle.request_authorization",
    "revenue_cycle.validate_procedure",
    "glosa.identify",
    "glosa.classify_type",
    "glosa.analyze_reason",
    "glosa.predict_risk",
    "denial.submit_appeal",
    "denial.track_appeal_status",
    "denial.generate_appeal_documentation",
]


def _service_available(url: str, path: str = "/", auth: tuple | None = None) -> bool:
    try:
        r = httpx.get(f"{url}{path}", auth=auth, timeout=5)
        return r.status_code < 500
    except Exception:
        return False


def _docker_pause(container: str) -> bool:
    result = subprocess.run(["docker", "pause", container], capture_output=True, text=True)
    return result.returncode == 0


def _docker_unpause(container: str) -> bool:
    result = subprocess.run(["docker", "unpause", container], capture_output=True, text=True)
    return result.returncode == 0


def _container_running(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", container],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "running"


def _unlock_competing_tasks(topics: list[str]) -> int:
    """
    Desbloqueia external tasks lockadas nos tópicos de integração.

    Cobre dois casos:
    - Worker de produção com locks longos (30 min)
    - Harness de sessões de teste anteriores ("integration-test-harness") com
      locks de 30s que podem ainda estar ativos no início da sessão atual

    Retorna quantas tasks foram desbloqueadas.
    """
    unlocked = 0
    try:
        with httpx.Client(
            base_url=f"{CIB7_URL}/engine-rest",
            auth=(CIB7_USER, CIB7_PASS),
            timeout=10,
        ) as c:
            r = c.get("/external-task", params={"active": "true"})
            if r.status_code != 200:
                return 0
            for task in r.json():
                topic = task.get("topicName", "")
                lock_exp = task.get("lockExpirationTime")
                # Desbloquear QUALQUER task nos tópicos de integração que esteja lockada.
                # Inclui locks do worker de produção (30 min) E locks residuais de
                # sessões de teste anteriores (harness "integration-test-harness").
                if topic in topics and lock_exp:
                    resp = c.post(f"/external-task/{task['id']}/unlock")
                    if resp.status_code == 204:
                        unlocked += 1
    except Exception:
        pass
    return unlocked


@pytest.fixture(scope="session", autouse=False)
def require_cib7():
    """Skip se CIB Seven não estiver disponível."""
    if not _service_available(CIB7_URL, "/engine-rest/engine", (CIB7_USER, CIB7_PASS)):
        pytest.skip("CIB Seven não disponível — execute: bash scripts/dev/start_local.sh")


@pytest.fixture(scope="session")
def pause_rc_worker():
    """
    Pausa o worker RC de produção e desbloqueia tasks já lockadas.

    O worker de produção (`maezo-worker-7`) compete com o WorkerHarness pelos
    mesmos tópicos (revenue_cycle.*, glosa.*, denial.*). Este fixture:
    1. Pausa o container Docker do worker RC
    2. Desbloqueia tasks já lockadas pelo worker de produção (locks de 30 min)

    Ao final (teardown), retoma o container.
    Escopo 'session': pausa uma vez para toda a sessão de testes, evitando
    janelas de concorrência entre módulos de teste.
    """
    was_running = _container_running(RC_WORKER_CONTAINER)
    if was_running:
        _docker_pause(RC_WORKER_CONTAINER)

    # Desbloquear tasks já lockadas pelo worker de produção
    _unlock_competing_tasks(_RC_INTEGRATION_TOPICS)

    yield

    if was_running:
        _docker_unpause(RC_WORKER_CONTAINER)
