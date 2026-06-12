"""Patient Access Workers - V2 Pattern."""
from __future__ import annotations

from healthcare_platform.patient_access.workers.assign_medical_record_number_worker import AssignMedicalRecordNumberWorkerV2
from healthcare_platform.patient_access.workers.assign_resources_worker import AssignResourcesWorkerV2
from healthcare_platform.patient_access.workers.calculate_estimated_duration_worker import CalculateEstimatedDurationWorkerV2
from healthcare_platform.patient_access.workers.capture_demographics_worker import CaptureDemographicsWorkerV2
from healthcare_platform.patient_access.workers.check_authorization_requirements_worker import CheckAuthorizationRequirementsWorkerV2
from healthcare_platform.patient_access.workers.check_availability_worker import CheckAvailabilityWorkerV2
from healthcare_platform.patient_access.workers.check_existing_patient_worker import CheckExistingPatientWorkerV2
from healthcare_platform.patient_access.workers.check_pre_authorization_worker import CheckPreAuthorizationWorkerV2
from healthcare_platform.patient_access.workers.create_appointment_worker import CreateAppointmentWorkerV2
from healthcare_platform.patient_access.workers.create_patient_record_worker import CreatePatientRecordWorkerV2
from healthcare_platform.patient_access.workers.doctor_patient_arrival_worker import DoctorPatientArrivalWorkerV2
from healthcare_platform.patient_access.workers.generate_patient_card_worker import GeneratePatientCardWorkerV2
from healthcare_platform.patient_access.workers.generate_pre_admission_checklist_worker import GeneratePreAdmissionChecklistWorkerV2
from healthcare_platform.patient_access.workers.handle_cancellation_worker import HandleCancellationWorkerV2
from healthcare_platform.patient_access.workers.notify_registration_complete_worker import NotifyRegistrationCompleteWorkerV2
from healthcare_platform.patient_access.workers.patient_birthday_worker import PatientBirthdayWorkerV2
from healthcare_platform.patient_access.workers.patient_emergency_wait_update_worker import PatientEmergencyWaitUpdateWorkerV2
from healthcare_platform.patient_access.workers.patient_health_anniversary_worker import PatientHealthAnniversaryWorkerV2
from healthcare_platform.patient_access.workers.patient_preventive_reminder_worker import PatientPreventiveReminderWorkerV2
from healthcare_platform.patient_access.workers.patient_satisfaction_survey_worker import PatientSatisfactionSurveyWorkerV2
from healthcare_platform.patient_access.workers.patient_triage_status_worker import PatientTriageStatusWorkerV2
from healthcare_platform.patient_access.workers.register_dependent_worker import RegisterDependentWorkerV2
from healthcare_platform.patient_access.workers.send_appointment_confirmation_worker import SendAppointmentConfirmationWorkerV2
from healthcare_platform.patient_access.workers.send_reminder_notification_worker import SendReminderNotificationWorkerV2
from healthcare_platform.patient_access.workers.update_patient_registry_worker import UpdatePatientRegistryWorkerV2
from healthcare_platform.patient_access.workers.update_scheduling_system_worker import UpdateSchedulingSystemWorkerV2
from healthcare_platform.patient_access.workers.validate_appointment_rules_worker import ValidateAppointmentRulesWorkerV2
from healthcare_platform.patient_access.workers.validate_documentation_worker import ValidateDocumentationWorkerV2
from healthcare_platform.patient_access.workers.validate_patient_data_worker import ValidatePatientDataWorkerV2
from healthcare_platform.patient_access.workers.verify_insurance_coverage_worker import VerifyInsuranceCoverageWorkerV2

__all__ = [
    'AssignMedicalRecordNumberWorkerV2',
    'AssignResourcesWorkerV2',
    'CalculateEstimatedDurationWorkerV2',
    'CaptureDemographicsWorkerV2',
    'CheckAuthorizationRequirementsWorkerV2',
    'CheckAvailabilityWorkerV2',
    'CheckExistingPatientWorkerV2',
    'CheckPreAuthorizationWorkerV2',
    'CreateAppointmentWorkerV2',
    'CreatePatientRecordWorkerV2',
    'DoctorPatientArrivalWorkerV2',
    'GeneratePatientCardWorkerV2',
    'GeneratePreAdmissionChecklistWorkerV2',
    'HandleCancellationWorkerV2',
    'NotifyRegistrationCompleteWorkerV2',
    'PatientBirthdayWorkerV2',
    'PatientEmergencyWaitUpdateWorkerV2',
    'PatientHealthAnniversaryWorkerV2',
    'PatientPreventiveReminderWorkerV2',
    'PatientSatisfactionSurveyWorkerV2',
    'PatientTriageStatusWorkerV2',
    'RegisterDependentWorkerV2',
    'SendAppointmentConfirmationWorkerV2',
    'SendReminderNotificationWorkerV2',
    'UpdatePatientRegistryWorkerV2',
    'UpdateSchedulingSystemWorkerV2',
    'ValidateAppointmentRulesWorkerV2',
    'ValidateDocumentationWorkerV2',
    'ValidatePatientDataWorkerV2',
    'VerifyInsuranceCoverageWorkerV2',
]
