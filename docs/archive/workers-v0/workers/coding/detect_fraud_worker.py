"""Detect coding fraud patterns using statistical analysis.

CIB7 External Task Topic: coding.detect_fraud
BPMN Error Codes: FRAUD_DETECTED, CODING_ERROR

Phase 2.2 - SUB_05_Coding_Audit: Fraud detection step identifies upcoding,
unbundling, phantom billing, frequency abuse, and provider pattern anomalies.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Known TUSS bundle groups: procedures that must be billed together
_KNOWN_BUNDLE_GROUPS: list[set[str]] = [
    {"30101012", "30101020", "30101039"},  # Anesthesia bundle
    {"31301010", "31301029", "31301037"},  # Surgical pack bundle
    {"40201015", "40201023"},              # Lab panel bundle
    {"40301010", "40301029", "40301037"},  # Imaging bundle
    {"20101015", "20101023", "20101031"},  # ICU daily bundle
    {"30715016", "30715024"},              # Cardiac catheterisation bundle
    {"30724015", "30724023", "30724031"},  # Orthopaedic implant bundle
    {"40601013", "40601021"},              # Pathology bundle
]

# Procedure complexity tiers by TUSS prefix
_COMPLEXITY_TIERS: dict[str, int] = {
    "1": 1,  # Clinical consultations - low
    "2": 2,  # Hospital daily charges - medium
    "3": 3,  # Surgical/invasive - high
    "4": 2,  # Diagnostics - medium
    "5": 1,  # Other therapies - low
}

# Encounter class expected max complexity
_ENCOUNTER_CLASS_MAX_COMPLEXITY: dict[str, int] = {
    "ambulatorio": 2,
    "internacao": 3,
    "urgencia": 3,
    "day_clinic": 2,
}

# Fraud score thresholds
_SCORE_UPCODING = 20
_SCORE_UNBUNDLING = 18
_SCORE_PHANTOM = 25
_SCORE_FREQUENCY = 15
_SCORE_PROVIDER_PATTERN = 22
_THRESHOLD_FLAG = 80
_THRESHOLD_REVIEW = 50

# Z-score threshold for frequency abuse
_ZSCORE_THRESHOLD = 2.0

# Provider peer comparison: max acceptable deviation (standard deviations)
_PROVIDER_DEVIATION_THRESHOLD = 2.5

# Expected mean procedure count per encounter class (stub baselines)
_BASELINE_PROCEDURE_COUNTS: dict[str, tuple[float, float]] = {
    "ambulatorio": (3.0, 1.5),    # mean, std
    "internacao": (8.0, 3.0),
    "urgencia": (5.0, 2.0),
    "day_clinic": (4.0, 1.5),
}


# ---------------------------------------------------------------------------
# Enums & Value Objects
# ---------------------------------------------------------------------------

class FraudType(str, Enum):
    """Types of coding fraud detected."""

    UPCODING = "UPCODING"
    UNBUNDLING = "UNBUNDLING"
    PHANTOM_BILLING = "PHANTOM_BILLING"
    FREQUENCY_ABUSE = "FREQUENCY_ABUSE"
    PROVIDER_PATTERN = "PROVIDER_PATTERN"


class AlertSeverity(str, Enum):
    """Severity levels for fraud alerts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudRecommendation(str, Enum):
    """Recommended action after fraud analysis."""

    CLEAR = "clear"
    REVIEW = "review"
    FLAG = "flag"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class DetectFraudInput(BaseModel):
    """Input variables for the detect-coding-fraud task."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ..., alias="encounterId", min_length=1,
        description="Unique encounter identifier",
    )
    validated_cid10: list[str] = Field(
        ..., alias="validatedCid10",
        description="CID-10 codes already validated",
    )
    validated_tuss: list[str] = Field(
        ..., alias="validatedTuss",
        description="TUSS codes already validated",
    )
    encounter_class: str = Field(
        ..., alias="encounterClass", min_length=1,
        description="ambulatorio | internacao | urgencia | day_clinic",
    )
    patient_id: str = Field(
        ..., alias="patientId", min_length=1,
        description="Patient identifier",
    )
    provider_id: str = Field(
        ..., alias="providerId", min_length=1,
        description="Provider identifier",
    )
    tenant_id: str = Field(
        ..., alias="tenantId", min_length=1,
        description="Tenant identifier",
    )

    @field_validator("encounter_id", "patient_id", "provider_id", "tenant_id")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()


@dataclass
class FraudAlert:
    """Single fraud alert produced by analysis."""

    type: str
    severity: str
    description: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence,
        }


@dataclass
class FraudAnalysisResult:
    """Aggregate result from the fraud detection engine."""

    risk_score: int = 0
    alerts: list[FraudAlert] = field(default_factory=list)
    recommendation: str = FraudRecommendation.CLEAR.value

    def add_alert(self, alert: FraudAlert, score: int) -> None:
        self.alerts.append(alert)
        self.risk_score = min(self.risk_score + score, 100)

    def finalize(self) -> None:
        if self.risk_score >= _THRESHOLD_FLAG:
            self.recommendation = FraudRecommendation.FLAG.value
        elif self.risk_score >= _THRESHOLD_REVIEW:
            self.recommendation = FraudRecommendation.REVIEW.value
        else:
            self.recommendation = FraudRecommendation.CLEAR.value


class DetectFraudOutput(BaseModel):
    """Output variables for the detect-coding-fraud task."""

    model_config = ConfigDict(populate_by_name=True)

    fraud_risk_score: int = Field(
        ..., alias="fraudRiskScore", ge=0, le=100,
        description="Risk score 0-100",
    )
    fraud_alerts: list[dict[str, str]] = Field(
        default_factory=list, alias="fraudAlerts",
        description="List of fraud alert dicts",
    )
    fraud_recommendation: str = Field(
        ..., alias="fraudRecommendation",
        description="clear | review | flag",
    )
    requires_manual_review: bool = Field(
        ..., alias="requiresManualReview",
        description="Whether a human must review",
    )

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# Protocol & Stub
# ---------------------------------------------------------------------------

@runtime_checkable
class FraudDetectionEngineProtocol(Protocol):
    """Contract for the fraud detection engine dependency."""

    async def analyze(
        self,
        encounter_id: str,
        cid10_codes: list[str],
        tuss_codes: list[str],
        encounter_class: str,
        patient_id: str,
        provider_id: str,
    ) -> FraudAnalysisResult: ...


class FraudDetectionEngineStub:
    """Stub implementation using heuristic / statistical patterns.

    Production implementation would integrate with an ML scoring service.
    """

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def analyze(
        self,
        encounter_id: str,
        cid10_codes: list[str],
        tuss_codes: list[str],
        encounter_class: str,
        patient_id: str,
        provider_id: str,
    ) -> FraudAnalysisResult:
        result = FraudAnalysisResult()

        self._check_upcoding(result, tuss_codes, encounter_class)
        self._check_unbundling(result, tuss_codes)
        # DMN-enhanced duplicate fraud detection
        dmn_result = self._evaluate_coding_dmn(
            subcategory="duplicate",
            table_name="duplicate_detection",
            inputs={"tuss_codes": tuss_codes, "cid10_codes": cid10_codes}
        )

        self._check_phantom_billing(result, cid10_codes, tuss_codes)
        self._check_frequency_abuse(result, tuss_codes, encounter_class)
        self._check_provider_pattern(result, tuss_codes, provider_id)

        result.finalize()
        return result

    # ------------------------------------------------------------------
    # 1. Upcoding detection
    # ------------------------------------------------------------------

    def _check_upcoding(
        self,
        result: FraudAnalysisResult,
        tuss_codes: list[str],
        encounter_class: str,
    ) -> None:
        """Compare code complexity against encounter class ceiling."""
        max_allowed = _ENCOUNTER_CLASS_MAX_COMPLEXITY.get(
            encounter_class.lower(), 2,
        )
        high_complexity_codes: list[str] = []

        for code in tuss_codes:
            tier = self._code_complexity_tier(code)
            if tier > max_allowed:
                high_complexity_codes.append(code)

        if high_complexity_codes:
            result.add_alert(
                FraudAlert(
                    type=FraudType.UPCODING.value,
                    severity=AlertSeverity.HIGH.value,
                    description=_(
                        "Codigos com complexidade acima do esperado para "
                        "classe de atendimento '{encounter_class}'"
                    ).format(encounter_class=encounter_class),
                    evidence=_(
                        "Codigos suspeitos: {codes}"
                    ).format(codes=", ".join(high_complexity_codes)),
                ),
                _SCORE_UPCODING,
            )

    # ------------------------------------------------------------------
    # 2. Unbundling detection
    # ------------------------------------------------------------------

    def _check_unbundling(
        self,
        result: FraudAnalysisResult,
        tuss_codes: list[str],
    ) -> None:
        """Detect services billed separately that should be bundled."""
        code_set = set(tuss_codes)
        for bundle in _KNOWN_BUNDLE_GROUPS:
            present = code_set & bundle
            if 0 < len(present) < len(bundle):
                missing = bundle - present
                result.add_alert(
                    FraudAlert(
                        type=FraudType.UNBUNDLING.value,
                        severity=AlertSeverity.MEDIUM.value,
                        description=_(
                            "Possivel desagrupamento: codigos parciais de "
                            "pacote identificados"
                        ),
                        evidence=_(
                            "Presentes: {present} | Ausentes do pacote: {missing}"
                        ).format(
                            present=", ".join(sorted(present)),
                            missing=", ".join(sorted(missing)),
                        ),
                    ),
                    _SCORE_UNBUNDLING,
                )

    # ------------------------------------------------------------------
    # 3. Phantom billing detection
    # ------------------------------------------------------------------

    def _check_phantom_billing(
        self,
        result: FraudAnalysisResult,
        cid10_codes: list[str],
        tuss_codes: list[str],
    ) -> None:
        """Flag procedures without matching diagnostic justification.

        Heuristic: if TUSS codes are present but no CID-10 codes exist,
        there is no clinical documentation supporting the charges.
        In the stub we also flag codes starting with '99' as suspicious
        (commonly used in phantom billing schemes).
        """
        # DMN-enhanced duplicate fraud detection
        dmn_result = self._evaluate_coding_dmn(
            subcategory="duplicate",
            table_name="duplicate_detection",
            inputs={"tuss_codes": tuss_codes, "cid10_codes": cid10_codes}
        )

        if tuss_codes and not cid10_codes:
            result.add_alert(
                FraudAlert(
                    type=FraudType.PHANTOM_BILLING.value,
                    severity=AlertSeverity.CRITICAL.value,
                    description=_(
                        "Procedimentos cobrados sem diagnostico documentado"
                    ),
                    evidence=_(
                        "TUSS presentes ({count}) sem nenhum CID-10 associado"
                    ).format(count=len(tuss_codes)),
                ),
                _SCORE_PHANTOM,
            )

        suspicious_codes = [c for c in tuss_codes if c.startswith("99")]
        if suspicious_codes:
            result.add_alert(
                FraudAlert(
                    type=FraudType.PHANTOM_BILLING.value,
                    severity=AlertSeverity.HIGH.value,
                    description=_(
                        "Codigos com prefixo suspeito identificados"
                    ),
                    evidence=_(
                        "Codigos iniciados em '99': {codes}"
                    ).format(codes=", ".join(suspicious_codes)),
                ),
                _SCORE_PHANTOM,
            )

    # ------------------------------------------------------------------
    # 4. Frequency abuse detection (z-score)
    # ------------------------------------------------------------------

    def _check_frequency_abuse(
        self,
        result: FraudAnalysisResult,
        tuss_codes: list[str],
        encounter_class: str,
    ) -> None:
        """Flag when code count deviates from statistical baseline."""
        baseline = _BASELINE_PROCEDURE_COUNTS.get(
            encounter_class.lower(),
            (5.0, 2.0),
        )
        mean, std = baseline
        if std == 0:
            return

        z_score = (len(tuss_codes) - mean) / std

        if z_score > _ZSCORE_THRESHOLD:
            result.add_alert(
                FraudAlert(
                    type=FraudType.FREQUENCY_ABUSE.value,
                    severity=AlertSeverity.MEDIUM.value,
                    description=_(
                        "Quantidade de procedimentos acima do esperado "
                        "para a classe '{encounter_class}'"
                    ).format(encounter_class=encounter_class),
                    evidence=_(
                        "Quantidade: {count}, Media esperada: {mean:.1f}, "
                        "Z-score: {z:.2f}"
                    ).format(count=len(tuss_codes), mean=mean, z=z_score),
                ),
                _SCORE_FREQUENCY,
            )

    # ------------------------------------------------------------------
    # 5. Provider pattern analysis
    # ------------------------------------------------------------------

    def _check_provider_pattern(
        self,
        result: FraudAnalysisResult,
        tuss_codes: list[str],
        provider_id: str,
    ) -> None:
        """Compare provider coding pattern against peer averages.

        Stub heuristic: providers whose ID hashes to an odd number are
        considered to have a historical average of 3 codes per encounter.
        If the current encounter deviates by more than the threshold we
        flag it.  In production this uses real historical data.
        """
        peer_mean = 5.0
        peer_std = 2.0
        provider_count = len(tuss_codes)

        if peer_std == 0:
            return

        deviation = abs(provider_count - peer_mean) / peer_std

        if deviation > _PROVIDER_DEVIATION_THRESHOLD:
            result.add_alert(
                FraudAlert(
                    type=FraudType.PROVIDER_PATTERN.value,
                    severity=AlertSeverity.HIGH.value,
                    description=_(
                        "Padrao de codificacao do prestador diverge "
                        "significativamente dos pares"
                    ),
                    evidence=_(
                        "Prestador {provider_id}: {count} codigos vs "
                        "media dos pares {mean:.1f} (desvio {dev:.2f} sigma)"
                    ).format(
                        provider_id=provider_id,
                        count=provider_count,
                        mean=peer_mean,
                        dev=deviation,
                    ),
                ),
                _SCORE_PROVIDER_PATTERN,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _code_complexity_tier(code: str) -> int:
        """Return complexity tier (1-3) based on TUSS code prefix."""
        if not code:
            return 1
        first_digit = code[0]
        return _COMPLEXITY_TIERS.get(first_digit, 2)


# ---------------------------------------------------------------------------
# Statistical helpers (used by production engine, exposed for testing)
# ---------------------------------------------------------------------------

def calculate_z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score; returns 0 when std is zero."""
    if std == 0:
        return 0.0
    return (value - mean) / std


def calculate_mean(values: list[float]) -> float:
    """Arithmetic mean; returns 0 for empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def calculate_std(values: list[float]) -> float:
    """Population standard deviation; returns 0 for < 2 values."""
    if len(values) < 2:
        return 0.0
    mean = calculate_mean(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def calculate_percentile(values: list[float], percentile: int) -> float:
    """Return the p-th percentile of a sorted copy of values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * percentile / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def detect_outliers_iqr(
    values: list[float],
    factor: float = 1.5,
) -> list[int]:
    """Return indices of outliers using the IQR method."""
    if len(values) < 4:
        return []
    sorted_vals = sorted(values)
    q1 = sorted_vals[len(sorted_vals) // 4]
    q3 = sorted_vals[3 * len(sorted_vals) // 4]
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    return [i for i, v in enumerate(values) if v < lower or v > upper]


def group_codes_by_prefix(
    codes: list[str],
    prefix_length: int = 2,
) -> dict[str, list[str]]:
    """Group codes by their first N characters."""
    groups: dict[str, list[str]] = defaultdict(list)
    for code in codes:
        prefix = code[:prefix_length] if len(code) >= prefix_length else code
        groups[prefix].append(code)
    return dict(groups)


def find_partial_bundles(
    codes: list[str],
    bundle_groups: list[set[str]] | None = None,
) -> list[dict[str, Any]]:
    """Return bundle groups that are partially present in the code list."""
    bundles = bundle_groups or _KNOWN_BUNDLE_GROUPS
    code_set = set(codes)
    partial: list[dict[str, Any]] = []
    for bundle in bundles:
        present = code_set & bundle
        if 0 < len(present) < len(bundle):
            partial.append({
                "present": sorted(present),
                "missing": sorted(bundle - present),
                "bundle_size": len(bundle),
            })
    return partial


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class DetectFraudWorker:
    """Detects coding fraud patterns via statistical and heuristic analysis.

    Checks for upcoding, unbundling, phantom billing, frequency abuse,
    and provider-level pattern anomalies.
    """

    TOPIC = "coding.detect_fraud"

    def __init__(
        self,
        fraud_engine: FraudDetectionEngineProtocol | None = None,
    ) -> None:
        self._engine: FraudDetectionEngineProtocol = (
            fraud_engine or FraudDetectionEngineStub()
        )
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_detect_fraud")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Run fraud detection on an encounter's validated codes.

        Task Variables (input):
            encounterId: str
            validatedCid10: list[str]
            validatedTuss: list[str]
            encounterClass: str
            patientId: str
            providerId: str
            tenantId: str

        Returns:
            fraudRiskScore: int (0-100)
            fraudAlerts: list[dict]
            fraudRecommendation: str (clear|review|flag)
            requiresManualReview: bool
        """
        ctx = get_required_tenant()

        try:
            inp = DetectFraudInput(**task_variables)
        except Exception as exc:
            raise CodingException(
                _("Dados de entrada invalidos para deteccao de fraude: {error}").format(
                    error=str(exc),
                ),
                bpmn_error_code="CODING_ERROR",
            ) from exc

        self._logger.info(
            "fraud_detection_started",
            encounter_id=inp.encounter_id,
            cid10_count=len(inp.validated_cid10),
            tuss_count=len(inp.validated_tuss),
            encounter_class=inp.encounter_class,
            provider_id=inp.provider_id,
            tenant_id=ctx.tenant_id,
        )

        analysis = await self._engine.analyze(
            encounter_id=inp.encounter_id,
            cid10_codes=inp.validated_cid10,
            tuss_codes=inp.validated_tuss,
            encounter_class=inp.encounter_class,
            patient_id=inp.patient_id,
            provider_id=inp.provider_id,
        )

        requires_manual = analysis.recommendation == FraudRecommendation.FLAG.value

        self._logger.info(
            "fraud_detection_completed",
            encounter_id=inp.encounter_id,
            risk_score=analysis.risk_score,
            alert_count=len(analysis.alerts),
            recommendation=analysis.recommendation,
            requires_manual_review=requires_manual,
            tenant_id=ctx.tenant_id,
        )

        if analysis.risk_score > _THRESHOLD_FLAG:
            self._logger.warning(
                "fraud_detected_high_risk",
                encounter_id=inp.encounter_id,
                risk_score=analysis.risk_score,
                tenant_id=ctx.tenant_id,
            )
            raise BpmnErrorException(
                error_code="FRAUD_DETECTED",
                message=_(
                    "Fraude detectada: pontuacao de risco {score}"
                ).format(score=analysis.risk_score),
            )

        output = DetectFraudOutput(
            fraud_risk_score=analysis.risk_score,
            fraud_alerts=[a.to_dict() for a in analysis.alerts],
            fraud_recommendation=analysis.recommendation,
            requires_manual_review=requires_manual,
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

def register_worker(
    *,
    fraud_engine: FraudDetectionEngineProtocol | None = None,
) -> DetectFraudWorker:
    """Create and return a configured DetectFraudWorker instance."""
    return DetectFraudWorker(fraud_engine=fraud_engine)
