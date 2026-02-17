"""Tests for GeneratePreAdmissionChecklistWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker():
    from healthcare_platform.patient_access.workers.generate_pre_admission_checklist_worker import (
        GeneratePreAdmissionChecklistWorker,
        StubPreAdmissionChecklistGenerator,
    )

    return GeneratePreAdmissionChecklistWorker(
        checklist_generator=StubPreAdmissionChecklistGenerator()
    )


@pytest.mark.unit
class TestGeneratePreAdmissionChecklistWorker:
    @pytest.mark.asyncio
    async def test_happy_path_generate_checklist(self, worker, tenant_austa):
        """Test successful checklist generation."""
        # Arrange
        task_vars = {
            "appointment_id": "Appointment/123",
            "appointment_type": "consulta",
            "specialty": "cardiologia",
            "patient_age": 45,
            "has_insurance": True,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["total_items"] > 0
        assert result["required_items"] > 0
        assert len(result["checklist_items"]) == result["total_items"]
        assert "instructions" in result

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"appointment_id": "Appointment/123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "appointment_id": "Appointment/123",
                    "appointment_type": "consulta",
                    "specialty": "cardiologia",
                    "patient_age": 45,
                    "has_insurance": True,
                }
            )

    @pytest.mark.asyncio
    async def test_surgical_checklist_more_items(self, worker, tenant_austa):
        """Test that surgical appointments have more checklist items."""
        # Consultation checklist
        result_consultation = await worker.execute(
            {
                "appointment_id": "Appointment/123",
                "appointment_type": "consulta",
                "specialty": "clinica_geral",
                "patient_age": 30,
                "has_insurance": False,
            }
        )

        # Surgery checklist
        result_surgery = await worker.execute(
            {
                "appointment_id": "Appointment/456",
                "appointment_type": "cirurgia",
                "specialty": "cirurgia_geral",
                "patient_age": 30,
                "has_insurance": False,
            }
        )

        # Surgery should have more items
        assert result_surgery["total_items"] > result_consultation["total_items"]

    @pytest.mark.asyncio
    async def test_insurance_adds_items(self, worker, tenant_austa):
        """Test that having insurance adds insurance-specific items."""
        # Without insurance
        result_no_insurance = await worker.execute(
            {
                "appointment_id": "Appointment/123",
                "appointment_type": "consulta",
                "specialty": "cardiologia",
                "patient_age": 45,
                "has_insurance": False,
            }
        )

        # With insurance
        result_with_insurance = await worker.execute(
            {
                "appointment_id": "Appointment/456",
                "appointment_type": "consulta",
                "specialty": "cardiologia",
                "patient_age": 45,
                "has_insurance": True,
                "insurance_plan": "Gold Plan",
            }
        )

        # Should have more items with insurance
        assert result_with_insurance["total_items"] > result_no_insurance["total_items"]

        # Check for insurance-specific items
        insurance_items = [
            item for item in result_with_insurance["checklist_items"]
            if "convênio" in item["description"].lower() or "autorização" in item["description"].lower()
        ]
        assert len(insurance_items) > 0

    @pytest.mark.asyncio
    async def test_patient_age_affects_requirements(self, worker, tenant_austa):
        """Test that patient age affects required items."""
        # Young patient
        result_young = await worker.execute(
            {
                "appointment_id": "Appointment/123",
                "appointment_type": "cirurgia",
                "specialty": "cirurgia_geral",
                "patient_age": 25,
                "has_insurance": False,
            }
        )

        # Older patient (>40)
        result_older = await worker.execute(
            {
                "appointment_id": "Appointment/456",
                "appointment_type": "cirurgia",
                "specialty": "cirurgia_geral",
                "patient_age": 65,
                "has_insurance": False,
            }
        )

        # Check for ECG requirement (required for age > 40)
        ecg_items_older = [
            item for item in result_older["checklist_items"]
            if "ECG" in item["description"] or "Eletrocardiograma" in item["description"]
        ]

        # Older patient should have ECG requirement
        assert len(ecg_items_older) > 0
        assert any(item["required"] for item in ecg_items_older)

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "appointment_id": "Appointment/austa-123",
                "appointment_type": "internacao",
                "specialty": "cardiologia",
                "patient_age": 55,
                "has_insurance": True,
            }
        )

        # Switch to HOSPITAL_B
        hospital_b_ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_B)
        set_current_tenant(hospital_b_ctx)

        # Execute with HOSPITAL_B
        result_hospital_b = await worker.execute(
            {
                "appointment_id": "Appointment/hpa-123",
                "appointment_type": "internacao",
                "specialty": "cardiologia",
                "patient_age": 55,
                "has_insurance": True,
            }
        )

        # Checklists should be consistent (same rules)
        assert result_austa["total_items"] == result_hospital_b["total_items"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        task_vars = {
            "appointment_id": "Appointment/789",
            "appointment_type": "consulta",
            "specialty": "cardiologia",
            "patient_age": 45,
            "has_insurance": True,
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be identical
        assert result1["total_items"] == result2["total_items"]
        assert result1["required_items"] == result2["required_items"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.generate_pre_admission_checklist_worker import (
            PatientAccessException,
        )

        # Mock failure
        worker.checklist_generator.generate_checklist = AsyncMock(
            side_effect=Exception("Checklist service unavailable")
        )

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "appointment_id": "Appointment/123",
                    "appointment_type": "consulta",
                    "specialty": "cardiologia",
                    "patient_age": 45,
                    "has_insurance": True,
                }
            )

    @pytest.mark.asyncio
    async def test_checklist_item_structure(self, worker, tenant_austa):
        """Test that checklist items have required structure."""
        result = await worker.execute(
            {
                "appointment_id": "Appointment/999",
                "appointment_type": "internacao",
                "specialty": "cardiologia",
                "patient_age": 50,
                "has_insurance": True,
            }
        )

        # Check item structure
        for item in result["checklist_items"]:
            assert "item_id" in item
            assert "description" in item
            assert "required" in item
            assert "category" in item
            assert item["category"] in ["document", "exam", "preparation"]

    @pytest.mark.asyncio
    async def test_earliest_deadline_calculated(self, worker, tenant_austa):
        """Test that earliest deadline is calculated correctly."""
        result = await worker.execute(
            {
                "appointment_id": "Appointment/888",
                "appointment_type": "cirurgia",
                "specialty": "ortopedia",
                "patient_age": 40,
                "has_insurance": True,
            }
        )

        # Should have an earliest deadline
        assert result["earliest_deadline"] is not None

        # Parse and validate
        earliest = datetime.fromisoformat(result["earliest_deadline"])
        assert earliest > datetime.now()

    @pytest.mark.asyncio
    async def test_instructions_vary_by_appointment_type(self, worker, tenant_austa):
        """Test that instructions are different for different appointment types."""
        result_consultation = await worker.execute(
            {
                "appointment_id": "Appointment/111",
                "appointment_type": "consulta",
                "specialty": "cardiologia",
                "patient_age": 45,
                "has_insurance": True,
            }
        )

        result_surgery = await worker.execute(
            {
                "appointment_id": "Appointment/222",
                "appointment_type": "cirurgia",
                "specialty": "cardiologia",
                "patient_age": 45,
                "has_insurance": True,
            }
        )

        # Instructions should be different
        assert result_consultation["instructions"] != result_surgery["instructions"]

        # Surgery instructions should mention specific requirements
        surgery_instructions = result_surgery["instructions"].lower()
        assert "cirurgia" in surgery_instructions or "jejum" in surgery_instructions
