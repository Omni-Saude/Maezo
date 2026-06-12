"""
test_infrastructure.py — Testes E2E de infraestrutura base.

Valida: PostgreSQL, Kafka, Debezium, exporters de métricas.
Requer: docker compose -f docker-compose.local.yml up -d (serviços de infra)
"""
from __future__ import annotations

import pytest
import httpx
import asyncpg

from tests.e2e.conftest import (
    PG_DSN,
    DEBEZIUM_URL,
    TIMEOUT,
)


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestPostgreSQL:
    """Testa conectividade e integridade do PostgreSQL local."""

    @pytest.mark.asyncio
    async def test_connection(self):
        """Deve conectar ao PostgreSQL e executar uma query simples."""
        conn = await asyncpg.connect(PG_DSN, timeout=TIMEOUT)
        try:
            version = await conn.fetchval("SELECT version()")
            assert "PostgreSQL 16" in version, f"Versão inesperada: {version}"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_databases_exist(self):
        """Todos os bancos necessários devem existir."""
        conn = await asyncpg.connect(PG_DSN, timeout=TIMEOUT)
        try:
            rows = await conn.fetch(
                "SELECT datname FROM pg_database WHERE datname IN "
                "('cibseven', 'hapi_fhir', 'maestro') ORDER BY datname"
            )
            found = {r["datname"] for r in rows}
            assert found == {"cibseven", "hapi_fhir", "maestro"}, (
                f"Bancos ausentes. Encontrados: {found}"
            )
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_maestro_tables_exist(self):
        """Tabelas de negócio no banco maestro devem existir."""
        dsn = PG_DSN.replace("/cibseven", "/maestro")
        conn = await asyncpg.connect(dsn, timeout=TIMEOUT)
        try:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename IN ('webhook_idempotency', 'kafka_dead_letter')"
            )
            found = {r["tablename"] for r in rows}
            assert "webhook_idempotency" in found, "Tabela webhook_idempotency não encontrada"
            assert "kafka_dead_letter" in found, "Tabela kafka_dead_letter não encontrada"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_uuid_ossp_extension(self):
        """Extensão uuid-ossp deve estar instalada no banco maestro."""
        dsn = PG_DSN.replace("/cibseven", "/maestro")
        conn = await asyncpg.connect(dsn, timeout=TIMEOUT)
        try:
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM pg_extension WHERE extname = 'uuid-ossp'"
            )
            assert result >= 1, "Extensão uuid-ossp não encontrada"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_webhook_idempotency_insert(self):
        """Deve ser possível inserir e recuperar um registro de idempotência."""
        import uuid
        dsn = PG_DSN.replace("/cibseven", "/maestro")
        conn = await asyncpg.connect(dsn, timeout=TIMEOUT)
        try:
            key = f"test-{uuid.uuid4()}"
            await conn.execute(
                """
                INSERT INTO webhook_idempotency
                    (idempotency_key, system, event_type, status)
                VALUES ($1, 'e2e_test', 'test.event', 'received')
                """,
                key,
            )
            row = await conn.fetchrow(
                "SELECT * FROM webhook_idempotency WHERE idempotency_key = $1", key
            )
            assert row is not None
            assert row["system"] == "e2e_test"
            assert row["status"] == "received"
        finally:
            # Cleanup
            await conn.execute(
                "DELETE FROM webhook_idempotency WHERE system = 'e2e_test'"
            )
            await conn.close()


# ---------------------------------------------------------------------------
# Debezium
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestDebezium:
    """Testa Debezium Kafka Connect."""

    def test_connectors_endpoint(self, require_debezium, http_client):
        """Endpoint /connectors deve retornar lista (pode estar vazia em local)."""
        r = http_client.get(f"{DEBEZIUM_URL}/connectors")
        assert r.status_code == 200, f"Status inesperado: {r.status_code}"
        data = r.json()
        assert isinstance(data, list), f"Esperado lista, recebido: {type(data)}"

    def test_version_endpoint(self, require_debezium, http_client):
        """Endpoint raiz deve retornar versão do Debezium."""
        r = http_client.get(DEBEZIUM_URL)
        assert r.status_code == 200
        data = r.json()
        assert "version" in data, f"'version' ausente na resposta: {data}"

    def test_plugins_available(self, require_debezium, http_client):
        """Plugins de conector devem estar listados."""
        r = http_client.get(f"{DEBEZIUM_URL}/connector-plugins")
        assert r.status_code == 200
        plugins = r.json()
        assert len(plugins) > 0, "Nenhum plugin encontrado"
        # Verifica se plugin PostgreSQL está disponível (incluído no Debezium 2.7)
        class_names = [p.get("class", "") for p in plugins]
        pg_connector = any("postgresql" in c.lower() for c in class_names)
        assert pg_connector, f"PostgreSQL connector não encontrado. Plugins: {class_names[:5]}"


# ---------------------------------------------------------------------------
# Kafka Exporter
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestKafkaExporter:
    """Testa kafka-exporter Prometheus scrape."""

    def test_metrics_endpoint(self, http_client):
        """Deve expor métricas Prometheus do Kafka."""
        try:
            r = http_client.get("http://localhost:9308/metrics", timeout=TIMEOUT)
        except httpx.ConnectError:
            pytest.skip("kafka_exporter não disponível")
        assert r.status_code == 200
        body = r.text
        # Verifica presença de métricas básicas do Kafka
        assert "kafka_brokers" in body or "kafka_topic" in body, (
            "Métricas Kafka ausentes no endpoint"
        )


# ---------------------------------------------------------------------------
# PostgreSQL Exporter
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestPostgresExporter:
    """Testa postgres-exporter Prometheus scrape."""

    def test_metrics_endpoint(self, http_client):
        """Deve expor métricas Prometheus do PostgreSQL."""
        try:
            r = http_client.get("http://localhost:9187/metrics", timeout=TIMEOUT)
        except httpx.ConnectError:
            pytest.skip("postgres_exporter não disponível")
        assert r.status_code == 200
        body = r.text
        assert "pg_up" in body, "Métrica pg_up ausente"
        # pg_up{} 1 significa que está conectado ao PostgreSQL
        assert "pg_up 1" in body or 'pg_up{' in body, (
            "PostgreSQL Exporter não conectado ao banco"
        )
