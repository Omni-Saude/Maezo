"""
conftest.py — Fixtures compartilhadas para testes E2E do ambiente local MAEZO.

Requer ambiente Docker rodando:
    bash scripts/dev/start_local.sh --infra

Configuração via variáveis de ambiente (ou valores padrão para local):
    E2E_CIB7_URL=http://localhost:8080
    E2E_FHIR_URL=http://localhost:8082
    E2E_CE_URL=http://localhost:8000
    E2E_DEBEZIUM_URL=http://localhost:8083
    E2E_PROMETHEUS_URL=http://localhost:9090
    E2E_GRAFANA_URL=http://localhost:3000
    E2E_PG_DSN=postgresql://maestro:maestro_local@localhost:5432/cibseven
    E2E_TIMEOUT=10
"""
from __future__ import annotations

import os
import time
from typing import Generator

import httpx
import pytest


# ---------------------------------------------------------------------------
# Configuração de URLs (override via env para outros ambientes)
# ---------------------------------------------------------------------------

CIB7_URL = os.getenv("E2E_CIB7_URL", "http://localhost:8080")
FHIR_URL = os.getenv("E2E_FHIR_URL", "http://localhost:8082")
CE_URL = os.getenv("E2E_CE_URL", "http://localhost:8000")
DEBEZIUM_URL = os.getenv("E2E_DEBEZIUM_URL", "http://localhost:8083")
PROMETHEUS_URL = os.getenv("E2E_PROMETHEUS_URL", "http://localhost:9090")
GRAFANA_URL = os.getenv("E2E_GRAFANA_URL", "http://localhost:3000")
PG_DSN = os.getenv(
    "E2E_PG_DSN",
    "postgresql://maestro:maestro_local@localhost:5432/cibseven",
)
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "10"))

CIB7_USER = os.getenv("E2E_CIB7_USER", "admin")
CIB7_PASS = os.getenv("E2E_CIB7_PASS", "admin")
GRAFANA_USER = os.getenv("E2E_GRAFANA_USER", "admin")
GRAFANA_PASS = os.getenv("E2E_GRAFANA_PASS", "admin")

# Workers health endpoints (porta local → porta interna 8000)
WORKER_URLS = {
    "rc": os.getenv("E2E_WORKER_RC_URL", "http://localhost:8100"),
    "co": os.getenv("E2E_WORKER_CO_URL", "http://localhost:8101"),
    "pa": os.getenv("E2E_WORKER_PA_URL", "http://localhost:8102"),
    "ps": os.getenv("E2E_WORKER_PS_URL", "http://localhost:8103"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_url(url: str, timeout: float = 30, interval: float = 2) -> bool:
    """Aguarda uma URL ficar disponível. Retorna True se OK, False se timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Fixtures de clientes HTTP
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    """Cliente HTTP genérico (sem auth)."""
    with httpx.Client(timeout=TIMEOUT) as client:
        yield client


@pytest.fixture(scope="session")
def cib7_client() -> Generator[httpx.Client, None, None]:
    """Cliente HTTP para CIB Seven com Basic Auth."""
    with httpx.Client(
        base_url=f"{CIB7_URL}/engine-rest",
        auth=(CIB7_USER, CIB7_PASS),
        timeout=TIMEOUT,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def fhir_client() -> Generator[httpx.Client, None, None]:
    """Cliente HTTP para HAPI FHIR R4."""
    with httpx.Client(
        base_url=f"{FHIR_URL}/fhir",
        headers={"Accept": "application/fhir+json", "Content-Type": "application/fhir+json"},
        timeout=TIMEOUT,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def prometheus_client() -> Generator[httpx.Client, None, None]:
    """Cliente HTTP para Prometheus."""
    with httpx.Client(base_url=PROMETHEUS_URL, timeout=TIMEOUT) as client:
        yield client


@pytest.fixture(scope="session")
def grafana_client() -> Generator[httpx.Client, None, None]:
    """Cliente HTTP para Grafana com Basic Auth."""
    with httpx.Client(
        base_url=GRAFANA_URL,
        auth=(GRAFANA_USER, GRAFANA_PASS),
        timeout=TIMEOUT,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Fixtures de pré-condição (skip automático se serviço não estiver UP)
# ---------------------------------------------------------------------------


def _service_available(url: str, path: str = "/", auth: tuple | None = None) -> bool:
    try:
        r = httpx.get(f"{url}{path}", auth=auth, timeout=5)
        return r.status_code < 500
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=False)
def require_cib7():
    """Skip se CIB Seven não estiver disponível."""
    if not _service_available(CIB7_URL, "/engine-rest/engine", (CIB7_USER, CIB7_PASS)):
        pytest.skip("CIB Seven não disponível — execute: bash scripts/dev/start_local.sh")


@pytest.fixture(scope="session", autouse=False)
def require_fhir():
    """Skip se HAPI FHIR não estiver disponível."""
    if not _service_available(FHIR_URL, "/fhir/metadata"):
        pytest.skip("HAPI FHIR não disponível — execute: bash scripts/dev/start_local.sh")


@pytest.fixture(scope="session", autouse=False)
def require_prometheus():
    """Skip se Prometheus não estiver disponível."""
    if not _service_available(PROMETHEUS_URL, "/-/healthy"):
        pytest.skip("Prometheus não disponível — execute: bash scripts/dev/start_local.sh")


@pytest.fixture(scope="session", autouse=False)
def require_grafana():
    """Skip se Grafana não estiver disponível."""
    if not _service_available(GRAFANA_URL, "/api/health"):
        pytest.skip("Grafana não disponível — execute: bash scripts/dev/start_local.sh")


@pytest.fixture(scope="session", autouse=False)
def require_workers():
    """Skip se workers não estiverem disponíveis."""
    if not _service_available(WORKER_URLS["rc"], "/health"):
        pytest.skip("Workers não disponíveis — execute: bash scripts/dev/start_local.sh (modo completo)")


@pytest.fixture(scope="session", autouse=False)
def require_ce_api():
    """Skip se CE API não estiver disponível."""
    if not _service_available(CE_URL, "/health"):
        pytest.skip("CE API não disponível — execute: bash scripts/dev/start_local.sh")


@pytest.fixture(scope="session", autouse=False)
def require_debezium():
    """Skip se Debezium não estiver disponível."""
    if not _service_available(DEBEZIUM_URL, "/connectors"):
        pytest.skip("Debezium não disponível — execute: bash scripts/dev/start_local.sh")
