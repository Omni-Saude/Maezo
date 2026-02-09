"""
ProcessMiningWorker - Zeebe worker for BPMN process mining and analytics.

This worker implements process mining for the Brazilian healthcare revenue cycle:
- BPMN process execution analysis
- Bottleneck identification
- Performance metrics calculation
- Process variant detection
- Cycle time analysis
- Exception flow tracking

Business Rule: Process Mining & Optimization Analytics
Industry Standard: Healthcare Process Mining (Celonis, UltimatusProfit)
KPI Reference:
  - Cycle Time: <7 days target (claim to payment)
  - Process Efficiency: 85%+ value-add activities
  - Exception Rate: <5% non-standard flows
  - Variant Consolidation: Reduce to <5 main paths
  - Bottleneck Impact: <10% cycle time per bottleneck
  - Continuous Improvement: 5-10% monthly efficiency gains

Migrated from Java ProcessMiningDelegate.

Topic: process-mining
BPMN Task: Task_Process_Mining
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


class ProcessEvent(BaseModel):
    """Model for a process event."""
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(..., alias="eventId")
    task_name: str = Field(..., alias="taskName")
    timestamp: datetime
    duration_ms: int = Field(..., alias="durationMs")
    status: str  # SUCCESS, ERROR, TIMEOUT


class ProcessVariant(BaseModel):
    """Model for a process variant (execution path)."""
    model_config = ConfigDict(populate_by_name=True)

    variant_id: str = Field(..., alias="variantId")
    path: list[str]  # Sequence of task names
    frequency: int
    average_duration_ms: int = Field(..., alias="averageDurationMs")
    first_occurrence: datetime = Field(..., alias="firstOccurrence")
    last_occurrence: datetime = Field(..., alias="lastOccurrence")


class TaskMetrics(BaseModel):
    """Model for task performance metrics."""
    model_config = ConfigDict(populate_by_name=True)

    task_name: str = Field(..., alias="taskName")
    execution_count: int = Field(..., alias="executionCount")
    average_duration_ms: int = Field(..., alias="averageDurationMs")
    min_duration_ms: int = Field(..., alias="minDurationMs")
    max_duration_ms: int = Field(..., alias="maxDurationMs")
    error_count: int = Field(..., alias="errorCount")
    error_rate: Decimal = Field(..., alias="errorRate")


class ProcessMiningInput(BaseModel):
    """Input model for process mining operation."""
    model_config = ConfigDict(populate_by_name=True)

    process_instance_id: str = Field(..., alias="processInstanceId")
    facility_id: str = Field(..., alias="facilityId")
    events: list[ProcessEvent]
    analysis_period: str = Field(..., alias="analysisPeriod")  # YYYY-MM


class ProcessMiningOutput(BaseModel):
    """Output model for process mining operation."""
    model_config = ConfigDict(populate_by_name=True)

    mining_complete: bool = Field(..., alias="miningComplete")
    process_id: str = Field(..., alias="processId")
    analysis_period: str = Field(..., alias="analysisPeriod")
    event_count: int = Field(..., alias="eventCount")
    variant_count: int = Field(..., alias="variantCount")
    top_variants: list[ProcessVariant] = Field(..., alias="topVariants")
    task_metrics: list[TaskMetrics] = Field(..., alias="taskMetrics")
    average_cycle_time_ms: int = Field(..., alias="averageCycleTimeMs")
    bottleneck_task: Optional[str] = Field(None, alias="bottleneckTask")
    bottleneck_duration_ms: Optional[int] = Field(None, alias="bottleneckDurationMs")
    exception_flow_count: int = Field(..., alias="exceptionFlowCount")
    exception_flow_percentage: Decimal = Field(..., alias="exceptionFlowPercentage")
    analysis_timestamp: datetime = Field(..., alias="analysisTimestamp")


class ProcessMiningError(BpmnErrorException):
    """Raised when process mining fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PROCESS_MINING_ERROR",
            message=message,
            details=details,
        )


@worker(topic="process-mining", max_jobs=8, lock_duration=120000)
class ProcessMiningWorker(BaseWorker):
    """
    Zeebe worker for BPMN process mining and analytics.

    This worker:
    1. Analyzes process execution events
    2. Identifies execution variants (process paths)
    3. Calculates task-level metrics
    4. Detects bottlenecks
    5. Tracks exception flows
    6. Computes cycle time statistics

    Input Variables:
        - processInstanceId: Process instance identifier (required)
        - facilityId: Hospital facility identifier (required)
        - events: List of process events (required)
        - analysisPeriod: Analysis period YYYY-MM (required)

    Output Variables:
        - miningComplete: Whether mining completed successfully
        - processId: Process identifier
        - analysisPeriod: Period used for analysis
        - eventCount: Total events analyzed
        - variantCount: Number of distinct execution paths
        - topVariants: Most frequent execution paths
        - taskMetrics: Performance metrics per task
        - averageCycleTimeMs: Average total process duration
        - bottleneckTask: Task with longest average duration
        - bottleneckDurationMs: Duration of bottleneck task
        - exceptionFlowCount: Number of error/exception paths
        - exceptionFlowPercentage: Percentage of executions with exceptions
        - analysisTimestamp: When analysis was performed
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
        """Get the operation name for idempotency and logging."""
        return "process_mining"

    @property
    def requires_idempotency(self) -> bool:
        """Process mining is read-only, no idempotency needed."""
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the process mining task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with process mining analysis
        """
        self._logger.info(
            "Starting process mining analysis",
            process_instance_id=variables.get("processInstanceId"),
            facility_id=variables.get("facilityId"),
        )

        try:
            # Parse and validate input
            input_data = ProcessMiningInput.model_validate(variables)

            # Analyze events
            variants = self._identify_variants(input_data.events)
            task_metrics = self._calculate_task_metrics(input_data.events)
            cycle_times = self._calculate_cycle_times(input_data.events)
            bottleneck = self._identify_bottleneck(task_metrics)
            exception_flows = self._analyze_exceptions(input_data.events)

            # Select top 5 variants by frequency
            top_variants = sorted(variants, key=lambda v: v.frequency, reverse=True)[:5]

            # Calculate exception percentage
            exception_percentage = (
                Decimal(exception_flows["count"]) / max(1, len(input_data.events))
                if input_data.events
                else Decimal("0")
            ) * 100

            # Create output
            output = ProcessMiningOutput(
                miningComplete=True,
                processId=input_data.process_instance_id,
                analysisPeriod=input_data.analysis_period,
                eventCount=len(input_data.events),
                variantCount=len(variants),
                topVariants=top_variants,
                taskMetrics=task_metrics,
                averageCycleTimeMs=int(sum(cycle_times) / len(cycle_times)) if cycle_times else 0,
                bottleneckTask=bottleneck["task"],
                bottleneckDurationMs=bottleneck["duration"],
                exceptionFlowCount=exception_flows["count"],
                exceptionFlowPercentage=exception_percentage,
                analysisTimestamp=datetime.utcnow(),
            )

            self._logger.info(
                "Process mining analysis completed",
                process_id=input_data.process_instance_id,
                variant_count=len(variants),
                bottleneck=bottleneck["task"],
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error("Process mining validation failed", errors=e.errors())
            return WorkerResult.bpmn_error(
                error_code="INVALID_MINING_DATA",
                error_message=f"Validation failed: {e}",
            )

        except ProcessMiningError as e:
            self._logger.error("Process mining error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error("Unexpected error in process mining", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=f"Process mining failed: {e}",
                retry=True,
            )

    def _identify_variants(self, events: list[ProcessEvent]) -> list[ProcessVariant]:
        """
        Identify distinct process execution variants.

        Args:
            events: List of process events

        Returns:
            List of process variants with frequencies
        """
        variant_paths = defaultdict(list)

        for event in events:
            path_key = event.task_name
            variant_paths[path_key].append(event)

        variants = []
        for idx, (path_key, path_events) in enumerate(variant_paths.items()):
            if path_events:
                variant = ProcessVariant(
                    variantId=f"VAR-{idx}",
                    path=[path_key],
                    frequency=len(path_events),
                    averageDurationMs=int(
                        sum(e.duration_ms for e in path_events) / len(path_events)
                    ),
                    firstOccurrence=min(e.timestamp for e in path_events),
                    lastOccurrence=max(e.timestamp for e in path_events),
                )
                variants.append(variant)

        return variants

    def _calculate_task_metrics(self, events: list[ProcessEvent]) -> list[TaskMetrics]:
        """
        Calculate performance metrics for each task.

        Args:
            events: List of process events

        Returns:
            List of task metrics
        """
        task_data = defaultdict(list)

        for event in events:
            task_data[event.task_name].append(event)

        metrics = []
        for task_name, task_events in task_data.items():
            durations = [e.duration_ms for e in task_events]
            errors = [e for e in task_events if e.status == "ERROR"]

            metric = TaskMetrics(
                taskName=task_name,
                executionCount=len(task_events),
                averageDurationMs=int(sum(durations) / len(durations)) if durations else 0,
                minDurationMs=min(durations) if durations else 0,
                maxDurationMs=max(durations) if durations else 0,
                errorCount=len(errors),
                errorRate=Decimal(len(errors)) / max(1, len(task_events)) * 100,
            )
            metrics.append(metric)

        return metrics

    def _calculate_cycle_times(self, events: list[ProcessEvent]) -> list[int]:
        """
        Calculate total cycle times for process instances.

        Args:
            events: List of process events

        Returns:
            List of cycle times in milliseconds
        """
        if not events:
            return []

        # Group events by process instance (simplified - use all events)
        # In reality, would group by process_instance_id
        cycle_times = [sum(e.duration_ms for e in events)]

        return cycle_times

    def _identify_bottleneck(self, task_metrics: list[TaskMetrics]) -> dict[str, Any]:
        """
        Identify the task with the longest average duration (bottleneck).

        Args:
            task_metrics: List of task metrics

        Returns:
            Dictionary with bottleneck task name and duration
        """
        if not task_metrics:
            return {"task": None, "duration": None}

        bottleneck_task = max(task_metrics, key=lambda m: m.average_duration_ms)

        return {
            "task": bottleneck_task.task_name,
            "duration": bottleneck_task.average_duration_ms,
        }

    def _analyze_exceptions(self, events: list[ProcessEvent]) -> dict[str, int]:
        """
        Analyze exception flows in the process.

        Args:
            events: List of process events

        Returns:
            Dictionary with exception count and details
        """
        exception_count = sum(1 for e in events if e.status in ["ERROR", "TIMEOUT"])

        return {
            "count": exception_count,
            "error_events": [e for e in events if e.status == "ERROR"],
            "timeout_events": [e for e in events if e.status == "TIMEOUT"],
        }
