"""Tasy DIAGNOSTICO_DOENCA to FHIR Condition R4 adapter.

Maps Tasy DIAGNOSTICO_DOENCA table to FHIR Condition resource per V03:
- NR_SEQ_DIAGNOSTICO (NR_SEQUENCIA) -> Condition.id
- NR_ATENDIMENTO -> Condition.encounter
- CD_PESSOA_FISICA / NR_SEQ_PACIENTE -> Condition.subject
- CD_DOENCA / CD_CID -> Condition.code.coding[0].code (CID-10)
- DS_DIAG / DS_CID -> Condition.code.coding[0].display
- IE_TIPO_DIAGNOSTICO -> Condition.category
- IE_CLASSIFICACAO_DOENCA -> severity
- IE_SITUACAO / DT_LIBERACAO -> Condition.clinicalStatus
- DT_DIAGNOSTICO -> Condition.recordedDate

Source: JOIN ATENDIMENTO_PACIENTE + DIAGNOSTICO_DOENCA
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyConditionAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy DIAGNOSTICO_DOENCA to FHIR Condition R4."""

    ADAPTER_TYPE = "condition"
    FHIR_RESOURCE_TYPE = "Condition"

    TASY_DIAGNOSTICO_SYSTEM = "http://tasy.com/fhir/identifier/diagnostico"
    CID10_SYSTEM = "http://hl7.org/fhir/sid/icd-10"

    # Diagnosis type mapping (IE_TIPO_DIAGNOSTICO)
    CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-category"
    CATEGORY_MAP = {
        "P": ("encounter-diagnosis", "Principal"),
        "S": ("encounter-diagnosis", "Secondary"),
        "C": ("problem-list-item", "Comorbidity"),
        "1": ("encounter-diagnosis", "Principal"),
        "2": ("encounter-diagnosis", "Secondary"),
    }

    # Clinical status mapping (IE_SITUACAO / active flag)
    STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"
    STATUS_MAP = {
        "A": ("active", "Active"),
        "R": ("resolved", "Resolved"),
        "I": ("inactive", "Inactive"),
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_required_fields(
                tasy_data, ["NR_ATENDIMENTO", "CD_DOENCA"]
            )

            # PK pode ser NR_SEQ_DIAGNOSTICO ou NR_SEQUENCIA
            diag_id = str(
                tasy_data.get("NR_SEQ_DIAGNOSTICO")
                or tasy_data.get("NR_SEQUENCIA")
                or f"{tasy_data['NR_ATENDIMENTO']}-{tasy_data['CD_DOENCA']}"
            )

            condition: dict[str, Any] = {
                "resourceType": "Condition",
                "meta": {
                    "profile": ["http://hl7.org/fhir/StructureDefinition/Condition"],
                    "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
                },
                "identifier": [
                    self._build_identifier(
                        system=self.TASY_DIAGNOSTICO_SYSTEM,
                        value=diag_id,
                    )
                ],
                "subject": self._build_reference(
                    "Patient",
                    str(tasy_data.get("NR_PACIENTE")
                        or tasy_data.get("CD_PESSOA_FISICA")
                        or tasy_data.get("NR_SEQ_PACIENTE")
                        or ""),
                ),
                "encounter": self._build_reference(
                    "Encounter", str(tasy_data["NR_ATENDIMENTO"])
                ),
            }

            # CID-10 code + description
            cd_cid = str(tasy_data.get("CD_DOENCA") or tasy_data.get("CD_CID", ""))
            ds_cid = (
                tasy_data.get("DS_DIAG")
                or tasy_data.get("DS_CID")
                or tasy_data.get("DS_DOENCA")
            )
            condition["code"] = self._build_codeable_concept(
                codings=[self._build_coding(
                    system=self.CID10_SYSTEM,
                    code=cd_cid,
                    display=ds_cid,
                )],
                text=ds_cid,
            )

            # Category (principal/secondary/comorbidity)
            tipo = tasy_data.get("IE_TIPO_DIAGNOSTICO")
            if tipo:
                cat_code, cat_display = self.CATEGORY_MAP.get(
                    str(tipo), ("encounter-diagnosis", "Diagnosis"),
                )
                condition["category"] = [self._build_codeable_concept(
                    codings=[self._build_coding(
                        system=self.CATEGORY_SYSTEM,
                        code=cat_code, display=cat_display,
                    )],
                )]

            # Clinical status
            status = tasy_data.get("IE_SITUACAO", "A")
            st_code, st_display = self.STATUS_MAP.get(
                str(status), ("active", "Active"),
            )
            condition["clinicalStatus"] = self._build_codeable_concept(
                codings=[self._build_coding(
                    system=self.STATUS_SYSTEM,
                    code=st_code, display=st_display,
                )],
            )

            # Recorded date
            dt_diag = tasy_data.get("DT_DIAGNOSTICO") or tasy_data.get("DT_LIBERACAO")
            if dt_diag:
                condition["recordedDate"] = str(dt_diag)

            self._track_conversion_success()
            return condition

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy condition to FHIR",
                extra={"error": str(exc), "tenant_id": self._tenant_id},
            )
            raise
