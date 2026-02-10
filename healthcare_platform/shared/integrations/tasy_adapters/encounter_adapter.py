"""Tasy Encounter to FHIR Encounter R4 adapter.

Maps Tasy ATENDIMENTO table to FHIR Encounter resource:
- NR_ATENDIMENTO -> Encounter.identifier
- DT_ATENDIMENTO -> Encounter.period.start
- DT_ALTA -> Encounter.period.end
- TP_ATENDIMENTO -> Encounter.class (I=inpatient, A=ambulatory, E=emergency)
- IE_SITUACAO -> Encounter.status (A=in-progress, F=finished, C=cancelled)
- Reference to Patient (subject)
- Reference to Location (serviceProvider)

Example Tasy data:
{
    "NR_ATENDIMENTO": "ATD-789",
    "DT_ATENDIMENTO": "2024-02-01T08:30:00",
    "DT_ALTA": "2024-02-05T14:00:00",
    "TP_ATENDIMENTO": "I",  # I=internação, A=ambulatorial, E=emergência
    "IE_SITUACAO": "F",  # A=ativo, F=finalizado, C=cancelado
    "NR_PACIENTE": "123456",
    "CD_ESTABELECIMENTO": "HOSP-01",
    "NM_ESTABELECIMENTO": "Hospital Central"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyEncounterAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy ATENDIMENTO to FHIR Encounter R4."""

    ADAPTER_TYPE = "encounter"
    FHIR_RESOURCE_TYPE = "Encounter"

    # Identifier system
    TASY_ATENDIMENTO_SYSTEM = "http://tasy.com/fhir/identifier/atendimento"

    # Encounter class mapping (v3-ActCode)
    CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
    CLASS_MAP = {
        "I": ("IMP", "inpatient encounter"),
        "A": ("AMB", "ambulatory"),
        "E": ("EMER", "emergency"),
        "U": ("OBSENC", "observation encounter"),
    }

    # Status mapping
    STATUS_MAP = {
        "A": "in-progress",
        "F": "finished",
        "C": "cancelled",
        "P": "planned",
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy ATENDIMENTO to FHIR Encounter R4.

        Args:
            tasy_data: Tasy ATENDIMENTO table data

        Returns:
            FHIR Encounter R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["NR_ATENDIMENTO", "DT_ATENDIMENTO", "TP_ATENDIMENTO", "NR_PACIENTE"],
            )

            self._logger.debug(
                "Converting Tasy encounter to FHIR",
                extra={
                    "nr_atendimento": tasy_data["NR_ATENDIMENTO"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR Encounter resource
            encounter: dict[str, Any] = {
                "resourceType": "Encounter",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/Encounter",
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
                        system=self.TASY_ATENDIMENTO_SYSTEM,
                        value=tasy_data["NR_ATENDIMENTO"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "class": self._build_encounter_class(tasy_data["TP_ATENDIMENTO"]),
                "subject": self._build_reference(
                    "Patient",
                    tasy_data["NR_PACIENTE"],
                ),
            }

            # Add period if dates available
            period = self._build_period(
                tasy_data["DT_ATENDIMENTO"], tasy_data.get("DT_ALTA")
            )
            if period:
                encounter["period"] = period

            # Add service provider (location) if available
            if "CD_ESTABELECIMENTO" in tasy_data:
                encounter["serviceProvider"] = self._build_location_reference(
                    tasy_data["CD_ESTABELECIMENTO"],
                    tasy_data.get("NM_ESTABELECIMENTO"),
                )

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy encounter to FHIR",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return encounter

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy encounter to FHIR",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR Encounter status.

        Args:
            situacao: Tasy IE_SITUACAO value

        Returns:
            FHIR status code (in-progress, finished, cancelled, planned, etc.)
        """
        return (
            self.STATUS_MAP.get(situacao, "in-progress") if situacao else "in-progress"
        )

    def _build_encounter_class(self, tp_atendimento: str) -> dict[str, Any]:
        """Build FHIR encounter class Coding.

        Args:
            tp_atendimento: Tasy TP_ATENDIMENTO value

        Returns:
            FHIR Coding for encounter class
        """
        code, display = self.CLASS_MAP.get(
            tp_atendimento, ("AMB", "ambulatory")
        )

        return self._build_coding(
            system=self.CLASS_SYSTEM, code=code, display=display
        )

    def _build_period(
        self, dt_atendimento: str, dt_alta: str | None
    ) -> dict[str, Any]:
        """Build FHIR Period from Tasy date fields.

        Args:
            dt_atendimento: Encounter start date/time (ISO 8601)
            dt_alta: Discharge date/time (ISO 8601), optional

        Returns:
            FHIR Period structure
        """
        period: dict[str, Any] = {
            "start": dt_atendimento,
        }

        if dt_alta:
            period["end"] = dt_alta

        return period

    def _build_location_reference(
        self, cd_estabelecimento: str, nm_estabelecimento: str | None
    ) -> dict[str, Any]:
        """Build reference to Location/Organization.

        Note: In production, this would need to resolve CD_ESTABELECIMENTO to a
        FHIR Location or Organization resource ID.

        Args:
            cd_estabelecimento: Tasy establishment code
            nm_estabelecimento: Establishment name for display

        Returns:
            FHIR Reference to Location
        """
        # TODO: Query FHIR server to resolve Location by identifier
        reference: dict[str, Any] = {
            "type": "Location",
            "identifier": self._build_identifier(
                system="http://tasy.com/fhir/identifier/estabelecimento",
                value=cd_estabelecimento,
            ),
        }

        if nm_estabelecimento:
            reference["display"] = nm_estabelecimento

        return reference
