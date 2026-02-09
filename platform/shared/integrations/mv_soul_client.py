"""MV Soul ERP Integration Client.

This module provides integration with MV Soul ERP used by AMH units (SP, RJ, MG).
Per ADR-004, uses CDC events only - NO direct ERP queries.

Per ADR-006, snapshot queries delegate to FHIR API instead of direct ERP access.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import ExternalServiceException
from platform.shared.integrations.base import BaseIntegrationClient
from platform.shared.multi_tenant.context import TenantContext
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_api_call


SERVICE_NAME = "mv_soul"

logger = get_logger(__name__)


# ============================================================================
# DTOs
# ============================================================================


class MvSoulCDCEvent(BaseModel):
    """CDC event from MV Soul ERP.

    Captures change data from MV Soul database via CDC pipeline.
    """

    event_id: str = Field(..., description="Unique event identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    table_name: str = Field(..., description="Source table name")
    operation: str = Field(..., description="INSERT, UPDATE, DELETE")
    timestamp: str = Field(..., description="Event timestamp (ISO 8601)")
    before_data: dict[str, Any] | None = Field(
        None, description="Record state before change"
    )
    after_data: dict[str, Any] | None = Field(
        None, description="Record state after change"
    )
    primary_keys: dict[str, Any] = Field(
        ..., description="Primary key values"
    )


class MvSoulPatientDTO(BaseModel):
    """Patient snapshot from MV Soul ERP.

    Per ADR-006, sourced from FHIR API, not direct ERP query.
    """

    patient_id: str = Field(..., description="MV Soul patient ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    national_id: str | None = Field(None, description="CPF (masked)")
    full_name: str = Field(..., description="Patient full name")
    date_of_birth: str | None = Field(None, description="Birth date (ISO)")
    gender: str | None = Field(None, description="Gender code")
    phone: str | None = Field(None, description="Phone (masked)")
    email: str | None = Field(None, description="Email (masked)")
    address: dict[str, Any] | None = Field(None, description="Address data")
    health_plan_code: str | None = Field(None, description="Health plan")
    registration_number: str | None = Field(
        None, description="Health plan number"
    )
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class MvSoulEncounterDTO(BaseModel):
    """Encounter snapshot from MV Soul ERP.

    Per ADR-006, sourced from FHIR API, not direct ERP query.
    """

    encounter_id: str = Field(..., description="MV Soul encounter ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    patient_id: str = Field(..., description="Patient ID")
    admission_date: str = Field(..., description="Admission date (ISO)")
    discharge_date: str | None = Field(None, description="Discharge date")
    encounter_type: str = Field(..., description="Encounter type code")
    specialty: str | None = Field(None, description="Medical specialty")
    attending_physician: str | None = Field(
        None, description="Physician ID"
    )
    diagnosis_codes: list[str] = Field(
        default_factory=list, description="ICD-10 codes"
    )
    procedure_codes: list[str] = Field(
        default_factory=list, description="Procedure codes"
    )
    status: str = Field(..., description="Encounter status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class MvSoulBillingItemDTO(BaseModel):
    """Billing item from MV Soul ERP.

    Per ADR-006, sourced from FHIR API, not direct ERP query.
    """

    item_id: str = Field(..., description="Billing item ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    encounter_id: str = Field(..., description="Encounter ID")
    item_code: str = Field(..., description="TUSS/CBHPM code")
    item_description: str = Field(..., description="Item description")
    quantity: float = Field(..., description="Quantity")
    unit_price: float = Field(..., description="Unit price")
    total_price: float = Field(..., description="Total price")
    service_date: str = Field(..., description="Service date (ISO)")
    professional_id: str | None = Field(
        None, description="Performing professional"
    )
    status: str = Field(..., description="Item status")
    created_at: str = Field(..., description="Creation timestamp")


# ============================================================================
# Protocol
# ============================================================================


class MvSoulClientProtocol(Protocol):
    """Protocol for MV Soul ERP integration clients."""

    async def process_cdc_event(
        self, event: MvSoulCDCEvent
    ) -> dict[str, Any]:
        """Process a CDC event from MV Soul.

        Args:
            event: CDC event to process

        Returns:
            Processing result with action taken

        Raises:
            ExternalServiceException: If processing fails
        """
        ...

    async def get_patient_snapshot(
        self, patient_id: str
    ) -> MvSoulPatientDTO:
        """Get patient snapshot.

        Per ADR-006, delegates to FHIR API instead of direct ERP query.

        Args:
            patient_id: MV Soul patient ID

        Returns:
            Patient snapshot

        Raises:
            ExternalServiceException: If retrieval fails
        """
        ...

    async def get_encounter_snapshot(
        self, encounter_id: str
    ) -> MvSoulEncounterDTO:
        """Get encounter snapshot.

        Per ADR-006, delegates to FHIR API instead of direct ERP query.

        Args:
            encounter_id: MV Soul encounter ID

        Returns:
            Encounter snapshot

        Raises:
            ExternalServiceException: If retrieval fails
        """
        ...

    async def get_billing_items(
        self, encounter_id: str
    ) -> list[MvSoulBillingItemDTO]:
        """Get billing items for encounter.

        Per ADR-006, delegates to FHIR API instead of direct ERP query.

        Args:
            encounter_id: MV Soul encounter ID

        Returns:
            List of billing items

        Raises:
            ExternalServiceException: If retrieval fails
        """
        ...


# ============================================================================
# Production Implementation
# ============================================================================


class MvSoulClient(BaseIntegrationClient):
    """Production MV Soul ERP client.

    Per ADR-004: Processes CDC events only, no direct ERP queries.
    Per ADR-006: Snapshot queries delegate to FHIR API.
    """

    def __init__(
        self,
        tenant_context: TenantContext,
        fhir_base_url: str | None = None,
    ) -> None:
        """Initialize MV Soul client.

        Args:
            tenant_context: Tenant context for multi-tenancy
            fhir_base_url: FHIR API base URL (for snapshot queries)
        """
        super().__init__(
            service_name=SERVICE_NAME,
            base_url="",  # No direct ERP access
            tenant_context=tenant_context,
        )
        self.fhir_base_url = fhir_base_url

    @track_api_call(service_name=SERVICE_NAME)
    async def process_cdc_event(
        self, event: MvSoulCDCEvent
    ) -> dict[str, Any]:
        """Process CDC event from MV Soul."""
        logger.info(
            "Processing MV Soul CDC event",
            extra={
                "event_id": event.event_id,
                "table": event.table_name,
                "operation": event.operation,
            },
        )

        # Validate tenant
        if event.tenant_id != self.tenant_context.tenant_id:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message="Tenant mismatch in CDC event",
            )

        # Process based on table and operation
        result = {
            "event_id": event.event_id,
            "table": event.table_name,
            "operation": event.operation,
            "processed": True,
        }

        # Table-specific processing would go here
        # This is where domain events would be emitted
        # for downstream consumption by bounded contexts

        logger.info(
            "MV Soul CDC event processed successfully",
            extra={"event_id": event.event_id},
        )

        return result

    @track_api_call(service_name=SERVICE_NAME)
    async def get_patient_snapshot(
        self, patient_id: str
    ) -> MvSoulPatientDTO:
        """Get patient snapshot via FHIR API.

        Per ADR-006, delegates to FHIR instead of direct ERP query.
        """
        if not self.fhir_base_url:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message="FHIR base URL not configured",
            )

        logger.info(
            "Fetching patient snapshot via FHIR",
            extra={"patient_id": patient_id},
        )

        # Delegate to FHIR API
        # In production, this would call the FHIR client
        raise NotImplementedError(
            "Patient snapshot retrieval via FHIR not yet implemented"
        )

    @track_api_call(service_name=SERVICE_NAME)
    async def get_encounter_snapshot(
        self, encounter_id: str
    ) -> MvSoulEncounterDTO:
        """Get encounter snapshot via FHIR API.

        Per ADR-006, delegates to FHIR instead of direct ERP query.
        """
        if not self.fhir_base_url:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message="FHIR base URL not configured",
            )

        logger.info(
            "Fetching encounter snapshot via FHIR",
            extra={"encounter_id": encounter_id},
        )

        # Delegate to FHIR API
        # In production, this would call the FHIR client
        raise NotImplementedError(
            "Encounter snapshot retrieval via FHIR not yet implemented"
        )

    @track_api_call(service_name=SERVICE_NAME)
    async def get_billing_items(
        self, encounter_id: str
    ) -> list[MvSoulBillingItemDTO]:
        """Get billing items via FHIR API.

        Per ADR-006, delegates to FHIR instead of direct ERP query.
        """
        if not self.fhir_base_url:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message="FHIR base URL not configured",
            )

        logger.info(
            "Fetching billing items via FHIR",
            extra={"encounter_id": encounter_id},
        )

        # Delegate to FHIR API
        # In production, this would call the FHIR client
        raise NotImplementedError(
            "Billing items retrieval via FHIR not yet implemented"
        )


# ============================================================================
# Test Stub
# ============================================================================


class StubMvSoulClient:
    """Stub MV Soul client for testing."""

    def __init__(self, tenant_context: TenantContext) -> None:
        """Initialize stub client."""
        self.tenant_context = tenant_context
        self.processed_events: list[MvSoulCDCEvent] = []

    async def process_cdc_event(
        self, event: MvSoulCDCEvent
    ) -> dict[str, Any]:
        """Process CDC event (stub)."""
        self.processed_events.append(event)
        return {
            "event_id": event.event_id,
            "table": event.table_name,
            "operation": event.operation,
            "processed": True,
            "stub": True,
        }

    async def get_patient_snapshot(
        self, patient_id: str
    ) -> MvSoulPatientDTO:
        """Get patient snapshot (stub)."""
        return MvSoulPatientDTO(
            patient_id=patient_id,
            tenant_id=self.tenant_context.tenant_id,
            full_name="Test Patient",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    async def get_encounter_snapshot(
        self, encounter_id: str
    ) -> MvSoulEncounterDTO:
        """Get encounter snapshot (stub)."""
        return MvSoulEncounterDTO(
            encounter_id=encounter_id,
            tenant_id=self.tenant_context.tenant_id,
            patient_id="test-patient",
            admission_date="2024-01-01T00:00:00Z",
            encounter_type="inpatient",
            status="in-progress",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    async def get_billing_items(
        self, encounter_id: str
    ) -> list[MvSoulBillingItemDTO]:
        """Get billing items (stub)."""
        return [
            MvSoulBillingItemDTO(
                item_id="test-item-1",
                tenant_id=self.tenant_context.tenant_id,
                encounter_id=encounter_id,
                item_code="40101012",
                item_description="Consulta médica",
                quantity=1.0,
                unit_price=150.00,
                total_price=150.00,
                service_date="2024-01-01T00:00:00Z",
                status="approved",
                created_at="2024-01-01T00:00:00Z",
            )
        ]
