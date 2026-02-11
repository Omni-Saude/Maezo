"""Tasy to FHIR ClaimResponse adapter with ANS glosa code support.

Converts TASY GLOSA table records to FHIR R4 ClaimResponse resources,
with Brazilian ANS (Agência Nacional de Saúde Suplementar) glosa codes
for standardized denial tracking.

FHIR ClaimResponse represents the adjudication result of a submitted claim,
including accepted, denied, and adjusted amounts. In Brazilian healthcare,
glosas (denials) are tracked with ANS-standardized reason codes.

Example FHIR ClaimResponse:
{
  "resourceType": "ClaimResponse",
  "id": "glosa-12345",
  "status": "active",
  "type": {"coding": [{"system": "...", "code": "institutional"}]},
  "use": "claim",
  "patient": {"reference": "Patient/789"},
  "created": "2024-01-15T10:30:00Z",
  "insurer": {"reference": "Organization/convenio-456"},
  "request": {"reference": "Claim/conta-789"},
  "outcome": "partial",
  "disposition": "Denied for lack of medical necessity",
  "item": [
    {
      "itemSequence": 1,
      "adjudication": [
        {
          "category": {"coding": [{"code": "denied"}]},
          "reason": {"coding": [{"system": "http://www.ans.gov.br/glosa-codes", "code": "302"}]},
          "amount": {"value": 1500.00, "currency": "BRL"}
        }
      ]
    }
  ],
  "payment": {
    "date": "2024-02-01",
    "amount": {"value": 3500.00, "currency": "BRL"}
  }
}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import BaseTasyFhirAdapter


class TasyClaimResponseAdapter(BaseTasyFhirAdapter):
    """Adapter for converting TASY GLOSA to FHIR ClaimResponse with ANS codes.

    Maps TASY glosa (denial) data to FHIR ClaimResponse with Brazilian ANS
    glosa reason codes for standardized denial tracking.

    TASY Table: GLOSA
    FHIR Resource: ClaimResponse (R4)
    ANS Code System: http://www.ans.gov.br/glosa-codes
    """

    ADAPTER_TYPE = "claim_response"
    FHIR_RESOURCE_TYPE = "ClaimResponse"

    # ANS glosa code system URI
    ANS_GLOSA_SYSTEM = "http://www.ans.gov.br/glosa-codes"

    # TASY GLOSA status codes to FHIR ClaimResponse outcome
    GLOSA_STATUS_MAP = {
        "A": "complete",    # Analisada/Aceita (Analyzed/Accepted)
        "N": "error",       # Negada (Denied)
        "R": "partial",     # Recurso/Parcial (Appeal/Partial)
        "P": "queued",      # Pendente (Pending)
        "I": "queued",      # Identificada (Identified)
    }

    # ANS glosa codes to FHIR adjudication category mapping
    # Reference: ANS RN 305/2012 - Glosa codes
    ANS_DENIAL_MAP = {
        # Administrative denials
        "101": "benefit",           # Documento/autorização ausente
        "102": "benefit",           # Prazo de apresentação expirado
        "103": "benefit",           # Fora da cobertura contratual

        # Clinical denials
        "201": "eligible",          # Falta de indicação clínica
        "202": "eligible",          # Procedimento não autorizado
        "203": "eligible",          # Material/medicamento não coberto

        # Technical denials
        "301": "submitted",         # Documentação insuficiente
        "302": "submitted",         # Necessidade médica não comprovada
        "303": "submitted",         # Código de procedimento incorreto

        # Financial denials
        "401": "copay",             # Valor acima da tabela
        "402": "deductible",        # Franquia não atingida
        "403": "benefit",           # Limite de cobertura excedido
    }

    async def adapt(self, tasy_glosa_data: dict[str, Any]) -> dict[str, Any]:
        """Convert TASY GLOSA to FHIR ClaimResponse with ANS codes.

        Args:
            tasy_glosa_data: Raw TASY GLOSA record with fields:
                - NR_GLOSA: Glosa ID (required)
                - CD_CONTA: Billing account/claim ID (required)
                - VL_GLOSADO: Denied amount (required)
                - CD_MOTIVO_GLOSA: ANS denial code (required)
                - DS_MOTIVO: Reason description (optional)
                - DT_GLOSA: Glosa date (optional)
                - ST_GLOSA: Status A/N/R/P/I (optional)
                - CD_CONVENIO: Insurance/payer ID (optional)
                - CD_PACIENTE: Patient ID (optional)
                - DT_PAGAMENTO: Payment date (optional)
                - VL_PAGO: Paid amount (optional)
                - DS_OBSERVACAO: Payer notes (optional)
                - ITENS: List of denied items (optional)

        Returns:
            FHIR R4 ClaimResponse resource

        Raises:
            ValueError: If required TASY fields are missing
        """
        # Validate required fields
        self._validate_required_fields(
            tasy_glosa_data,
            ["NR_GLOSA", "CD_CONTA", "VL_GLOSADO", "CD_MOTIVO_GLOSA"],
        )

        # Sanitize for LGPD logging
        sanitized = self._sanitize_for_lgpd(tasy_glosa_data)
        self._logger.info(
            "Converting TASY GLOSA to FHIR ClaimResponse",
            extra={
                "glosa_id": tasy_glosa_data["NR_GLOSA"],
                "tenant_id": self._tenant_id,
            },
        )

        # Build ClaimResponse
        try:
            claim_response = self._build_claim_response(tasy_glosa_data)
            self._track_conversion_success()
            return claim_response

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            raise

    def _build_claim_response(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build FHIR ClaimResponse resource from TASY GLOSA data."""
        glosa_id = str(tasy_data["NR_GLOSA"])
        claim_id = str(tasy_data["CD_CONTA"])
        status = tasy_data.get("ST_GLOSA", "P")
        glosa_date = tasy_data.get("DT_GLOSA")
        convenio_id = tasy_data.get("CD_CONVENIO", "unknown")
        patient_id = tasy_data.get("CD_PACIENTE", "unknown")

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
                    type_code="FILL",
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
            "patient": self._build_reference("Patient", patient_id),
            "created": created,
            "insurer": self._build_reference(
                "Organization",
                convenio_id,
                display=f"Convênio {convenio_id}"
            ),
            "request": self._build_reference("Claim", claim_id),
            "outcome": outcome,
        }

        # Add disposition (reason text)
        if tasy_data.get("DS_MOTIVO"):
            claim_response["disposition"] = tasy_data["DS_MOTIVO"]

        # Add adjudication items
        claim_response["item"] = self._build_adjudication_items(tasy_data)

        # Add total amounts
        claim_response["total"] = self._build_total_amounts(tasy_data)

        # Add payment information if available
        payment_info = self._build_payment(tasy_data)
        if payment_info:
            claim_response["payment"] = payment_info

        # Add process notes if available
        if tasy_data.get("DS_OBSERVACAO"):
            claim_response["processNote"] = [
                {
                    "type": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://hl7.org/fhir/note-type",
                                code="display",
                                display="Display",
                            )
                        ],
                        text="Payer Notes"
                    ),
                    "text": tasy_data["DS_OBSERVACAO"],
                }
            ]

        return claim_response

    def _build_adjudication_items(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build item list with adjudication details and ANS codes."""
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
        """Build individual glosa item with adjudication and ANS codes."""
        denied_amount = float(tasy_item.get("VL_GLOSADO", 0))
        ans_code = str(tasy_item.get("CD_MOTIVO_GLOSA", tasy_glosa.get("CD_MOTIVO_GLOSA", "999")))

        # Map ANS code to FHIR adjudication category
        adjudication_category = self.ANS_DENIAL_MAP.get(ans_code, "denied")

        item: dict[str, Any] = {
            "itemSequence": sequence,
            "adjudication": [
                {
                    "category": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/adjudication",
                                code=adjudication_category,
                                display=adjudication_category.capitalize(),
                            )
                        ],
                        text="Glosa Item",
                    ),
                    "reason": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=self.ANS_GLOSA_SYSTEM,
                                code=ans_code,
                                display=tasy_item.get("DS_MOTIVO", ""),
                            )
                        ],
                        text=tasy_item.get("DS_MOTIVO", "Denial reason"),
                    ),
                    "amount": self._build_money(denied_amount),
                }
            ],
        }

        return item

    def _build_summary_item(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Build summary item when no itemization is available."""
        denied_amount = float(tasy_data.get("VL_GLOSADO", 0))
        ans_code = str(tasy_data.get("CD_MOTIVO_GLOSA", "999"))

        # Map ANS code to FHIR adjudication category
        adjudication_category = self.ANS_DENIAL_MAP.get(ans_code, "denied")

        item: dict[str, Any] = {
            "itemSequence": 1,
            "adjudication": [
                {
                    "category": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system="http://terminology.hl7.org/CodeSystem/adjudication",
                                code=adjudication_category,
                                display=adjudication_category.capitalize(),
                            )
                        ],
                        text="Glosa Total",
                    ),
                    "reason": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=self.ANS_GLOSA_SYSTEM,
                                code=ans_code,
                                display=tasy_data.get("DS_MOTIVO", ""),
                            )
                        ],
                        text=tasy_data.get("DS_MOTIVO", "Total denial"),
                    ),
                    "amount": self._build_money(denied_amount),
                }
            ],
        }

        return item

    def _build_total_amounts(self, tasy_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build total amount section with submitted and denied amounts."""
        denied_amount = float(tasy_data.get("VL_GLOSADO", 0))

        totals = [
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
                "amount": self._build_money(denied_amount),
            }
        ]

        # Add submitted amount if available
        submitted_amount = tasy_data.get("VL_APRESENTADO")
        if submitted_amount is not None:
            totals.append({
                "category": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/adjudication",
                            code="submitted",
                            display="Submitted",
                        )
                    ],
                    text="Valor Apresentado",
                ),
                "amount": self._build_money(float(submitted_amount)),
            })

        # Add eligible amount (submitted - denied)
        if submitted_amount is not None:
            eligible_amount = float(submitted_amount) - denied_amount
            totals.append({
                "category": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/adjudication",
                            code="eligible",
                            display="Eligible",
                        )
                    ],
                    text="Valor Elegível",
                ),
                "amount": self._build_money(eligible_amount),
            })

        return totals

    def _build_payment(self, tasy_data: dict[str, Any]) -> dict[str, Any] | None:
        """Build payment information if available."""
        payment_date = tasy_data.get("DT_PAGAMENTO")
        paid_amount = tasy_data.get("VL_PAGO")

        if not payment_date and paid_amount is None:
            return None

        payment: dict[str, Any] = {}

        if payment_date:
            payment["date"] = self._parse_tasy_date(payment_date).split("T")[0]  # Date only

        if paid_amount is not None:
            payment["amount"] = self._build_money(float(paid_amount))

        return payment if payment else None

    def _build_money(self, value: float) -> dict[str, Any]:
        """Build FHIR Money datatype with BRL currency."""
        return {
            "value": round(value, 2),
            "currency": "BRL",
        }

    def _parse_tasy_date(self, date_str: str) -> str:
        """Parse TASY date to ISO 8601 format.

        TASY dates can be in formats like:
        - "2024-01-15 10:30:00"
        - "2024-01-15"
        - "15/01/2024"
        """
        if not date_str:
            return datetime.utcnow().isoformat()

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
                try:
                    # Try Brazilian date format
                    dt = datetime.strptime(date_str, "%d/%m/%Y")
                    return dt.isoformat()
                except ValueError:
                    # Return as-is if parsing fails
                    self._logger.warning(
                        "Unable to parse TASY date",
                        extra={"date_str": date_str, "tenant_id": self._tenant_id},
                    )
                    return date_str

    async def reverse_adapt(self, fhir_claim_response: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR ClaimResponse back to TASY glosa format.

        Used for sending appeal responses or updates back to TASY.

        Args:
            fhir_claim_response: FHIR ClaimResponse resource

        Returns:
            TASY GLOSA format dictionary

        Raises:
            ValueError: If required FHIR fields are missing
        """
        if fhir_claim_response.get("resourceType") != "ClaimResponse":
            raise ValueError("Resource must be of type ClaimResponse")

        # Extract glosa ID from identifier
        glosa_id = None
        for identifier in fhir_claim_response.get("identifier", []):
            if "tasy" in identifier.get("system", ""):
                glosa_id = identifier.get("value")
                break

        if not glosa_id:
            glosa_id = fhir_claim_response.get("id")

        # Extract claim ID from request reference
        claim_ref = fhir_claim_response.get("request", {}).get("reference", "")
        claim_id = claim_ref.split("/")[-1] if "/" in claim_ref else claim_ref

        # Extract denied amount from total
        denied_amount = 0.0
        for total in fhir_claim_response.get("total", []):
            category_code = total.get("category", {}).get("coding", [{}])[0].get("code")
            if category_code == "denied":
                denied_amount = total.get("amount", {}).get("value", 0.0)
                break

        # Extract ANS code from first item adjudication
        ans_code = None
        items = fhir_claim_response.get("item", [])
        if items:
            adjudications = items[0].get("adjudication", [])
            if adjudications:
                reason_codings = adjudications[0].get("reason", {}).get("coding", [])
                for coding in reason_codings:
                    if self.ANS_GLOSA_SYSTEM in coding.get("system", ""):
                        ans_code = coding.get("code")
                        break

        # Map FHIR outcome back to TASY status
        outcome = fhir_claim_response.get("outcome", "queued")
        status = "P"  # Default to Pending
        for tasy_status, fhir_outcome in self.GLOSA_STATUS_MAP.items():
            if fhir_outcome == outcome:
                status = tasy_status
                break

        # Build TASY format
        tasy_glosa = {
            "NR_GLOSA": glosa_id,
            "CD_CONTA": claim_id,
            "VL_GLOSADO": denied_amount,
            "CD_MOTIVO_GLOSA": ans_code or "999",
            "DS_MOTIVO": fhir_claim_response.get("disposition", ""),
            "ST_GLOSA": status,
            "DT_GLOSA": fhir_claim_response.get("created", ""),
        }

        # Add payment info if present
        payment = fhir_claim_response.get("payment")
        if payment:
            if payment.get("date"):
                tasy_glosa["DT_PAGAMENTO"] = payment["date"]
            if payment.get("amount"):
                tasy_glosa["VL_PAGO"] = payment["amount"].get("value", 0.0)

        # Add process notes
        process_notes = fhir_claim_response.get("processNote", [])
        if process_notes:
            tasy_glosa["DS_OBSERVACAO"] = process_notes[0].get("text", "")

        self._logger.info(
            "Converted FHIR ClaimResponse to TASY GLOSA format",
            extra={
                "glosa_id": glosa_id,
                "tenant_id": self._tenant_id,
            },
        )

        return tasy_glosa
