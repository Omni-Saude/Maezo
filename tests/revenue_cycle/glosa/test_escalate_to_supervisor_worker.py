"""
Tests for Escalate to Supervisor Worker

Tests human task escalation package creation with priority assignment,
team routing, and systemic issue detection.
"""

import pytest

from platform.revenue_cycle.glosa.workers.escalate_to_supervisor_worker import (
    EscalateToSupervisorWorker,
)
from platform.shared.domain.enums import GlosaReasonCode, GlosaType


@pytest.fixture
def worker():
    """Create worker instance."""
    return EscalateToSupervisorWorker()


@pytest.fixture
def base_variables():
    """Base variables for testing."""
    return {
        "claimId": "CLAIM-2024-001",
        "escalationReason": "Alto impacto financeiro",
    }


@pytest.mark.asyncio
async def test_escalation_high_impact(worker, base_variables):
    """Test escalation for high financial impact (>R$10,000)."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION.value,
            "amountBRL": "15.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "15.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert result.variables["priority"] == "HIGH"
    assert result.variables["requiresHumanDecision"] is True
    assert result.variables["humanTaskType"] == "supervisor_review"
    assert "escalationId" in result.variables
    assert result.variables["escalationId"].startswith("ESC-")


@pytest.mark.asyncio
async def test_escalation_many_glosas(worker, base_variables):
    """Test escalation when there are many glosas (>5)."""
    # Create 7 glosas with smaller amounts
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": f"GLO-{i:03d}",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "800,00",
        }
        for i in range(1, 8)
    ]
    base_variables["totalImpactBRL"] = "5.600,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert result.variables["priority"] == "MEDIUM"  # Total < 10k but > 5k
    escalation_package = result.variables["escalationPackage"]
    assert escalation_package["glosaCount"] == 7


@pytest.mark.asyncio
async def test_priority_assignment(worker, base_variables):
    """Test priority assignment based on impact amount."""
    # Test CRITICAL priority (>R$50,000)
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TOTAL.value,
            "reasonCode": GlosaReasonCode.LACK_OF_PRIOR_AUTHORIZATION.value,
            "amountBRL": "75.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "75.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert result.variables["priority"] == "CRITICAL"
    assert "Diretoria" in result.variables["assignedTeam"]


@pytest.mark.asyncio
async def test_no_escalation_needed(worker, base_variables):
    """Test low priority escalation for low impact and few glosas."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
    ]
    base_variables["totalImpactBRL"] = "500,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert result.variables["priority"] == "LOW"
    assert result.variables["requiresHumanDecision"] is True  # Still human task


@pytest.mark.asyncio
async def test_systemic_issues_detection(worker, base_variables):
    """Test detection of systemic issues from recurring patterns."""
    # Create multiple glosas with same reason code
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": f"GLO-{i:03d}",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "500,00",
        }
        for i in range(1, 6)  # 5 glosas with same reason
    ]
    base_variables["totalImpactBRL"] = "2.500,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert result.variables["systemicIssuesDetected"] is True
    escalation_package = result.variables["escalationPackage"]
    systemic_issues = escalation_package["systemicIssues"]
    assert len(systemic_issues) > 0
    # Should detect recurring reason code
    assert any("recorrente" in issue.get("description", "").lower() for issue in systemic_issues)


@pytest.mark.asyncio
async def test_total_glosa_critical_escalation(worker, base_variables):
    """Test that TOTAL glosa triggers critical escalation."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TOTAL.value,
            "reasonCode": GlosaReasonCode.NOT_COVERED_PROCEDURE.value,
            "amountBRL": "30.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "30.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    escalation_package = result.variables["escalationPackage"]
    systemic_issues = escalation_package["systemicIssues"]

    # Should flag TOTAL glosa as critical systemic issue
    total_issue = next(
        (i for i in systemic_issues if i.get("issueType") == "total_glosa"),
        None
    )
    assert total_issue is not None
    assert total_issue["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_escalation_summary_portuguese(worker, base_variables):
    """Test that escalation summary is in Portuguese."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "8.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "8.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    summary = result.variables["escalationSummary"]

    # Check Portuguese content
    assert "ESCALAÇÃO PARA REVISÃO MANUAL" in summary
    assert "Data:" in summary
    assert "Conta:" in summary
    assert "Prioridade:" in summary
    assert "Valor Total:" in summary
    assert "MOTIVO DA ESCALAÇÃO:" in summary


@pytest.mark.asyncio
async def test_assigned_team_routing(worker, base_variables):
    """Test that team assignment is appropriate for impact level."""
    # MEDIUM impact - should go to coordination
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "7.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "7.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    assert "Coordenação" in result.variables["assignedTeam"]


@pytest.mark.asyncio
async def test_recommended_actions_included(worker, base_variables):
    """Test that recommended actions are included in escalation package."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION.value,
            "amountBRL": "12.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "12.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    escalation_package = result.variables["escalationPackage"]
    actions = escalation_package["recommendedActions"]

    assert len(actions) > 0
    # Should include review action
    assert any("revisar" in action.lower() for action in actions)
    # Should include medical audit recommendation for technical glosa
    assert any("auditoria médica" in action.lower() for action in actions)


@pytest.mark.asyncio
async def test_financial_impact_breakdown(worker, base_variables):
    """Test financial impact breakdown by type and reason."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "1.000,00",
        },
        {
            "glosaId": "GLO-002",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.DUPLICATE_BILLING.value,
            "amountBRL": "2.000,00",
        },
        {
            "glosaId": "GLO-003",
            "type": GlosaType.TECHNICAL.value,
            "reasonCode": GlosaReasonCode.INVALID_CODE.value,
            "amountBRL": "1.500,00",
        },
    ]
    base_variables["totalImpactBRL"] = "4.500,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    escalation_package = result.variables["escalationPackage"]
    breakdown = escalation_package["financialImpactBreakdown"]

    # Check breakdown by type
    assert "byType" in breakdown
    assert GlosaType.ADMINISTRATIVE.value in breakdown["byType"]
    assert breakdown["byType"][GlosaType.ADMINISTRATIVE.value]["count"] == 2

    # Check breakdown by reason
    assert "byReason" in breakdown
    assert GlosaReasonCode.MISSING_SIGNATURE.value in breakdown["byReason"]


@pytest.mark.asyncio
async def test_empty_glosas_handled(worker, base_variables):
    """Test that empty glosas list is handled gracefully."""
    base_variables["analyzedGlosas"] = []
    base_variables["totalImpactBRL"] = "0,00"

    result = await worker.process_task(None, base_variables)

    # Should still succeed but with LOW priority and 0 count
    assert result.success is True
    assert result.variables["priority"] == "LOW"


@pytest.mark.asyncio
async def test_escalation_id_format(worker, base_variables):
    """Test that escalation ID has correct format."""
    base_variables["analyzedGlosas"] = [
        {
            "glosaId": "GLO-001",
            "type": GlosaType.ADMINISTRATIVE.value,
            "reasonCode": GlosaReasonCode.MISSING_SIGNATURE.value,
            "amountBRL": "5.000,00",
        }
    ]
    base_variables["totalImpactBRL"] = "5.000,00"

    result = await worker.process_task(None, base_variables)

    assert result.success is True
    escalation_id = result.variables["escalationId"]
    # Format: ESC-{claimId}-{8-char-hex}
    assert escalation_id.startswith("ESC-CLAIM-2024-001-")
    assert len(escalation_id.split("-")[-1]) == 8  # 8 hex chars
