"""
Base Worker implementation for Camunda 8 External Task Workers.

Provides a template method pattern for consistent task handling with:
- Multi-tenant context management
- Federated rules access via DMN
- Error handling with BPMN error mapping
- Idempotency checking
- Comprehensive observability (logging, metrics, tracing)

This is the Python equivalent of the Java BaseWorker class.
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import structlog
from opentelemetry import trace
from prometheus_client import Counter, Histogram
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.domain.exceptions import BpmnErrorException, DomainException
from revenue_cycle.multi_tenant.context import TenantContext

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Prometheus metrics - use lazy initialization to prevent duplicate registration
_metrics_initialized = False
WORKER_EXECUTION_TIME = None
WORKER_EXECUTIONS_TOTAL = None
WORKER_RETRIES_TOTAL = None
WORKER_BPMN_ERRORS_TOTAL = None


def _init_metrics():
    """Initialize Prometheus metrics on first use to prevent duplicate registration."""
    global _metrics_initialized, WORKER_EXECUTION_TIME, WORKER_EXECUTIONS_TOTAL
    global WORKER_RETRIES_TOTAL, WORKER_BPMN_ERRORS_TOTAL

    if _metrics_initialized:
        return

    from prometheus_client import REGISTRY

    # Check if metrics already exist in registry
    try:
        WORKER_EXECUTION_TIME = Histogram(
            "worker_execution_seconds",
            "Time spent executing worker tasks",
            ["worker", "status"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
    except ValueError:
        # Metric already registered, retrieve it
        WORKER_EXECUTION_TIME = REGISTRY._collector_to_names.get(
            "worker_execution_seconds"
        ) or Histogram._MULTIPROC_MODE

    try:
        WORKER_EXECUTIONS_TOTAL = Counter(
            "worker_executions_total",
            "Total number of worker executions",
            ["worker", "status"],
        )
    except ValueError:
        pass

    try:
        WORKER_RETRIES_TOTAL = Counter(
            "worker_retries_total",
            "Total number of worker retries",
            ["worker"],
        )
    except ValueError:
        pass

    try:
        WORKER_BPMN_ERRORS_TOTAL = Counter(
            "worker_bpmn_errors_total",
            "Total number of BPMN errors thrown",
            ["worker", "error_code"],
        )
    except ValueError:
        pass

    _metrics_initialized = True


@dataclass
class WorkerResult:
    """
    Result of a worker task execution.

    This dataclass encapsulates the outcome of processing an external task,
    including output variables, error information, and retry settings.

    Attributes:
        success: Whether the task completed successfully
        variables: Output variables to return to the process
        error_code: BPMN error code (for error boundary events)
        error_message: Human-readable error message
        retry: Whether to retry the task
        retry_timeout: Delay before retry in milliseconds

    Example:
        # Successful completion
        return WorkerResult(
            success=True,
            variables={"appealStrategy": "COMPREHENSIVE_APPEAL", "priority": "HIGH"}
        )

        # BPMN error for process handling
        return WorkerResult.bpmn_error(
            error_code="INVALID_GLOSA_DATA",
            error_message="Glosa type is required"
        )

        # Technical failure with retry
        return WorkerResult.failure(
            error_message="Database connection failed",
            retry=True,
            retry_timeout=5000
        )
    """

    success: bool
    variables: dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry: bool = False
    retry_timeout: Optional[int] = None  # milliseconds

    @classmethod
    def ok(cls, variables: Optional[dict[str, Any]] = None) -> "WorkerResult":
        """
        Create a successful result.

        Args:
            variables: Output variables for the process

        Returns:
            WorkerResult with success=True
        """
        return cls(success=True, variables=variables or {})

    @classmethod
    def bpmn_error(
        cls,
        error_code: str,
        error_message: Optional[str] = None,
        variables: Optional[dict[str, Any]] = None,
    ) -> "WorkerResult":
        """
        Create a BPMN error result.

        This triggers a BPMN error boundary event in the process.

        Args:
            error_code: BPMN error code
            error_message: Error description
            variables: Additional variables to pass

        Returns:
            WorkerResult configured for BPMN error
        """
        return cls(
            success=False,
            variables=variables or {},
            error_code=error_code,
            error_message=error_message,
        )

    @classmethod
    def failure(
        cls,
        error_message: str,
        retry: bool = True,
        retry_timeout: Optional[int] = None,
    ) -> "WorkerResult":
        """
        Create a technical failure result.

        Args:
            error_message: Error description
            retry: Whether to retry
            retry_timeout: Delay before retry in milliseconds

        Returns:
            WorkerResult configured for retry or failure
        """
        return cls(
            success=False,
            error_message=error_message,
            retry=retry,
            retry_timeout=retry_timeout,
        )

    @classmethod
    def from_exception(cls, exception: Exception) -> "WorkerResult":
        """
        Create a WorkerResult from an exception.

        Args:
            exception: The exception that occurred

        Returns:
            WorkerResult configured based on exception type
        """
        if isinstance(exception, BpmnErrorException):
            return cls.bpmn_error(
                error_code=exception.error_code,
                error_message=exception.error_message,
            )
        elif isinstance(exception, DomainException):
            # Domain exceptions become BPMN errors
            return cls.bpmn_error(
                error_code=exception.code,
                error_message=exception.message,
            )
        else:
            # Technical exceptions allow retry
            return cls.failure(
                error_message=str(exception),
                retry=True,
            )


# Type variable for the decorator
F = TypeVar("F", bound=Callable[..., Any])


def worker(
    topic: str,
    lock_duration: int = 300000,  # 5 minutes
    max_jobs: int = 1,
    variables: Optional[list[str]] = None,
) -> Callable[[type["BaseWorker"]], type["BaseWorker"]]:
    """
    Decorator to register a worker class for a Camunda topic.

    This is the Python equivalent of Java's @Component("beanName").

    Args:
        topic: Camunda topic name to subscribe to
        lock_duration: Lock duration in milliseconds
        max_jobs: Maximum concurrent jobs
        variables: Variables to fetch (None = all)

    Returns:
        Decorated worker class

    Example:
        @worker(topic="analyze-glosa", max_jobs=5)
        class AnalyzeGlosaWorker(BaseWorker):
            async def process(self, job, variables):
                ...
    """

    def decorator(cls: type["BaseWorker"]) -> type["BaseWorker"]:
        cls._topic = topic
        cls._lock_duration = lock_duration
        cls._max_jobs = max_jobs
        cls._variables = variables
        return cls

    return decorator


class BaseWorker(ABC):
    """
    Abstract base class for all Camunda 8 External Task Workers.

    Provides a template method pattern for task processing with:
    - Multi-tenant context handling
    - Federated rules access
    - Error handling with BPMN error mapping
    - Idempotency checking
    - Observability (logging, metrics, tracing)

    This is the Python equivalent of the Java BaseWorker class.

    Subclasses must implement:
    - process_task(): Main business logic
    - operation_name: Property returning the operation name

    Example:
        @worker(topic="analyze-glosa")
        class AnalyzeGlosaWorker(BaseWorker):

            @property
            def operation_name(self) -> str:
                return "analyze_glosa"

            async def process_task(
                self,
                job: ExternalTask,
                variables: dict[str, Any],
            ) -> WorkerResult:
                glosa_type = self.get_required_variable(variables, "glosaType", str)
                glosa_amount = self.get_amount_variable(variables, "glosaAmount")

                # Business logic...

                return WorkerResult.ok({
                    "appealStrategy": "COMPREHENSIVE_APPEAL",
                    "priority": "HIGH",
                })
    """

    # Class-level attributes set by @worker decorator
    _topic: str = ""
    _lock_duration: int = 300000
    _max_jobs: int = 1
    _variables: Optional[list[str]] = None

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the worker.

        Args:
            settings: Application settings
        """
        # Initialize metrics on first worker instantiation
        _init_metrics()

        self._settings = settings or get_settings()
        self._logger = logger.bind(worker=self.worker_name)
        self._idempotency_cache: dict[str, Any] = {}  # Simple in-memory cache

    @property
    def worker_name(self) -> str:
        """Get the worker name for logging and metrics."""
        return self.__class__.__name__

    @property
    @abstractmethod
    def operation_name(self) -> str:
        """
        Get the operation name for idempotency and logging.

        Should be a unique identifier like "analyze_glosa", "submit_claim".

        Returns:
            Operation name string
        """
        ...

    @property
    def default_retries(self) -> int:
        """Get the default number of retries."""
        return self._settings.default_retries

    @property
    def requires_idempotency(self) -> bool:
        """
        Check if this worker requires idempotency checking.

        Override to return False for naturally idempotent operations
        like read-only queries.

        Returns:
            True if idempotency checking is required
        """
        return True

    async def execute(
        self,
        job: Any,  # ExternalTask from Camunda client
        job_service: Any,  # ExternalTaskService from Camunda client
    ) -> None:
        """
        Main execution entry point.

        This is the template method that orchestrates task processing:
        1. Start metrics timer and tracing span
        2. Set up tenant context
        3. Validate task
        4. Check idempotency
        5. Execute business logic
        6. Handle result (complete/error/retry)
        7. Record metrics

        Args:
            job: Camunda external task
            job_service: Camunda external task service
        """
        start_time = time.time()
        job_key = str(job.key) if hasattr(job, "key") else "unknown"
        business_key = self._get_business_key(job)
        variables = self._get_all_variables(job)

        self._logger.info(
            "Processing task",
            job_key=job_key,
            business_key=business_key,
            process_instance_key=getattr(job, "process_instance_key", None),
        )

        try:
            # Set up tenant context from job variables
            tenant_ctx = TenantContext.from_job_variables(variables)

            with tracer.start_as_current_span(
                f"{self.worker_name}.execute",
                attributes={
                    "worker.name": self.worker_name,
                    "worker.operation": self.operation_name,
                    "job.key": job_key,
                    "tenant.id": tenant_ctx.tenant.tenant_id,
                },
            ):
                async with tenant_ctx:
                    # Validate task
                    self._validate_task(job, variables)

                    # Check idempotency
                    if self.requires_idempotency:
                        cached_result = await self._check_idempotency(job, variables)
                        if cached_result is not None:
                            self._logger.info(
                                "Returning cached idempotent result",
                                job_key=job_key,
                            )
                            result = cached_result
                        else:
                            result = await self._execute_with_retry(job, variables)
                            await self._store_idempotency(job, variables, result)
                    else:
                        result = await self._execute_with_retry(job, variables)

            # Handle result
            await self._handle_result(job, job_service, result)

            # Record success metrics
            self._record_metrics(start_time, "success")
            self._logger.info(
                "Task completed",
                job_key=job_key,
                success=result.success,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            self._logger.error(
                "Task execution failed",
                job_key=job_key,
                error=str(e),
                exc_info=True,
            )

            # Convert exception to WorkerResult and handle
            result = WorkerResult.from_exception(e)
            await self._handle_result(job, job_service, result)

            # Record failure metrics
            self._record_metrics(start_time, "failure")

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _execute_with_retry(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Execute the task with automatic retry for transient failures.

        Uses tenacity for exponential backoff retry.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult from process_task
        """
        return await self.process_task(job, variables)

    @abstractmethod
    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the external task.

        This method should contain the main business logic implementation.
        It is called by the template method after validation and
        idempotency checks.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult indicating success/failure and output variables
        """
        ...

    async def _handle_result(
        self,
        job: Any,
        job_service: Any,
        result: WorkerResult,
    ) -> None:
        """
        Handle the worker result by completing/failing the task.

        Args:
            job: Camunda external task
            job_service: Camunda external task service
            result: Worker result to handle
        """
        if result.success:
            # Complete the task with output variables
            await job_service.complete(job, result.variables)

        elif result.error_code:
            # Throw BPMN error for process error handling
            if WORKER_BPMN_ERRORS_TOTAL:
                WORKER_BPMN_ERRORS_TOTAL.labels(
                    worker=self.worker_name,
                    error_code=result.error_code,
                ).inc()

            await job_service.throw_error(
                job,
                result.error_code,
                result.error_message or result.error_code,
            )

        elif result.retry:
            # Schedule retry with backoff
            retries = getattr(job, "retries", self.default_retries)
            if retries is None:
                retries = self.default_retries

            if retries > 0:
                retry_timeout = result.retry_timeout or self._calculate_retry_timeout(retries)
                if WORKER_RETRIES_TOTAL:
                    WORKER_RETRIES_TOTAL.labels(worker=self.worker_name).inc()

                self._logger.warning(
                    "Scheduling retry",
                    retries_remaining=retries - 1,
                    retry_timeout_ms=retry_timeout,
                )

                await job_service.fail(
                    job,
                    retries - 1,
                    retry_timeout,
                    result.error_message or "Task failed, retrying",
                )
            else:
                # No more retries - throw BPMN error
                if WORKER_BPMN_ERRORS_TOTAL:
                    WORKER_BPMN_ERRORS_TOTAL.labels(
                        worker=self.worker_name,
                        error_code="WORKER_FAILURE",
                    ).inc()

                await job_service.throw_error(
                    job,
                    "WORKER_FAILURE",
                    result.error_message or "Max retries exceeded",
                )
        else:
            # Fail without retry
            await job_service.fail(
                job,
                0,
                0,
                result.error_message or "Task failed",
            )

    def _calculate_retry_timeout(self, remaining_retries: int) -> int:
        """
        Calculate retry timeout using exponential backoff.

        Formula: base^(default_retries - remaining_retries + 1) * 1000ms

        Args:
            remaining_retries: Number of remaining retries

        Returns:
            Timeout in milliseconds
        """
        base = self._settings.retry_backoff_base
        attempt = self.default_retries - remaining_retries + 1
        return int(pow(base, attempt - 1) * 1000)

    def _validate_task(self, job: Any, variables: dict[str, Any]) -> None:
        """
        Validate the external task before processing.

        Override to add custom validation.

        Args:
            job: Camunda external task
            variables: Job variables

        Raises:
            BpmnErrorException: If validation fails
        """
        if not job:
            raise BpmnErrorException(
                error_code="INVALID_TASK",
                message="External task cannot be null",
            )

    async def _check_idempotency(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> Optional[WorkerResult]:
        """
        Check if this task has already been processed.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            Cached result if found, None otherwise
        """
        idempotency_key = self._generate_idempotency_key(job, variables)
        return self._idempotency_cache.get(idempotency_key)

    async def _store_idempotency(
        self,
        job: Any,
        variables: dict[str, Any],
        result: WorkerResult,
    ) -> None:
        """
        Store the task result for idempotency.

        Args:
            job: Camunda external task
            variables: Job variables
            result: Worker result to cache
        """
        idempotency_key = self._generate_idempotency_key(job, variables)
        self._idempotency_cache[idempotency_key] = result

    def _generate_idempotency_key(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> str:
        """
        Generate an idempotency key for the task.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            Unique idempotency key
        """
        # Extract key parameters for idempotency
        params = self.extract_idempotency_params(variables)

        # Create a deterministic hash
        key_data = f"{self.operation_name}:{params}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Override to customize which variables are used for idempotency.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        # Default: use process instance key and business key
        process_instance = variables.get("processInstanceKey", "")
        business_key = variables.get("businessKey", "")
        return f"{process_instance}:{business_key}"

    def _record_metrics(self, start_time: float, status: str) -> None:
        """
        Record execution metrics.

        Args:
            start_time: Execution start time
            status: Execution status (success/failure)
        """
        if not _metrics_initialized:
            return

        duration = time.time() - start_time

        if WORKER_EXECUTION_TIME:
            WORKER_EXECUTION_TIME.labels(
                worker=self.worker_name,
                status=status,
            ).observe(duration)

        if WORKER_EXECUTIONS_TOTAL:
            WORKER_EXECUTIONS_TOTAL.labels(
                worker=self.worker_name,
                status=status,
            ).inc()

    # =========================================================================
    # VARIABLE HELPER METHODS
    # =========================================================================

    def _get_all_variables(self, job: Any) -> dict[str, Any]:
        """Get all variables from the job."""
        if hasattr(job, "variables"):
            return job.variables or {}
        return {}

    def _get_business_key(self, job: Any) -> Optional[str]:
        """Get the business key from the job."""
        variables = self._get_all_variables(job)
        return variables.get("businessKey") or getattr(job, "business_key", None)

    def get_required_variable(
        self,
        variables: dict[str, Any],
        name: str,
        expected_type: type,
    ) -> Any:
        """
        Get a required variable from job variables.

        Args:
            variables: Job variables
            name: Variable name
            expected_type: Expected type

        Returns:
            Variable value

        Raises:
            BpmnErrorException: If variable is missing or has wrong type
        """
        value = variables.get(name)

        if value is None:
            raise BpmnErrorException.missing_variable(name)

        if not isinstance(value, expected_type):
            raise BpmnErrorException(
                error_code="INVALID_VARIABLE_TYPE",
                message=f"Variable '{name}' has incorrect type. "
                f"Expected: {expected_type.__name__}, "
                f"Actual: {type(value).__name__}",
            )

        return value

    def get_variable(
        self,
        variables: dict[str, Any],
        name: str,
        expected_type: type,
        default: Any = None,
    ) -> Any:
        """
        Get an optional variable from job variables.

        Args:
            variables: Job variables
            name: Variable name
            expected_type: Expected type
            default: Default value if not found

        Returns:
            Variable value or default
        """
        value = variables.get(name)

        if value is None:
            return default

        if not isinstance(value, expected_type):
            self._logger.warning(
                "Variable has incorrect type",
                variable=name,
                expected=expected_type.__name__,
                actual=type(value).__name__,
            )
            return default

        return value

    def get_amount_variable(
        self,
        variables: dict[str, Any],
        name: str,
        default: Optional[Decimal] = None,
    ) -> Optional[Decimal]:
        """
        Get a monetary amount variable, handling various numeric types.

        Converts int, float, str to Decimal for precise arithmetic.

        Args:
            variables: Job variables
            name: Variable name
            default: Default value if not found

        Returns:
            Amount as Decimal or default

        Raises:
            BpmnErrorException: If value cannot be parsed
        """
        value = variables.get(name)

        if value is None:
            return default

        try:
            if isinstance(value, Decimal):
                return value
            elif isinstance(value, (int, float)):
                return Decimal(str(value))
            elif isinstance(value, str):
                # Handle Brazilian format (1.234,56) vs American format (1,234.56)
                # Brazilian: dot as thousands separator, comma as decimal
                # American: comma as thousands separator, dot as decimal
                if "," in value and "." in value:
                    # Both separators present - determine format by position
                    if value.rfind(",") > value.rfind("."):
                        # Comma is last = Brazilian (e.g., "1.234,56")
                        normalized = value.replace(".", "").replace(",", ".")
                    else:
                        # Dot is last = American (e.g., "1,234.56")
                        normalized = value.replace(",", "")
                elif "," in value:
                    # Only comma = Brazilian decimal (e.g., "1234,56")
                    normalized = value.replace(",", ".")
                else:
                    # Only dot or no separator = American format (e.g., "1234.56" or "1234")
                    normalized = value
                return Decimal(normalized)
            else:
                raise ValueError(f"Unsupported type: {type(value).__name__}")
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_AMOUNT",
                message=f"Cannot parse amount variable '{name}': {e}",
            )

    def get_required_amount_variable(
        self,
        variables: dict[str, Any],
        name: str,
    ) -> Decimal:
        """
        Get a required monetary amount variable.

        Args:
            variables: Job variables
            name: Variable name

        Returns:
            Amount as Decimal

        Raises:
            BpmnErrorException: If variable is missing or invalid
        """
        amount = self.get_amount_variable(variables, name)
        if amount is None:
            raise BpmnErrorException.missing_variable(name)
        return amount
