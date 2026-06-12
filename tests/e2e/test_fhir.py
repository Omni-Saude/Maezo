"""
test_fhir.py — Testes E2E do HAPI FHIR R4.

Valida: capability statement, operações CRUD em recursos clínicos,
        busca, validação e compatibilidade com padrões HL7 FHIR R4.
Requer: hapi_fhir container rodando (porta 8082)
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import FHIR_URL, TIMEOUT


# ---------------------------------------------------------------------------
# CapabilityStatement (metadata)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFHIRMetadata:
    """Testa o CapabilityStatement do servidor FHIR."""

    def test_metadata_endpoint(self, require_fhir, fhir_client):
        """GET /metadata deve retornar CapabilityStatement."""
        r = fhir_client.get("/metadata")
        assert r.status_code == 200
        data = r.json()
        assert data.get("resourceType") == "CapabilityStatement"

    def test_fhir_version_is_r4(self, require_fhir, fhir_client):
        """Servidor deve ser FHIR R4."""
        r = fhir_client.get("/metadata")
        data = r.json()
        fhir_version = data.get("fhirVersion", "")
        assert fhir_version.startswith("4."), f"Versão FHIR inesperada: {fhir_version}"

    def test_server_supports_patient(self, require_fhir, fhir_client):
        """Servidor deve suportar recurso Patient."""
        r = fhir_client.get("/metadata")
        data = r.json()
        rest = data.get("rest", [{}])[0]
        resource_types = [r_["type"] for r_ in rest.get("resource", [])]
        assert "Patient" in resource_types, f"Patient não suportado. Recursos: {resource_types[:10]}"

    def test_server_supports_encounter(self, require_fhir, fhir_client):
        """Servidor deve suportar recurso Encounter."""
        r = fhir_client.get("/metadata")
        data = r.json()
        rest = data.get("rest", [{}])[0]
        resource_types = [r_["type"] for r_ in rest.get("resource", [])]
        assert "Encounter" in resource_types

    def test_server_supports_claim(self, require_fhir, fhir_client):
        """Servidor deve suportar recurso Claim (TISS)."""
        r = fhir_client.get("/metadata")
        data = r.json()
        rest = data.get("rest", [{}])[0]
        resource_types = [r_["type"] for r_ in rest.get("resource", [])]
        assert "Claim" in resource_types


# ---------------------------------------------------------------------------
# CRUD — Patient
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFHIRPatientCRUD:
    """Testa operações CRUD no recurso Patient."""

    def test_create_patient(self, require_fhir, fhir_client):
        """POST /Patient deve criar um paciente."""
        patient = {
            "resourceType": "Patient",
            "identifier": [
                {
                    "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                    "value": "98765432100",
                }
            ],
            "name": [{"use": "official", "family": "TestSilva", "given": ["E2E"]}],
            "gender": "male",
            "birthDate": "1990-01-15",
        }
        r = fhir_client.post("/Patient", json=patient)
        assert r.status_code == 201, f"Falha ao criar Patient: {r.status_code} {r.text[:200]}"
        created = r.json()
        assert created.get("resourceType") == "Patient"
        assert "id" in created

    def test_read_patient(self, require_fhir, fhir_client):
        """GET /Patient/{id} deve recuperar paciente criado."""
        # Cria paciente primeiro
        patient = {
            "resourceType": "Patient",
            "name": [{"use": "official", "family": "TestRead", "given": ["E2E"]}],
            "gender": "female",
            "birthDate": "1985-06-20",
        }
        r_create = fhir_client.post("/Patient", json=patient)
        assert r_create.status_code == 201
        patient_id = r_create.json()["id"]

        # Lê paciente
        r_read = fhir_client.get(f"/Patient/{patient_id}")
        assert r_read.status_code == 200
        data = r_read.json()
        assert data["id"] == patient_id
        assert data["resourceType"] == "Patient"

    def test_search_patient_by_name(self, require_fhir, fhir_client):
        """GET /Patient?family=X deve buscar pacientes por sobrenome."""
        # Cria paciente com nome único
        import uuid
        unique_name = f"E2ESearch{uuid.uuid4().hex[:6].upper()}"
        patient = {
            "resourceType": "Patient",
            "name": [{"use": "official", "family": unique_name, "given": ["Test"]}],
        }
        r_create = fhir_client.post("/Patient", json=patient)
        assert r_create.status_code == 201

        # Busca por sobrenome
        r_search = fhir_client.get(f"/Patient", params={"family": unique_name, "_count": 5})
        assert r_search.status_code == 200
        bundle = r_search.json()
        assert bundle.get("resourceType") == "Bundle"
        total = bundle.get("total", 0)
        assert total >= 1, f"Paciente '{unique_name}' não encontrado na busca"

    def test_update_patient(self, require_fhir, fhir_client):
        """PUT /Patient/{id} deve atualizar um paciente."""
        # Cria
        patient = {
            "resourceType": "Patient",
            "name": [{"use": "official", "family": "TestUpdate", "given": ["E2E"]}],
        }
        r_create = fhir_client.post("/Patient", json=patient)
        assert r_create.status_code == 201
        created = r_create.json()
        patient_id = created["id"]

        # Atualiza
        created["name"] = [{"use": "official", "family": "TestUpdateModified", "given": ["E2E"]}]
        r_update = fhir_client.put(
            f"/Patient/{patient_id}",
            json=created,
            headers={"If-Match": f"W/\"{created.get('meta', {}).get('versionId', '1')}\""},
        )
        assert r_update.status_code in (200, 201), f"Update falhou: {r_update.text[:200]}"

    def test_bundle_search_returns_bundle(self, require_fhir, fhir_client):
        """GET /Patient deve retornar Bundle mesmo sem resultados."""
        r = fhir_client.get("/Patient", params={"_count": 1})
        assert r.status_code == 200
        data = r.json()
        assert data.get("resourceType") == "Bundle"
        assert "type" in data


# ---------------------------------------------------------------------------
# Encounter
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFHIREncounter:
    """Testa operações no recurso Encounter (atendimento hospitalar)."""

    def test_create_encounter(self, require_fhir, fhir_client):
        """POST /Encounter deve criar um atendimento."""
        # Cria paciente primeiro
        patient = {
            "resourceType": "Patient",
            "name": [{"use": "official", "family": "TestEncPaciente", "given": ["E2E"]}],
        }
        r_p = fhir_client.post("/Patient", json=patient)
        assert r_p.status_code == 201
        patient_id = r_p.json()["id"]

        encounter = {
            "resourceType": "Encounter",
            "status": "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory",
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "period": {"start": "2026-01-15T10:00:00Z", "end": "2026-01-15T10:30:00Z"},
        }
        r = fhir_client.post("/Encounter", json=encounter)
        assert r.status_code == 201, f"Falha ao criar Encounter: {r.text[:200]}"
        data = r.json()
        assert data.get("resourceType") == "Encounter"
        assert "id" in data

    def test_list_encounters(self, require_fhir, fhir_client):
        """GET /Encounter deve retornar Bundle."""
        r = fhir_client.get("/Encounter", params={"_count": 5})
        assert r.status_code == 200
        assert r.json().get("resourceType") == "Bundle"


# ---------------------------------------------------------------------------
# Organization / Tenant context
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFHIROrganization:
    """Testa recurso Organization (mapeado para tenants/hospitais)."""

    def test_create_organization(self, require_fhir, fhir_client):
        """POST /Organization deve criar organização hospitalar."""
        org = {
            "resourceType": "Organization",
            "identifier": [
                {
                    "system": "http://www.saude.gov.br/fhir/r4/NamingSystem/cnes",
                    "value": "1234567",
                }
            ],
            "name": "Hospital Austa — E2E Test",
            "type": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/organization-type",
                            "code": "prov",
                            "display": "Healthcare Provider",
                        }
                    ]
                }
            ],
        }
        r = fhir_client.post("/Organization", json=org)
        assert r.status_code == 201, f"Falha ao criar Organization: {r.text[:200]}"
        data = r.json()
        assert data.get("resourceType") == "Organization"
