"""Tasy Billing to FHIR Claim R4 adapter with Brazilian coding systems.

Maps Tasy CONTA_MEDICA + ITEM_CONTA tables to FHIR Claim resource:
- NR_CONTA -> Claim.identifier
- DT_CONTA -> Claim.created
- VL_TOTAL -> Claim.total
- IE_SITUACAO -> Claim.status (A=active, C=cancelled, E=entered-in-error)
- TP_CONTA -> Claim.type (I=institutional, P=professional, F=pharmacy)
- Items from ITEM_CONTA -> Claim.item[] with:
  - CD_PROCEDIMENTO -> item.productOrService (TUSS/CBHPM/CID-10)
  - QT_ITEM -> item.quantity
  - VL_UNITARIO -> item.unitPrice
  - DT_SERVICO -> item.servicedDate

Brazilian Coding Systems:
- TUSS: Terminologia Unificada da Saúde Suplementar (ANS)
- CBHPM: Classificação Brasileira Hierarquizada de Procedimentos Médicos
- CID-10: Classificação Internacional de Doenças

Example Tasy data:
{
    "NR_CONTA": "CONTA-456",
    "DT_CONTA": "2024-02-10",
    "VL_TOTAL": 2500.00,
    "IE_SITUACAO": "A",  # A=active, C=cancelled, E=entered-in-error
    "TP_CONTA": "P",  # P=professional, I=institutional, F=pharmacy
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "CD_CONVENIO": "CONV-123",
    "IE_PRIORIDADE": "N",  # N=normal, S=stat
    "items": [
        {
            "CD_ITEM_CONTA": "ITEM-001",
            "CD_PROCEDIMENTO": "40101010",  # TUSS code
            "TP_PROCEDIMENTO": "TUSS",  # TUSS|CBHPM|CID10
            "DS_PROCEDIMENTO": "Consulta médica",
            "QT_ITEM": 1,
            "VL_UNITARIO": 500.00,
            "VL_TOTAL": 500.00,
            "DT_SERVICO": "2024-02-10"
        },
        {
            "CD_ITEM_CONTA": "ITEM-002",
            "CD_PROCEDIMENTO": "20104030",
            "TP_PROCEDIMENTO": "CBHPM",
            "DS_PROCEDIMENTO": "Raio-X de tórax",
            "QT_ITEM": 1,
            "VL_UNITARIO": 2000.00,
            "VL_TOTAL": 2000.00,
            "DT_SERVICO": "2024-02-10"
        }
    ]
}

Example FHIR Claim R4:
{
    "resourceType": "Claim",
    "identifier": [{
        "system": "http://tasy.com/fhir/identifier/conta-medica",
        "value": "CONTA-456"
    }],
    "status": "active",
    "type": {
        "coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/claim-type",
            "code": "professional"
        }]
    },
    "use": "claim",
    "patient": {
        "reference": "Patient/123456"
    },
    "created": "2024-02-10",
    "provider": {
        "type": "Organization",
        "display": "Healthcare Provider"
    },
    "priority": {
        "coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/processpriority",
            "code": "normal"
        }]
    },
    "insurance": [{
        "sequence": 1,
        "focal": true,
        "coverage": {
            "type": "Coverage",
            "identifier": {
                "system": "http://tasy.com/fhir/identifier/convenio",
                "value": "CONV-123"
            }
        }
    }],
    "item": [{
        "sequence": 1,
        "productOrService": {
            "coding": [{
                "system": "http://www.ans.gov.br/tuss",
                "code": "40101010",
                "display": "Consulta médica"
            }]
        },
        "quantity": {"value": 1},
        "unitPrice": {"value": 500.00, "currency": "BRL"},
        "net": {"value": 500.00, "currency": "BRL"},
        "servicedDate": "2024-02-10"
    }],
    "total": {"value": 2500.00, "currency": "BRL"}
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyClaimAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy CONTA_MEDICA to FHIR Claim R4.

    Supports Brazilian coding systems (TUSS, CBHPM, CID-10) and
    handles institutional, professional, and pharmacy claims.
    """

    ADAPTER_TYPE = "claim"
    FHIR_RESOURCE_TYPE = "Claim"

    # Identifier systems
    TASY_CONTA_SYSTEM = "http://tasy.com/fhir/identifier/conta-medica"
    TASY_CONVENIO_SYSTEM = "http://tasy.com/fhir/identifier/convenio"

    # Brazilian coding systems
    TUSS_SYSTEM = "http://www.ans.gov.br/tuss"
    CBHPM_SYSTEM = "http://www.cbhpm.com.br"
    CID10_SYSTEM = "http://hl7.org/fhir/sid/icd-10"

    # FHIR terminology systems
    CLAIM_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/claim-type"
    PRIORITY_SYSTEM = "http://terminology.hl7.org/CodeSystem/processpriority"

    # Status mapping: Tasy IE_SITUACAO -> FHIR Claim.status
    STATUS_MAP = {
        "A": "active",  # Aberta
        "F": "active",  # Fechada
        "P": "active",  # Paga
        "C": "cancelled",  # Cancelada
        "E": "entered-in-error",  # Erro
        "G": "active",  # Glosada (with denial)
    }

    # Type mapping: Tasy TP_CONTA -> FHIR claim-type
    TYPE_MAP = {
        "I": "institutional",  # Internação
        "P": "professional",  # Profissional
        "F": "pharmacy",  # Farmácia
    }

    # Priority mapping: Tasy IE_PRIORIDADE -> FHIR priority
    PRIORITY_MAP = {
        "N": "normal",
        "S": "stat",
        "U": "stat",  # Urgente = stat
    }

    # Procedure type to coding system mapping
    PROCEDURE_SYSTEM_MAP = {
        "TUSS": TUSS_SYSTEM,
        "CBHPM": CBHPM_SYSTEM,
        "CID10": CID10_SYSTEM,
    }

    async def adapt(self, tasy_billing_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy CONTA_MEDICA to FHIR Claim R4.

        Args:
            tasy_billing_data: Tasy CONTA_MEDICA + ITEM_CONTA data

        Returns:
            FHIR Claim R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_billing_data,
                ["NR_CONTA", "DT_CONTA", "NR_PACIENTE", "NR_ATENDIMENTO"],
            )

            self._logger.debug(
                "Converting Tasy billing to FHIR Claim",
                extra={
                    "nr_conta": tasy_billing_data["NR_CONTA"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR Claim resource
            claim: dict[str, Any] = {
                "resourceType": "Claim",
                "meta": {
                    "profile": [
                        "http://hl7.org/fhir/StructureDefinition/Claim",
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
                        system=self.TASY_CONTA_SYSTEM,
                        value=tasy_billing_data["NR_CONTA"],
                    )
                ],
                "status": self._map_status(tasy_billing_data.get("IE_SITUACAO")),
                "type": self._build_claim_type(tasy_billing_data.get("TP_CONTA")),
                "use": "claim",
                "patient": self._build_reference(
                    "Patient",
                    tasy_billing_data["NR_PACIENTE"],
                ),
                "created": tasy_billing_data["DT_CONTA"],
                "provider": self._build_provider_reference(),
            }

            # Add priority if provided
            if "IE_PRIORIDADE" in tasy_billing_data:
                claim["priority"] = self._build_priority(
                    tasy_billing_data["IE_PRIORIDADE"]
                )

            # Add insurance reference if convênio provided
            if "CD_CONVENIO" in tasy_billing_data:
                claim["insurance"] = [
                    self._build_insurance(
                        tasy_billing_data["CD_CONVENIO"],
                        tasy_billing_data["NR_PACIENTE"],
                    )
                ]

            # Add items if provided
            if "items" in tasy_billing_data and tasy_billing_data["items"]:
                claim["item"] = self._build_items(tasy_billing_data["items"])

            # Add total if provided
            if "VL_TOTAL" in tasy_billing_data:
                claim["total"] = self._build_money(tasy_billing_data["VL_TOTAL"])

            self._track_conversion_success()
            self._logger.info(
                "Successfully converted Tasy billing to FHIR Claim",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "nr_conta": tasy_billing_data["NR_CONTA"],
                    "tenant_id": self._tenant_id,
                },
            )

            return claim

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy billing to FHIR Claim",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tasy_data": self._sanitize_for_lgpd(tasy_billing_data),
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    async def reverse_adapt(self, fhir_claim: dict[str, Any]) -> dict[str, Any]:
        """Convert FHIR Claim R4 back to Tasy format.

        Args:
            fhir_claim: FHIR Claim R4 resource

        Returns:
            Tasy CONTA_MEDICA format dictionary

        Raises:
            ValueError: If required FHIR fields are missing
        """
        try:
            self._logger.debug(
                "Converting FHIR Claim to Tasy billing format",
                extra={
                    "resource_type": fhir_claim.get("resourceType"),
                    "tenant_id": self._tenant_id,
                },
            )

            # Extract Tasy identifier
            nr_conta = None
            for identifier in fhir_claim.get("identifier", []):
                if identifier.get("system") == self.TASY_CONTA_SYSTEM:
                    nr_conta = identifier.get("value")
                    break

            if not nr_conta:
                raise ValueError("Missing Tasy conta identifier in FHIR Claim")

            # Build Tasy format
            tasy_data: dict[str, Any] = {
                "NR_CONTA": nr_conta,
                "DT_CONTA": fhir_claim.get("created"),
            }

            # Reverse map status
            fhir_status = fhir_claim.get("status")
            for tasy_status, mapped_status in self.STATUS_MAP.items():
                if mapped_status == fhir_status:
                    tasy_data["IE_SITUACAO"] = tasy_status
                    break

            # Reverse map type
            if "type" in fhir_claim:
                type_coding = fhir_claim["type"].get("coding", [{}])[0]
                type_code = type_coding.get("code")
                for tasy_type, mapped_type in self.TYPE_MAP.items():
                    if mapped_type == type_code:
                        tasy_data["TP_CONTA"] = tasy_type
                        break

            # Extract patient reference
            if "patient" in fhir_claim:
                patient_ref = fhir_claim["patient"].get("reference", "")
                if "/" in patient_ref:
                    tasy_data["NR_PACIENTE"] = patient_ref.split("/")[1]

            # Extract total
            if "total" in fhir_claim:
                tasy_data["VL_TOTAL"] = fhir_claim["total"].get("value")

            # Extract items
            if "item" in fhir_claim:
                tasy_data["items"] = self._reverse_build_items(fhir_claim["item"])

            self._logger.info(
                "Successfully converted FHIR Claim to Tasy format",
                extra={
                    "nr_conta": nr_conta,
                    "tenant_id": self._tenant_id,
                },
            )

            return tasy_data

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert FHIR Claim to Tasy format",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def _map_status(self, situacao: str | None) -> str:
        """Map Tasy IE_SITUACAO to FHIR Claim status.

        Args:
            situacao: Tasy IE_SITUACAO value

        Returns:
            FHIR status code (active, cancelled, entered-in-error)
        """
        return self.STATUS_MAP.get(situacao, "active") if situacao else "active"

    def _build_claim_type(self, tp_conta: str | None) -> dict[str, Any]:
        """Build FHIR claim type CodeableConcept from Tasy TP_CONTA.

        Args:
            tp_conta: Tasy TP_CONTA value (I=institutional, P=professional, F=pharmacy)

        Returns:
            FHIR CodeableConcept with claim-type coding
        """
        claim_type_code = self.TYPE_MAP.get(tp_conta, "professional") if tp_conta else "professional"

        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.CLAIM_TYPE_SYSTEM,
                    code=claim_type_code,
                    display=claim_type_code.capitalize(),
                )
            ],
            text=claim_type_code.capitalize(),
        )

    def _build_priority(self, ie_prioridade: str) -> dict[str, Any]:
        """Build FHIR priority CodeableConcept from Tasy IE_PRIORIDADE.

        Args:
            ie_prioridade: Tasy IE_PRIORIDADE value (N=normal, S=stat, U=urgente)

        Returns:
            FHIR CodeableConcept with priority coding
        """
        priority_code = self.PRIORITY_MAP.get(ie_prioridade, "normal")

        return self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.PRIORITY_SYSTEM,
                    code=priority_code,
                    display=priority_code.capitalize(),
                )
            ],
            text=priority_code.capitalize(),
        )

    def _build_provider_reference(self) -> dict[str, Any]:
        """Build reference to provider Organization.

        Note: In production, this would reference the actual provider Organization.
        For now, returns a placeholder reference.
        """
        return {
            "type": "Organization",
            "display": "Healthcare Provider",
        }

    def _build_insurance(
        self, cd_convenio: str, nr_paciente: str
    ) -> dict[str, Any]:
        """Build Claim.insurance element.

        Args:
            cd_convenio: Tasy convênio code
            nr_paciente: Patient identifier

        Returns:
            FHIR Claim.insurance structure
        """
        return {
            "sequence": 1,
            "focal": True,
            "coverage": {
                "type": "Coverage",
                "identifier": self._build_identifier(
                    system=self.TASY_CONVENIO_SYSTEM,
                    value=cd_convenio,
                ),
            },
        }

    def _build_items(self, tasy_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build FHIR Claim.item array from Tasy ITEM_CONTA.

        Supports Brazilian coding systems: TUSS, CBHPM, CID-10.

        Args:
            tasy_items: List of Tasy ITEM_CONTA records

        Returns:
            List of FHIR Claim.item structures
        """
        fhir_items = []

        for idx, item in enumerate(tasy_items, start=1):
            fhir_item: dict[str, Any] = {
                "sequence": idx,
                "productOrService": self._build_procedure_code(
                    item.get("CD_PROCEDIMENTO", ""),
                    item.get("TP_PROCEDIMENTO", "TUSS"),
                    item.get("DS_PROCEDIMENTO"),
                ),
            }

            # Add quantity if present
            if "QT_ITEM" in item:
                fhir_item["quantity"] = {
                    "value": item["QT_ITEM"],
                }

            # Add unit price if present
            if "VL_UNITARIO" in item:
                fhir_item["unitPrice"] = self._build_money(item["VL_UNITARIO"])

            # Add net (total) if present
            if "VL_TOTAL" in item:
                fhir_item["net"] = self._build_money(item["VL_TOTAL"])

            # Add service date if present
            if "DT_SERVICO" in item:
                fhir_item["servicedDate"] = item["DT_SERVICO"]

            fhir_items.append(fhir_item)

        return fhir_items

    def _build_procedure_code(
        self, cd_procedimento: str, tp_procedimento: str, ds_procedimento: str | None
    ) -> dict[str, Any]:
        """Build CodeableConcept for procedure code with Brazilian systems.

        Supports TUSS (ANS), CBHPM, and CID-10 coding systems.

        Args:
            cd_procedimento: Procedure code (TUSS/CBHPM/CID-10)
            tp_procedimento: Type of procedure code (TUSS|CBHPM|CID10)
            ds_procedimento: Procedure description

        Returns:
            FHIR CodeableConcept with appropriate Brazilian coding system
        """
        codings = []

        if cd_procedimento:
            # Determine coding system based on procedure type
            coding_system = self.PROCEDURE_SYSTEM_MAP.get(tp_procedimento, self.TUSS_SYSTEM)

            codings.append(
                self._build_coding(
                    system=coding_system,
                    code=cd_procedimento,
                    display=ds_procedimento,
                )
            )

        return self._build_codeable_concept(
            codings=codings,
            text=ds_procedimento,
        )

    def _build_money(self, value: float) -> dict[str, Any]:
        """Build FHIR Money datatype with Brazilian Real (BRL) currency.

        Args:
            value: Monetary amount

        Returns:
            FHIR Money structure with BRL currency
        """
        return {
            "value": value,
            "currency": "BRL",
        }

    def _reverse_build_items(
        self, fhir_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert FHIR Claim.item array back to Tasy format.

        Args:
            fhir_items: List of FHIR Claim.item structures

        Returns:
            List of Tasy ITEM_CONTA records
        """
        tasy_items = []

        for item in fhir_items:
            tasy_item: dict[str, Any] = {}

            # Extract procedure code
            if "productOrService" in item:
                product_service = item["productOrService"]
                codings = product_service.get("coding", [])
                if codings:
                    coding = codings[0]
                    tasy_item["CD_PROCEDIMENTO"] = coding.get("code")
                    tasy_item["DS_PROCEDIMENTO"] = coding.get("display")

                    # Determine procedure type from system
                    system = coding.get("system")
                    if system == self.TUSS_SYSTEM:
                        tasy_item["TP_PROCEDIMENTO"] = "TUSS"
                    elif system == self.CBHPM_SYSTEM:
                        tasy_item["TP_PROCEDIMENTO"] = "CBHPM"
                    elif system == self.CID10_SYSTEM:
                        tasy_item["TP_PROCEDIMENTO"] = "CID10"

            # Extract quantity
            if "quantity" in item:
                tasy_item["QT_ITEM"] = item["quantity"].get("value")

            # Extract unit price
            if "unitPrice" in item:
                tasy_item["VL_UNITARIO"] = item["unitPrice"].get("value")

            # Extract net total
            if "net" in item:
                tasy_item["VL_TOTAL"] = item["net"].get("value")

            # Extract service date
            if "servicedDate" in item:
                tasy_item["DT_SERVICO"] = item["servicedDate"]

            tasy_items.append(tasy_item)

        return tasy_items
