"""Tasy Pricing to FHIR ChargeItemDefinition R4 adapter.

Maps Tasy TABELA_PRECO tables to FHIR ChargeItemDefinition resource for
Brasindice/SIMPRO price table lookups (36 combinations: 6 types x 6 editions).

Brasindice editions:
- Hospitalar (hospital pricing)
- Varejo (retail pharmacy pricing)

SIMPRO editions:
- Hospitalar (hospital pricing)
- Varejo (retail pharmacy pricing)
- Industrial (wholesale pricing)
- Farmácia (pharmacy pricing)

Price table types:
- Medicamento (medications)
- Material (medical materials)
- Gases (medical gases)
- Dietas (nutritional diets)
- Soluções (medical solutions)
- OPME (orthopedic/prosthetic materials)

Example Tasy data:
{
    "CD_TABELA_PRECO": "BRAS-HOSP-MED-001",
    "DS_PRODUTO": "Dipirona Sódica 500mg",
    "VL_PRECO": 12.50,
    "CD_PRODUTO": "7891234567890",  # EAN/GTIN barcode
    "IE_TIPO_TABELA": "medicamento",
    "CD_EDICAO": "brasindice_hospitalar",
    "DT_VIGENCIA": "2024-02-01",
    "DT_VALIDADE": "2024-12-31",
    "CD_FORNECEDOR": "FORN-123",
    "DS_FABRICANTE": "EMS S/A"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyPricingAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy TABELA_PRECO to FHIR ChargeItemDefinition R4.

    Supports 36 price table combinations:
    - 6 price table types (medicamento, material, gases, dietas, soluções, OPME)
    - 6 editions (brasindice_hospitalar, brasindice_varejo, simpro_hospitalar,
                  simpro_varejo, simpro_industrial, simpro_farmacia)
    """

    ADAPTER_TYPE = "pricing"
    FHIR_RESOURCE_TYPE = "ChargeItemDefinition"

    # Identifier systems
    BRASINDICE_SYSTEM = "http://brasindice.com.br/fhir/price-table"
    SIMPRO_SYSTEM = "http://simpro.com.br/fhir/price-table"
    TASY_PRICE_SYSTEM = "http://tasy.com/fhir/identifier/tabela-preco"
    GTIN_SYSTEM = "http://hl7.org/fhir/sid/gtin"

    # Price table types
    PRICE_TABLE_TYPES = [
        "medicamento",
        "material",
        "gases",
        "dietas",
        "solucoes",
        "opme",
    ]

    # Price editions
    PRICE_EDITIONS = [
        "brasindice_hospitalar",
        "brasindice_varejo",
        "simpro_hospitalar",
        "simpro_varejo",
        "simpro_industrial",
        "simpro_farmacia",
    ]

    # Type display names (pt-BR)
    TYPE_DISPLAY_MAP = {
        "medicamento": "Medicamento",
        "material": "Material Médico-Hospitalar",
        "gases": "Gases Medicinais",
        "dietas": "Dietas e Nutrição Enteral",
        "solucoes": "Soluções Parenterais",
        "opme": "Órteses, Próteses e Materiais Especiais",
    }

    # Edition display names (pt-BR)
    EDITION_DISPLAY_MAP = {
        "brasindice_hospitalar": "Brasíndice - Hospitalar",
        "brasindice_varejo": "Brasíndice - Varejo",
        "simpro_hospitalar": "SIMPRO - Hospitalar",
        "simpro_varejo": "SIMPRO - Varejo",
        "simpro_industrial": "SIMPRO - Industrial",
        "simpro_farmacia": "SIMPRO - Farmácia",
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy TABELA_PRECO to FHIR ChargeItemDefinition R4.

        Args:
            tasy_data: Tasy TABELA_PRECO data with price table entry

        Returns:
            FHIR ChargeItemDefinition R4 resource

        Raises:
            ValueError: If required fields are missing or invalid combination
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["CD_TABELA_PRECO", "DS_PRODUTO", "VL_PRECO", "CD_PRODUTO"],
            )

            # Validate price table combination
            table_type = tasy_data.get("IE_TIPO_TABELA", "")
            edition = tasy_data.get("CD_EDICAO", "")

            if not self.validate_price_table_combination(table_type, edition):
                raise ValueError(
                    f"Invalid price table combination: type={table_type}, edition={edition}"
                )

            self._logger.debug(
                "Converting Tasy price table to FHIR ChargeItemDefinition",
                extra={
                    "cd_tabela_preco": tasy_data["CD_TABELA_PRECO"],
                    "table_type": table_type,
                    "edition": edition,
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR ChargeItemDefinition resource
            charge_item_def = self._build_charge_item_definition(tasy_data)

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy price table to FHIR ChargeItemDefinition",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "table_type": table_type,
                    "edition": edition,
                    "tenant_id": self._tenant_id,
                },
            )

            return charge_item_def

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy price table to FHIR ChargeItemDefinition",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def get_price_table_code(self, table_type: str, edition: str) -> str:
        """Generate combined price table code.

        Args:
            table_type: Price table type (medicamento, material, etc.)
            edition: Price edition (brasindice_hospitalar, simpro_varejo, etc.)

        Returns:
            Combined code like "brasindice_hospitalar:medicamento"

        Raises:
            ValueError: If combination is invalid
        """
        if not self.validate_price_table_combination(table_type, edition):
            raise ValueError(
                f"Invalid price table combination: type={table_type}, edition={edition}"
            )

        return f"{edition}:{table_type}"

    def validate_price_table_combination(self, table_type: str, edition: str) -> bool:
        """Validate if price table type and edition combination is supported.

        Args:
            table_type: Price table type
            edition: Price edition

        Returns:
            True if combination is valid, False otherwise
        """
        return (
            table_type in self.PRICE_TABLE_TYPES
            and edition in self.PRICE_EDITIONS
        )

    def _build_charge_item_definition(
        self, tasy_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build FHIR ChargeItemDefinition from Tasy price table data.

        Args:
            tasy_data: Tasy TABELA_PRECO data

        Returns:
            FHIR ChargeItemDefinition R4 structure
        """
        table_type = tasy_data.get("IE_TIPO_TABELA", "")
        edition = tasy_data.get("CD_EDICAO", "")

        charge_item_def: dict[str, Any] = {
            "resourceType": "ChargeItemDefinition",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/ChargeItemDefinition",
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
                    system=self.TASY_PRICE_SYSTEM,
                    value=tasy_data["CD_TABELA_PRECO"],
                )
            ],
            "status": "active",
            "title": tasy_data["DS_PRODUTO"],
            "code": self._build_product_code(
                tasy_data["CD_PRODUTO"],
                tasy_data["DS_PRODUTO"],
            ),
        }

        # Add edition and type as additional identifiers
        charge_item_def["identifier"].append(
            self._build_identifier(
                system=self._get_edition_system(edition),
                value=self.get_price_table_code(table_type, edition),
            )
        )

        # Add product type applicability
        charge_item_def["applicability"] = [
            self._build_applicability(table_type)
        ]

        # Add property group with price component
        charge_item_def["propertyGroup"] = [
            self._build_property_group(tasy_data)
        ]

        # Add effective period if dates provided
        if "DT_VIGENCIA" in tasy_data or "DT_VALIDADE" in tasy_data:
            charge_item_def["effectivePeriod"] = {}
            if "DT_VIGENCIA" in tasy_data:
                charge_item_def["effectivePeriod"]["start"] = tasy_data["DT_VIGENCIA"]
            if "DT_VALIDADE" in tasy_data:
                charge_item_def["effectivePeriod"]["end"] = tasy_data["DT_VALIDADE"]

        return charge_item_def

    def _get_edition_system(self, edition: str) -> str:
        """Get the appropriate system URI for the price edition.

        Args:
            edition: Price edition code

        Returns:
            System URI (Brasindice or SIMPRO)
        """
        if edition.startswith("brasindice"):
            return self.BRASINDICE_SYSTEM
        elif edition.startswith("simpro"):
            return self.SIMPRO_SYSTEM
        else:
            # Fallback to Tasy system
            return self.TASY_PRICE_SYSTEM

    def _build_product_code(
        self, cd_produto: str, ds_produto: str
    ) -> dict[str, Any]:
        """Build CodeableConcept for product code.

        Args:
            cd_produto: Product code (typically EAN/GTIN barcode)
            ds_produto: Product description

        Returns:
            FHIR CodeableConcept
        """
        codings = [
            self._build_coding(
                system=self.GTIN_SYSTEM,
                code=cd_produto,
                display=ds_produto,
            )
        ]

        return self._build_codeable_concept(
            codings=codings,
            text=ds_produto,
        )

    def _build_applicability(self, table_type: str) -> dict[str, Any]:
        """Build applicability element for product type.

        Args:
            table_type: Price table type (medicamento, material, etc.)

        Returns:
            FHIR ChargeItemDefinition.applicability structure
        """
        type_display = self.TYPE_DISPLAY_MAP.get(table_type, table_type)

        return {
            "description": f"Aplicável para: {type_display}",
            "expression": f"productType = '{table_type}'",
        }

    def _build_property_group(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build propertyGroup with price component.

        Args:
            tasy_data: Tasy TABELA_PRECO data

        Returns:
            FHIR ChargeItemDefinition.propertyGroup structure
        """
        property_group: dict[str, Any] = {
            "priceComponent": [
                {
                    "type": "base",
                    "code": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/chargeitem-billingcodes",
                                code="base",
                                display="Base Price",
                            )
                        ],
                        text="Preço Base",
                    ),
                    "amount": self._build_money(tasy_data["VL_PRECO"]),
                }
            ]
        }

        # Add manufacturer info if available
        if "DS_FABRICANTE" in tasy_data:
            property_group["extension"] = [
                {
                    "url": "http://tasy.com/fhir/extension/manufacturer",
                    "valueString": tasy_data["DS_FABRICANTE"],
                }
            ]

        return property_group

    def _build_money(self, value: float) -> dict[str, Any]:
        """Build FHIR Money datatype.

        Args:
            value: Monetary amount

        Returns:
            FHIR Money structure with BRL currency
        """
        return {
            "value": value,
            "currency": "BRL",
        }
