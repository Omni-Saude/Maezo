"""
Pydantic V2 models for clinical workers.

Includes input/output models for:
- TASY EHR data collection
- Encounter registration
- Procedure registration
- LIS (Laboratory Information System) integration
- PACS (Picture Archiving and Communication System) integration
- Encounter closure
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict, field_validator

from revenue_cycle.validators.patient_id import validate_patient_id


# =============================================================================
# Enums
# =============================================================================


class EncounterType(str, Enum):
    """Clinical encounter types."""
    AMBULATORY = "AMBULATORY"
    INPATIENT = "INPATIENT"
    EMERGENCY = "EMERGENCY"
    ICU = "ICU"
    SURGERY = "SURGERY"


class DischargeType(str, Enum):
    """Encounter discharge types."""
    NORMAL = "NORMAL"
    AGAINST_MEDICAL_ADVICE = "AGAINST_MEDICAL_ADVICE"
    TRANSFERRED = "TRANSFERRED"
    DECEASED = "DECEASED"
    LEFT_WITHOUT_PERMISSION = "LEFT_WITHOUT_PERMISSION"


class LabStatus(str, Enum):
    """Lab result status."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CRITICAL = "CRITICAL"
    CORRECTED = "CORRECTED"


class ImagingStatus(str, Enum):
    """Imaging study status."""
    SCHEDULED = "SCHEDULED"
    ACQUIRED = "ACQUIRED"
    PROCESSING = "PROCESSING"
    REVIEWED = "REVIEWED"
    REPORTED = "REPORTED"


# =============================================================================
# TASY EHR Integration Models
# =============================================================================


class LabResult(BaseModel):
    """Lab test result."""
    model_config = ConfigDict(populate_by_name=True)

    test_code: str = Field(..., alias="testCode")
    test_name: str = Field(..., alias="testName")
    result_value: str = Field(..., alias="resultValue")
    reference_range: Optional[str] = Field(None, alias="referenceRange")
    unit: Optional[str] = None
    collected_date: datetime = Field(..., alias="collectedDate")
    result_date: datetime = Field(..., alias="resultDate")
    status: LabStatus = LabStatus.COMPLETED


class Medication(BaseModel):
    """Medication prescribed."""
    model_config = ConfigDict(populate_by_name=True)

    medication_code: str = Field(..., alias="medicationCode")
    medication_name: str = Field(..., alias="medicationName")
    dosage: str = Field(...)
    frequency: str = Field(...)
    route: str = Field(...)
    start_date: date = Field(..., alias="startDate")
    end_date: Optional[date] = Field(None, alias="endDate")
    prescriber_id: str = Field(..., alias="prescriberId")


class Diagnosis(BaseModel):
    """Diagnosis record."""
    model_config = ConfigDict(populate_by_name=True)

    diagnosis_code: str = Field(..., alias="diagnosisCode")  # ICD-10
    description: str = Field(...)
    is_primary: bool = Field(True, alias="isPrimary")
    diagnosis_date: date = Field(..., alias="diagnosisDate")


class CollectTasyDataInput(BaseModel):
    """Input for TASY EHR data collection."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    patient_id: str = Field(..., alias="patientId", description="Patient identifier (CPF or CNJ)")
    tenant_id: str = Field(..., alias="tenantId")

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)


class CollectTasyDataOutput(BaseModel):
    """Output from TASY EHR data collection."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    clinical_data: dict[str, Any] = Field(..., alias="clinicalData")
    lab_results: list[LabResult] = Field(default_factory=list, alias="labResults")
    medications: list[Medication] = Field(default_factory=list)
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    collection_status: str = Field(..., alias="collectionStatus")
    collection_timestamp: datetime = Field(..., alias="collectionTimestamp")


# =============================================================================
# Encounter Registration Models
# =============================================================================


class RegisterEncounterInput(BaseModel):
    """Input for encounter registration."""
    model_config = ConfigDict(populate_by_name=True)

    patient_id: str = Field(..., alias="patientId", description="Patient identifier (CPF or CNJ)")
    appointment_id: str = Field(..., alias="appointmentId")
    encounter_type: EncounterType = Field(..., alias="encounterType")
    provider_id: str = Field(..., alias="providerId")
    facility_id: Optional[str] = Field(None, alias="facilityId")
    tenant_id: str = Field(..., alias="tenantId")

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)


class RegisterEncounterOutput(BaseModel):
    """Output from encounter registration."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    patient_id: str = Field(..., alias="patientId", description="Patient identifier (CPF or CNJ)")
    registration_status: str = Field(..., alias="registrationStatus")
    admission_date: datetime = Field(..., alias="admissionDate")
    encounter_type: EncounterType = Field(..., alias="encounterType")
    registration_timestamp: datetime = Field(..., alias="registrationTimestamp")

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)

    @field_validator("registration_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = ["REGISTERED", "PENDING", "FAILED"]
        if v not in allowed:
            raise ValueError(f"Invalid status: {v}. Must be one of {allowed}")
        return v


# =============================================================================
# Procedure Registration Models (TUSS)
# =============================================================================


class RegisterProcedimentoInput(BaseModel):
    """Input for medical procedure registration."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    procedure_code: str = Field(..., alias="procedureCode")  # TUSS code
    procedure_description: Optional[str] = Field(None, alias="procedureDescription")
    quantity: int = Field(default=1)
    procedure_date: date = Field(..., alias="procedureDate")
    provider_id: str = Field(..., alias="providerId")
    tenant_id: str = Field(..., alias="tenantId")

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class RegisterProcedimentoOutput(BaseModel):
    """Output from procedure registration."""
    model_config = ConfigDict(populate_by_name=True)

    procedure_id: str = Field(..., alias="procedureId")
    encounter_id: str = Field(..., alias="encounterId")
    procedure_code: str = Field(..., alias="procedureCode")
    registration_status: str = Field(..., alias="registrationStatus")
    registration_timestamp: datetime = Field(..., alias="registrationTimestamp")


# =============================================================================
# LIS Integration Models
# =============================================================================


class LisIntegrationInput(BaseModel):
    """Input for LIS integration."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    lab_order_ids: list[str] = Field(..., alias="labOrderIds")
    tenant_id: str = Field(..., alias="tenantId")


class LisIntegrationOutput(BaseModel):
    """Output from LIS integration."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    lab_results: list[LabResult] = Field(..., alias="labResults")
    integration_status: str = Field(..., alias="integrationStatus")
    integration_timestamp: datetime = Field(..., alias="integrationTimestamp")
    missing_orders: list[str] = Field(default_factory=list, alias="missingOrders")


# =============================================================================
# PACS Integration Models
# =============================================================================


class ImagingResult(BaseModel):
    """Medical imaging study result."""
    model_config = ConfigDict(populate_by_name=True)

    study_id: str = Field(..., alias="studyId")
    study_type: str = Field(..., alias="studyType")  # CT, MRI, X-RAY, etc.
    study_date: datetime = Field(..., alias="studyDate")
    status: ImagingStatus = ImagingStatus.REPORTED
    report: Optional[str] = None
    dicom_url: Optional[str] = Field(None, alias="dicomUrl")


class PacsIntegrationInput(BaseModel):
    """Input for PACS integration."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    study_ids: list[str] = Field(..., alias="studyIds")
    tenant_id: str = Field(..., alias="tenantId")


class PacsIntegrationOutput(BaseModel):
    """Output from PACS integration."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    imaging_results: list[ImagingResult] = Field(..., alias="imagingResults")
    integration_status: str = Field(..., alias="integrationStatus")
    integration_timestamp: datetime = Field(..., alias="integrationTimestamp")
    missing_studies: list[str] = Field(default_factory=list, alias="missingStudies")


# =============================================================================
# Encounter Closure Models
# =============================================================================


class CloseEncounterInput(BaseModel):
    """Input for encounter closure."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    discharge_type: DischargeType = Field(..., alias="dischargeType")
    final_diagnoses: list[Diagnosis] = Field(..., alias="finalDiagnoses")
    discharge_notes: Optional[str] = Field(None, alias="dischargeNotes")
    discharge_date: datetime = Field(..., alias="dischargeDate")
    tenant_id: str = Field(..., alias="tenantId")


class CloseEncounterOutput(BaseModel):
    """Output from encounter closure."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    closure_status: str = Field(..., alias="closureStatus")
    final_bill: Optional[Decimal] = Field(None, alias="finalBill")
    discharge_date: datetime = Field(..., alias="dischargeDate")
    closure_timestamp: datetime = Field(..., alias="closureTimestamp")
