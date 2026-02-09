"""
DMN Service for Hospital Revenue Cycle.

Provides DMN decision evaluation with support for:
- Zeebe REST API integration
- Python fallback implementations
- Retry and error handling

This is the Python equivalent of the Java DMN evaluation service.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx
import structlog

from revenue_cycle.services.dmn.billing_calculation_dmn import BillingCalculationDMN

logger = structlog.get_logger(__name__)


class DMNEvaluationError(Exception):
    """Exception raised when DMN evaluation fails."""

    def __init__(
        self,
        message: str,
        decision_key: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        self.message = message
        self.decision_key = decision_key
        self.original_error = original_error
        super().__init__(message)


class DMNService(ABC):
    """
    Abstract DMN evaluation service.

    Defines the contract for DMN decision evaluation.
    """

    @abstractmethod
    async def evaluate(
        self,
        decision_key: str,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate a DMN decision.

        Args:
            decision_key: DMN decision key
            variables: Input variables for the decision

        Returns:
            Dictionary with decision outputs

        Raises:
            DMNEvaluationError: If evaluation fails
        """
        ...


class ZeebeDMNService(DMNService):
    """
    Zeebe-based DMN evaluation via REST API.

    Evaluates DMN decisions deployed to Camunda 8 via the Zeebe REST API.
    """

    def __init__(
        self,
        zeebe_rest_url: str,
        timeout: int = 5,
        auth_token: Optional[str] = None,
    ):
        """
        Initialize Zeebe DMN service.

        Args:
            zeebe_rest_url: Base URL for Zeebe REST API
            timeout: Request timeout in seconds
            auth_token: Optional authentication token
        """
        self.base_url = zeebe_rest_url.rstrip("/")
        self.timeout = timeout
        self.auth_token = auth_token
        self._logger = logger.bind(service="ZeebeDMNService")

    async def evaluate(
        self,
        decision_key: str,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate DMN decision via Zeebe REST API.

        Args:
            decision_key: DMN decision key
            variables: Input variables

        Returns:
            Decision outputs

        Raises:
            DMNEvaluationError: If evaluation fails
        """
        self._logger.debug(
            "Evaluating DMN decision via Zeebe",
            decision_key=decision_key,
            variables=variables,
        )

        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v2/decision-definitions/key/{decision_key}/evaluation",
                    json={"variables": variables},
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()

                self._logger.debug(
                    "DMN evaluation response",
                    decision_key=decision_key,
                    response=result,
                )

                # Extract outputs from Zeebe DMN response
                if result.get("evaluatedDecisions"):
                    outputs = result["evaluatedDecisions"][0].get("output", {})
                    self._logger.info(
                        "DMN decision evaluated successfully",
                        decision_key=decision_key,
                        outputs=outputs,
                    )
                    return outputs

                self._logger.warning(
                    "DMN evaluation returned empty result",
                    decision_key=decision_key,
                )
                return {}

        except httpx.HTTPStatusError as e:
            self._logger.error(
                "DMN HTTP error",
                decision_key=decision_key,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise DMNEvaluationError(
                f"DMN HTTP error: {e.response.status_code}",
                decision_key=decision_key,
                original_error=e,
            )
        except httpx.RequestError as e:
            self._logger.error(
                "DMN request error",
                decision_key=decision_key,
                error=str(e),
            )
            raise DMNEvaluationError(
                f"DMN request failed: {e}",
                decision_key=decision_key,
                original_error=e,
            )
        except Exception as e:
            self._logger.error(
                "DMN evaluation error",
                decision_key=decision_key,
                error=str(e),
            )
            raise DMNEvaluationError(
                f"DMN evaluation failed: {e}",
                decision_key=decision_key,
                original_error=e,
            )


class FallbackDMNService(DMNService):
    """
    Fallback DMN evaluation using Python implementations.

    Used when Zeebe DMN service is unavailable.
    """

    def __init__(self):
        """Initialize fallback DMN service with Python implementations."""
        self.billing_dmn = BillingCalculationDMN()
        self._logger = logger.bind(service="FallbackDMNService")

    async def evaluate(
        self,
        decision_key: str,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate using Python DMN implementation.

        Args:
            decision_key: DMN decision key
            variables: Input variables

        Returns:
            Decision outputs

        Raises:
            DMNEvaluationError: If decision key is unknown
        """
        self._logger.debug(
            "Evaluating DMN decision via Python fallback",
            decision_key=decision_key,
            variables=variables,
        )

        if decision_key == "billing-calculation":
            result = self.billing_dmn.evaluate(
                procedure_type=variables.get("procedureType", "CLINICAL"),
                insurance_table=variables.get("insuranceTable", "CUSTOM"),
                base_value=variables.get("baseValue", 0.0),
                has_glosa=variables.get("hasGlosa", False),
                glosa_percentage=variables.get("glosaPercentage", 0.0),
            )
            self._logger.info(
                "Python fallback DMN evaluated",
                decision_key=decision_key,
                rule=result["calculationRule"],
            )
            return result

        self._logger.error(
            "Unknown DMN decision key",
            decision_key=decision_key,
        )
        raise DMNEvaluationError(
            f"Unknown decision key: {decision_key}",
            decision_key=decision_key,
        )


class HybridDMNService(DMNService):
    """
    Hybrid DMN service with automatic fallback.

    Attempts to use Zeebe DMN service first, falls back to Python
    implementation on failure.
    """

    def __init__(
        self,
        zeebe_service: Optional[ZeebeDMNService] = None,
        fallback_service: Optional[FallbackDMNService] = None,
    ):
        """
        Initialize hybrid DMN service.

        Args:
            zeebe_service: Optional Zeebe DMN service
            fallback_service: Optional fallback service
        """
        self.zeebe_service = zeebe_service
        self.fallback_service = fallback_service or FallbackDMNService()
        self._logger = logger.bind(service="HybridDMNService")

    async def evaluate(
        self,
        decision_key: str,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate DMN with automatic fallback.

        Tries Zeebe first, falls back to Python on failure.

        Args:
            decision_key: DMN decision key
            variables: Input variables

        Returns:
            Decision outputs
        """
        # Try Zeebe first if available
        if self.zeebe_service:
            try:
                return await self.zeebe_service.evaluate(decision_key, variables)
            except DMNEvaluationError as e:
                self._logger.warning(
                    "Zeebe DMN failed, using fallback",
                    decision_key=decision_key,
                    error=str(e),
                )

        # Use fallback
        return await self.fallback_service.evaluate(decision_key, variables)
