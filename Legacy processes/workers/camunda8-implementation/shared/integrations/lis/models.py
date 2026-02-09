"""LIS (Laboratory Information System) data models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from revenue_cycle.validators.patient_id import validate_patient_id


class LISOrderDTO(BaseModel):
    """Laboratory order details."""

    order_id: str = Field(alias="orderId", description="Lab order ID")
    patient_id: str = Field(alias="patientId", description="Patient ID (CPF or CNJ)")
    order_date: datetime = Field(alias="orderDate", description="Order creation date")
    status: str = Field(description="Order status (pending, collected, completed)")
    priority: Optional[str] = Field(default=None, description="Order priority (routine, urgent, stat)")
    ordering_physician: Optional[str] = Field(
        default=None, alias="orderingPhysician", description="Physician who ordered tests"
    )

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)

    class Config:
        """Pydantic config."""

        populate_by_name = True


class LISResultDTO(BaseModel):
    """Laboratory test result."""

    result_id: str = Field(alias="resultId", description="Result ID")
    order_id: str = Field(alias="orderId", description="Lab order ID")
    test_code: str = Field(alias="testCode", description="Test code (LOINC or internal)")
    test_name: str = Field(alias="testName", description="Test name")
    result: str = Field(description="Test result value")
    unit: Optional[str] = Field(default=None, description="Unit of measure")
    reference_range: Optional[str] = Field(
        default=None, alias="referenceRange", description="Normal reference range"
    )
    abnormal_flag: Optional[str] = Field(
        default=None,
        alias="abnormalFlag",
        description="Abnormal flag (N=normal, H=high, L=low, A=abnormal)",
    )
    result_date: datetime = Field(alias="resultDate", description="Result date/time")
    status: str = Field(default="final", description="Result status (preliminary, final, corrected)")

    class Config:
        """Pydantic config."""

        populate_by_name = True
