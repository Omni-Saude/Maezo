"""BPMN deployment smoke tests."""
import pytest

HELLO_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  id="Definitions_smoke" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="smoke_test_process" isExecutable="true">
    <bpmn:startEvent id="start"/>
    <bpmn:endEvent id="end"/>
    <bpmn:sequenceFlow id="flow1" sourceRef="start" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>"""


def test_deploy_simple_process(http_client, camunda_base_url):
    """Should deploy a simple BPMN process."""
    resp = http_client.post(
        f"{camunda_base_url}/deployment/create",
        data={"tenant-id": "austa-hospital", "deployment-name": "smoke-test"},
        files={"upload": ("smoke.bpmn", HELLO_BPMN, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body


def test_start_process_instance(http_client, camunda_base_url):
    """Should start a process instance."""
    # First find the deployed process definition
    resp = http_client.get(
        f"{camunda_base_url}/process-definition",
        params={"key": "smoke_test_process", "tenantIdIn": "austa-hospital", "latestVersion": "true"},
    )
    if resp.status_code != 200 or not resp.json():
        pytest.skip("smoke_test_process not deployed")

    proc_def = resp.json()[0]
    resp = http_client.post(
        f"{camunda_base_url}/process-definition/{proc_def['id']}/start",
        json={},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("id") is not None
