"""
from __future__ import annotations

Tests for Generate Appeal Documentation Worker

Tests appeal documentation generation including Portuguese letter templates,
evidence checklists, and regulatory references.
"""

import pytest

from healthcare_platform.revenue_cycle.glosa.workers import GenerateAppealDocumentationWorker
from healthcare_platform.shared.domain.enums import GlosaReasonCode, GlosaType


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker instance with mocked DMN service."""
    return GenerateAppealDocumentationWorker(dmn_service=mock_dmn_service)


@pytest.fixture
def base_variables():
    """Base variables for testing."""
    return {
        "claimId": "CLAIM-2024-001",
        "patientReference": "PAT-12345",
        "providerReference": "PROV-67890",
    }


@pytest.mark.asyncio
async def test_generate_appeal_letter_portuguese(worker, base_variables):
    """Test generation of appeal letter in Portuguese."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.500,00",
            "procedureCode": "40101012",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert "appealLetter" in result.variables
    assert "appealDocumentId" in result.variables

    # Check Portuguese content
    letter = result.variables["appealLetter"]
    assert "RECURSO DE GLOSA" in letter
    assert "Prezados Senhores" in letter
    assert "CLAIM-2024-001" in letter
    assert "ANS RN 424/2017" in letter
    assert "Atenciosamente" in letter

    # Check individual letters
    individual_letters = result.variables["individualLetters"]
    assert len(individual_letters) == 1
    assert "ausência de assinatura" in individual_letters[0]["letter"]


@pytest.mark.asyncio
async def test_evidence_checklist_per_type(worker, base_variables):
    """Test that evidence checklist is generated per glosa type."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.000,00",
        },
        {
            "glosaId": "GLO-002",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION.value,
            "amountBRL": "2.000,00",
        },
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    checklist = result.variables["evidenceChecklist"]

    # Should include items from both ADMINISTRATIVE and TECHNICAL types
    assert any("nota fiscal" in item.lower() for item in checklist)
    assert any("relatório médico" in item.lower() for item in checklist)
    assert any("evolução clínica" in item.lower() for item in checklist)


@pytest.mark.asyncio
async def test_regulatory_references_included(worker, base_variables):
    """Test that regulatory references are included."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    references = result.variables["regulatoryReferences"]

    # Check for key regulatory references
    assert any("ANS RN 424/2017" in ref for ref in references)
    assert any("ANS RN 395/2016" in ref for ref in references)
    assert any("Lei 9.656/98" in ref for ref in references)
    assert any("TISS" in ref for ref in references)


@pytest.mark.asyncio
async def test_empty_eligible_glosas(worker, base_variables):
    """Test error handling when no eligible glosas provided."""
    base_variables["eligibleGlosas"] = []

    result = await worker.process_task(None, base_variables)

    assert result.success is False
    assert "error" in result.variables


@pytest.mark.asyncio
async def test_required_documents_per_reason_code(worker, base_variables):
    """Test that required documents are listed based on reason code."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION.value,
            "amountBRL": "3.000,00",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    required_docs = result.variables["requiredDocuments"]

    # Should include clinical documentation
    assert any("relatório médico" in doc.lower() for doc in required_docs)
    assert any("evolução clínica" in doc.lower() for doc in required_docs)
    assert any("exames complementares" in doc.lower() for doc in required_docs)


@pytest.mark.asyncio
async def test_multiple_glosas_multiple_reasons(worker, base_variables):
    """Test documentation generation for multiple glosas with different reasons."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "800,00",
        },
        {
            "glosaId": "GLO-002",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.INVALID_CODE.value,
            "amountBRL": "1.200,00",
        },
        {
            "glosaId": "GLO-003",
            "type": GlosaType.PARTIAL.value,
            "reasonCode": GlosaReasonCode.DUPLICATE_BILLING.value,
            "amountBRL": "500,00",
        },
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert len(result.variables["individualLetters"]) == 3
    assert "2.500,00" in result.variables["totalAppealAmount"]

    required_docs = result.variables["requiredDocuments"]
    # Should include docs for all three reason codes
    assert len(required_docs) > 0


@pytest.mark.asyncio
async def test_appeal_letter_formatting(worker, base_variables):
    """Test that appeal letter is properly formatted with all sections."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.NOT_COVERED_PROCEDURE.value,
            "amountBRL": "5.000,00",
            "procedureCode": "40201015",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    letter = result.variables["appealLetter"]

    # Check all required sections
    assert "Data:" in letter
    assert "Conta:" in letter
    assert "Paciente:" in letter
    assert "Prestador:" in letter
    assert "RECURSO DE GLOSA" in letter
    assert "BASE LEGAL:" in letter
    assert "Atenciosamente" in letter


@pytest.mark.asyncio
async def test_documentation_complete_flag(worker, base_variables):
    """Test the documentationComplete flag based on required documents."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.000,00",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert "documentationComplete" in result.variables
    assert isinstance(result.variables["documentationComplete"], bool)


@pytest.mark.asyncio
async def test_lack_of_authorization_emergency_template(worker, base_variables):
    """Test emergency/urgency template for lack of authorization."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.LACK_OF_PRIOR_AUTHORIZATION.value,
            "amountBRL": "15.000,00",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    individual_letters = result.variables["individualLetters"]

    # Check for emergency/urgency language
    letter_text = individual_letters[0]["letter"]
    assert "EMERGÊNCIA" in letter_text or "URGÊNCIA" in letter_text
    assert "Lei 9.656/98" in letter_text
    assert "Art. 35-C" in letter_text


@pytest.mark.asyncio
async def test_generation_date_included(worker, base_variables):
    """Test that generation date is included in result."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert "generationDate" in result.variables
    # Should be ISO format
    from datetime import datetime
    datetime.fromisoformat(result.variables["generationDate"].replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_total_appeal_amount_calculation(worker, base_variables):
    """Test accurate calculation of total appeal amount."""
    base_variables["eligibleGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.234,56",
        },
        {
            "glosaId": "GLO-002",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.INVALID_CODE.value,
            "amountBRL": "2.345,67",
        },
    ]

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    # Total should be 1.234,56 + 2.345,67 = 3.580,23
    assert "3.580,23" in result.variables["totalAppealAmount"]
