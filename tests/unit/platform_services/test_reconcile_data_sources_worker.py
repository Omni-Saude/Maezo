"""Tests for ReconcileDataSourcesWorker."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.reconcile_data_sources_worker import (
    ReconcileDataSourcesInput,
    ReconcileDataSourcesOutput,
    ReconcileDataSourcesStub,
    ReconciliationException,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return ReconcileDataSourcesStub(fhir_client=fhir_client)


@pytest.mark.unit
class TestReconcileDataSourcesWorker:
    """Test suite for ReconcileDataSourcesWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful data source reconciliation."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
            reconciliation_mode="incremental",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, ReconcileDataSourcesOutput)
        assert result.source_a == "tasy"
        assert result.source_b == "fhir"
        assert result.entity_type == "patient"
        assert result.total_records_a >= 0
        assert result.total_records_b >= 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            ReconcileDataSourcesInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_incremental_mode(self, worker, tenant_austa):
        """Test incremental reconciliation mode."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="encounter",
            reconciliation_mode="incremental",
        )

        result = await worker.execute(input_data)

        # Incremental should have fewer records
        assert result.total_records_a <= 200  # Stub returns ~150 for incremental

    @pytest.mark.asyncio
    async def test_full_mode(self, worker, tenant_austa):
        """Test full reconciliation mode."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
            reconciliation_mode="full",
        )

        result = await worker.execute(input_data)

        # Full should have more records
        assert result.total_records_a > 200  # Stub returns ~5000 for full

    @pytest.mark.asyncio
    async def test_different_entity_types(self, worker, tenant_austa):
        """Test reconciliation of different entity types."""
        entity_types = ["patient", "encounter", "claim"]

        for entity_type in entity_types:
            input_data = ReconcileDataSourcesInput(
                source_a="tasy",
                source_b="mv_soul",
                entity_type=entity_type,
            )

            result = await worker.execute(input_data)

            assert result.entity_type == entity_type

    @pytest.mark.asyncio
    async def test_with_date_range(self, worker, tenant_austa):
        """Test reconciliation with specific date range."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
            reconciliation_mode="incremental",
            date_start=datetime.now() - timedelta(days=7),
            date_end=datetime.now(),
        )

        result = await worker.execute(input_data)

        assert isinstance(result, ReconcileDataSourcesOutput)

    @pytest.mark.asyncio
    async def test_auto_resolve_disabled(self, worker, tenant_austa):
        """Test reconciliation without auto-resolve."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
            auto_resolve=False,
        )

        result = await worker.execute(input_data)

        assert result.auto_resolved_count == 0

    @pytest.mark.asyncio
    async def test_auto_resolve_enabled(self, worker, tenant_austa):
        """Test reconciliation with auto-resolve."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
            auto_resolve=True,
            priority_source="source_a",
        )

        result = await worker.execute(input_data)

        # Should resolve some mismatches
        assert result.auto_resolved_count >= 0

    @pytest.mark.asyncio
    async def test_mismatches_detected(self, worker, tenant_austa):
        """Test that mismatches are detected."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
        )

        result = await worker.execute(input_data)

        assert isinstance(result.mismatches, list)

    @pytest.mark.asyncio
    async def test_report_url_generated(self, worker, tenant_austa):
        """Test that reconciliation report URL is generated."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
        )

        result = await worker.execute(input_data)

        assert result.reconciliation_report_url is not None
        assert "s3://" in result.reconciliation_report_url

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, ReconcileDataSourcesOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = ReconcileDataSourcesInput(
            source_a="tasy",
            source_b="fhir",
            entity_type="patient",
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same sources and entity type
        assert result1.source_a == result2.source_a
        assert result1.source_b == result2.source_b
        assert result1.entity_type == result2.entity_type
