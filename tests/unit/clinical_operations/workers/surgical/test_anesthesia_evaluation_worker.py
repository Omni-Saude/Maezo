"""Unit tests for AnesthesiaEvaluationWorker."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.surgical.anesthesia_evaluation_worker import (
    ClinicalOperationsException,
    AnesthesiaEvaluationInput,
    AnesthesiaEvaluationOutput,
    AnesthesiaEvaluationWorker,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    """Set up tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance."""
    return AnesthesiaEvaluationWorker()


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    """Valid task variables for testing."""
    return {
        "surgery_id": "SRG-12345",
        "patient_id": "Patient/12345",
        "anesthesiologist_id": "Practitioner/MED-002",
        "asa_classification": 1,
        "anesthesia_type": "general",
        "allergies": [],
        "comorbidities": [],
        "fasting_hours": 8.0,
        "weight_kg": 70.0,
        "height_cm": 175.0,
    }


@pytest.mark.unit
class TestAnesthesiaEvaluationWorker:
    """Test suite for AnesthesiaEvaluationWorker."""

    @pytest.mark.asyncio
    async def test_execute_success_low_risk(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test successful execution for low risk patient (ASA 1)."""
        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["evaluation_id"] is not None
        assert result["surgery_id"] == "SRG-12345"
        assert result["patient_id"] == "Patient/12345"
        assert result["asa_classification"] == 1
        assert result["anesthesia_plan"] is not None
        assert result["risk_level"] == "low"
        assert result["cleared_for_surgery"] is True
        assert result["evaluated_at"] is not None

    @pytest.mark.asyncio
    async def test_execute_success_high_risk(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test successful execution for high risk patient (ASA 4 with comorbidities)."""
        valid_task_variables["asa_classification"] = 4
        valid_task_variables["allergies"] = ["Penicilina", "Dipirona"]
        valid_task_variables["comorbidities"] = [
            "Diabetes tipo 2",
            "Hipertensão arterial",
            "Doença renal crônica",
        ]

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["asa_classification"] == 4
        assert result["risk_level"] == "high"
        assert result["cleared_for_surgery"] is True
        assert result["anesthesia_plan"] is not None
        assert "Invasive monitoring recommended" in result["anesthesia_plan"]
        assert result["notes"] is not None

    @pytest.mark.asyncio
    async def test_insufficient_fasting(self, worker, tenant_ctx, valid_task_variables):
        """Test with insufficient fasting hours."""
        valid_task_variables["fasting_hours"] = 4.0

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["cleared_for_surgery"] is False
        assert result["notes"] is not None
        assert "Fasting não conforme" in result["notes"]

    @pytest.mark.asyncio
    async def test_invalid_asa_classification_zero(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test validation error with invalid ASA classification (0)."""
        valid_task_variables["asa_classification"] = 0

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_invalid_asa_classification_seven(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test validation error with invalid ASA classification (7)."""
        valid_task_variables["asa_classification"] = 7

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_missing_patient_id(self, worker, tenant_ctx, valid_task_variables):
        """Test validation error when patient_id is missing."""
        del valid_task_variables["patient_id"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_output_fields(self, worker, tenant_ctx, valid_task_variables):
        """Test all expected output fields are present."""
        result = await worker.execute(valid_task_variables)

        expected_fields = [
            "evaluation_id",
            "surgery_id",
            "patient_id",
            "asa_classification",
            "anesthesia_plan",
            "risk_level",
            "cleared_for_surgery",
            "evaluated_at",
        ]

        for field in expected_fields:
            assert field in result

    @pytest.mark.asyncio
    async def test_bmi_calculation(self, worker, tenant_ctx, valid_task_variables):
        """Test BMI calculation."""
        valid_task_variables["weight_kg"] = 70.0
        valid_task_variables["height_cm"] = 175.0

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert "bmi" in result
        # BMI = weight_kg / (height_m ^ 2) = 70 / (1.75 ^ 2) = 70 / 3.0625 ≈ 22.86
        expected_bmi = 70.0 / ((175.0 / 100) ** 2)
        assert abs(result["bmi"] - expected_bmi) < 0.01

    @pytest.mark.asyncio
    async def test_missing_surgery_id(self, worker, tenant_ctx, valid_task_variables):
        """Test validation error when surgery_id is missing."""
        del valid_task_variables["surgery_id"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_missing_anesthesiologist_id(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test validation error when anesthesiologist_id is missing."""
        del valid_task_variables["anesthesiologist_id"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_regional_anesthesia(self, worker, tenant_ctx, valid_task_variables):
        """Test with regional anesthesia type."""
        valid_task_variables["anesthesia_type"] = "regional"

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["anesthesia_type"] == "regional"
        assert result["cleared_for_surgery"] is True

    @pytest.mark.asyncio
    async def test_local_anesthesia(self, worker, tenant_ctx, valid_task_variables):
        """Test with local anesthesia type."""
        valid_task_variables["anesthesia_type"] = "local"
        valid_task_variables["asa_classification"] = 1

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["anesthesia_type"] == "local"
        assert result["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_asa_2_moderate_risk(self, worker, tenant_ctx, valid_task_variables):
        """Test ASA 2 classification (moderate risk)."""
        valid_task_variables["asa_classification"] = 2
        valid_task_variables["comorbidities"] = ["Hipertensão controlada"]

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["asa_classification"] == 2
        assert result["risk_level"] == "moderate"
        assert result["cleared_for_surgery"] is True

    @pytest.mark.asyncio
    async def test_asa_3_moderate_risk(self, worker, tenant_ctx, valid_task_variables):
        """Test ASA 3 classification (moderate risk)."""
        valid_task_variables["asa_classification"] = 3
        valid_task_variables["comorbidities"] = ["Diabetes não controlado"]

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["asa_classification"] == 3
        assert result["risk_level"] == "moderate"

    @pytest.mark.asyncio
    async def test_asa_5_critical_risk(self, worker, tenant_ctx, valid_task_variables):
        """Test ASA 5 classification (critical risk)."""
        valid_task_variables["asa_classification"] = 5

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["asa_classification"] == 5
        assert result["risk_level"] == "critical"

    @pytest.mark.asyncio
    async def test_missing_weight(self, worker, tenant_ctx, valid_task_variables):
        """Test validation error when weight is missing."""
        del valid_task_variables["weight_kg"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_missing_height(self, worker, tenant_ctx, valid_task_variables):
        """Test validation error when height is missing."""
        del valid_task_variables["height_cm"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_multiple_allergies(self, worker, tenant_ctx, valid_task_variables):
        """Test with multiple allergies."""
        valid_task_variables["allergies"] = [
            "Penicilina",
            "Dipirona",
            "Látex",
            "Contraste iodado",
        ]

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert len(result["allergies"]) == 4
        assert "Látex" in result["allergies"]
        assert "Contraste iodado" in result["allergies"]
