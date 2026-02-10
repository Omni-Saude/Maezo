"""Tests for CheckPreAuthorizationWorker."""
from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.check_pre_authorization_worker import (
        CheckPreAuthorizationWorker,
        StubPreAuthorizationChecker,
    )

    return CheckPreAuthorizationWorker(
        fhir_client=fhir_client, pre_auth_checker=StubPreAuthorizationChecker()
    )


@pytest.mark.unit
class TestCheckPreAuthorizationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_no_preauth_required(self, worker, fhir_client, tenant_austa):
        """Test procedure that doesn't require pre-authorization."""
        # Arrange
        proposed_date = datetime.utcnow() + timedelta(days=7)

        task_vars = {
            "patient_id": "Patient/123",
            "coverage_id": "Coverage/456",
            "service_type": "consulta",  # Simple consultation
            "procedure_codes": [],
            "specialty_code": "clinica_geral",
            "practitioner_id": "Practitioner/789",
            "proposed_date": proposed_date.isoformat(),
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["pre_auth_required"] is False
        assert result["authorization_status"] == "not_required"
        assert result["requires_action"] is False

    @pytest.mark.asyncio
    async def test_happy_path_preauth_required_approved(self, worker, fhir_client, tenant_austa):
        """Test procedure requiring pre-authorization (auto-approved in stub)."""
        # Arrange
        proposed_date = datetime.utcnow() + timedelta(days=7)

        task_vars = {
            "patient_id": "Patient/123",
            "coverage_id": "Coverage/456",
            "service_type": "cirurgia",  # Surgery requires pre-auth
            "procedure_codes": ["40101010"],
            "specialty_code": "cardiologia",
            "practitioner_id": "Practitioner/789",
            "proposed_date": proposed_date.isoformat(),
            "estimated_cost": 5000.00,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["pre_auth_required"] is True
        assert result["authorization_status"] == "approved"
        assert result["authorization_number"] is not None
        assert result["authorization_details"] is not None
        assert result["requires_action"] is False

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"patient_id": "Patient/123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        proposed_date = datetime.utcnow() + timedelta(days=7)

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "Patient/123",
                    "coverage_id": "Coverage/456",
                    "service_type": "consulta",
                    "procedure_codes": [],
                    "specialty_code": "clinica_geral",
                    "practitioner_id": "Practitioner/789",
                    "proposed_date": proposed_date.isoformat(),
                }
            )

    @pytest.mark.asyncio
    async def test_high_cost_procedure_requires_auth(self, worker, tenant_austa):
        """Test that high-cost procedures require pre-authorization."""
        proposed_date = datetime.utcnow() + timedelta(days=7)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "coverage_id": "Coverage/456",
                "service_type": "exame",
                "procedure_codes": ["30701011"],  # Not in HIGH_COST but cost triggers
                "specialty_code": "radiologia",
                "practitioner_id": "Practitioner/789",
                "proposed_date": proposed_date.isoformat(),
                "estimated_cost": 2000.00,  # >= 1000 triggers pre-auth
            }
        )

        assert result["pre_auth_required"] is True

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        proposed_date = datetime.utcnow() + timedelta(days=7)

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "patient_id": "Patient/austa-123",
                "coverage_id": "Coverage/austa-456",
                "service_type": "cirurgia",
                "procedure_codes": ["40101010"],
                "specialty_code": "cardiologia",
                "practitioner_id": "Practitioner/789",
                "proposed_date": proposed_date.isoformat(),
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "patient_id": "Patient/hpa-123",
                "coverage_id": "Coverage/hpa-456",
                "service_type": "cirurgia",
                "procedure_codes": ["40101010"],
                "specialty_code": "cardiologia",
                "practitioner_id": "Practitioner/789",
                "proposed_date": proposed_date.isoformat(),
            }
        )

        # Both should require auth (same procedure)
        assert result_austa["pre_auth_required"] == result_hpa["pre_auth_required"]
        # But authorization numbers should be different
        assert result_austa["authorization_number"] != result_hpa["authorization_number"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        proposed_date = datetime.utcnow() + timedelta(days=7)

        task_vars = {
            "patient_id": "Patient/123",
            "coverage_id": "Coverage/456",
            "service_type": "cirurgia",
            "procedure_codes": ["40101010"],
            "specialty_code": "cardiologia",
            "practitioner_id": "Practitioner/789",
            "proposed_date": proposed_date.isoformat(),
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be consistent
        assert result1["pre_auth_required"] == result2["pre_auth_required"]
        assert result1["authorization_status"] == result2["authorization_status"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.check_pre_authorization_worker import (
            PatientAccessException,
        )

        proposed_date = datetime.utcnow() + timedelta(days=7)

        # Mock failure
        worker.pre_auth_checker.check_pre_authorization = AsyncMock(
            side_effect=Exception("Insurance provider API unavailable")
        )

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "patient_id": "Patient/123",
                    "coverage_id": "Coverage/456",
                    "service_type": "cirurgia",
                    "procedure_codes": ["40101010"],
                    "specialty_code": "cardiologia",
                    "practitioner_id": "Practitioner/789",
                    "proposed_date": proposed_date.isoformat(),
                }
            )

    @pytest.mark.asyncio
    async def test_authorization_details_structure(self, worker, tenant_austa):
        """Test authorization details contain required fields."""
        proposed_date = datetime.utcnow() + timedelta(days=7)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "coverage_id": "Coverage/456",
                "service_type": "cirurgia",
                "procedure_codes": ["40101010"],
                "specialty_code": "cardiologia",
                "practitioner_id": "Practitioner/789",
                "proposed_date": proposed_date.isoformat(),
                "estimated_cost": 5000.00,
            }
        )

        # Check authorization details structure
        assert result["authorization_details"] is not None
        auth_details = result["authorization_details"]
        assert "authorization_number" in auth_details
        assert "status" in auth_details
        assert "approved_date" in auth_details
        assert "expiration_date" in auth_details
        assert "approved_procedures" in auth_details

    @pytest.mark.asyncio
    async def test_multiple_procedures_authorization(self, worker, tenant_austa):
        """Test authorization check with multiple procedures."""
        proposed_date = datetime.utcnow() + timedelta(days=7)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "coverage_id": "Coverage/456",
                "service_type": "procedimento",
                "procedure_codes": ["40101010", "40201020", "40301030"],  # Multiple high-cost
                "specialty_code": "cardiologia",
                "practitioner_id": "Practitioner/789",
                "proposed_date": proposed_date.isoformat(),
            }
        )

        # Should require authorization
        assert result["pre_auth_required"] is True
        assert len(result["authorization_details"]["approved_procedures"]) == 3
