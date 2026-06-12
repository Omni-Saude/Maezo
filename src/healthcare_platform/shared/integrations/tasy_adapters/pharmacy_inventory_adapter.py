"""Tasy Pharmacy Inventory to FHIR SupplyDelivery R4 adapter.

Maps Tasy ESTOQUE_FARMACIA table to FHIR SupplyDelivery resource for stock movements
and custom extensions for stock level tracking. Supports:
- Lot number and expiration date tracking (ANVISA traceability)
- Storage condition monitoring (temperature-sensitive medications)
- Stock movement types (receipt, dispensing, transfer, adjustment, disposal)

Example Tasy data:
{
    "NR_MOVIMENTO": "MOV-001",
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
    "IE_SITUACAO": "C"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyPharmacyInventoryAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy pharmacy inventory movements to FHIR SupplyDelivery R4."""

    ADAPTER_TYPE = "pharmacy_inventory"
    FHIR_RESOURCE_TYPE = "SupplyDelivery"

    ANVISA_SYSTEM = "http://www.anvisa.gov.br/medicamentos"
    TASY_INVENTORY_SYSTEM = "http://tasy.com/fhir/identifier/inventory-movement"
    TASY_FORMULARY_SYSTEM = "http://tasy.com/fhir/identifier/formulary"
    TASY_PHARMACY_SYSTEM = "http://tasy.com/fhir/identifier/pharmacy"
    TASY_SUPPLIER_SYSTEM = "http://tasy.com/fhir/identifier/supplier"
    UCUM_SYSTEM = "http://unitsofmeasure.org"

    # Status mapping: Tasy IE_SITUACAO -> FHIR SupplyDelivery status
    STATUS_MAP = {
        "E": "in-progress",
        "C": "completed",
        "X": "abandoned",
    }

    # Movement type mapping
    MOVEMENT_TYPE_MAP = {
        "E": ("incoming", "Stock receipt"),
        "S": ("outgoing", "Stock dispensing"),
        "T": ("transfer", "Inter-pharmacy transfer"),
        "A": ("adjustment", "Stock adjustment"),
        "D": ("disposal", "Expired/damaged disposal"),
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy inventory movement to FHIR SupplyDelivery R4.

        Args:
            tasy_data: Tasy ESTOQUE_FARMACIA table data

        Returns:
            FHIR SupplyDelivery R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            self._validate_required_fields(
                tasy_data,
                ["NR_MOVIMENTO", "CD_MEDICAMENTO", "QT_MOVIMENTADA"],
            )

            self._logger.debug(
                "Converting Tasy inventory movement to FHIR SupplyDelivery",
                extra={
                    "nr_movimento": tasy_data["NR_MOVIMENTO"],
                    "tenant_id": self._tenant_id,
                },
            )

            resource: dict[str, Any] = {
                "resourceType": "SupplyDelivery",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/SupplyDelivery",
                    ],
                    "tag": [
                        {
                            "system": "http://tasy.com/fhir/tenant",
                            "code": self._tenant_id,
                        },
                    ],
                },
                "identifier": [
                    self._build_identifier(
                        system=self.TASY_INVENTORY_SYSTEM,
                        value=tasy_data["NR_MOVIMENTO"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "suppliedItem": self._build_supplied_item(tasy_data),
            }

            # Movement type
            if "IE_TIPO_MOVIMENTO" in tasy_data:
                mov_type = tasy_data["IE_TIPO_MOVIMENTO"]
                if mov_type in self.MOVEMENT_TYPE_MAP:
                    code, display = self.MOVEMENT_TYPE_MAP[mov_type]
                    resource["type"] = self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/supply-item-type",
                                code="medication",
                                display="Medication",
                            )
                        ],
                        text=display,
                    )

            if "DT_MOVIMENTO" in tasy_data:
                resource["occurrenceDateTime"] = tasy_data["DT_MOVIMENTO"]

            if "CD_FORNECEDOR" in tasy_data:
                resource["supplier"] = self._build_reference(
                    "Organization",
                    tasy_data["CD_FORNECEDOR"],
                    tasy_data.get("NM_FORNECEDOR"),
                )

            if "CD_FARMACIA_DESTINO" in tasy_data:
                resource["destination"] = self._build_reference(
                    "Location",
                    tasy_data["CD_FARMACIA_DESTINO"],
                    tasy_data.get("NM_FARMACIA_DESTINO"),
                )

            # Extensions for lot tracking, expiration, and storage
            extensions = self._build_extensions(tasy_data)
            if extensions:
                resource["extension"] = extensions

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy inventory movement to FHIR SupplyDelivery",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return resource

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy inventory movement to FHIR SupplyDelivery",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                    "sanitized_data": self._sanitize_for_lgpd(tasy_data),
                },
            )
            raise

    async def reverse_adapt(self, fhir_resource: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR SupplyDelivery R4 to Tasy inventory format.

        Args:
            fhir_resource: FHIR SupplyDelivery R4 resource

        Returns:
            Tasy ESTOQUE_FARMACIA format dictionary
        """
        try:
            tasy_data: dict[str, Any] = {}

            if "identifier" in fhir_resource:
                for identifier in fhir_resource["identifier"]:
                    if identifier.get("system") == self.TASY_INVENTORY_SYSTEM:
                        tasy_data["NR_MOVIMENTO"] = identifier["value"]
                        break

            if "status" in fhir_resource:
                for tasy_status, fhir_status in self.STATUS_MAP.items():
                    if fhir_status == fhir_resource["status"]:
                        tasy_data["IE_SITUACAO"] = tasy_status
                        break

            if "suppliedItem" in fhir_resource:
                item = fhir_resource["suppliedItem"]
                if "quantity" in item:
                    tasy_data["QT_MOVIMENTADA"] = item["quantity"].get("value")
                    tasy_data["DS_UNIDADE"] = item["quantity"].get("unit")
                if "itemCodeableConcept" in item:
                    for coding in item["itemCodeableConcept"].get("coding", []):
                        if coding.get("system") == self.ANVISA_SYSTEM:
                            tasy_data["CD_ANVISA"] = coding["code"]
                            tasy_data["NM_MEDICAMENTO"] = coding.get("display")
                        elif coding.get("system") == self.TASY_FORMULARY_SYSTEM:
                            tasy_data["CD_MEDICAMENTO"] = coding["code"]

            if "occurrenceDateTime" in fhir_resource:
                tasy_data["DT_MOVIMENTO"] = fhir_resource["occurrenceDateTime"]

            if "supplier" in fhir_resource:
                ref = fhir_resource["supplier"]["reference"]
                tasy_data["CD_FORNECEDOR"] = ref.split("/")[-1]
                tasy_data["NM_FORNECEDOR"] = fhir_resource["supplier"].get("display")

            if "destination" in fhir_resource:
                ref = fhir_resource["destination"]["reference"]
                tasy_data["CD_FARMACIA_DESTINO"] = ref.split("/")[-1]
                tasy_data["NM_FARMACIA_DESTINO"] = fhir_resource["destination"].get(
                    "display"
                )

            # Extract movement type from resource type field
            if "type" in fhir_resource:
                type_text = fhir_resource["type"].get("text", "")
                for tasy_type, (_, display) in self.MOVEMENT_TYPE_MAP.items():
                    if display == type_text:
                        tasy_data["IE_TIPO_MOVIMENTO"] = tasy_type
                        break

            # Extract extensions
            for ext in fhir_resource.get("extension", []):
                url = ext.get("url", "")
                if url.endswith("/lot-number"):
                    tasy_data["NR_LOTE"] = ext.get("valueString")
                elif url.endswith("/expiration-date"):
                    tasy_data["DT_VALIDADE"] = ext.get("valueDate")
                elif url.endswith("/storage-conditions"):
                    tasy_data["DS_CONDICAO_ARMAZENAMENTO"] = ext.get("valueString")

            self._track_conversion_success()
            self._logger.debug(
                "Successfully reverse-adapted FHIR SupplyDelivery to Tasy format",
                extra={"tenant_id": self._tenant_id},
            )

            return tasy_data

        except Exception as exc:
            self._logger.error(
                "Failed to reverse-adapt FHIR SupplyDelivery",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR SupplyDelivery status."""
        return self.STATUS_MAP.get(situacao, "in-progress") if situacao else "in-progress"

    def _build_supplied_item(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR suppliedItem with medication and quantity."""
        codings: list[dict[str, Any]] = []

        if "CD_ANVISA" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.ANVISA_SYSTEM,
                    code=tasy_data["CD_ANVISA"],
                    display=tasy_data.get("NM_MEDICAMENTO"),
                )
            )

        if "CD_MEDICAMENTO" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.TASY_FORMULARY_SYSTEM,
                    code=tasy_data["CD_MEDICAMENTO"],
                    display=tasy_data.get("NM_MEDICAMENTO"),
                )
            )

        item: dict[str, Any] = {
            "quantity": {
                "value": tasy_data["QT_MOVIMENTADA"],
                "unit": tasy_data.get("DS_UNIDADE", "unidade"),
            },
        }

        if codings:
            item["itemCodeableConcept"] = self._build_codeable_concept(
                codings=codings,
                text=tasy_data.get("NM_MEDICAMENTO"),
            )

        return item

    def _build_extensions(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build FHIR extensions for lot tracking and storage conditions."""
        extensions: list[dict[str, Any]] = []

        if "NR_LOTE" in tasy_data:
            extensions.append(
                {
                    "url": "http://tasy.com/fhir/StructureDefinition/lot-number",
                    "valueString": tasy_data["NR_LOTE"],
                }
            )

        if "DT_VALIDADE" in tasy_data:
            extensions.append(
                {
                    "url": "http://tasy.com/fhir/StructureDefinition/expiration-date",
                    "valueDate": tasy_data["DT_VALIDADE"],
                }
            )

        if "DS_CONDICAO_ARMAZENAMENTO" in tasy_data:
            extensions.append(
                {
                    "url": "http://tasy.com/fhir/StructureDefinition/storage-conditions",
                    "valueString": tasy_data["DS_CONDICAO_ARMAZENAMENTO"],
                }
            )

        return extensions
