"""Tasy ERP Integration Client (Hospital AUSTA).

ADR-004: CDC only — NO direct ERP queries.
ADR-006: REST bridge only — NO Kafka consumption.

This client processes CDC events from Debezium and delegates snapshot
queries to FHIR (ADR-005). It never queries Tasy directly.
"""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient, IntegrationSettings
from healthcare_platform.shared.multi_tenant.context import get_current_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class TasyCDCEvent(BaseModel):
    """CDC event from Tasy ERP via Debezium."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str  # c=create, u=update, d=delete
    table_name: str
    timestamp: datetime
    payload: dict[str, Any]
    tenant_id: str


class TasyPatientDTO(BaseModel):
    """Patient snapshot sourced from FHIR (not ERP)."""

    model_config = ConfigDict(frozen=True)

    patient_id: str
    tenant_id: str
    mrn: str = ""
    given_name: str = ""
    family_name: str = ""
    birth_date: str | None = None
    gender: str | None = None
    active: bool = True


class TasyEncounterDTO(BaseModel):
    """Encounter snapshot sourced from FHIR (not ERP)."""

    model_config = ConfigDict(frozen=True)

    encounter_id: str
    tenant_id: str
    patient_id: str
    status: str
    class_code: str
    period_start: datetime | None = None
    period_end: datetime | None = None


class TasyProcedureDTO(BaseModel):
    """Procedure snapshot sourced from FHIR (not ERP)."""

    model_config = ConfigDict(frozen=True)

    procedure_id: str
    tenant_id: str
    encounter_id: str
    patient_id: str
    code: str
    display: str = ""
    status: str = "completed"
    performed_date: datetime | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class TasyClientProtocol(Protocol):
    """Interface for Tasy integration (CDC-only, ADR-004)."""

    @abstractmethod
    async def process_cdc_event(self, event: TasyCDCEvent) -> dict[str, Any]: ...

    @abstractmethod
    async def get_patient_snapshot(self, patient_id: str) -> TasyPatientDTO: ...

    @abstractmethod
    async def get_encounter_snapshot(self, encounter_id: str) -> TasyEncounterDTO: ...

    @abstractmethod
    async def get_procedures(self, encounter_id: str) -> list[TasyProcedureDTO]: ...


# ---------------------------------------------------------------------------
# Production Implementation
# ---------------------------------------------------------------------------


class TasyClient(BaseIntegrationClient, TasyClientProtocol):
    """Production Tasy client.

    - CDC events are processed locally (no outbound call).
    - Snapshot queries delegate to FHIR via the injected fhir_base_url.
    """

    SERVICE_NAME = "tasy"

    def __init__(
        self,
        settings: IntegrationSettings,
        fhir_base_url: str = "",
    ) -> None:
        super().__init__(settings)
        self._fhir_base_url = fhir_base_url

    # -- CDC event processing (local, no HTTP) --

    @track_api_call(service="tasy", endpoint="process_cdc_event", method="POST")
    async def process_cdc_event(self, event: TasyCDCEvent) -> dict[str, Any]:
        ctx = self._get_tenant_context()
        if ctx.tenant_id != event.tenant_id:
            raise ExternalServiceException(
                _("Evento CDC com tenant incompatível"),
                service_name=self.SERVICE_NAME,
                operation="process_cdc_event",
            )
        self._logger.info(
            "cdc_event_processed",
            event_id=event.event_id,
            event_type=event.event_type,
            table=event.table_name,
        )
        return {
            "event_id": event.event_id,
            "processed_at": datetime.utcnow().isoformat(),
            "status": "processed",
        }

    # -- Snapshot queries (delegate to FHIR, ADR-005) --

    @track_api_call(service="tasy", endpoint="get_patient_snapshot", method="GET")
    async def get_patient_snapshot(self, patient_id: str) -> TasyPatientDTO:
        ctx = self._get_tenant_context()
        resp = await self._request("GET", f"{self._fhir_base_url}/Patient/{patient_id}")
        data = resp.json()
        names = data.get("name", [{}])
        return TasyPatientDTO(
            patient_id=patient_id,
            tenant_id=ctx.tenant_id,
            mrn=next(
                (i["value"] for i in data.get("identifier", []) if i.get("value")),
                "",
            ),
            given_name=(names[0].get("given", [""]))[0] if names else "",
            family_name=names[0].get("family", "") if names else "",
            birth_date=data.get("birthDate"),
            gender=data.get("gender"),
            active=data.get("active", True),
        )

    @track_api_call(service="tasy", endpoint="get_encounter_snapshot", method="GET")
    async def get_encounter_snapshot(self, encounter_id: str) -> TasyEncounterDTO:
        ctx = self._get_tenant_context()
        resp = await self._request("GET", f"{self._fhir_base_url}/Encounter/{encounter_id}")
        data = resp.json()
        period = data.get("period", {})
        return TasyEncounterDTO(
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id,
            patient_id=data.get("subject", {}).get("reference", "").rsplit("/", 1)[-1],
            status=data.get("status", "unknown"),
            class_code=data.get("class", {}).get("code", "unknown"),
            period_start=datetime.fromisoformat(period["start"]) if period.get("start") else None,
            period_end=datetime.fromisoformat(period["end"]) if period.get("end") else None,
        )

    @track_api_call(service="tasy", endpoint="get_procedures", method="GET")
    async def get_procedures(self, encounter_id: str) -> list[TasyProcedureDTO]:
        ctx = self._get_tenant_context()
        resp = await self._request(
            "GET",
            f"{self._fhir_base_url}/Procedure",
            params={"encounter": encounter_id},
        )
        bundle = resp.json()
        results: list[TasyProcedureDTO] = []
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            coding = (r.get("code", {}).get("coding", [{}]))[0]
            results.append(
                TasyProcedureDTO(
                    procedure_id=r.get("id", ""),
                    tenant_id=ctx.tenant_id,
                    encounter_id=encounter_id,
                    patient_id=r.get("subject", {}).get("reference", "").rsplit("/", 1)[-1],
                    code=coding.get("code", ""),
                    display=coding.get("display", ""),
                    status=r.get("status", "completed"),
                    performed_date=(
                        datetime.fromisoformat(r["performedDateTime"])
                        if r.get("performedDateTime")
                        else None
                    ),
                )
            )
        return results


# ---------------------------------------------------------------------------
# Stub for Testing
# ---------------------------------------------------------------------------


class StubTasyClient(TasyClientProtocol):
    """In-memory stub for unit tests."""

    def __init__(self) -> None:
        self.processed_events: list[TasyCDCEvent] = []

    async def process_cdc_event(self, event: TasyCDCEvent) -> dict[str, Any]:
        self.processed_events.append(event)
        return {"event_id": event.event_id, "status": "processed"}

    async def get_patient_snapshot(self, patient_id: str) -> TasyPatientDTO:
        ctx = get_current_tenant()
        return TasyPatientDTO(
            patient_id=patient_id,
            tenant_id=ctx.tenant_id if ctx else "test",
            mrn=f"MRN-{patient_id}",
            given_name="Test",
            family_name="Patient",
        )

    async def get_encounter_snapshot(self, encounter_id: str) -> TasyEncounterDTO:
        ctx = get_current_tenant()
        return TasyEncounterDTO(
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id if ctx else "test",
            patient_id="patient-001",
            status="in-progress",
            class_code="AMB",
        )

    async def get_procedures(self, encounter_id: str) -> list[TasyProcedureDTO]:
        ctx = get_current_tenant()
        return [
            TasyProcedureDTO(
                procedure_id="proc-001",
                tenant_id=ctx.tenant_id if ctx else "test",
                encounter_id=encounter_id,
                patient_id="patient-001",
                code="10101012",
                display="Consulta em consultorio",
                status="completed",
            )
        ]
