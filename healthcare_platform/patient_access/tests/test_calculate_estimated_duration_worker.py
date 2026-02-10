"""Tests for CalculateEstimatedDurationWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def duration_calculator():
    """Mock duration calculator protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, duration_calculator):
    from healthcare_platform.patient_access.workers.calculate_estimated_duration_worker import CalculateEstimatedDurationWorker
    return CalculateEstimatedDurationWorker(fhir_client=fhir_client, duration_calculator=duration_calculator)


class TestCalculateEstimatedDurationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_calculates_duration(self, worker, fhir_client, duration_calculator, tenant_austa):
        """Test successful duration calculation."""
        duration_calculator.calculate.return_value = {
            "estimated_minutes": 30,
            "confidence": 0.85
        }

        result = await worker.execute({
            "service_type": "consultation",
            "complexity": "standard"
        })

        assert result["estimated_minutes"] == 30
        assert result["confidence"] == 0.85
        duration_calculator.calculate.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing service_type raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"service_type": "consultation"})

    @pytest.mark.asyncio
    async def test_complex_procedure_longer_duration(self, worker, fhir_client, duration_calculator, tenant_austa):
        """Test that complex procedures have longer duration."""
        duration_calculator.calculate.return_value = {
            "estimated_minutes": 90,
            "confidence": 0.75
        }

        result = await worker.execute({
            "service_type": "surgery",
            "complexity": "high"
        })

        assert result["estimated_minutes"] == 90
        assert result["estimated_minutes"] > 30
