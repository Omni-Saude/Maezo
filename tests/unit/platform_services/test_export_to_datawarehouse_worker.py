"""Tests for ExportToDataWarehouseWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import (
    ExportToDataWarehouseInput,
    ExportToDataWarehouseOutput,
    DataWarehouseExportException,
    ExportToDataWarehouseStub,
)


@pytest.fixture
def worker(tenant_austa):
    """Create worker instance."""
    return ExportToDataWarehouseStub()


@pytest.fixture
def valid_input():
    """Valid input for data warehouse export."""
    return ExportToDataWarehouseInput(
        entity_type="patient",
        export_mode="incremental",
        output_format="parquet",
        compression="snappy",
        partition_by=["year", "month"],
        include_deleted=False,
        anonymize_pii=True,
    )


@pytest.mark.unit
class TestExportToDataWarehouseWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input):
        """Test successful data warehouse export."""
        result = await worker.execute(valid_input)

        assert isinstance(result, ExportToDataWarehouseOutput)
        assert result.export_id is not None
        assert result.entity_type == "patient"
        assert result.total_records > 0
        assert len(result.file_paths) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            ExportToDataWarehouseInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        worker = ExportToDataWarehouseStub()
        valid_input = ExportToDataWarehouseInput(
            entity_type="patient",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_incremental_mode(self, worker, tenant_austa):
        """Test incremental export mode."""
        input_data = ExportToDataWarehouseInput(
            entity_type="encounter",
            export_mode="incremental",
        )

        result = await worker.execute(input_data)

        # Incremental should export fewer records than full
        assert result.total_records > 0

    @pytest.mark.asyncio
    async def test_full_mode(self, worker, tenant_austa):
        """Test full export mode."""
        input_data = ExportToDataWarehouseInput(
            entity_type="encounter",
            export_mode="full",
        )

        result = await worker.execute(input_data)

        assert result.total_records > 0

    @pytest.mark.asyncio
    async def test_parquet_format(self, worker, tenant_austa):
        """Test Parquet output format."""
        input_data = ExportToDataWarehouseInput(
            entity_type="claim",
            output_format="parquet",
        )

        result = await worker.execute(input_data)

        assert result.output_format == "parquet"
        for path in result.file_paths:
            assert "parquet" in path

    @pytest.mark.asyncio
    async def test_csv_format(self, worker, tenant_austa):
        """Test CSV output format."""
        input_data = ExportToDataWarehouseInput(
            entity_type="claim",
            output_format="csv",
        )

        result = await worker.execute(input_data)

        assert result.output_format == "csv"

    @pytest.mark.asyncio
    async def test_anonymization_enabled(self, worker, tenant_austa):
        """Test PII anonymization when enabled."""
        input_data = ExportToDataWarehouseInput(
            entity_type="patient",
            anonymize_pii=True,
        )

        result = await worker.execute(input_data)

        assert len(result.anonymized_fields) > 0

    @pytest.mark.asyncio
    async def test_anonymization_disabled(self, worker, tenant_austa):
        """Test no anonymization when disabled."""
        input_data = ExportToDataWarehouseInput(
            entity_type="patient",
            anonymize_pii=False,
        )

        result = await worker.execute(input_data)

        assert result.anonymized_fields == []

    @pytest.mark.asyncio
    async def test_partitioning(self, worker, tenant_austa):
        """Test data partitioning."""
        input_data = ExportToDataWarehouseInput(
            entity_type="encounter",
            partition_by=["year", "month", "tenant_id"],
        )

        result = await worker.execute(input_data)

        assert len(result.partitions) > 0
        # Partitions should have year, month, tenant_id
        partition = result.partitions[0]
        assert "year=" in partition["key"]
        assert "month=" in partition["key"]

    @pytest.mark.asyncio
    async def test_compression_formats(self, worker, tenant_austa):
        """Test different compression formats."""
        for compression in ["snappy", "gzip", "none"]:
            input_data = ExportToDataWarehouseInput(
                entity_type="patient",
                compression=compression,
            )

            result = await worker.execute(input_data)

            # File paths should reflect compression
            for path in result.file_paths:
                if compression != "none":
                    assert compression in path

    @pytest.mark.asyncio
    async def test_include_deleted_records(self, worker, tenant_austa):
        """Test including deleted records."""
        input_data = ExportToDataWarehouseInput(
            entity_type="patient",
            include_deleted=True,
        )

        result = await worker.execute(input_data)

        assert result.total_records > 0

    @pytest.mark.asyncio
    async def test_duration_recorded(self, worker, tenant_austa):
        """Test duration is recorded."""
        input_data = ExportToDataWarehouseInput(
            entity_type="patient",
        )

        result = await worker.execute(input_data)

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_file_size_calculated(self, worker, tenant_austa):
        """Test file size is calculated."""
        input_data = ExportToDataWarehouseInput(
            entity_type="patient",
        )

        result = await worker.execute(input_data)

        assert result.file_size_bytes > 0
