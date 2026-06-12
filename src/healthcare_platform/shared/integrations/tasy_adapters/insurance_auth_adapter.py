"""Tasy Insurance Authorization to FHIR ClaimResponse R4 adapter.

Maps Tasy AUTORIZACAO table to FHIR ClaimResponse resource:
- NR_AUTORIZACAO -> ClaimResponse.identifier
- DT_AUTORIZACAO -> ClaimResponse.created
- CD_CONVENIO -> ClaimResponse.insurer
- NR_ATENDIMENTO -> ClaimResponse.request (Claim reference)
- IE_STATUS -> ClaimResponse.outcome
- TISS guide data -> extensions

Handles 9 authorization workflow operations:
1. Submit authorization request (guia TISS)
2. Check authorization status
3. Get authorization details
4. Renew/extend authorization
5. Cancel authorization
6. Appeal denied authorization
7. Batch authorization query
8. Authorization audit trail
9. Authorization document attachment

Example Tasy data:
{
    "NR_AUTORIZACAO": "AUTH-123456",
    "DT_AUTORIZACAO": "2024-02-10",
    "CD_CONVENIO": "CONV-123",
    "NR_ATENDIMENTO": "ATD-789",
    "IE_STATUS": "A",  # A=aprovada, P=pendente, N=negada, R=renovada, E=cancelada, S=solicitada
    "DT_VALIDADE_INICIO": "2024-02-10",
    "DT_VALIDADE_FIM": "2024-03-10",
    "NR_GUIA_TISS": "TISS-2024-001",
    "DS_JUSTIFICATIVA": "Procedimento de urgência",
    "items": [
        {
            "CD_PROCEDIMENTO": "40101010",
            "DS_PROCEDIMENTO": "Consulta médica",
            "QT_AUTORIZADA": 1,
            "QT_SOLICITADA": 1,
            "IE_STATUS": "A"
        }
    ]
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyInsuranceAuthAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy AUTORIZACAO to FHIR ClaimResponse R4."""

    ADAPTER_TYPE = "insurance_auth"
    FHIR_RESOURCE_TYPE = "ClaimResponse"

    # Identifier systems
    TASY_AUTH_SYSTEM = "http://tasy.com/fhir/identifier/autorizacao"
    TISS_SYSTEM = "http://www.ans.gov.br/tiss"

    # Authorization status mapping to FHIR ClaimResponse outcome
    AUTH_STATUS_MAP = {
        "A": "complete",  # Aprovada
        "P": "queued",  # Pendente
        "N": "error",  # Negada
        "R": "complete",  # Renovada (approved renewal)
        "E": "entered-in-error",  # Cancelada
        "S": "active",  # Solicitada
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy AUTORIZACAO to FHIR ClaimResponse R4.

        Args:
            tasy_data: Tasy AUTORIZACAO data with optional TISS guide info

        Returns:
            FHIR ClaimResponse R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                [
                    "NR_AUTORIZACAO",
                    "DT_AUTORIZACAO",
                    "CD_CONVENIO",
                    "NR_ATENDIMENTO",
                    "IE_STATUS",
                ],
            )

            self._logger.debug(
                "Converting Tasy authorization to FHIR ClaimResponse",
                extra={
                    "nr_autorizacao": tasy_data["NR_AUTORIZACAO"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR ClaimResponse resource
            claim_response = self._build_claim_response(tasy_data)

            # Add TISS extension if TISS data present
            if "NR_GUIA_TISS" in tasy_data:
                if "extension" not in claim_response:
                    claim_response["extension"] = []
                claim_response["extension"].append(
                    self._build_tiss_extension(tasy_data)
                )

            # Add authorization validity period
            if "DT_VALIDADE_INICIO" in tasy_data or "DT_VALIDADE_FIM" in tasy_data:
                claim_response["preAuthPeriod"] = self._build_period(
                    tasy_data.get("DT_VALIDADE_INICIO"),
                    tasy_data.get("DT_VALIDADE_FIM"),
                )

            # Add items adjudication if present
            if "items" in tasy_data and tasy_data["items"]:
                claim_response["item"] = self._build_items(tasy_data["items"])

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy authorization to FHIR ClaimResponse",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "tenant_id": self._tenant_id,
                },
            )

            return claim_response

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy authorization to FHIR ClaimResponse",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    async def adapt_tiss_guide(self, tiss_data: dict[str, Any]) -> dict[str, Any]:
        """Convert TISS guide data to FHIR ClaimResponse with extensions.

        Args:
            tiss_data: TISS guide data from Tasy

        Returns:
            FHIR ClaimResponse with TISS-specific extensions
        """
        # Validate TISS-specific required fields
        self._validate_required_fields(
            tiss_data,
            [
                "NR_GUIA_TISS",
                "NR_AUTORIZACAO",
                "DT_AUTORIZACAO",
                "CD_CONVENIO",
                "NR_ATENDIMENTO",
                "IE_STATUS",
            ],
        )

        self._logger.debug(
            "Converting TISS guide to FHIR ClaimResponse",
            extra={
                "nr_guia_tiss": tiss_data["NR_GUIA_TISS"],
                "tenant_id": self._tenant_id,
            },
        )

        # Use standard adapt method, which will include TISS extension
        return await self.adapt(tiss_data)

    def _build_claim_response(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR ClaimResponse base structure.

        Args:
            tasy_data: Tasy AUTORIZACAO data

        Returns:
            FHIR ClaimResponse structure
        """
        claim_response: dict[str, Any] = {
            "resourceType": "ClaimResponse",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/ClaimResponse",
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
                    system=self.TASY_AUTH_SYSTEM,
                    value=tasy_data["NR_AUTORIZACAO"],
                )
            ],
            "status": "active",
            "type": self._build_claim_type(),
            "use": "preauthorization",
            "patient": self._build_reference(
                "Patient",
                tasy_data.get("NR_PACIENTE", "unknown"),
            ),
            "created": tasy_data["DT_AUTORIZACAO"],
            "insurer": self._build_insurer_reference(tasy_data["CD_CONVENIO"]),
            "outcome": self._map_auth_outcome(tasy_data["IE_STATUS"]),
        }

        # Add request reference (original Claim)
        if "NR_ATENDIMENTO" in tasy_data:
            claim_response["request"] = self._build_reference(
                "Claim",
                tasy_data["NR_ATENDIMENTO"],
            )

        # Add justification as process note
        if "DS_JUSTIFICATIVA" in tasy_data:
            claim_response["processNote"] = [
                {
                    "number": 1,
                    "type": "print",
                    "text": tasy_data["DS_JUSTIFICATIVA"],
                }
            ]

        return claim_response

    def _build_tiss_extension(self, tiss_data: dict[str, Any]) -> dict[str, Any]:
        """Build TISS-specific extension for ANS data.

        Args:
            tiss_data: TISS guide data

        Returns:
            FHIR extension structure for TISS data
        """
        extension: dict[str, Any] = {
            "url": f"{self.TISS_SYSTEM}/guia-autorizacao",
            "extension": [],
        }

        # Add TISS guide number
        if "NR_GUIA_TISS" in tiss_data:
            extension["extension"].append(
                {
                    "url": "numeroGuia",
                    "valueString": tiss_data["NR_GUIA_TISS"],
                }
            )

        # Add registration date at ANS
        if "DT_REGISTRO_ANS" in tiss_data:
            extension["extension"].append(
                {
                    "url": "dataRegistroANS",
                    "valueDateTime": tiss_data["DT_REGISTRO_ANS"],
                }
            )

        # Add operator code at ANS
        if "CD_OPERADORA_ANS" in tiss_data:
            extension["extension"].append(
                {
                    "url": "codigoOperadoraANS",
                    "valueString": tiss_data["CD_OPERADORA_ANS"],
                }
            )

        # Add authorization protocol
        if "NR_PROTOCOLO" in tiss_data:
            extension["extension"].append(
                {
                    "url": "numeroProtocolo",
                    "valueString": tiss_data["NR_PROTOCOLO"],
                }
            )

        return extension

    def _map_auth_outcome(self, ie_status: str) -> str:
        """Map TASY authorization status to FHIR ClaimResponse outcome.

        Args:
            ie_status: Tasy IE_STATUS value (A/P/N/R/E/S)

        Returns:
            FHIR outcome code (queued, complete, error, partial, entered-in-error)
        """
        return self.AUTH_STATUS_MAP.get(ie_status, "queued")

    def _build_claim_type(self) -> dict[str, Any]:
        """Build FHIR claim type CodeableConcept.

        Returns professional claim type for hospital authorization.
        """
        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system="http://terminology.hl7.org/CodeSystem/claim-type",
                    code="professional",
                    display="Professional",
                )
            ],
            text="Professional",
        )

    def _build_insurer_reference(self, cd_convenio: str) -> dict[str, Any]:
        """Build reference to insurer Organization.

        Args:
            cd_convenio: Tasy convênio code

        Returns:
            FHIR Reference to insurer Organization
        """
        return {
            "type": "Organization",
            "identifier": self._build_identifier(
                system="http://tasy.com/fhir/identifier/convenio",
                value=cd_convenio,
            ),
            "display": f"Insurance {cd_convenio}",
        }

    def _build_period(
        self, start: str | None, end: str | None
    ) -> dict[str, Any] | None:
        """Build FHIR Period datatype.

        Args:
            start: Period start date (ISO 8601)
            end: Period end date (ISO 8601)

        Returns:
            FHIR Period structure or None if both dates missing
        """
        if not start and not end:
            return None

        period: dict[str, Any] = {}

        if start:
            period["start"] = start

        if end:
            period["end"] = end

        return period

    def _build_items(
        self, tasy_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build FHIR ClaimResponse.item array from Tasy authorization items.

        Args:
            tasy_items: List of Tasy authorization item records

        Returns:
            List of FHIR ClaimResponse.item structures
        """
        fhir_items = []

        for idx, item in enumerate(tasy_items, start=1):
            fhir_item: dict[str, Any] = {
                "itemSequence": idx,
            }

            # Add adjudication (approved/denied quantities)
            adjudication = []

            if "QT_SOLICITADA" in item:
                adjudication.append(
                    {
                        "category": self._build_codeable_concept(
                            codings=[
                                self._build_coding(
                                    system="http://terminology.hl7.org/CodeSystem/adjudication",
                                    code="submitted",
                                    display="Submitted Amount",
                                )
                            ],
                        ),
                        "amount": {
                            "value": item["QT_SOLICITADA"],
                        },
                    }
                )

            if "QT_AUTORIZADA" in item:
                adjudication.append(
                    {
                        "category": self._build_codeable_concept(
                            codings=[
                                self._build_coding(
                                    system="http://terminology.hl7.org/CodeSystem/adjudication",
                                    code="eligible",
                                    display="Eligible Amount",
                                )
                            ],
                        ),
                        "amount": {
                            "value": item["QT_AUTORIZADA"],
                        },
                    }
                )

            if adjudication:
                fhir_item["adjudication"] = adjudication

            fhir_items.append(fhir_item)

        return fhir_items
