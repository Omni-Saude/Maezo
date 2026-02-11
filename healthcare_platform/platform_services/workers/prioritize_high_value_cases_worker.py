"""
Prioritize High-Value Cases Worker.

Ranks clinical cases by revenue potential, complexity, and payer margin
to enable expedited processing of high-value encounters.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
prioritizations_total = Counter(
    "prioritize_high_value_cases_total",
    "Total case prioritizations performed",
    ["tenant_id", "priority_tier"],
)
prioritization_duration_seconds = Histogram(
    "prioritize_high_value_cases_duration_seconds",
    "Duration of case prioritization operations",
    ["tenant_id"],
)


class CasePrioritizationError(DomainException):
    """Exception raised when case prioritization fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="CASE_PRIORITIZATION_ERROR",
            bpmn_error_code="CasePrioritizationError",
            details=details or {},
        )


class PrioritizeHighValueCasesInput(BaseModel):
    """Input model for prioritizing high-value cases."""

    encounter_ids: list[str] = Field(
        ..., description=_("Lista de IDs de atendimentos para priorizar")
    )
    include_complexity: bool = Field(
        True, description=_("Incluir análise de complexidade clínica")
    )
    include_payer_margin: bool = Field(
        True, description=_("Incluir análise de margem por operadora")
    )
    revenue_threshold: Decimal = Field(
        Decimal("5000.00"),
        description=_("Limiar de receita para alta prioridade (R$)"),
    )
    max_cases: int = Field(
        100, description=_("Número máximo de casos para priorizar")
    )


class CasePriority(BaseModel):
    """Individual case priority assessment."""

    encounter_id: str = Field(..., description=_("ID do atendimento"))
    patient_id_hash: str = Field(..., description=_("Hash do ID do paciente"))
    priority_score: Decimal = Field(
        ..., description=_("Score de prioridade (0-100)")
    )
    priority_tier: str = Field(
        ..., description=_("Nível de prioridade (CRITICAL/HIGH/MEDIUM/LOW)")
    )
    estimated_revenue: Decimal = Field(..., description=_("Receita estimada (R$)"))
    complexity_score: Decimal | None = Field(
        None, description=_("Score de complexidade clínica")
    )
    payer_margin: Decimal | None = Field(
        None, description=_("Margem da operadora (%)")
    )
    risk_factors: list[str] = Field(
        default_factory=list, description=_("Fatores de risco identificados")
    )
    recommended_actions: list[str] = Field(
        default_factory=list, description=_("Ações recomendadas")
    )


class PrioritizeHighValueCasesOutput(BaseModel):
    """Output model for case prioritization."""

    prioritized_cases: list[CasePriority] = Field(
        ..., description=_("Casos priorizados ordenados por score")
    )
    total_cases_analyzed: int = Field(..., description=_("Total de casos analisados"))
    critical_cases: int = Field(..., description=_("Casos críticos (prioridade alta)"))
    total_estimated_revenue: Decimal = Field(
        ..., description=_("Receita total estimada (R$)")
    )
    prioritization_timestamp: datetime = Field(
        ..., description=_("Timestamp da priorização")
    )
    analysis_criteria: dict[str, Any] = Field(
        ..., description=_("Critérios utilizados na análise")
    )


class PrioritizeHighValueCasesProtocol(ABC):
    """Protocol for prioritizing high-value cases."""

    @abstractmethod
    async def execute(
        self, input_data: PrioritizeHighValueCasesInput
    ) -> PrioritizeHighValueCasesOutput:
        """
        Prioritize high-value cases based on revenue potential and complexity.

        Args:
            input_data: Case prioritization parameters

        Returns:
            PrioritizeHighValueCasesOutput with prioritized cases

        Raises:
            CasePrioritizationError: If prioritization fails
        """
        pass


class PrioritizeHighValueCasesWorkerStub(PrioritizeHighValueCasesProtocol):
    """Stub implementation for prioritizing high-value cases."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    def _hash_patient_id(self, patient_id: str) -> str:
        """Hash patient ID for LGPD compliance."""
        return hashlib.sha256(patient_id.encode()).hexdigest()[:16]

    def _calculate_complexity_score(self, encounter_data: dict[str, Any]) -> Decimal:
        """Calculate clinical complexity score."""
        score = Decimal("50.0")  # Base score

        # Comorbidities
        comorbidities = encounter_data.get("comorbidities", [])
        score += Decimal(len(comorbidities)) * Decimal("5.0")

        # Length of stay
        los = encounter_data.get("length_of_stay", 0)
        if los > 7:
            score += Decimal("15.0")
        elif los > 3:
            score += Decimal("10.0")

        # ICU admission
        if encounter_data.get("icu_admission"):
            score += Decimal("20.0")

        # Procedures count
        procedures = encounter_data.get("procedures", [])
        score += Decimal(len(procedures)) * Decimal("3.0")

        return min(score, Decimal("100.0"))

    def _calculate_payer_margin(self, encounter_data: dict[str, Any]) -> Decimal:
        """Calculate payer margin percentage."""
        estimated_cost = Decimal(str(encounter_data.get("estimated_cost", 1000)))
        estimated_revenue = Decimal(str(encounter_data.get("estimated_revenue", 1500)))

        if estimated_revenue == 0:
            return Decimal("0.0")

        margin = ((estimated_revenue - estimated_cost) / estimated_revenue) * 100
        return margin

    def _calculate_priority_score(
        self,
        revenue: Decimal,
        complexity: Decimal,
        margin: Decimal,
        revenue_threshold: Decimal,
    ) -> Decimal:
        """Calculate overall priority score."""
        # Weighted scoring
        revenue_score = min((revenue / revenue_threshold) * 40, Decimal("40.0"))
        complexity_score = (complexity / 100) * Decimal("30.0")
        margin_score = min((margin / 50) * 30, Decimal("30.0"))

        return revenue_score + complexity_score + margin_score

    def _determine_priority_tier(self, score: Decimal) -> str:
        """Determine priority tier based on score."""
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "HIGH"
        elif score >= 40:
            return "MEDIUM"
        else:
            return "LOW"

    def _identify_risk_factors(
        self, encounter_data: dict[str, Any], complexity: Decimal, margin: Decimal
    ) -> list[str]:
        """Identify risk factors requiring attention."""
        risks = []

        if complexity > 80:
            risks.append(_("Complexidade clínica muito alta"))

        if margin < 10:
            risks.append(_("Margem da operadora baixa"))

        if encounter_data.get("length_of_stay", 0) > 10:
            risks.append(_("Internação prolongada"))

        if encounter_data.get("pending_authorizations", 0) > 0:
            risks.append(_("Autorizações pendentes"))

        if encounter_data.get("payer") == "SUS":
            risks.append(_("Reembolso SUS - processamento prioritário"))

        return risks

    def _recommend_actions(
        self, tier: str, risks: list[str], encounter_data: dict[str, Any]
    ) -> list[str]:
        """Recommend actions based on priority and risks."""
        actions = []

        if tier in ["CRITICAL", "HIGH"]:
            actions.append(_("Processar com prioridade máxima"))
            actions.append(_("Revisar codificação antes do faturamento"))

        if _("Autorizações pendentes") in risks:
            actions.append(_("Acelerar aprovação de autorizações"))

        if _("Margem da operadora baixa") in risks:
            actions.append(_("Revisar glosas potenciais"))
            actions.append(_("Validar tabela de preços"))

        if encounter_data.get("icu_admission"):
            actions.append(_("Verificar diárias de UTI e materiais especiais"))

        if not actions:
            actions.append(_("Processar no fluxo padrão"))

        return actions

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: PrioritizeHighValueCasesInput
    ) -> PrioritizeHighValueCasesOutput:
        """Execute case prioritization."""
        tenant_id = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='accred/comp_accred_004',
                inputs={'case_type': input_data.case_type},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        logger.info(
            "Prioritizing high-value cases",
            extra={
                "tenant_id": tenant_id,
                "case_count": len(input_data.encounter_ids),
            },
        )

        with prioritization_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                prioritized_cases: list[CasePriority] = []
                tier_counts: dict[str, int] = {}

                for encounter_id in input_data.encounter_ids[: input_data.max_cases]:
                    # Simulate encounter data retrieval
                    encounter_data = {
                        "encounter_id": encounter_id,
                        "patient_id": f"PAT-{encounter_id[-6:]}",
                        "estimated_revenue": float(
                            Decimal("1000") + (Decimal(encounter_id[-2:]) * 200)
                        ),
                        "estimated_cost": float(
                            Decimal("700") + (Decimal(encounter_id[-2:]) * 100)
                        ),
                        "comorbidities": ["HAS", "DM"] if int(encounter_id[-1]) % 2 == 0 else [],
                        "length_of_stay": int(encounter_id[-1]) if int(encounter_id[-1]) > 0 else 1,
                        "icu_admission": int(encounter_id[-1]) > 7,
                        "procedures": ["PROC1", "PROC2"] if int(encounter_id[-1]) > 5 else ["PROC1"],
                        "payer": "UNIMED" if int(encounter_id[-1]) % 3 == 0 else "AMIL",
                        "pending_authorizations": 1 if int(encounter_id[-1]) % 5 == 0 else 0,
                    }

                    revenue = Decimal(str(encounter_data["estimated_revenue"]))
                    complexity = (
                        self._calculate_complexity_score(encounter_data)
                        if input_data.include_complexity
                        else None
                    )
                    margin = (
                        self._calculate_payer_margin(encounter_data)
                        if input_data.include_payer_margin
                        else None
                    )

                    priority_score = self._calculate_priority_score(
                        revenue,
                        complexity or Decimal("50.0"),
                        margin or Decimal("20.0"),
                        input_data.revenue_threshold,
                    )

                    tier = self._determine_priority_tier(priority_score)
                    tier_counts[tier] = tier_counts.get(tier, 0) + 1

                    risks = self._identify_risk_factors(
                        encounter_data, complexity or Decimal("50.0"), margin or Decimal("20.0")
                    )
                    actions = self._recommend_actions(tier, risks, encounter_data)

                    case_priority = CasePriority(
                        encounter_id=encounter_id,
                        patient_id_hash=self._hash_patient_id(
                            encounter_data["patient_id"]
                        ),
                        priority_score=priority_score,
                        priority_tier=tier,
                        estimated_revenue=revenue,
                        complexity_score=complexity,
                        payer_margin=margin,
                        risk_factors=risks,
                        recommended_actions=actions,
                    )
                    prioritized_cases.append(case_priority)

                    prioritizations_total.labels(
                        tenant_id=tenant_id, priority_tier=tier
                    ).inc()

                # Sort by priority score descending
                prioritized_cases.sort(key=lambda x: x.priority_score, reverse=True)

                total_revenue = sum(c.estimated_revenue for c in prioritized_cases)

                result = PrioritizeHighValueCasesOutput(
                    prioritized_cases=prioritized_cases,
                    total_cases_analyzed=len(prioritized_cases),
                    critical_cases=tier_counts.get("CRITICAL", 0)
                    + tier_counts.get("HIGH", 0),
                    total_estimated_revenue=total_revenue,
                    prioritization_timestamp=datetime.now(),
                    analysis_criteria={
                        "revenue_threshold": str(input_data.revenue_threshold),
                        "include_complexity": input_data.include_complexity,
                        "include_payer_margin": input_data.include_payer_margin,
                        "tier_distribution": tier_counts,
                    },
                )

                logger.info(
                    "Case prioritization completed",
                    extra={
                        "tenant_id": tenant_id,
                        "cases_analyzed": result.total_cases_analyzed,
                        "critical_cases": result.critical_cases,
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Case prioritization failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise CasePrioritizationError(
                    _("Falha ao priorizar casos de alto valor"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "prioritize-high-value-cases"
