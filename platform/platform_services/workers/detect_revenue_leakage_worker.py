"""
Detect Revenue Leakage Worker.

Identifies unbilled services, missed supplies, and uncaptured professional fees
to prevent revenue loss.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)

# Prometheus metrics
leakage_scans_total = Counter(
    "detect_revenue_leakage_scans_total",
    "Total revenue leakage scans performed",
    ["tenant_id", "leakage_type"],
)
leakage_duration_seconds = Histogram(
    "detect_revenue_leakage_duration_seconds",
    "Duration of revenue leakage detection",
    ["tenant_id"],
)
leakage_amount_gauge = Gauge(
    "detect_revenue_leakage_amount_total",
    "Total revenue leakage amount detected (R$)",
    ["tenant_id", "leakage_type"],
)


class RevenueLeakageDetectionError(DomainException):
    """Exception raised when revenue leakage detection fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="REVENUE_LEAKAGE_DETECTION_ERROR",
            bpmn_error_code="RevenueLeakageDetectionError",
            details=details or {},
        )


class DetectRevenueLeakageInput(BaseModel):
    """Input model for detecting revenue leakage."""

    encounter_ids: list[str] = Field(
        ..., description=_("Lista de IDs de atendimentos para analisar")
    )
    analysis_period_days: int = Field(
        30, description=_("Período de análise em dias")
    )
    include_procedures: bool = Field(
        True, description=_("Incluir análise de procedimentos não cobrados")
    )
    include_supplies: bool = Field(
        True, description=_("Incluir análise de materiais não cobrados")
    )
    include_professional_fees: bool = Field(
        True, description=_("Incluir análise de honorários não capturados")
    )
    minimum_amount: Decimal = Field(
        Decimal("10.00"),
        description=_("Valor mínimo para considerar perda (R$)"),
    )


class LeakageItem(BaseModel):
    """Individual revenue leakage item."""

    leakage_type: str = Field(
        ..., description=_("Tipo de perda (PROCEDURE/SUPPLY/PROFESSIONAL_FEE)")
    )
    item_code: str = Field(..., description=_("Código do item não cobrado"))
    item_description: str = Field(..., description=_("Descrição do item"))
    quantity: int = Field(..., description=_("Quantidade não cobrada"))
    unit_price: Decimal = Field(..., description=_("Preço unitário (R$)"))
    total_amount: Decimal = Field(..., description=_("Valor total perdido (R$)"))
    encounter_id: str = Field(..., description=_("ID do atendimento"))
    service_date: datetime = Field(..., description=_("Data do serviço"))
    detection_reason: str = Field(
        ..., description=_("Razão da detecção da perda")
    )


class DetectRevenueLeakageOutput(BaseModel):
    """Output model for revenue leakage detection."""

    leakage_items: list[LeakageItem] = Field(
        ..., description=_("Itens de perda de receita identificados")
    )
    total_leakage_amount: Decimal = Field(
        ..., description=_("Valor total de perda identificado (R$)")
    )
    leakage_by_type: dict[str, Decimal] = Field(
        ..., description=_("Perda agregada por tipo")
    )
    encounters_with_leakage: int = Field(
        ..., description=_("Atendimentos com perda identificada")
    )
    scan_timestamp: datetime = Field(..., description=_("Timestamp da varredura"))
    recommendations: list[str] = Field(
        ..., description=_("Recomendações para recuperação de receita")
    )


class DetectRevenueLeakageProtocol(ABC):
    """Protocol for detecting revenue leakage."""

    @abstractmethod
    async def execute(
        self, input_data: DetectRevenueLeakageInput
    ) -> DetectRevenueLeakageOutput:
        """
        Detect revenue leakage from unbilled services and supplies.

        Args:
            input_data: Leakage detection parameters

        Returns:
            DetectRevenueLeakageOutput with identified leakage items

        Raises:
            RevenueLeakageDetectionError: If detection fails
        """
        pass


class DetectRevenueLeakageWorkerStub(DetectRevenueLeakageProtocol):
    """Stub implementation for detecting revenue leakage."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client

    def _detect_unbilled_procedures(
        self, encounter_id: str, encounter_data: dict[str, Any]
    ) -> list[LeakageItem]:
        """Detect procedures performed but not billed."""
        leakage_items: list[LeakageItem] = []

        performed = encounter_data.get("performed_procedures", [])
        billed = encounter_data.get("billed_procedures", [])

        unbilled = [p for p in performed if p["code"] not in [b["code"] for b in billed]]

        for proc in unbilled:
            leakage_items.append(
                LeakageItem(
                    leakage_type="PROCEDURE",
                    item_code=proc["code"],
                    item_description=proc["description"],
                    quantity=1,
                    unit_price=Decimal(str(proc["price"])),
                    total_amount=Decimal(str(proc["price"])),
                    encounter_id=encounter_id,
                    service_date=datetime.fromisoformat(proc["date"]),
                    detection_reason=_("Procedimento realizado mas não faturado"),
                )
            )

        return leakage_items

    def _detect_unbilled_supplies(
        self, encounter_id: str, encounter_data: dict[str, Any]
    ) -> list[LeakageItem]:
        """Detect supplies used but not billed."""
        leakage_items: list[LeakageItem] = []

        used = encounter_data.get("used_supplies", [])
        billed = encounter_data.get("billed_supplies", [])

        for supply in used:
            billed_qty = sum(
                b["quantity"] for b in billed if b["code"] == supply["code"]
            )
            unbilled_qty = supply["quantity"] - billed_qty

            if unbilled_qty > 0:
                unit_price = Decimal(str(supply["unit_price"]))
                leakage_items.append(
                    LeakageItem(
                        leakage_type="SUPPLY",
                        item_code=supply["code"],
                        item_description=supply["description"],
                        quantity=unbilled_qty,
                        unit_price=unit_price,
                        total_amount=unit_price * unbilled_qty,
                        encounter_id=encounter_id,
                        service_date=datetime.fromisoformat(supply["date"]),
                        detection_reason=_(
                            "Material utilizado mas não faturado completamente"
                        ),
                    )
                )

        return leakage_items

    def _detect_uncaptured_professional_fees(
        self, encounter_id: str, encounter_data: dict[str, Any]
    ) -> list[LeakageItem]:
        """Detect professional fees not captured."""
        leakage_items: list[LeakageItem] = []

        professionals = encounter_data.get("attending_professionals", [])
        billed_fees = encounter_data.get("billed_professional_fees", [])

        for prof in professionals:
            fee_code = f"HONOR_{prof['specialty']}"
            if fee_code not in [f["code"] for f in billed_fees]:
                fee_amount = Decimal(str(prof.get("standard_fee", 200)))
                leakage_items.append(
                    LeakageItem(
                        leakage_type="PROFESSIONAL_FEE",
                        item_code=fee_code,
                        item_description=_(
                            f"Honorário {prof['specialty']} - Dr. {prof['name']}"
                        ),
                        quantity=1,
                        unit_price=fee_amount,
                        total_amount=fee_amount,
                        encounter_id=encounter_id,
                        service_date=datetime.fromisoformat(prof["attendance_date"]),
                        detection_reason=_("Honorário profissional não capturado"),
                    )
                )

        return leakage_items

    def _generate_recommendations(
        self, leakage_items: list[LeakageItem]
    ) -> list[str]:
        """Generate recommendations based on detected leakage."""
        recommendations = []

        procedure_count = sum(
            1 for item in leakage_items if item.leakage_type == "PROCEDURE"
        )
        supply_count = sum(
            1 for item in leakage_items if item.leakage_type == "SUPPLY"
        )
        fee_count = sum(
            1 for item in leakage_items if item.leakage_type == "PROFESSIONAL_FEE"
        )

        if procedure_count > 0:
            recommendations.append(
                _(
                    f"Revisar {procedure_count} procedimentos não faturados e emitir cobranças complementares"
                )
            )

        if supply_count > 0:
            recommendations.append(
                _(
                    f"Corrigir {supply_count} materiais não faturados no próximo lote"
                )
            )

        if fee_count > 0:
            recommendations.append(
                _(
                    f"Capturar {fee_count} honorários profissionais pendentes"
                )
            )

        recommendations.append(
            _("Implementar auditoria contínua para prevenir perdas futuras")
        )
        recommendations.append(
            _("Treinar equipe de faturamento sobre itens frequentemente não cobrados")
        )

        return recommendations

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: DetectRevenueLeakageInput
    ) -> DetectRevenueLeakageOutput:
        """Execute revenue leakage detection."""
        tenant_id = get_required_tenant()
        logger.info(
            "Detecting revenue leakage",
            extra={
                "tenant_id": tenant_id,
                "encounter_count": len(input_data.encounter_ids),
            },
        )

        with leakage_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                all_leakage_items: list[LeakageItem] = []
                encounters_with_leakage = set()

                for encounter_id in input_data.encounter_ids:
                    # Simulate encounter data with potential leakage
                    encounter_data = {
                        "encounter_id": encounter_id,
                        "performed_procedures": [
                            {
                                "code": "PROC001",
                                "description": "Consulta médica",
                                "price": 150.00,
                                "date": "2024-01-15T10:00:00",
                            },
                            {
                                "code": "PROC002",
                                "description": "Exame laboratorial",
                                "price": 80.00,
                                "date": "2024-01-15T11:00:00",
                            },
                        ],
                        "billed_procedures": [
                            {"code": "PROC001", "price": 150.00}
                        ],
                        "used_supplies": [
                            {
                                "code": "MAT001",
                                "description": "Seringa 10ml",
                                "quantity": 5,
                                "unit_price": 2.50,
                                "date": "2024-01-15T10:30:00",
                            },
                            {
                                "code": "MAT002",
                                "description": "Luva descartável",
                                "quantity": 10,
                                "unit_price": 0.50,
                                "date": "2024-01-15T10:30:00",
                            },
                        ],
                        "billed_supplies": [
                            {"code": "MAT001", "quantity": 3}
                        ],
                        "attending_professionals": [
                            {
                                "name": "Silva",
                                "specialty": "CARDIOLOGIA",
                                "standard_fee": 300.00,
                                "attendance_date": "2024-01-15T10:00:00",
                            }
                        ],
                        "billed_professional_fees": [],
                    }

                    encounter_leakage: list[LeakageItem] = []

                    if input_data.include_procedures:
                        encounter_leakage.extend(
                            self._detect_unbilled_procedures(encounter_id, encounter_data)
                        )

                    if input_data.include_supplies:
                        encounter_leakage.extend(
                            self._detect_unbilled_supplies(encounter_id, encounter_data)
                        )

                    if input_data.include_professional_fees:
                        encounter_leakage.extend(
                            self._detect_uncaptured_professional_fees(
                                encounter_id, encounter_data
                            )
                        )

                    # Filter by minimum amount
                    encounter_leakage = [
                        item
                        for item in encounter_leakage
                        if item.total_amount >= input_data.minimum_amount
                    ]

                    if encounter_leakage:
                        encounters_with_leakage.add(encounter_id)
                        all_leakage_items.extend(encounter_leakage)

                        for item in encounter_leakage:
                            leakage_scans_total.labels(
                                tenant_id=tenant_id, leakage_type=item.leakage_type
                            ).inc()

                # Aggregate by type
                leakage_by_type: dict[str, Decimal] = {}
                for item in all_leakage_items:
                    current = leakage_by_type.get(item.leakage_type, Decimal("0"))
                    leakage_by_type[item.leakage_type] = current + item.total_amount

                # Update gauges
                for leakage_type, amount in leakage_by_type.items():
                    leakage_amount_gauge.labels(
                        tenant_id=tenant_id, leakage_type=leakage_type
                    ).set(float(amount))

                total_leakage = sum(item.total_amount for item in all_leakage_items)

                result = DetectRevenueLeakageOutput(
                    leakage_items=all_leakage_items,
                    total_leakage_amount=total_leakage,
                    leakage_by_type=leakage_by_type,
                    encounters_with_leakage=len(encounters_with_leakage),
                    scan_timestamp=datetime.now(),
                    recommendations=self._generate_recommendations(all_leakage_items),
                )

                logger.info(
                    "Revenue leakage detection completed",
                    extra={
                        "tenant_id": tenant_id,
                        "leakage_items": len(all_leakage_items),
                        "total_amount": float(total_leakage),
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Revenue leakage detection failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise RevenueLeakageDetectionError(
                    _("Falha ao detectar perda de receita"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "detect-revenue-leakage"
