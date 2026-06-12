"""Tasy AUTORIZACAO_CONVENIO to FHIR ClaimResponse R4 adapter.

Maps Tasy AUTORIZACAO_CONVENIO table to FHIR ClaimResponse (preAuth) per V06:
- NR_SEQ_AUTORIZACAO -> ClaimResponse.identifier
- NR_ATENDIMENTO -> ClaimResponse.request (ref Encounter)
- CD_PESSOA_FISICA -> ClaimResponse.patient (ref Patient)
- CD_CONVENIO -> ClaimResponse.insurer (ref Organization)
- CD_AUTORIZACAO -> ClaimResponse.preAuthRef
- DT_AUTORIZACAO -> ClaimResponse.created
- IE_ECLIPSE_STATUS -> ClaimResponse.outcome
- DT_VALIDADE_GUIA -> ClaimResponse.preAuthPeriod.end
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyAuthorizationAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy AUTORIZACAO_CONVENIO to FHIR ClaimResponse R4."""

    ADAPTER_TYPE = "authorization"
    FHIR_RESOURCE_TYPE = "ClaimResponse"

    TASY_AUTH_SYSTEM = "http://tasy.com/fhir/identifier/autorizacao"

    # Status mapping: Tasy IE_ECLIPSE_STATUS -> FHIR outcome
    STATUS_MAP = {
        "A": "complete",       # Aprovada
        "N": "error",          # Negada
        "P": "queued",         # Pendente
        "C": "error",          # Cancelada
        "E": "partial",        # Em análise
    }

    # Accident type mapping (IE_TISS_TIPO_ACIDENTE / TP_ACIDENTE)
    ACCIDENT_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
    ACCIDENT_TYPE_MAP = {
        "0": ("NOT-ACCIDENT", "Não acidente"),
        "1": ("MVA", "Acidente de trânsito"),
        "2": ("WPA", "Acidente de trabalho"),
        "9": ("ACCIDENT", "Outros"),
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_required_fields(
                tasy_data, ["NR_SEQ_AUTORIZACAO", "NR_ATENDIMENTO"]
            )

            claim_response: dict[str, Any] = {
                "resourceType": "ClaimResponse",
                "meta": {
                    "profile": ["http://hl7.org/fhir/StructureDefinition/ClaimResponse"],
                    "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
                },
                "identifier": [
                    self._build_identifier(
                        system=self.TASY_AUTH_SYSTEM,
                        value=str(tasy_data["NR_SEQ_AUTORIZACAO"]),
                    )
                ],
                "status": "active",
                "type": self._build_codeable_concept(
                    codings=[self._build_coding(
                        system="http://terminology.hl7.org/CodeSystem/claim-type",
                        code="institutional",
                        display="Institutional",
                    )]
                ),
                "use": "preauthorization",
                "patient": self._build_reference(
                    "Patient", str(tasy_data.get("NR_PACIENTE", tasy_data.get("CD_PESSOA_FISICA", "")))
                ),
                "created": str(tasy_data.get("DT_AUTORIZACAO", "")),
                "insurer": self._build_reference(
                    "Organization", str(tasy_data.get("CD_CONVENIO", ""))
                ),
                "outcome": self.STATUS_MAP.get(
                    str(tasy_data.get("IE_STATUS_AUTORIZACAO", "P")), "queued"
                ),
            }

            # ClaimResponse.request must reference a Claim (not Encounter)
            # Use the authorization ID as Claim reference
            claim_response["request"] = self._build_reference(
                "Claim", str(tasy_data["NR_SEQ_AUTORIZACAO"])
            )

            # Add encounter as extension
            if tasy_data.get("NR_ATENDIMENTO"):
                claim_response.setdefault("extension", []).append({
                    "url": "http://tasy.com/fhir/extension/encounter",
                    "valueReference": self._build_reference(
                        "Encounter", str(tasy_data["NR_ATENDIMENTO"])
                    ),
                })

            # Add preAuthRef (authorization number/guide)
            auth_code = tasy_data.get("CD_AUTORIZACAO")
            if auth_code:
                claim_response["preAuthRef"] = str(auth_code)

            # Add validity period
            dt_validade = tasy_data.get("DT_VALIDADE_GUIA")
            if dt_validade:
                claim_response["preAuthPeriod"] = {"end": str(dt_validade)}

            # Add accident type (IE_TISS_TIPO_ACIDENTE / TP_ACIDENTE) as extension
            tp_acidente = (
                tasy_data.get("IE_TISS_TIPO_ACIDENTE")
                or tasy_data.get("TP_ACIDENTE")
            )
            if tp_acidente is not None:
                acc_code, acc_display = self.ACCIDENT_TYPE_MAP.get(
                    str(tp_acidente), ("OTH", "Other"),
                )
                claim_response.setdefault("extension", []).append({
                    "url": "http://tasy.com/fhir/extension/accident",
                    "valueCodeableConcept": self._build_codeable_concept(
                        codings=[self._build_coding(
                            system=self.ACCIDENT_TYPE_SYSTEM,
                            code=acc_code, display=acc_display,
                        )],
                    ),
                })

            self._track_conversion_success()
            return claim_response

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy authorization to FHIR ClaimResponse",
                extra={"error": str(exc), "tenant_id": self._tenant_id},
            )
            raise
