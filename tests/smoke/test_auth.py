"""Authentication smoke tests."""
import pytest


def test_keycloak_realm_exists(http_client, keycloak_url):
    """Keycloak austa-bpm realm should exist."""
    resp = http_client.get(f"{keycloak_url}/auth/realms/austa-bpm")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("realm") == "austa-bpm"


def test_worker_service_account_token(http_client, keycloak_url):
    """Worker service account should be able to obtain a token."""
    import os
    client_id = os.getenv("WORKER_CLIENT_ID", "maestro-workers")
    client_secret = os.getenv("WORKER_CLIENT_SECRET", "")
    if not client_secret:
        pytest.skip("WORKER_CLIENT_SECRET not set")

    resp = http_client.post(
        f"{keycloak_url}/auth/realms/austa-bpm/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
