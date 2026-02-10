"""Tests for DetectDataQualityIssuesWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import (
    execute,
    DetectDataQualityIssuesInput,
    DataQualityException,
    DetectDataQualityIssuesStub,
)


@pytest.fixture
def valid_input():
    """Valid input for data quality detection."""
    return {
        "quality_dimensions": ["completeness", "accuracy"],
        "data_sources": ["tasy", "fhir"],
        "entity_types": ["patient", "encounter"],
        "period_start": datetime.utcnow() - timedelta(days=30),
        "period_end": datetime.utcnow(),
        "severity_threshold": "medium",
    }


@pytest.mark.unit
class TestDetectDataQualityIssuesWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, valid_input, tenant_austa):
        """Test successful data quality detection."""
        result = await execute(valid_input)

        assert "check_id" in result
        assert "issues" in result
        assert "quality_score" in result
        assert 0 <= result["quality_score"] <= 100

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self, tenant_austa):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            await execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await execute({"quality_dimensions": ["completeness"]})

    @pytest.mark.asyncio
    async def test_all_quality_dimensions(self, tenant_austa):
        """Test all quality dimensions."""
        input_data = {
            "quality_dimensions": ["completeness", "accuracy", "timeliness", "consistency"],
            "data_sources": ["tasy"],
            "entity_types": ["patient"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert set(result["dimensions_checked"]) == {
            "completeness",
            "accuracy",
            "timeliness",
            "consistency",
        }

    @pytest.mark.asyncio
    async def test_completeness_check(self, tenant_austa):
        """Test completeness check."""
        service = DetectDataQualityIssuesStub()

        issues = await service.check_completeness(
            "tasy",
            "patient",
            datetime.utcnow() - timedelta(days=30),
            datetime.utcnow(),
        )

        if issues:
            assert issues[0].dimension == "completeness"

    @pytest.mark.asyncio
    async def test_accuracy_check(self, tenant_austa):
        """Test accuracy check."""
        service = DetectDataQualityIssuesStub()

        issues = await service.check_accuracy(
            "fhir",
            "lab_result",
            datetime.utcnow() - timedelta(days=30),
            datetime.utcnow(),
        )

        if issues:
            assert issues[0].dimension == "accuracy"

    @pytest.mark.asyncio
    async def test_timeliness_check(self, tenant_austa):
        """Test timeliness check."""
        service = DetectDataQualityIssuesStub()

        issues = await service.check_timeliness(
            "tasy",
            "encounter",
            datetime.utcnow() - timedelta(days=30),
            datetime.utcnow(),
        )

        if issues:
            assert issues[0].dimension == "timeliness"

    @pytest.mark.asyncio
    async def test_consistency_check(self, tenant_austa):
        """Test consistency check."""
        service = DetectDataQualityIssuesStub()

        issues = await service.check_consistency(
            "patient",
            datetime.utcnow() - timedelta(days=30),
            datetime.utcnow(),
        )

        if issues:
            assert issues[0].dimension == "consistency"

    @pytest.mark.asyncio
    async def test_severity_threshold_filtering(self, tenant_austa):
        """Test severity threshold filtering."""
        input_data = {
            "quality_dimensions": ["completeness", "accuracy"],
            "data_sources": ["tasy"],
            "entity_types": ["patient"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "severity_threshold": "high",
        }

        result = await execute(input_data)

        # Should only include high and critical issues
        for issue in result["issues"]:
            assert issue["severity"] in ["high", "critical"]

    @pytest.mark.asyncio
    async def test_issues_by_severity_count(self, tenant_austa):
        """Test issues by severity counting."""
        input_data = {
            "quality_dimensions": ["completeness"],
            "data_sources": ["tasy"],
            "entity_types": ["patient"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "issues_by_severity" in result
        assert "low" in result["issues_by_severity"]
        assert "medium" in result["issues_by_severity"]
        assert "high" in result["issues_by_severity"]
        assert "critical" in result["issues_by_severity"]

    @pytest.mark.asyncio
    async def test_quality_score_calculation(self, tenant_austa):
        """Test quality score calculation."""
        service = DetectDataQualityIssuesStub()

        issues = []
        total_records = 1000

        score = await service.calculate_quality_score(issues, total_records)

        assert score == 100.0  # No issues = perfect score

    @pytest.mark.asyncio
    async def test_duration_recorded(self, tenant_austa):
        """Test duration is recorded."""
        input_data = {
            "quality_dimensions": ["completeness"],
            "data_sources": ["tasy"],
            "entity_types": ["patient"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "duration_ms" in result
        assert result["duration_ms"] > 0
