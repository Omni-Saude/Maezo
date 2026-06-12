"""Tasy Pharmacy Dispense to FHIR MedicationDispense R4 adapter with Brazilian pharmaceutical standards.

Maps Tasy DISPENSACAO table to FHIR MedicationDispense resource with support for:
- ANVISA (Agência Nacional de Vigilância Sanitária) medication registry codes
- DCB (Denominação Comum Brasileira) - Brazilian common denomination
- RENAME (Relação Nacional de Medicamentos Essenciais)
- CFF (Conselho Federal de Farmácia) pharmacist identification
- Generic substitution rules per Brazilian law (Lei 9.787/1999)

Example Tasy data:
{
    "NR_DISPENSACAO": "DISP-001",
    "NR_PRESCRICAO": "PRESC-123",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "NR_CRF": "CRF/SP 12345",
    "NM_FARMACEUTICO": "Dr. Ana Souza",
    "CD_ANVISA": "1234567890123",
    "CD_DCB": "00220",
    "CD_FORMULARIO": "MED-AMO-500",
    "NM_MEDICAMENTO": "Amoxicilina 500mg",
    "QT_DISPENSADA": 21,
    "DS_UNIDADE": "comprimido",
    "NR_DIAS_FORNECIMENTO": 7,
    "DT_PREPARACAO": "2024-02-10T14:00:00",
    "DT_ENTREGA": "2024-02-10T14:30:00",
    "IE_SITUACAO": "C",
    "IE_SUBSTITUICAO": true,
    "CD_ANVISA_ORIGINAL": "9876543210987",
    "DS_MOTIVO_SUBSTITUICAO": "Genérico disponível conforme Lei 9.787/1999",
    "DS_POSOLOGIA": "1 comprimido a cada 8 horas por 7 dias"
}

Example FHIR MedicationDispense output:
{
    "resourceType": "MedicationDispense",
    "identifier": [{"system": "http://tasy.com/fhir/identifier/dispensacao", "value": "DISP-001"}],
    "status": "completed",
    "medicationCodeableConcept": {
        "coding": [
            {"system": "http://www.anvisa.gov.br/medicamentos", "code": "1234567890123", "display": "Amoxicilina 500mg"},
            {"system": "http://www.anvisa.gov.br/dcb", "code": "00220", "display": "amoxicilina"}
        ]
    },
    "subject": {"reference": "Patient/123456"},
    "context": {"reference": "Encounter/ATD-789"},
    "performer": [{"actor": {"reference": "Practitioner/CRF-SP-12345"}}],
    "authorizingPrescription": [{"reference": "MedicationRequest/PRESC-123"}],
    "quantity": {"value": 21, "unit": "comprimido"},
    "daysSupply": {"value": 7, "unit": "dias", "system": "http://unitsofmeasure.org", "code": "d"},
    "whenPrepared": "2024-02-10T14:00:00",
    "whenHandedOver": "2024-02-10T14:30:00",
    "substitution": {
        "wasSubstituted": true,
        "reason": [{"text": "Genérico disponível conforme Lei 9.787/1999"}]
    }
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyMedicationDispenseAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy DISPENSACAO to FHIR MedicationDispense R4 with Brazilian standards."""

    ADAPTER_TYPE = "medication_dispense"
    FHIR_RESOURCE_TYPE = "MedicationDispense"

    ANVISA_SYSTEM = "http://www.anvisa.gov.br/medicamentos"
    DCB_SYSTEM = "http://www.anvisa.gov.br/dcb"
    TASY_FORMULARY_SYSTEM = "http://tasy.com/fhir/identifier/formulary"
    TASY_DISPENSACAO_SYSTEM = "http://tasy.com/fhir/identifier/dispensacao"
    TASY_PRESCRICAO_SYSTEM = "http://tasy.com/fhir/identifier/prescricao"
    CRF_SYSTEM = "http://www.cff.org.br/pharmacist"
    UCUM_SYSTEM = "http://unitsofmeasure.org"
    SNOMED_SYSTEM = "http://snomed.info/sct"

    # Status mapping: Tasy IE_SITUACAO -> FHIR MedicationDispense status
    STATUS_MAP = {
        "P": "preparation",
        "E": "in-progress",
        "C": "completed",
        "R": "declined",
        "X": "entered-in-error",
    }

    # SNOMED route mapping (same as MedicationRequest)
    ROUTE_MAP = {
        "VO": ("26643006", "Oral route"),
        "IV": ("47625008", "Intravenous route"),
        "IM": ("78421000", "Intramuscular route"),
        "SC": ("34206005", "Subcutaneous route"),
        "SL": ("37161004", "Sublingual route"),
        "TOP": ("6064005", "Topical route"),
    }

    # Substitution type mapping
    SUBSTITUTION_TYPE_MAP = {
        "G": ("G", "generic composition"),
        "TE": ("TE", "therapeutic alternative"),
        "F": ("F", "formulary"),
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy DISPENSACAO to FHIR MedicationDispense R4.

        Args:
            tasy_data: Tasy DISPENSACAO table data

        Returns:
            FHIR MedicationDispense R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            self._validate_required_fields(
                tasy_data,
                ["NR_DISPENSACAO", "NR_PACIENTE", "CD_ANVISA"],
            )

            self._logger.debug(
                "Converting Tasy dispense to FHIR MedicationDispense",
                extra={
                    "nr_dispensacao": tasy_data["NR_DISPENSACAO"],
                    "tenant_id": self._tenant_id,
                },
            )

            resource: dict[str, Any] = {
                "resourceType": "MedicationDispense",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/MedicationDispense",
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
                        system=self.TASY_DISPENSACAO_SYSTEM,
                        value=tasy_data["NR_DISPENSACAO"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "medicationCodeableConcept": self._build_medication_code(tasy_data),
                "subject": self._build_reference("Patient", tasy_data["NR_PACIENTE"]),
            }

            if "NR_ATENDIMENTO" in tasy_data:
                resource["context"] = self._build_reference(
                    "Encounter", tasy_data["NR_ATENDIMENTO"]
                )

            if "NR_CRF" in tasy_data:
                resource["performer"] = [
                    {
                        "actor": self._build_pharmacist_reference(
                            tasy_data["NR_CRF"],
                            tasy_data.get("NM_FARMACEUTICO"),
                        ),
                    }
                ]

            if "NR_PRESCRICAO" in tasy_data:
                resource["authorizingPrescription"] = [
                    self._build_reference(
                        "MedicationRequest", tasy_data["NR_PRESCRICAO"]
                    )
                ]

            if "QT_DISPENSADA" in tasy_data:
                resource["quantity"] = {
                    "value": tasy_data["QT_DISPENSADA"],
                    "unit": tasy_data.get("DS_UNIDADE", "unidade"),
                }

            if "NR_DIAS_FORNECIMENTO" in tasy_data:
                resource["daysSupply"] = {
                    "value": tasy_data["NR_DIAS_FORNECIMENTO"],
                    "unit": "dias",
                    "system": self.UCUM_SYSTEM,
                    "code": "d",
                }

            if "DT_PREPARACAO" in tasy_data:
                resource["whenPrepared"] = tasy_data["DT_PREPARACAO"]

            if "DT_ENTREGA" in tasy_data:
                resource["whenHandedOver"] = tasy_data["DT_ENTREGA"]

            if "DS_POSOLOGIA" in tasy_data:
                resource["dosageInstruction"] = [
                    self._build_dosage_instruction(tasy_data)
                ]

            if tasy_data.get("IE_SUBSTITUICAO") is not None:
                resource["substitution"] = self._build_substitution(tasy_data)

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy dispense to FHIR MedicationDispense",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return resource

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy dispense to FHIR MedicationDispense",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                    "sanitized_data": self._sanitize_for_lgpd(tasy_data),
                },
            )
            raise

    async def reverse_adapt(self, fhir_resource: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR MedicationDispense R4 to Tasy DISPENSACAO format.

        Args:
            fhir_resource: FHIR MedicationDispense R4 resource

        Returns:
            Tasy DISPENSACAO format dictionary
        """
        try:
            tasy_data: dict[str, Any] = {}

            # Extract dispense identifier
            if "identifier" in fhir_resource:
                for identifier in fhir_resource["identifier"]:
                    if identifier.get("system") == self.TASY_DISPENSACAO_SYSTEM:
                        tasy_data["NR_DISPENSACAO"] = identifier["value"]
                        break

            # Extract status
            if "status" in fhir_resource:
                for tasy_status, fhir_status in self.STATUS_MAP.items():
                    if fhir_status == fhir_resource["status"]:
                        tasy_data["IE_SITUACAO"] = tasy_status
                        break

            # Extract patient reference
            if "subject" in fhir_resource:
                tasy_data["NR_PACIENTE"] = (
                    fhir_resource["subject"]["reference"].split("/")[-1]
                )

            # Extract encounter reference
            if "context" in fhir_resource:
                tasy_data["NR_ATENDIMENTO"] = (
                    fhir_resource["context"]["reference"].split("/")[-1]
                )

            # Extract medication codes
            if "medicationCodeableConcept" in fhir_resource:
                for coding in fhir_resource["medicationCodeableConcept"].get(
                    "coding", []
                ):
                    if coding.get("system") == self.ANVISA_SYSTEM:
                        tasy_data["CD_ANVISA"] = coding["code"]
                        tasy_data["NM_MEDICAMENTO"] = coding.get("display")
                    elif coding.get("system") == self.DCB_SYSTEM:
                        tasy_data["CD_DCB"] = coding["code"]
                    elif coding.get("system") == self.TASY_FORMULARY_SYSTEM:
                        tasy_data["CD_FORMULARIO"] = coding["code"]

            # Extract authorizing prescription
            if "authorizingPrescription" in fhir_resource:
                for ref in fhir_resource["authorizingPrescription"]:
                    tasy_data["NR_PRESCRICAO"] = ref["reference"].split("/")[-1]
                    break

            # Extract performer (pharmacist)
            if "performer" in fhir_resource and fhir_resource["performer"]:
                actor = fhir_resource["performer"][0].get("actor", {})
                if "identifier" in actor:
                    identifier = actor["identifier"]
                    if identifier.get("system") == self.CRF_SYSTEM:
                        tasy_data["NR_CRF"] = identifier["value"]
                if "display" in actor:
                    tasy_data["NM_FARMACEUTICO"] = actor["display"]

            # Extract quantity
            if "quantity" in fhir_resource:
                tasy_data["QT_DISPENSADA"] = fhir_resource["quantity"].get("value")
                tasy_data["DS_UNIDADE"] = fhir_resource["quantity"].get("unit")

            # Extract days supply
            if "daysSupply" in fhir_resource:
                tasy_data["NR_DIAS_FORNECIMENTO"] = fhir_resource["daysSupply"].get(
                    "value"
                )

            # Extract timestamps
            if "whenPrepared" in fhir_resource:
                tasy_data["DT_PREPARACAO"] = fhir_resource["whenPrepared"]

            if "whenHandedOver" in fhir_resource:
                tasy_data["DT_ENTREGA"] = fhir_resource["whenHandedOver"]

            # Extract dosage
            if (
                "dosageInstruction" in fhir_resource
                and fhir_resource["dosageInstruction"]
            ):
                dosage = fhir_resource["dosageInstruction"][0]
                if "text" in dosage:
                    tasy_data["DS_POSOLOGIA"] = dosage["text"]

            # Extract substitution
            if "substitution" in fhir_resource:
                sub = fhir_resource["substitution"]
                tasy_data["IE_SUBSTITUICAO"] = sub.get("wasSubstituted", False)
                if "reason" in sub and sub["reason"]:
                    tasy_data["DS_MOTIVO_SUBSTITUICAO"] = sub["reason"][0].get("text")

            self._track_conversion_success()
            self._logger.debug(
                "Successfully reverse-adapted FHIR MedicationDispense to Tasy format",
                extra={"tenant_id": self._tenant_id},
            )

            return tasy_data

        except Exception as exc:
            self._logger.error(
                "Failed to reverse-adapt FHIR MedicationDispense",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR MedicationDispense status."""
        return self.STATUS_MAP.get(situacao, "preparation") if situacao else "preparation"

    def _build_medication_code(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build CodeableConcept for medication with Brazilian codes."""
        codings: list[dict[str, Any]] = []

        if "CD_ANVISA" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.ANVISA_SYSTEM,
                    code=tasy_data["CD_ANVISA"],
                    display=tasy_data.get("NM_MEDICAMENTO"),
                )
            )

        if "CD_DCB" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.DCB_SYSTEM,
                    code=tasy_data["CD_DCB"],
                    display=tasy_data.get("NM_DCB"),
                )
            )

        if "CD_FORMULARIO" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.TASY_FORMULARY_SYSTEM,
                    code=tasy_data["CD_FORMULARIO"],
                )
            )

        return self._build_codeable_concept(
            codings=codings,
            text=tasy_data.get("NM_MEDICAMENTO"),
        )

    def _build_dosage_instruction(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR DosageInstruction."""
        dosage: dict[str, Any] = {"text": tasy_data["DS_POSOLOGIA"]}

        if "VIA_ADMINISTRACAO" in tasy_data:
            via = tasy_data["VIA_ADMINISTRACAO"]
            if via in self.ROUTE_MAP:
                snomed_code, snomed_display = self.ROUTE_MAP[via]
                dosage["route"] = self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code=snomed_code,
                            display=snomed_display,
                        )
                    ]
                )

        return dosage

    def _build_substitution(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR substitution element for generic substitution tracking."""
        substitution: dict[str, Any] = {
            "wasSubstituted": bool(tasy_data.get("IE_SUBSTITUICAO", False)),
        }

        if "CD_TIPO_SUBSTITUICAO" in tasy_data:
            tipo = tasy_data["CD_TIPO_SUBSTITUICAO"]
            if tipo in self.SUBSTITUTION_TYPE_MAP:
                code, display = self.SUBSTITUTION_TYPE_MAP[tipo]
                substitution["type"] = self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/v3-substanceAdminSubstitution",
                            code=code,
                            display=display,
                        )
                    ]
                )

        if "DS_MOTIVO_SUBSTITUICAO" in tasy_data:
            substitution["reason"] = [{"text": tasy_data["DS_MOTIVO_SUBSTITUICAO"]}]

        if "CD_ANVISA_ORIGINAL" in tasy_data:
            substitution["responsibleParty"] = [
                self._build_reference(
                    "Organization", "pharmacy", "Hospital Pharmacy"
                )
            ]

        return substitution

    def _build_pharmacist_reference(
        self, nr_crf: str, nm_farmaceutico: str | None
    ) -> dict[str, Any]:
        """Build reference to dispensing Pharmacist with CRF identifier."""
        crf_id = nr_crf.replace("/", "-").replace(" ", "-")

        reference: dict[str, Any] = {
            "reference": f"Practitioner/{crf_id}",
            "identifier": self._build_identifier(
                system=self.CRF_SYSTEM,
                value=nr_crf,
            ),
        }

        if nm_farmaceutico:
            reference["display"] = nm_farmaceutico

        return reference
