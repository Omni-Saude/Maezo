"""Tasy Vital Signs to FHIR Observation R4 adapter.

Maps Tasy SINAL_VITAL table to FHIR Observation resource with LOINC codes:
- HR (Heart Rate) -> LOINC 8867-4
- BP_SYS (Blood Pressure Systolic) -> LOINC 8480-6
- BP_DIA (Blood Pressure Diastolic) -> LOINC 8462-4
- TEMP (Temperature) -> LOINC 8310-5
- SPO2 (Oxygen Saturation) -> LOINC 2708-6
- RR (Respiratory Rate) -> LOINC 9279-1

Example Tasy data:
{
    "NR_SINAL_VITAL": "SV-456",
    "DT_REGISTRO": "2024-02-10T14:30:00",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "TP_SINAL": "HR",  # HR, BP, TEMP, SPO2, RR
    "VL_MEDIDA": 72,
    "UN_MEDIDA": "bpm",
    "VL_SISTOLICA": 120,  # Only for BP
    "VL_DIASTOLICA": 80,  # Only for BP
    "CD_PROFISSIONAL": "ENF-123",
    "NM_PROFISSIONAL": "Enf. Maria Santos"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyVitalSignsAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy SINAL_VITAL to FHIR Observation R4."""

    ADAPTER_TYPE = "vital_signs"
    FHIR_RESOURCE_TYPE = "Observation"

    # Identifier system
    TASY_SINAL_SYSTEM = "http://tasy.com/fhir/identifier/sinal-vital"

    # LOINC system
    LOINC_SYSTEM = "http://loinc.org"

    # Vital sign type to LOINC code mapping
    VITAL_SIGN_MAP = {
        "HR": ("8867-4", "Heart rate", "beats/min"),
        "BP_SYS": ("8480-6", "Systolic blood pressure", "mm[Hg]"),
        "BP_DIA": ("8462-4", "Diastolic blood pressure", "mm[Hg]"),
        "TEMP": ("8310-5", "Body temperature", "Cel"),
        "SPO2": ("2708-6", "Oxygen saturation", "%"),
        "RR": ("9279-1", "Respiratory rate", "breaths/min"),
        "BP": ("85354-9", "Blood pressure panel", "mm[Hg]"),  # Panel for BP
    }

    # UCUM system for units
    UCUM_SYSTEM = "http://unitsofmeasure.org"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy SINAL_VITAL to FHIR Observation R4.

        Args:
            tasy_data: Tasy SINAL_VITAL table data

        Returns:
            FHIR Observation R4 resource (or list for blood pressure panel)

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["NR_SINAL_VITAL", "DT_REGISTRO", "NR_PACIENTE", "TP_SINAL"],
            )

            self._logger.debug(
                "Converting Tasy vital sign to FHIR Observation",
                extra={
                    "nr_sinal_vital": tasy_data["NR_SINAL_VITAL"],
                    "tp_sinal": tasy_data["TP_SINAL"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Blood pressure requires special handling (panel observation)
            if tasy_data["TP_SINAL"] == "BP":
                observation = await self._build_blood_pressure_panel(tasy_data)
            else:
                observation = await self._build_simple_observation(tasy_data)

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy vital sign to FHIR Observation",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return observation

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy vital sign to FHIR Observation",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    async def _build_simple_observation(
        self, tasy_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build simple FHIR Observation for non-BP vital signs.

        Args:
            tasy_data: Tasy SINAL_VITAL data

        Returns:
            FHIR Observation R4 resource
        """
        tp_sinal = tasy_data["TP_SINAL"]
        loinc_code, display, unit = self.VITAL_SIGN_MAP.get(
            tp_sinal, ("unknown", "Unknown vital sign", "")
        )

        observation: dict[str, Any] = {
            "resourceType": "Observation",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/vitalsigns",
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
                    system=self.TASY_SINAL_SYSTEM,
                    value=tasy_data["NR_SINAL_VITAL"],
                )
            ],
            "status": "final",
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/observation-category",
                            code="vital-signs",
                            display="Vital Signs",
                        )
                    ]
                )
            ],
            "code": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.LOINC_SYSTEM,
                        code=loinc_code,
                        display=display,
                    )
                ],
                text=display,
            ),
            "subject": self._build_reference(
                "Patient",
                tasy_data["NR_PACIENTE"],
            ),
            "effectiveDateTime": tasy_data["DT_REGISTRO"],
        }

        # Add value if present
        if "VL_MEDIDA" in tasy_data:
            observation["valueQuantity"] = self._build_quantity(
                tasy_data["VL_MEDIDA"],
                unit or tasy_data.get("UN_MEDIDA", ""),
            )

        # Add encounter reference if available
        if "NR_ATENDIMENTO" in tasy_data:
            observation["encounter"] = self._build_reference(
                "Encounter",
                tasy_data["NR_ATENDIMENTO"],
            )

        # Add performer if available
        if "CD_PROFISSIONAL" in tasy_data:
            observation["performer"] = [
                self._build_practitioner_reference(
                    tasy_data["CD_PROFISSIONAL"],
                    tasy_data.get("NM_PROFISSIONAL"),
                )
            ]

        return observation

    async def _build_blood_pressure_panel(
        self, tasy_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build FHIR Observation panel for blood pressure.

        Blood pressure requires a panel observation with systolic and
        diastolic components.

        Args:
            tasy_data: Tasy SINAL_VITAL data with VL_SISTOLICA and VL_DIASTOLICA

        Returns:
            FHIR Observation R4 panel resource
        """
        observation: dict[str, Any] = {
            "resourceType": "Observation",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/vitalsigns",
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
                    system=self.TASY_SINAL_SYSTEM,
                    value=tasy_data["NR_SINAL_VITAL"],
                )
            ],
            "status": "final",
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/observation-category",
                            code="vital-signs",
                            display="Vital Signs",
                        )
                    ]
                )
            ],
            "code": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.LOINC_SYSTEM,
                        code="85354-9",
                        display="Blood pressure panel",
                    )
                ],
                text="Blood pressure",
            ),
            "subject": self._build_reference(
                "Patient",
                tasy_data["NR_PACIENTE"],
            ),
            "effectiveDateTime": tasy_data["DT_REGISTRO"],
        }

        # Build component observations for systolic and diastolic
        components = []

        if "VL_SISTOLICA" in tasy_data:
            components.append(
                {
                    "code": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=self.LOINC_SYSTEM,
                                code="8480-6",
                                display="Systolic blood pressure",
                            )
                        ]
                    ),
                    "valueQuantity": self._build_quantity(
                        tasy_data["VL_SISTOLICA"], "mm[Hg]"
                    ),
                }
            )

        if "VL_DIASTOLICA" in tasy_data:
            components.append(
                {
                    "code": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=self.LOINC_SYSTEM,
                                code="8462-4",
                                display="Diastolic blood pressure",
                            )
                        ]
                    ),
                    "valueQuantity": self._build_quantity(
                        tasy_data["VL_DIASTOLICA"], "mm[Hg]"
                    ),
                }
            )

        if components:
            observation["component"] = components

        # Add encounter reference if available
        if "NR_ATENDIMENTO" in tasy_data:
            observation["encounter"] = self._build_reference(
                "Encounter",
                tasy_data["NR_ATENDIMENTO"],
            )

        # Add performer if available
        if "CD_PROFISSIONAL" in tasy_data:
            observation["performer"] = [
                self._build_practitioner_reference(
                    tasy_data["CD_PROFISSIONAL"],
                    tasy_data.get("NM_PROFISSIONAL"),
                )
            ]

        return observation

    def _build_quantity(self, value: float, unit: str) -> dict[str, Any]:
        """Build FHIR Quantity datatype.

        Args:
            value: Numeric value
            unit: Unit of measure (UCUM code)

        Returns:
            FHIR Quantity structure
        """
        return {
            "value": value,
            "unit": unit,
            "system": self.UCUM_SYSTEM,
            "code": unit,
        }

    def _build_practitioner_reference(
        self, cd_profissional: str, nm_profissional: str | None
    ) -> dict[str, Any]:
        """Build reference to Practitioner who recorded the vital sign.

        Args:
            cd_profissional: Tasy professional code
            nm_profissional: Professional name for display

        Returns:
            FHIR Reference to Practitioner
        """
        reference: dict[str, Any] = {
            "type": "Practitioner",
            "identifier": self._build_identifier(
                system="http://tasy.com/fhir/identifier/profissional",
                value=cd_profissional,
            ),
        }

        if nm_profissional:
            reference["display"] = nm_profissional

        return reference
