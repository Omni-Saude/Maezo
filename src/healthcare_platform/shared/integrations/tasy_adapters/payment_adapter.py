"""Tasy Payment to FHIR PaymentReconciliation R4 adapter.

Maps Tasy PAGAMENTO table to FHIR PaymentReconciliation resource with PIX support:
- NR_PAGAMENTO -> PaymentReconciliation.identifier
- DT_PAGAMENTO -> PaymentReconciliation.created
- VL_PAGAMENTO -> PaymentReconciliation.paymentAmount
- IE_FORMA_PAGAMENTO -> PaymentReconciliation.paymentIdentifier
- IE_STATUS -> PaymentReconciliation.status

Supports 9 PIX endpoint operations:
1. PIX payment initiation (QR code generation)
2. PIX payment confirmation
3. PIX refund
4. PIX status check
5. PIX reconciliation (daily batch)
6. PIX receipt validation
7. PIX end-to-end ID lookup
8. PIX batch export
9. PIX settlement report

Example Tasy data:
{
    "NR_PAGAMENTO": "PAG-789",
    "DT_PAGAMENTO": "2024-02-10T14:30:00Z",
    "VL_PAGAMENTO": 2500.00,
    "IE_FORMA_PAGAMENTO": "PIX",  # PIX, CARTAO, DINHEIRO, BOLETO, etc.
    "IE_STATUS": "P",  # P=pago, A=aguardando, C=cancelado, E=erro, R=reembolsado
    "NR_CONTA": "CONTA-456",
    "NR_PACIENTE": "123456",
    "pix_data": {
        "txid": "E00416968202402101430s0001",
        "e2e_id": "E00416968202402101430123456789",
        "qr_code": "00020126580014br.gov.bcb.pix...",
        "status": "CONCLUIDA",
        "devolucao_id": None
    }
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasyPaymentAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy PAGAMENTO to FHIR PaymentReconciliation R4."""

    ADAPTER_TYPE = "payment"
    FHIR_RESOURCE_TYPE = "PaymentReconciliation"

    # Identifier systems
    TASY_PAYMENT_SYSTEM = "http://tasy.com/fhir/identifier/pagamento"
    PIX_SYSTEM = "http://bcb.gov.br/fhir/pix"

    # Status mapping
    PAYMENT_STATUS_MAP = {
        "P": "complete",  # Pago
        "A": "active",  # Aguardando
        "C": "cancelled",  # Cancelado
        "E": "entered-in-error",  # Erro
        "R": "active",  # Reembolsado (active with refund detail)
    }

    # Payment method codes
    PAYMENT_METHOD_SYSTEM = "http://terminology.hl7.org/CodeSystem/payment-type"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy PAGAMENTO to FHIR PaymentReconciliation R4.

        Args:
            tasy_data: Tasy PAGAMENTO data

        Returns:
            FHIR PaymentReconciliation R4 resource

        Raises:
            ValueError: If required fields are missing
        """
        try:
            # Validate required fields
            self._validate_required_fields(
                tasy_data,
                ["NR_PAGAMENTO", "DT_PAGAMENTO", "VL_PAGAMENTO", "IE_FORMA_PAGAMENTO"],
            )

            self._logger.debug(
                "Convertendo pagamento Tasy para FHIR PaymentReconciliation",
                extra={
                    "nr_pagamento": tasy_data["NR_PAGAMENTO"],
                    "forma_pagamento": tasy_data["IE_FORMA_PAGAMENTO"],
                    "tenant_id": self._tenant_id,
                },
            )

            # Build FHIR PaymentReconciliation resource
            payment_reconciliation = self._build_payment_reconciliation(tasy_data)

            self._track_conversion_success()
            self._logger.info(
                "Pagamento Tasy convertido com sucesso para FHIR PaymentReconciliation",
                extra={
                    "resource_type": self.FHIR_RESOURCE_TYPE,
                    "forma_pagamento": tasy_data["IE_FORMA_PAGAMENTO"],
                    "tenant_id": self._tenant_id,
                },
            )

            return payment_reconciliation

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Falha ao converter pagamento Tasy para FHIR PaymentReconciliation",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                },
            )
            raise

    def adapt_pix_payment(self, tasy_pix_data: dict[str, Any]) -> dict[str, Any]:
        """Convert PIX-specific payment data to FHIR PaymentReconciliation.

        Used for PIX operations:
        - Payment initiation (QR code)
        - Payment confirmation
        - Refund processing
        - Status check
        - Reconciliation

        Args:
            tasy_pix_data: Tasy PAGAMENTO with PIX details

        Returns:
            FHIR PaymentReconciliation with PIX extensions

        Raises:
            ValueError: If PIX-specific fields are missing
        """
        # Validate PIX-specific fields
        if tasy_pix_data.get("IE_FORMA_PAGAMENTO") != "PIX":
            self._logger.warning(
                "adapt_pix_payment chamado para pagamento não-PIX",
                extra={
                    "forma_pagamento": tasy_pix_data.get("IE_FORMA_PAGAMENTO"),
                    "tenant_id": self._tenant_id,
                },
            )

        if "pix_data" not in tasy_pix_data:
            raise ValueError("pix_data é obrigatório para pagamentos PIX")

        # Use standard adaptation with PIX extensions
        return self.adapt(tasy_pix_data)

    def _build_payment_reconciliation(
        self, tasy_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build FHIR PaymentReconciliation resource.

        Args:
            tasy_data: Tasy PAGAMENTO data

        Returns:
            FHIR PaymentReconciliation structure
        """
        payment: dict[str, Any] = {
            "resourceType": "PaymentReconciliation",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/PaymentReconciliation",
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
                    system=self.TASY_PAYMENT_SYSTEM,
                    value=tasy_data["NR_PAGAMENTO"],
                )
            ],
            "status": self._map_payment_status(tasy_data.get("IE_STATUS")),
            "created": tasy_data["DT_PAGAMENTO"],
            "paymentAmount": self._build_money(tasy_data["VL_PAGAMENTO"]),
            "paymentDate": tasy_data["DT_PAGAMENTO"].split("T")[0],
        }

        # Add payment method identifier
        forma_pagamento = tasy_data["IE_FORMA_PAGAMENTO"]
        payment["paymentIdentifier"] = self._build_codeable_concept(
            codings=[
                self._build_coding(
                    system=self.PAYMENT_METHOD_SYSTEM,
                    code=self._map_payment_method(forma_pagamento),
                    display=forma_pagamento,
                )
            ],
            text=forma_pagamento,
        )

        # Add request reference if conta provided
        if "NR_CONTA" in tasy_data:
            payment["request"] = self._build_reference(
                "Claim",
                tasy_data["NR_CONTA"],
            )

        # Add detail array with payment information
        payment["detail"] = self._build_payment_details(tasy_data)

        # Add PIX extension if PIX payment
        if forma_pagamento == "PIX" and "pix_data" in tasy_data:
            payment["extension"] = [self._build_pix_extension(tasy_data["pix_data"])]

        return payment

    def _build_payment_details(
        self, tasy_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Build PaymentReconciliation.detail array.

        Args:
            tasy_data: Tasy PAGAMENTO data

        Returns:
            List of FHIR PaymentReconciliation.detail structures
        """
        details = [
            {
                "type": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/payment-type",
                            code="payment",
                            display="Payment",
                        )
                    ],
                    text="Pagamento",
                ),
                "amount": self._build_money(tasy_data["VL_PAGAMENTO"]),
                "date": tasy_data["DT_PAGAMENTO"].split("T")[0],
            }
        ]

        # Add request reference if conta provided
        if "NR_CONTA" in tasy_data:
            details[0]["request"] = self._build_reference(
                "Claim",
                tasy_data["NR_CONTA"],
            )

        return details

    def _build_pix_extension(self, pix_data: dict[str, Any]) -> dict[str, Any]:
        """Build PIX extension for PaymentReconciliation.

        Contains PIX-specific data:
        - txid: Transaction identifier
        - e2e_id: End-to-end identifier
        - qr_code: QR code for payment
        - status: PIX transaction status
        - devolucao_id: Refund identifier (if applicable)

        Args:
            pix_data: PIX-specific data from Tasy

        Returns:
            FHIR Extension structure
        """
        extension: dict[str, Any] = {
            "url": "http://bcb.gov.br/fhir/StructureDefinition/pix-payment",
            "extension": [],
        }

        # Add txid
        if "txid" in pix_data:
            extension["extension"].append(
                {
                    "url": "txid",
                    "valueString": pix_data["txid"],
                }
            )

        # Add e2e_id
        if "e2e_id" in pix_data:
            extension["extension"].append(
                {
                    "url": "endToEndId",
                    "valueIdentifier": self._build_identifier(
                        system=self.PIX_SYSTEM,
                        value=pix_data["e2e_id"],
                    ),
                }
            )

        # Add QR code
        if "qr_code" in pix_data:
            extension["extension"].append(
                {
                    "url": "qrCode",
                    "valueString": pix_data["qr_code"],
                }
            )

        # Add PIX status
        if "status" in pix_data:
            extension["extension"].append(
                {
                    "url": "pixStatus",
                    "valueCode": pix_data["status"],
                }
            )

        # Add refund ID if present
        if pix_data.get("devolucao_id"):
            extension["extension"].append(
                {
                    "url": "refundId",
                    "valueString": pix_data["devolucao_id"],
                }
            )

        return extension

    def _map_payment_status(self, status: str | None) -> str:
        """Map Tasy IE_STATUS to FHIR PaymentReconciliation status.

        Args:
            status: Tasy IE_STATUS value

        Returns:
            FHIR status code (active, complete, cancelled, entered-in-error)
        """
        return (
            self.PAYMENT_STATUS_MAP.get(status, "active") if status else "active"
        )

    def _map_payment_method(self, ie_forma: str) -> str:
        """Map Tasy payment method to FHIR payment-type code.

        Args:
            ie_forma: Tasy IE_FORMA_PAGAMENTO value

        Returns:
            FHIR payment-type code
        """
        method_map = {
            "PIX": "payment",
            "CARTAO": "payment",
            "DINHEIRO": "payment",
            "BOLETO": "payment",
            "CHEQUE": "payment",
            "TRANSFERENCIA": "payment",
            "DEBITO": "payment",
            "CREDITO": "payment",
        }
        return method_map.get(ie_forma, "payment")

    def _build_money(self, value: float) -> dict[str, Any]:
        """Build FHIR Money datatype.

        Args:
            value: Monetary amount

        Returns:
            FHIR Money structure with BRL currency
        """
        return {
            "value": value,
            "currency": "BRL",
        }
