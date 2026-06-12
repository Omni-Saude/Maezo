"""Tasy Prescription to FHIR MedicationRequest R4 adapter with Brazilian pharmaceutical standards.

Maps Tasy PRESCRICAO table to FHIR MedicationRequest resource with support for:
- ANVISA (Agência Nacional de Vigilância Sanitária) medication registry codes
- DCB (Denominação Comum Brasileira) - Brazilian common denomination
- RENAME (Relação Nacional de Medicamentos Essenciais)
- ATC (Anatomical Therapeutic Chemical) classification
- SNOMED CT route codes for administration routes
- CRM (Conselho Regional de Medicina) practitioner identification

Example Tasy data:
{
    "NR_PRESCRICAO": "PRESC-123",
    "DT_PRESCRICAO": "2024-02-10T10:30:00",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "NR_CRM": "CRM/SP 123456",
    "NM_MEDICO": "Dr. Carlos Silva",
    "CD_ANVISA": "1234567890123",
    "CD_ATC": "J01CA04",
    "CD_FORMULARIO": "MED-AMO-500",
    "NM_MEDICAMENTO": "Amoxicilina 500mg",
    "DS_POSOLOGIA": "1 comprimido a cada 8 horas por 7 dias",
    "VL_DOSE": 500,
    "DS_DOSE_UNIDADE": "mg",
    "NR_FREQUENCIA": 3,
    "NR_PERIODO": 8,
    "DS_PERIODO_UNIDADE": "h",
    "VIA_ADMINISTRACAO": "VO",
    "QT_PRESCRITA": 21,
    "NR_DIAS_TRATAMENTO": 7,
    "IE_SITUACAO": "A",
    "IE_INTENCAO": "order"
}

Example FHIR MedicationRequest output:
{
    "resourceType": "MedicationRequest",
    "identifier": [{
        "system": "http://tasy.com/fhir/identifier/prescricao",
        "value": "PRESC-123"
    }],
    "status": "active",
    "intent": "order",
    "medicationCodeableConcept": {
        "coding": [{
            "system": "http://www.anvisa.gov.br/medicamentos",
            "code": "1234567890123",
            "display": "Amoxicilina 500mg"
        }, {
            "system": "http://www.whocc.no/atc",
            "code": "J01CA04",
            "display": "Amoxicillin"
        }]
    },
    "subject": {"reference": "Patient/123456"},
    "encounter": {"reference": "Encounter/ATD-789"},
    "authoredOn": "2024-02-10T10:30:00",
    "requester": {
        "reference": "Practitioner/CRM-SP-123456",
        "identifier": {
            "system": "http://www.crm.org.br/practitioner",
            "value": "CRM/SP 123456"
        },
        "display": "Dr. Carlos Silva"
    },
    "dosageInstruction": [{
        "text": "1 comprimido a cada 8 horas por 7 dias",
        "timing": {
            "repeat": {
                "frequency": 3,
                "period": 8,
                "periodUnit": "h"
            }
        },
        "route": {
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "26643006",
                "display": "Oral route"
            }]
        },
        "doseAndRate": [{
            "doseQuantity": {
                "value": 500,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg"
            }
        }]
    }],
    "dispenseRequest": {
        "quantity": {
            "value": 21,
            "unit": "comprimido"
        },
        "expectedSupplyDuration": {
            "value": 7,
            "unit": "dias",
            "system": "http://unitsofmeasure.org",
            "code": "d"
        }
    }
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyMedicationRequestAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy PRESCRICAO to FHIR MedicationRequest R4 with Brazilian standards."""

    ADAPTER_TYPE = "medication_request"
    FHIR_RESOURCE_TYPE = "MedicationRequest"

    # Brazilian pharmaceutical code systems
    ANVISA_SYSTEM = "http://www.anvisa.gov.br/medicamentos"
    ATC_SYSTEM = "http://www.whocc.no/atc"
    TASY_FORMULARY_SYSTEM = "http://tasy.com/fhir/identifier/formulary"
    TASY_PRESCRICAO_SYSTEM = "http://tasy.com/fhir/identifier/prescricao"
    CRM_SYSTEM = "http://www.crm.org.br/practitioner"
    UCUM_SYSTEM = "http://unitsofmeasure.org"
    SNOMED_SYSTEM = "http://snomed.info/sct"

    # Status mapping: Tasy IE_SITUACAO -> FHIR MedicationRequest status
    STATUS_MAP = {
        "A": "active",
        "S": "on-hold",
        "C": "cancelled",
        "F": "completed",
    }

    # Route of administration mapping: Tasy VIA_ADMINISTRACAO -> SNOMED CT codes
    ROUTE_MAP = {
        "VO": ("26643006", "Oral route"),
        "IV": ("47625008", "Intravenous route"),
        "IM": ("78421000", "Intramuscular route"),
        "SC": ("34206005", "Subcutaneous route"),
        "SL": ("37161004", "Sublingual route"),
        "TOP": ("6064005", "Topical route"),
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy PRESCRICAO to FHIR MedicationRequest R4.

        Args:
            tasy_data: Tasy PRESCRICAO table data with Brazilian pharmaceutical codes

        Returns:
            FHIR MedicationRequest R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                [
                    "NR_PRESCRICAO",
                    "DT_PRESCRICAO",
                    "NR_PACIENTE",
                    "CD_ANVISA",
                ],
            )

            self._logger.debug(
                "Converting Tasy prescription to FHIR MedicationRequest",
                extra={
                    "nr_prescricao": tasy_data["NR_PRESCRICAO"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR MedicationRequest resource
            medication_request: dict[str, Any] = {
                "resourceType": "MedicationRequest",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/MedicationRequest",
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
                        system=self.TASY_PRESCRICAO_SYSTEM,
                        value=tasy_data["NR_PRESCRICAO"],
                    )
                ],
                "status": self._map_status(tasy_data.get("IE_SITUACAO")),
                "intent": tasy_data.get("IE_INTENCAO", "order"),
                "medicationCodeableConcept": self._build_medication_code(tasy_data),
                "subject": self._build_reference(
                    "Patient",
                    tasy_data["NR_PACIENTE"],
                ),
                "authoredOn": tasy_data["DT_PRESCRICAO"],
            }

            # Add practitioner reference with CRM if available
            if "NR_CRM" in tasy_data:
                medication_request["requester"] = self._build_practitioner_reference(
                    tasy_data["NR_CRM"],
                    tasy_data.get("NM_MEDICO"),
                )

            # Add dosage instructions if available
            if "DS_POSOLOGIA" in tasy_data:
                medication_request["dosageInstruction"] = [
                    self._build_dosage_instruction(tasy_data)
                ]

            # Add dispense request if quantity available
            if "QT_PRESCRITA" in tasy_data:
                medication_request["dispenseRequest"] = self._build_dispense_request(
                    tasy_data
                )

            # Add encounter reference if available
            if "NR_ATENDIMENTO" in tasy_data:
                medication_request["encounter"] = self._build_reference(
                    "Encounter",
                    tasy_data["NR_ATENDIMENTO"],
                )

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy prescription to FHIR MedicationRequest",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return medication_request

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy prescription to FHIR MedicationRequest",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                    "sanitized_data": self._sanitize_for_lgpd(tasy_data),
                },
            )
            raise

    async def reverse_adapt(self, fhir_resource: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR MedicationRequest R4 to Tasy PRESCRICAO format.

        Args:
            fhir_resource: FHIR MedicationRequest R4 resource

        Returns:
            Tasy PRESCRICAO format dictionary

        Raises:
            ValueError: If required FHIR fields are missing
        """
        try:
            tasy_data: dict[str, Any] = {}

            # Extract prescription identifier
            if "identifier" in fhir_resource:
                for identifier in fhir_resource["identifier"]:
                    if identifier.get("system") == self.TASY_PRESCRICAO_SYSTEM:
                        tasy_data["NR_PRESCRICAO"] = identifier["value"]
                        break

            # Extract dates
            if "authoredOn" in fhir_resource:
                tasy_data["DT_PRESCRICAO"] = fhir_resource["authoredOn"]

            # Extract patient reference
            if "subject" in fhir_resource:
                subject_ref = fhir_resource["subject"]["reference"]
                tasy_data["NR_PACIENTE"] = subject_ref.split("/")[-1]

            # Extract encounter reference
            if "encounter" in fhir_resource:
                encounter_ref = fhir_resource["encounter"]["reference"]
                tasy_data["NR_ATENDIMENTO"] = encounter_ref.split("/")[-1]

            # Extract medication codes
            if "medicationCodeableConcept" in fhir_resource:
                for coding in fhir_resource["medicationCodeableConcept"].get("coding", []):
                    if coding.get("system") == self.ANVISA_SYSTEM:
                        tasy_data["CD_ANVISA"] = coding["code"]
                        tasy_data["NM_MEDICAMENTO"] = coding.get("display")
                    elif coding.get("system") == self.ATC_SYSTEM:
                        tasy_data["CD_ATC"] = coding["code"]
                    elif coding.get("system") == self.TASY_FORMULARY_SYSTEM:
                        tasy_data["CD_FORMULARIO"] = coding["code"]

            # Extract status
            if "status" in fhir_resource:
                for tasy_status, fhir_status in self.STATUS_MAP.items():
                    if fhir_status == fhir_resource["status"]:
                        tasy_data["IE_SITUACAO"] = tasy_status
                        break

            # Extract intent
            if "intent" in fhir_resource:
                tasy_data["IE_INTENCAO"] = fhir_resource["intent"]

            # Extract dosage instructions
            if "dosageInstruction" in fhir_resource and fhir_resource["dosageInstruction"]:
                dosage = fhir_resource["dosageInstruction"][0]
                if "text" in dosage:
                    tasy_data["DS_POSOLOGIA"] = dosage["text"]

                # Extract timing
                if "timing" in dosage and "repeat" in dosage["timing"]:
                    repeat = dosage["timing"]["repeat"]
                    if "frequency" in repeat:
                        tasy_data["NR_FREQUENCIA"] = repeat["frequency"]
                    if "period" in repeat:
                        tasy_data["NR_PERIODO"] = repeat["period"]
                    if "periodUnit" in repeat:
                        tasy_data["DS_PERIODO_UNIDADE"] = repeat["periodUnit"]

                # Extract dose
                if "doseAndRate" in dosage and dosage["doseAndRate"]:
                    dose_and_rate = dosage["doseAndRate"][0]
                    if "doseQuantity" in dose_and_rate:
                        tasy_data["VL_DOSE"] = dose_and_rate["doseQuantity"].get("value")
                        tasy_data["DS_DOSE_UNIDADE"] = dose_and_rate["doseQuantity"].get("unit")

                # Extract route
                if "route" in dosage and "coding" in dosage["route"]:
                    for coding in dosage["route"]["coding"]:
                        if coding.get("system") == self.SNOMED_SYSTEM:
                            for tasy_route, (snomed_code, _) in self.ROUTE_MAP.items():
                                if snomed_code == coding.get("code"):
                                    tasy_data["VIA_ADMINISTRACAO"] = tasy_route
                                    break

            # Extract dispense request
            if "dispenseRequest" in fhir_resource:
                dispense = fhir_resource["dispenseRequest"]
                if "quantity" in dispense:
                    tasy_data["QT_PRESCRITA"] = dispense["quantity"].get("value")
                if "expectedSupplyDuration" in dispense:
                    tasy_data["NR_DIAS_TRATAMENTO"] = dispense["expectedSupplyDuration"].get("value")

            # Extract requester (practitioner)
            if "requester" in fhir_resource:
                if "identifier" in fhir_resource["requester"]:
                    identifier = fhir_resource["requester"]["identifier"]
                    if identifier.get("system") == self.CRM_SYSTEM:
                        tasy_data["NR_CRM"] = identifier["value"]
                if "display" in fhir_resource["requester"]:
                    tasy_data["NM_MEDICO"] = fhir_resource["requester"]["display"]

            self._logger.debug(
                "Successfully reverse-adapted FHIR MedicationRequest to Tasy format",
                extra={"tenant_id": self._tenant_id},
            )

            return tasy_data

        except Exception as exc:
            self._logger.error(
                "Failed to reverse-adapt FHIR MedicationRequest",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR MedicationRequest status.

        Args:
            situacao: Tasy IE_SITUACAO value (A, S, C, F)

        Returns:
            FHIR status code (active, on-hold, cancelled, completed)
        """
        return self.STATUS_MAP.get(situacao, "active") if situacao else "active"

    def _build_medication_code(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build CodeableConcept for medication with Brazilian pharmaceutical codes.

        Args:
            tasy_data: Tasy prescription data containing medication codes

        Returns:
            FHIR CodeableConcept with ANVISA, ATC, and formulary codings
        """
        codings: list[dict[str, Any]] = []

        # ANVISA registry code (primary)
        if "CD_ANVISA" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.ANVISA_SYSTEM,
                    code=tasy_data["CD_ANVISA"],
                    display=tasy_data.get("NM_MEDICAMENTO"),
                )
            )

        # ATC therapeutic classification
        if "CD_ATC" in tasy_data:
            codings.append(
                self._build_coding(
                    system=self.ATC_SYSTEM,
                    code=tasy_data["CD_ATC"],
                )
            )

        # Local hospital formulary code
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
        """Build FHIR DosageInstruction with timing, route, and dose.

        Args:
            tasy_data: Tasy prescription data

        Returns:
            FHIR DosageInstruction structure
        """
        dosage: dict[str, Any] = {
            "text": tasy_data["DS_POSOLOGIA"],
        }

        # Build timing if frequency/period available
        if "NR_FREQUENCIA" in tasy_data or "NR_PERIODO" in tasy_data:
            timing_repeat: dict[str, Any] = {}

            if "NR_FREQUENCIA" in tasy_data:
                timing_repeat["frequency"] = tasy_data["NR_FREQUENCIA"]

            if "NR_PERIODO" in tasy_data:
                timing_repeat["period"] = tasy_data["NR_PERIODO"]

            if "DS_PERIODO_UNIDADE" in tasy_data:
                timing_repeat["periodUnit"] = tasy_data["DS_PERIODO_UNIDADE"]

            if timing_repeat:
                dosage["timing"] = {"repeat": timing_repeat}

        # Build route if available
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

        # Build dose if available
        if "VL_DOSE" in tasy_data:
            dose_quantity: dict[str, Any] = {
                "value": tasy_data["VL_DOSE"],
            }

            if "DS_DOSE_UNIDADE" in tasy_data:
                dose_quantity["unit"] = tasy_data["DS_DOSE_UNIDADE"]
                dose_quantity["system"] = self.UCUM_SYSTEM
                dose_quantity["code"] = tasy_data["DS_DOSE_UNIDADE"]

            dosage["doseAndRate"] = [{"doseQuantity": dose_quantity}]

        return dosage

    def _build_dispense_request(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR dispenseRequest with quantity and supply duration.

        Args:
            tasy_data: Tasy prescription data

        Returns:
            FHIR dispenseRequest structure
        """
        dispense_request: dict[str, Any] = {}

        # Quantity to dispense
        if "QT_PRESCRITA" in tasy_data:
            dispense_request["quantity"] = {
                "value": tasy_data["QT_PRESCRITA"],
                "unit": tasy_data.get("DS_UNIDADE_DISPENSA", "unidade"),
            }

        # Expected supply duration
        if "NR_DIAS_TRATAMENTO" in tasy_data:
            dispense_request["expectedSupplyDuration"] = {
                "value": tasy_data["NR_DIAS_TRATAMENTO"],
                "unit": "dias",
                "system": self.UCUM_SYSTEM,
                "code": "d",
            }

        return dispense_request

    def _build_practitioner_reference(
        self, nr_crm: str, nm_medico: str | None
    ) -> dict[str, Any]:
        """Build reference to prescribing Practitioner with CRM identifier.

        Args:
            nr_crm: CRM registration number (e.g., "CRM/SP 123456")
            nm_medico: Physician name for display

        Returns:
            FHIR Reference to Practitioner with CRM identifier
        """
        # Extract CRM code for resource ID (remove slashes and spaces)
        crm_id = nr_crm.replace("/", "-").replace(" ", "-")

        reference: dict[str, Any] = {
            "reference": f"Practitioner/{crm_id}",
            "identifier": self._build_identifier(
                system=self.CRM_SYSTEM,
                value=nr_crm,
            ),
        }

        if nm_medico:
            reference["display"] = nm_medico

        return reference
