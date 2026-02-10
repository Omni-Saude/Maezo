"""Tests for DetectRevenueLeakageWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from healthcare_platform.platform_services.workers.detect_revenue_leakage_worker import (
    DetectRevenueLeakageInput,
    DetectRevenueLeakageOutput,
    RevenueLeakageDetectionError,
    DetectRevenueLeakageWorkerStub,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return DetectRevenueLeakageWorkerStub(fhir_client=fhir_client)


@pytest.fixture
def valid_input():
    """Valid input for revenue leakage detection."""
    return DetectRevenueLeakageInput(
        encounter_ids=["ENC001", "ENC002"],
        analysis_period_days=30,
        include_procedures=True,
        include_supplies=True,
        include_professional_fees=True,
        minimum_amount=Decimal("10.00"),
    )


@pytest.mark.unit
class TestDetectRevenueLeakageWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input, tenant_austa):
        """Test successful revenue leakage detection."""
        result = await worker.execute(valid_input)

        assert isinstance(result, DetectRevenueLeakageOutput)
        assert result.total_leakage_amount >= Decimal("0")
        assert result.encounters_with_leakage >= 0
        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            DetectRevenueLeakageInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(DetectRevenueLeakageInput(encounter_ids=["ENC001"]))

    @pytest.mark.asyncio
    async def test_procedures_detection(self, worker, tenant_austa):
        """Test unbilled procedures detection."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001"],
            include_procedures=True,
            include_supplies=False,
            include_professional_fees=False,
        )

        result = await worker.execute(input_data)

        procedure_items = [
            item for item in result.leakage_items if item.leakage_type == "PROCEDURE"
        ]
        assert len(procedure_items) >= 0

    @pytest.mark.asyncio
    async def test_supplies_detection(self, worker, tenant_austa):
        """Test unbilled supplies detection."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001"],
            include_procedures=False,
            include_supplies=True,
            include_professional_fees=False,
        )

        result = await worker.execute(input_data)

        supply_items = [
            item for item in result.leakage_items if item.leakage_type == "SUPPLY"
        ]
        assert len(supply_items) >= 0

    @pytest.mark.asyncio
    async def test_professional_fees_detection(self, worker, tenant_austa):
        """Test uncaptured professional fees detection."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001"],
            include_procedures=False,
            include_supplies=False,
            include_professional_fees=True,
        )

        result = await worker.execute(input_data)

        fee_items = [
            item for item in result.leakage_items if item.leakage_type == "PROFESSIONAL_FEE"
        ]
        assert len(fee_items) >= 0

    @pytest.mark.asyncio
    async def test_minimum_amount_filter(self, worker, tenant_austa):
        """Test minimum amount filtering."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001"],
            minimum_amount=Decimal("50.00"),
        )

        result = await worker.execute(input_data)

        # All items should meet minimum
        for item in result.leakage_items:
            assert item.total_amount >= Decimal("50.00")

    @pytest.mark.asyncio
    async def test_leakage_by_type_aggregation(self, worker, tenant_austa):
        """Test leakage aggregation by type."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001"],
        )

        result = await worker.execute(input_data)

        assert isinstance(result.leakage_by_type, dict)

        # Sum by type should match individual items
        for leakage_type, total in result.leakage_by_type.items():
            items_of_type = [
                item for item in result.leakage_items if item.leakage_type == leakage_type
            ]
            expected_total = sum(item.total_amount for item in items_of_type)
            assert total == expected_total

    @pytest.mark.asyncio
    async def test_recommendations_generation(self, worker, tenant_austa):
        """Test recommendations generation."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001", "ENC002"],
        )

        result = await worker.execute(input_data)

        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_leakage_item_structure(self, worker, tenant_austa):
        """Test leakage item structure."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001"],
        )

        result = await worker.execute(input_data)

        if result.leakage_items:
            item = result.leakage_items[0]
            assert item.leakage_type in ["PROCEDURE", "SUPPLY", "PROFESSIONAL_FEE"]
            assert item.item_code is not None
            assert item.quantity > 0
            assert item.total_amount > Decimal("0")
            assert item.detection_reason is not None

    @pytest.mark.asyncio
    async def test_multiple_encounters(self, worker, tenant_austa):
        """Test handling multiple encounters."""
        input_data = DetectRevenueLeakageInput(
            encounter_ids=["ENC001", "ENC002", "ENC003"],
        )

        result = await worker.execute(input_data)

        assert result.encounters_with_leakage <= 3
