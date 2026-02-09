"""TASY ERP integration data models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from revenue_cycle.validators.patient_id import validate_patient_id


class TasyPatientDTO(BaseModel):
    """Patient data from TASY ERP."""

    patient_id: str = Field(description="TASY patient ID (CPF or CNJ)")
    cpf: str = Field(description="CPF number (XXX.XXX.XXX-XX or 11 digits)")
    nome: str = Field(description="Patient full name")
    data_nascimento: date = Field(description="Birth date")
    sexo: str = Field(description="Sex (M/F)")
    telefone: Optional[str] = Field(default=None, description="Phone number")
    email: Optional[str] = Field(default=None, description="Email address")
    endereco: Optional[str] = Field(default=None, description="Address")
    cidade: Optional[str] = Field(default=None, description="City")
    estado: Optional[str] = Field(default=None, description="State")
    cep: Optional[str] = Field(default=None, description="Postal code")

    @field_validator("patient_id", "cpf", mode="before")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate patient ID and CPF format."""
        return validate_patient_id(v)

    class Config:
        """Pydantic config."""

        frozen = False


class TasyEncounterDTO(BaseModel):
    """Encounter (atendimento) data from TASY."""

    encounter_id: str = Field(description="TASY encounter ID")
    patient_id: str = Field(description="Associated patient ID (CPF or CNJ)")
    date_admission: datetime = Field(description="Admission date/time")
    date_discharge: Optional[datetime] = Field(default=None, description="Discharge date/time")
    tipo_atendimento: str = Field(description="Encounter type (internacao, ambulatorio, pronto-socorro)")
    convenio: str = Field(description="Insurance/payer name")
    numero_carteirinha: Optional[str] = Field(default=None, description="Insurance card number")
    medico_solicitante: Optional[str] = Field(default=None, description="Requesting physician")
    diagnostico_principal: Optional[str] = Field(default=None, description="Primary diagnosis code")
    status: str = Field(description="Encounter status (ativo, fechado, faturado)")

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)

    class Config:
        """Pydantic config."""

        frozen = False


class TasyProcedureDTO(BaseModel):
    """Procedure/service data from TASY."""

    procedure_id: str = Field(description="TASY procedure ID")
    encounter_id: str = Field(description="Associated encounter ID")
    code: str = Field(description="Procedure code (TUSS, AMB, etc.)")
    description: str = Field(description="Procedure description")
    quantity: int = Field(default=1, ge=1, description="Quantity performed")
    unit_price: Decimal = Field(description="Unit price")
    total_price: Decimal = Field(description="Total price (quantity * unit_price)")
    date_performed: datetime = Field(description="Date procedure was performed")
    professional: Optional[str] = Field(default=None, description="Professional who performed")
    status: str = Field(description="Procedure status (realizado, faturado, glosado)")

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True


class TasyDiagnosisDTO(BaseModel):
    """Diagnosis data from TASY."""

    diagnosis_id: str = Field(description="TASY diagnosis ID")
    encounter_id: str = Field(description="Associated encounter ID")
    code_cid10: str = Field(description="CID-10 diagnosis code")
    description: str = Field(description="Diagnosis description")
    tipo: str = Field(description="Diagnosis type (principal, secundario)")
    date_registered: datetime = Field(description="Date diagnosis was registered")

    class Config:
        """Pydantic config."""

        frozen = False


class TasyMedicalRecord(BaseModel):
    """Medical record data for glosa appeals."""

    patient_id: str = Field(description="Patient ID (CPF or CNJ)")
    encounter_id: str = Field(description="Encounter ID")
    admission_date: datetime = Field(description="Admission date")
    discharge_date: Optional[datetime] = Field(default=None, description="Discharge date")

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)

    # Clinical data
    diagnoses: List[TasyDiagnosisDTO] = Field(default_factory=list, description="All diagnoses")
    procedures: List[TasyProcedureDTO] = Field(default_factory=list, description="All procedures")

    # Medical notes
    anamnese: Optional[str] = Field(default=None, description="Anamnesis/history")
    evolucao: Optional[str] = Field(default=None, description="Clinical evolution notes")
    exame_fisico: Optional[str] = Field(default=None, description="Physical exam findings")
    prescricoes: List[str] = Field(default_factory=list, description="Prescriptions")

    # Lab results
    lab_results: List[dict] = Field(default_factory=list, description="Laboratory results")
    image_results: List[dict] = Field(default_factory=list, description="Imaging results")

    # Administrative
    discharge_summary: Optional[str] = Field(default=None, description="Discharge summary")
    complications: List[str] = Field(default_factory=list, description="Complications recorded")

    class Config:
        """Pydantic config."""

        frozen = False


class TasyBillingItemDTO(BaseModel):
    """Billing item ready for TISS submission."""

    encounter_id: str = Field(description="Source encounter ID")
    patient_cpf: str = Field(description="Patient CPF")
    convenio: str = Field(description="Insurance name")
    numero_carteirinha: str = Field(description="Insurance card number")
    procedures: List[TasyProcedureDTO] = Field(description="Procedures to bill")
    diagnoses: List[TasyDiagnosisDTO] = Field(description="Associated diagnoses")
    total_amount: Decimal = Field(description="Total billing amount")
    date_service_start: datetime = Field(description="Start of service period")
    date_service_end: Optional[datetime] = Field(default=None, description="End of service period")

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True
