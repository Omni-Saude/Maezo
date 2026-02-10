"""DDI Integration Service - Aggregates multiple DMN evaluations for drug-drug interactions.

Checks all medication pairs against DDI category DMN tables (bleeding risk,
hepatotoxicity, nephrotoxicity, QT prolongation, contraindications, major/moderate
severity, serotonin syndrome) and returns aggregated findings with severity ranking.

Author: CIB7 Platform Team
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

# Patient context fields forwarded to DMN evaluation inputs
_PATIENT_CONTEXT_KEYS = frozenset(
    {"age", "renal_function", "hepatic_function", "weight_kg"}
)

# DDI severity categories matching DMN subcategories under clinical_safety/ddi/
DDI_CATEGORIES: list[str] = [
    "bleed",
    "hepato",
    "nephro",
    "qt",
    "contraind",
    "major",
    "moderate",
    "serotonin",
]

# Severity ranking (lower index = higher severity)
_SEVERITY_ORDER: list[str] = [
    "CONTRAINDICATED",
    "MAJOR",
    "MODERATE",
    "MINOR",
    "NONE",
]


@dataclass
class DDIResult:
    """Aggregated result of drug-drug interaction checks."""

    has_interactions: bool
    interactions: List[Dict[str, Any]] = field(default_factory=list)
    highest_severity: str = "NONE"
    categories_triggered: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class DDIService:
    """Aggregates multiple DDI DMN table evaluations for a medication list.

    For each unique pair of medications the service evaluates every DMN table
    in every DDI category directory and collects matching interactions.  Results
    are aggregated into a single :class:`DDIResult` with the highest severity
    and all triggered categories.
    """

    def __init__(self, dmn_service: Optional[FederatedDMNService] = None) -> None:
        self._dmn = dmn_service or get_dmn_service()
        self._dmn_base: Path = (
            Path(__file__).resolve().parent.parent / "dmn" / "clinical_safety" / "ddi"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_drug_drug_interactions(
        self,
        medications: List[str],
        patient_context: Optional[Dict[str, Any]] = None,
    ) -> DDIResult:
        """Check all drug pairs against all DDI DMN categories.

        Args:
            medications: List of medication names (case-insensitive).
            patient_context: Optional dict with keys such as ``age``,
                ``renal_function``, ``hepatic_function``, ``weight_kg``.

        Returns:
            :class:`DDIResult` with aggregated findings across all categories.
        """
        tenant_id = get_required_tenant().tenant_id
        patient_ctx = patient_context or {}

        all_interactions: list[Dict[str, Any]] = []
        categories_triggered: set[str] = set()
        recommendations: list[str] = []

        # Check each unique pair of medications
        for i, drug1 in enumerate(medications):
            for drug2 in medications[i + 1 :]:
                pair_results = self._check_pair(
                    tenant_id, drug1.upper(), drug2.upper(), patient_ctx
                )
                for result in pair_results:
                    all_interactions.append(result)
                    categories_triggered.add(result["category"])
                    rec = result.get("recommendation")
                    if rec:
                        recommendations.append(rec)

        highest = self._highest_severity(all_interactions)

        return DDIResult(
            has_interactions=len(all_interactions) > 0,
            interactions=all_interactions,
            highest_severity=highest,
            categories_triggered=sorted(categories_triggered),
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_pair(
        self,
        tenant_id: str,
        drug1: str,
        drug2: str,
        patient_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Evaluate a single drug pair against every DDI category."""
        results: list[Dict[str, Any]] = []

        for category in DDI_CATEGORIES:
            category_dir = self._dmn_base / category
            if not category_dir.exists():
                continue

            dmn_files = sorted(category_dir.glob("ddi_*.dmn"))
            for dmn_file in dmn_files:
                table_name = f"ddi/{category}/{dmn_file.stem}"
                try:
                    inputs: Dict[str, Any] = {
                        "drug_1": drug1,
                        "drug_2": drug2,
                        **{
                            k: v
                            for k, v in patient_context.items()
                            if k in _PATIENT_CONTEXT_KEYS
                        },
                    }
                    result = self._dmn.evaluate(
                        tenant_id=tenant_id,
                        category="clinical_safety",
                        table_name=table_name,
                        inputs=inputs,
                    )
                    if not result:
                        continue

                    base = {
                        "drug_1": drug1,
                        "drug_2": drug2,
                        "category": category.upper(),
                        "table": dmn_file.stem,
                    }

                    # COLLECT hit policy returns {"results": [...], "count": N}
                    if "results" in result:
                        for r in result["results"]:
                            results.append({**base, **r})
                    else:
                        results.append({**base, **result})

                except (FileNotFoundError, ValueError):
                    # No matching rule for this drug pair in this table
                    continue
                except Exception:
                    logger.warning(
                        "ddi_evaluation_error",
                        table=table_name,
                        drug_1=drug1,
                        drug_2=drug2,
                        exc_info=True,
                    )
                    continue

        return results

    @staticmethod
    def _highest_severity(interactions: List[Dict[str, Any]]) -> str:
        """Determine the highest severity across all interactions."""
        highest = "NONE"
        for interaction in interactions:
            sev = interaction.get("severity", "NONE").upper()
            if sev in _SEVERITY_ORDER:
                if _SEVERITY_ORDER.index(sev) < _SEVERITY_ORDER.index(highest):
                    highest = sev
        return highest
