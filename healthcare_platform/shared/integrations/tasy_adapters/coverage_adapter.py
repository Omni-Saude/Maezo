"""Tasy Coverage to FHIR Coverage R4 adapter.

Maps Tasy CONVENIO_PACIENTE table to FHIR Coverage resource:
- CD_CONVENIO -> Coverage.identifier
- NR_CARTEIRA -> Coverage.subscriberId
- DT_VALIDADE -> Coverage.period.end
- IE_TIPO_CONVENIO -> Coverage.type
- Reference to Patient
- Reference to Organization (payor)

Example Tasy data:
{
    "CD_CONVENIO": "CONV-123",
    "NM_CONVENIO": "Unimed São Paulo",
    "NR_CARTEIRA": "9876543210",
    "DT_VALIDADE": "2025-12-31",
    "IE_TIPO_CONVENIO": "P",  # P=particular, C=convênio, S=SUS
    "NR_PACIENTE": "123456",
    "IE_SITUACAO": "A",
    "DT_INICIO": "2024-01-01"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyCoverageAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy CONVENIO_PACIENTE to FHIR Coverage R4."""

    ADAPTER_TYPE = "coverage"
    FHIR_RESOURCE_TYPE = "Coverage"

    # Identifier systems
    TASY_CONVENIO_SYSTEM = "http://tasy.com/fhir/identifier/convenio"
    CARTEIRA_SYSTEM = "http://tasy.com/fhir/identifier/carteira"

    # Coverage type mapping
    COVERAGE_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
    COVERAGE_TYPE_MAP = {
        "P": ("PUBLICPOL", "public healthcare"),  # Particular/SUS
        "C": ("EHCPOL", "extended healthcare"),  # Convênio/Private insurance
        "S": ("PUBLICPOL", "public healthcare"),  # SUS
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy CONVENIO_PACIENTE to FHIR Coverage R4.

        Args:
            tasy_data: Tasy CONVENIO_PACIENTE table data

        Returns:
            FHIR Coverage R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["CD_CONVENIO", "NR_CARTEIRA", "NR_PACIENTE"],
            )

            self._logger.debug(
                "Converting Tasy coverage to FHIR",
                extra={
                    "cd_convenio": tasy_data["CD_CONVENIO"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR Coverage resource
            coverage: dict[str, Any] = {
                "resourceType": "Coverage",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/Coverage",
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
                        system=self.TASY_CONVENIO_SYSTEM,
                        value=tasy_data["CD_CONVENIO"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "subscriberId": tasy_data["NR_CARTEIRA"],
                "beneficiary": self._build_reference(
                    "Patient",
                    tasy_data["NR_PACIENTE"],
                ),
                "payor": [
                    self._build_payor_reference(
                        tasy_data.get("CD_CONVENIO"),
                        tasy_data.get("NM_CONVENIO"),
                    )
                ],
            }

            # Add coverage type if available
            if "IE_TIPO_CONVENIO" in tasy_data:
                coverage["type"] = self._build_coverage_type(
                    tasy_data["IE_TIPO_CONVENIO"]
                )

            # Add period if dates available
            period = self._build_period(
                tasy_data.get("DT_INICIO"), tasy_data.get("DT_VALIDADE")
            )
            if period:
                coverage["period"] = period

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy coverage to FHIR",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return coverage

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy coverage to FHIR",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR Coverage status.

        Args:
            situacao: Tasy IE_SITUACAO value (A=active, I=inactive, C=cancelled)

        Returns:
            FHIR status code (active, cancelled, draft, entered-in-error)
        """
        status_map = {
            "A": "active",
            "I": "cancelled",
            "C": "cancelled",
        }
        return status_map.get(situacao, "active") if situacao else "active"

    def _build_coverage_type(self, tipo_convenio: str) -> dict[str, Any]:
        """Build FHIR coverage type CodeableConcept.

        Args:
            tipo_convenio: Tasy IE_TIPO_CONVENIO (P, C, S)

        Returns:
            FHIR CodeableConcept for coverage type
        """
        code, display = self.COVERAGE_TYPE_MAP.get(
            tipo_convenio, ("PUBLICPOL", "public healthcare")
        )

        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.COVERAGE_TYPE_SYSTEM, code=code, display=display
                )
            ],
            text=display,
        )

    def _build_period(
        self, dt_inicio: str | None, dt_validade: str | None
    ) -> dict[str, Any] | None:
        """Build FHIR Period from Tasy date fields.

        Args:
            dt_inicio: Start date (YYYY-MM-DD)
            dt_validade: End/expiration date (YYYY-MM-DD)

        Returns:
            FHIR Period structure or None if no dates provided
        """
        if not dt_inicio and not dt_validade:
            return None

        period: dict[str, Any] = {}

        if dt_inicio:
            period["start"] = dt_inicio

        if dt_validade:
            period["end"] = dt_validade

        return period

    def _build_payor_reference(
        self, cd_convenio: str | None, nm_convenio: str | None
    ) -> dict[str, Any]:
        """Build reference to payor Organization.

        Note: In production, this would need to resolve CD_CONVENIO to a FHIR
        Organization resource ID. For now, we use the Tasy code as identifier.

        Args:
            cd_convenio: Tasy convênio code
            nm_convenio: Convênio name for display

        Returns:
            FHIR Reference to Organization
        """
        # TODO: Query FHIR server to resolve Organization by identifier
        # For now, use identifier-based reference
        reference: dict[str, Any] = {
            "type": "Organization",
        }

        if cd_convenio:
            reference["identifier"] = self._build_identifier(
                system=self.TASY_CONVENIO_SYSTEM,
                value=cd_convenio,
            )

        if nm_convenio:
            reference["display"] = nm_convenio

        return reference
