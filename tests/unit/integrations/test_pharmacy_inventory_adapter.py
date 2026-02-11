"""Unit tests for TasyPharmacyInventoryAdapter."""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.integrations.tasy_adapters.pharmacy_inventory_adapter import (
    TasyPharmacyInventoryAdapter,
)


@pytest.fixture
def fhir_client():
    return MagicMock()


@pytest.fixture
def adapter(fhir_client):
    return TasyPharmacyInventoryAdapter(fhir_client=fhir_client, tenant_id="test-hospital")


@pytest.mark.asyncio
async def test_adapt_minimal(adapter):
    tasy_data = {
        "NR_MOVIMENTO": "MOV-001",
        "CD_MEDICAMENTO": "MED-AMO-500",
        "QT_MOVIMENTADA": 100,
    }
    result = await adapter.adapt(tasy_data)

    assert result["resourceType"] == "SupplyDelivery"
    assert result["status"] == "in-progress"
    assert result["identifier"][0]["value"] == "MOV-001"
    assert result["suppliedItem"]["quantity"]["value"] == 100
    assert result["suppliedItem"]["quantity"]["unit"] == "unidade"
    assert any(
        c["system"] == "http://tasy.com/fhir/identifier/formulary" and c["code"] == "MED-AMO-500"
        for c in result["suppliedItem"]["itemCodeableConcept"]["coding"]
    )


@pytest.mark.asyncio
async def test_adapt_complete_with_brazilian_codes(adapter):
    tasy_data = {
        "NR_MOVIMENTO": "MOV-002",
        "CD_MEDICAMENTO": "MED-AMO-500",
        "CD_ANVISA": "1234567890123",
        "NM_MEDICAMENTO": "Amoxicilina 500mg",
        "QT_MOVIMENTADA": 100,
        "DS_UNIDADE": "comprimido",
        "DT_MOVIMENTO": "2024-02-10T08:00:00",
        "IE_TIPO_MOVIMENTO": "E",
        "NR_LOTE": "LOT-2024-001",
        "DT_VALIDADE": "2025-06-30",
        "DS_CONDICAO_ARMAZENAMENTO": "Temperatura ambiente (15-30°C)",
        "CD_FORNECEDOR": "FORN-001",
        "NM_FORNECEDOR": "Distribuidora Pharma Ltda",
        "CD_FARMACIA_DESTINO": "FARM-CENTRAL",
        "NM_FARMACIA_DESTINO": "Farmácia Central",
        "IE_SITUACAO": "C",
    }
    result = await adapter.adapt(tasy_data)

    assert result["status"] == "completed"
    assert result["occurrenceDateTime"] == "2024-02-10T08:00:00"
    assert result["supplier"]["reference"] == "Organization/FORN-001"
    assert result["supplier"]["display"] == "Distribuidora Pharma Ltda"
    assert result["destination"]["reference"] == "Location/FARM-CENTRAL"
    assert result["destination"]["display"] == "Farmácia Central"
    assert result["suppliedItem"]["quantity"]["value"] == 100
    assert result["suppliedItem"]["quantity"]["unit"] == "comprimido"

    # Brazilian codes (ANVISA)
    codings = result["suppliedItem"]["itemCodeableConcept"]["coding"]
    assert any(
        c["system"] == "http://www.anvisa.gov.br/medicamentos" and c["code"] == "1234567890123"
        for c in codings
    )
    assert any(
        c["system"] == "http://tasy.com/fhir/identifier/formulary" and c["code"] == "MED-AMO-500"
        for c in codings
    )

    # Movement type
    assert result["type"]["text"] == "Stock receipt"

    # Extensions
    extensions = result["extension"]
    assert any(
        ext["url"] == "http://tasy.com/fhir/StructureDefinition/lot-number"
        and ext["valueString"] == "LOT-2024-001"
        for ext in extensions
    )
    assert any(
        ext["url"] == "http://tasy.com/fhir/StructureDefinition/expiration-date"
        and ext["valueDate"] == "2025-06-30"
        for ext in extensions
    )
    assert any(
        ext["url"] == "http://tasy.com/fhir/StructureDefinition/storage-conditions"
        and ext["valueString"] == "Temperatura ambiente (15-30°C)"
        for ext in extensions
    )


@pytest.mark.asyncio
async def test_reverse_adapt(adapter):
    fhir_resource = {
        "resourceType": "SupplyDelivery",
        "identifier": [{"system": "http://tasy.com/fhir/identifier/inventory-movement", "value": "MOV-999"}],
        "status": "completed",
        "suppliedItem": {
            "quantity": {"value": 200, "unit": "comprimido"},
            "itemCodeableConcept": {
                "coding": [
                    {"system": "http://www.anvisa.gov.br/medicamentos", "code": "9876543210987", "display": "Ibuprofeno 600mg"},
                    {"system": "http://tasy.com/fhir/identifier/formulary", "code": "MED-IBU-600"},
                ]
            },
        },
        "occurrenceDateTime": "2024-02-11T09:00:00",
        "supplier": {"reference": "Organization/FORN-999", "display": "Fornecedor XYZ"},
        "destination": {"reference": "Location/FARM-SUL", "display": "Farmácia Sul"},
        "extension": [
            {"url": "http://tasy.com/fhir/StructureDefinition/lot-number", "valueString": "LOT-2024-999"},
            {"url": "http://tasy.com/fhir/StructureDefinition/expiration-date", "valueDate": "2026-12-31"},
            {"url": "http://tasy.com/fhir/StructureDefinition/storage-conditions", "valueString": "Refrigeração (2-8°C)"},
        ],
    }
    result = await adapter.reverse_adapt(fhir_resource)

    assert result["NR_MOVIMENTO"] == "MOV-999"
    assert result["IE_SITUACAO"] == "C"
    assert result["QT_MOVIMENTADA"] == 200
    assert result["DS_UNIDADE"] == "comprimido"
    assert result["CD_ANVISA"] == "9876543210987"
    assert result["NM_MEDICAMENTO"] == "Ibuprofeno 600mg"
    assert result["CD_MEDICAMENTO"] == "MED-IBU-600"
    assert result["DT_MOVIMENTO"] == "2024-02-11T09:00:00"
    assert result["CD_FORNECEDOR"] == "FORN-999"
    assert result["NM_FORNECEDOR"] == "Fornecedor XYZ"
    assert result["CD_FARMACIA_DESTINO"] == "FARM-SUL"
    assert result["NM_FARMACIA_DESTINO"] == "Farmácia Sul"
    assert result["NR_LOTE"] == "LOT-2024-999"
    assert result["DT_VALIDADE"] == "2026-12-31"
    assert result["DS_CONDICAO_ARMAZENAMENTO"] == "Refrigeração (2-8°C)"


@pytest.mark.asyncio
async def test_lot_tracking(adapter):
    tasy_data = {
        "NR_MOVIMENTO": "MOV-LOT",
        "CD_MEDICAMENTO": "MED-INSULIN",
        "QT_MOVIMENTADA": 50,
        "NR_LOTE": "LOT-2024-INSULIN-123",
        "DT_VALIDADE": "2024-12-31",
        "DS_CONDICAO_ARMAZENAMENTO": "Refrigeração obrigatória (2-8°C). Não congelar.",
    }
    result = await adapter.adapt(tasy_data)

    # Verify lot tracking extensions are created properly
    extensions = result["extension"]
    assert len(extensions) == 3

    lot_ext = next(
        (ext for ext in extensions if ext["url"] == "http://tasy.com/fhir/StructureDefinition/lot-number"),
        None,
    )
    assert lot_ext is not None
    assert lot_ext["valueString"] == "LOT-2024-INSULIN-123"

    exp_ext = next(
        (ext for ext in extensions if ext["url"] == "http://tasy.com/fhir/StructureDefinition/expiration-date"),
        None,
    )
    assert exp_ext is not None
    assert exp_ext["valueDate"] == "2024-12-31"

    storage_ext = next(
        (ext for ext in extensions if ext["url"] == "http://tasy.com/fhir/StructureDefinition/storage-conditions"),
        None,
    )
    assert storage_ext is not None
    assert storage_ext["valueString"] == "Refrigeração obrigatória (2-8°C). Não congelar."
