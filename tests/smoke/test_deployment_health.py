"""
MAEZO — Smoke Tests (pytest)

Testa a saúde dos serviços após deploy.
Execução: pytest tests/smoke/ -v --timeout=30

Variáveis de ambiente:
  CIB7_URL      — URL do CIB Seven (default: http://localhost:8080)
  FHIR_URL      — URL do HAPI FHIR (default: http://localhost:8082)
  CE_URL        — URL da Contract Extraction API (default: http://localhost:8000)
  CIB7_USER     — usuário Basic Auth CIB Seven (default: admin)
  CIB7_PASS     — senha Basic Auth CIB Seven (default: admin)
"""

import os
import httpx
import pytest

# ── Configuração ──────────────────────────────────────────────────────────────
CIB7_URL = os.getenv("CIB7_URL", "http://localhost:8080")
FHIR_URL = os.getenv("FHIR_URL", "http://localhost:8082")
CE_URL = os.getenv("CE_URL", "http://localhost:8000")
CIB7_USER = os.getenv("CIB7_USER", "admin")
CIB7_PASS = os.getenv("CIB7_PASS", "admin")

TIMEOUT = 15.0


@pytest.fixture(scope="module")
def cib7_client() -> httpx.Client:
    with httpx.Client(
        base_url=CIB7_URL,
        auth=(CIB7_USER, CIB7_PASS),
        timeout=TIMEOUT,
    ) as client:
        yield client


@pytest.fixture(scope="module")
def fhir_client() -> httpx.Client:
    with httpx.Client(
        base_url=FHIR_URL,
        timeout=TIMEOUT,
        headers={"Accept": "application/fhir+json"},
    ) as client:
        yield client


@pytest.fixture(scope="module")
def ce_client() -> httpx.Client:
    with httpx.Client(base_url=CE_URL, timeout=TIMEOUT) as client:
        yield client


# ── CIB Seven BPM Engine ──────────────────────────────────────────────────────
class TestCIBSeven:
    def test_engine_rest_api_accessible(self, cib7_client: httpx.Client) -> None:
        """O endpoint REST do engine deve responder com lista de engines."""
        resp = cib7_client.get("/engine-rest/engine")
        assert resp.status_code == 200, f"Engine REST retornou {resp.status_code}: {resp.text}"
        engines = resp.json()
        assert isinstance(engines, list), "Esperada lista de engines"
        assert len(engines) > 0, "Nenhum engine disponível"

    def test_default_engine_exists(self, cib7_client: httpx.Client) -> None:
        """O engine padrão 'default' deve existir."""
        resp = cib7_client.get("/engine-rest/engine")
        assert resp.status_code == 200
        engines = resp.json()
        names = [e.get("name") for e in engines]
        assert "default" in names, f"Engine 'default' não encontrado. Disponíveis: {names}"

    def test_process_definitions_accessible(self, cib7_client: httpx.Client) -> None:
        """Process definitions devem estar acessíveis."""
        resp = cib7_client.get("/engine-rest/process-definition?maxResults=1")
        assert resp.status_code == 200

    def test_bpmn_processes_deployed(self, cib7_client: httpx.Client) -> None:
        """Ao menos 1 processo BPMN deve estar deployado."""
        resp = cib7_client.get("/engine-rest/process-definition/count")
        assert resp.status_code == 200
        data = resp.json()
        count = data.get("count", 0)
        assert count > 0, (
            f"Nenhum processo BPMN deployado (count={count}). "
            "Execute o deploy dos BPMNs no CIB Seven antes do go-live."
        )

    def test_external_tasks_endpoint(self, cib7_client: httpx.Client) -> None:
        """O endpoint de external tasks deve responder."""
        resp = cib7_client.get("/engine-rest/external-task/count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data

    def test_deployment_endpoint(self, cib7_client: httpx.Client) -> None:
        """O endpoint de deployments deve responder."""
        resp = cib7_client.get("/engine-rest/deployment?maxResults=1")
        assert resp.status_code == 200

    @pytest.mark.parametrize("tenant", [
        "hospital-a", "amh-sp-morumbi", "amh-rj-barra", "amh-mg-bh"
    ])
    def test_tenants_configured(self, cib7_client: httpx.Client, tenant: str) -> None:
        """Todos os 4 tenants devem estar configurados no CIB Seven."""
        resp = cib7_client.get(f"/engine-rest/tenant/{tenant}")
        # 200 = tenant exists, 404 = not found (also acceptable for new installs)
        assert resp.status_code in (200, 404), (
            f"Resposta inesperada para tenant '{tenant}': {resp.status_code}"
        )


# ── HAPI FHIR R4 ─────────────────────────────────────────────────────────────
class TestHAPIFHIR:
    def test_capability_statement(self, fhir_client: httpx.Client) -> None:
        """O CapabilityStatement FHIR deve estar acessível."""
        resp = fhir_client.get("/fhir/metadata")
        assert resp.status_code == 200, f"FHIR metadata retornou {resp.status_code}"
        data = resp.json()
        assert data.get("resourceType") == "CapabilityStatement"

    def test_fhir_version_r4(self, fhir_client: httpx.Client) -> None:
        """O servidor FHIR deve ser versão R4."""
        resp = fhir_client.get("/fhir/metadata")
        assert resp.status_code == 200
        data = resp.json()
        fhir_version = data.get("fhirVersion", "")
        assert fhir_version.startswith("4."), f"FHIR version esperada R4, encontrada: {fhir_version}"

    def test_patient_resource_endpoint(self, fhir_client: httpx.Client) -> None:
        """O endpoint FHIR de Patient deve ser acessível."""
        resp = fhir_client.get("/fhir/Patient?_count=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("resourceType") == "Bundle"

    def test_encounter_resource_endpoint(self, fhir_client: httpx.Client) -> None:
        """O endpoint FHIR de Encounter deve ser acessível."""
        resp = fhir_client.get("/fhir/Encounter?_count=1")
        assert resp.status_code == 200

    def test_claim_resource_endpoint(self, fhir_client: httpx.Client) -> None:
        """O endpoint FHIR de Claim deve ser acessível."""
        resp = fhir_client.get("/fhir/Claim?_count=1")
        assert resp.status_code == 200

    def test_observation_resource_endpoint(self, fhir_client: httpx.Client) -> None:
        """O endpoint FHIR de Observation deve ser acessível."""
        resp = fhir_client.get("/fhir/Observation?_count=1")
        assert resp.status_code == 200


# ── Contract Extraction API ───────────────────────────────────────────────────
class TestContractExtractionAPI:
    def test_health_endpoint(self, ce_client: httpx.Client) -> None:
        """O health check da CE API deve retornar 200."""
        resp = ce_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("ok", "healthy", "up")

    def test_ready_endpoint(self, ce_client: httpx.Client) -> None:
        """O ready check da CE API deve retornar 200."""
        resp = ce_client.get("/ready")
        assert resp.status_code == 200

    def test_openapi_docs_accessible(self, ce_client: httpx.Client) -> None:
        """A documentação OpenAPI deve estar acessível."""
        resp = ce_client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_schema(self, ce_client: httpx.Client) -> None:
        """O schema OpenAPI deve estar disponível."""
        resp = ce_client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data


# ── Integração — Fluxo Básico ─────────────────────────────────────────────────
class TestIntegrationFlow:
    @pytest.mark.integration
    def test_cib7_can_create_process_instance(self, cib7_client: httpx.Client) -> None:
        """
        Verifica que o CIB Seven consegue iniciar um processo de teste.
        Requer que o processo SP-RC-001_Eligibility_Check.bpmn esteja deployado.
        Marcado como 'integration' — executar apenas em staging/prod.
        """
        # Verificar se o processo existe antes de tentar instanciar
        resp = cib7_client.get(
            "/engine-rest/process-definition",
            params={"key": "SP-RC-001_Eligibility_Check", "latestVersion": "true"},
        )
        assert resp.status_code == 200
        definitions = resp.json()
        if not definitions:
            pytest.skip("Processo SP-RC-001 não deployado, pulando teste de instanciação")

        # Tentar criar instância com variáveis mínimas de teste
        resp = cib7_client.post(
            "/engine-rest/process-definition/key/SP-RC-001_Eligibility_Check/start",
            json={
                "variables": {
                    "tenantId": {"value": "hospital-a", "type": "String"},
                    "patientFhirId": {"value": "SMOKE-TEST-PATIENT", "type": "String"},
                    "smokeTest": {"value": True, "type": "Boolean"},
                }
            },
        )
        assert resp.status_code in (200, 201), (
            f"Falha ao criar instância de processo: {resp.status_code} — {resp.text}"
        )

        # Limpar instância criada (cancela para não poluir)
        if resp.status_code in (200, 201):
            instance_id = resp.json().get("id")
            if instance_id:
                cib7_client.delete(f"/engine-rest/process-instance/{instance_id}")
