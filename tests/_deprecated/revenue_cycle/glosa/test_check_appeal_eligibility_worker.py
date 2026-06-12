"""
from __future__ import annotations

Tests for Check Appeal Eligibility Worker

Tests appeal eligibility validation including deadlines, appealability,
and documentation requirements per ANS RN 424/2017.
"""

from datetime import datetime, timedelta, timezone

import pytest

from healthcare_platform.revenue_cycle.glosa.workers import CheckAppealEligibilityWorker
from healthcare_platform.shared.domain.enums import GlosaReasonCode, GlosaType
from healthcare_platform.shared.domain.exceptions import (
    GlosaAppealDeadlineExpired,
    GlosaNotAppealable,
)


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker instance with mocked DMN service."""
    return CheckAppealEligibilityWorker(dmn_service=mock_dmn_service)


@pytest.fixture
def base_variables():
    """Base variables for testing."""
    glosa_date = datetime.now(timezone.utc) - timedelta(days=10)
    return {
        "claimId": "CLAIM-2024-001",
        "glosaDate": glosa_date.isoformat(),
        "availableDocumentation": [
            "medical_authorization",
            "signed_forms",
            "medical_report",
            "clinical_notes",
        ],
    }


@pytest.mark.asyncio
async def test_eligible_within_deadline(worker, base_variables):
    """Test successful eligibility check within deadline."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.500,00",
            "procedureCode": "40101012",
        },
        {
            "glosaId": "GLO-002",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION.value,
            "amountBRL": "2.300,50",
            "procedureCode": "40201015",
        },
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert result.variables["appealEligible"] is True
    assert len(result.variables["eligibleGlosas"]) == 2
    assert len(result.variables["ineligibleGlosas"]) == 0
    assert result.variables["daysRemaining"] > 0
    assert result.variables["daysRemaining"] <= 20  # 30 - 10 days
    assert "3.800,50" in result.variables["totalEligibleAmount"]


@pytest.mark.asyncio
async def test_expired_deadline_raises_error(worker, base_variables):
    """Test that expired deadline raises GlosaAppealDeadlineExpired."""
    # Set glosa date to 35 days ago (past 30-day deadline)
    expired_date = datetime.now(timezone.utc) - timedelta(days=35)
    base_variables["glosaDate"] = expired_date.isoformat()
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.000,00",
        }
    ]

    with pytest.raises(GlosaAppealDeadlineExpired) as exc_info:
        await worker.process_task(None, base_variables)

    assert "Prazo de recurso expirado" in str(exc_info.value)
    assert "ANS RN 424/2017" in str(exc_info.value)


@pytest.mark.asyncio
async def test_total_glosa_not_appealable(worker, base_variables):
    """Test that TOTAL glosa type is not appealable."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TOTAL.value,
            "reasonCode": GlosaReasonCode.LACK_OF_PRIOR_AUTHORIZATION.value,
            "amountBRL": "50.000,00",
        }
    ]

    with pytest.raises(GlosaNotAppealable) as exc_info:
        await worker.process_task(None, base_variables)

    assert "Nenhuma glosa elegível para recurso" in str(exc_info.value)


@pytest.mark.asyncio
async def test_partial_eligibility(worker, base_variables):
    """Test mixed eligibility with some glosas eligible and others not."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.000,00",
        },
        {
            "glosaId": "GLO-002",
            "type": GlosaType.TOTAL.value,
            "reasonCode": GlosaReasonCode.LACK_OF_PRIOR_AUTHORIZATION.value,
            "amountBRL": "50.000,00",
        },
        {
            "glosaId": "GLO-003",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.INVALID_CODE.value,
            "amountBRL": "800,00",
        },
    ]

    # Missing documentation for INVALID_CODE
    base_variables["availableDocumentation"] = [
        "medical_authorization",
        "signed_forms",
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert len(result.variables["eligibleGlosas"]) == 1  # Only GLO-001
    assert len(result.variables["ineligibleGlosas"]) == 2  # GLO-002 and GLO-003
    assert "1.000,00" in result.variables["totalEligibleAmount"]

    # Check ineligibility reasons
    ineligible = result.variables["ineligibleGlosas"]
    total_glosa = next(g for g in ineligible if g["glosaId"] == "GLO-002")
    assert "não são passíveis de recurso" in total_glosa["ineligibilityReason"]

    missing_docs_glosa = next(g for g in ineligible if g["glosaId"] == "GLO-003")
    assert "Documentação obrigatória ausente" in missing_docs_glosa["ineligibilityReason"]
    assert "missingDocumentation" in missing_docs_glosa


@pytest.mark.asyncio
async def test_days_remaining_calculation(worker, base_variables):
    """Test accurate calculation of days remaining until deadline."""
    # Set glosa date to exactly 25 days ago
    glosa_date = datetime.now(timezone.utc) - timedelta(days=25)
    base_variables["glosaDate"] = glosa_date.isoformat()
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    # Should have approximately 5 days remaining (30 - 25)
    assert result.variables["daysRemaining"] >= 4
    assert result.variables["daysRemaining"] <= 6


@pytest.mark.asyncio
async def test_missing_documentation_ineligible(worker, base_variables):
    """Test that glosas with missing required documentation are ineligible."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION.value,
            "amountBRL": "2.000,00",
        }
    ]

    # No documentation available
    base_variables["availableDocumentation"] = []

    with pytest.raises(GlosaNotAppealable):
        await worker.process_task(None, base_variables)


@pytest.mark.asyncio
async def test_empty_glosas_list_error(worker, base_variables):
    """Test that empty glosas list returns error."""
    base_variables["analyzedGlosas"] = []

    result = await worker.process_task(None, base_variables)

    assert result.success is False
    assert result.error_code == "ERR_NO_GLOSAS"
    assert "Nenhuma glosa encontrada" in result.error_message


@pytest.mark.asyncio
async def test_missing_glosa_date_error(worker, base_variables):
    """Test that missing glosa date returns error."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
    ]
    del base_variables["glosaDate"]

    result = await worker.process_task(None, base_variables)

    assert result.success is False
    assert result.error_code == "ERR_MISSING_DATE"
    assert "Data da glosa não informada" in result.error_message


@pytest.mark.asyncio
async def test_invalid_glosa_type_skipped(worker, base_variables):
    """Test that glosas with invalid type are marked ineligible."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": "INVALID_TYPE",
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
    ]

    with pytest.raises(GlosaNotAppealable):
        await worker.process_task(None, base_variables)


@pytest.mark.asyncio
async def test_all_required_documentation_present(worker, base_variables):
    """Test successful eligibility when all required documentation is present."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.INVALID_CODE.value,
            "amountBRL": "1.200,00",
        }
    ]

    # Provide all required documentation for INVALID_CODE
    base_variables["availableDocumentation"] = [
        "procedure_documentation",
        "code_justification",
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert len(result.variables["eligibleGlosas"]) == 1
    assert "1.200,00" in result.variables["totalEligibleAmount"]
