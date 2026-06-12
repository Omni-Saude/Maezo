"""Apply DMN coding rules to validated procedure/diagnosis codes.

CIB7 External Task Topic: apply-coding-rules
BPMN Error Codes: CODING_RULE_VIOLATION, CODING_ERROR

Phase 2.2 - Coding & Audit: evaluates coding business rules via a DMN
decision table.  Rules cover quantity limits, bundling, modifier
requirements, and specialty restrictions.  The DMN engine is abstracted
behind a Protocol so the stub can be swapped for the real Camunda DMN
integration in Phase 6.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Enums ─────────────────────────────────────────────────────────────


class RuleSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# ── Data Transfer Objects ─────────────────────────────────────────────


class ApplyCodingRulesInput(BaseModel):
    """Variables consumed from the BPMN process."""

    validated_cid10: list[str] = Field(..., alias="validatedCid10", min_length=1)
    validated_tuss: list[str] = Field(..., alias="validatedTuss", min_length=1)
    encounter_class: str = Field(..., alias="encounterClass")
    encounter_id: str = Field(..., alias="encounterId")
    tenant_id: str = Field(..., alias="tenantId")


class RuleResultDTO(BaseModel):
    """Single rule evaluation result."""

    rule_id: str = Field(..., alias="ruleId")
    rule_name: str = Field(..., alias="ruleName")
    passed: bool
    message: str
    severity: RuleSeverity


class ApplyCodingRulesOutput(BaseModel):
    """Variables returned to the BPMN process."""

    rules_applied: list[RuleResultDTO] = Field(default_factory=list, alias="rulesApplied")
    rules_passed: bool = Field(True, alias="rulesPassed")
    rule_violations: list[RuleResultDTO] = Field(
        default_factory=list, alias="ruleViolations"
    )
    modifiers_required: list[str] = Field(
        default_factory=list, alias="modifiersRequired"
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "rulesApplied": [r.model_dump(by_alias=True) for r in self.rules_applied],
            "rulesPassed": self.rules_passed,
            "ruleViolations": [
                r.model_dump(by_alias=True) for r in self.rule_violations
            ],
            "modifiersRequired": self.modifiers_required,
        }


# ── Value Objects ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Value object returned by the DMN engine."""

    rule_id: str
    rule_name: str
    passed: bool
    message: str
    severity: str = "INFO"


# ── Protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class DMNRuleEngineProtocol(Protocol):
    """Port: evaluates a named DMN decision table."""

    def evaluate(
        self,
        rule_table: str,
        input_data: dict[str, Any],
    ) -> list[RuleResult]: ...


# ── Hardcoded rule data for the stub ──────────────────────────────────

# TUSS codes that require modifiers
_MODIFIER_REQUIRED_TUSS: dict[str, str] = {
    "30101012": _("Modificador -51 (múltiplos procedimentos)"),
    "40201010": _("Modificador -59 (procedimento distinto)"),
    "40301010": _("Modificador -26 (componente profissional)"),
}

# Maximum quantity per encounter class
_QUANTITY_LIMITS: dict[str, int] = {
    "ambulatorial": 5,
    "internacao": 20,
    "pronto_socorro": 10,
}

# TUSS codes that cannot be billed together (bundling rules)
_BUNDLE_GROUPS: list[set[str]] = [
    {"30101012", "30101020"},  # Consulta simples + detalhada
    {"40201010", "40201028"},  # ECG repouso + esforço
]

# TUSS prefix groups considered surgical
_SURGICAL_PREFIXES: set[str] = {"40", "41", "42"}


# ── Stub Implementation ──────────────────────────────────────────────


class DMNRuleEngineStub:
    """Hardcoded rule results for common scenarios.

    Will be replaced by Camunda DMN REST calls in Phase 6.
    """

    def evaluate(
        self,
        rule_table: str,
        input_data: dict[str, Any],
    ) -> list[RuleResult]:
        results: list[RuleResult] = []
        tuss_codes: list[str] = input_data.get("tuss_codes", [])
        encounter_class: str = input_data.get("encounter_class", "ambulatorial")

        # ── R1: Quantity limit ────────────────────────────────────────
        max_qty = _QUANTITY_LIMITS.get(encounter_class, 10)
        if len(tuss_codes) > max_qty:
            results.append(
                RuleResult(
                    rule_id="RULE-QTY-001",
                    rule_name=_("Limite de quantidade por atendimento"),
                    passed=False,
                    message=_(
                        "Quantidade de procedimentos ({qty}) excede o limite "
                        "de {max} para atendimento {cls}"
                    ).format(qty=len(tuss_codes), max=max_qty, cls=encounter_class),
                    severity="ERROR",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id="RULE-QTY-001",
                    rule_name=_("Limite de quantidade por atendimento"),
                    passed=True,
                    message=_(
                        "Quantidade de procedimentos ({qty}) dentro do limite ({max})"
                    ).format(qty=len(tuss_codes), max=max_qty),
                    severity="INFO",
                )
            )

        # ── R2: Bundling rules ────────────────────────────────────────
        tuss_set = set(tuss_codes)
        bundling_found = False
        for group in _BUNDLE_GROUPS:
            overlap = tuss_set & group
            if len(overlap) > 1:
                bundling_found = True
                codes_str = ", ".join(sorted(overlap))
                results.append(
                    RuleResult(
                        rule_id="RULE-BND-001",
                        rule_name=_("Regra de agrupamento (bundling)"),
                        passed=False,
                        message=_(
                            "Procedimentos {codes} não podem ser cobrados juntos "
                            "no mesmo atendimento (regra de bundling)"
                        ).format(codes=codes_str),
                        severity="ERROR",
                    )
                )
        if not bundling_found:
            results.append(
                RuleResult(
                    rule_id="RULE-BND-001",
                    rule_name=_("Regra de agrupamento (bundling)"),
                    passed=True,
                    message=_("Nenhum conflito de bundling detectado"),
                    severity="INFO",
                )
            )

        # ── R3: Modifier requirements ────────────────────────────────
        for tuss in tuss_codes:
            if tuss in _MODIFIER_REQUIRED_TUSS:
                results.append(
                    RuleResult(
                        rule_id="RULE-MOD-001",
                        rule_name=_("Modificador obrigatório"),
                        passed=False,
                        message=_(
                            "Procedimento {tuss} requer modificador: {mod}"
                        ).format(tuss=tuss, mod=_MODIFIER_REQUIRED_TUSS[tuss]),
                        severity="WARNING",
                    )
                )

        # ── R4: Specialty restriction (ambulatorial only) ─────────────
        if encounter_class == "ambulatorial":
            for tuss in tuss_codes:
                prefix = tuss[:2] if len(tuss) >= 2 else ""
                if prefix in _SURGICAL_PREFIXES:
                    results.append(
                        RuleResult(
                            rule_id="RULE-SPE-001",
                            rule_name=_("Restrição de especialidade"),
                            passed=False,
                            message=_(
                                "Procedimento cirúrgico {tuss} não permitido em "
                                "atendimento ambulatorial sem autorização prévia"
                            ).format(tuss=tuss),
                            severity="ERROR",
                        )
                    )

        return results


# ── Worker ────────────────────────────────────────────────────────────


class ApplyCodingRulesWorker:
    """Evaluates DMN coding rules for quantity, bundling, modifiers, and specialty.

    Uses a pluggable DMNRuleEngine; the default stub provides hardcoded
    rules for development.  Production will call the Camunda DMN REST
    API (Phase 6 integration).
    """

    TOPIC = "apply-coding-rules"
    _DMN_TABLE = "coding-rules-v1"

    def __init__(
        self,
        dmn_engine: DMNRuleEngineProtocol | None = None,
    ) -> None:
        self._dmn = dmn_engine or DMNRuleEngineStub()
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_apply_coding_rules")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute coding rules evaluation.

        Task Variables (input):
            validatedCid10: list[str] - Validated CID-10 codes
            validatedTuss: list[str] - Validated TUSS codes
            encounterClass: str - ambulatorial | internacao | pronto_socorro
            encounterId: str - Encounter identifier
            tenantId: str - Tenant identifier

        Returns:
            rulesApplied: list[dict] - All evaluated rules
            rulesPassed: bool - True if no ERROR-severity failures
            ruleViolations: list[dict] - Failed rules only
            modifiersRequired: list[str] - Modifiers that must be added

        Raises:
            BpmnErrorException (CODING_RULE_VIOLATION): on ERROR-severity failures.
            CodingException: on invalid input.
        """
        ctx = get_required_tenant()

        # ── Parse & validate input ────────────────────────────────────
        validated_cid10: list[str] = task_variables.get("validatedCid10", [])
        validated_tuss: list[str] = task_variables.get("validatedTuss", [])
        encounter_class: str = task_variables.get("encounterClass", "")
        encounter_id: str = task_variables.get("encounterId", "")

        if not validated_cid10 or not validated_tuss:
            raise CodingException(
                _("Entrada inválida para aplicação de regras de codificação: "
                  "códigos CID-10 e TUSS são obrigatórios"),
                bpmn_error_code="CODING_ERROR",
            )
        if not encounter_class:
            raise CodingException(
                _("Entrada inválida para aplicação de regras de codificação: "
                  "classe do atendimento (encounterClass) é obrigatória"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "coding_rules_started",
            encounter_id=encounter_id,
            encounter_class=encounter_class,
            tuss_count=len(validated_tuss),
            cid10_count=len(validated_cid10),
            tenant_id=ctx.tenant_id,
        )

        # DMN-enhanced frequency rules check
        dmn_result = self._evaluate_coding_dmn(
            subcategory="freq",
            table_name="frequency_rules",
            inputs={
                "tuss_codes": validated_tuss,
                "encounter_class": encounter_class
            }
        )

        # ── Evaluate DMN table ────────────────────────────────────────
        dmn_input = {
            "cid10_codes": validated_cid10,
            "tuss_codes": validated_tuss,
            "encounter_class": encounter_class,
        }
        rule_results = self._dmn.evaluate(self._DMN_TABLE, dmn_input)

        # ── Classify results ──────────────────────────────────────────
        applied: list[RuleResultDTO] = []
        violations: list[RuleResultDTO] = []
        modifiers_required: list[str] = []

        for r in rule_results:
            dto = RuleResultDTO(
                ruleId=r.rule_id,
                ruleName=r.rule_name,
                passed=r.passed,
                message=r.message,
                severity=RuleSeverity(r.severity),
            )
            applied.append(dto)

            if not r.passed:
                violations.append(dto)

            # Collect modifier names from WARNING-level modifier rules
            if r.rule_id.startswith("RULE-MOD") and not r.passed:
                if ": " in r.message:
                    modifiers_required.append(r.message.split(": ", 1)[1])

        has_errors = any(v.severity == RuleSeverity.ERROR for v in violations)
        rules_passed = not has_errors

        output = ApplyCodingRulesOutput(
            rulesApplied=applied,
            rulesPassed=rules_passed,
            ruleViolations=violations,
            modifiersRequired=modifiers_required,
        )

        # ── Handle ERROR-severity violations ──────────────────────────
        if has_errors:
            error_count = sum(
                1 for v in violations if v.severity == RuleSeverity.ERROR
            )
            self._logger.error(
                "coding_rule_violations",
                encounter_id=encounter_id,
                violation_count=len(violations),
                error_count=error_count,
                tenant_id=ctx.tenant_id,
            )
            raise BpmnErrorException(
                error_code="CODING_RULE_VIOLATION",
                message=_(
                    "Violação de regras de codificação: {count} erro(s) encontrado(s) "
                    "para o atendimento {enc}"
                ).format(count=error_count, enc=encounter_id),
                details=output.to_variables(),
            )

        if violations:
            self._logger.warning(
                "coding_rule_warnings",
                encounter_id=encounter_id,
                warning_count=len(violations),
                modifiers_required=modifiers_required,
                tenant_id=ctx.tenant_id,
            )

        self._logger.info(
            "coding_rules_passed",
            encounter_id=encounter_id,
            rules_applied_count=len(applied),
            tenant_id=ctx.tenant_id,
        )

        return output.to_variables()


    def _evaluate_coding_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate coding_audit DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='coding_audit',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_worker() -> ApplyCodingRulesWorker:
    """Create and return a configured ApplyCodingRulesWorker instance."""
    return ApplyCodingRulesWorker()

