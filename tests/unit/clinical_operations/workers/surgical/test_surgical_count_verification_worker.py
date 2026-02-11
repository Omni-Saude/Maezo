"""
Unit tests for Surgical Count Verification Worker.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker import (
    CountItem,
    SurgicalCountVerificationInput,
    SurgicalCountVerificationOutput,
    SurgicalCountVerificationWorker,
    SurgicalOperationsException,
)


@pytest.mark.unit
class TestSurgicalCountVerificationWorker:
    """Unit tests for SurgicalCountVerificationWorker."""

    @pytest.fixture
    def mock_tasy_adapter(self):
        """Create a mock TASY adapter."""
        adapter = AsyncMock()
        adapter.record_surgical_count_verification = AsyncMock(return_value=True)
        return adapter

    @pytest.fixture
    def worker(self, mock_tasy_adapter):
        """Create a worker instance with mocked adapter."""
        return SurgicalCountVerificationWorker(tasy_adapter=mock_tasy_adapter)

    @pytest.fixture
    def base_count_item(self) -> Dict[str, Any]:
        """Base count item data."""
        return {
            "item_type": "sponge",
            "item_name": "Laparotomy Sponge",
            "initial_count": 5,
            "final_count": 5,
            "counted_by_primary": "PRAC001",
            "counted_by_secondary": "PRAC002",
            "count_confirmed": True
        }

    @pytest.fixture
    def base_input_data(self, base_count_item) -> Dict[str, Any]:
        """Base input data for verification."""
        return {
            "surgery_id": "SURG-12345",
            "patient_id": "PAT-67890",
            "count_phase": "final",
            "items": [base_count_item],
            "who_checklist_phase": "sign_out"
        }

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_execute_all_counts_correct(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test verification when all counts are correct."""
        mock_get_tenant.return_value = "tenant-123"

        # Add multiple items, all correct
        base_input_data["items"] = [
            {
                "item_type": "sponge",
                "item_name": "Laparotomy Sponge",
                "initial_count": 5,
                "final_count": 5,
                "counted_by_primary": "PRAC001",
                "counted_by_secondary": "PRAC002",
                "count_confirmed": True
            },
            {
                "item_type": "instrument",
                "item_name": "Hemostat",
                "initial_count": 3,
                "final_count": 3,
                "counted_by_primary": "PRAC001",
                "counted_by_secondary": "PRAC002",
                "count_confirmed": True
            }
        ]

        result = await worker.execute(base_input_data)

        assert result["all_counts_correct"] is True
        assert result["dual_count_confirmed"] is True
        assert len(result["discrepancies"]) == 0
        assert result["requires_xray"] is False
        assert result["surgery_id"] == "SURG-12345"
        assert result["count_phase"] == "final"

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_sponge_discrepancy_requires_xray(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that sponge discrepancy triggers X-ray requirement."""
        mock_get_tenant.return_value = "tenant-123"

        # Sponge with discrepancy
        base_input_data["items"][0]["initial_count"] = 5
        base_input_data["items"][0]["final_count"] = 4

        result = await worker.execute(base_input_data)

        assert result["all_counts_correct"] is False
        assert result["requires_xray"] is True
        assert len(result["discrepancies"]) == 1

        discrepancy = result["discrepancies"][0]
        assert discrepancy["item_type"] == "sponge"
        assert discrepancy["initial_count"] == 5
        assert discrepancy["final_count"] == 4
        assert discrepancy["difference"] == 1

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_instrument_discrepancy_no_xray(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that instrument discrepancy does NOT trigger X-ray."""
        mock_get_tenant.return_value = "tenant-123"

        # Change to instrument with discrepancy
        base_input_data["items"][0]["item_type"] = "instrument"
        base_input_data["items"][0]["item_name"] = "Hemostat"
        base_input_data["items"][0]["initial_count"] = 3
        base_input_data["items"][0]["final_count"] = 2

        result = await worker.execute(base_input_data)

        assert result["all_counts_correct"] is False
        assert result["requires_xray"] is False  # Only sponge/needle trigger X-ray
        assert len(result["discrepancies"]) == 1

        discrepancy = result["discrepancies"][0]
        assert discrepancy["item_type"] == "instrument"
        assert discrepancy["difference"] == 1

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_needle_discrepancy_requires_xray(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that needle discrepancy triggers X-ray requirement."""
        mock_get_tenant.return_value = "tenant-123"

        # Change to needle with discrepancy
        base_input_data["items"][0]["item_type"] = "needle"
        base_input_data["items"][0]["item_name"] = "Suture Needle"
        base_input_data["items"][0]["initial_count"] = 10
        base_input_data["items"][0]["final_count"] = 9

        result = await worker.execute(base_input_data)

        assert result["all_counts_correct"] is False
        assert result["requires_xray"] is True
        assert len(result["discrepancies"]) == 1

        discrepancy = result["discrepancies"][0]
        assert discrepancy["item_type"] == "needle"
        assert discrepancy["difference"] == 1

    def test_dual_count_same_person_raises(self, base_count_item):
        """Test that dual count validation rejects same person for both counts."""
        base_count_item["counted_by_secondary"] = "PRAC001"  # Same as primary

        with pytest.raises(ValueError, match="Dual count requirement"):
            CountItem(**base_count_item)

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_dual_count_not_confirmed(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that unconfirmed dual count is flagged."""
        mock_get_tenant.return_value = "tenant-123"

        base_input_data["items"][0]["count_confirmed"] = False

        result = await worker.execute(base_input_data)

        assert result["dual_count_confirmed"] is False
        assert result["all_counts_correct"] is True  # Counts still match

    def test_invalid_count_phase_raises(self, base_input_data):
        """Test that invalid count phase raises validation error."""
        base_input_data["count_phase"] = "invalid"

        with pytest.raises(ValueError, match="count_phase must be one of"):
            SurgicalCountVerificationInput(**base_input_data)

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_multiple_discrepancies(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that multiple discrepancies are all recorded."""
        mock_get_tenant.return_value = "tenant-123"

        base_input_data["items"] = [
            {
                "item_type": "sponge",
                "item_name": "Lap Sponge",
                "initial_count": 5,
                "final_count": 4,
                "counted_by_primary": "PRAC001",
                "counted_by_secondary": "PRAC002",
                "count_confirmed": True
            },
            {
                "item_type": "needle",
                "item_name": "Suture Needle",
                "initial_count": 10,
                "final_count": 8,
                "counted_by_primary": "PRAC001",
                "counted_by_secondary": "PRAC002",
                "count_confirmed": True
            },
            {
                "item_type": "instrument",
                "item_name": "Hemostat",
                "initial_count": 3,
                "final_count": 2,
                "counted_by_primary": "PRAC003",
                "counted_by_secondary": "PRAC004",
                "count_confirmed": True
            }
        ]

        result = await worker.execute(base_input_data)

        assert result["all_counts_correct"] is False
        assert result["requires_xray"] is True  # Sponge and needle discrepancies
        assert len(result["discrepancies"]) == 3

        # Verify all discrepancies are recorded
        item_types = [d["item_type"] for d in result["discrepancies"]]
        assert "sponge" in item_types
        assert "needle" in item_types
        assert "instrument" in item_types

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_verification_id_is_uuid(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that verification_id is a valid UUID."""
        mock_get_tenant.return_value = "tenant-123"

        result = await worker.execute(base_input_data)

        verification_id = result["verification_id"]
        # Should not raise exception if valid UUID
        UUID(verification_id)

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_invalid_input_raises_exception(
        self,
        mock_get_tenant,
        worker
    ):
        """Test that invalid input raises SurgicalOperationsException."""
        mock_get_tenant.return_value = "tenant-123"

        invalid_input = {
            "surgery_id": "SURG-12345",
            # Missing required fields
        }

        with pytest.raises(SurgicalOperationsException, match="Invalid input"):
            await worker.execute(invalid_input)

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_tasy_adapter_called(
        self,
        mock_get_tenant,
        worker,
        base_input_data,
        mock_tasy_adapter
    ):
        """Test that TASY adapter is called with correct parameters."""
        mock_get_tenant.return_value = "tenant-123"

        result = await worker.execute(base_input_data)

        mock_tasy_adapter.record_surgical_count_verification.assert_called_once()
        call_kwargs = mock_tasy_adapter.record_surgical_count_verification.call_args.kwargs

        assert call_kwargs["tenant_id"] == "tenant-123"
        assert call_kwargs["verification_id"] == result["verification_id"]
        assert call_kwargs["surgery_id"] == "SURG-12345"
        assert call_kwargs["patient_id"] == "PAT-67890"
        assert call_kwargs["count_phase"] == "final"

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_tasy_failure_does_not_fail_verification(
        self,
        mock_get_tenant,
        worker,
        base_input_data,
        mock_tasy_adapter
    ):
        """Test that TASY adapter failure doesn't fail the verification."""
        mock_get_tenant.return_value = "tenant-123"
        mock_tasy_adapter.record_surgical_count_verification.side_effect = Exception("TASY error")

        # Should not raise exception
        result = await worker.execute(base_input_data)

        assert result["all_counts_correct"] is True
        assert "verification_id" in result

    @pytest.mark.asyncio
    @patch("healthcare_platform.clinical_operations.workers.surgical.surgical_count_verification_worker.get_required_tenant")
    async def test_counted_by_pairs_recorded(
        self,
        mock_get_tenant,
        worker,
        base_input_data
    ):
        """Test that counter pairs are properly recorded."""
        mock_get_tenant.return_value = "tenant-123"

        base_input_data["items"] = [
            {
                "item_type": "sponge",
                "item_name": "Lap Sponge",
                "initial_count": 5,
                "final_count": 5,
                "counted_by_primary": "PRAC001",
                "counted_by_secondary": "PRAC002",
                "count_confirmed": True
            },
            {
                "item_type": "instrument",
                "item_name": "Hemostat",
                "initial_count": 3,
                "final_count": 3,
                "counted_by_primary": "PRAC003",
                "counted_by_secondary": "PRAC004",
                "count_confirmed": True
            }
        ]

        result = await worker.execute(base_input_data)

        assert len(result["counted_by_pairs"]) == 2

        pairs = result["counted_by_pairs"]
        assert {"primary": "PRAC001", "secondary": "PRAC002", "item": "Lap Sponge"} in pairs
        assert {"primary": "PRAC003", "secondary": "PRAC004", "item": "Hemostat"} in pairs
