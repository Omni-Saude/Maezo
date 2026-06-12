"""Tasy PROCEDIMENTO_PACIENTE to FHIR Procedure R4 adapter.

Maps Tasy PROCEDIMENTO_PACIENTE table to FHIR Procedure resource per V04:
- NR_SEQ_PROCEDIMENTO -> Procedure.identifier
- NR_ATENDIMENTO -> Procedure.encounter (ref Encounter)
- NR_PACIENTE -> Procedure.subject (ref Patient)
- CD_PROCEDIMENTO -> Procedure.code (TUSS)
- DS_PROCEDIMENTO -> Procedure.code.display
- IE_STATUS_PROC -> Procedure.status (R=completed, C=not-done, P=preparation)
- DT_PROCEDIMENTO -> Procedure.performedDateTime
- QT_PROCEDIMENTO -> Procedure.extension[quantity]
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyProcedureAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy PROCEDIMENTO_PACIENTE to FHIR Procedure R4."""

    ADAPTER_TYPE = "procedure"
    FHIR_RESOURCE_TYPE = "Procedure"

    TASY_PROC_SYSTEM = "http://tasy.com/fhir/identifier/procedimento"
    TUSS_SYSTEM = "http://www.ans.gov.br/tuss"

    STATUS_MAP = {
        "R": "completed",
        "C": "not-done",
        "P": "preparation",
        "A": "in-progress",
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_required_fields(
                tasy_data, ["NR_SEQ_PROCEDIMENTO", "NR_ATENDIMENTO", "NR_PACIENTE"]
            )

            procedure: dict[str, Any] = {
                "resourceType": "Procedure",
                "meta": {
                    "profile": ["http://hl7.org/fhir/StructureDefinition/Procedure"],
                    "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
                },
                "identifier": [
                    self._build_identifier(
                        system=self.TASY_PROC_SYSTEM,
                        value=str(tasy_data["NR_SEQ_PROCEDIMENTO"]),
                    )
                ],
                "status": self.STATUS_MAP.get(
                    str(tasy_data.get("IE_STATUS_PROC", "A")), "in-progress"
                ),
                "subject": self._build_reference("Patient", str(tasy_data["NR_PACIENTE"])),
                "encounter": self._build_reference("Encounter", str(tasy_data["NR_ATENDIMENTO"])),
            }

            # Add procedure code (TUSS)
            cd_proc = tasy_data.get("CD_PROCEDIMENTO")
            if cd_proc:
                procedure["code"] = self._build_codeable_concept(
                    codings=[self._build_coding(
                        system=self.TUSS_SYSTEM,
                        code=str(cd_proc),
                        display=tasy_data.get("DS_PROCEDIMENTO"),
                    )],
                    text=tasy_data.get("DS_PROCEDIMENTO"),
                )

            # Add performed date
            dt_proc = tasy_data.get("DT_PROCEDIMENTO")
            if dt_proc:
                procedure["performedDateTime"] = str(dt_proc)

            # Add quantity (QT_PROCEDIMENTO) as extension
            qt = tasy_data.get("QT_PROCEDIMENTO")
            if qt is not None:
                try:
                    qt_num = float(qt)
                    procedure.setdefault("extension", []).append({
                        "url": "http://tasy.com/fhir/extension/quantity",
                        "valueDecimal": qt_num,
                    })
                except (ValueError, TypeError):
                    pass

            # Add executor physician (CD_MEDICO_EXEC) as performer
            cd_medico = tasy_data.get("CD_MEDICO_EXEC") or tasy_data.get("CD_MEDICO_EXECUTOR")
            if cd_medico:
                procedure["performer"] = [{
                    "actor": {
                        "type": "Practitioner",
                        "identifier": self._build_identifier(
                            system="http://tasy.com/fhir/identifier/medico",
                            value=str(cd_medico),
                        ),
                    },
                }]

            # Add authorization reference (NR_SEQ_AUTORIZACAO) as extension
            nr_auth = tasy_data.get("NR_SEQ_AUTORIZACAO")
            if nr_auth:
                procedure.setdefault("extension", []).append({
                    "url": "http://tasy.com/fhir/extension/authorization",
                    "valueReference": {
                        "type": "ClaimResponse",
                        "identifier": self._build_identifier(
                            system="http://tasy.com/fhir/identifier/autorizacao",
                            value=str(nr_auth),
                        ),
                    },
                })

            self._track_conversion_success()
            return procedure

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy procedure to FHIR",
                extra={"error": str(exc), "tenant_id": self._tenant_id},
            )
            raise
