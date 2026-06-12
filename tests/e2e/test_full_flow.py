"""
test_full_flow.py — Testes E2E de fluxo completo (end-to-end).

Valida: integração entre serviços — CIB Seven, FHIR, Workers.
Simula um ciclo completo de processo hospitalar:
  1. Criar paciente no FHIR
  2. Fazer deploy de processo BPMN
  3. Iniciar processo com referência ao paciente
  4. Workers fazem fetchAndLock do External Task
  5. Workers completam o task
  6. Verificar histórico no CIB Seven

Requer: todos os serviços rodando (cib7, hapi_fhir, workers)
"""
from __future__ import annotations

import io
import time
import uuid

import httpx
import pytest

from tests.e2e.conftest import (
    CIB7_URL,
    CIB7_USER,
    CIB7_PASS,
    FHIR_URL,
    WORKER_URLS,
    TIMEOUT,
)


# ---------------------------------------------------------------------------
# Integração CIB Seven + FHIR
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.integration
class TestCIB7FHIRIntegration:
    """Testa integração entre CIB Seven e HAPI FHIR."""

    def test_patient_reference_in_process(
        self, require_cib7, require_fhir, cib7_client, fhir_client
    ):
        """
        Fluxo: criar paciente FHIR → iniciar processo BPMN com ID do paciente → verificar.
        """
        # 1. Criar paciente no FHIR
        patient_id = f"e2e-{uuid.uuid4().hex[:8]}"
        patient = {
            "resourceType": "Patient",
            "id": patient_id,
            "name": [{"use": "official", "family": "FluxoTeste", "given": ["E2E"]}],
            "birthDate": "1990-01-01",
        }
        r_p = fhir_client.put(f"/Patient/{patient_id}", json=patient)
        assert r_p.status_code in (200, 201), f"Falha ao criar Patient: {r_p.text[:200]}"

        # 2. Verificar que paciente existe no FHIR
        r_get = fhir_client.get(f"/Patient/{patient_id}")
        assert r_get.status_code == 200
        assert r_get.json()["id"] == patient_id

        # 3. Deploy de processo que referencia paciente FHIR
        bpmn = f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://bpmn.io/schema/bpmn">
  <process id="e2e_fhir_integration_{patient_id[:8]}" isExecutable="true"
           camunda:historyTimeToLive="1">
    <startEvent id="start"/>
    <sequenceFlow id="f1" sourceRef="start" targetRef="task"/>
    <serviceTask id="task" name="Process Patient"
                 camunda:type="external"
                 camunda:topic="e2e.fhir.integration.test">
    </serviceTask>
    <sequenceFlow id="f2" sourceRef="task" targetRef="end"/>
    <endEvent id="end"/>
  </process>
</definitions>"""

        r_deploy = cib7_client.post(
            "/deployment/create",
            files={
                "deployment-name": (None, f"e2e-fhir-int-{patient_id[:8]}"),
                "enable-duplicate-filtering": (None, "false"),
                "e2e_fhir.bpmn": ("e2e_fhir.bpmn", io.BytesIO(bpmn.encode()), "application/xml"),
            },
        )
        assert r_deploy.status_code == 200, f"Deploy falhou: {r_deploy.text[:200]}"
        deployment_id = r_deploy.json()["id"]

        try:
            # 4. Iniciar processo com variável fhir_patient_id
            r_start = cib7_client.post(
                f"/process-definition/key/e2e_fhir_integration_{patient_id[:8]}/start",
                json={
                    "variables": {
                        "fhir_patient_id": {"value": patient_id, "type": "String"},
                        "fhir_server_url": {"value": f"{FHIR_URL}/fhir", "type": "String"},
                    }
                },
            )
            assert r_start.status_code == 200, f"Start falhou: {r_start.text[:200]}"
            instance_id = r_start.json()["id"]

            # 5. Verificar external task criada com tópico correto
            r_tasks = cib7_client.get(
                "/external-task",
                params={"processInstanceId": instance_id},
            )
            assert r_tasks.status_code == 200
            tasks = r_tasks.json()
            assert len(tasks) == 1, f"Esperado 1 task, recebido: {len(tasks)}"
            assert tasks[0]["topicName"] == "e2e.fhir.integration.test"

            # 6. Simular worker: fetch and lock → complete
            r_lock = cib7_client.post(
                "/external-task/fetchAndLock",
                json={
                    "workerId": "e2e-fhir-test-worker",
                    "maxTasks": 1,
                    "usePriority": False,
                    "topics": [
                        {"topicName": "e2e.fhir.integration.test", "lockDuration": 30000}
                    ],
                },
            )
            assert r_lock.status_code == 200
            locked = r_lock.json()
            assert len(locked) == 1

            task_id = locked[0]["id"]
            # Verificar que variável fhir_patient_id está na task
            task_vars = locked[0].get("variables", {})
            assert "fhir_patient_id" in task_vars, (
                f"Variável fhir_patient_id ausente na task: {list(task_vars.keys())}"
            )
            assert task_vars["fhir_patient_id"]["value"] == patient_id

            # 7. Completar task simulando worker bem-sucedido
            r_complete = cib7_client.post(
                f"/external-task/{task_id}/complete",
                json={
                    "workerId": "e2e-fhir-test-worker",
                    "variables": {
                        "fhir_operation_status": {"value": "SUCCESS", "type": "String"},
                        "processed_patient_id": {"value": patient_id, "type": "String"},
                    },
                },
            )
            assert r_complete.status_code == 204, f"Complete falhou: {r_complete.text}"

            # 8. Verificar processo no histórico
            r_hist = cib7_client.get(
                "/history/process-instance",
                params={"processInstanceId": instance_id},
            )
            assert r_hist.status_code == 200
            history = r_hist.json()
            assert len(history) >= 1
            state = history[0].get("state")
            assert state in ("COMPLETED", "ACTIVE"), f"Estado inesperado: {state}"

        finally:
            cib7_client.delete(f"/deployment/{deployment_id}", params={"cascade": "true"})


# ---------------------------------------------------------------------------
# Multi-tenancy flow
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.integration
class TestMultiTenancyFlow:
    """
    Testa isolamento multi-tenancy.

    NOTA: Camunda Run (substituto local do CIBSeven) não tem multi-tenancy
    habilitado por padrão no modo OSS. Estes testes adaptam-se ao modo disponível.
    """

    def test_engine_responds_to_tenant_query(self, require_cib7, cib7_client):
        """Endpoint de tenant deve responder (mesmo que vazio em local)."""
        r = cib7_client.get("/tenant", params={"maxResults": 10})
        assert r.status_code == 200
        tenants = r.json()
        assert isinstance(tenants, list)
        # Em modo OSS (Camunda Run), tenants podem estar vazios
        # Em CIBSeven Enterprise, haveria hospital-a, amh-sp-morumbi, etc.

    def test_process_definition_accessible_without_tenant(self, require_cib7, cib7_client):
        """Process definitions devem ser acessíveis sem tenant (modo OSS local)."""
        r = cib7_client.get("/process-definition/count")
        assert r.status_code == 200
        assert "count" in r.json()


# ---------------------------------------------------------------------------
# CDC stack smoke test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.integration
class TestCdcStack:
    """
    Testa se a stack de CDC está operacional.
    Verifica conectividade sem produzir mensagens reais.
    """

    def test_debezium_connector_slot_available(self, http_client):
        """Debezium deve estar pronto para registrar conectores."""
        try:
            r = http_client.get("http://localhost:8083/connector-plugins", timeout=TIMEOUT)
        except httpx.ConnectError:
            pytest.skip("Debezium não disponível")
        assert r.status_code == 200
        plugins = r.json()
        assert len(plugins) > 0


# ---------------------------------------------------------------------------
# Database integration
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.integration
async def test_idempotency_full_cycle():
    """
    Fluxo completo de idempotência de webhook:
    insert → query → mark processed → verify.
    """
    import asyncpg
    from tests.e2e.conftest import PG_DSN

    dsn = PG_DSN.replace("/cibseven", "/maestro")
    try:
        conn = await asyncpg.connect(dsn, timeout=TIMEOUT)
    except Exception:
        pytest.skip("PostgreSQL não disponível")

    key = f"e2e-idempotency-{uuid.uuid4()}"
    try:
        # Insert
        await conn.execute(
            """
            INSERT INTO webhook_idempotency
                (idempotency_key, system, event_type, status)
            VALUES ($1, 'e2e_full_cycle', 'test.webhook', 'received')
            """,
            key,
        )

        # Verify exists
        row = await conn.fetchrow(
            "SELECT * FROM webhook_idempotency WHERE idempotency_key = $1", key
        )
        assert row is not None
        assert row["status"] == "received"
        assert row["processed_at"] is None

        # Mark as processed
        await conn.execute(
            """
            UPDATE webhook_idempotency
            SET status = 'processed', processed_at = NOW()
            WHERE idempotency_key = $1
            """,
            key,
        )

        # Verify processed
        row2 = await conn.fetchrow(
            "SELECT * FROM webhook_idempotency WHERE idempotency_key = $1", key
        )
        assert row2["status"] == "processed"
        assert row2["processed_at"] is not None

        # Try duplicate insert (should fail with unique constraint)
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO webhook_idempotency
                    (idempotency_key, system, event_type, status)
                VALUES ($1, 'e2e_full_cycle', 'test.webhook', 'received')
                """,
                key,
            )

    finally:
        await conn.execute(
            "DELETE FROM webhook_idempotency WHERE idempotency_key = $1", key
        )
        await conn.close()
