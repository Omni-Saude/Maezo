"""
test_observability.py — Testes E2E de observabilidade (Prometheus + Grafana).

Valida: saúde do Prometheus, targets ativos, métricas presentes,
        Grafana datasources provisionados, dashboards disponíveis.
Requer: prometheus (9090) e grafana (3000) rodando
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import PROMETHEUS_URL, GRAFANA_URL, TIMEOUT


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestPrometheus:
    """Testa o servidor Prometheus."""

    def test_healthy(self, require_prometheus, prometheus_client):
        """GET /-/healthy deve retornar 200."""
        r = prometheus_client.get("/-/healthy")
        assert r.status_code == 200
        assert "Healthy" in r.text or "healthy" in r.text.lower()

    def test_ready(self, require_prometheus, prometheus_client):
        """GET /-/ready deve retornar 200."""
        r = prometheus_client.get("/-/ready")
        assert r.status_code == 200

    def test_config_loaded(self, require_prometheus, prometheus_client):
        """GET /api/v1/status/config deve retornar configuração carregada."""
        r = prometheus_client.get("/api/v1/status/config")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        # Prometheus retorna a config em data.yaml como string YAML
        yaml_config = data.get("data", {}).get("yaml", "")
        assert len(yaml_config) > 0, "Config YAML vazia"
        assert "scrape_configs" in yaml_config or "global:" in yaml_config

    def test_targets_defined(self, require_prometheus, prometheus_client):
        """GET /api/v1/targets deve retornar targets definidos."""
        r = prometheus_client.get("/api/v1/targets")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"

        active_targets = data.get("data", {}).get("activeTargets", [])
        assert len(active_targets) > 0, "Nenhum target ativo encontrado"

        jobs = {t["labels"].get("job", "") for t in active_targets}
        assert len(jobs) >= 1, f"Nenhum job encontrado nos targets"

    def test_target_maezo_workers_defined(self, require_prometheus, prometheus_client):
        """Job maezo_workers deve estar configurado nos targets."""
        r = prometheus_client.get("/api/v1/targets")
        data = r.json()
        active = data.get("data", {}).get("activeTargets", [])
        all_jobs = [t["labels"].get("job", "") for t in active]
        assert "maezo_workers" in all_jobs, (
            f"Job 'maezo_workers' não encontrado. Jobs: {set(all_jobs)}"
        )

    def test_prometheus_self_monitoring(self, require_prometheus, prometheus_client):
        """Prometheus deve se auto-monitorar (job=prometheus)."""
        r = prometheus_client.get("/api/v1/targets")
        data = r.json()
        active = data.get("data", {}).get("activeTargets", [])
        prom_targets = [t for t in active if t["labels"].get("job") == "prometheus"]
        assert len(prom_targets) >= 1, "Target prometheus self-monitoring não encontrado"
        assert prom_targets[0]["health"] == "up", (
            f"Prometheus self-monitoring não está UP: {prom_targets[0]['health']}"
        )

    def test_postgres_target_defined(self, require_prometheus, prometheus_client):
        """Job postgres deve estar configurado."""
        r = prometheus_client.get("/api/v1/targets")
        data = r.json()
        active = data.get("data", {}).get("activeTargets", [])
        jobs = {t["labels"].get("job", "") for t in active}
        assert "postgres" in jobs, f"Job 'postgres' não encontrado. Jobs: {jobs}"

    def test_kafka_target_defined(self, require_prometheus, prometheus_client):
        """Job kafka deve estar configurado."""
        r = prometheus_client.get("/api/v1/targets")
        data = r.json()
        active = data.get("data", {}).get("activeTargets", [])
        jobs = {t["labels"].get("job", "") for t in active}
        assert "kafka" in jobs, f"Job 'kafka' não encontrado. Jobs: {jobs}"

    def test_prometheus_metrics_endpoint(self, require_prometheus, prometheus_client):
        """GET /metrics deve expor métricas do próprio Prometheus."""
        r = prometheus_client.get("/metrics")
        assert r.status_code == 200
        body = r.text
        assert "prometheus_build_info" in body or "go_gc_duration_seconds" in body

    def test_query_up_metric(self, require_prometheus, prometheus_client):
        """Query da métrica 'up' deve retornar resultados."""
        r = prometheus_client.get(
            "/api/v1/query",
            params={"query": "up"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        results = data.get("data", {}).get("result", [])
        assert len(results) > 0, "Métrica 'up' não tem resultados"

    def test_postgres_up_metric(self, require_prometheus, prometheus_client):
        """Métrica pg_up deve estar disponível e igual a 1."""
        r = prometheus_client.get(
            "/api/v1/query",
            params={"query": "pg_up"},
        )
        assert r.status_code == 200
        data = r.json()
        results = data.get("data", {}).get("result", [])
        if len(results) == 0:
            pytest.skip("pg_up ainda não disponível (postgres_exporter pode estar iniciando)")
        # Pelo menos um resultado deve ser 1 (banco UP)
        values = [float(r_["value"][1]) for r_ in results]
        assert any(v == 1.0 for v in values), f"pg_up não é 1 em nenhum resultado: {values}"


# ---------------------------------------------------------------------------
# Grafana
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestGrafana:
    """Testa o servidor Grafana."""

    def test_api_health(self, require_grafana, grafana_client):
        """GET /api/health deve retornar status ok."""
        r = grafana_client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("database") == "ok", f"Grafana DB não OK: {data}"

    def test_datasources_provisioned(self, require_grafana, grafana_client):
        """Datasource Prometheus deve estar provisionado."""
        r = grafana_client.get("/api/datasources")
        assert r.status_code == 200
        datasources = r.json()
        assert len(datasources) >= 1, "Nenhum datasource encontrado"

        names = [ds.get("name", "") for ds in datasources]
        assert "Prometheus" in names, f"Datasource 'Prometheus' não encontrado. Encontrados: {names}"

    def test_prometheus_datasource_uid(self, require_grafana, grafana_client):
        """Datasource Prometheus deve ter UID correto (prometheus-maezo)."""
        r = grafana_client.get("/api/datasources")
        datasources = r.json()
        prom_ds = next((ds for ds in datasources if ds.get("name") == "Prometheus"), None)
        if prom_ds is None:
            pytest.skip("Datasource Prometheus não encontrado")
        assert prom_ds.get("uid") == "prometheus-maezo", (
            f"UID inesperado: {prom_ds.get('uid')}"
        )
        assert prom_ds.get("isDefault") is True, "Prometheus não é o datasource padrão"

    def test_dashboards_provisioned(self, require_grafana, grafana_client):
        """Dashboard MAEZO Workers Overview deve estar provisionado."""
        r = grafana_client.get("/api/search", params={"type": "dash-db"})
        assert r.status_code == 200
        dashboards = r.json()
        assert len(dashboards) >= 1, "Nenhum dashboard encontrado"

        titles = [d.get("title", "") for d in dashboards]
        assert any("MAEZO" in t for t in titles), (
            f"Dashboard MAEZO não encontrado. Dashboards: {titles}"
        )

    def test_dashboard_uid_accessible(self, require_grafana, grafana_client):
        """Dashboard com UID 'maezo-workers-overview' deve estar acessível."""
        r = grafana_client.get("/api/dashboards/uid/maezo-workers-overview")
        if r.status_code == 404:
            pytest.skip("Dashboard maezo-workers-overview não provisionado ainda")
        assert r.status_code == 200, f"Erro ao acessar dashboard: {r.status_code}"
        data = r.json()
        assert "dashboard" in data
        assert data["dashboard"].get("uid") == "maezo-workers-overview"

    def test_prometheus_datasource_is_reachable(self, require_grafana, grafana_client):
        """Grafana deve conseguir alcançar o Prometheus (proxy test)."""
        r = grafana_client.get("/api/datasources/proxy/uid/prometheus-maezo/-/healthy")
        # Pode retornar 200 ou outro status dependendo da versão
        # O importante é não retornar 502/503 (que indicaria falha de conexão)
        assert r.status_code not in (502, 503), (
            f"Grafana não consegue alcançar Prometheus: {r.status_code}"
        )

    def test_grafana_orgs(self, require_grafana, grafana_client):
        """Deve existir a organização padrão do Grafana."""
        r = grafana_client.get("/api/orgs/1")
        assert r.status_code == 200
        org = r.json()
        assert org.get("id") == 1
