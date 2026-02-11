"""
Unit tests for Surgical Equipment Worker.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from healthcare_platform.clinical_operations.workers.surgical.surgical_equipment_worker import (
    EquipmentItem,
    SurgicalEquipmentInput,
    SurgicalEquipmentOutput,
    SurgicalEquipmentWorker,
    SurgicalOperationsException,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.mark.unit
class TestSurgicalEquipmentWorker:
    """Test suite for SurgicalEquipmentWorker."""

    @pytest.fixture
    def tenant_context(self):
        """Set up tenant context for tests."""
        tenant = TenantContext(
            tenant_id="hospital-123",
            instance_id="prod-instance",
            subscription_tier="premium",
        )
        set_current_tenant(tenant)
        yield tenant
        clear_tenant()

    @pytest.fixture
    def mock_tasy_adapter(self):
        """Create a mock TASY adapter."""
        adapter = MagicMock()
        return adapter

    @pytest.fixture
    def worker(self, mock_tasy_adapter):
        """Create a worker instance."""
        return SurgicalEquipmentWorker(tasy_adapter=mock_tasy_adapter)

    @pytest.fixture
    def base_variables(self) -> dict[str, Any]:
        """Base variables for surgical equipment check."""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        past_date = datetime.now(timezone.utc) - timedelta(days=5)

        return {
            "surgery_id": "SURGERY-001",
            "operating_room_id": "OR-01",
            "procedure_code": "PRO-456",
            "required_equipment": [
                {
                    "equipment_id": "EQ-001",
                    "name": "Surgical Scalpel Set",
                    "category": "instrument",
                    "sterilization_status": "sterile",
                    "sterilization_date": past_date.isoformat(),
                    "expiration_date": future_date.isoformat(),
                    "available": True,
                },
                {
                    "equipment_id": "EQ-002",
                    "name": "Surgical Drapes",
                    "category": "disposable",
                    "sterilization_status": "sterile",
                    "sterilization_date": past_date.isoformat(),
                    "expiration_date": future_date.isoformat(),
                    "available": True,
                },
            ],
            "who_checklist_phase": "time_out",
            "checked_by_practitioner_id": "PRACT-123",
        }

    @pytest.mark.asyncio
    async def test_execute_all_ready(
        self, worker, tenant_context, base_variables
    ):
        """Test equipment check when all equipment is ready."""
        result = await worker.execute(base_variables)

        assert result["surgery_id"] == "SURGERY-001"
        assert result["all_equipment_available"] is True
        assert result["all_sterilization_valid"] is True
        assert result["equipment_ready"] is True
        assert len(result["missing_equipment"]) == 0
        assert len(result["expired_sterilization"]) == 0
        assert result["who_timeout_equipment_confirmed"] is True
        assert "check_id" in result
        assert "check_timestamp" in result

    @pytest.mark.asyncio
    async def test_missing_equipment(
        self, worker, tenant_context, base_variables
    ):
        """Test equipment check when equipment is missing."""
        # Make one equipment unavailable
        base_variables["required_equipment"][0]["available"] = False

        result = await worker.execute(base_variables)

        assert result["all_equipment_available"] is False
        assert result["equipment_ready"] is False
        assert len(result["missing_equipment"]) == 1
        assert "Surgical Scalpel Set" in result["missing_equipment"]
        assert result["who_timeout_equipment_confirmed"] is False

    @pytest.mark.asyncio
    async def test_expired_sterilization(
        self, worker, tenant_context, base_variables
    ):
        """Test equipment check when sterilization is expired."""
        # Set sterilization status to expired
        base_variables["required_equipment"][0]["sterilization_status"] = "expired"

        result = await worker.execute(base_variables)

        assert result["all_sterilization_valid"] is False
        assert result["equipment_ready"] is False
        assert len(result["expired_sterilization"]) == 1
        assert "Surgical Scalpel Set" in result["expired_sterilization"]
        assert result["who_timeout_equipment_confirmed"] is False

    @pytest.mark.asyncio
    async def test_pending_sterilization(
        self, worker, tenant_context, base_variables
    ):
        """Test equipment check when sterilization is pending."""
        # Set sterilization status to pending
        base_variables["required_equipment"][1]["sterilization_status"] = "pending"

        result = await worker.execute(base_variables)

        assert result["all_sterilization_valid"] is False
        assert result["equipment_ready"] is False
        assert result["who_timeout_equipment_confirmed"] is False

    @pytest.mark.asyncio
    async def test_not_required_sterilization_ok(
        self, worker, tenant_context, base_variables
    ):
        """Test equipment that doesn't require sterilization."""
        # Add equipment that doesn't require sterilization
        base_variables["required_equipment"].append(
            {
                "equipment_id": "EQ-003",
                "name": "Monitor Stand",
                "category": "device",
                "sterilization_status": "not_required",
                "sterilization_date": None,
                "expiration_date": None,
                "available": True,
            }
        )

        result = await worker.execute(base_variables)

        assert result["all_equipment_available"] is True
        assert result["all_sterilization_valid"] is True
        assert result["equipment_ready"] is True
        assert result["who_timeout_equipment_confirmed"] is True

    @pytest.mark.asyncio
    async def test_who_timeout_phase(
        self, worker, tenant_context, base_variables
    ):
        """Test WHO checklist phase confirmation."""
        # Change phase to sign_in
        base_variables["who_checklist_phase"] = "sign_in"

        result = await worker.execute(base_variables)

        # Equipment is ready but not in time_out phase
        assert result["equipment_ready"] is True
        assert result["who_timeout_equipment_confirmed"] is False

    @pytest.mark.asyncio
    async def test_check_id_is_uuid(
        self, worker, tenant_context, base_variables
    ):
        """Test that check_id is a valid UUID."""
        result = await worker.execute(base_variables)

        import uuid

        try:
            uuid.UUID(result["check_id"])
            is_valid_uuid = True
        except ValueError:
            is_valid_uuid = False

        assert is_valid_uuid is True

    @pytest.mark.asyncio
    async def test_sterilization_date_expired(
        self, worker, tenant_context, base_variables
    ):
        """Test equipment with expired sterilization date."""
        # Set expiration date to past
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        base_variables["required_equipment"][0]["expiration_date"] = past_date.isoformat()
        base_variables["required_equipment"][0]["sterilization_status"] = "sterile"

        result = await worker.execute(base_variables)

        assert result["all_sterilization_valid"] is False
        assert result["equipment_ready"] is False
        assert "Surgical Scalpel Set" in result["expired_sterilization"]

    @pytest.mark.asyncio
    async def test_multiple_missing_equipment(
        self, worker, tenant_context, base_variables
    ):
        """Test with multiple missing equipment items."""
        # Make both equipment unavailable
        base_variables["required_equipment"][0]["available"] = False
        base_variables["required_equipment"][1]["available"] = False

        result = await worker.execute(base_variables)

        assert result["all_equipment_available"] is False
        assert len(result["missing_equipment"]) == 2
        assert "Surgical Scalpel Set" in result["missing_equipment"]
        assert "Surgical Drapes" in result["missing_equipment"]

    @pytest.mark.asyncio
    async def test_invalid_input(self, worker, tenant_context):
        """Test with invalid input data."""
        invalid_variables = {
            "surgery_id": "SURGERY-001",
            # Missing required fields
        }

        with pytest.raises(SurgicalOperationsException) as exc_info:
            await worker.execute(invalid_variables)

        assert "Invalid surgical equipment input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_equipment_list(
        self, worker, tenant_context, base_variables
    ):
        """Test with empty equipment list."""
        base_variables["required_equipment"] = []

        result = await worker.execute(base_variables)

        assert result["all_equipment_available"] is True
        assert result["all_sterilization_valid"] is True
        assert result["equipment_ready"] is True
        assert len(result["missing_equipment"]) == 0
        assert len(result["expired_sterilization"]) == 0
