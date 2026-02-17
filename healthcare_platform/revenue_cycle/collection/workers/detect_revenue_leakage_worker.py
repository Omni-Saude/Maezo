"""Worker for detecting revenue leakage opportunities."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class RevenueLeakage(BaseModel):
    """    Oportunidade de recuperação de receita.
    
        Archetype: FINANCIAL_CALCULATION
        """

    category: str
    description: str
    amount: float
    count: int
    priority: str


class DetectRevenueLeakageWorker:
    """Identifica vazamentos de receita (revenue leakage)."""

    WORKER_TYPE = "detect_revenue_leakage"

    def __init__(self, tasy_api_client=None) -> None:
        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)
        self._tasy_api_client = tasy_api_client

    def _evaluate_cash_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate cash_operations DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id='default',
                category='cash_operations',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @track_task_execution(metric_name="detect_revenue_leakage")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Identifica oportunidades de recuperação de receita.

        Args:
            task_variables: {
                "unbilled_encounters": list[dict],
                "undercoded_procedures": list[dict],
                "uncollected_approvals": list[dict],
                "expired_authorizations": list[dict]
            }

        Returns:
            {
                "leakages": list[RevenueLeakage],
                "total_potential_recovery": float,
                "total_opportunities": int,
                "by_category": dict[str, float]
            }
        """
        # Try to get revenue leakage from TASY API if available
        if self._tasy_api_client:
            try:
                from datetime import datetime, timedelta
                today = date.today()
                date_from = (today - timedelta(days=30)).isoformat()
                date_to = today.isoformat()

                tasy_leakage = await self._tasy_api_client.get_revenue_leakage(
                    date_from=date_from,
                    date_to=date_to,
                )

                # Convert TASY leakage to internal format
                leakages = []
                by_category = {}

                if "unbilled_encounters" in tasy_leakage:
                    ub = tasy_leakage["unbilled_encounters"]
                    amount = Decimal(str(ub.get("amount", 0)))
                    leakages.append(
                        RevenueLeakage(
                            category="unbilled_encounters",
                            description=_("Atendimentos realizados mas não faturados"),
                            amount=float(amount),
                            count=ub.get("count", 0),
                            priority="high" if amount > 10000 else "medium",
                        )
                    )
                    by_category["unbilled_encounters"] = amount

                if "undercoded_procedures" in tasy_leakage:
                    uc = tasy_leakage["undercoded_procedures"]
                    amount = Decimal(str(uc.get("amount", 0)))
                    leakages.append(
                        RevenueLeakage(
                            category="undercoded_procedures",
                            description=_("Procedimentos com codificação abaixo do adequado"),
                            amount=float(amount),
                            count=uc.get("count", 0),
                            priority="medium",
                        )
                    )
                    by_category["undercoded_procedures"] = amount

                if "uncollected_approvals" in tasy_leakage:
                    ua = tasy_leakage["uncollected_approvals"]
                    amount = Decimal(str(ua.get("amount", 0)))
                    leakages.append(
                        RevenueLeakage(
                            category="uncollected_approvals",
                            description=_("Autorizações aprovadas mas não cobradas"),
                            amount=float(amount),
                            count=ua.get("count", 0),
                            priority="high",
                        )
                    )
                    by_category["uncollected_approvals"] = amount

                if "expired_authorizations" in tasy_leakage:
                    ea = tasy_leakage["expired_authorizations"]
                    amount = Decimal(str(ea.get("amount", 0)))
                    leakages.append(
                        RevenueLeakage(
                            category="expired_authorizations",
                            description=_("Autorizações expiradas antes da cobrança"),
                            amount=float(amount),
                            count=ea.get("count", 0),
                            priority="critical",
                        )
                    )
                    by_category["expired_authorizations"] = amount

                total_potential_recovery = sum(by_category.values())
                total_opportunities = sum(leak.count for leak in leakages)

                self._logger.info("Using TASY revenue leakage data", total=float(total_potential_recovery))

                return {
                    "leakages": [leak.model_dump() for leak in leakages],
                    "total_potential_recovery": float(total_potential_recovery),
                    "total_opportunities": total_opportunities,
                    "by_category": {k: float(v) for k, v in by_category.items()},
                    "source": "tasy",
                }
            except Exception as e:
                self._logger.warning("Failed to get TASY revenue leakage, using fallback", error=str(e))

        # Fallback to task variables
        unbilled = task_variables.get("unbilled_encounters", [])
        undercoded = task_variables.get("undercoded_procedures", [])
        uncollected = task_variables.get("uncollected_approvals", [])
        expired = task_variables.get("expired_authorizations", [])

        logger.info(
            _("Detectando vazamentos de receita"),
            extra={
                "unbilled_count": len(unbilled),
                "undercoded_count": len(undercoded),
                "uncollected_count": len(uncollected),
                "expired_count": len(expired),
            },
        )

        leakages: list[RevenueLeakage] = []
        by_category: dict[str, Decimal] = {}

        # Unbilled encounters
        if unbilled:
            amount = sum(
                Decimal(str(e.get("estimated_value", 0))) for e in unbilled
            )
            leakages.append(
                RevenueLeakage(
                    category="unbilled_encounters",
                    description=_(
                        "Atendimentos realizados mas não faturados"
                    ),
                    amount=float(amount),
                    count=len(unbilled),
                    priority="high" if amount > 10000 else "medium",
                )
            )
            by_category["unbilled_encounters"] = amount

        # Undercoded procedures
        if undercoded:
            amount = sum(
                Decimal(str(p.get("potential_increase", 0))) for p in undercoded
            )
            leakages.append(
                RevenueLeakage(
                    category="undercoded_procedures",
                    description=_(
                        "Procedimentos com codificação abaixo do adequado"
                    ),
                    amount=float(amount),
                    count=len(undercoded),
                    priority="medium",
                )
            )
            by_category["undercoded_procedures"] = amount

        # Uncollected approvals
        if uncollected:
            amount = sum(
                Decimal(str(a.get("approved_amount", 0))) for a in uncollected
            )
            leakages.append(
                RevenueLeakage(
                    category="uncollected_approvals",
                    description=_(
                        "Autorizações aprovadas mas não cobradas"
                    ),
                    amount=float(amount),
                    count=len(uncollected),
                    priority="high",
                )
            )
            by_category["uncollected_approvals"] = amount

        # Expired authorizations
        if expired:
            amount = sum(
                Decimal(str(a.get("authorized_amount", 0))) for a in expired
            )
            leakages.append(
                RevenueLeakage(
                    category="expired_authorizations",
                    description=_(
                        "Autorizações expiradas antes da cobrança"
                    ),
                    amount=float(amount),
                    count=len(expired),
                    priority="critical",
                )
            )
            by_category["expired_authorizations"] = amount

        total_potential_recovery = sum(by_category.values())
        total_opportunities = sum(leak.count for leak in leakages)

        logger.info(
            _("Detecção de vazamentos concluída"),
            extra={
                "total_potential_recovery": float(total_potential_recovery),
                "total_opportunities": total_opportunities,
                "categories": len(leakages),
            },
        )

        return {
            "leakages": [leak.model_dump() for leak in leakages],
            "total_potential_recovery": float(total_potential_recovery),
            "total_opportunities": total_opportunities,
            "by_category": {k: float(v) for k, v in by_category.items()},
        }
