"""Tests for SuggestDocumentationImprovementsWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import (
    SuggestDocumentationImprovementsInput,
    SuggestDocumentationImprovementsOutput,
    SuggestDocumentationImprovementsStub,
    DocumentationImprovementError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return SuggestDocumentationImprovementsStub(fhir_client=fhir_client)


@pytest.mark.unit
class TestSuggestDocumentationImprovementsWorker:
    """Test suite for SuggestDocumentationImprovementsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful documentation improvement suggestions."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={
                "chief_complaint": "Chest pain",
                "history": "Patient reports chest pain",
                "physical_exam": "NAD",
                "assessment": "Chest pain evaluation",
                "plan": "Further testing",
            },
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, SuggestDocumentationImprovementsOutput)
        assert result.encounter_id == "enc-123"
        assert isinstance(result.suggestions, list)
        assert result.completeness_score >= Decimal("0")
        assert result.completeness_score <= Decimal("1.0")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            SuggestDocumentationImprovementsInput(
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={},
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_incomplete_documentation(self, worker, tenant_austa):
        """Test suggestions for incomplete documentation."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={
                "chief_complaint": "Chest pain",
                # Missing other sections
            },
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        # Should have lower completeness score
        assert result.completeness_score < Decimal("1.0")
        # Should have suggestions
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_different_analysis_focus(self, worker, tenant_austa):
        """Test different analysis focus options."""
        focuses = ["coding_accuracy", "compliance", "quality_metrics"]

        for focus in focuses:
            input_data = SuggestDocumentationImprovementsInput(
                encounter_id="enc-123",
                patient_id="pat-456",
                clinical_documentation={
                    "chief_complaint": "Chest pain",
                },
                procedure_codes=["10101012"],
                provider_specialty="cardiology",
                analysis_focus=focus,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, SuggestDocumentationImprovementsOutput)

    @pytest.mark.asyncio
    async def test_quality_metrics_calculated(self, worker, tenant_austa):
        """Test that quality metrics are calculated."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={
                "chief_complaint": "Test",
                "history": "Test",
            },
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        assert isinstance(result.quality_metrics, dict)
        assert "completeness_percentage" in result.quality_metrics

    @pytest.mark.asyncio
    async def test_high_priority_suggestions_counted(self, worker, tenant_austa):
        """Test that high priority suggestions are counted."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={
                "physical_exam": "NAD",  # Triggers high priority suggestion
            },
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        assert result.high_priority_count >= 0

    @pytest.mark.asyncio
    async def test_revenue_impact_estimated(self, worker, tenant_austa):
        """Test that revenue impact is estimated."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={},
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        assert result.estimated_revenue_impact >= Decimal("0")

    @pytest.mark.asyncio
    async def test_suggestions_have_categories(self, worker, tenant_austa):
        """Test that suggestions are categorized."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={
                "physical_exam": "NAD",
            },
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        for suggestion in result.suggestions:
            assert suggestion.category in ["missing", "incomplete", "ambiguous"]

    @pytest.mark.asyncio
    async def test_suggestions_have_priorities(self, worker, tenant_austa):
        """Test that suggestions have priorities."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            clinical_documentation={},
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        for suggestion in result.suggestions:
            assert suggestion.priority in ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-999",
            patient_id="pat-999",
            clinical_documentation={},
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, SuggestDocumentationImprovementsOutput)
        assert result.encounter_id == "enc-999"

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent results."""
        input_data = SuggestDocumentationImprovementsInput(
            encounter_id="enc-idem",
            patient_id="pat-idem",
            clinical_documentation={
                "chief_complaint": "Test",
            },
            procedure_codes=["10101012"],
            provider_specialty="cardiology",
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same encounter_id and structure
        assert result1.encounter_id == result2.encounter_id
        assert type(result1.suggestions) == type(result2.suggestions)
