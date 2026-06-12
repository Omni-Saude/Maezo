"""Tasy MEDICO to FHIR Practitioner R4 adapter.

Maps Tasy MEDICO table to FHIR Practitioner resource per V07:
- CD_PESSOA_FISICA -> Practitioner.id / identifier
- NM_MEDICO (or NM_GUERRA) -> Practitioner.name
- NR_CRM -> Practitioner.identifier[crm]
- UF_CRM -> Practitioner.identifier[crm].assigner
- CD_ESPECIALIDADE -> Practitioner.qualification (CBOS)
- DS_ESPECIALIDADE -> Practitioner.qualification display
- NR_TELEFONE_CELULAR -> Practitioner.telecom

Source: JOIN of MEDICO + MEDICO_ESPECIALIDADE + PESSOA_FISICA
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyPractitionerAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy MEDICO to FHIR Practitioner R4."""

    ADAPTER_TYPE = "practitioner"
    FHIR_RESOURCE_TYPE = "Practitioner"

    TASY_MEDICO_SYSTEM = "http://tasy.com/fhir/identifier/medico"
    CRM_SYSTEM = "http://www.cfm.org.br/fhir/NamingSystem/crm"
    CBOS_SYSTEM = "http://www.saude.gov.br/fhir/r4/CodeSystem/BRCBO"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_required_fields(
                tasy_data, ["CD_PESSOA_FISICA"]
            )

            pf_id = str(tasy_data["CD_PESSOA_FISICA"])
            nm_medico = (
                tasy_data.get("NM_MEDICO")
                or tasy_data.get("NM_GUERRA")
                or tasy_data.get("NM_PESSOA_FISICA")
                or ""
            )

            practitioner: dict[str, Any] = {
                "resourceType": "Practitioner",
                "meta": {
                    "profile": ["http://hl7.org/fhir/StructureDefinition/Practitioner"],
                    "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
                },
                "identifier": self._build_identifiers(tasy_data, pf_id),
                "active": True,
                "name": [self._build_name(nm_medico)],
            }

            # Qualification (especialidade CBOS)
            cd_esp = tasy_data.get("CD_ESPECIALIDADE")
            if cd_esp:
                practitioner["qualification"] = [{
                    "code": self._build_codeable_concept(
                        codings=[self._build_coding(
                            system=self.CBOS_SYSTEM,
                            code=str(cd_esp),
                            display=tasy_data.get("DS_ESPECIALIDADE"),
                        )],
                        text=tasy_data.get("DS_ESPECIALIDADE"),
                    ),
                }]

            # Telecom (celular)
            telefone = (
                tasy_data.get("NR_TELEFONE_CELULAR")
                or tasy_data.get("NR_CELULAR")
            )
            if telefone:
                practitioner["telecom"] = [{
                    "system": "phone",
                    "value": str(telefone),
                    "use": "mobile",
                }]

            self._track_conversion_success()
            return practitioner

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy practitioner to FHIR",
                extra={"error": str(exc), "tenant_id": self._tenant_id},
            )
            raise

    def _build_identifiers(
        self, tasy_data: dict[str, Any], pf_id: str
    ) -> list[dict[str, Any]]:
        """Build identifier list: Tasy ID + CRM."""
        identifiers = [
            self._build_identifier(
                system=self.TASY_MEDICO_SYSTEM,
                value=pf_id,
            )
        ]

        # CRM with UF as assigner
        nr_crm = tasy_data.get("NR_CRM")
        if nr_crm:
            crm_id: dict[str, Any] = self._build_identifier(
                system=self.CRM_SYSTEM,
                value=str(nr_crm),
                type_code="MD",
            )
            uf_crm = tasy_data.get("UF_CRM")
            if uf_crm:
                crm_id["assigner"] = {"display": f"CRM-{uf_crm}"}
            identifiers.append(crm_id)

        return identifiers

    def _build_name(self, full_name: str) -> dict[str, Any]:
        """Build FHIR HumanName from full name string."""
        if not full_name:
            return {"text": "Unknown"}
        parts = full_name.strip().split()
        name: dict[str, Any] = {"use": "official", "text": full_name}
        if len(parts) >= 2:
            name["family"] = parts[-1]
            name["given"] = parts[:-1]
        elif parts:
            name["family"] = parts[0]
        return name
