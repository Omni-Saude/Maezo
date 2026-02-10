"""Tests for GenerateOptimizationReportWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from healthcare_platform.platform_services.workers.generate_optimization_report_worker import (
    GenerateOptimizationReportInput,
    GenerateOptimizationReportOutput,
    OptimizationReportGenerationError,
    GenerateOptimizationReportWorkerStub,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return GenerateOptimizationReportWorkerStub(fhir_client=fhir_client)


@pytest.fixture
def valid_input():
    """Valid input for optimization report."""
    return GenerateOptimizationReportInput(
        report_period_start=datetime.utcnow() - timedelta(days=30),
        report_period_end=datetime.utcnow(),
        include_revenue_leakage=True,
        include_case_prioritization=True,
        include_resource_utilization=True,
        include_payer_performance=True,
        include_revenue_forecast=True,
        include_roi_tracking=True,
        executive_summary_only=False,
    )


@pytest.mark.unit
class TestGenerateOptimizationReportWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input, tenant_austa):
        """Test successful optimization report generation."""
        result = await worker.execute(valid_input)

        assert isinstance(result, GenerateOptimizationReportOutput)
        assert result.report_id is not None
        assert result.executive_summary is not None
        assert result.kpi_summary is not None
        assert len(result.findings) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            GenerateOptimizationReportInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                GenerateOptimizationReportInput(
                    report_period_start=datetime.utcnow(),
                    report_period_end=datetime.utcnow(),
                )
            )

    @pytest.mark.asyncio
    async def test_revenue_leakage_findings(self, worker, tenant_austa):
        """Test revenue leakage findings."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
            include_revenue_leakage=True,
            include_case_prioritization=False,
            include_resource_utilization=False,
            include_payer_performance=False,
            include_revenue_forecast=False,
            include_roi_tracking=False,
        )

        result = await worker.execute(input_data)

        leakage_findings = [f for f in result.findings if "Perda de Receita" in f.category]
        assert len(leakage_findings) > 0

    @pytest.mark.asyncio
    async def test_resource_utilization_findings(self, worker, tenant_austa):
        """Test resource utilization findings."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
            include_resource_utilization=True,
        )

        result = await worker.execute(input_data)

        resource_findings = [f for f in result.findings if "Recurso" in f.category]
        assert len(resource_findings) >= 0

    @pytest.mark.asyncio
    async def test_implementation_progress(self, worker, tenant_austa):
        """Test implementation progress tracking."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
        )

        result = await worker.execute(input_data)

        progress = result.implementation_progress
        assert progress.total_findings > 0
        assert progress.implemented + progress.in_progress + progress.pending <= progress.total_findings
        assert Decimal("0") <= progress.completion_rate <= Decimal("100")

    @pytest.mark.asyncio
    async def test_kpi_summary(self, worker, tenant_austa):
        """Test KPI summary calculation."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
        )

        result = await worker.execute(input_data)

        kpis = result.kpi_summary
        assert kpis.total_revenue_opportunity > Decimal("0")
        assert kpis.realized_revenue >= Decimal("0")
        assert kpis.cost_savings >= Decimal("0")
        assert kpis.roi >= Decimal("0")

    @pytest.mark.asyncio
    async def test_executive_summary_structure(self, worker, tenant_austa):
        """Test executive summary structure."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
        )

        result = await worker.execute(input_data)

        summary = result.executive_summary
        assert len(summary.key_achievements) >= 0
        assert len(summary.critical_issues) >= 0
        assert len(summary.top_recommendations) > 0
        assert summary.outlook in ["POSITIVE", "NEUTRAL", "CONCERNING"]

    @pytest.mark.asyncio
    async def test_executive_summary_only_mode(self, worker, tenant_austa):
        """Test executive summary only mode."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
            executive_summary_only=True,
        )

        result = await worker.execute(input_data)

        assert result.detailed_sections is None

    @pytest.mark.asyncio
    async def test_full_report_mode(self, worker, tenant_austa):
        """Test full report with detailed sections."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
            executive_summary_only=False,
        )

        result = await worker.execute(input_data)

        assert result.detailed_sections is not None
        assert isinstance(result.detailed_sections, dict)

    @pytest.mark.asyncio
    async def test_finding_priority_levels(self, worker, tenant_austa):
        """Test finding priority levels."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
        )

        result = await worker.execute(input_data)

        for finding in result.findings:
            assert finding.priority in ["HIGH", "MEDIUM", "LOW"]

    @pytest.mark.asyncio
    async def test_finding_status_tracking(self, worker, tenant_austa):
        """Test finding status tracking."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
        )

        result = await worker.execute(input_data)

        for finding in result.findings:
            assert finding.status in [
                "IDENTIFIED",
                "IN_PROGRESS",
                "IMPLEMENTED",
                "CLOSED",
            ]

    @pytest.mark.asyncio
    async def test_next_report_due(self, worker, tenant_austa):
        """Test next report due date."""
        input_data = GenerateOptimizationReportInput(
            report_period_start=datetime.utcnow() - timedelta(days=30),
            report_period_end=datetime.utcnow(),
        )

        result = await worker.execute(input_data)

        assert result.next_report_due > datetime.now()
