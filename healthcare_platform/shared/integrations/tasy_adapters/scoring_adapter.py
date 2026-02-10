"""Tasy Clinical Scoring to FHIR RiskAssessment R4 adapter.

Maps Tasy clinical scoring API responses to FHIR RiskAssessment resource:
- Score types: EWS, Sepsis, Acuity, Death Risk, Readmission Risk
- Sentry deterioration scores and alerts
- Ventilation management scores
- Sepsis alerts

Example Tasy data:
{
    "score_type": "ews",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "DT_SCORE": "2024-02-10T14:30:00",
    "VL_SCORE": 5,
    "DS_CLASSIFICACAO": "Medium Risk",
    "IE_RISCO": "M",  # B=baixo, M=médio, A=alto
    "observations": [
        {
            "CD_OBS": "HR",
            "DS_OBS": "Heart Rate",
            "VL_OBS": "105",
            "UN_MEDIDA": "bpm"
        }
    ]
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyScoringAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy clinical scores to FHIR RiskAssessment R4."""

    ADAPTER_TYPE = "scoring"
    FHIR_RESOURCE_TYPE = "RiskAssessment"

    # Identifier system
    TASY_SCORE_SYSTEM = "http://tasy.com/fhir/identifier/clinical-score"

    # Score type mapping
    SCORE_TYPES = {
        "ews": "Early Warning Score",
        "sepsis": "Sepsis Score",
        "acuity": "Automated Acuity",
        "risk_of_death": "Risk of Death",
        "risk_of_readmission": "Risk of Readmission",
        "sentry": "Sentry Deterioration Score",
        "sentry_smart_alert": "Sentry Smart Alert",
        "vent_management": "Ventilation Management",
        "sepsis_alert": "Sepsis Alert",
    }

    # Risk classification mapping
    RISK_MAP = {
        "B": "low",
        "M": "moderate",
        "A": "high",
    }

    # Code systems
    LOINC_SYSTEM = "http://loinc.org"
    SNOMED_SYSTEM = "http://snomed.info/sct"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy clinical score to FHIR RiskAssessment R4.

        Routes to specific adapter method based on score_type.

        Args:
            tasy_data: Tasy clinical score data

        Returns:
            FHIR RiskAssessment R4 resource

        Raises:
            ValueError: If required fields are missing or score_type unknown
        """
        try:
            self._validate_required_fields(
                tasy_data,
                ["score_type", "NR_PACIENTE", "DT_SCORE"],
            )

            score_type = tasy_data["score_type"]

            self._logger.debug(
                "Converting Tasy clinical score to FHIR RiskAssessment",
                extra={
                    "score_type": score_type,
                    "tenant_id": self._tenant_id,
                },
            )

            # Route to specific adapter method
            adapter_method = {
                "ews": self.adapt_ews,
                "sepsis": self.adapt_sepsis,
                "acuity": self.adapt_acuity,
                "risk_of_death": self.adapt_risk_of_death,
                "risk_of_readmission": self.adapt_risk_of_readmission,
                "sentry": self.adapt_sentry,
                "sentry_smart_alert": self.adapt_sentry_smart_alert,
                "vent_management": self.adapt_vent_management,
                "sepsis_alert": self.adapt_sepsis_alert,
            }.get(score_type)

            if not adapter_method:
                raise ValueError(f"Unknown score_type: {score_type}")

            return await adapter_method(tasy_data)

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy score to FHIR RiskAssessment",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    async def adapt_ews(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Early Warning Score to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy EWS data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(tasy_data, "ews")

        # Add EWS-specific code
        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="1104051000000101",
                    display="Royal College of Physicians National Early Warning Score 2",
                )
            ],
            text="Early Warning Score",
        )

        # Add prediction with score value
        risk_assessment["prediction"] = self._build_prediction(tasy_data)

        # Add basis (source observations)
        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_sepsis(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Sepsis score to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy sepsis score data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(tasy_data, "sepsis")

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="91302008",
                    display="Sepsis",
                )
            ],
            text="Sepsis Score",
        )

        risk_assessment["prediction"] = self._build_prediction(tasy_data)

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_acuity(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Automated Acuity to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy acuity data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(tasy_data, "acuity")

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="272125009",
                    display="Patient acuity score",
                )
            ],
            text="Automated Acuity",
        )

        risk_assessment["prediction"] = self._build_prediction(tasy_data)

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_risk_of_death(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Risk of Death (APACHE/SAPS) to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy risk of death data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(tasy_data, "risk_of_death")

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="419620001",
                    display="Death risk assessment",
                )
            ],
            text="Risk of Death",
        )

        # Use probability for death risk
        risk_assessment["prediction"] = self._build_prediction(
            tasy_data, use_probability=True
        )

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_risk_of_readmission(
        self, tasy_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert Risk of Readmission to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy risk of readmission data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(
            tasy_data, "risk_of_readmission"
        )

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="225928004",
                    display="Risk of hospital readmission",
                )
            ],
            text="Risk of Readmission",
        )

        risk_assessment["prediction"] = self._build_prediction(
            tasy_data, use_probability=True
        )

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_sentry(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Sentry deterioration score to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy Sentry score data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(tasy_data, "sentry")

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system="http://tasy.com/fhir/CodeSystem/clinical-score",
                    code="SENTRY",
                    display="Sentry Deterioration Score",
                )
            ],
            text="Sentry Deterioration Score",
        )

        risk_assessment["prediction"] = self._build_prediction(tasy_data)

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_sentry_smart_alert(
        self, tasy_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert Sentry Smart Alert to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy Sentry Smart Alert data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(
            tasy_data, "sentry_smart_alert"
        )

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system="http://tasy.com/fhir/CodeSystem/clinical-score",
                    code="SENTRY-ALERT",
                    display="Sentry Smart Alert",
                )
            ],
            text="Sentry Smart Alert",
        )

        # Smart alerts typically have binary risk
        risk_assessment["prediction"] = [
            {
                "outcome": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="229070002",
                            display="Patient condition deteriorating",
                        )
                    ],
                    text="Patient Deterioration",
                ),
                "qualitativeRisk": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/risk-probability",
                            code=self._map_risk(tasy_data.get("IE_RISCO", "A")),
                        )
                    ],
                ),
            }
        ]

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_vent_management(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Ventilation Management score to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy ventilation management data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(
            tasy_data, "vent_management"
        )

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="40617009",
                    display="Artificial respiration",
                )
            ],
            text="Ventilation Management",
        )

        risk_assessment["prediction"] = self._build_prediction(tasy_data)

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    async def adapt_sepsis_alert(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Sepsis Alert to FHIR RiskAssessment.

        Args:
            tasy_data: Tasy sepsis alert data

        Returns:
            FHIR RiskAssessment R4 resource
        """
        risk_assessment = self._build_base_risk_assessment(tasy_data, "sepsis_alert")

        risk_assessment["code"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.SNOMED_SYSTEM,
                    code="91302008",
                    display="Sepsis",
                )
            ],
            text="Sepsis Alert",
        )

        # Sepsis alerts are typically high risk binary events
        risk_assessment["prediction"] = [
            {
                "outcome": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="91302008",
                            display="Sepsis",
                        )
                    ],
                    text="Sepsis Risk",
                ),
                "qualitativeRisk": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/risk-probability",
                            code="high",
                        )
                    ],
                ),
            }
        ]

        if "observations" in tasy_data:
            risk_assessment["basis"] = self._build_basis(tasy_data["observations"])

        self._track_conversion_success()
        return risk_assessment

    def _build_base_risk_assessment(
        self, tasy_data: dict[str, Any], score_type: str
    ) -> dict[str, Any]:
        """Build base FHIR RiskAssessment structure.

        Args:
            tasy_data: Tasy score data
            score_type: Score type key

        Returns:
            Base FHIR RiskAssessment structure
        """
        risk_assessment: dict[str, Any] = {
            "resourceType": "RiskAssessment",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/RiskAssessment",
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
                    system=self.TASY_SCORE_SYSTEM,
                    value=f"{score_type}-{tasy_data['NR_PACIENTE']}-{tasy_data['DT_SCORE']}",
                )
            ],
            "status": "final",
            "subject": self._build_reference(
                "Patient",
                tasy_data["NR_PACIENTE"],
            ),
            "occurrenceDateTime": tasy_data["DT_SCORE"],
        }

        # Add encounter reference if provided
        if "NR_ATENDIMENTO" in tasy_data:
            risk_assessment["encounter"] = self._build_reference(
                "Encounter",
                tasy_data["NR_ATENDIMENTO"],
            )

        return risk_assessment

    def _build_prediction(
        self, tasy_data: dict[str, Any], use_probability: bool = False
    ) -> list[dict[str, Any]]:
        """Build FHIR RiskAssessment.prediction array.

        Args:
            tasy_data: Tasy score data
            use_probability: If True, use probability instead of qualitative risk

        Returns:
            List of prediction structures
        """
        prediction: dict[str, Any] = {
            "outcome": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://tasy.com/fhir/CodeSystem/clinical-score",
                        code=tasy_data["score_type"],
                        display=self.SCORE_TYPES.get(tasy_data["score_type"]),
                    )
                ],
                text=tasy_data.get("DS_CLASSIFICACAO"),
            )
        }

        if use_probability and "VL_SCORE" in tasy_data:
            # Convert score to probability (0-1 range)
            # Adjust logic based on your scoring system
            probability = min(tasy_data["VL_SCORE"] / 100.0, 1.0)
            prediction["probabilityDecimal"] = probability
        elif "IE_RISCO" in tasy_data:
            prediction["qualitativeRisk"] = self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://terminology.hl7.org/CodeSystem/risk-probability",
                        code=self._map_risk(tasy_data["IE_RISCO"]),
                    )
                ]
            )

        return [prediction]

    def _build_basis(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build FHIR RiskAssessment.basis references to source observations.

        Args:
            observations: List of Tasy observations

        Returns:
            List of FHIR References to Observation resources
        """
        basis = []
        for obs in observations:
            if "CD_OBS" in obs:
                basis.append(
                    {
                        "type": "Observation",
                        "identifier": self._build_identifier(
                            system="http://tasy.com/fhir/identifier/observation",
                            value=obs["CD_OBS"],
                        ),
                        "display": obs.get("DS_OBS"),
                    }
                )
        return basis

    def _map_risk(self, ie_risco: str) -> str:
        """Map Tasy IE_RISCO to FHIR risk probability code.

        Args:
            ie_risco: Tasy risk indicator (B=baixo, M=médio, A=alto)

        Returns:
            FHIR risk probability code (low, moderate, high)
        """
        return self.RISK_MAP.get(ie_risco, "moderate")
