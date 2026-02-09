"""
Optimize Resource Utilization Worker.

Analyzes OR utilization, bed turnover, staff productivity, and equipment usage
to identify optimization opportunities.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)

# Prometheus metrics
utilization_analyses_total = Counter(
    "optimize_resource_utilization_analyses_total",
    "Total resource utilization analyses performed",
    ["tenant_id", "resource_type"],
)
utilization_duration_seconds = Histogram(
    "optimize_resource_utilization_duration_seconds",
    "Duration of resource utilization analysis",
    ["tenant_id"],
)


class ResourceUtilizationOptimizationError(DomainException):
    """Exception raised when resource utilization optimization fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="RESOURCE_UTILIZATION_OPTIMIZATION_ERROR",
            bpmn_error_code="ResourceUtilizationOptimizationError",
            details=details or {},
        )


class OptimizeResourceUtilizationInput(BaseModel):
    """Input model for optimizing resource utilization."""

    analysis_period_days: int = Field(
        30, description=_("Período de análise em dias")
    )
    include_or_analysis: bool = Field(
        True, description=_("Incluir análise de centro cirúrgico")
    )
    include_bed_analysis: bool = Field(
        True, description=_("Incluir análise de ocupação de leitos")
    )
    include_staff_analysis: bool = Field(
        True, description=_("Incluir análise de produtividade da equipe")
    )
    include_equipment_analysis: bool = Field(
        True, description=_("Incluir análise de utilização de equipamentos")
    )
    target_utilization: Decimal = Field(
        Decimal("85.0"), description=_("Meta de utilização ideal (%)")
    )


class ORUtilization(BaseModel):
    """Operating room utilization metrics."""

    or_id: str = Field(..., description=_("ID do centro cirúrgico"))
    utilization_rate: Decimal = Field(
        ..., description=_("Taxa de utilização (%)")
    )
    total_hours_available: Decimal = Field(
        ..., description=_("Total de horas disponíveis")
    )
    total_hours_used: Decimal = Field(
        ..., description=_("Total de horas utilizadas")
    )
    average_turnover_time: Decimal = Field(
        ..., description=_("Tempo médio de virada (minutos)")
    )
    first_case_delays: int = Field(
        ..., description=_("Atrasos no primeiro caso")
    )
    revenue_per_hour: Decimal = Field(
        ..., description=_("Receita por hora (R$)")
    )


class BedUtilization(BaseModel):
    """Bed utilization metrics."""

    unit_name: str = Field(..., description=_("Nome da unidade"))
    bed_count: int = Field(..., description=_("Total de leitos"))
    occupancy_rate: Decimal = Field(
        ..., description=_("Taxa de ocupação (%)")
    )
    average_length_of_stay: Decimal = Field(
        ..., description=_("Tempo médio de permanência (dias)")
    )
    turnover_interval: Decimal = Field(
        ..., description=_("Intervalo de virada (horas)")
    )
    admissions_count: int = Field(
        ..., description=_("Total de admissões")
    )


class StaffProductivity(BaseModel):
    """Staff productivity metrics."""

    department: str = Field(..., description=_("Departamento"))
    staff_type: str = Field(..., description=_("Tipo de profissional"))
    productivity_score: Decimal = Field(
        ..., description=_("Score de produtividade (0-100)")
    )
    patients_per_staff: Decimal = Field(
        ..., description=_("Pacientes por profissional")
    )
    overtime_hours: Decimal = Field(
        ..., description=_("Horas extras totais")
    )
    absence_rate: Decimal = Field(
        ..., description=_("Taxa de absenteísmo (%)")
    )


class EquipmentUtilization(BaseModel):
    """Equipment utilization metrics."""

    equipment_id: str = Field(..., description=_("ID do equipamento"))
    equipment_type: str = Field(..., description=_("Tipo de equipamento"))
    utilization_rate: Decimal = Field(
        ..., description=_("Taxa de utilização (%)")
    )
    maintenance_downtime: Decimal = Field(
        ..., description=_("Tempo de manutenção (horas)")
    )
    revenue_generated: Decimal = Field(
        ..., description=_("Receita gerada (R$)")
    )


class OptimizeResourceUtilizationOutput(BaseModel):
    """Output model for resource utilization optimization."""

    or_utilization: list[ORUtilization] | None = Field(
        None, description=_("Métricas de centro cirúrgico")
    )
    bed_utilization: list[BedUtilization] | None = Field(
        None, description=_("Métricas de leitos")
    )
    staff_productivity: list[StaffProductivity] | None = Field(
        None, description=_("Métricas de produtividade")
    )
    equipment_utilization: list[EquipmentUtilization] | None = Field(
        None, description=_("Métricas de equipamentos")
    )
    overall_efficiency_score: Decimal = Field(
        ..., description=_("Score geral de eficiência (0-100)")
    )
    optimization_opportunities: list[str] = Field(
        ..., description=_("Oportunidades de otimização identificadas")
    )
    estimated_revenue_impact: Decimal = Field(
        ..., description=_("Impacto estimado na receita (R$)")
    )
    analysis_timestamp: datetime = Field(
        ..., description=_("Timestamp da análise")
    )


class OptimizeResourceUtilizationProtocol(ABC):
    """Protocol for optimizing resource utilization."""

    @abstractmethod
    async def execute(
        self, input_data: OptimizeResourceUtilizationInput
    ) -> OptimizeResourceUtilizationOutput:
        """
        Analyze and optimize resource utilization.

        Args:
            input_data: Resource utilization analysis parameters

        Returns:
            OptimizeResourceUtilizationOutput with optimization recommendations

        Raises:
            ResourceUtilizationOptimizationError: If analysis fails
        """
        pass


class OptimizeResourceUtilizationWorkerStub(OptimizeResourceUtilizationProtocol):
    """Stub implementation for optimizing resource utilization."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client

    def _analyze_or_utilization(
        self, period_days: int, target: Decimal
    ) -> list[ORUtilization]:
        """Analyze operating room utilization."""
        or_data = []

        for i in range(1, 6):  # 5 ORs
            available_hours = Decimal(str(period_days * 12))  # 12 hours/day
            used_hours = available_hours * (Decimal("60") + Decimal(i * 5)) / 100

            utilization = ORUtilization(
                or_id=f"OR-{i:02d}",
                utilization_rate=(used_hours / available_hours) * 100,
                total_hours_available=available_hours,
                total_hours_used=used_hours,
                average_turnover_time=Decimal(str(30 + i * 5)),
                first_case_delays=i * 2,
                revenue_per_hour=Decimal(str(1000 + i * 200)),
            )
            or_data.append(utilization)

        return or_data

    def _analyze_bed_utilization(
        self, period_days: int
    ) -> list[BedUtilization]:
        """Analyze bed utilization."""
        units = [
            ("UTI Adulto", 20, 88.5, 5.2),
            ("Enfermaria Clínica", 50, 75.3, 4.1),
            ("Enfermaria Cirúrgica", 40, 82.1, 3.8),
            ("Pediatria", 30, 68.9, 2.9),
        ]

        bed_data = []
        for unit_name, bed_count, occupancy, avg_los in units:
            admissions = int((bed_count * occupancy / 100 * period_days) / avg_los)

            utilization = BedUtilization(
                unit_name=unit_name,
                bed_count=bed_count,
                occupancy_rate=Decimal(str(occupancy)),
                average_length_of_stay=Decimal(str(avg_los)),
                turnover_interval=Decimal(str(2.5 + (occupancy / 50))),
                admissions_count=admissions,
            )
            bed_data.append(utilization)

        return bed_data

    def _analyze_staff_productivity(self) -> list[StaffProductivity]:
        """Analyze staff productivity."""
        departments = [
            ("Enfermagem", "ENFERMEIRO", 78.5, 5.2, 120, 3.5),
            ("Enfermagem", "TECNICO", 82.1, 7.8, 150, 5.2),
            ("Farmácia", "FARMACEUTICO", 85.3, 8.5, 80, 2.1),
            ("Radiologia", "TECNICO_RAD", 73.2, 6.3, 90, 4.8),
        ]

        staff_data = []
        for dept, staff_type, score, patients, overtime, absence in departments:
            productivity = StaffProductivity(
                department=dept,
                staff_type=staff_type,
                productivity_score=Decimal(str(score)),
                patients_per_staff=Decimal(str(patients)),
                overtime_hours=Decimal(str(overtime)),
                absence_rate=Decimal(str(absence)),
            )
            staff_data.append(productivity)

        return staff_data

    def _analyze_equipment_utilization(
        self, period_days: int
    ) -> list[EquipmentUtilization]:
        """Analyze equipment utilization."""
        equipment = [
            ("MRI-01", "RESSONANCIA", 72.5, 24, 85000),
            ("TC-01", "TOMOGRAFO", 88.3, 12, 120000),
            ("USG-01", "ULTRASSOM", 65.8, 8, 35000),
            ("RX-01", "RAIO_X", 92.1, 6, 45000),
        ]

        equipment_data = []
        for eq_id, eq_type, utilization, downtime, revenue in equipment:
            util = EquipmentUtilization(
                equipment_id=eq_id,
                equipment_type=eq_type,
                utilization_rate=Decimal(str(utilization)),
                maintenance_downtime=Decimal(str(downtime)),
                revenue_generated=Decimal(str(revenue)),
            )
            equipment_data.append(util)

        return equipment_data

    def _identify_optimization_opportunities(
        self,
        or_data: list[ORUtilization] | None,
        bed_data: list[BedUtilization] | None,
        staff_data: list[StaffProductivity] | None,
        equipment_data: list[EquipmentUtilization] | None,
        target: Decimal,
    ) -> list[str]:
        """Identify optimization opportunities."""
        opportunities = []

        if or_data:
            underutilized_ors = [
                or_item for or_item in or_data if or_item.utilization_rate < target
            ]
            if underutilized_ors:
                opportunities.append(
                    _(
                        f"{len(underutilized_ors)} centro(s) cirúrgico(s) com utilização abaixo do ideal - considerar redistribuição de casos"
                    )
                )

            high_turnover = [
                or_item
                for or_item in or_data
                if or_item.average_turnover_time > 35
            ]
            if high_turnover:
                opportunities.append(
                    _(
                        f"Reduzir tempo de virada em {len(high_turnover)} sala(s) - economia potencial de 2-3 horas/dia"
                    )
                )

        if bed_data:
            low_occupancy = [
                bed for bed in bed_data if bed.occupancy_rate < Decimal("70")
            ]
            if low_occupancy:
                opportunities.append(
                    _(
                        f"{len(low_occupancy)} unidade(s) com ocupação baixa - oportunidade para consolidação"
                    )
                )

        if staff_data:
            low_productivity = [
                staff
                for staff in staff_data
                if staff.productivity_score < Decimal("75")
            ]
            if low_productivity:
                opportunities.append(
                    _(
                        f"Melhorar produtividade em {len(low_productivity)} departamento(s) através de treinamento"
                    )
                )

            high_overtime = [
                staff
                for staff in staff_data
                if staff.overtime_hours > Decimal("100")
            ]
            if high_overtime:
                opportunities.append(
                    _(
                        f"Reduzir horas extras em {len(high_overtime)} área(s) - economia de custos estimada"
                    )
                )

        if equipment_data:
            underutilized_equipment = [
                eq for eq in equipment_data if eq.utilization_rate < Decimal("70")
            ]
            if underutilized_equipment:
                opportunities.append(
                    _(
                        f"{len(underutilized_equipment)} equipamento(s) subutilizado(s) - aumentar agendamento ou considerar realocação"
                    )
                )

        return opportunities

    def _calculate_efficiency_score(
        self,
        or_data: list[ORUtilization] | None,
        bed_data: list[BedUtilization] | None,
        staff_data: list[StaffProductivity] | None,
        equipment_data: list[EquipmentUtilization] | None,
    ) -> Decimal:
        """Calculate overall efficiency score."""
        scores = []

        if or_data:
            avg_or = sum(or_item.utilization_rate for or_item in or_data) / len(
                or_data
            )
            scores.append(avg_or)

        if bed_data:
            avg_bed = sum(bed.occupancy_rate for bed in bed_data) / len(bed_data)
            scores.append(avg_bed)

        if staff_data:
            avg_staff = sum(
                staff.productivity_score for staff in staff_data
            ) / len(staff_data)
            scores.append(avg_staff)

        if equipment_data:
            avg_equipment = sum(
                eq.utilization_rate for eq in equipment_data
            ) / len(equipment_data)
            scores.append(avg_equipment)

        return sum(scores) / len(scores) if scores else Decimal("0")

    def _estimate_revenue_impact(
        self,
        or_data: list[ORUtilization] | None,
        opportunities: list[str],
    ) -> Decimal:
        """Estimate potential revenue impact from optimizations."""
        impact = Decimal("0")

        if or_data:
            # Assume 5% improvement in OR utilization
            for or_item in or_data:
                potential_hours = or_item.total_hours_available * Decimal("0.05")
                impact += potential_hours * or_item.revenue_per_hour

        # Add estimated impact from other optimizations
        impact += Decimal(str(len(opportunities) * 10000))  # R$10k per opportunity

        return impact

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: OptimizeResourceUtilizationInput
    ) -> OptimizeResourceUtilizationOutput:
        """Execute resource utilization optimization analysis."""
        tenant_id = get_required_tenant()
        logger.info(
            "Analyzing resource utilization",
            extra={"tenant_id": tenant_id, "period_days": input_data.analysis_period_days},
        )

        with utilization_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                or_data = None
                bed_data = None
                staff_data = None
                equipment_data = None

                if input_data.include_or_analysis:
                    or_data = self._analyze_or_utilization(
                        input_data.analysis_period_days, input_data.target_utilization
                    )
                    utilization_analyses_total.labels(
                        tenant_id=tenant_id, resource_type="OR"
                    ).inc()

                if input_data.include_bed_analysis:
                    bed_data = self._analyze_bed_utilization(
                        input_data.analysis_period_days
                    )
                    utilization_analyses_total.labels(
                        tenant_id=tenant_id, resource_type="BED"
                    ).inc()

                if input_data.include_staff_analysis:
                    staff_data = self._analyze_staff_productivity()
                    utilization_analyses_total.labels(
                        tenant_id=tenant_id, resource_type="STAFF"
                    ).inc()

                if input_data.include_equipment_analysis:
                    equipment_data = self._analyze_equipment_utilization(
                        input_data.analysis_period_days
                    )
                    utilization_analyses_total.labels(
                        tenant_id=tenant_id, resource_type="EQUIPMENT"
                    ).inc()

                opportunities = self._identify_optimization_opportunities(
                    or_data, bed_data, staff_data, equipment_data, input_data.target_utilization
                )

                efficiency_score = self._calculate_efficiency_score(
                    or_data, bed_data, staff_data, equipment_data
                )

                revenue_impact = self._estimate_revenue_impact(or_data, opportunities)

                result = OptimizeResourceUtilizationOutput(
                    or_utilization=or_data,
                    bed_utilization=bed_data,
                    staff_productivity=staff_data,
                    equipment_utilization=equipment_data,
                    overall_efficiency_score=efficiency_score,
                    optimization_opportunities=opportunities,
                    estimated_revenue_impact=revenue_impact,
                    analysis_timestamp=datetime.now(),
                )

                logger.info(
                    "Resource utilization analysis completed",
                    extra={
                        "tenant_id": tenant_id,
                        "efficiency_score": float(efficiency_score),
                        "opportunities": len(opportunities),
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Resource utilization analysis failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise ResourceUtilizationOptimizationError(
                    _("Falha ao analisar utilização de recursos"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "optimize-resource-utilization"
