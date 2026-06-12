"""Base worker for billing subprocess."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WorkerResult:
    """Result of worker task execution."""

    success: bool
    variables: dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry: bool = False
    retry_timeout: Optional[int] = None

    @classmethod
    def ok(cls, variables: Optional[dict[str, Any]] = None) -> WorkerResult:
        """Create successful result."""
        return cls(success=True, variables=variables or {})

    @classmethod
    def bpmn_error(
        cls,
        error_code: str,
        error_message: Optional[str] = None,
        variables: Optional[dict[str, Any]] = None
    ) -> WorkerResult:
        """Create BPMN error result."""
        return cls(
            success=False,
            variables=variables or {},
            error_code=error_code,
            error_message=error_message
        )

    @classmethod
    def failure(
        cls,
        error_message: str,
        retry: bool = True,
        retry_timeout: Optional[int] = None
    ) -> WorkerResult:
        """Create failure result with optional retry."""
        return cls(
            success=False,
            error_message=error_message,
            retry=retry,
            retry_timeout=retry_timeout
        )


def worker(topic: str, max_jobs: int = 1, lock_duration: int = 300000) -> Callable:
    """Decorator to register worker topic and configuration."""
    def decorator(cls):
        cls._topic = topic
        cls._max_jobs = max_jobs
        cls._lock_duration = lock_duration
        return cls
    return decorator


class BaseWorker(ABC):
    """Base class for all billing workers."""

    _topic: str = ""
    _max_jobs: int = 1
    _lock_duration: int = 300000

    def __init__(self) -> None:
        """Initialize worker."""
        self._logger = get_logger(f"billing.worker.{self.worker_name}")

    @property
    def worker_name(self) -> str:
        """Get worker name from class name."""
        return self.__class__.__name__

    @property
    @abstractmethod
    def operation_name(self) -> str:
        """Get human-readable operation name."""
        ...

    @abstractmethod
    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """Process the worker task.

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with success status and output variables
        """
        ...

    async def execute(self, job: Any) -> WorkerResult:
        """Execute worker task with error handling.

        Args:
            job: Job object from workflow engine

        Returns:
            WorkerResult with execution outcome
        """
        start = time.monotonic()
        variables = getattr(job, "variables", {}) or {}

        self._logger.info(
            "Processing task",
            worker=self.worker_name,
            topic=self._topic,
            operation=self.operation_name
        )

        try:
            result = await self.process_task(job, variables)

            duration_ms = int((time.monotonic() - start) * 1000)
            self._logger.info(
                "Task completed",
                worker=self.worker_name,
                success=result.success,
                duration_ms=duration_ms
            )

            return result

        except DomainException as e:
            self._logger.error(
                "Domain error",
                error=str(e),
                bpmn_code=e.bpmn_error_code,
                retryable=e.retryable
            )
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error",
                error=str(e),
                exc_info=True
            )
            return WorkerResult.failure(
                error_message=str(e),
                retry=True
            )
