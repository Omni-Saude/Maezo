"""DMN evaluation smoke tests."""
import pytest

SIMPLE_DMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
  id="smoke_dmn" name="Smoke Test DMN" namespace="http://camunda.org/schema/1.0/dmn">
  <decision id="smoke_decision" name="Smoke Decision">
    <decisionTable id="smoke_table" hitPolicy="FIRST">
      <input id="input1" label="Score">
        <inputExpression id="inputExp1" typeRef="integer">
          <text>score</text>
        </inputExpression>
      </input>
      <output id="output1" label="Result" name="result" typeRef="string"/>
      <rule id="rule1">
        <inputEntry id="ie1"><text>&gt;= 70</text></inputEntry>
        <outputEntry id="oe1"><text>"PASS"</text></outputEntry>
      </rule>
      <rule id="rule2">
        <inputEntry id="ie2"><text>&lt; 70</text></inputEntry>
        <outputEntry id="oe2"><text>"FAIL"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>"""


def test_deploy_dmn_table(http_client, camunda_base_url):
    """Should deploy a DMN decision table."""
    resp = http_client.post(
        f"{camunda_base_url}/deployment/create",
        data={"tenant-id": "austa-hospital", "deployment-name": "smoke-dmn"},
        files={"upload": ("smoke.dmn", SIMPLE_DMN, "application/octet-stream")},
    )
    assert resp.status_code == 200


def test_evaluate_decision(http_client, camunda_base_url):
    """Should evaluate DMN decision and return expected output."""
    resp = http_client.get(
        f"{camunda_base_url}/decision-definition",
        params={"key": "smoke_decision", "tenantIdIn": "austa-hospital", "latestVersion": "true"},
    )
    if resp.status_code != 200 or not resp.json():
        pytest.skip("smoke_decision not deployed")

    dec_def = resp.json()[0]
    resp = http_client.post(
        f"{camunda_base_url}/decision-definition/{dec_def['id']}/evaluate",
        json={"variables": {"score": {"value": 85, "type": "Integer"}}},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    assert results[0].get("result", {}).get("value") == "PASS"
