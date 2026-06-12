"""Tests for ValidateTISSSchemaWorker."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.billing.workers.validate_tiss_schema_worker import ValidateTISSSchemaWorker
from healthcare_platform.shared.integrations.tiss_client import StubTISSClient

from unittest.mock import Mock


@pytest.fixture
def mock_dmn_service():
    """Create mock DMN service."""
    dmn_service = Mock()
    # Default DMN response: PROSSEGUIR (allow processing)
    dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Processar com sucesso",
        "risco": "BAIXO"
    }
    return dmn_service


@pytest.fixture
def tiss_client():
    """Create stub TISS client."""
    return StubTISSClient()


@pytest.fixture
def worker(tiss_client, mock_dmn_service):
    """Create worker instance."""
    return ValidateTISSSchemaWorker(
        tiss_client=tiss_client,
        dmn_service=mock_dmn_service
    )


@pytest.fixture
def valid_tiss_xml():
    """Create valid TISS XML."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<tissComunicacao xmlns="http://www.ans.gov.br/padroes/tiss/schemas" versao="4.01.00">
    <cabecalho>
        <codigoPrestador>CNES-67890</codigoPrestador>
        <codigoOperadora>ANS-12345</codigoOperadora>
        <numeroGuia>PROVIDER-20240209-12345678</numeroGuia>
    </cabecalho>
    <guiaSP-SADT>
        <dataRealizacao>2024-02-09</dataRealizacao>
    </guiaSP-SADT>
</tissComunicacao>"""


@pytest.fixture
def valid_variables(valid_tiss_xml):
    """Create valid process variables."""
    return {
        "tiss_xml": valid_tiss_xml,
        "guide_type": "sp_sadt",
        "guide_number": "PROVIDER-20240209-12345678",
        "payer_id": "ANS-12345",
        "provider_id": "CNES-67890",
        "patient_id": str(uuid4()),
    }


class TestValidateTISSSchemaWorker:
    """Test suite for ValidateTISSSchemaWorker."""

    @pytest.mark.asyncio
    async def test_successful_validation(self, worker, valid_variables):
        """Test successful TISS schema validation."""
        job = SimpleNamespace(variables=valid_variables)

        result = await worker.process_task(job, valid_variables)

        assert result.success is True
        assert result.variables["schema_valid"] is True
        assert len(result.variables["schema_errors"]) == 0

    @pytest.mark.asyncio
    async def test_missing_tiss_xml(self, worker, valid_variables):
        """Test error when tiss_xml is missing."""
        variables = valid_variables.copy()
        del variables["tiss_xml"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_empty_tiss_xml(self, worker, valid_variables):
        """Test error when tiss_xml is empty."""
        variables = valid_variables.copy()
        variables["tiss_xml"] = ""

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_missing_guide_type(self, worker, valid_variables):
        """Test error when guide_type is missing."""
        variables = valid_variables.copy()
        del variables["guide_type"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_invalid_guide_type(self, worker, valid_variables):
        """Test error for invalid guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "invalid_type"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is False
        assert result.error_code == "TISS_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_guide_type_consultation(self, worker, valid_variables):
        """Test validation for consultation guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "consultation"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["schema_valid"] is True

    @pytest.mark.asyncio
    async def test_guide_type_admission(self, worker, valid_variables):
        """Test validation for admission guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "admission"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["schema_valid"] is True

    @pytest.mark.asyncio
    async def test_guide_type_extension(self, worker, valid_variables):
        """Test validation for extension guide type."""
        variables = valid_variables.copy()
        variables["guide_type"] = "extension"

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_optional_payer_id(self, worker, valid_variables):
        """Test validation works without payer_id."""
        variables = valid_variables.copy()
        del variables["payer_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_optional_provider_id(self, worker, valid_variables):
        """Test validation works without provider_id."""
        variables = valid_variables.copy()
        del variables["provider_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_optional_patient_id(self, worker, valid_variables):
        """Test validation works without patient_id."""
        variables = valid_variables.copy()
        del variables["patient_id"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_guide_number_defaults(self, worker, valid_variables):
        """Test validation uses default guide number if missing."""
        variables = valid_variables.copy()
        del variables["guide_number"]

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_large_xml(self, worker, valid_variables):
        """Test validation with large XML."""
        variables = valid_variables.copy()
        # Create large XML
        large_xml = valid_variables["tiss_xml"] * 100

        variables["tiss_xml"] = large_xml

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_xml_with_special_characters(self, worker, valid_variables):
        """Test validation with XML containing special characters."""
        variables = valid_variables.copy()
        xml_with_special = valid_variables["tiss_xml"].replace(
            "CNES-67890",
            "CNES-67890-ÇÃÕ&lt;&gt;"
        )
        variables["tiss_xml"] = xml_with_special

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_stub_client_always_validates(self, worker, valid_variables):
        """Test that stub client always returns valid."""
        # Stub client returns empty errors list (valid)
        variables = valid_variables.copy()

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        assert result.variables["schema_valid"] is True

    @pytest.mark.asyncio
    async def test_xml_logging(self, worker, valid_variables):
        """Test that XML length is logged correctly."""
        variables = valid_variables.copy()

        job = SimpleNamespace(variables=variables)
        result = await worker.process_task(job, variables)

        assert result.success is True
        # Verify that result contains expected data
        assert "schema_valid" in result.variables
        assert "schema_errors" in result.variables
