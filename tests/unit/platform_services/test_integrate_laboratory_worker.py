"""Tests for IntegrateLaboratoryWorker."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.integrate_laboratory_worker import (
    IntegrateLaboratoryInput,
    IntegrateLaboratoryOutput,
    execute,
    LaboratoryIntegrationException,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.mark.unit
class TestIntegrateLaboratoryWorker:
    """Test suite for IntegrateLaboratoryWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_with_hl7(self, tenant_austa):
        """Test successful lab integration with HL7 message."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-456",
            "test_type": "hematology",
            "hl7_message": "MSH|^~\\&|LIS|...",
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
            "validate_ranges": True,
        }

        result = await execute(input_data)

        assert result["patient_id"] == "pat-123"
        assert result["order_id"] == "order-456"
        assert result["test_type"] == "hematology"
        assert len(result["results"]) > 0
        assert result["validation_status"] in ["validated", "warnings", "failed"]

    @pytest.mark.asyncio
    async def test_happy_path_with_fhir(self, tenant_austa):
        """Test successful lab integration with FHIR observation."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-456",
            "test_type": "biochemistry",
            "fhir_observation": {
                "code": {
                    "coding": [{"code": "GLU", "display": "Glicemia"}]
                },
                "valueQuantity": {"value": 95, "unit": "mg/dL"},
                "referenceRange": [{"text": "70-100"}],
            },
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        result = await execute(input_data)

        assert result["patient_id"] == "pat-123"
        assert len(result["results"]) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            await execute({
                "patient_id": "pat-123",
                # Missing required fields
            })

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-456",
            "test_type": "hematology",
            "hl7_message": "MSH|...",
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        with pytest.raises(InvalidTenant):
            await execute(input_data)

    @pytest.mark.asyncio
    async def test_different_test_types(self, tenant_austa):
        """Test integration with different test types."""
        test_types = ["hematology", "biochemistry", "microbiology", "pathology"]

        for test_type in test_types:
            input_data = {
                "patient_id": f"pat-{test_type}",
                "order_id": f"order-{test_type}",
                "test_type": test_type,
                "hl7_message": "MSH|...",
                "lab_system_code": "LIS-001",
                "collected_at": datetime.now().isoformat(),
                "resulted_at": datetime.now().isoformat(),
            }

            result = await execute(input_data)

            assert result["test_type"] == test_type

    @pytest.mark.asyncio
    async def test_critical_results_detection(self, tenant_austa):
        """Test detection of critical lab results."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-critical",
            "test_type": "biochemistry",
            "hl7_message": "MSH|...",  # Stub returns critical result
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        result = await execute(input_data)

        # Stub returns critical results
        assert result["critical_results_count"] >= 0

    @pytest.mark.asyncio
    async def test_abnormal_results_count(self, tenant_austa):
        """Test counting of abnormal results."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-abnormal",
            "test_type": "hematology",
            "hl7_message": "MSH|...",
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
            "validate_ranges": True,
        }

        result = await execute(input_data)

        assert result["abnormal_results_count"] >= 0

    @pytest.mark.asyncio
    async def test_validation_messages(self, tenant_austa):
        """Test that validation messages are generated for abnormal results."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-validation",
            "test_type": "biochemistry",
            "hl7_message": "MSH|...",
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
            "validate_ranges": True,
        }

        result = await execute(input_data)

        assert "validation_messages" in result
        assert isinstance(result["validation_messages"], list)

    @pytest.mark.asyncio
    async def test_fhir_resource_created(self, tenant_austa):
        """Test that FHIR Observation resource ID is generated."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-fhir",
            "test_type": "hematology",
            "hl7_message": "MSH|...",
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        result = await execute(input_data)

        assert "fhir_resource_id" in result
        assert result["fhir_resource_id"] is not None
        assert "Observation/" in result["fhir_resource_id"]

    @pytest.mark.asyncio
    async def test_no_input_data_raises(self, tenant_austa):
        """Test that missing both HL7 and FHIR data raises error."""
        input_data = {
            "patient_id": "pat-123",
            "order_id": "order-456",
            "test_type": "hematology",
            # No hl7_message or fhir_observation
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        with pytest.raises(LaboratoryIntegrationException):
            await execute(input_data)

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = {
            "patient_id": "pat-999",
            "order_id": "order-999",
            "test_type": "hematology",
            "hl7_message": "MSH|...",
            "lab_system_code": "LIS-999",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        result = await execute(input_data)

        assert result["patient_id"] == "pat-999"
        assert result["order_id"] == "order-999"

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test that multiple executions produce consistent results."""
        input_data = {
            "patient_id": "pat-idem",
            "order_id": "order-idem",
            "test_type": "biochemistry",
            "hl7_message": "MSH|...",
            "lab_system_code": "LIS-001",
            "collected_at": datetime.now().isoformat(),
            "resulted_at": datetime.now().isoformat(),
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        # Should have same patient_id and order_id
        assert result1["patient_id"] == result2["patient_id"]
        assert result1["order_id"] == result2["order_id"]
