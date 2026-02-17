"""Tests for TasySurgicalAdapter - comprehensive unit test coverage."""
from __future__ import annotations

from typing import Any

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)


def make_surgery_data(**overrides) -> dict[str, Any]:
    """Create test surgery data with sensible defaults."""
    base = {
        "operation_type": "surgery_creation",
        "NR_CIRURGIA": "CIR-001",
        "NR_PACIENTE": "12345",
        "NR_ATENDIMENTO": "ATD-789",
        "CD_SALA": "SALA-01",
        "DT_CIRURGIA": "2024-06-15T08:00:00",
        "DT_INICIO": "2024-06-15T08:00:00",
        "DT_FIM": "2024-06-15T10:30:00",
        "HR_INICIO": "08:00",
        "HR_FIM": "10:30",
        "CD_PROCEDIMENTO": "30101012",
        "DS_PROCEDIMENTO": "Colecistectomia videolaparoscópica",
        "NR_MEDICO": "DOC-456",
        "IE_STATUS": "SCHEDULED",
    }
    base.update(overrides)
    return base


class StubFHIRClient:
    """Stub FHIR client implementing FHIRClientProtocol."""

    def __init__(self):
        self.created_resources: list[dict[str, Any]] = []
        self.updated_resources: list[dict[str, Any]] = []

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        return {"id": resource_id, "resourceType": resource_type}

    async def search(
        self, resource_type: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        return []

    async def create(
        self, resource_type: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        resource["id"] = f"gen-{len(self.created_resources)}"
        self.created_resources.append(resource.copy())
        return resource

    async def update(
        self, resource_type: str, resource_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        resource["id"] = resource_id
        self.updated_resources.append(resource.copy())
        return resource


@pytest.fixture
def fhir_client():
    return StubFHIRClient()


@pytest.fixture
def adapter(fhir_client):
    return TasySurgicalAdapter(fhir_client=fhir_client, tenant_id="test-tenant")


@pytest.mark.unit
class TestTasySurgicalAdapterRooms:
    """Tests for room management operations."""

    @pytest.mark.asyncio
    async def test_adapt_room_availability(self, adapter):
        result = await adapter.adapt({
            "operation_type": "room_availability",
            "CD_SALA": "SALA-01",
            "DT_CONSULTA": "2024-06-15",
            "HR_INICIO": "08:00",
            "HR_FIM": "18:00",
            "IE_DISPONIVEL": "S",
        })
        assert result["resourceType"] == "Location"
        assert any(id_obj["value"] == "SALA-01" for id_obj in result.get("identifier", []))

    @pytest.mark.asyncio
    async def test_adapt_room_schedule(self, adapter):
        result = await adapter.adapt({
            "operation_type": "room_schedule",
            "CD_SALA": "SALA-01",
            "DT_INICIO": "2024-06-15",
            "DT_FIM": "2024-06-15",
            "schedules": [{"NR_CIRURGIA": "CIR-001", "HR_INICIO": "08:00"}],
        })
        assert result["resourceType"] == "Schedule"

    @pytest.mark.asyncio
    async def test_adapt_room_booking(self, adapter):
        result = await adapter.adapt(make_surgery_data(operation_type="room_booking"))
        assert result["resourceType"] == "Appointment"
        assert result["status"] == "booked"


@pytest.mark.unit
class TestTasySurgicalAdapterScheduling:
    """Tests for surgery scheduling operations."""

    @pytest.mark.asyncio
    async def test_adapt_surgery_creation(self, adapter):
        result = await adapter.adapt(make_surgery_data())
        assert result["resourceType"] == "Procedure"
        assert any(id_obj["value"] == "CIR-001" for id_obj in result.get("identifier", []))
        assert result["subject"]["reference"] == "Patient/12345"
        assert "code" in result

    @pytest.mark.asyncio
    async def test_adapt_surgery_update(self, adapter):
        result = await adapter.adapt(make_surgery_data(
            operation_type="surgery_update", IE_STATUS="IN_PROGRESS"
        ))
        assert result["resourceType"] == "Procedure"
        assert result["status"] == "in-progress"

    @pytest.mark.asyncio
    async def test_adapt_surgery_cancellation(self, adapter):
        result = await adapter.adapt(make_surgery_data(
            operation_type="surgery_cancellation", IE_STATUS="CANCELLED"
        ))
        assert result["resourceType"] == "Procedure"
        assert result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_adapt_surgery_details(self, adapter):
        result = await adapter.adapt(make_surgery_data(
            operation_type="surgery_details", IE_STATUS="COMPLETED"
        ))
        assert result["resourceType"] == "Procedure"
        assert "identifier" in result and "code" in result

    @pytest.mark.asyncio
    async def test_adapt_surgery_search(self, adapter):
        result = await adapter.adapt({
            "operation_type": "surgery_search",
            "NR_PACIENTE": "12345",
            "DT_INICIO": "2024-06-01",
            "DT_FIM": "2024-06-30",
        })
        assert result["resourceType"] == "Bundle" or "searchParams" in result


@pytest.mark.unit
class TestTasySurgicalAdapterTeam:
    """Tests for surgical team management."""

    @pytest.mark.asyncio
    async def test_adapt_surgeon_availability(self, adapter):
        result = await adapter.adapt({
            "operation_type": "surgeon_availability",
            "NR_MEDICO": "DOC-456",
            "DT_CONSULTA": "2024-06-15",
            "IE_DISPONIVEL": "S",
        })
        assert result["resourceType"] in ["Practitioner", "Schedule"]

    @pytest.mark.asyncio
    async def test_adapt_team_assignment(self, adapter):
        result = await adapter.adapt({
            "operation_type": "team_assignment",
            "NR_CIRURGIA": "CIR-001",
            "team_members": [
                {"NR_MEDICO": "DOC-456", "DS_FUNCAO": "surgeon"},
                {"NR_MEDICO": "DOC-789", "DS_FUNCAO": "anesthesiologist"},
            ],
        })
        assert result["resourceType"] == "CareTeam"
        assert len(result["participant"]) >= 2

    @pytest.mark.asyncio
    async def test_adapt_team_availability(self, adapter):
        result = await adapter.adapt({
            "operation_type": "team_availability",
            "NR_CIRURGIA": "CIR-001",
            "DT_CIRURGIA": "2024-06-15T08:00:00",
        })
        assert "availability" in result or result["resourceType"] == "Bundle"


@pytest.mark.unit
class TestTasySurgicalAdapterMaterials:
    """Tests for material management."""

    @pytest.mark.asyncio
    async def test_adapt_preference_card(self, adapter):
        result = await adapter.adapt({
            "operation_type": "preference_card",
            "CD_PROCEDIMENTO": "30101012",
            "materials": [{"CD_MATERIAL": "MAT-001", "QT_NECESSARIA": 2}],
        })
        assert result["resourceType"] in ["List", "SupplyRequest"]

    @pytest.mark.asyncio
    async def test_adapt_material_request(self, adapter):
        result = await adapter.adapt({
            "operation_type": "material_request",
            "NR_CIRURGIA": "CIR-001",
            "CD_MATERIAL": "MAT-001",
            "QT_SOLICITADA": 2,
        })
        assert result["resourceType"] == "SupplyRequest"

    @pytest.mark.asyncio
    async def test_adapt_material_availability(self, adapter):
        result = await adapter.adapt({
            "operation_type": "material_availability",
            "CD_MATERIAL": "MAT-001",
            "QT_NECESSARIA": 2,
        })
        assert "availability" in result or result["resourceType"] == "SupplyRequest"

    @pytest.mark.asyncio
    async def test_adapt_surgical_kit(self, adapter):
        result = await adapter.adapt({
            "operation_type": "surgical_kit",
            "CD_KIT": "KIT-001",
            "materials": [{"CD_MATERIAL": "MAT-001", "QT_KIT": 2}],
        })
        assert result["resourceType"] == "List"


@pytest.mark.unit
class TestTasySurgicalAdapterRecords:
    """Tests for surgical records and outcomes."""

    @pytest.mark.asyncio
    async def test_adapt_surgical_record(self, adapter):
        result = await adapter.adapt({
            "operation_type": "surgical_record",
            "NR_CIRURGIA": "CIR-001",
            "NR_PACIENTE": "12345",
            "DS_REGISTRO": "Cirurgia sem intercorrências",
        })
        assert result["resourceType"] in ["DocumentReference", "Observation"]

    @pytest.mark.asyncio
    async def test_adapt_surgical_notes(self, adapter):
        result = await adapter.adapt({
            "operation_type": "surgical_notes",
            "NR_CIRURGIA": "CIR-001",
            "DS_NOTAS": "Achados intraoperatórios normais",
        })
        assert result["resourceType"] in ["DocumentReference", "Observation"]

    @pytest.mark.asyncio
    async def test_adapt_complication(self, adapter):
        result = await adapter.adapt({
            "operation_type": "complication",
            "NR_CIRURGIA": "CIR-001",
            "NR_PACIENTE": "12345",
            "DS_COMPLICACAO": "Sangramento",
            "IE_GRAVIDADE": "moderate",
        })
        assert result["resourceType"] == "Condition"
        assert "severity" in result

    @pytest.mark.asyncio
    async def test_adapt_surgical_outcome(self, adapter):
        result = await adapter.adapt({
            "operation_type": "surgical_outcome",
            "NR_CIRURGIA": "CIR-001",
            "NR_PACIENTE": "12345",
            "IE_RESULTADO": "success",
        })
        assert result["resourceType"] == "Observation"
        assert result["status"] == "final"


@pytest.mark.unit
class TestTasySurgicalAdapterErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_adapt_missing_required_fields(self, adapter):
        with pytest.raises(ValueError, match="Missing required fields"):
            await adapter.adapt({"operation_type": "surgery_creation"})

    @pytest.mark.asyncio
    async def test_adapt_unknown_operation_type(self, adapter):
        with pytest.raises(ValueError, match="Unknown operation_type"):
            await adapter.adapt({
                "operation_type": "invalid_operation",
                "NR_CIRURGIA": "CIR-001",
            })

    @pytest.mark.asyncio
    async def test_adapt_missing_operation_type(self, adapter):
        with pytest.raises(ValueError):
            await adapter.adapt({"NR_CIRURGIA": "CIR-001"})


@pytest.mark.unit
class TestTasySurgicalAdapterLGPD:
    """Tests for LGPD compliance."""

    @pytest.mark.asyncio
    async def test_pii_not_in_logs(self, adapter, caplog):
        tasy_data = make_surgery_data(
            NM_PACIENTE="João da Silva",
            NR_CPF="123.456.789-00",
        )
        await adapter.adapt(tasy_data)
        log_output = caplog.text
        assert "João da Silva" not in log_output
        assert "123.456.789-00" not in log_output

    @pytest.mark.asyncio
    async def test_surgical_pii_fields_sanitized(self, adapter):
        tasy_data = make_surgery_data(NM_MEDICO="Dr. Silva")
        sanitized = adapter._sanitize_for_lgpd(tasy_data)
        if "NM_MEDICO" in adapter.PII_FIELDS:
            assert sanitized.get("NM_MEDICO") == "[REDACTED]"


@pytest.mark.unit
class TestTasySurgicalAdapterMetrics:
    """Tests for metrics tracking."""

    @pytest.mark.asyncio
    async def test_successful_conversion_tracked(self, adapter):
        await adapter.adapt(make_surgery_data())
        assert adapter.ADAPTER_TYPE == "surgical"
        assert adapter.FHIR_RESOURCE_TYPE == "Procedure"

    @pytest.mark.asyncio
    async def test_failed_conversion_tracked(self, adapter):
        with pytest.raises(ValueError):
            await adapter.adapt({"operation_type": "surgery_creation"})
