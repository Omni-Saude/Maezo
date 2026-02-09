"""Tests for GenerateTISSXMLWorker."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from platform.revenue_cycle.billing.workers.generate_tiss_xml_worker import GenerateTISSXMLWorker
from platform.shared.integrations.tiss_client import StubTISSClient


@pytest.fixture
def tiss_client():
    """Create stub TISS client."""
    return StubTISSClient()


@pytest.fixture
def worker(tiss_client):
    """Create worker instance."""
    return GenerateTISSXMLWorker(tiss_client=tiss_client)


@pytest.fixture
def valid_claim_data():
    """Create valid claim data."""
    return {
        "id": str(uuid4()),
        "tiss_guide_number": "PROVIDER-20240209-12345678",
        "diagnosis_codes": [
            {"code": "A00.0", "system": "http://hl7.org/fhir/sid/icd-10"},
            {"code": "B00.1"},
        ],
        "total": {"amount": 250.00, "currency": "BRL"},
        "authorization_number": "AUTH-12345",
        "attending_physician_id": "CRM-SP-123456",
        "requested_date": "2024-02-09T10:30:00Z",
    }


@pytest.fixture
def valid_items():
    """Create valid line items."""
    return [
        {
            "procedure_code": {"code": "10101012", "display": "Consulta médica"},
            "quantity": 1,
            "unit_price": {"amount": 150.00},
        },
        {
            "procedure_code": {"code": "20104030", "display": "Hemograma"},
            "quantity": 2,
            "unit_price": {"amount": 50.00},
        },
    ]


@pytest.fixture
def valid_variables(valid_claim_data, valid_items):
    """Create valid process variables."""
    return {
        "claim": valid_claim_data,
        "payer_id": "ANS-12345",
        "provider_id": "CNES-67890",
        "patient_id": str(uuid4()),
        "guide_type": "sp_sadt",
        "items": valid_items,
    }


class TestGenerateTISSXMLWorker:
    """Test suite for GenerateTISSXMLWorker."""

    @pytest.mark.asyncio
    async def test_successful_xml_generation(self, worker, valid_variables):
        """Test successful TISS XML generation."""
        job = SimpleNamespace(variables=valid_variables)

        result = await worker.process_task(job, valid_variables)

        assert result.success is True
        assert "tiss_xml" in result.variables
        assert result.variables["tiss_xml"]  # Not empty
        assert "guide_number" in result.variables
        assert result.variables["guide_type"] == "sp_sadt"

    @pytest.mark.asyncio
    async def test_missing_claim_data(self, worker, valid_variables):
        """Test error when claim data is missing."""
        variables = valid_variables.copy()
        del variables["claim"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_ERROR"

    @pytest.mark.asyncio
    async def test_missing_payer_id(self, worker, valid_variables):
        """Test error when payer_id is missing."""
        variables = valid_variables.copy()
        del variables["payer_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_ERROR"
        assert "operadora" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_missing_provider_id(self, worker, valid_variables):
        """Test error when provider_id is missing."""
        variables = valid_variables.copy()
        del variables["provider_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_ERROR"
        assert "prestador" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_missing_patient_id(self, worker, valid_variables):
        """Test error when patient_id is missing."""
        variables = valid_variables.copy()
        del variables["patient_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_ERROR"
        assert "paciente" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_missing_guide_type(self, worker, valid_variables):
        """Test error when guide_type is missing."""
        variables = valid_variables.copy()
        del variables["guide_type"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_ERROR"
        assert "tipo de guia" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_invalid_guide_type(self, worker, valid_variables):
        """Test error for invalid guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "invalid_type"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_ERROR"
        assert "inválido" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_auto_generate_guide_number(self, worker, valid_variables):
        """Test that guide number is auto-generated if missing."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        del claim["tiss_guide_number"]
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["guide_number"]  # Generated
        assert variables["provider_id"] in result.variables["guide_number"]

    @pytest.mark.asyncio
    async def test_diagnosis_codes_extraction(self, worker, valid_variables):
        """Test diagnosis codes are correctly extracted."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["diagnosis_codes"] = [
            {"code": "A00.0"},
            {"code": "B00.1"},
        ]
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_procedure_codes_from_items(self, worker, valid_variables):
        """Test procedure codes are extracted from items."""
        variables = valid_variables.copy()
        variables["items"] = [
            {"procedure_code": {"code": "10101012"}},
            {"procedure_code": {"code": "20104030"}},
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_datetime_parsing(self, worker, valid_variables):
        """Test datetime fields are correctly parsed."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["admission_date"] = "2024-02-01T08:00:00Z"
        claim["discharge_date"] = "2024-02-09T18:00:00Z"
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_financial_data_extraction(self, worker, valid_variables):
        """Test financial data is correctly extracted."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["total"] = {"amount": 1000.00, "currency": "BRL"}
        claim["authorized_amount"] = 900.00
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_authorization_number(self, worker, valid_variables):
        """Test authorization number is included."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["authorization_number"] = "AUTH-99999"
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_attending_physician_extraction(self, worker, valid_variables):
        """Test attending physician is extracted from references."""
        variables = valid_variables.copy()
        claim = variables["claim"].copy()
        claim["practitioner_references"] = [
            {"reference": "Practitioner/CRM-SP-123456"}
        ]
        variables["claim"] = claim

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_empty_items_list(self, worker, valid_variables):
        """Test with empty items list."""
        variables = valid_variables.copy()
        variables["items"] = []

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_guide_type_consultation(self, worker, valid_variables):
        """Test XML generation for consultation guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "consultation"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["guide_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_guide_type_admission(self, worker, valid_variables):
        """Test XML generation for admission guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "admission"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["guide_type"] == "admission"

    @pytest.mark.asyncio
    async def test_item_with_string_procedure_code(self, worker, valid_variables):
        """Test item with procedure code as string instead of dict."""
        variables = valid_variables.copy()
        variables["items"] = [
            {
                "procedure_code": "10101012",  # String format
                "quantity": 1,
                "unit_price": 100.00,
            }
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_unit_price_extraction_variants(self, worker, valid_variables):
        """Test unit price extraction from different formats."""
        variables = valid_variables.copy()
        variables["items"] = [
            {"procedure_code": {"code": "10101012"}, "quantity": 1, "unit_price": {"amount": 100.00}},
            {"procedure_code": {"code": "20104030"}, "quantity": 1, "unit_price": 50.00},  # Direct float
        ]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
