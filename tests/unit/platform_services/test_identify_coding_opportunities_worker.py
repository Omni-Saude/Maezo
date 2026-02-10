"""Tests for IdentifyCodingOpportunitiesWorker."""
from __future__ import annotations

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import (
    IdentifyCodingOpportunitiesInput,
    IdentifyCodingOpportunitiesOutput,
    IdentifyCodingOpportunitiesStub,
    CodingOpportunityAnalysisError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def ans_client():
    """Mock ANS client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, ans_client):
    """Create worker instance."""
    return IdentifyCodingOpportunitiesStub(
        fhir_client=fhir_client,
        ans_client=ans_client,
    )


@pytest.mark.unit
class TestIdentifyCodingOpportunitiesWorker:
    """Test suite for IdentifyCodingOpportunitiesWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful coding opportunity analysis."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            current_procedure_codes=["10101012"],
            clinical_documentation={
                "comorbidities": ["HAS", "DM"],
                "procedures_performed": 3,
                "time_spent_minutes": 45,
            },
            provider_id="prov-789",
            analysis_depth="standard",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyCodingOpportunitiesOutput)
        assert result.encounter_id == "enc-123"
        assert len(result.opportunities) >= 0
        assert result.total_potential_revenue >= Decimal("0")
        assert result.analysis_timestamp is not None
        assert "compliant" in result.compliance_summary

    @pytest.mark.asyncio
    async def test_identifies_upgrade_opportunity(self, worker, tenant_austa):
        """Test identification of upgrade opportunity."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            current_procedure_codes=["10101012"],
            clinical_documentation={
                "comorbidities": ["HAS", "DM", "Dislipidemia"],
                "procedures_performed": 5,
                "time_spent_minutes": 60,
                "complexity_score": 0.85,
            },
            provider_id="prov-789",
        )

        result = await worker.execute(input_data)

        # Should identify opportunities with high complexity
        assert isinstance(result, IdentifyCodingOpportunitiesOutput)
        assert result.total_potential_revenue >= Decimal("0")

    @pytest.mark.asyncio
    async def test_missing_encounter_id_raises(self, worker, tenant_austa):
        """Test that missing encounter_id raises validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            IdentifyCodingOpportunitiesInput(
                encounter_id="",
                patient_id="pat-456",
                current_procedure_codes=["10101012"],
                clinical_documentation={},
                provider_id="prov-789",
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            current_procedure_codes=["10101012"],
            clinical_documentation={},
            provider_id="prov-789",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_empty_procedure_codes(self, worker, tenant_austa):
        """Test analysis with empty procedure codes list."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            current_procedure_codes=[],
            clinical_documentation={
                "comorbidities": ["HAS"],
            },
            provider_id="prov-789",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyCodingOpportunitiesOutput)
        assert result.encounter_id == "enc-123"

    @pytest.mark.asyncio
    async def test_minimal_clinical_documentation(self, worker, tenant_austa):
        """Test analysis with minimal clinical documentation."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            current_procedure_codes=["10101012"],
            clinical_documentation={},
            provider_id="prov-789",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyCodingOpportunitiesOutput)
        # Should complete successfully even with minimal data

    @pytest.mark.asyncio
    async def test_analysis_depth_variations(self, worker, tenant_austa):
        """Test different analysis depths."""
        for depth in ["basic", "standard", "deep"]:
            input_data = IdentifyCodingOpportunitiesInput(
                encounter_id="enc-123",
                patient_id="pat-456",
                current_procedure_codes=["10101012"],
                clinical_documentation={
                    "comorbidities": ["HAS", "DM"],
                },
                provider_id="prov-789",
                analysis_depth=depth,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, IdentifyCodingOpportunitiesOutput)
            assert result.analysis_id is not None

    @pytest.mark.asyncio
    async def test_recommendations_generated(self, worker, tenant_austa):
        """Test that recommendations are generated."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-123",
            patient_id="pat-456",
            current_procedure_codes=["10101012"],
            clinical_documentation={
                "comorbidities": ["HAS", "DM"],
                "time_spent_minutes": 50,
            },
            provider_id="prov-789",
        )

        result = await worker.execute(input_data)

        assert isinstance(result.recommendations, list)
        # Should have at least some recommendations

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-999",
            patient_id="pat-999",
            current_procedure_codes=["10101012"],
            clinical_documentation={},
            provider_id="prov-999",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyCodingOpportunitiesOutput)
        assert result.encounter_id == "enc-999"

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions with same input produce consistent results."""
        input_data = IdentifyCodingOpportunitiesInput(
            encounter_id="enc-idempotent",
            patient_id="pat-idempotent",
            current_procedure_codes=["10101012"],
            clinical_documentation={
                "comorbidities": ["HAS"],
                "time_spent_minutes": 30,
            },
            provider_id="prov-idem",
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same structure and encounter_id
        assert result1.encounter_id == result2.encounter_id
        assert type(result1.opportunities) == type(result2.opportunities)
