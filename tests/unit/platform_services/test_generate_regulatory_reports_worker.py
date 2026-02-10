"""Tests for GenerateRegulatoryReportsWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from healthcare_platform.platform_services.workers.generate_regulatory_reports_worker import (
    GenerateRegulatoryReportsInput,
    GenerateRegulatoryReportsOutput,
    RegulatoryReportException,
    GenerateRegulatoryReportsStub,
)


@pytest.fixture
def ans_client():
    """Mock ANS client."""
    return AsyncMock()


@pytest.fixture
def worker(ans_client, tenant_austa):
    """Create worker instance."""
    return GenerateRegulatoryReportsStub(ans_client=ans_client)


@pytest.fixture
def valid_input():
    """Valid input for regulatory report generation."""
    return GenerateRegulatoryReportsInput(
        report_type="RN_124_SIP",
        reference_period="2025-01",
        ans_registry_code="123456",
        include_subsidiaries=False,
        output_format="xml",
        auto_submit_ans=False,
    )


@pytest.mark.unit
class TestGenerateRegulatoryReportsWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input):
        """Test successful regulatory report generation."""
        result = await worker.execute(valid_input)

        assert isinstance(result, GenerateRegulatoryReportsOutput)
        assert result.report_id is not None
        assert result.report_type == "RN_124_SIP"
        assert result.reference_period == "2025-01"
        assert len(result.metrics) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            GenerateRegulatoryReportsInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        worker = GenerateRegulatoryReportsStub(ans_client=None)
        valid_input = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-01",
            ans_registry_code="123456",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_all_report_types(self, worker, tenant_austa):
        """Test all regulatory report types."""
        for report_type in [
            "RN_124_SIP",
            "RN_209_UTILIZATION",
            "RN_388_QUALITY",
            "RN_424_TRANSPARENCY",
        ]:
            input_data = GenerateRegulatoryReportsInput(
                report_type=report_type,
                reference_period="2025-01",
                ans_registry_code="123456",
            )

            result = await worker.execute(input_data)

            assert result.report_type == report_type
            assert len(result.metrics) > 0

    @pytest.mark.asyncio
    async def test_metric_structure(self, worker, tenant_austa):
        """Test regulatory metric structure."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_388_QUALITY",
            reference_period="2025-01",
            ans_registry_code="123456",
        )

        result = await worker.execute(input_data)

        if result.metrics:
            metric = result.metrics[0]
            assert metric.metric_code is not None
            assert metric.metric_name is not None
            assert metric.value >= 0
            assert metric.unit is not None
            assert isinstance(metric.compliant, bool)

    @pytest.mark.asyncio
    async def test_compliance_calculation(self, worker, tenant_austa):
        """Test compliance rate calculation."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_388_QUALITY",
            reference_period="2025-01",
            ans_registry_code="123456",
        )

        result = await worker.execute(input_data)

        assert 0 <= result.compliance_rate <= 100

    @pytest.mark.asyncio
    async def test_xml_format(self, worker, tenant_austa):
        """Test XML output format."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-01",
            ans_registry_code="123456",
            output_format="xml",
        )

        result = await worker.execute(input_data)

        assert "xml" in result.file_path

    @pytest.mark.asyncio
    async def test_csv_format(self, worker, tenant_austa):
        """Test CSV output format."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_209_UTILIZATION",
            reference_period="2025-01",
            ans_registry_code="123456",
            output_format="csv",
        )

        result = await worker.execute(input_data)

        assert "csv" in result.file_path

    @pytest.mark.asyncio
    async def test_auto_submit_enabled(self, worker, tenant_austa):
        """Test automatic ANS submission."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-01",
            ans_registry_code="123456",
            auto_submit_ans=True,
        )

        result = await worker.execute(input_data)

        assert result.ans_submission_protocol is not None

    @pytest.mark.asyncio
    async def test_auto_submit_disabled(self, worker, tenant_austa):
        """Test no submission when disabled."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-01",
            ans_registry_code="123456",
            auto_submit_ans=False,
        )

        result = await worker.execute(input_data)

        assert result.ans_submission_protocol is None

    @pytest.mark.asyncio
    async def test_include_subsidiaries(self, worker, tenant_austa):
        """Test including subsidiary data."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-01",
            ans_registry_code="123456",
            include_subsidiaries=True,
        )

        result = await worker.execute(input_data)

        assert result.total_beneficiaries > 0

    @pytest.mark.asyncio
    async def test_reference_period_validation(self, worker, tenant_austa):
        """Test reference period format validation."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-Q1",  # Quarterly format
            ans_registry_code="123456",
        )

        # Should not raise validation error
        result = await worker.execute(input_data)
        assert result is not None

    @pytest.mark.asyncio
    async def test_duration_recorded(self, worker, tenant_austa):
        """Test duration is recorded."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_124_SIP",
            reference_period="2025-01",
            ans_registry_code="123456",
        )

        result = await worker.execute(input_data)

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_operational_data_extraction(self, worker, tenant_austa):
        """Test operational data extraction."""
        input_data = GenerateRegulatoryReportsInput(
            report_type="RN_209_UTILIZATION",
            reference_period="2025-01",
            ans_registry_code="123456",
        )

        result = await worker.execute(input_data)

        assert result.total_beneficiaries > 0
        assert result.total_claims > 0
