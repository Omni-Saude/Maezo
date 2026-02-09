"""
CollectRPALogsWorker - Zeebe worker for RPA execution logging and analytics.

This worker implements RPA log collection for the Brazilian healthcare revenue cycle:
- RPA (Robotic Process Automation) bot execution logging
- Performance metrics aggregation
- Failure and retry tracking
- Bot health monitoring
- Process completion rate analytics
- RPA activity trend analysis

Business Rule: RPA Operations & Monitoring Standards
Industry Standard: Healthcare RPA Best Practices (UiPath, Blue Prism, Automation Anywhere)
KPI Reference:
  - Bot Success Rate: Target 99%+
  - Average Execution Time: <5 minutes per process
  - Bot Health Score: 95%+ uptime
  - Exception Handling: <1% critical errors
  - Process Completion Rate: 98%+
  - Cost Savings per Transaction: 60-80% vs manual

Migrated from Java CollectRPALogsDelegate.

Topic: collect-rpa-logs
BPMN Task: Task_Collect_RPA_Logs
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from collections import defaultdict

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class RPALogEntry(BaseModel):
    """Model for an RPA log entry."""
    model_config = ConfigDict(populate_by_name=True)

    log_id: str = Field(..., alias="logId")
    bot_name: str = Field(..., alias="botName")
    timestamp: datetime
    log_level: str = Field(..., alias="logLevel")  # ERROR, WARN, INFO, DEBUG
    message: str
    execution_time_ms: int = Field(..., alias="executionTimeMs")
    status: str  # SUCCESS, FAILURE, RETRY, TIMEOUT
    error_code: Optional[str] = Field(None, alias="errorCode")


class BotMetrics(BaseModel):
    """Model for bot performance metrics."""
    model_config = ConfigDict(populate_by_name=True)

    bot_name: str = Field(..., alias="botName")
    execution_count: int = Field(..., alias="executionCount")
    success_count: int = Field(..., alias="successCount")
    failure_count: int = Field(..., alias="failureCount")
    retry_count: int = Field(..., alias="retryCount")
    average_execution_ms: int = Field(..., alias="averageExecutionMs")
    min_execution_ms: int = Field(..., alias="minExecutionMs")
    max_execution_ms: int = Field(..., alias="maxExecutionMs")
    success_rate: Decimal = Field(..., alias="successRate")


class RPALogsInput(BaseModel):
    """Input model for RPA log collection."""
    model_config = ConfigDict(populate_by_name=True)

    rpa_job_id: str = Field(..., alias="rpaJobId")
    facility_id: str = Field(..., alias="facilityId")
    time_window_start: datetime = Field(..., alias="timeWindowStart")
    time_window_end: datetime = Field(..., alias="timeWindowEnd")
    log_level: str = Field(default="INFO", alias="logLevel")
    logs: list[RPALogEntry] = Field(default_factory=list)


class RPALogsOutput(BaseModel):
    """Output model for RPA log collection results."""
    model_config = ConfigDict(populate_by_name=True)

    collection_complete: bool = Field(..., alias="collectionComplete")
    rpa_job_id: str = Field(..., alias="rpaJobId")
    time_window_start: datetime = Field(..., alias="timeWindowStart")
    time_window_end: datetime = Field(..., alias="timeWindowEnd")
    logs_collected: int = Field(..., alias="logsCollected")
    bot_count: int = Field(..., alias="botCount")
    bot_metrics: list[BotMetrics] = Field(..., alias="botMetrics")
    overall_success_rate: Decimal = Field(..., alias="overallSuccessRate")
    total_execution_time_ms: int = Field(..., alias="totalExecutionTimeMs")
    average_execution_time_ms: int = Field(..., alias="averageExecutionTimeMs")
    failure_count: int = Field(..., alias="failureCount")
    retry_count: int = Field(..., alias="retryCount")
    timeout_count: int = Field(..., alias="timeoutCount")
    rpa_status: str = Field(..., alias="rpaStatus")  # HEALTHY, WARNING, ERROR
    error_summary: dict[str, int] = Field(..., alias="errorSummary")
    collection_timestamp: datetime = Field(..., alias="collectionTimestamp")


class RPALogsError(BpmnErrorException):
    """Raised when RPA log collection fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="RPA_LOGS_ERROR",
            message=message,
            details=details,
        )


@worker(topic="collect-rpa-logs", max_jobs=8, lock_duration=60000)
class CollectRPALogsWorker(BaseWorker):
    """
    Zeebe worker for RPA execution logging and analytics.

    This worker:
    1. Aggregates RPA bot execution logs
    2. Calculates bot-level performance metrics
    3. Analyzes failure patterns
    4. Tracks retry behavior
    5. Assesses RPA health status
    6. Generates performance summaries

    Input Variables:
        - rpaJobId: RPA job identifier (required)
        - facilityId: Hospital facility identifier (required)
        - timeWindowStart: Log collection start time (required)
        - timeWindowEnd: Log collection end time (required)
        - logLevel: Minimum log level to collect (default: INFO)
        - logs: List of RPA log entries (optional)

    Output Variables:
        - collectionComplete: Whether collection completed
        - rpaJobId: Job being analyzed
        - timeWindowStart: Collection start time
        - timeWindowEnd: Collection end time
        - logsCollected: Total log entries collected
        - botCount: Number of distinct bots
        - botMetrics: Metrics per bot
        - overallSuccessRate: Percentage of successful executions
        - totalExecutionTimeMs: Total time spent in executions
        - averageExecutionTimeMs: Average execution time
        - failureCount: Total failures
        - retryCount: Total retries
        - timeoutCount: Total timeouts
        - rpaStatus: HEALTHY/WARNING/ERROR
        - errorSummary: Count of errors by code
        - collectionTimestamp: When collection was performed
    """

    def __init__(self, settings=None, service=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            service: Optional service (for testing)
        """
        super().__init__(settings=settings)
        self._service = service

    @property
    def operation_name(self) -> str:
        """Operation name for logging."""
        return "collect_rpa_logs"

    @property
    def requires_idempotency(self) -> bool:
        """RPA log collection is read-only, no idempotency needed."""
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the RPA log collection task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with RPA log analysis
        """
        self._logger.info(
            "Starting RPA log collection",
            rpa_job_id=variables.get("rpaJobId"),
            facility_id=variables.get("facilityId"),
        )

        try:
            # Parse and validate input
            input_data = RPALogsInput.model_validate(variables)

            # Analyze logs by bot
            bot_metrics = self._analyze_bot_metrics(input_data.logs)
            failure_summary = self._analyze_failures(input_data.logs)
            overall_metrics = self._calculate_overall_metrics(input_data.logs, bot_metrics)

            # Determine RPA status
            success_rate = overall_metrics["success_rate"]
            if success_rate >= 95:
                rpa_status = "HEALTHY"
            elif success_rate >= 85:
                rpa_status = "WARNING"
            else:
                rpa_status = "ERROR"

            # Create output
            output = RPALogsOutput(
                collectionComplete=True,
                rpaJobId=input_data.rpa_job_id,
                timeWindowStart=input_data.time_window_start,
                timeWindowEnd=input_data.time_window_end,
                logsCollected=len(input_data.logs),
                botCount=len(bot_metrics),
                botMetrics=bot_metrics,
                overallSuccessRate=success_rate,
                totalExecutionTimeMs=overall_metrics["total_execution_ms"],
                averageExecutionTimeMs=overall_metrics["average_execution_ms"],
                failureCount=overall_metrics["failure_count"],
                retryCount=overall_metrics["retry_count"],
                timeoutCount=overall_metrics["timeout_count"],
                rpaStatus=rpa_status,
                errorSummary=failure_summary,
                collectionTimestamp=datetime.utcnow(),
            )

            self._logger.info(
                "RPA log collection completed",
                rpa_job_id=input_data.rpa_job_id,
                success_rate=str(success_rate),
                status=rpa_status,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error("RPA log collection validation failed", errors=e.errors())
            return WorkerResult.bpmn_error(
                error_code="INVALID_RPA_DATA",
                error_message=f"Validation failed: {e}",
            )

        except RPALogsError as e:
            self._logger.error("RPA log collection error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error("Unexpected error in RPA log collection", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=f"RPA log collection failed: {e}",
                retry=True,
            )

    def _analyze_bot_metrics(self, logs: list[RPALogEntry]) -> list[BotMetrics]:
        """
        Analyze performance metrics per bot.

        Args:
            logs: List of RPA log entries

        Returns:
            List of bot metrics
        """
        bot_data = defaultdict(list)

        for log in logs:
            bot_data[log.bot_name].append(log)

        metrics = []
        for bot_name, bot_logs in bot_data.items():
            execution_times = [log.execution_time_ms for log in bot_logs]
            success_logs = [log for log in bot_logs if log.status == "SUCCESS"]
            failure_logs = [log for log in bot_logs if log.status == "FAILURE"]
            retry_logs = [log for log in bot_logs if log.status == "RETRY"]

            success_rate = (
                Decimal(len(success_logs)) / max(1, len(bot_logs)) * 100
                if bot_logs
                else Decimal("0")
            )

            metric = BotMetrics(
                botName=bot_name,
                executionCount=len(bot_logs),
                successCount=len(success_logs),
                failureCount=len(failure_logs),
                retryCount=len(retry_logs),
                averageExecutionMs=int(sum(execution_times) / len(execution_times)) if execution_times else 0,
                minExecutionMs=min(execution_times) if execution_times else 0,
                maxExecutionMs=max(execution_times) if execution_times else 0,
                successRate=success_rate,
            )
            metrics.append(metric)

        return metrics

    def _analyze_failures(self, logs: list[RPALogEntry]) -> dict[str, int]:
        """
        Analyze failure patterns in RPA logs.

        Args:
            logs: List of RPA log entries

        Returns:
            Dictionary with error code counts
        """
        error_summary = defaultdict(int)

        for log in logs:
            if log.status in ["FAILURE", "ERROR"] and log.error_code:
                error_summary[log.error_code] += 1

        return dict(error_summary)

    def _calculate_overall_metrics(
        self, logs: list[RPALogEntry], bot_metrics: list[BotMetrics]
    ) -> dict[str, Any]:
        """
        Calculate overall RPA metrics.

        Args:
            logs: List of RPA log entries
            bot_metrics: Pre-calculated bot metrics

        Returns:
            Dictionary with overall metrics
        """
        if not logs:
            return {
                "success_rate": Decimal("0"),
                "total_execution_ms": 0,
                "average_execution_ms": 0,
                "failure_count": 0,
                "retry_count": 0,
                "timeout_count": 0,
            }

        success_count = sum(1 for log in logs if log.status == "SUCCESS")
        failure_count = sum(1 for log in logs if log.status == "FAILURE")
        retry_count = sum(1 for log in logs if log.status == "RETRY")
        timeout_count = sum(1 for log in logs if log.status == "TIMEOUT")
        execution_times = [log.execution_time_ms for log in logs]

        success_rate = Decimal(success_count) / max(1, len(logs)) * 100

        return {
            "success_rate": success_rate,
            "total_execution_ms": sum(execution_times),
            "average_execution_ms": int(sum(execution_times) / len(execution_times)) if execution_times else 0,
            "failure_count": failure_count,
            "retry_count": retry_count,
            "timeout_count": timeout_count,
        }
