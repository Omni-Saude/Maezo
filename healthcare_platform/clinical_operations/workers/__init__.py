"""Clinical Operations Workers."""
from __future__ import annotations

# Core Clinical Workers - with actual class names
from .adverse_event_detection_worker import AdverseEventDetectionWorker
from .care_planning_worker import CarePlanningWorker
from .care_team_coordination_worker import CareTeamCoordinationWorker
from .clinical_analytics_worker import ClinicalAnalyticsWorker
from .clinical_assessment_worker import ClinicalAssessmentWorker
from .clinical_auditing_worker import ClinicalAuditingWorker
from .clinical_compliance_worker import ClinicalComplianceWorker
from .clinical_decision_support_worker import ClinicalDecisionSupportWorker
from .clinical_documentation_worker import ClinicalDocumentationWorker
from .clinical_outcomes_tracking_worker import ClinicalOutcomesTrackingWorker
from .clinical_pathways_worker import ClinicalPathwaysWorker
from .clinical_protocols_worker import ClinicalProtocolsWorker
from .discharge_planning_worker import DischargePlanningWorker
from .surgical_team_assign_worker import SurgicalTeamAssignWorker
from .doctor_bed_availability_worker import DoctorBedAvailabilityWorker
from .doctor_cme_reminder_worker import DoctorCmeReminderWorker
from .doctor_critical_value_worker import DoctorCriticalValueWorker
from .doctor_discharge_readiness_worker import DoctorDischargeReadinessWorker
from .doctor_followup_completion_worker import DoctorFollowupCompletionWorker
from .doctor_patient_feedback_worker import DoctorPatientFeedbackWorker
from .doctor_patient_recovery_alert_worker import DoctorPatientRecoveryAlertWorker
from .doctor_performance_summary_worker import DoctorPerformanceSummaryWorker
from .doctor_readmission_risk_worker import DoctorReadmissionRiskWorker
from .doctor_referral_status_worker import DoctorReferralStatusWorker
from .doctor_rounds_summary_worker import DoctorRoundsSummaryWorker
from .doctor_specialist_consult_worker import DoctorSpecialistConsultWorker
from .doctor_triage_escalation_worker import DoctorTriageEscalationWorker
from .medication_management_worker import MedicationManagementWorker
from .patient_care_team_intro_worker import PatientCareTeamIntroWorker
from .patient_daily_care_plan_worker import PatientDailyCarePlanWorker
from .patient_followup_reminder_worker import PatientFollowupReminderWorker
from .patient_meal_preference_worker import PatientMealPreferenceWorker
from .patient_medication_adherence_worker import PatientMedicationAdherenceWorker
from .patient_medication_reminder_worker import PatientMedicationReminderWorker
from .patient_recovery_checkin_worker import PatientRecoveryCheckinWorker
from .patient_test_results_worker import PatientTestResultsWorker
from .vital_signs_monitoring_worker import VitalSignsMonitoringWorker

# Surgical Workers
from .surgical.surgical_consent_worker import SurgicalConsentWorker
from .surgical.surgical_team_assignment_worker import SurgicalTeamAssignmentWorker
from .surgical.surgical_checklist_worker import SurgicalChecklistWorker
from .surgical.surgical_site_marking_worker import SurgicalSiteMarkingWorker
from .surgical.surgical_equipment_worker import SurgicalEquipmentWorker
from .surgical.surgical_materials_worker import SurgicalMaterialsWorker
from .surgical.surgical_specimen_worker import SurgicalSpecimenWorker
from .surgical.surgical_count_verification_worker import SurgicalCountVerificationWorker
from .surgical.pre_surgical_checklist_worker import PreSurgicalChecklistWorker
from .surgical.anesthesia_evaluation_worker import AnesthesiaEvaluationWorker
from .surgical.post_op_recovery_worker import PostOpRecoveryWorker
from .surgical.or_scheduling_optimization_worker import ORSchedulingOptimizationWorker
from .surgical.or_turnover_worker import ORTurnoverWorker
from .surgical.surgery_scheduling_worker import SurgerySchedulingWorker
from .surgical.surgeon_preference_card_worker import SurgeonPreferenceCardWorker

__all__ = [
    # Core Clinical Workers
    "AdverseEventDetectionWorker",
    "CarePlanningWorker",
    "CareTeamCoordinationWorker",
    "ClinicalAnalyticsWorker",
    "ClinicalAssessmentWorker",
    "ClinicalAuditingWorker",
    "ClinicalComplianceWorker",
    "ClinicalDecisionSupportWorker",
    "ClinicalDocumentationWorker",
    "ClinicalOutcomesTrackingWorker",
    "ClinicalPathwaysWorker",
    "ClinicalProtocolsWorker",
    "DischargePlanningWorker",
    "DoctorBedAvailabilityWorker",
    "DoctorCmeReminderWorker",
    "DoctorCriticalValueWorker",
    "DoctorDischargeReadinessWorker",
    "DoctorFollowupCompletionWorker",
    "DoctorPatientFeedbackWorker",
    "DoctorPatientRecoveryAlertWorker",
    "DoctorPerformanceSummaryWorker",
    "DoctorReadmissionRiskWorker",
    "DoctorReferralStatusWorker",
    "DoctorRoundsSummaryWorker",
    "DoctorSpecialistConsultWorker",
    "DoctorTriageEscalationWorker",
    "MedicationManagementWorker",
    "PatientCareTeamIntroWorker",
    "PatientDailyCarePlanWorker",
    "PatientFollowupReminderWorker",
    "PatientMealPreferenceWorker",
    "PatientMedicationAdherenceWorker",
    "PatientMedicationReminderWorker",
    "PatientRecoveryCheckinWorker",
    "PatientTestResultsWorker",
    "SurgicalTeamAssignWorker",
    "VitalSignsMonitoringWorker",
    # Surgical Workers (subdirectory)
    "SurgicalConsentWorker",
    "SurgicalTeamAssignmentWorker",
    "SurgicalChecklistWorker",
    "SurgicalSiteMarkingWorker",
    "SurgicalEquipmentWorker",
    "SurgicalMaterialsWorker",
    "SurgicalSpecimenWorker",
    "SurgicalCountVerificationWorker",
    "PreSurgicalChecklistWorker",
    "AnesthesiaEvaluationWorker",
    "PostOpRecoveryWorker",
    "ORSchedulingOptimizationWorker",
    "ORTurnoverWorker",
    "SurgerySchedulingWorker",
    "SurgeonPreferenceCardWorker",
]
