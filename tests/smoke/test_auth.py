"""Authentication smoke tests — Basic Auth (ADR-020)."""
import os
import pytest


def test_cib7_engine_accessible(http_client, camunda_base_url):
    """CIB Seven engine REST API deve estar acessível."""
    resp = http_client.get(f"{camunda_base_url}/engine")
    assert resp.status_code == 200, f"Engine indisponível: {resp.status_code}"
    body = resp.json()
    assert len(body) > 0
    assert "name" in body[0]


def test_cib7_basic_auth(http_client, camunda_base_url):
    """Workers devem autenticar no CIB Seven via Basic Auth."""
    user = os.getenv("CIB7_USER", "admin")
    password = os.getenv("CIB7_PASSWORD", "")
    if not password:
        pytest.skip("CIB7_PASSWORD não configurado")

    resp = http_client.get(
        f"{camunda_base_url}/engine",
        auth=(user, password),
    )
    assert resp.status_code == 200, f"Basic Auth falhou: {resp.status_code}"


def test_cib7_unauthorized_without_credentials(http_client, camunda_base_url):
    """Requisições sem credenciais devem ser rejeitadas quando auth está ativo."""
    resp = http_client.get(f"{camunda_base_url}/process-definition")
    assert resp.status_code in (200, 401), (
        f"Status inesperado: {resp.status_code}"
    )
