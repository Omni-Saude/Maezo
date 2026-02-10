"""Tests for CalculateEstimatedDurationWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.calculate_estimated_duration_worker import (
        CalculateEstimatedDurationWorker,
        StubDurationCalculator,
    )

    return CalculateEstimatedDurationWorker(
        fhir_client=fhir_client, duration_calculator=StubDurationCalculator()
    )


@pytest.mark.unit
class TestCalculateEstimatedDurationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_duration_calculation(self, worker, fhir_client, tenant_austa):
        """Test successful duration calculation."""
        # Arrange
        task_vars = {
            "service_type": "consulta",
            "specialty_code": "cardiologia",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["estimated_duration_minutes"] > 0
        assert result["breakdown"]["base_duration_minutes"] == 30  # Base for consulta
        assert result["confidence_level"] in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"service_type": "consulta"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "service_type": "consulta",
                    "specialty_code": "cardiologia",
                }
            )

    @pytest.mark.asyncio
    async def test_first_visit_adjustment(self, worker, tenant_austa):
        """Test that first visit adds extra duration."""
        # Without first visit
        result1 = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "clinica_geral",
                "is_first_visit": False,
            }
        )

        # With first visit
        result2 = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "clinica_geral",
                "is_first_visit": True,
            }
        )

        # First visit should take longer
        assert result2["estimated_duration_minutes"] > result1["estimated_duration_minutes"]
        assert result2["breakdown"]["first_visit_adjustment_minutes"] == 10

    @pytest.mark.asyncio
    async def test_complexity_adjustment(self, worker, tenant_austa):
        """Test complexity level affects duration."""
        # Low complexity
        result_low = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "clinica_geral",
                "complexity_level": "low",
            }
        )

        # High complexity
        result_high = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "clinica_geral",
                "complexity_level": "high",
            }
        )

        # High complexity should take longer
        assert result_high["estimated_duration_minutes"] > result_low["estimated_duration_minutes"]

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "cardiologia",
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "cardiologia",
            }
        )

        # Results should be consistent (same calculation logic)
        assert result_austa["estimated_duration_minutes"] == result_hpa["estimated_duration_minutes"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        task_vars = {
            "service_type": "consulta",
            "specialty_code": "cardiologia",
            "complexity_level": "medium",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be identical
        assert result1["estimated_duration_minutes"] == result2["estimated_duration_minutes"]
        assert result1["breakdown"] == result2["breakdown"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.calculate_estimated_duration_worker import (
            PatientAccessException,
        )

        # Mock failure
        worker.duration_calculator.calculate_duration = AsyncMock(
            side_effect=Exception("Duration service unavailable")
        )

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "service_type": "consulta",
                    "specialty_code": "cardiologia",
                }
            )

    @pytest.mark.asyncio
    async def test_procedure_codes_adjustment(self, worker, tenant_austa):
        """Test that procedure codes add to duration."""
        # Without procedures
        result1 = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "clinica_geral",
                "procedure_codes": [],
            }
        )

        # With procedures
        result2 = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "clinica_geral",
                "procedure_codes": ["proc1", "proc2", "proc3"],
            }
        )

        # More procedures = longer duration
        assert result2["estimated_duration_minutes"] > result1["estimated_duration_minutes"]
        assert result2["breakdown"]["procedure_adjustment_minutes"] == 15  # 3 * 5 minutes

    @pytest.mark.asyncio
    async def test_confidence_level_with_patient_data(self, worker, tenant_austa):
        """Test confidence level increases with patient/practitioner data."""
        # Without patient/practitioner data
        result_low = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "cardiologia",
            }
        )

        # With patient data
        result_med = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "cardiologia",
                "patient_id": "Patient/123",
            }
        )

        # With both patient and practitioner data
        result_high = await worker.execute(
            {
                "service_type": "consulta",
                "specialty_code": "cardiologia",
                "patient_id": "Patient/123",
                "practitioner_id": "Practitioner/456",
            }
        )

        assert result_low["confidence_level"] == "low"
        assert result_med["confidence_level"] == "medium"
        assert result_high["confidence_level"] == "high"

    @pytest.mark.asyncio
    async def test_surgical_procedure_duration(self, worker, tenant_austa):
        """Test duration calculation for surgical procedures."""
        result = await worker.execute(
            {
                "service_type": "cirurgia",
                "specialty_code": "ortopedia",
                "complexity_level": "high",
            }
        )

        # Surgery base duration is 120 minutes
        assert result["breakdown"]["base_duration_minutes"] == 120
        assert result["estimated_duration_minutes"] >= 120
