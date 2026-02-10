"""Tests for ArchiveHistoricalDataWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from healthcare_platform.platform_services.workers.archive_historical_data_worker import (
    ArchiveHistoricalDataInput,
    ArchiveHistoricalDataOutput,
    ArchivalException,
    ArchiveHistoricalDataStub,
)


@pytest.fixture
def worker(tenant_austa):
    """Create worker instance."""
    return ArchiveHistoricalDataStub()


@pytest.fixture
def valid_input():
    """Valid input for data archival."""
    return ArchiveHistoricalDataInput(
        entity_type="patient",
        retention_days=2555,
        archive_mode="soft_delete",
        compression="gzip",
        verify_referential_integrity=True,
        anonymize_on_archive=True,
    )


@pytest.mark.unit
class TestArchiveHistoricalDataWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input):
        """Test successful data archival."""
        result = await worker.execute(valid_input)

        assert isinstance(result, ArchiveHistoricalDataOutput)
        assert result.archive_id is not None
        assert result.entity_type == "patient"
        assert result.total_records_archived > 0
        assert result.archive_size_bytes > 0
        assert result.compression == "gzip"

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            ArchiveHistoricalDataInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        worker = ArchiveHistoricalDataStub()
        valid_input = ArchiveHistoricalDataInput(
            entity_type="patient",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_soft_delete_mode(self, worker, tenant_austa):
        """Test soft delete mode."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="encounter",
            archive_mode="soft_delete",
        )

        result = await worker.execute(input_data)

        assert result.total_records_deleted == 0  # Soft delete doesn't physically delete

    @pytest.mark.asyncio
    async def test_hard_delete_mode(self, worker, tenant_austa):
        """Test hard delete mode."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="encounter",
            archive_mode="hard_delete",
        )

        result = await worker.execute(input_data)

        assert result.total_records_deleted > 0

    @pytest.mark.asyncio
    async def test_anonymization_enabled(self, worker, tenant_austa):
        """Test anonymization when enabled."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="patient",
            anonymize_on_archive=True,
        )

        result = await worker.execute(input_data)

        assert len(result.anonymized_fields) > 0

    @pytest.mark.asyncio
    async def test_anonymization_disabled(self, worker, tenant_austa):
        """Test no anonymization when disabled."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="patient",
            anonymize_on_archive=False,
        )

        result = await worker.execute(input_data)

        assert result.anonymized_fields == []

    @pytest.mark.asyncio
    async def test_referential_integrity_check(self, worker, tenant_austa):
        """Test referential integrity verification."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="claim",
            verify_referential_integrity=True,
        )

        result = await worker.execute(input_data)

        assert result.referential_integrity_verified is True

    @pytest.mark.asyncio
    async def test_compression_formats(self, worker, tenant_austa):
        """Test different compression formats."""
        for compression in ["gzip", "snappy", "none"]:
            input_data = ArchiveHistoricalDataInput(
                entity_type="encounter",
                compression=compression,
            )

            result = await worker.execute(input_data)

            assert result.compression == compression

    @pytest.mark.asyncio
    async def test_retention_period(self, worker, tenant_austa):
        """Test retention period configuration."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="audit_log",
            retention_days=365,  # 1 year
        )

        result = await worker.execute(input_data)

        assert result.total_records_archived >= 0

    @pytest.mark.asyncio
    async def test_duration_recorded(self, worker, tenant_austa):
        """Test duration is recorded."""
        input_data = ArchiveHistoricalDataInput(
            entity_type="patient",
        )

        result = await worker.execute(input_data)

        assert result.duration_seconds > 0
