"""
Worker para identificação de oportunidades de codificação compliant.

Analisa documentação clínica para procedimentos sub-codificados e sugere
upgrades TUSS/CBHPM baseados em complexidade documentada, mantendo
conformidade com normas ANS.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
coding_analyses_total = Counter(
    "coding_analyses_total",
    "Total de análises de codificação realizadas",
    ["tenant_id", "procedure_type", "result"],
)
coding_duration_seconds = Histogram(
    "coding_duration_seconds",
    "Duração das análises de codificação em segundos",
    ["tenant_id"],
)
opportunities_found_gauge = Gauge(
    "coding_opportunities_found",
    "Número de oportunidades de codificação identificadas",
    ["tenant_id", "opportunity_type"],
)


class CodingOpportunityAnalysisError(DomainException):
    """    Exceção para erros na análise de oportunidades de codificação.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="CODING_OPPORTUNITY_ANALYSIS_ERROR",
            bpmn_error_code="CodingOpportunityAnalysisError",
            details=details or {},
        )


class IdentifyCodingOpportunitiesInput(BaseModel):
    """Input para identificação de oportunidades de codificação."""

    encounter_id: str = Field(description=_("ID do atendimento FHIR"))
    patient_id: str = Field(description=_("ID do paciente"))
    current_procedure_codes: list[str] = Field(
        description=_("Códigos TUSS/CBHPM atuais")
    )
    clinical_documentation: dict[str, Any] = Field(
        description=_("Documentação clínica completa")
    )
    provider_id: str = Field(description=_("ID do prestador"))
    analysis_depth: str = Field(
        default="standard", description=_("Profundidade da análise: basic, standard, deep")
    )


class CodingOpportunity(BaseModel):
    """Modelo de oportunidade de codificação identificada."""

    current_code: str = Field(description=_("Código atual"))
    suggested_code: str = Field(description=_("Código sugerido"))
    confidence_score: Decimal = Field(description=_("Score de confiança 0-1"))
    revenue_impact: Decimal = Field(description=_("Impacto financeiro estimado em R$"))
    justification: str = Field(description=_("Justificativa clínica"))
    documentation_evidence: list[str] = Field(
        description=_("Evidências na documentação")
    )
    compliance_notes: str = Field(description=_("Notas de conformidade ANS"))
    risk_level: str = Field(description=_("Nível de risco: low, medium, high"))


class IdentifyCodingOpportunitiesOutput(BaseModel):
    """Output da identificação de oportunidades de codificação."""

    analysis_id: str = Field(description=_("ID da análise"))
    encounter_id: str = Field(description=_("ID do atendimento"))
    opportunities: list[CodingOpportunity] = Field(
        description=_("Oportunidades identificadas")
    )
    total_potential_revenue: Decimal = Field(
        description=_("Receita potencial total em R$")
    )
    analysis_timestamp: datetime = Field(description=_("Timestamp da análise"))
    compliance_summary: dict[str, Any] = Field(
        description=_("Sumário de conformidade")
    )
    recommendations: list[str] = Field(description=_("Recomendações adicionais"))
    analyzed_at: datetime


class IdentifyCodingOpportunitiesProtocol(ABC):
    """Protocolo para identificação de oportunidades de codificação."""

    @abstractmethod
    async def execute(
        self, input_data: IdentifyCodingOpportunitiesInput
    ) -> IdentifyCodingOpportunitiesOutput:
        """Executa identificação de oportunidades de codificação."""
        pass


class IdentifyCodingOpportunitiesStub(IdentifyCodingOpportunitiesProtocol):
    """Implementação stub para identificação de oportunidades de codificação."""

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        ans_client: ANSClientProtocol,
    ):
        self.fhir_client = fhir_client
        self.ans_client = ans_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: IdentifyCodingOpportunitiesInput
    ) -> IdentifyCodingOpportunitiesOutput:
        """
        Executa identificação de oportunidades de codificação.

        Analisa documentação clínica contra códigos atuais, identifica
        sub-codificação, valida conformidade ANS.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='tiss/comp_tiss_005',
                inputs={'encounter_id': input_data.encounter_id},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        analysis_id = self._generate_analysis_id(input_data.encounter_id)

        logger.info(
            "Iniciando análise de codificação",
            extra={
                "tenant_id": tenant.tenant_id,
                "encounter_id": input_data.encounter_id,
                "analysis_id": analysis_id,
            },
        )

        with coding_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                # Buscar dados clínicos FHIR
                encounter = await self._fetch_encounter(input_data.encounter_id)
                procedures = await self._fetch_procedures(input_data.encounter_id)

                # Analisar documentação clínica
                complexity_analysis = self._analyze_clinical_complexity(
                    input_data.clinical_documentation
                )

                # Identificar oportunidades
                opportunities = await self._identify_opportunities(
                    current_codes=input_data.current_procedure_codes,
                    complexity=complexity_analysis,
                    clinical_doc=input_data.clinical_documentation,
                    encounter=encounter,
                )

                # Validar conformidade ANS
                compliance_summary = await self._validate_ans_compliance(
                    opportunities=opportunities,
                    provider_id=input_data.provider_id,
                )

                # Calcular impacto financeiro
                total_revenue = sum(opp.revenue_impact for opp in opportunities)

                # Gerar recomendações
                recommendations = self._generate_recommendations(
                    opportunities=opportunities,
                    compliance=compliance_summary,
                )

                # Atualizar métricas
                coding_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    procedure_type="all",
                    result="success",
                ).inc()

                for opp in opportunities:
                    opportunities_found_gauge.labels(
                        tenant_id=tenant.tenant_id,
                        opportunity_type=opp.risk_level,
                    ).set(len(opportunities))

                logger.info(
                    "Análise de codificação concluída",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "opportunities_count": len(opportunities),
                        "total_revenue": float(total_revenue),
                    },
                )

                return IdentifyCodingOpportunitiesOutput(
                    analysis_id=analysis_id,
                    encounter_id=input_data.encounter_id,
                    opportunities=opportunities,
                    total_potential_revenue=total_revenue,
                    analysis_timestamp=datetime.now(),
                    compliance_summary=compliance_summary,
                    recommendations=recommendations,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                coding_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    procedure_type="all",
                    result="error",
                ).inc()
                logger.error(
                    "Erro na análise de codificação",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                )
                raise CodingOpportunityAnalysisError(
                    message=_("Erro ao analisar oportunidades de codificação"),
                    details={
                        "analysis_id": analysis_id,
                        "encounter_id": input_data.encounter_id,
                        "error": str(e),
                    },
                )

    def _generate_analysis_id(self, encounter_id: str) -> str:
        """Gera ID único para análise."""
        hash_input = f"{encounter_id}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _fetch_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Busca dados do atendimento no FHIR."""
        return {"id": encounter_id, "status": "finished"}

    async def _fetch_procedures(self, encounter_id: str) -> list[dict[str, Any]]:
        """Busca procedimentos realizados."""
        return [{"code": "10101012", "description": "Consulta médica"}]

    def _analyze_clinical_complexity(
        self, clinical_doc: dict[str, Any]
    ) -> dict[str, Any]:
        """Analisa complexidade clínica da documentação."""
        return {
            "complexity_score": Decimal("0.75"),
            "comorbidities": 2,
            "procedures_performed": 3,
            "time_spent_minutes": 45,
            "documentation_quality": "high",
        }

    async def _identify_opportunities(
        self,
        current_codes: list[str],
        complexity: dict[str, Any],
        clinical_doc: dict[str, Any],
        encounter: dict[str, Any],
    ) -> list[CodingOpportunity]:
        """Identifica oportunidades de upgrade de código."""
        opportunities = []

        # Exemplo: consulta pode ser upgradada baseado em complexidade
        if "10101012" in current_codes and complexity["complexity_score"] > Decimal(
            "0.7"
        ):
            opportunities.append(
                CodingOpportunity(
                    current_code="10101012",
                    suggested_code="10101039",
                    confidence_score=Decimal("0.85"),
                    revenue_impact=Decimal("150.00"),
                    justification=_(
                        "Complexidade clínica documentada justifica consulta de alto nível"
                    ),
                    documentation_evidence=[
                        "Comorbidades múltiplas documentadas",
                        "Tempo de atendimento > 40 minutos",
                        "Procedimentos adicionais realizados",
                    ],
                    compliance_notes=_("Conformidade ANS RN 465/2021 verificada"),
                    risk_level="low",
                )
            )

        return opportunities

    async def _validate_ans_compliance(
        self, opportunities: list[CodingOpportunity], provider_id: str
    ) -> dict[str, Any]:
        """Valida conformidade ANS para oportunidades."""
        return {
            "compliant": True,
            "validation_date": datetime.now().isoformat(),
            "ans_rules_checked": ["RN_465_2021", "RN_439_2018"],
            "warnings": [],
            "provider_accredited": True,
        }

    def _generate_recommendations(
        self,
        opportunities: list[CodingOpportunity],
        compliance: dict[str, Any],
    ) -> list[str]:
        """Gera recomendações adicionais."""
        recommendations = []

        if len(opportunities) > 0:
            recommendations.append(
                _("Revisar documentação clínica para suportar códigos sugeridos")
            )

        high_risk = [o for o in opportunities if o.risk_level == "high"]
        if high_risk:
            recommendations.append(
                _(
                    "Oportunidades de alto risco requerem validação por auditor médico"
                )
            )

        if not compliance.get("compliant", False):
            recommendations.append(_("Resolver questões de conformidade ANS antes de aplicar"))

        return recommendations


# Task topic para Camunda
TOPIC = "platform.identify_coding_opportunities"
