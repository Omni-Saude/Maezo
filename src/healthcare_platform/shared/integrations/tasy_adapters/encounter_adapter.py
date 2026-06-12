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

    # Priority mapping (IE_CARATER_INTER_SUS)
    PRIORITY_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActPriority"
    PRIORITY_MAP = {
        "U": ("UR", "urgent"),
        "E": ("EL", "elective"),
        "A": ("EM", "emergency"),
        "1": ("EL", "elective"),
        "2": ("UR", "urgent"),
        "3": ("EM", "emergency"),
    }

    # Consultation type mapping (IE_TIPO_CONSULTA)
    CONSULTATION_TYPE_SYSTEM = "http://tasy.com/fhir/CodeSystem/consultation-type"
    CONSULTATION_TYPE_MAP = {
        "P": ("first-visit", "Primeira consulta"),
        "R": ("return", "Retorno"),
        "N": ("prenatal", "Pré-natal"),
        "1": ("first-visit", "Primeira consulta"),
        "2": ("return", "Retorno"),
    }

    # Admission source mapping (IE_REGIME_INTERNACAO)
    ADMIT_SOURCE_SYSTEM = "http://terminology.hl7.org/CodeSystem/admit-source"
    ADMIT_SOURCE_MAP = {
        "PS": ("emd", "From accident/emergency department"),
        "EL": ("hosp-trans", "Transferred from other hospital"),
        "TR": ("hosp-trans", "Transferred from other hospital"),
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

            # Add priority (IE_CARATER_INTER_SUS) — urgência/eletivo
            priority = tasy_data.get("IE_CARATER_INTER_SUS") or tasy_data.get("IE_CARATER_ATEND")
            if priority:
                pri_code, pri_display = self.PRIORITY_MAP.get(
                    str(priority), ("R", "routine")
                )
                encounter["priority"] = self._build_codeable_concept(
                    codings=[self._build_coding(
                        system=self.PRIORITY_SYSTEM, code=pri_code, display=pri_display,
                    )],
                )

            # Add service type (IE_TIPO_CONSULTA) — primeira consulta/retorno
            consult_type = tasy_data.get("IE_TIPO_CONSULTA")
            if consult_type:
                ct_code, ct_display = self.CONSULTATION_TYPE_MAP.get(
                    str(consult_type), ("unspecified", "Não especificado"),
                )
                encounter["serviceType"] = self._build_codeable_concept(
                    codings=[self._build_coding(
                        system=self.CONSULTATION_TYPE_SYSTEM,
                        code=ct_code, display=ct_display,
                    )],
                )

            # Add admission source (IE_REGIME_INTERNACAO from ATEND_CATEGORIA_CONVENIO join)
            regime = tasy_data.get("IE_REGIME_INTERNACAO")
            if regime:
                ad_code, ad_display = self.ADMIT_SOURCE_MAP.get(
                    str(regime), ("other", "Other"),
                )
                encounter.setdefault("hospitalization", {})
                encounter["hospitalization"]["admitSource"] = self._build_codeable_concept(
                    codings=[self._build_coding(
                        system=self.ADMIT_SOURCE_SYSTEM,
                        code=ad_code, display=ad_display,
                    )],
                )

            # Add service provider/location (CD_SETOR_ATENDIMENTO)
            setor = tasy_data.get("CD_SETOR_ATENDIMENTO")
            if setor:
                encounter["location"] = [{
                    "location": {
                        "type": "Location",
                        "identifier": self._build_identifier(
                            system="http://tasy.com/fhir/identifier/setor",
                            value=str(setor),
                        ),
                    },
                }]

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
