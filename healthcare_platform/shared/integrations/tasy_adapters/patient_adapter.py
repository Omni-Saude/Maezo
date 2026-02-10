"""Tasy Patient to FHIR Patient R4 adapter.

Maps Tasy PACIENTE table to FHIR Patient resource per specification:
- NR_PACIENTE -> Patient.identifier (system=tasy-mrn)
- NM_PACIENTE -> Patient.name[0] (split into given/family)
- DT_NASCIMENTO -> Patient.birthDate
- TP_SEXO -> Patient.gender (M->male, F->female)
- NR_CPF -> Patient.identifier (system=cpf, type=TAX)
- CD_PACIENTE -> Patient.identifier (system=tasy-cd)
- IE_SITUACAO -> Patient.active (A=true, I=false)
- DS_ENDERECO -> Patient.address
- NR_TELEFONE -> Patient.telecom

Example Tasy data:
{
    "NR_PACIENTE": "123456",
    "NM_PACIENTE": "João Silva Santos",
    "DT_NASCIMENTO": "1980-05-15",
    "TP_SEXO": "M",
    "NR_CPF": "12345678901",
    "CD_PACIENTE": "PAC-789",
    "IE_SITUACAO": "A",
    "DS_ENDERECO": "Rua das Flores, 100",
    "NR_TELEFONE": "11987654321"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyPatientAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy PACIENTE to FHIR Patient R4."""

    ADAPTER_TYPE = "patient"
    FHIR_RESOURCE_TYPE = "Patient"

    # Identifier systems
    TASY_MRN_SYSTEM = "http://tasy.com/fhir/identifier/mrn"
    TASY_CD_SYSTEM = "http://tasy.com/fhir/identifier/cd-paciente"
    CPF_SYSTEM = "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf"

    # Gender mapping
    GENDER_MAP = {
        "M": "male",
        "F": "female",
        "O": "other",
        "I": "unknown",
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy PACIENTE to FHIR Patient R4.

        Args:
            tasy_data: Tasy PACIENTE table data

        Returns:
            FHIR Patient R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["NR_PACIENTE", "NM_PACIENTE", "DT_NASCIMENTO", "TP_SEXO"],
            )

            # Log sanitized input
            self._logger.debug(
                "Converting Tasy patient to FHIR",
                extra={
                    "tasy_data": self._sanitize_for_lgpd(tasy_data),
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR Patient resource
            patient: dict[str, Any] = {
                "resourceType": "Patient",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/Patient",
                    ],
                    "tag": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
                            "code": "SUBSETTED",
                            "display": "Resource encoded in summary mode",
                        },
                        {
                            "system": "http://tasy.com/fhir/tenant",
                            "code": self._tenant_id,
                        },
                    ],
                },
                "identifier": self._build_identifiers(tasy_data),
                "active": self._map_active_status(tasy_data.get("IE_SITUACAO")),
                "name": self._build_name(tasy_data["NM_PACIENTE"]),
                "gender": self._map_gender(tasy_data["TP_SEXO"]),
                "birthDate": tasy_data["DT_NASCIMENTO"],
            }

            # Add optional fields
            if "DS_ENDERECO" in tasy_data:
                patient["address"] = [self._build_address(tasy_data["DS_ENDERECO"])]

            if "NR_TELEFONE" in tasy_data:
                patient["telecom"] = [self._build_telecom(tasy_data["NR_TELEFONE"])]

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy patient to FHIR",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return patient

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy patient to FHIR",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _build_identifiers(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build FHIR identifier list from Tasy patient data."""
        identifiers = []

        # MRN (Medical Record Number)
        identifiers.append(
            self._build_identifier(
                system=self.TASY_MRN_SYSTEM,
                value=tasy_data["NR_PACIENTE"],
                type_code="MR",
            )
        )

        # CPF (Brazilian tax ID)
        if "NR_CPF" in tasy_data and tasy_data["NR_CPF"]:
            identifiers.append(
                self._build_identifier(
                    system=self.CPF_SYSTEM,
                    value=tasy_data["NR_CPF"],
                    type_code="TAX",
                )
            )

        # CD_PACIENTE (Tasy patient code)
        if "CD_PACIENTE" in tasy_data and tasy_data["CD_PACIENTE"]:
            identifiers.append(
                self._build_identifier(
                    system=self.TASY_CD_SYSTEM,
                    value=tasy_data["CD_PACIENTE"],
                )
            )

        return identifiers

    def _build_name(self, full_name: str) -> list[dict[str, Any]]:
        """Split full name into FHIR HumanName structure.

        Assumes Brazilian naming convention: first names + family name
        Example: "João Silva Santos" -> given=["João", "Silva"], family="Santos"
        """
        parts = full_name.strip().split()

        if not parts:
            return [{"text": full_name}]

        # Last part is family name, rest are given names
        given = parts[:-1] if len(parts) > 1 else []
        family = parts[-1]

        name: dict[str, Any] = {
            "use": "official",
            "text": full_name,
        }

        if family:
            name["family"] = family

        if given:
            name["given"] = given

        return [name]

    def _map_gender(self, tasy_gender: str) -> str:
        """Map Tasy gender code to FHIR gender.

        Args:
            tasy_gender: Tasy TP_SEXO value (M, F, O, I)

        Returns:
            FHIR gender code (male, female, other, unknown)
        """
        return self.GENDER_MAP.get(tasy_gender, "unknown")

    def _map_active_status(self, situacao: str | None) -> bool:
        """Map Tasy IE_SITUACAO to FHIR active boolean.

        Args:
            situacao: Tasy IE_SITUACAO value (A=active, I=inactive)

        Returns:
            True if active, False otherwise
        """
        return situacao == "A" if situacao else True

    def _build_address(self, endereco: str) -> dict[str, Any]:
        """Build FHIR Address from Tasy address string.

        Note: Tasy stores address as single string. For structured address,
        additional Tasy fields would be needed (street, number, city, etc.).
        """
        return {
            "use": "home",
            "type": "physical",
            "text": endereco,
        }

    def _build_telecom(self, telefone: str) -> dict[str, Any]:
        """Build FHIR ContactPoint from Tasy phone number."""
        return {
            "system": "phone",
            "value": telefone,
            "use": "home",
        }
