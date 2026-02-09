"""PACS (Picture Archiving and Communication System) data models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from revenue_cycle.validators.patient_id import validate_patient_id


class PACSStudyDTO(BaseModel):
    """Medical imaging study details."""

    study_id: str = Field(alias="studyId", description="Study instance UID")
    patient_id: str = Field(alias="patientId", description="Patient ID (CPF or CNJ)")
    accession_number: str = Field(alias="accessionNumber", description="Accession number")
    modality: str = Field(
        description="Imaging modality (CT, MRI, X-RAY, US, etc.)"
    )
    study_date: datetime = Field(alias="studyDate", description="Study date/time")
    description: str = Field(description="Study description")
    referring_physician: Optional[str] = Field(
        default=None, alias="referringPhysician", description="Referring physician"
    )
    study_status: str = Field(
        default="completed",
        alias="studyStatus",
        description="Study status (scheduled, in_progress, completed)",
    )
    number_of_images: Optional[int] = Field(
        default=None, alias="numberOfImages", description="Total number of images in study"
    )

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)

    class Config:
        """Pydantic config."""

        populate_by_name = True


class PACSReportDTO(BaseModel):
    """Radiology report for imaging study."""

    report_id: str = Field(alias="reportId", description="Report ID")
    study_id: str = Field(alias="studyId", description="Study instance UID")
    report_text: str = Field(alias="reportText", description="Report text content")
    radiologist: str = Field(description="Radiologist name")
    report_date: datetime = Field(alias="reportDate", description="Report date/time")
    report_status: str = Field(
        default="final",
        alias="reportStatus",
        description="Report status (preliminary, final, amended)",
    )
    findings: Optional[str] = Field(default=None, description="Key findings summary")
    impression: Optional[str] = Field(default=None, description="Impression/conclusion")

    class Config:
        """Pydantic config."""

        populate_by_name = True
