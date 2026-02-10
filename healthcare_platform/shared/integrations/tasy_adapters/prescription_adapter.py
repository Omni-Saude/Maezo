"""Tasy Prescription to FHIR MedicationRequest R4 adapter.

Maps Tasy PRESCRICAO table to FHIR MedicationRequest resource:
- NR_PRESCRICAO -> MedicationRequest.identifier
- DT_PRESCRICAO -> MedicationRequest.authoredOn
- CD_MEDICAMENTO -> MedicationRequest.medicationCodeableConcept
- DS_POSOLOGIA -> MedicationRequest.dosageInstruction.text
- IE_SITUACAO -> MedicationRequest.status
- Reference to Patient
- Reference to Practitioner (prescriber)

Example Tasy data:
{
    "NR_PRESCRICAO": "PRESC-123",
    "DT_PRESCRICAO": "2024-02-10T10:30:00",
    "NR_PACIENTE": "123456",
    "CD_MEDICO": "MED-789",
    "NM_MEDICO": "Dr. Carlos Silva",
    "CD_MEDICAMENTO": "7896658025020",  # EAN/GTIN
    "NM_MEDICAMENTO": "Amoxicilina 500mg",
    "DS_POSOLOGIA": "1 comprimido a cada 8 horas por 7 dias",
    "QT_PRESCRITA": 21,
    "IE_SITUACAO": "A",  # A=ativa, S=suspensa, C=cancelada
    "NR_ATENDIMENTO": "ATD-789"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyPrescriptionAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy PRESCRICAO to FHIR MedicationRequest R4."""

    ADAPTER_TYPE = "prescription"
    FHIR_RESOURCE_TYPE = "MedicationRequest"

    # Identifier system
    TASY_PRESCRICAO_SYSTEM = "http://tasy.com/fhir/identifier/prescricao"

    # Status mapping
    STATUS_MAP = {
        "A": "active",
        "S": "stopped",
        "C": "cancelled",
        "F": "completed",
    }

    # Medication code system (EAN/GTIN for Brazilian medications)
    MEDICATION_SYSTEM = "http://www.gs1.org/gtin"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy PRESCRICAO to FHIR MedicationRequest R4.

        Args:
            tasy_data: Tasy PRESCRICAO table data

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
                    "CD_MEDICAMENTO",
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
                "intent": "order",
                "medicationCodeableConcept": self._build_medication_code(
                    tasy_data["CD_MEDICAMENTO"],
                    tasy_data.get("NM_MEDICAMENTO"),
                ),
                "subject": self._build_reference(
                    "Patient",
                    tasy_data["NR_PACIENTE"],
                ),
                "authoredOn": tasy_data["DT_PRESCRICAO"],
            }

            # Add prescriber reference if available
            if "CD_MEDICO" in tasy_data:
                medication_request["requester"] = self._build_practitioner_reference(
                    tasy_data["CD_MEDICO"],
                    tasy_data.get("NM_MEDICO"),
                )

            # Add dosage instructions if available
            if "DS_POSOLOGIA" in tasy_data:
                medication_request["dosageInstruction"] = [
                    self._build_dosage(
                        tasy_data["DS_POSOLOGIA"],
                        tasy_data.get("QT_PRESCRITA"),
                    )
                ]

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
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR MedicationRequest status.

        Args:
            situacao: Tasy IE_SITUACAO value

        Returns:
            FHIR status code (active, stopped, cancelled, completed, etc.)
        """
        return self.STATUS_MAP.get(situacao, "active") if situacao else "active"

    def _build_medication_code(
        self, cd_medicamento: str, nm_medicamento: str | None
    ) -> dict[str, Any]:
        """Build CodeableConcept for medication.

        Args:
            cd_medicamento: EAN/GTIN medication code
            nm_medicamento: Medication name

        Returns:
            FHIR CodeableConcept for medication
        """
        codings = [
            self._build_coding(
                system=self.MEDICATION_SYSTEM,
                code=cd_medicamento,
                display=nm_medicamento,
            )
        ]

        return self._build_codeable_concept(
            codings=codings,
            text=nm_medicamento,
        )

    def _build_practitioner_reference(
        self, cd_medico: str, nm_medico: str | None
    ) -> dict[str, Any]:
        """Build reference to prescribing Practitioner.

        Note: In production, this would need to resolve CD_MEDICO to a
        FHIR Practitioner resource ID.

        Args:
            cd_medico: Tasy physician code
            nm_medico: Physician name for display

        Returns:
            FHIR Reference to Practitioner
        """
        reference: dict[str, Any] = {
            "type": "Practitioner",
            "identifier": self._build_identifier(
                system="http://tasy.com/fhir/identifier/medico",
                value=cd_medico,
            ),
        }

        if nm_medico:
            reference["display"] = nm_medico

        return reference

    def _build_dosage(
        self, ds_posologia: str, qt_prescrita: int | None
    ) -> dict[str, Any]:
        """Build FHIR DosageInstruction.

        Args:
            ds_posologia: Posology/dosage instructions text
            qt_prescrita: Total quantity prescribed

        Returns:
            FHIR DosageInstruction structure
        """
        dosage: dict[str, Any] = {
            "text": ds_posologia,
        }

        if qt_prescrita:
            dosage["doseAndRate"] = [
                {
                    "type": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/dose-rate-type",
                                code="ordered",
                                display="Ordered",
                            )
                        ]
                    ),
                }
            ]

        return dosage
