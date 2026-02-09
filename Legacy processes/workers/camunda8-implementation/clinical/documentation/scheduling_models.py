"""
Data models for scheduling workers (Brazilian hospital appointments).

Supports appointment scheduling, consultation, and routing for the hospital
revenue cycle. Portuguese field names for healthcare compliance.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AppointmentStatus(str, Enum):
    """Status of an appointment."""

    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    RESCHEDULED = "RESCHEDULED"


class SlotStatus(str, Enum):
    """Status of an appointment slot."""

    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"


class ServiceType(str, Enum):
    """Types of medical services."""

    CONSULTATION = "CONSULTATION"
    PROCEDURE = "PROCEDURE"
    IMAGING = "IMAGING"
    LABORATORY = "LABORATORY"
    EMERGENCY = "EMERGENCY"
    VACCINATION = "VACCINATION"


class ContactMethod(str, Enum):
    """Methods to contact patient about appointment."""

    SMS = "SMS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    LETTER = "LETTER"
    WHATSAPP = "WHATSAPP"


class AvailableSlot(BaseModel):
    """Represents an available appointment slot."""

    slot_id: str = Field(alias="slotId")
    date: str = Field(description="Date in YYYY-MM-DD format")
    time: str = Field(description="Time in HH:MM format")
    provider_name: str = Field(alias="providerName")
    provider_id: str = Field(alias="providerId")
    specialty: str
    service_code: str = Field(alias="serviceCode")
    estimated_duration_minutes: int = Field(
        alias="estimatedDurationMinutes",
        description="Estimated duration in minutes",
    )
    location: str
    is_urgent: bool = Field(default=False, alias="isUrgent")

    class Config:
        populate_by_name = True


class ConsultarAgendaInput(BaseModel):
    """Input for scheduling query worker."""

    patient_id: str = Field(alias="patientId")
    service_code: str = Field(alias="serviceCode")
    date_range_start: Optional[str] = Field(
        default=None,
        alias="dateRangeStart",
        description="Start date in YYYY-MM-DD format",
    )
    date_range_end: Optional[str] = Field(
        default=None,
        alias="dateRangeEnd",
        description="End date in YYYY-MM-DD format",
    )
    provider_code: Optional[str] = Field(default=None, alias="providerCode")
    specialty: Optional[str] = None
    max_results: int = Field(default=10, alias="maxResults")
    preferred_time: Optional[str] = Field(
        default=None,
        alias="preferredTime",
        description="Preferred time (MORNING/AFTERNOON/EVENING)",
    )
    tenant_id: Optional[str] = Field(default=None, alias="tenantId")

    class Config:
        populate_by_name = True


class ConsultarAgendaOutput(BaseModel):
    """Output from scheduling query worker."""

    available_slots: list[AvailableSlot] = Field(
        default_factory=list,
        alias="availableSlots",
    )
    scheduling_available: bool = Field(alias="schedulingAvailable")
    slot_count: int = Field(alias="slotCount")
    service_code: str = Field(alias="serviceCode")
    patient_id: str = Field(alias="patientId")
    queried_at: datetime = Field(alias="queriedAt", default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class ConfirmarAgendamentoInput(BaseModel):
    """Input for appointment confirmation worker."""

    patient_id: str = Field(alias="patientId")
    slot_id: str = Field(alias="slotId")
    service_code: str = Field(alias="serviceCode")
    provider_id: str = Field(alias="providerId")
    provider_name: Optional[str] = Field(default=None, alias="providerName")
    specialty: Optional[str] = None
    appointment_date: Optional[str] = Field(
        default=None,
        alias="appointmentDate",
        description="Date in YYYY-MM-DD format",
    )
    appointment_time: Optional[str] = Field(
        default=None,
        alias="appointmentTime",
        description="Time in HH:MM format",
    )
    patient_name: Optional[str] = Field(default=None, alias="patientName")
    patient_phone: Optional[str] = Field(default=None, alias="patientPhone")
    patient_email: Optional[str] = Field(default=None, alias="patientEmail")
    notes: Optional[str] = None
    is_urgent: bool = Field(default=False, alias="isUrgent")
    tenant_id: Optional[str] = Field(default=None, alias="tenantId")

    @field_validator("slot_id")
    @classmethod
    def validate_slot_id(cls, v: str) -> str:
        """Validate slot ID is not empty."""
        if not v or not v.strip():
            raise ValueError("slot_id cannot be empty")
        return v.strip()

    class Config:
        populate_by_name = True


class ConfirmarAgendamentoOutput(BaseModel):
    """Output from appointment confirmation worker."""

    appointment_id: str = Field(alias="appointmentId")
    appointment_confirmed: bool = Field(alias="appointmentConfirmed")
    confirmation_number: str = Field(alias="confirmationNumber")
    appointment_date: str = Field(
        alias="appointmentDate",
        description="Confirmed date in YYYY-MM-DD format",
    )
    appointment_time: str = Field(
        alias="appointmentTime",
        description="Confirmed time in HH:MM format",
    )
    patient_id: str = Field(alias="patientId")
    service_code: str = Field(alias="serviceCode")
    provider_id: str = Field(alias="providerId")
    provider_name: str = Field(alias="providerName")
    specialty: str
    location: str
    estimated_duration_minutes: int = Field(alias="estimatedDurationMinutes")
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    confirmed_at: datetime = Field(alias="confirmedAt", default_factory=datetime.utcnow)
    confirmation_sent_via: Optional[str] = Field(
        default=None,
        alias="confirmationSentVia",
        description="Method used to send confirmation (SMS/EMAIL/PHONE)",
    )
    next_reminder_date: Optional[str] = Field(
        default=None,
        alias="nextReminderDate",
        description="Date of next appointment reminder",
    )

    class Config:
        populate_by_name = True


class EncaminharAtendimentoInput(BaseModel):
    """Input for service routing worker."""

    patient_id: str = Field(alias="patientId")
    appointment_id: str = Field(alias="appointmentId")
    service_code: str = Field(alias="serviceCode")
    provider_id: str = Field(alias="providerId")
    provider_name: Optional[str] = Field(default=None, alias="providerName")
    specialty: Optional[str] = None
    appointment_date: Optional[str] = Field(
        default=None,
        alias="appointmentDate",
        description="Date in YYYY-MM-DD format",
    )
    appointment_time: Optional[str] = Field(
        default=None,
        alias="appointmentTime",
        description="Time in HH:MM format",
    )
    patient_name: Optional[str] = Field(default=None, alias="patientName")
    location: Optional[str] = None
    check_in_required: bool = Field(default=True, alias="checkInRequired")
    estimated_wait_time: Optional[int] = Field(
        default=None,
        alias="estimatedWaitTime",
        description="Estimated wait time in minutes",
    )
    tenant_id: Optional[str] = Field(default=None, alias="tenantId")

    @field_validator("appointment_id")
    @classmethod
    def validate_appointment_id(cls, v: str) -> str:
        """Validate appointment ID is not empty."""
        if not v or not v.strip():
            raise ValueError("appointment_id cannot be empty")
        return v.strip()

    class Config:
        populate_by_name = True


class RouteInstruction(BaseModel):
    """Single instruction for patient routing."""

    step_number: int = Field(alias="stepNumber")
    instruction: str
    location: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, alias="durationMinutes")


class EncaminharAtendimentoOutput(BaseModel):
    """Output from service routing worker."""

    route_id: str = Field(alias="routeId")
    assigned_room: str = Field(alias="assignedRoom")
    instructions: list[RouteInstruction]
    estimated_wait_time: int = Field(alias="estimatedWaitTime")
    patient_id: str = Field(alias="patientId")
    appointment_id: str = Field(alias="appointmentId")
    provider_id: str = Field(alias="providerId")
    provider_name: str = Field(alias="providerName")
    specialty: str
    location: str
    check_in_instructions: str = Field(alias="checkInInstructions")
    contact_phone: Optional[str] = Field(
        default=None,
        alias="contactPhone",
        description="Provider/location contact phone",
    )
    routed_at: datetime = Field(alias="routedAt", default_factory=datetime.utcnow)
    status: str = "ROUTED"

    class Config:
        populate_by_name = True
