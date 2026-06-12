"""Validate procedure compatibility rules.

CIB7 External Task Topic: production.validate_compatibility
BPMN Error Codes: INCOMPATIBLE_CODES, CODING_ERROR
"""
from __future__ import annotations

from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import CodingException, IncompatibleCodes
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

# Incompatibility matrix: code pairs that cannot coexist on same date
_INCOMPATIBLE_PAIRS: set[frozenset[str]] = {
    frozenset({"40101010", "40101028"}),  # Office visit vs telemedicine
    frozenset({"40201010", "40201028"}),  # Specialist vs follow-up same day
    frozenset({"10101012", "10101039"}),  # Duplicate consultation types
}

# Frequency limits: (code, max_per_period, period_days)
_FREQUENCY_LIMITS: dict[str, tuple[int, int]] = {
    "40101010": (4, 1),    # Max 4 office visits per day
    "40201010": (2, 1),    # Max 2 specialist consults per day
    "40301010": (1, 30),   # Max 1 comprehensive exam per 30 days
    "41301011": (12, 365), # Max 12 therapy sessions per year
}

# Gender restrictions: code -> allowed genders
_GENDER_RESTRICTIONS: dict[str, set[str]] = {
    "40601013": {"female"},  # Obstetric procedures
    "40601021": {"female"},  # Gynecological procedures
    "40501020": {"male"},    # Prostate procedures
}

# Age restrictions: code -> (min_age, max_age) or None for unrestricted
_AGE_RESTRICTIONS: dict[str, tuple[int | None, int | None]] = {
    "40401010": (0, 18),     # Pediatric procedures
    "40401028": (65, None),  # Geriatric screening
}


class ValidateCompatibilityWorker:
    """Validates procedure compatibility and business rules.

    Checks:
    - Mutually exclusive procedure pairs (INCOMPATIBLE_CODES)
    - Frequency limits per time period
    - Gender restrictions
    - Age restrictions
    - Same-date conflicts
    """

    TOPIC = "production.validate_compatibility"

    def __init__(self) -> None:
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    def _evaluate_pricing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate pricing DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='pricing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @require_tenant
    @track_task_execution(metric_name="production_validate_compatibility")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Validate procedure compatibility.

        Task Variables (input):
            priced_procedures: list[dict] - Procedures with prices
            patient_gender: str | None - Patient gender code
            patient_age_years: int | None - Patient age in years

        Returns:
            compatible_procedures: list[dict] - Validated procedures
            compatibility_warnings: list[str] - Non-blocking warnings
            all_compatible: bool - Whether all checks passed
        """
        ctx = get_required_tenant()
        procedures: list[dict[str, Any]] = task_variables.get("priced_procedures", [])
        patient_gender: str | None = task_variables.get("patient_gender")
        patient_age: int | None = task_variables.get("patient_age_years")

        self._logger.info(
            "validating_compatibility",
            procedure_count=len(procedures),
            tenant_id=ctx.tenant_id,
        )

        warnings: list[str] = []
        codes = [p.get("code", "") for p in procedures]

        # 1. Check incompatible pairs
        for i, code1 in enumerate(codes):
            for code2 in codes[i + 1:]:
                pair = frozenset({code1, code2})
                if pair in _INCOMPATIBLE_PAIRS:
                    raise IncompatibleCodes(
                        _("Incompatible procedures detected: {code1} and {code2}").format(
                            code1=code1, code2=code2
                        ),
                        details={"code1": code1, "code2": code2},
                    )

        # 2. Check frequency limits
        code_counts: dict[str, int] = {}
        for code in codes:
            code_counts[code] = code_counts.get(code, 0) + 1

        for code, count in code_counts.items():
            if code in _FREQUENCY_LIMITS:
                max_qty, period = _FREQUENCY_LIMITS[code]
                if count > max_qty:
                    raise IncompatibleCodes(
                        _("Procedure {code} exceeds frequency limit: {limit} per {period}").format(
                            code=code, limit=max_qty, period=f"{period} days"
                        ),
                        details={
                            "code": code,
                            "count": count,
                            "limit": max_qty,
                            "period_days": period,
                        },
                    )

        # 3. Gender restrictions
        if patient_gender:
            for code in codes:
                allowed = _GENDER_RESTRICTIONS.get(code)
                if allowed and patient_gender.lower() not in allowed:
                    raise IncompatibleCodes(
                        _("Gender restriction violated for procedure {code}").format(code=code),
                        details={
                            "code": code,
                            "patient_gender": patient_gender,
                            "allowed_genders": list(allowed),
                        },
                    )

        # 4. Age restrictions
        if patient_age is not None:
            for code in codes:
                age_range = _AGE_RESTRICTIONS.get(code)
                if age_range:
                    min_age, max_age = age_range
                    if min_age is not None and patient_age < min_age:
                        raise IncompatibleCodes(
                            _("Age restriction violated for procedure {code}").format(code=code),
                            details={
                                "code": code,
                                "patient_age": patient_age,
                                "min_age": min_age,
                            },
                        )
                    if max_age is not None and patient_age > max_age:
                        raise IncompatibleCodes(
                            _("Age restriction violated for procedure {code}").format(code=code),
                            details={
                                "code": code,
                                "patient_age": patient_age,
                                "max_age": max_age,
                            },
                        )

        # 5. Duplicate detection warning
        for code, count in code_counts.items():
            if count > 1:
                warnings.append(
                    f"Procedure {code} appears {count} times - verify intentional"
                )

        self._logger.info(
            "compatibility_validated",
            procedure_count=len(procedures),
            warning_count=len(warnings),
            tenant_id=ctx.tenant_id,
        )

        return {
            "compatible_procedures": procedures,
            "compatibility_warnings": warnings,
            "all_compatible": True,
        }
