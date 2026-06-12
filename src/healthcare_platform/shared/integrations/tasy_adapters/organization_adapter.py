"""Tasy CONVENIO to FHIR Organization R4 adapter.

Maps Tasy CONVENIO table to FHIR Organization resource per V24 specification:
- CD_CONVENIO -> Organization.identifier (system=tasy-convenio)
- NM_CONVENIO -> Organization.name
- NR_CNPJ -> Organization.identifier (system=cnpj)
- NR_ANS -> Organization.identifier (system=ans)
- IE_ATIVO -> Organization.active (S=true, N=false)

Example Tasy data:
{
    "CD_CONVENIO": "42",
    "NM_CONVENIO": "Unimed São Paulo",
    "NR_CNPJ": "12345678000199",
    "NR_ANS": "312345",
    "IE_ATIVO": "S"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyOrganizationAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy CONVENIO to FHIR Organization R4."""

    ADAPTER_TYPE = "organization"
    FHIR_RESOURCE_TYPE = "Organization"

    TASY_CONVENIO_SYSTEM = "http://tasy.com/fhir/identifier/convenio"
    CNPJ_SYSTEM = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnpj"
    ANS_SYSTEM = "http://www.ans.gov.br/registry"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy CONVENIO to FHIR Organization R4.

        Args:
            tasy_data: Tasy CONVENIO table data

        Returns:
            FHIR Organization R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            self._validate_required_fields(
                tasy_data, ["CD_CONVENIO", "NM_CONVENIO"]
            )

            self._logger.debug(
                "Converting Tasy convenio to FHIR Organization",
                extra={
                    "tasy_data": self._sanitize_for_lgpd(tasy_data),
                    "tenant_id": self._tenant_id,
                },
            )

            organization: dict[str, Any] = {
                "resourceType": "Organization",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/Organization",
                    ],
                    "tag": [
                        {
                            "system": "http://tasy.com/fhir/tenant",
                            "code": self._tenant_id,
                        },
                    ],
                },
                "identifier": self._build_identifiers(tasy_data),
                "active": tasy_data.get("IE_ATIVO", "S") == "S",
                "name": tasy_data["NM_CONVENIO"],
                "type": [
                    self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/organization-type",
                                code="ins",
                                display="Insurance Company",
                            )
                        ]
                    )
                ],
            }

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy convenio to FHIR Organization",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return organization

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy convenio to FHIR Organization",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _build_identifiers(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build FHIR identifier list from Tasy convenio data."""
        identifiers = [
            self._build_identifier(
                system=self.TASY_CONVENIO_SYSTEM,
                value=str(tasy_data["CD_CONVENIO"]),
            )
        ]

        if tasy_data.get("NR_CNPJ"):
            identifiers.append(
                self._build_identifier(
                    system=self.CNPJ_SYSTEM,
                    value=tasy_data["NR_CNPJ"],
                    type_code="TAX",
                )
            )

        if tasy_data.get("NR_ANS"):
            identifiers.append(
                self._build_identifier(
                    system=self.ANS_SYSTEM,
                    value=tasy_data["NR_ANS"],
                )
            )

        return identifiers
