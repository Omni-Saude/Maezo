"""Tasy Billing to FHIR Claim R4 adapter.

Maps Tasy CONTA_MEDICA + ITEM_CONTA tables to FHIR Claim resource:
- NR_CONTA -> Claim.identifier
- DT_CONTA -> Claim.created
- VL_TOTAL -> Claim.total
- IE_SITUACAO -> Claim.status
- Items from ITEM_CONTA -> Claim.item[] with:
  - CD_PROCEDIMENTO -> item.productOrService
  - QT_ITEM -> item.quantity
  - VL_ITEM -> item.unitPrice

Example Tasy data:
{
    "NR_CONTA": "CONTA-456",
    "DT_CONTA": "2024-02-10",
    "VL_TOTAL": 2500.00,
    "IE_SITUACAO": "A",  # A=aberta, F=fechada, P=paga, G=glosada
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "CD_CONVENIO": "CONV-123",
    "items": [
        {
            "CD_ITEM_CONTA": "ITEM-001",
            "CD_PROCEDIMENTO": "40101010",  # TUSS/CBHPM code
            "DS_PROCEDIMENTO": "Consulta médica",
            "QT_ITEM": 1,
            "VL_UNITARIO": 500.00,
            "VL_TOTAL": 500.00
        },
        {
            "CD_ITEM_CONTA": "ITEM-002",
            "CD_PROCEDIMENTO": "20104030",
            "DS_PROCEDIMENTO": "Raio-X de tórax",
            "QT_ITEM": 1,
            "VL_UNITARIO": 2000.00,
            "VL_TOTAL": 2000.00
        }
    ]
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyBillingAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy CONTA_MEDICA to FHIR Claim R4."""

    ADAPTER_TYPE = "billing"
    FHIR_RESOURCE_TYPE = "Claim"

    # Identifier system
    TASY_CONTA_SYSTEM = "http://tasy.com/fhir/identifier/conta-medica"

    # Status mapping
    STATUS_MAP = {
        "A": "active",
        "F": "active",
        "P": "active",
        "C": "cancelled",
        "G": "active",  # Glosada (with denial)
    }

    # Procedure code system (TUSS/CBHPM)
    TUSS_SYSTEM = "http://www.ans.gov.br/tiss/terminologia-de-unificacao-da-saude-suplementar"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy CONTA_MEDICA to FHIR Claim R4.

        Args:
            tasy_data: Tasy CONTA_MEDICA + ITEM_CONTA data

        Returns:
            FHIR Claim R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["NR_CONTA", "DT_CONTA", "NR_PACIENTE", "NR_ATENDIMENTO"],
            )

            self._logger.debug(
                "Converting Tasy billing to FHIR Claim",
                extra={
                    "nr_conta": tasy_data["NR_CONTA"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR Claim resource
            claim: dict[str, Any] = {
                "resourceType": "Claim",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/Claim",
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
                        system=self.TASY_CONTA_SYSTEM,
                        value=tasy_data["NR_CONTA"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "type": self._build_claim_type(),
                "use": "claim",
                "patient": self._build_reference(
                    "Patient",
                    tasy_data["NR_PACIENTE"],
                ),
                "created": tasy_data["DT_CONTA"],
                "provider": self._build_provider_reference(),
            }

            # Add insurance reference if convênio provided
            if "CD_CONVENIO" in tasy_data:
                claim["insurance"] = [
                    self._build_insurance(
                        tasy_data["CD_CONVENIO"],
                        tasy_data["NR_PACIENTE"],
                    )
                ]

            # Add items if provided
            if "items" in tasy_data and tasy_data["items"]:
                claim["item"] = self._build_items(tasy_data["items"])

            # Add total if provided
            if "VL_TOTAL" in tasy_data:
                claim["total"] = self._build_money(tasy_data["VL_TOTAL"])

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy billing to FHIR Claim",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return claim

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy billing to FHIR Claim",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR Claim status.

        Args:
            situacao: Tasy IE_SITUACAO value

        Returns:
            FHIR status code (active, cancelled, draft, entered-in-error)
        """
        return self.STATUS_MAP.get(situacao, "active") if situacao else "active"

    def _build_claim_type(self) -> dict[str, Any]:
        """Build FHIR claim type CodeableConcept.

        Returns professional claim type for hospital billing.
        """
        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system="http://terminology.hl7.org/CodeSystem/claim-type",
                    code="professional",
                    display="Professional",
                )
            ],
            text="Professional",
        )

    def _build_provider_reference(self) -> dict[str, Any]:
        """Build reference to provider Organization.

        Note: In production, this would reference the actual provider Organization.
        For now, returns a placeholder reference.
        """
        return {
            "type": "Organization",
            "display": "Healthcare Provider",
        }

    def _build_insurance(
        self, cd_convenio: str, nr_paciente: str
    ) -> dict[str, Any]:
        """Build Claim.insurance element.

        Args:
            cd_convenio: Tasy convênio code
            nr_paciente: Patient identifier

        Returns:
            FHIR Claim.insurance structure
        """
        return {
            "sequence": 1,
            "focal": True,
            "coverage": {
                "type": "Coverage",
                "identifier": self._build_identifier(
                    system="http://tasy.com/fhir/identifier/convenio",
                    value=cd_convenio,
                ),
            },
        }

    def _build_items(self, tasy_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build FHIR Claim.item array from Tasy ITEM_CONTA.

        Args:
            tasy_items: List of Tasy ITEM_CONTA records

        Returns:
            List of FHIR Claim.item structures
        """
        fhir_items = []

        for idx, item in enumerate(tasy_items, start=1):
            fhir_item: dict[str, Any] = {
                "sequence": idx,
                "productOrService": self._build_procedure_code(
                    item.get("CD_PROCEDIMENTO", ""),
                    item.get("DS_PROCEDIMENTO"),
                ),
            }

            # Add quantity if present
            if "QT_ITEM" in item:
                fhir_item["quantity"] = {
                    "value": item["QT_ITEM"],
                }

            # Add unit price if present
            if "VL_UNITARIO" in item:
                fhir_item["unitPrice"] = self._build_money(item["VL_UNITARIO"])

            # Add net (total) if present
            if "VL_TOTAL" in item:
                fhir_item["net"] = self._build_money(item["VL_TOTAL"])

            fhir_items.append(fhir_item)

        return fhir_items

    def _build_procedure_code(
        self, cd_procedimento: str, ds_procedimento: str | None
    ) -> dict[str, Any]:
        """Build CodeableConcept for procedure code.

        Args:
            cd_procedimento: TUSS/CBHPM procedure code
            ds_procedimento: Procedure description

        Returns:
            FHIR CodeableConcept
        """
        codings = []

        if cd_procedimento:
            codings.append(
                self._build_coding(
                    system=self.TUSS_SYSTEM,
                    code=cd_procedimento,
                    display=ds_procedimento,
                )
            )

        return self._build_codeable_concept(
            codings=codings,
            text=ds_procedimento,
        )

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
