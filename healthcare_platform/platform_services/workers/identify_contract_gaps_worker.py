"""
Worker para identificação de gaps contratuais.

Analisa contratos com operadoras para identificar procedimentos não cobertos,
termos desfavoráveis, emendas perdidas e contratos expirando.

Archetype: COMPLIANCE_VALIDATION
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
contract_analyses_total = Counter(
    "contract_analyses_total",
    "Total de análises de contrato realizadas",
    ["tenant_id", "contract_type", "result"],
)
contract_duration_seconds = Histogram(
    "contract_duration_seconds",
    "Duração das análises de contrato em segundos",
    ["tenant_id"],
)
gaps_found_gauge = Gauge(
    "contract_gaps_found",
    "Número de gaps contratuais identificados",
    ["tenant_id", "gap_type"],
)


class ContractGapAnalysisError(DomainException):
    """Exceção para erros na análise de gaps contratuais."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="CONTRACT_GAP_ANALYSIS_ERROR",
            bpmn_error_code="ContractGapAnalysisError",
            details=details or {},
        )


class IdentifyContractGapsInput(BaseModel):
    """Input para identificação de gaps contratuais."""

    contract_id: str = Field(description=_("ID do contrato"))
    payer_id: str = Field(description=_("ID da operadora"))
    include_procedure_coverage: bool = Field(
        default=True, description=_("Analisar cobertura de procedimentos")
    )
    include_term_analysis: bool = Field(
        default=True, description=_("Analisar termos contratuais")
    )
    include_expiration_check: bool = Field(
        default=True, description=_("Verificar proximidade de expiração")
    )
    expiration_warning_days: int = Field(
        default=90, description=_("Dias de antecedência para alerta de expiração")
    )


class ContractGap(BaseModel):
    """Modelo de gap contratual identificado."""

    gap_type: str = Field(
        description=_(
            "Tipo: uncovered_procedure, unfavorable_term, missing_amendment, expiring"
        )
    )
    severity: str = Field(description=_("Severidade: critical, high, medium, low"))
    title: str = Field(description=_("Título do gap"))
    description: str = Field(description=_("Descrição detalhada"))
    impact: str = Field(description=_("Impacto para o negócio"))
    estimated_annual_impact: Decimal = Field(
        description=_("Impacto financeiro anual estimado em R$")
    )
    affected_items: list[str] = Field(
        description=_("Itens afetados: procedimentos, cláusulas, etc")
    )
    recommendation: str = Field(description=_("Recomendação de ação"))
    action_deadline: datetime | None = Field(
        default=None, description=_("Prazo para ação")
    )


class IdentifyContractGapsOutput(BaseModel):
    """Output da identificação de gaps contratuais."""

    analysis_id: str = Field(description=_("ID da análise"))
    contract_id: str = Field(description=_("ID do contrato"))
    payer_name: str = Field(description=_("Nome da operadora"))
    contract_start_date: datetime = Field(description=_("Data de início do contrato"))
    contract_end_date: datetime = Field(description=_("Data de fim do contrato"))
    days_until_expiration: int = Field(description=_("Dias até expiração"))
    gaps: list[ContractGap] = Field(description=_("Gaps identificados"))
    critical_gaps_count: int = Field(description=_("Número de gaps críticos"))
    total_estimated_impact: Decimal = Field(
        description=_("Impacto total estimado anual em R$")
    )
    contract_health_score: Decimal = Field(
        description=_("Score de saúde do contrato 0-1")
    )
    priority_actions: list[str] = Field(description=_("Ações prioritárias"))
    analyzed_at: datetime


class IdentifyContractGapsProtocol(ABC):
    """Protocolo para identificação de gaps contratuais."""

    @abstractmethod
    async def execute(
        self, input_data: IdentifyContractGapsInput
    ) -> IdentifyContractGapsOutput:
        """Executa identificação de gaps contratuais."""
        pass


class IdentifyContractGapsStub(IdentifyContractGapsProtocol):
    """Implementação stub para identificação de gaps contratuais."""

    def __init__(self, ans_client: ANSClientProtocol):
        self.ans_client = ans_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: IdentifyContractGapsInput
    ) -> IdentifyContractGapsOutput:
        """
        Executa identificação de gaps contratuais.

        Analisa cobertura de procedimentos, termos contratuais,
        emendas, prazos de expiração e identifica riscos.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='tiss/comp_tiss_002',
                inputs={'payer_code': input_data.payer_code},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        analysis_id = self._generate_analysis_id(input_data.contract_id)

        logger.info(
            "Iniciando análise de gaps contratuais",
            extra={
                "tenant_id": tenant.tenant_id,
                "contract_id": input_data.contract_id,
                "analysis_id": analysis_id,
            },
        )

        with contract_duration_seconds.labels(tenant_id=tenant.tenant_id).time():
            try:
                # Buscar dados do contrato
                contract = await self._fetch_contract_details(
                    input_data.contract_id, input_data.payer_id
                )

                gaps: list[ContractGap] = []

                # Analisar cobertura de procedimentos
                if input_data.include_procedure_coverage:
                    coverage_gaps = await self._analyze_procedure_coverage(contract)
                    gaps.extend(coverage_gaps)

                # Analisar termos contratuais
                if input_data.include_term_analysis:
                    term_gaps = self._analyze_contract_terms(contract)
                    gaps.extend(term_gaps)

                # Verificar expiração
                if input_data.include_expiration_check:
                    expiration_gaps = self._check_expiration(
                        contract, input_data.expiration_warning_days
                    )
                    gaps.extend(expiration_gaps)

                # Calcular métricas
                critical_count = sum(1 for g in gaps if g.severity == "critical")
                total_impact = sum(g.estimated_annual_impact for g in gaps)

                # Score de saúde do contrato
                health_score = self._calculate_health_score(gaps, contract)

                # Calcular dias até expiração
                days_until_exp = (
                    contract["end_date"] - datetime.now()
                ).days

                # Gerar ações prioritárias
                priority_actions = self._generate_priority_actions(gaps)

                # Atualizar métricas
                contract_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    contract_type="health_insurance",
                    result="success",
                ).inc()

                gap_types = ["uncovered_procedure", "unfavorable_term", "expiring"]
                for gap_type in gap_types:
                    count = sum(1 for g in gaps if g.gap_type == gap_type)
                    gaps_found_gauge.labels(
                        tenant_id=tenant.tenant_id, gap_type=gap_type
                    ).set(count)

                logger.info(
                    "Análise de gaps contratuais concluída",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "gaps_count": len(gaps),
                        "critical_count": critical_count,
                    },
                )

                return IdentifyContractGapsOutput(
                    analysis_id=analysis_id,
                    contract_id=input_data.contract_id,
                    payer_name=contract["payer_name"],
                    contract_start_date=contract["start_date"],
                    contract_end_date=contract["end_date"],
                    days_until_expiration=days_until_exp,
                    gaps=gaps,
                    critical_gaps_count=critical_count,
                    total_estimated_impact=total_impact,
                    contract_health_score=health_score,
                    priority_actions=priority_actions,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                contract_analyses_total.labels(
                    tenant_id=tenant.tenant_id,
                    contract_type="health_insurance",
                    result="error",
                ).inc()
                logger.error(
                    "Erro na análise de gaps contratuais",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "analysis_id": analysis_id,
                        "error": str(e),
                    },
                )
                raise ContractGapAnalysisError(
                    message=_("Erro ao analisar gaps contratuais"),
                    details={
                        "analysis_id": analysis_id,
                        "contract_id": input_data.contract_id,
                        "error": str(e),
                    },
                )

    def _generate_analysis_id(self, contract_id: str) -> str:
        """Gera ID único para análise."""
        hash_input = f"{contract_id}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _fetch_contract_details(
        self, contract_id: str, payer_id: str
    ) -> dict[str, Any]:
        """Busca detalhes do contrato."""
        return {
            "contract_id": contract_id,
            "payer_id": payer_id,
            "payer_name": "Operadora ABC",
            "start_date": datetime.now() - timedelta(days=730),
            "end_date": datetime.now() + timedelta(days=60),
            "covered_procedures": ["10101012", "20101020"],
            "payment_terms": {"days": 60, "penalties": "2% ao mês"},
            "readjustment_clause": "IPCA anual",
        }

    async def _analyze_procedure_coverage(
        self, contract: dict[str, Any]
    ) -> list[ContractGap]:
        """Analisa cobertura de procedimentos."""
        gaps = []

        # Simula procedimentos realizados mas não cobertos
        uncovered = ["30101015", "40101018"]

        for proc_code in uncovered:
            gaps.append(
                ContractGap(
                    gap_type="uncovered_procedure",
                    severity="high",
                    title=_("Procedimento não coberto pelo contrato"),
                    description=_(
                        "Procedimento {code} realizado regularmente mas sem cobertura contratual"
                    ).format(code=proc_code),
                    impact=_(
                        "Receita perdida ou necessidade de negociação caso a caso"
                    ),
                    estimated_annual_impact=Decimal("45000.00"),
                    affected_items=[proc_code],
                    recommendation=_(
                        "Solicitar adendo contratual para inclusão do procedimento"
                    ),
                    action_deadline=datetime.now() + timedelta(days=30),
                )
            )

        return gaps

    def _analyze_contract_terms(
        self, contract: dict[str, Any]
    ) -> list[ContractGap]:
        """Analisa termos contratuais."""
        gaps = []

        # Prazo de pagamento desfavorável
        payment_days = contract.get("payment_terms", {}).get("days", 0)
        if payment_days > 45:
            gaps.append(
                ContractGap(
                    gap_type="unfavorable_term",
                    severity="medium",
                    title=_("Prazo de pagamento desfavorável"),
                    description=_(
                        "Prazo de {days} dias excede padrão de mercado (30-45 dias)"
                    ).format(days=payment_days),
                    impact=_("Impacto no fluxo de caixa e capital de giro"),
                    estimated_annual_impact=Decimal("15000.00"),
                    affected_items=["payment_terms"],
                    recommendation=_(
                        "Negociar redução para 45 dias ou desconto por antecipação"
                    ),
                    action_deadline=None,
                )
            )

        # Reajuste inadequado
        readjustment = contract.get("readjustment_clause", "")
        if "IPCA" in readjustment:
            gaps.append(
                ContractGap(
                    gap_type="unfavorable_term",
                    severity="medium",
                    title=_("Cláusula de reajuste inadequada"),
                    description=_(
                        "Reajuste por IPCA não acompanha custos médicos (VCMH)"
                    ),
                    impact=_("Erosão de margem ao longo do tempo"),
                    estimated_annual_impact=Decimal("25000.00"),
                    affected_items=["readjustment_clause"],
                    recommendation=_(
                        "Negociar mudança para VCMH ou IPCA + percentual fixo"
                    ),
                    action_deadline=None,
                )
            )

        return gaps

    def _check_expiration(
        self, contract: dict[str, Any], warning_days: int
    ) -> list[ContractGap]:
        """Verifica proximidade de expiração."""
        gaps = []

        end_date = contract["end_date"]
        days_until = (end_date - datetime.now()).days

        if days_until <= warning_days:
            severity = "critical" if days_until <= 30 else "high"
            gaps.append(
                ContractGap(
                    gap_type="expiring",
                    severity=severity,
                    title=_("Contrato próximo de expiração"),
                    description=_(
                        "Contrato expira em {days} dias - ação urgente necessária"
                    ).format(days=days_until),
                    impact=_(
                        "Risco de interrupção de atendimento ou renovação desfavorável"
                    ),
                    estimated_annual_impact=Decimal("0.00"),
                    affected_items=["contract_expiration"],
                    recommendation=_(
                        "Iniciar processo de renovação/renegociação imediatamente"
                    ),
                    action_deadline=end_date - timedelta(days=30),
                )
            )

        return gaps

    def _calculate_health_score(
        self, gaps: list[ContractGap], contract: dict[str, Any]
    ) -> Decimal:
        """Calcula score de saúde do contrato."""
        base_score = Decimal("1.0")

        # Penalizar por gaps
        critical_gaps = sum(1 for g in gaps if g.severity == "critical")
        high_gaps = sum(1 for g in gaps if g.severity == "high")

        penalty = (critical_gaps * Decimal("0.15")) + (high_gaps * Decimal("0.08"))
        score = max(Decimal("0"), base_score - penalty)

        return score

    def _generate_priority_actions(
        self, gaps: list[ContractGap]
    ) -> list[str]:
        """Gera lista de ações prioritárias."""
        actions = []

        critical = [g for g in gaps if g.severity == "critical"]
        if critical:
            actions.append(
                _(
                    "URGENTE: Resolver {count} gap(s) crítico(s) imediatamente"
                ).format(count=len(critical))
            )

        expiring = [g for g in gaps if g.gap_type == "expiring"]
        if expiring:
            actions.append(_("Iniciar processo de renovação/renegociação contratual"))

        uncovered = [g for g in gaps if g.gap_type == "uncovered_procedure"]
        if uncovered:
            actions.append(
                _(
                    "Solicitar adendos para inclusão de {count} procedimento(s) não coberto(s)"
                ).format(count=len(uncovered))
            )

        return actions


# Task topic para Camunda
TOPIC = "platform.identify_contract_gaps"
