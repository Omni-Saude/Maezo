"""
Worker para sugestão de melhorias em documentação clínica.

Identifica gaps em prontuários médicos que afetam acurácia de codificação
e sugere adições específicas para melhorar documentação.

Archetype: DATA_ENRICHMENT
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
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
doc_analyses_total = Counter(
    "doc_analyses_total",
    "Total de análises de documentação realizadas",
    ["tenant_id", "document_type", "result"],
)
doc_duration_seconds = Histogram(
    "doc_duration_seconds",
    "Duração das análises de documentação em segundos",
    ["tenant_id"],
)
suggestions_gauge = Gauge(
    "doc_suggestions_found",
    "Número de sugestões de documentação geradas",
    ["tenant_id", "priority"],
)


class DocumentationImprovementError(DomainException):
    """Exceção para erros na análise de documentação."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="DOCUMENTATION_IMPROVEMENT_ERROR",
            bpmn_error_code="DocumentationImprovementError",
            details=details or {},
        )


class SuggestDocumentationImprovementsInput(BaseModel):
    """Input para sugestões de melhorias em documentação."""

    encounter_id: str = Field(description=_("ID do atendimento FHIR"))
    patient_id: str = Field(description=_("ID do paciente"))
    clinical_documentation: dict[str, Any] = Field(
        description=_("Documentação clínica atual")
    )
    procedure_codes: list[str] = Field(description=_("Códigos de procedimentos"))
    provider_specialty: str = Field(description=_("Especialidade do prestador"))
    analysis_focus: str = Field(
        default="coding_accuracy",
        description=_("Foco: coding_accuracy, compliance, quality_metrics"),
    )


class DocumentationSuggestion(BaseModel):
    """Modelo de sugestão de melhoria em documentação."""

    category: str = Field(description=_("Categoria: missing, incomplete, ambiguous"))
    priority: str = Field(description=_("Prioridade: high, medium, low"))
    section: str = Field(description=_("Seção do prontuário"))
    current_content: str = Field(description=_("Conteúdo atual"))
    suggested_addition: str = Field(description=_("Adição sugerida"))
    rationale: str = Field(description=_("Justificativa clínica"))
    impact_on_coding: str = Field(description=_("Impacto na codificação"))
    compliance_requirement: bool = Field(
        description=_("Requerido para conformidade")
    )
    example_template: str = Field(description=_("Exemplo de texto adequado"))


class SuggestDocumentationImprovementsOutput(BaseModel):
    """Output das sugestões de melhoria em documentação."""

    analysis_id: str = Field(description=_("ID da análise"))
    encounter_id: str = Field(description=_("ID do atendimento"))
    suggestions: list[DocumentationSuggestion] = Field(
        description=_("Sugestões de melhoria")
    )
    completeness_score: Decimal = Field(
        description=_("Score de completude 0-1 da documentação atual")
    )
    quality_metrics: dict[str, Any] = Field(description=_("Métricas de qualidade"))
    high_priority_count: int = Field(description=_("Número de itens de alta prioridade"))
    estimated_revenue_impact: Decimal = Field(
        description=_("Impacto estimado em receita com melhorias")
    )
    analyzed_at: datetime


class SuggestDocumentationImprovementsProtocol(ABC):
    """Protocolo para sugestões de melhorias em documentação."""

    @abstractmethod
    async def execute(
        self, input_data: SuggestDocumentationImprovementsInput
    ) -> SuggestDocumentationImprovementsOutput:
        """Executa análise e sugestões de documentação."""
        pass


class SuggestDocumentationImprovementsStub(SuggestDocumentationImprovementsProtocol):
    """Implementação stub para sugestões de melhoria em documentação."""

    def __init__(self, fhir_client: FHIRClientProtocol):
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: SuggestDocumentationImprovementsInput
    ) -> SuggestDocumentationImprovementsOutput:
        """
        Executa análise de documentação e gera sugestões.

        Identifica gaps críticos, avalia completude, sugere melhorias
        específicas para acurácia de codificação.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='documentation/cross_comp_001',
                inputs={'document_type': input_data.document_type},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        analysis_id = self._generate_analysis_id(input_data.encounter_id)

        logger.info(
            "Iniciando análise de documentação",
            extra={
                "tenant_id": tenant.tenant_id,
                "encounter_id": input_data.encounter_id,
                "analysis_id": analysis_id,
            },
        )

        with doc_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                # Avaliar completude da documentação
                completeness = self._assess_completeness(
                    input_data.clinical_documentation,
                    input_data.procedure_codes,
                    input_data.provider_specialty,
                )

                # Identificar gaps
                suggestions = self._identify_documentation_gaps(
                    clinical_doc=input_data.clinical_documentation,
                    procedures=input_data.procedure_codes,
                    specialty=input_data.provider_specialty,
                    focus=input_data.analysis_focus,
                )

                # Calcular métricas de qualidade
                quality_metrics = self._calculate_quality_metrics(
                    documentation=input_data.clinical_documentation,
                    suggestions=suggestions,
                )

                # Contar prioridades
                high_priority = sum(1 for s in suggestions if s.priority == "high")

                # Estimar impacto na receita
                revenue_impact = self._estimate_revenue_impact(
                    suggestions=suggestions,
                    procedures=input_data.procedure_codes,
                )

                # Atualizar métricas
                doc_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    document_type="clinical",
                    result="success",
                ).inc()

                for priority in ["high", "medium", "low"]:
                    count = sum(1 for s in suggestions if s.priority == priority)
                    suggestions_gauge.labels(
                        tenant_id=tenant.tenant_id, priority=priority
                    ).set(count)

                logger.info(
                    "Análise de documentação concluída",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "suggestions_count": len(suggestions),
                        "high_priority": high_priority,
                    },
                )

                return SuggestDocumentationImprovementsOutput(
                    analysis_id=analysis_id,
                    encounter_id=input_data.encounter_id,
                    suggestions=suggestions,
                    completeness_score=completeness,
                    quality_metrics=quality_metrics,
                    high_priority_count=high_priority,
                    estimated_revenue_impact=revenue_impact,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                doc_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    document_type="clinical",
                    result="error",
                ).inc()
                logger.error(
                    "Erro na análise de documentação",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                )
                raise DocumentationImprovementError(
                    message=_("Erro ao analisar documentação clínica"),
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

    def _assess_completeness(
        self, clinical_doc: dict[str, Any], procedures: list[str], specialty: str
    ) -> Decimal:
        """Avalia completude da documentação."""
        required_sections = [
            "chief_complaint",
            "history",
            "physical_exam",
            "assessment",
            "plan",
        ]
        present_sections = sum(
            1 for section in required_sections if clinical_doc.get(section)
        )
        return Decimal(str(present_sections / len(required_sections)))

    def _identify_documentation_gaps(
        self,
        clinical_doc: dict[str, Any],
        procedures: list[str],
        specialty: str,
        focus: str,
    ) -> list[DocumentationSuggestion]:
        """Identifica gaps na documentação."""
        suggestions = []

        # Gap: Falta de documentação de comorbidades
        if not clinical_doc.get("comorbidities"):
            suggestions.append(
                DocumentationSuggestion(
                    category="missing",
                    priority="high",
                    section="history",
                    current_content=_("Sem documentação de comorbidades"),
                    suggested_addition=_(
                        "Documentar presença/ausência de comorbidades relevantes"
                    ),
                    rationale=_(
                        "Comorbidades afetam complexidade e codificação do atendimento"
                    ),
                    impact_on_coding=_("Pode elevar nível de codificação em até 20%"),
                    compliance_requirement=True,
                    example_template=_(
                        "Paciente apresenta: [HAS controlada, DM tipo 2, dislipidemia]"
                    ),
                )
            )

        # Gap: Tempo de atendimento não documentado
        if not clinical_doc.get("consultation_duration"):
            suggestions.append(
                DocumentationSuggestion(
                    category="missing",
                    priority="medium",
                    section="metadata",
                    current_content=_("Duração do atendimento não registrada"),
                    suggested_addition=_(
                        "Registrar tempo total de atendimento em minutos"
                    ),
                    rationale=_("Tempo justifica nível de consulta e codificação"),
                    impact_on_coding=_("Essencial para consultas de nível 4-5"),
                    compliance_requirement=False,
                    example_template=_("Duração total: 45 minutos"),
                )
            )

        # Gap: Exame físico incompleto
        if clinical_doc.get("physical_exam") == "NAD":
            suggestions.append(
                DocumentationSuggestion(
                    category="incomplete",
                    priority="high",
                    section="physical_exam",
                    current_content="NAD (Nada de Anormal Detectado)",
                    suggested_addition=_(
                        "Detalhar sistemas examinados e achados específicos"
                    ),
                    rationale=_(
                        "Exame físico detalhado suporta nível de complexidade"
                    ),
                    impact_on_coding=_(
                        "Documentação adequada pode aumentar reembolso em R$ 100-200"
                    ),
                    compliance_requirement=True,
                    example_template=_(
                        "CV: BNF 2T, sem sopros. Resp: MV+ bilateralmente, sem RA. Abd: RHA+, indolor, sem massas."
                    ),
                )
            )

        return suggestions

    def _calculate_quality_metrics(
        self, documentation: dict[str, Any], suggestions: list[DocumentationSuggestion]
    ) -> dict[str, Any]:
        """Calcula métricas de qualidade."""
        return {
            "total_sections": 5,
            "complete_sections": 3,
            "completeness_percentage": 60.0,
            "critical_gaps": sum(
                1 for s in suggestions if s.compliance_requirement
            ),
            "average_section_quality": 0.72,
            "coding_accuracy_risk": "medium",
        }

    def _estimate_revenue_impact(
        self, suggestions: list[DocumentationSuggestion], procedures: list[str]
    ) -> Decimal:
        """Estima impacto financeiro das melhorias."""
        base_impact = Decimal("50.00")
        high_priority_bonus = sum(
            Decimal("75.00") for s in suggestions if s.priority == "high"
        )
        return base_impact + high_priority_bonus


# Task topic para Camunda
TOPIC = "platform.suggest_documentation_improvements"
