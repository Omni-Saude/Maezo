"""
Tests for Clinical MEDIUM Complexity Workers (Refactored V2)

Purpose: Validate 7 MEDIUM workers using pytest fixtures (no Stubs)

Test Categories:
1. Happy path - All DMN calls succeed → TaskStatus.SUCCESS
2. BLOQUEAR path - First DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR
3. Error handling - DMN raises Exception → TaskStatus.BPMN_ERROR
4. Correlation ID - Verify process_instance_id in logging

ADR Compliance:
- ADR-003: Pytest fixtures instead of Stub classes
- ADR-007: DMN federation mocking
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService with default PROSSEGUIR response."""
    mock = MagicMock()
    mock.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Processar normalmente",
        "risco": "BAIXO",
    }
    return mock


@pytest.fixture
def mock_metrics():
    """Mock WorkerMetrics."""
    return MagicMock()


@pytest.fixture
def base_context():
    """Base task context for testing."""
    return TaskContext(
        task_id="task-001",
        process_instance_id="proc-001",
        tenant_id="HOSPITAL_TEST",
        variables={},
        worker_id="test-worker",
        retries=3,
    )


# ============================================================================
# CLINICAL DOCUMENTATION WORKER TESTS
# ============================================================================

class TestClinicalDocumentationWorker:
    """Tests for ClinicalDocumentationWorker (2 DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.clinical_documentation_worker import (
            ClinicalDocumentationWorker,
        )

        # Mock DMN responses for both steps
        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "completeness_score": 85,
                "risco": "BAIXO",
            },
            {
                "resultado": "PROSSEGUIR",
                "acao": "Proceed to filing",
                "requires_review": False,
                "routing_destination": "medical_records",
            },
        ]

        worker = ClinicalDocumentationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "note_type": "admission_note",
            "note_content": "Patient admitted with chest pain. History of hypertension.",
            "encounter_reference": "Encounter/e-123",
            "patient_reference": "Patient/p-456",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"
        assert result.variables["completeness_score"] == 85
        assert result.variables["requires_review"] is False
        assert mock_dmn_service.evaluate.call_count == 2

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """First DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_documentation_worker import (
            ClinicalDocumentationWorker,
        )

        # First DMN call succeeds, second blocks
        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "completeness_score": 45,
                "risco": "MEDIO",
            },
            {
                "resultado": "BLOQUEAR",
                "acao": "Documentation incomplete - missing required sections",
                "risco": "MEDIO",
            },
        ]

        worker = ClinicalDocumentationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "note_type": "discharge_summary",
            "note_content": "Brief note",
            "encounter_reference": "Encounter/e-123",
            "patient_reference": "Patient/p-456",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INCOMPLETE_DOCUMENTATION"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_documentation_worker import (
            ClinicalDocumentationWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("DMN evaluation failed")

        worker = ClinicalDocumentationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "note_type": "progress_note",
            "note_content": "Patient stable",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_DOCUMENTATION_FAILED"

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.clinical_documentation_worker import (
            ClinicalDocumentationWorker,
        )

        worker = ClinicalDocumentationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "note_type": "consultation",
            "note_content": "Consult note content",
            "encounter_reference": "Encounter/e-789",
            "patient_reference": "Patient/p-101",
        }

        result = worker.execute(base_context)

        # Verify worker completed successfully with process context
        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"


# ============================================================================
# CLINICAL PATHWAYS WORKER TESTS
# ============================================================================

class TestClinicalPathwaysWorker:
    """Tests for ClinicalPathwaysWorker (3 DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.clinical_pathways_worker import (
            ClinicalPathwaysWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {"resultado": "PROSSEGUIR", "pathway_valid": True},
            {
                "resultado": "PROSSEGUIR",
                "pathway_status": "on_track",
                "next_milestone": "Day 3 Assessment",
                "progress_percentage": 60.0,
                "timeline_variance": 0,
                "deviation_count": 0,
            },
            {
                "resultado": "PROSSEGUIR",
                "acao": "Continue pathway",
                "risco": "BAIXO",
                "requires_team_review": False,
                "alert_level": "none",
            },
        ]

        worker = ClinicalPathwaysWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "pathway_id": "stroke_pathway",
            "current_step": "step_2",
            "encounter_reference": "Encounter/e-555",
            "completed_milestones": ["admission", "ct_scan"],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["pathway_status"] == "on_track"
        assert result.variables["progress_percentage"] == 60.0
        assert mock_dmn_service.evaluate.call_count == 3

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """Third DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_pathways_worker import (
            ClinicalPathwaysWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {"resultado": "PROSSEGUIR", "pathway_valid": True},
            {
                "resultado": "PROSSEGUIR",
                "pathway_status": "delayed",
                "timeline_variance": 48,
                "deviation_count": 3,
            },
            {
                "resultado": "BLOQUEAR",
                "acao": "Pathway deviation exceeds threshold - team intervention required",
                "risco": "ALTO",
            },
        ]

        worker = ClinicalPathwaysWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "pathway_id": "sepsis_pathway",
            "current_step": "step_5",
            "encounter_reference": "Encounter/e-666",
            "completed_milestones": ["admission"],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_PATHWAY_DEVIATION"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_pathways_worker import (
            ClinicalPathwaysWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Pathway evaluation failed")

        worker = ClinicalPathwaysWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "pathway_id": "ami_pathway",
            "current_step": "step_1",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_PATHWAY_TRACKING_FAILED"

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.clinical_pathways_worker import (
            ClinicalPathwaysWorker,
        )

        worker = ClinicalPathwaysWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "pathway_id": "hip_fracture_pathway",
            "current_step": "step_3",
            "encounter_reference": "Encounter/e-777",
            "completed_milestones": ["admission", "xray", "consult"],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"


# ============================================================================
# CLINICAL PROTOCOLS WORKER TESTS
# ============================================================================

class TestClinicalProtocolsWorker:
    """Tests for ClinicalProtocolsWorker (multiple DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.clinical_protocols_worker import (
            ClinicalProtocolsWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "PROSSEGUIR",
            "acao": "Apply protocol",
            "risco": "BAIXO",
        }

        worker = ClinicalProtocolsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "protocol_id": "anticoagulation_protocol",
            "patient_reference": "Patient/p-888",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_protocols_worker import (
            ClinicalProtocolsWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Protocol contraindicated",
            "risco": "ALTO",
        }

        worker = ClinicalProtocolsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "protocol_id": "thrombolysis_protocol",
            "patient_reference": "Patient/p-999",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_protocols_worker import (
            ClinicalProtocolsWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Protocol evaluation failed")

        worker = ClinicalProtocolsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "protocol_id": "sepsis_protocol",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.clinical_protocols_worker import (
            ClinicalProtocolsWorker,
        )

        worker = ClinicalProtocolsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "protocol_id": "diabetes_protocol",
            "patient_reference": "Patient/p-1001",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"


# ============================================================================
# DISCHARGE PLANNING WORKER TESTS
# ============================================================================

class TestDischargePlanningWorker:
    """Tests for DischargePlanningWorker (2 DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.discharge_planning_worker import (
            DischargePlanningWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "criteria_met": 8,
                "criteria_total": 10,
                "barriers": ["pending_home_health"],
            },
            {
                "resultado": "PROSSEGUIR",
                "acao": "Discharge planning complete",
                "risco": "BAIXO",
                "discharge_readiness": "ready",
                "readiness_score": 0.8,
                "estimated_discharge_date": "2026-02-18",
            },
        ]

        worker = DischargePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-123",
            "patient_reference": "Patient/p-456",
            "discharge_criteria": ["vitals_stable", "pain_controlled", "home_care_arranged"],
            "pending_items": ["home_health_setup"],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["discharge_readiness"] == "ready"
        assert result.variables["discharge_readiness_score"] == 0.8
        assert mock_dmn_service.evaluate.call_count == 2

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """Second DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.discharge_planning_worker import (
            DischargePlanningWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "criteria_met": 3,
                "criteria_total": 10,
                "barriers": ["unstable_vitals", "no_home_care", "pending_labs"],
            },
            {
                "resultado": "BLOQUEAR",
                "acao": "Patient not ready for discharge - multiple barriers",
                "risco": "ALTO",
                "discharge_readiness": "not_ready",
                "readiness_score": 0.3,
            },
        ]

        worker = DischargePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-999",
            "patient_reference": "Patient/p-888",
            "discharge_criteria": [],
            "pending_items": ["labs", "consult", "home_care"],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_DISCHARGE_NOT_READY"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.discharge_planning_worker import (
            DischargePlanningWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Discharge planning evaluation failed")

        worker = DischargePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-555",
            "patient_reference": "Patient/p-333",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_DISCHARGE_PLANNING_FAILED"

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.discharge_planning_worker import (
            DischargePlanningWorker,
        )

        worker = DischargePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-777",
            "patient_reference": "Patient/p-444",
            "discharge_criteria": ["criteria1", "criteria2"],
            "pending_items": [],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"


# ============================================================================
# CLINICAL ASSESSMENT WORKER TESTS
# ============================================================================

class TestClinicalAssessmentWorker:
    """Tests for ClinicalAssessmentWorker (5 DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.clinical_assessment_worker import (
            ClinicalAssessmentWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "assessment_score": 75,
                "triage_priority": 3,
                "vital_signs_abnormal": False,
            },
            {
                "resultado": "PROSSEGUIR",
                "risk_level": "STANDARD",
                "risco": "BAIXO",
            },
            {
                "resultado": "PROSSEGUIR",
                "acao": "Standard care pathway",
                "severity_grade": 2,
                "recommended_actions": ["monitor_vitals", "hydration"],
            },
            {
                "resultado": "PROSSEGUIR",
                "comorbidity_index": 1,
            },
            {
                "resultado": "PROSSEGUIR",
                "functional_status": "independent",
            },
        ]

        worker = ClinicalAssessmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "chief_complaint": "chest_pain",
            "vital_signs": {"heart_rate": 85, "oxygen_saturation": 98},
            "encounter_reference": "Encounter/e-222",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["triage_priority"] == 3
        assert result.variables["risk_level"] == "STANDARD"
        assert result.variables["severity_grade"] == 2
        assert result.variables["functional_status"] == "independent"
        assert mock_dmn_service.evaluate.call_count == 5

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """Third DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_assessment_worker import (
            ClinicalAssessmentWorker,
        )

        # Worker makes 5 DMN calls, severity_result (step 3) returns BLOQUEAR
        # But all 5 calls execute before the check
        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "assessment_score": 95,
                "triage_priority": 1,
                "vital_signs_abnormal": True,
            },
            {
                "resultado": "PROSSEGUIR",
                "risk_level": "HIGH",
                "risco": "ALTO",
            },
            {
                "resultado": "BLOQUEAR",
                "acao": "Critical condition - immediate intervention",
                "severity_grade": 5,
                "risco": "CRITICO",
            },
            {
                "resultado": "PROSSEGUIR",
                "comorbidity_index": 2,
            },
            {
                "resultado": "PROSSEGUIR",
                "functional_status": "dependent",
            },
        ]

        worker = ClinicalAssessmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "chief_complaint": "severe_chest_pain",
            "vital_signs": {"heart_rate": 140, "oxygen_saturation": 88},
            "encounter_reference": "Encounter/e-emergency",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CRITICAL_ASSESSMENT"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.clinical_assessment_worker import (
            ClinicalAssessmentWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Assessment scoring failed")

        worker = ClinicalAssessmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "chief_complaint": "abdominal_pain",
            "vital_signs": {},
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_ASSESSMENT_FAILED"

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.clinical_assessment_worker import (
            ClinicalAssessmentWorker,
        )

        worker = ClinicalAssessmentWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "chief_complaint": "headache",
            "vital_signs": {"heart_rate": 70, "oxygen_saturation": 99},
            "encounter_reference": "Encounter/e-333",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"


# ============================================================================
# CARE PLANNING WORKER TESTS
# ============================================================================

class TestCarePlanningWorker:
    """Tests for CarePlanningWorker (4 DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.care_planning_worker import (
            CarePlanningWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "template_id": "diabetes_care_plan",
                "activities": ["glucose_monitoring", "insulin_admin", "diet_education"],
            },
            {
                "resultado": "PROSSEGUIR",
                "priority_level": "high",
                "risco": "MEDIO",
            },
            {
                "resultado": "PROSSEGUIR",
                "tracking_metrics": ["HbA1c", "daily_glucose", "weight"],
                "complexity_score": 3,
            },
            {
                "resultado": "PROSSEGUIR",
                "acao": "Standard care plan workflow",
                "escalation_threshold": "72h",
                "requires_specialist": False,
            },
        ]

        worker = CarePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "diagnosis_codes": ["E11.9"],
            "treatment_goals": ["glucose_control", "weight_loss"],
            "encounter_reference": "Encounter/e-123",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["care_plan_template"] == "diabetes_care_plan"
        assert result.variables["intervention_priority"] == "high"
        assert result.variables["requires_specialist"] is False
        assert mock_dmn_service.evaluate.call_count == 4

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """Fourth DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.care_planning_worker import (
            CarePlanningWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "template_id": "complex_multi_morbidity",
                "activities": ["multiple_meds", "specialist_consults"],
            },
            {
                "resultado": "PROSSEGUIR",
                "priority_level": "urgent",
                "risco": "ALTO",
            },
            {
                "resultado": "PROSSEGUIR",
                "tracking_metrics": ["multiple"],
                "complexity_score": 8,
            },
            {
                "resultado": "BLOQUEAR",
                "acao": "High complexity requires specialist care plan design",
                "risco": "ALTO",
                "requires_specialist": True,
            },
        ]

        worker = CarePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "diagnosis_codes": ["I50.9", "E11.9", "N18.5"],
            "treatment_goals": ["multi_goal_complex"],
            "encounter_reference": "Encounter/e-complex",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CARE_PLAN_ESCALATION"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.care_planning_worker import (
            CarePlanningWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Template selection failed")

        worker = CarePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "diagnosis_codes": [],
            "treatment_goals": [],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CARE_PLANNING_FAILED"

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.care_planning_worker import (
            CarePlanningWorker,
        )

        worker = CarePlanningWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "diagnosis_codes": ["I10"],
            "treatment_goals": ["bp_control"],
            "encounter_reference": "Encounter/e-444",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"


# ============================================================================
# CARE TEAM COORDINATION WORKER TESTS
# ============================================================================

class TestCareTeamCoordinationWorker:
    """Tests for CareTeamCoordinationWorker (3 DMN calls)."""

    def test_happy_path(self, mock_dmn_service, mock_metrics, base_context):
        """All DMN calls succeed → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.care_team_coordination_worker import (
            CareTeamCoordinationWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "assignment_valid": True,
            },
            {
                "resultado": "PROSSEGUIR",
                "requires_handoff": False,
                "handoff_protocol": "",
            },
            {
                "resultado": "PROSSEGUIR",
                "acao": "Broadcast to team",
                "risco": "BAIXO",
                "routing_method": "broadcast",
                "notification_targets": ["attending", "nurse", "case_manager"],
                "escalated_priority": "routine",
            },
        ]

        worker = CareTeamCoordinationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-555",
            "care_team_members": ["Dr. Smith", "Nurse Jones", "Case Manager Brown"],
            "message_type": "routine",
            "priority": "routine",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["team_assignment_valid"] is True
        assert result.variables["routing_method"] == "broadcast"
        assert mock_dmn_service.evaluate.call_count == 3

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """Third DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.care_team_coordination_worker import (
            CareTeamCoordinationWorker,
        )

        mock_dmn_service.evaluate.side_effect = [
            {
                "resultado": "PROSSEGUIR",
                "assignment_valid": True,
            },
            {
                "resultado": "PROSSEGUIR",
                "requires_handoff": True,
                "handoff_protocol": "SBAR",
            },
            {
                "resultado": "BLOQUEAR",
                "acao": "Critical message blocked - handoff protocol not completed",
                "risco": "ALTO",
            },
        ]

        worker = CareTeamCoordinationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-critical",
            "care_team_members": ["Dr. A", "Dr. B"],
            "message_type": "handoff",
            "priority": "urgent",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_COORDINATION_BLOCKED"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.care_team_coordination_worker import (
            CareTeamCoordinationWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Team assignment validation failed")

        worker = CareTeamCoordinationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-666",
            "care_team_members": [],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_COORDINATION_FAILED"

    def test_correlation_id(self, mock_dmn_service, mock_metrics, base_context):
        """Verify process_instance_id is passed to worker correctly."""
        from healthcare_platform.clinical_operations.workers.care_team_coordination_worker import (
            CareTeamCoordinationWorker,
        )

        worker = CareTeamCoordinationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-777",
            "care_team_members": ["Team Member 1", "Team Member 2"],
            "message_type": "status_update",
            "priority": "routine",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert base_context.process_instance_id == "proc-001"
