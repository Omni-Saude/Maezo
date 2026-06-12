"""Tasy Observation to FHIR Observation R4 adapter.

Maps Tasy OBSERVACAO (lab results and vital signs) to FHIR Observation resource
with LOINC codes for Brazilian healthcare context:
- Laboratory results (glucose, creatinine, hemoglobin, etc.)
- Vital signs (heart rate, blood pressure, temperature, SpO2, respiratory rate, pain)
- Imaging observations
- Critical value flagging for immediate clinical attention

Example Tasy data (laboratory result):
{
    "NR_OBSERVACAO": "OBS-789",
    "DT_REGISTRO": "2024-02-10T08:15:00",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "TP_CATEGORIA": "laboratory",  # laboratory, vital-signs, imaging
    "TP_RESULTADO": "GLUCOSE",  # GLUCOSE, HR, BP_SYS, etc.
    "VL_RESULTADO": 95.0,
    "DS_UNIDADE": "mg/dL",
    "IE_STATUS": "F",  # F=final, P=preliminary, A=amended
    "IE_INTERPRETACAO": "N",  # N=normal, H=high, L=low, A=abnormal, C=critical
    "VL_REF_MIN": 70.0,
    "VL_REF_MAX": 100.0,
    "CD_PROFISSIONAL": "LAB-456",
    "NM_PROFISSIONAL": "Dr. João Silva"
}

Example Tasy data (vital sign - blood pressure):
{
    "NR_OBSERVACAO": "OBS-456",
    "DT_REGISTRO": "2024-02-10T14:30:00",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "TP_CATEGORIA": "vital-signs",
    "TP_SINAL": "BP",  # Indicates blood pressure panel
    "VL_SISTOLICA": 120,
    "VL_DIASTOLICA": 80,
    "IE_STATUS": "F",
    "CD_PROFISSIONAL": "ENF-123",
    "NM_PROFISSIONAL": "Enf. Maria Santos"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyObservationAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy OBSERVACAO to FHIR Observation R4."""

    ADAPTER_TYPE = "observation"
    FHIR_RESOURCE_TYPE = "Observation"

    # Identifier system
    TASY_OBS_SYSTEM = "http://tasy.com/fhir/identifier/observation"

    # LOINC system
    LOINC_SYSTEM = "http://loinc.org"

    # UCUM system for units
    UCUM_SYSTEM = "http://unitsofmeasure.org"

    # Vital signs to LOINC code mapping (overlaps with vital_signs_adapter)
    VITAL_SIGNS_MAP = {
        "HR": ("8867-4", "Heart rate"),
        "BP_SYS": ("8480-6", "Systolic blood pressure"),
        "BP_DIA": ("8462-4", "Diastolic blood pressure"),
        "TEMP": ("8310-5", "Body temperature"),
        "SPO2": ("2708-6", "Oxygen saturation in Arterial blood by Pulse oximetry"),
        "RR": ("9279-1", "Respiratory rate"),
        "PAIN": ("72514-3", "Pain severity - 0-10 verbal numeric rating"),
        "BP": ("85354-9", "Blood pressure panel"),  # Panel for BP
    }

    # Laboratory results to LOINC code mapping
    LAB_RESULTS_MAP = {
        "GLUCOSE": ("2345-7", "Glucose [Mass/volume] in Serum or Plasma"),
        "CREATININE": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma"),
        "HEMOGLOBIN": ("718-7", "Hemoglobin [Mass/volume] in Blood"),
        "PLATELETS": ("777-3", "Platelets [#/volume] in Blood by Automated count"),
        "WBC": ("6690-2", "Leukocytes [#/volume] in Blood by Automated count"),
        "POTASSIUM": ("2823-3", "Potassium [Moles/volume] in Serum or Plasma"),
        "SODIUM": ("2951-2", "Sodium [Moles/volume] in Serum or Plasma"),
    }

    # Tasy interpretation to FHIR interpretation mapping
    INTERPRETATION_MAP = {
        "N": ("N", "Normal"),
        "H": ("H", "High"),
        "L": ("L", "Low"),
        "A": ("A", "Abnormal"),
        "C": ("HH", "Critical high"),  # Critical values map to HH or LL
    }

    # Tasy status to FHIR status mapping
    STATUS_MAP = {
        "F": "final",
        "P": "preliminary",
        "A": "amended",
        "C": "corrected",
        "E": "entered-in-error",
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy OBSERVACAO to FHIR Observation R4.

        Args:
            tasy_data: Tasy OBSERVACAO table data

        Returns:
            FHIR Observation R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["NR_OBSERVACAO", "DT_REGISTRO", "NR_PACIENTE"],
            )

            self._logger.debug(
                "Converting Tasy observation to FHIR Observation",
                extra={
                    "nr_observacao": tasy_data["NR_OBSERVACAO"],
                    "tp_categoria": tasy_data.get("TP_CATEGORIA", "unknown"),
                    "tenant_id": self._tenant_id,
                },
            )

            # Blood pressure requires special handling (panel observation)
            if tasy_data.get("TP_SINAL") == "BP":
                observation = await self._build_blood_pressure_panel(tasy_data)
            else:
                observation = await self._build_simple_observation(tasy_data)

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy observation to FHIR Observation",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return observation

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy observation to FHIR Observation",
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
        """Build simple FHIR Observation for non-BP observations.

        Args:
            tasy_data: Tasy OBSERVACAO data

        Returns:
            FHIR Observation R4 resource
        """
        # Determine observation type and get LOINC code
        tp_resultado = tasy_data.get("TP_RESULTADO", "")
        loinc_code, display = self._get_loinc_mapping(tp_resultado)

        # Determine category
        category_code = tasy_data.get("TP_CATEGORIA", "laboratory")
        if category_code not in ["vital-signs", "laboratory", "imaging"]:
            category_code = "laboratory"

        # Determine status
        ie_status = tasy_data.get("IE_STATUS", "F")
        status = self.STATUS_MAP.get(ie_status, "final")

        observation: dict[str, Any] = {
            "resourceType": "Observation",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/Observation",
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
                    system=self.TASY_OBS_SYSTEM,
                    value=tasy_data["NR_OBSERVACAO"],
                )
            ],
            "status": status,
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/observation-category",
                            code=category_code,
                            display=category_code.title(),
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
        if "VL_RESULTADO" in tasy_data:
            observation["valueQuantity"] = self._build_quantity(
                tasy_data["VL_RESULTADO"],
                tasy_data.get("DS_UNIDADE", ""),
            )

        # Add interpretation if present
        if "IE_INTERPRETACAO" in tasy_data:
            interpretation = self._build_interpretation(
                tasy_data["IE_INTERPRETACAO"]
            )
            if interpretation:
                observation["interpretation"] = [interpretation]

                # Add critical flag to meta.tag if interpretation is critical
                if tasy_data["IE_INTERPRETACAO"] == "C":
                    observation["meta"]["tag"].append(
                        {
                            "system": "http://tasy.com/fhir/critical-value",
                            "code": "critical",
                            "display": "Critical Value",
                        }
                    )

        # Add reference range if present
        if "VL_REF_MIN" in tasy_data or "VL_REF_MAX" in tasy_data:
            observation["referenceRange"] = [
                self._build_reference_range(
                    tasy_data.get("VL_REF_MIN"),
                    tasy_data.get("VL_REF_MAX"),
                )
            ]

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
            tasy_data: Tasy OBSERVACAO data with VL_SISTOLICA and VL_DIASTOLICA

        Returns:
            FHIR Observation R4 panel resource
        """
        # Determine status
        ie_status = tasy_data.get("IE_STATUS", "F")
        status = self.STATUS_MAP.get(ie_status, "final")

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
                    system=self.TASY_OBS_SYSTEM,
                    value=tasy_data["NR_OBSERVACAO"],
                )
            ],
            "status": status,
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

        # Add interpretation if present
        if "IE_INTERPRETACAO" in tasy_data:
            interpretation = self._build_interpretation(
                tasy_data["IE_INTERPRETACAO"]
            )
            if interpretation:
                observation["interpretation"] = [interpretation]

                # Add critical flag to meta.tag if interpretation is critical
                if tasy_data["IE_INTERPRETACAO"] == "C":
                    observation["meta"]["tag"].append(
                        {
                            "system": "http://tasy.com/fhir/critical-value",
                            "code": "critical",
                            "display": "Critical Value",
                        }
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

    def _get_loinc_mapping(self, tp_resultado: str) -> tuple[str, str]:
        """Get LOINC code and display for a given observation type.

        Args:
            tp_resultado: Tasy observation type code

        Returns:
            Tuple of (LOINC code, display text)
        """
        # Check vital signs first
        if tp_resultado in self.VITAL_SIGNS_MAP:
            return self.VITAL_SIGNS_MAP[tp_resultado]

        # Check lab results
        if tp_resultado in self.LAB_RESULTS_MAP:
            return self.LAB_RESULTS_MAP[tp_resultado]

        # Default fallback
        return ("unknown", "Unknown observation")

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

    def _build_interpretation(
        self, ie_interpretacao: str
    ) -> dict[str, Any] | None:
        """Build FHIR interpretation CodeableConcept.

        Args:
            ie_interpretacao: Tasy interpretation code (N, H, L, A, C)

        Returns:
            FHIR CodeableConcept for interpretation, or None if unknown
        """
        if ie_interpretacao not in self.INTERPRETATION_MAP:
            return None

        code, display = self.INTERPRETATION_MAP[ie_interpretacao]

        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system="http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                    code=code,
                    display=display,
                )
            ]
        )

    def _build_reference_range(
        self, low: float | None, high: float | None
    ) -> dict[str, Any]:
        """Build FHIR reference range structure.

        Args:
            low: Low reference value
            high: High reference value

        Returns:
            FHIR referenceRange structure
        """
        reference_range: dict[str, Any] = {}

        if low is not None:
            reference_range["low"] = {"value": low}

        if high is not None:
            reference_range["high"] = {"value": high}

        return reference_range

    def _build_practitioner_reference(
        self, cd_profissional: str, nm_profissional: str | None
    ) -> dict[str, Any]:
        """Build reference to Practitioner who recorded the observation.

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
