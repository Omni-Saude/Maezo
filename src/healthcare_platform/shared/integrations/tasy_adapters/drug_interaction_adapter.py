"""Tasy Drug Interaction to FHIR DetectedIssue R4 adapter.

Maps Tasy INTERACAO_MEDICAMENTOSA table to FHIR DetectedIssue resource for:
- Drug-drug interactions
- Drug-allergy cross-references
- Drug-food interactions
- Duplicate therapy detection

Supports Brazilian interaction databases and ANVISA safety alerts.

Example Tasy data:
{
    "NR_INTERACAO": "INT-001",
    "NR_PACIENTE": "123456",
    "IE_TIPO": "DD",
    "IE_GRAVIDADE": "A",
    "IE_SITUACAO": "F",
    "CD_MEDICAMENTO_1": "1234567890123",
    "NM_MEDICAMENTO_1": "Warfarina 5mg",
    "NR_PRESCRICAO_1": "PRESC-100",
    "CD_MEDICAMENTO_2": "9876543210987",
    "NM_MEDICAMENTO_2": "Amoxicilina 500mg",
    "NR_PRESCRICAO_2": "PRESC-101",
    "DS_INTERACAO": "Amoxicilina pode aumentar o efeito anticoagulante da Warfarina",
    "DS_MITIGACAO": "Monitorar INR a cada 48h durante uso concomitante",
    "DT_DETECCAO": "2024-02-10T10:30:00",
    "CD_ALERGIA": null
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyDrugInteractionAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy drug interactions to FHIR DetectedIssue R4."""

    ADAPTER_TYPE = "drug_interaction"
    FHIR_RESOURCE_TYPE = "DetectedIssue"

    TASY_INTERACTION_SYSTEM = "http://tasy.com/fhir/identifier/interaction"
    ANVISA_SYSTEM = "http://www.anvisa.gov.br/medicamentos"
    ANVISA_INTERACTION_SYSTEM = "http://www.anvisa.gov.br/interacoes"
    SNOMED_SYSTEM = "http://snomed.info/sct"

    # Interaction type mapping: Tasy IE_TIPO -> FHIR code
    INTERACTION_TYPE_MAP = {
        "DD": ("drug-drug", "Drug-drug interaction"),
        "DA": ("drug-allergy", "Drug-allergy interaction"),
        "DF": ("drug-food", "Drug-food interaction"),
        "DT": ("duplicate-therapy", "Duplicate therapy"),
    }

    # Severity mapping: Tasy IE_GRAVIDADE -> FHIR severity
    SEVERITY_MAP = {
        "A": "high",
        "M": "moderate",
        "B": "low",
    }

    # Status mapping: Tasy IE_SITUACAO -> FHIR DetectedIssue status
    STATUS_MAP = {
        "R": "registered",
        "P": "preliminary",
        "F": "final",
        "X": "entered-in-error",
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy drug interaction to FHIR DetectedIssue R4.

        Args:
            tasy_data: Tasy INTERACAO_MEDICAMENTOSA table data

        Returns:
            FHIR DetectedIssue R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            self._validate_required_fields(
                tasy_data,
                ["NR_INTERACAO", "NR_PACIENTE", "IE_TIPO"],
            )

            self._logger.debug(
                "Converting Tasy drug interaction to FHIR DetectedIssue",
                extra={
                    "nr_interacao": tasy_data["NR_INTERACAO"],
                    "tenant_id": self._tenant_id,
                },
            )

            resource: dict[str, Any] = {
                "resourceType": "DetectedIssue",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/DetectedIssue",
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
                        system=self.TASY_INTERACTION_SYSTEM,
                        value=tasy_data["NR_INTERACAO"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "code": self._build_interaction_code(tasy_data["IE_TIPO"]),
                "patient": self._build_reference("Patient", tasy_data["NR_PACIENTE"]),
            }

            # Severity
            if "IE_GRAVIDADE" in tasy_data:
                resource["severity"] = self._map_severity(tasy_data["IE_GRAVIDADE"])

            # Identified datetime
            if "DT_DETECCAO" in tasy_data:
                resource["identifiedDateTime"] = tasy_data["DT_DETECCAO"]

            # Implicated medications
            implicated = self._build_implicated(tasy_data)
            if implicated:
                resource["implicated"] = implicated

            # Detail text
            if "DS_INTERACAO" in tasy_data:
                resource["detail"] = tasy_data["DS_INTERACAO"]

            # Mitigation
            if "DS_MITIGACAO" in tasy_data:
                mitigation_code = tasy_data.get("CD_MITIGACAO", "13")
                resource["mitigation"] = [
                    {
                        "action": self._build_codeable_concept(
                            codings=[
                                self._build_coding(
                                    system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
                                    code=mitigation_code,
                                    display="Stopped Concurrent Therapy",
                                )
                            ],
                            text=tasy_data["DS_MITIGACAO"],
                        ),
                    }
                ]

            # Allergy cross-reference extension
            if "CD_ALERGIA" in tasy_data and tasy_data["CD_ALERGIA"]:
                resource["extension"] = [
                    {
                        "url": "http://tasy.com/fhir/StructureDefinition/allergy-reference",
                        "valueReference": self._build_reference(
                            "AllergyIntolerance", tasy_data["CD_ALERGIA"]
                        ),
                    }
                ]

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy drug interaction to FHIR DetectedIssue",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return resource

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy drug interaction to FHIR DetectedIssue",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                    "sanitized_data": self._sanitize_for_lgpd(tasy_data),
                },
            )
            raise

    async def reverse_adapt(self, fhir_resource: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR DetectedIssue R4 to Tasy interaction format.

        Args:
            fhir_resource: FHIR DetectedIssue R4 resource

        Returns:
            Tasy INTERACAO_MEDICAMENTOSA format dictionary
        """
        try:
            tasy_data: dict[str, Any] = {}

            if "identifier" in fhir_resource:
                for identifier in fhir_resource["identifier"]:
                    if identifier.get("system") == self.TASY_INTERACTION_SYSTEM:
                        tasy_data["NR_INTERACAO"] = identifier["value"]
                        break

            if "status" in fhir_resource:
                for tasy_status, fhir_status in self.STATUS_MAP.items():
                    if fhir_status == fhir_resource["status"]:
                        tasy_data["IE_SITUACAO"] = tasy_status
                        break

            if "patient" in fhir_resource:
                tasy_data["NR_PACIENTE"] = (
                    fhir_resource["patient"]["reference"].split("/")[-1]
                )

            # Extract interaction type from code
            if "code" in fhir_resource:
                for coding in fhir_resource["code"].get("coding", []):
                    for tasy_type, (fhir_code, _) in self.INTERACTION_TYPE_MAP.items():
                        if coding.get("code") == fhir_code:
                            tasy_data["IE_TIPO"] = tasy_type
                            break

            # Extract severity
            if "severity" in fhir_resource:
                for tasy_sev, fhir_sev in self.SEVERITY_MAP.items():
                    if fhir_sev == fhir_resource["severity"]:
                        tasy_data["IE_GRAVIDADE"] = tasy_sev
                        break

            if "identifiedDateTime" in fhir_resource:
                tasy_data["DT_DETECCAO"] = fhir_resource["identifiedDateTime"]

            if "detail" in fhir_resource:
                tasy_data["DS_INTERACAO"] = fhir_resource["detail"]

            # Extract implicated medications
            if "implicated" in fhir_resource:
                for i, ref in enumerate(fhir_resource["implicated"][:2], 1):
                    tasy_data[f"NR_PRESCRICAO_{i}"] = ref["reference"].split("/")[-1]
                    if "display" in ref:
                        tasy_data[f"NM_MEDICAMENTO_{i}"] = ref["display"]

            # Extract mitigation
            if "mitigation" in fhir_resource and fhir_resource["mitigation"]:
                action = fhir_resource["mitigation"][0].get("action", {})
                tasy_data["DS_MITIGACAO"] = action.get("text")

            # Extract allergy reference
            for ext in fhir_resource.get("extension", []):
                if ext.get("url", "").endswith("/allergy-reference"):
                    val_ref = ext.get("valueReference", {})
                    tasy_data["CD_ALERGIA"] = val_ref.get("reference", "").split("/")[
                        -1
                    ]

            self._track_conversion_success()
            self._logger.debug(
                "Successfully reverse-adapted FHIR DetectedIssue to Tasy format",
                extra={"tenant_id": self._tenant_id},
            )

            return tasy_data

        except Exception as exc:
            self._logger.error(
                "Failed to reverse-adapt FHIR DetectedIssue",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR DetectedIssue status."""
        return self.STATUS_MAP.get(situacao, "preliminary") if situacao else "preliminary"

    def _map_severity(self, gravidade: str) -> str:
        """Map Tasy IE_GRAVIDADE to FHIR severity."""
        return self.SEVERITY_MAP.get(gravidade, "moderate")

    def _build_interaction_code(self, tipo: str) -> dict[str, Any]:
        """Build CodeableConcept for interaction type."""
        if tipo in self.INTERACTION_TYPE_MAP:
            code, display = self.INTERACTION_TYPE_MAP[tipo]
            return self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        code=code,
                        display=display,
                    ),
                    self._build_coding(
                        system=self.ANVISA_INTERACTION_SYSTEM,
                        code=code,
                        display=display,
                    ),
                ],
            )
        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    code="drug-drug",
                    display="Drug-drug interaction",
                ),
                self._build_coding(
                    system=self.ANVISA_INTERACTION_SYSTEM,
                    code="drug-drug",
                    display="Drug-drug interaction",
                ),
            ],
        )

    def _build_implicated(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build list of implicated MedicationRequest references."""
        implicated: list[dict[str, Any]] = []

        if "NR_PRESCRICAO_1" in tasy_data:
            ref = self._build_reference(
                "MedicationRequest",
                tasy_data["NR_PRESCRICAO_1"],
                tasy_data.get("NM_MEDICAMENTO_1"),
            )
            implicated.append(ref)

        if "NR_PRESCRICAO_2" in tasy_data:
            ref = self._build_reference(
                "MedicationRequest",
                tasy_data["NR_PRESCRICAO_2"],
                tasy_data.get("NM_MEDICAMENTO_2"),
            )
            implicated.append(ref)

        return implicated
