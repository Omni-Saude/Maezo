"""Worker auto-discovery registry.

Discovers all worker classes across the healthcare_platform package by scanning
for multiple patterns used in the codebase:

1. @worker(topic="...") decorator (billing, glosa domains)
2. WORKER_TYPE class attribute (collection domain)
3. TOPIC class attribute (v2 workers — clinical_operations, patient_access)
4. Module-level TOPIC + execute() function (platform_services function-based workers)

All patterns are unified into a single topic→class mapping.

Supports 3 execution modes (Principle 5):
    - Subdomain-specific (container mode): discover(domain_filter="revenue_cycle")
      + get_by_subdomain("revenue_cycle", "billing")
    - Domain-wide (swarm/debug mode): discover(domain_filter="revenue_cycle")
      + get_by_domain("revenue_cycle")
    - Topic-specific (dev mode): discover() + get("billing-calculate-charges")
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
import re
from pathlib import Path
from typing import Any

from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

# Top-level package path
_PLATFORM_ROOT = Path(__file__).resolve().parent.parent.parent

# Topic name validation pattern: alphanumeric start, then alphanumeric, underscore, dash, or dot
TOPIC_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*$')


class FunctionWorkerAdapter:
    """Adapter that wraps a module-level execute() function as a class-based worker.

    Used for platform_services workers that follow the function-based pattern:
        TOPIC = "platform.sync_erp_data"
        async def execute(input_data: dict) -> dict: ...

    The adapter makes them compatible with the class-based worker runner by
    extracting variables from the ExternalTask, calling execute(), and
    returning a ProcessTaskResult-compatible object.
    """

    # Set by _create_function_adapter() for each module
    TOPIC: str = ""

    def __init__(self) -> None:
        pass

    async def execute(self, task: Any) -> Any:
        """Execute the wrapped function with task variables."""
        from healthcare_platform.shared.workers.base import ProcessTaskResult

        variables = {}
        if hasattr(task, "get_variables"):
            variables = task.get_variables() or {}
        elif hasattr(task, "variables"):
            variables = task.variables or {}

        try:
            result = self._execute_fn(variables)
            if asyncio.iscoroutine(result):
                result = await result

            return ProcessTaskResult(
                success=True,
                variables=result if isinstance(result, dict) else {},
            )
        except Exception as exc:
            error_code = None
            if hasattr(exc, "bpmn_error_code"):
                error_code = exc.bpmn_error_code
            return ProcessTaskResult(
                success=False,
                error_code=error_code,
                error_message=str(exc)[:666],
            )


def _create_function_adapter(module: Any, topic: str) -> type:
    """Create a FunctionWorkerAdapter subclass bound to a specific module.

    Returns a new class (not instance) so the registry can store type→class
    and the runner can instantiate it with cls().
    """
    execute_fn = module.execute

    adapter_cls = type(
        f"FunctionAdapter_{module.__name__.rsplit('.', 1)[-1]}",
        (FunctionWorkerAdapter,),
        {
            "TOPIC": topic,
            "__module__": module.__name__,
            "_execute_fn": staticmethod(execute_fn),
        },
    )
    return adapter_cls

# All known worker domains
_ALL_DOMAINS = [
    "healthcare_platform.revenue_cycle",
    "healthcare_platform.patient_access",
    "healthcare_platform.clinical_operations",
    "healthcare_platform.platform_services",
]


class WorkerRegistry:
    """Registry of all external task workers keyed by CIB Seven topic name."""

    def __init__(self) -> None:
        self._workers: dict[str, type] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(self, domain_filter: str | None = None) -> None:
        """Scan healthcare_platform for worker classes and register them.

        Args:
            domain_filter: If set, scan ONLY this domain (e.g. "revenue_cycle").
                          This improves startup time in container mode by skipping
                          domains not present in the Docker image.
        """
        if domain_filter:
            domains = [f"healthcare_platform.{domain_filter}"]
        else:
            domains = list(_ALL_DOMAINS)

        for domain in domains:
            self._scan_package(domain)

        logger.info(
            "Worker discovery complete",
            total=len(self._workers),
            domain_filter=domain_filter or "all",
        )

        # Fail-fast if no workers discovered (but only when not filtering)
        if len(self._workers) == 0:
            if domain_filter:
                logger.warning(
                    "No workers found for domain",
                    domain=domain_filter,
                )
            else:
                raise RuntimeError("Worker discovery found 0 workers")

    def get(self, topic: str) -> type | None:
        return self._workers.get(topic)

    def all(self) -> dict[str, type]:
        return dict(self._workers)

    def get_by_domain(self, domain: str) -> dict[str, type]:
        """Get all workers belonging to a domain.

        Args:
            domain: Domain name (e.g. "revenue_cycle")

        Returns:
            Dict of topic→worker_class for workers in that domain.
        """
        prefix = f"healthcare_platform.{domain}"
        return {
            topic: cls
            for topic, cls in self._workers.items()
            if cls.__module__.startswith(prefix)
        }

    def get_by_subdomain(self, domain: str, subdomain: str) -> dict[str, type]:
        """Get workers belonging to a specific subdomain (container mode).

        Matches workers whose module path starts with
        healthcare_platform.{domain}.{subdomain}

        Args:
            domain: Domain name (e.g. "revenue_cycle")
            subdomain: Subdomain name (e.g. "billing")

        Returns:
            Dict of topic→worker_class for workers in that subdomain.
        """
        prefix = f"healthcare_platform.{domain}.{subdomain}"
        return {
            topic: cls
            for topic, cls in self._workers.items()
            if cls.__module__.startswith(prefix)
        }

    def topics(self) -> list[str]:
        return list(self._workers.keys())

    # ------------------------------------------------------------------
    # Internal scanning
    # ------------------------------------------------------------------

    def _scan_package(self, package_name: str) -> None:
        """Recursively import all modules in a package and extract workers."""
        try:
            package = importlib.import_module(package_name)
        except ImportError as exc:
            logger.warning("Could not import package", package=package_name, error=str(exc))
            return

        if not hasattr(package, "__path__"):
            return

        for _importer, modname, _ispkg in pkgutil.walk_packages(
            package.__path__, prefix=package.__name__ + "."
        ):
            if "workers" not in modname:
                continue
            # Skip base modules (base classes, not actual workers)
            if modname.endswith(".base") or modname.endswith(".base_v2_worker"):
                continue
            # Skip generic workers in shared (they're base classes)
            if "shared.workers" in modname:
                continue

            try:
                module = importlib.import_module(modname)
            except Exception as exc:
                # Principle 9: tolerant runtime — log and skip, don't crash
                logger.warning("Could not import module", module=modname, error=str(exc))
                continue

            self._extract_workers(module)

    def _extract_workers(self, module: Any) -> None:
        """Extract worker classes from a module.

        Also detects function-based workers (Pattern 4): modules with a
        top-level TOPIC string constant and a callable execute() function.
        These are wrapped in FunctionWorkerAdapter subclasses.
        """
        # Pattern 4: module-level TOPIC + execute() (platform_services)
        module_topic = getattr(module, "TOPIC", None)
        module_execute = getattr(module, "execute", None)
        if (
            isinstance(module_topic, str)
            and module_topic
            and callable(module_execute)
            and not isinstance(module_execute, type)
            and TOPIC_PATTERN.match(module_topic)
            and module_topic not in self._workers
        ):
            adapter_cls = _create_function_adapter(module, module_topic)
            self._workers[module_topic] = adapter_cls
            logger.debug(
                "Registered function-based worker",
                topic=module_topic,
                module=module.__name__,
            )

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if not isinstance(obj, type):
                continue

            # Skip abstract classes — they can't be instantiated
            if inspect.isabstract(obj):
                continue

            topic = self._get_topic(obj)
            if not topic:
                continue

            # Validate topic name format
            if not TOPIC_PATTERN.match(topic):
                logger.warning(
                    "Invalid topic name, skipping worker",
                    topic=topic,
                    worker=obj.__name__,
                    module=obj.__module__,
                )
                continue

            # Validate worker has callable execute method
            if not callable(getattr(obj, "execute", None)):
                logger.warning(
                    "Worker missing callable execute method, skipping",
                    topic=topic,
                    worker=obj.__name__,
                    module=obj.__module__,
                )
                continue

            # Skip workers that require DI args in __init__ (can't instantiate without them)
            try:
                init_sig = inspect.signature(obj.__init__)
                required_params = [
                    p for p in init_sig.parameters.values()
                    if p.name != "self"
                    and p.default is inspect.Parameter.empty
                    and p.kind not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                ]
                if required_params:
                    logger.debug(
                        "Worker requires constructor args, skipping auto-registration",
                        worker=obj.__name__,
                        required=", ".join(p.name for p in required_params),
                    )
                    continue
            except (ValueError, TypeError):
                pass  # Can't inspect __init__, proceed anyway

            # Warn on topic collision
            if topic in self._workers:
                existing = self._workers[topic]
                # Same class re-imported from different path (e.g. re-exports) — skip silently
                if existing is obj:
                    continue
                logger.warning(
                    "Topic collision detected, skipping duplicate",
                    topic=topic,
                    existing_worker=existing.__name__,
                    existing_module=existing.__module__,
                    duplicate_worker=obj.__name__,
                    duplicate_module=obj.__module__,
                )
                continue

            self._workers[topic] = obj
            logger.debug(
                "Registered worker",
                topic=topic,
                worker=obj.__name__,
                module=obj.__module__,
            )

    @staticmethod
    def _get_topic(cls: type) -> str | None:
        """Extract topic from any of the supported registration patterns."""
        # Pattern 1: @worker(topic="...") sets cls._topic
        topic = getattr(cls, "_topic", None)
        if topic and isinstance(topic, str) and topic != "":
            return topic

        # Pattern 2: WORKER_TYPE = "..." class attribute
        worker_type = getattr(cls, "WORKER_TYPE", None)
        if worker_type and isinstance(worker_type, str):
            return worker_type

        # Pattern 3: TOPIC = "..." class attribute (v2 workers)
        topic_attr = getattr(cls, "TOPIC", None)
        if topic_attr and isinstance(topic_attr, str):
            return topic_attr

        return None
