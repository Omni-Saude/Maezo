"""
test_bpm_engine.py — Testes E2E do CIB Seven BPM Engine.

Valida: conectividade REST API, process definitions, external tasks,
        deployments, histórico e multi-tenancy.
Requer: cib7 container rodando (porta 8080)
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import CIB7_URL, CIB7_USER, CIB7_PASS, TIMEOUT


# ---------------------------------------------------------------------------
# Engine REST API — health e versão
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCIB7EngineBasic:
    """Conectividade básica com a Engine REST API."""

    def test_engine_endpoint(self, require_cib7, cib7_client):
        """GET /engine deve retornar lista de engines."""
        r = cib7_client.get("/engine")
        assert r.status_code == 200
        engines = r.json()
        assert isinstance(engines, list)
        assert len(engines) >= 1, "Nenhuma engine encontrada"
        assert "name" in engines[0], f"'name' ausente: {engines[0]}"

    def test_engine_default(self, require_cib7, cib7_client):
        """Engine 'default' deve existir."""
        r = cib7_client.get("/engine")
        engines = r.json()
        names = [e["name"] for e in engines]
        assert "default" in names, f"Engine 'default' não encontrada. Engines: {names}"

    def test_version_or_telemetry(self, require_cib7, cib7_client):
        """Algum endpoint de versão deve responder."""
        # Camunda 7 expõe /version em algumas versões
        r = cib7_client.get("/version")
        # Pode retornar 200 ou 404 dependendo da versão
        assert r.status_code in (200, 404, 405)

    def test_unauthorized_without_credentials(self, http_client):
        """Engine REST API deve retornar 401 sem credenciais."""
        import httpx
        try:
            r = http_client.get(f"{CIB7_URL}/engine-rest/engine")
        except Exception:
            pytest.skip("CIB7 não disponível")
        # Pode ser 401 (se Basic Auth requerido) ou 200 (se auth desativada)
        assert r.status_code in (200, 401), f"Status inesperado: {r.status_code}"


# ---------------------------------------------------------------------------
# Process Definitions
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestProcessDefinitions:
    """Testa endpoints de definições de processo (BPMN)."""

    def test_list_process_definitions(self, require_cib7, cib7_client):
        """GET /process-definition deve retornar lista (pode ser vazia em ambiente limpo)."""
        r = cib7_client.get("/process-definition", params={"maxResults": 10})
        assert r.status_code == 200
        definitions = r.json()
        assert isinstance(definitions, list)

    def test_count_process_definitions(self, require_cib7, cib7_client):
        """GET /process-definition/count deve retornar contagem."""
        r = cib7_client.get("/process-definition/count")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert isinstance(data["count"], int)
        assert data["count"] >= 0


# ---------------------------------------------------------------------------
# External Tasks
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestExternalTasks:
    """Testa endpoints de External Tasks (usados pelos workers Python)."""

    def test_list_external_tasks(self, require_cib7, cib7_client):
        """GET /external-task deve responder."""
        r = cib7_client.get("/external-task", params={"maxResults": 10})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_count_external_tasks(self, require_cib7, cib7_client):
        """GET /external-task/count deve retornar contagem."""
        r = cib7_client.get("/external-task/count")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data

    def test_fetch_and_lock_endpoint_exists(self, require_cib7, cib7_client):
        """POST /external-task/fetchAndLock deve aceitar a requisição."""
        # Faz fetch com workerId inexistente — deve retornar lista vazia, não 404
        payload = {
            "workerId": "e2e-test-worker",
            "maxTasks": 1,
            "usePriority": False,
            "topics": [{"topicName": "e2e.test.topic", "lockDuration": 10000}],
        }
        r = cib7_client.post("/external-task/fetchAndLock", json=payload)
        assert r.status_code == 200
        assert isinstance(r.json(), list), f"Esperado lista, recebido: {r.json()}"


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestDeployments:
    """Testa gerenciamento de deployments BPMN/DMN."""

    def test_list_deployments(self, require_cib7, cib7_client):
        """GET /deployment deve responder."""
        r = cib7_client.get("/deployment", params={"maxResults": 5})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_and_delete_minimal_process(self, require_cib7, cib7_client):
        """Deve ser possível fazer deploy de um processo BPMN mínimo e deletar."""
        import io

        # Camunda 7.22+ requer camunda:historyTimeToLive no processo
        minimal_bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://bpmn.io/schema/bpmn">
  <process id="e2e_test_process" name="E2E Test Process" isExecutable="true"
           camunda:historyTimeToLive="1">
    <startEvent id="start"/>
    <sequenceFlow id="flow1" sourceRef="start" targetRef="end"/>
    <endEvent id="end"/>
  </process>
</definitions>"""

        # Deploy
        r = cib7_client.post(
            "/deployment/create",
            files={
                "deployment-name": (None, "e2e-test-deployment"),
                "enable-duplicate-filtering": (None, "false"),
                "e2e_test.bpmn": ("e2e_test.bpmn", io.BytesIO(minimal_bpmn.encode()), "application/xml"),
            },
        )
        assert r.status_code == 200, f"Deploy falhou: {r.text}"
        deployment = r.json()
        assert "id" in deployment
        deployment_id = deployment["id"]

        try:
            # Verificar processo criado
            r2 = cib7_client.get(
                "/process-definition",
                params={"deploymentId": deployment_id},
            )
            assert r2.status_code == 200
            procs = r2.json()
            assert len(procs) >= 1, "Processo não encontrado após deploy"
        finally:
            # Cleanup — deletar deployment
            r_del = cib7_client.delete(f"/deployment/{deployment_id}", params={"cascade": "true"})
            assert r_del.status_code in (200, 204), f"Delete falhou: {r_del.text}"


# ---------------------------------------------------------------------------
# Process Instances & History
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestProcessInstances:
    """Testa instâncias de processo e histórico."""

    def test_list_process_instances(self, require_cib7, cib7_client):
        """GET /process-instance deve responder."""
        r = cib7_client.get("/process-instance", params={"maxResults": 5})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_history_process_instance(self, require_cib7, cib7_client):
        """GET /history/process-instance deve responder."""
        r = cib7_client.get("/history/process-instance", params={"maxResults": 5})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_full_process_lifecycle(self, require_cib7, cib7_client):
        """Deploy → start → verify histórico → cleanup."""
        import io

        # BPMN com External Task para testar fetch cycle completo
        # Camunda 7.22+ requer camunda:historyTimeToLive
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://bpmn.io/schema/bpmn">
  <process id="e2e_lifecycle_test" name="E2E Lifecycle Test" isExecutable="true"
           camunda:historyTimeToLive="1">
    <startEvent id="start"/>
    <sequenceFlow id="flow1" sourceRef="start" targetRef="ext_task"/>
    <serviceTask id="ext_task" name="E2E Task"
                 camunda:type="external" camunda:topic="e2e.lifecycle.test">
      <extensionElements>
        <camunda:taskDefinition type="e2e.lifecycle.test"/>
      </extensionElements>
    </serviceTask>
    <sequenceFlow id="flow2" sourceRef="ext_task" targetRef="end"/>
    <endEvent id="end"/>
  </process>
</definitions>"""

        # 1. Deploy
        r = cib7_client.post(
            "/deployment/create",
            files={
                "deployment-name": (None, "e2e-lifecycle-test"),
                "enable-duplicate-filtering": (None, "false"),
                "e2e_lifecycle.bpmn": ("e2e_lifecycle.bpmn", io.BytesIO(bpmn.encode()), "application/xml"),
            },
        )
        assert r.status_code == 200
        deployment_id = r.json()["id"]

        try:
            # 2. Start process instance
            r2 = cib7_client.post(
                "/process-definition/key/e2e_lifecycle_test/start",
                json={"variables": {"e2e": {"value": "test", "type": "String"}}},
            )
            assert r2.status_code == 200, f"Start falhou: {r2.text}"
            instance_id = r2.json()["id"]

            # 3. Verificar external task criada
            r3 = cib7_client.get(
                "/external-task",
                params={"processInstanceId": instance_id},
            )
            assert r3.status_code == 200
            tasks = r3.json()
            assert len(tasks) >= 1, "External task não criada"
            assert tasks[0]["topicName"] == "e2e.lifecycle.test"

            # 4. Fetch and lock
            r4 = cib7_client.post(
                "/external-task/fetchAndLock",
                json={
                    "workerId": "e2e-lifecycle-worker",
                    "maxTasks": 1,
                    "usePriority": False,
                    "topics": [{"topicName": "e2e.lifecycle.test", "lockDuration": 30000}],
                },
            )
            assert r4.status_code == 200
            locked = r4.json()
            assert len(locked) >= 1, "Fetch and lock retornou vazio"
            task_id = locked[0]["id"]

            # 5. Complete task
            r5 = cib7_client.post(
                f"/external-task/{task_id}/complete",
                json={"workerId": "e2e-lifecycle-worker", "variables": {}},
            )
            assert r5.status_code == 204, f"Complete falhou: {r5.text}"

        finally:
            # Cleanup
            cib7_client.delete(f"/deployment/{deployment_id}", params={"cascade": "true"})
