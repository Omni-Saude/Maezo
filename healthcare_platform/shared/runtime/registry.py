"""Worker auto-discovery registry.

Discovers all worker classes across the healthcare_platform package by scanning
for two patterns used in the codebase:

1. @worker(topic="...") decorator (billing, glosa domains)
2. WORKER_TYPE class attribute (collection domain)

Both patterns are unified into a single topic→class mapping.
"""
from __future__ import annotations

import importlib
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


class WorkerRegistry:
    """Registry of all external task workers keyed by CIB Seven topic name."""

    def __init__(self) -> None:
        self._workers: dict[str, type] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Scan healthcare_platform for worker classes and register them."""
        domains = [
            "healthcare_platform.revenue_cycle",
            "healthcare_platform.patient_access",
            "healthcare_platform.clinical_operations",
            "healthcare_platform.platform_services",
        ]
        for domain in domains:
            self._scan_package(domain)

        logger.info("Worker discovery complete", total=len(self._workers))

        # Fail-fast if no workers discovered
        if len(self._workers) == 0:
            raise RuntimeError("Worker discovery found 0 workers")

    def get(self, topic: str) -> type | None:
        return self._workers.get(topic)

    def all(self) -> dict[str, type]:
        return dict(self._workers)

    def get_by_domain(self, domain: str) -> dict[str, type]:
        prefix = f"healthcare_platform.{domain}"
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

        for _importer, modname, ispkg in pkgutil.walk_packages(
            package.__path__, prefix=package.__name__ + "."
        ):
            if "workers" not in modname:
                continue
            if modname.endswith(".base"):
                continue

            try:
                module = importlib.import_module(modname)
            except Exception as exc:
                logger.warning("Could not import module", module=modname, error=str(exc))
                continue

            self._extract_workers(module)

    def _extract_workers(self, module: Any) -> None:
        """Extract worker classes from a module."""
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if not isinstance(obj, type):
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

            # Warn on topic collision
            if topic in self._workers:
                logger.warning(
                    "Topic collision detected, skipping duplicate",
                    topic=topic,
                    existing_worker=self._workers[topic].__name__,
                    duplicate_worker=obj.__name__,
                    module=obj.__module__,
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
        """Extract topic from either @worker decorator or WORKER_TYPE attribute."""
        # Pattern 1: @worker(topic="...") sets cls._topic
        topic = getattr(cls, "_topic", None)
        if topic and isinstance(topic, str) and topic != "":
            return topic

        # Pattern 2: WORKER_TYPE = "..." class attribute
        worker_type = getattr(cls, "WORKER_TYPE", None)
        if worker_type and isinstance(worker_type, str):
            return worker_type

        return None
