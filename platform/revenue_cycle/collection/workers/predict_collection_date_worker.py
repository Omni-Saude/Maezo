from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import numpy as np
from sklearn.linear_model import LinearRegression

from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class PredictCollectionDateWorker:
    """Prediz data esperada de cobrança usando regressão linear baseada em histórico."""

    WORKER_TYPE = "predict_collection_date"

    @track_task_execution(metric_name="predict_collection_date")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Prediz data esperada de cobrança usando ML (regressão linear baseline).

        Args:
            task_variables: {
                "claim_id": str,
                "payer_id": str,
                "claim_amount": float,
                "claim_date": str (ISO format),
                "claim_type": str (optional),
                "historical_data": list (optional, for training - [{days, amount}, ...])
            }

        Returns:
            {
                "claim_id": str,
                "predicted_collection_date": str,
                "predicted_days": int,
                "confidence": float,
                "model_type": str,
                "historical_samples": int
            }
        """
        claim_id = task_variables["claim_id"]
        payer_id = task_variables["payer_id"]
        claim_amount = Decimal(str(task_variables["claim_amount"]))
        claim_date = date.fromisoformat(task_variables["claim_date"])
        claim_type = task_variables.get("claim_type", "standard")

        logger.info(
            _("Predizendo data de cobrança"),
            extra={
                "claim_id": claim_id,
                "payer_id": payer_id,
                "claim_amount": float(claim_amount),
            },
        )

        # Get historical data for this payer
        historical_data = task_variables.get("historical_data")
        if not historical_data:
            # Mock historical data - in real implementation, query from database
            historical_data = [
                {"days": 45, "amount": 25000.00},
                {"days": 52, "amount": 38000.00},
                {"days": 38, "amount": 15000.00},
                {"days": 61, "amount": 55000.00},
                {"days": 48, "amount": 32000.00},
                {"days": 55, "amount": 42000.00},
                {"days": 43, "amount": 28000.00},
                {"days": 58, "amount": 48000.00},
            ]

        if len(historical_data) < 3:
            # Not enough data for ML - use simple average
            avg_days = int(np.mean([d["days"] for d in historical_data])) if historical_data else 60
            predicted_days = avg_days
            confidence = 0.5
            model_type = "average"
            logger.warning(
                _("Dados históricos insuficientes para ML - usando média"),
                extra={"historical_samples": len(historical_data)},
            )
        else:
            # Train simple linear regression model
            X = np.array([[d["amount"]] for d in historical_data])
            y = np.array([d["days"] for d in historical_data])

            model = LinearRegression()
            model.fit(X, y)

            # Predict for current claim
            predicted_days = int(model.predict([[float(claim_amount)]])[0])

            # Calculate confidence based on R² score
            confidence = float(model.score(X, y))
            model_type = "linear_regression"

        # Ensure predicted_days is reasonable (30-180 days)
        predicted_days = max(30, min(predicted_days, 180))

        predicted_collection_date = claim_date + timedelta(days=predicted_days)

        logger.info(
            _("Previsão de cobrança concluída"),
            extra={
                "claim_id": claim_id,
                "predicted_days": predicted_days,
                "predicted_date": predicted_collection_date.isoformat(),
                "confidence": confidence,
                "model_type": model_type,
            },
        )

        return {
            "claim_id": claim_id,
            "payer_id": payer_id,
            "predicted_collection_date": predicted_collection_date.isoformat(),
            "predicted_days": predicted_days,
            "confidence": confidence,
            "model_type": model_type,
            "historical_samples": len(historical_data),
            "claim_date": claim_date.isoformat(),
            "claim_amount": float(claim_amount),
        }
