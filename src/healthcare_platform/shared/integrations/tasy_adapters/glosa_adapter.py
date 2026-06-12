"""Tasy Glosa to FHIR ClaimResponse adapter.

Converts TASY GLOSA table records to FHIR R4 ClaimResponse resources,
enabling standardized denial/glosa tracking per RC-GAP-3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import BaseTasyFhirAdapter


class TasyGlosaAdapter(BaseTasyFhirAdapter):
    """Adapter for converting TASY GLOSA to FHIR ClaimResponse.

    Maps TASY glosa (denial) data to FHIR ClaimResponse with adjudication details.

    TASY Table: GLOSA
    FHIR Resource: ClaimResponse (R4)
    """

    ADAPTER_TYPE = "glosa"
    FHIR_RESOURCE_TYPE = "ClaimResponse"

    # TASY GLOSA status codes to FHIR ClaimResponse outcome
    GLOSA_STATUS_MAP = {
        "I": "queued",      # Identificada (Identified)
        "A": "complete",    # Analisada (Analyzed)
        "N": "error",       # Negada (Denied)
        "R": "partial",     # Recurso (Appeal)
        "P": "active",      # Pendente (Pending)
    }

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert TASY GLOSA to FHIR ClaimResponse.

        Args:
            tasy_data: Raw TASY GLOSA record with fields:
                - NR_GLOSA: Glosa ID
                - CD_CONTA: Billing account/claim ID
                - VL_GLOSADO: Denied amount
                - CD_MOTIVO_GLOSA: Denial reason code
                - DS_MOTIVO: Reason description
                - DT_GLOSA: Glosa date
                - ST_GLOSA: Status (I/A/N/R/P)
                - ITENS: List of denied items (optional)

        Returns:
            FHIR R4 ClaimResponse resource

        Raises:
            ValueError: If required TASY fields are missing
        """
        # Validate required fields
        self._validate_required_fields(
            tasy_data,
            ["NR_GLOSA", "CD_CONTA", "VL_GLOSADO", "CD_MOTIVO_GLOSA"],
        )

        # Sanitize for LGPD logging
        _sanitized = self._sanitize_for_lgpd(tasy_data)
        self._logger.info(
            "Converting TASY GLOSA to FHIR ClaimResponse",
            extra={
                "glosa_id": tasy_data["NR_GLOSA"],
                "tenant_id": self._tenant_id,
            },
        )

        # Build ClaimResponse
        try:
            claim_response = self._build_claim_response(tasy_data)
            self._track_conversion_success()
            return claim_response

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            raise

    def _build_claim_response(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR ClaimResponse resource from TASY GLOSA data."""
        glosa_id = str(tasy_data["NR_GLOSA"])
        claim_id = str(tasy_data["CD_CONTA"])
        status = tasy_data.get("ST_GLOSA", "I")
        glosa_date = tasy_data.get("DT_GLOSA")

        # Map TASY status to FHIR outcome
        outcome = self.GLOSA_STATUS_MAP.get(status, "queued")

        # Parse glosa date
        created = self._parse_tasy_date(glosa_date) if glosa_date else datetime.utcnow().isoformat()

        # Build base ClaimResponse
        claim_response: dict[str, Any] = {
            "resourceType": "ClaimResponse",
            "id": glosa_id,
            "identifier": [
                self._build_identifier(
                    system=f"https://tasy.{self._tenant_id}/glosa",
                    value=glosa_id,
                    type_code="FILL",  # Filler/Placer identifier
                )
            ],
            "status": "active",
            "type": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://terminology.hl7.org/CodeSystem/claim-type",
                        code="institutional",
                        display="Institutional",
                    )
                ],
                text="Hospital Claim",
            ),
            "use": "claim",
            "patient": self._build_reference("Patient", "unknown"),  # Would need patient lookup
            "created": created,
            "insurer": self._build_reference("Organization", "unknown"),  # Would need payer lookup
            "request": self._build_reference("Claim", claim_id),
            "outcome": outcome,
            "item": self._build_items(tasy_data),
            "total": self._build_total(tasy_data),
        }

        # Add disposition (reason text)
        if tasy_data.get("DS_MOTIVO"):
            claim_response["disposition"] = tasy_data["DS_MOTIVO"]

        return claim_response

    def _build_items(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build item list with adjudication details."""
        items = []

        # Check if TASY data includes itemized glosas
        tasy_items = tasy_data.get("ITENS", [])

        if tasy_items:
            # Process itemized glosas
            for idx, tasy_item in enumerate(tasy_items, start=1):
                item = self._build_glosa_item(idx, tasy_item, tasy_data)
                items.append(item)
        else:
            # Single glosa without items - create summary item
            item = self._build_summary_item(tasy_data)
            items.append(item)

        return items

    def _build_glosa_item(
        self, sequence: int, tasy_item: dict[str, Any], tasy_glosa: dict[str, Any]
    ) -> dict[str, Any]:
        """Build individual glosa item with adjudication."""
        denied_amount = float(tasy_item.get("VL_GLOSADO", 0))
        reason_code = tasy_item.get("CD_MOTIVO_GLOSA", tasy_glosa.get("CD_MOTIVO_GLOSA"))

        item: dict[str, Any] = {
            "itemSequence": sequence,
            "adjudication": [
                {
                    "category": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/adjudication",
                                code="denied",
                                display="Denied",
                            )
                        ],
                        text="Glosa",
                    ),
                    "reason": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=f"https://tasy.{self._tenant_id}/glosa-reason",
                                code=str(reason_code),
                            )
                        ],
                        text=tasy_item.get("DS_MOTIVO", ""),
                    ),
                    "amount": {
                        "value": denied_amount,
                        "currency": "BRL",
                    },
                }
            ],
        }

        return item

    def _build_summary_item(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build summary item when no itemization is available."""
        denied_amount = float(tasy_data.get("VL_GLOSADO", 0))
        reason_code = tasy_data.get("CD_MOTIVO_GLOSA")

        item: dict[str, Any] = {
            "itemSequence": 1,
            "adjudication": [
                {
                    "category": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/adjudication",
                                code="denied",
                                display="Denied",
                            )
                        ],
                        text="Glosa Total",
                    ),
                    "reason": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=f"https://tasy.{self._tenant_id}/glosa-reason",
                                code=str(reason_code),
                            )
                        ],
                        text=tasy_data.get("DS_MOTIVO", ""),
                    ),
                    "amount": {
                        "value": denied_amount,
                        "currency": "BRL",
                    },
                }
            ],
        }

        return item

    def _build_total(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build total amount section."""
        denied_amount = float(tasy_data.get("VL_GLOSADO", 0))

        return [
            {
                "category": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/adjudication",
                            code="denied",
                            display="Denied",
                        )
                    ],
                    text="Total Glosado",
                ),
                "amount": {
                    "value": denied_amount,
                    "currency": "BRL",
                },
            }
        ]

    def _parse_tasy_date(self, date_str: str) -> str:
        """Parse TASY date to ISO 8601 format.

        TASY dates can be in formats like:
        - "2024-01-15 10:30:00"
        - "2024-01-15"
        """
        try:
            # Try full datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            return dt.isoformat()
        except ValueError:
            try:
                # Try date only
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.isoformat()
            except ValueError:
                # Return as-is if parsing fails
                return date_str

    async def adapt_appeal(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert TASY appeal data to FHIR ClaimResponse with appeal details.

        Args:
            tasy_data: TASY GLOSA record with appeal information:
                - NR_RECURSO: Appeal ID
                - DT_RECURSO: Appeal date
                - DS_JUSTIFICATIVA: Appeal justification
                - ST_RECURSO: Appeal status

        Returns:
            FHIR ClaimResponse with appeal extension
        """
        # Start with base ClaimResponse
        claim_response = await self.adapt(tasy_data)

        # Add appeal-specific extensions
        appeal_id = tasy_data.get("NR_RECURSO")
        appeal_date = tasy_data.get("DT_RECURSO")
        appeal_status = tasy_data.get("ST_RECURSO")
        justification = tasy_data.get("DS_JUSTIFICATIVA")

        if appeal_id:
            extension = {
                "url": f"https://tasy.{self._tenant_id}/fhir/StructureDefinition/glosa-appeal",
                "extension": [
                    {
                        "url": "appealId",
                        "valueString": str(appeal_id),
                    },
                ],
            }

            if appeal_date:
                extension["extension"].append({
                    "url": "appealDate",
                    "valueDateTime": self._parse_tasy_date(appeal_date),
                })

            if appeal_status:
                extension["extension"].append({
                    "url": "appealStatus",
                    "valueCode": appeal_status,
                })

            if justification:
                extension["extension"].append({
                    "url": "justification",
                    "valueString": justification,
                })

            # Add extension to ClaimResponse
            if "extension" not in claim_response:
                claim_response["extension"] = []
            claim_response["extension"].append(extension)

        return claim_response
