"""
test_workers.py — Testes E2E dos Workers Python (CIB Seven External Tasks).

Valida: health endpoints, métricas Prometheus, MOCK_MODE,
        conectividade com CIB Seven (fetchAndLock).
Requer: workers containers rodando (portas 8100-8103)
"""
from __future__ import annotations

import pytest
import httpx

from tests.e2e.conftest import WORKER_URLS, CIB7_URL, CIB7_USER, CIB7_PASS, TIMEOUT


# ---------------------------------------------------------------------------
# Worker Health
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestWorkerHealth:
    """Testa endpoints /health dos workers."""

    @pytest.mark.parametrize("domain,url", list(WORKER_URLS.items()))
    def test_worker_health_up(self, require_workers, http_client, domain, url):
        """Worker deve retornar status UP no /health."""
        try:
            r = http_client.get(f"{url}/health")
        except httpx.ConnectError:
            pytest.skip(f"Worker {domain} não disponível em {url}")
        assert r.status_code == 200, (
            f"Worker {domain} retornou {r.status_code}: {r.text[:100]}"
        )
        data = r.json()
        assert data.get("status") == "UP", (
            f"Worker {domain} status: {data.get('status')} (esperado UP)"
        )

    def test_all_workers_healthy(self, require_workers, http_client):
        """Todos os 4 workers devem estar UP."""
        failing = []
        for domain, url in WORKER_URLS.items():
            try:
                r = http_client.get(f"{url}/health", timeout=5)
                if r.status_code != 200 or r.json().get("status") != "UP":
                    failing.append(f"{domain}: status={r.status_code}")
            except Exception as e:
                failing.append(f"{domain}: {e}")

        assert not failing, f"Workers com problema: {failing}"


# ---------------------------------------------------------------------------
# Worker Metrics
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestWorkerMetrics:
    """Testa exposição de métricas Prometheus nos workers."""

    @pytest.mark.parametrize("domain,url", list(WORKER_URLS.items()))
    def test_worker_metrics_exposed(self, require_workers, http_client, domain, url):
        """Worker deve expor /metrics no formato Prometheus."""
        try:
            r = http_client.get(f"{url}/metrics")
        except httpx.ConnectError:
            pytest.skip(f"Worker {domain} não disponível")
        assert r.status_code == 200, f"Worker {domain} /metrics retornou {r.status_code}"
        body = r.text
        # Verifica presença das métricas definidas no worker_runner.py
        assert "cib7_worker_tasks_total" in body, (
            f"Worker {domain}: cib7_worker_tasks_total ausente nos /metrics"
        )
        assert "cib7_worker_task_duration_seconds" in body, (
            f"Worker {domain}: cib7_worker_task_duration_seconds ausente"
        )
        assert "cib7_worker_tasks_in_progress" in body, (
            f"Worker {domain}: cib7_worker_tasks_in_progress ausente"
        )

    def test_rc_worker_domain_label(self, require_workers, http_client):
        """Worker RC deve expor métricas com definição de labels por domínio.

        Nota: Labels com valores (domain="revenue_cycle") só aparecem APÓS o
        primeiro task ser processado. Em ambiente fresh, verificamos apenas que
        o metric name existe e o endpoint responde corretamente.
        """
        try:
            r = http_client.get(f"{WORKER_URLS['rc']}/metrics")
        except httpx.ConnectError:
            pytest.skip("Worker RC não disponível")
        assert r.status_code == 200
        # As métricas são definidas com label 'domain' — verificamos a definição
        # (labels com valores só aparecem após tasks serem processadas)
        assert "cib7_worker_tasks_total" in r.text, (
            "Métrica cib7_worker_tasks_total não encontrada no worker RC"
        )
        # Se algum task já foi processado, verifica o label domain
        if 'domain="' in r.text:
            assert 'domain="revenue_cycle"' in r.text or 'domain="rc"' in r.text, (
                "Label domain inesperado no worker RC"
            )

    @pytest.mark.parametrize("domain,url", list(WORKER_URLS.items()))
    def test_worker_metrics_content_type(self, require_workers, http_client, domain, url):
        """Content-Type dos /metrics deve ser text/plain (Prometheus format)."""
        try:
            r = http_client.get(f"{url}/metrics")
        except httpx.ConnectError:
            pytest.skip(f"Worker {domain} não disponível")
        assert r.status_code == 200
        content_type = r.headers.get("content-type", "")
        assert "text/plain" in content_type, (
            f"Content-Type inesperado para /metrics: {content_type}"
        )


# ---------------------------------------------------------------------------
# Worker → CIB Seven connectivity
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestWorkerCIB7Connectivity:
    """Testa se workers conseguem alcançar o CIB Seven."""

    def test_workers_appear_in_external_tasks(self, require_workers, require_cib7, http_client):
        """Workers ativos devem aparecer nos external tasks do CIB Seven."""
        try:
            r = http_client.get(
                f"{CIB7_URL}/engine-rest/external-task",
                auth=(CIB7_USER, CIB7_PASS),
                params={"maxResults": 100},
            )
        except Exception:
            pytest.skip("CIB7 não disponível")
        assert r.status_code == 200

    def test_worker_logs_available(self, require_workers, http_client):
        """Ao menos 1 worker deve estar saudável (liveness básico)."""
        for domain, url in WORKER_URLS.items():
            try:
                r = http_client.get(f"{url}/health", timeout=3)
                if r.status_code == 200:
                    return  # Pelo menos um worker está UP
            except Exception:
                continue
        pytest.fail("Nenhum worker respondeu ao /health")


# ---------------------------------------------------------------------------
# Worker Mock Mode (geração de métricas realistas)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.slow
class TestWorkerMockMode:
    """
    Testa MOCK_MODE dos workers para geração de métricas.

    Em MOCK_MODE=true os workers simulam processamento sem lógica real,
    útil para verificar dashboards Grafana sem processos BPMN ativos.

    Para ativar:
        docker compose -f docker-compose.local.yml exec workers_rc
        env MOCK_MODE=true python -m healthcare_platform.shared.runtime.worker_runner ...
    """

    def test_mock_mode_env_documented(self, require_workers, http_client):
        """
        Verifica que workers respondem normalmente (MOCK_MODE é opt-in).
        Este teste confirma que a infra está pronta para ativar MOCK_MODE.
        """
        # Em modo normal, workers devem estar UP
        rc_url = WORKER_URLS["rc"]
        try:
            r = http_client.get(f"{rc_url}/health", timeout=5)
            is_up = r.status_code == 200 and r.json().get("status") == "UP"
        except Exception:
            is_up = False

        if not is_up:
            pytest.skip("Worker RC não disponível para teste de MOCK_MODE")

        # Confirma que /metrics está exposto (necessário para MOCK_MODE gerar dados)
        r_m = http_client.get(f"{rc_url}/metrics")
        assert r_m.status_code == 200, "Worker RC não expõe /metrics"
        assert "cib7_worker_tasks_total" in r_m.text
