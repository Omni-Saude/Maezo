"""
Dependency Injection Container.

Provides a simple DI container for managing application dependencies
and their lifecycle. Supports singleton and factory patterns.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, TypeVar

import structlog

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager
from revenue_cycle.multi_tenant.database import MultiTenantDatabase
from revenue_cycle.observability.logging import configure_logging
from revenue_cycle.observability.metrics import MetricsRegistry, get_metrics

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class Container:
    """
    Dependency injection container.

    Manages the lifecycle of application components including:
    - Configuration (Settings)
    - Database connections (MultiTenantDatabase)
    - Metrics registry
    - Workers and services

    Example:
        container = Container()
        await container.initialize()

        db = container.database
        metrics = container.metrics

        await container.shutdown()
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize the container.

        Args:
            settings: Application settings (creates from environment if not provided)
        """
        self._settings = settings or get_settings()
        self._database: MultiTenantDatabase | None = None
        self._credential_manager: TenantCredentialManager | None = None
        self._metrics: MetricsRegistry | None = None
        self._workers: dict[str, Any] = {}
        self._services: dict[str, Any] = {}
        self._initialized = False

    @property
    def settings(self) -> Settings:
        """Get application settings."""
        return self._settings

    @property
    def database(self) -> MultiTenantDatabase:
        """Get database manager."""
        if self._database is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._database

    @property
    def credential_manager(self) -> TenantCredentialManager:
        """Get credential manager."""
        if self._credential_manager is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._credential_manager

    @property
    def metrics(self) -> MetricsRegistry:
        """Get metrics registry."""
        if self._metrics is None:
            self._metrics = get_metrics()
        return self._metrics

    async def initialize(self) -> None:
        """
        Initialize all container components.

        Should be called once at application startup.
        """
        if self._initialized:
            logger.warning("Container already initialized")
            return

        logger.info(
            "Initializing container",
            environment=self._settings.environment,
        )

        # Configure logging
        configure_logging(self._settings)

        # Initialize database
        self._database = MultiTenantDatabase(self._settings)
        await self._database.initialize()

        # Initialize credential manager
        self._credential_manager = TenantCredentialManager(
            settings=self._settings,
            cache_ttl_seconds=300,  # 5 minutes
            audit_enabled=True,
        )
        await self._credential_manager.initialize()

        # Initialize metrics
        self._metrics = get_metrics()
        self._metrics.set_app_info(
            version="1.0.0",
            environment=self._settings.environment,
        )

        # Discover and register workers
        self._discover_workers()

        self._initialized = True
        logger.info("Container initialized successfully")

    async def shutdown(self) -> None:
        """
        Shutdown all container components.

        Should be called during application shutdown.
        """
        logger.info("Shutting down container")

        # Close database connections
        if self._database:
            await self._database.close()
            self._database = None

        # Close credential manager
        if self._credential_manager:
            await self._credential_manager.close()
            self._credential_manager = None

        # Clear workers and services
        self._workers.clear()
        self._services.clear()

        self._initialized = False
        logger.info("Container shutdown complete")

    def _discover_workers(self) -> None:
        """
        Discover and register worker classes.

        Imports worker modules and registers classes with @worker decorator.
        """
        # Import worker modules to trigger @worker decorator registration
        from revenue_cycle.workers.glosa import AnalyzeGlosaWorker

        # Register known workers
        self.register_worker("analyze-glosa", AnalyzeGlosaWorker)

        logger.info(
            "Discovered workers",
            count=len(self._workers),
            topics=list(self._workers.keys()),
        )

    def register_worker(
        self,
        topic: str,
        worker_class: type,
    ) -> None:
        """
        Register a worker class for a topic.

        Args:
            topic: Camunda topic name
            worker_class: Worker class to instantiate
        """
        self._workers[topic] = worker_class(self._settings)
        logger.debug(
            "Registered worker",
            topic=topic,
            worker=worker_class.__name__,
        )

    def get_worker(self, topic: str) -> Any:
        """
        Get a worker instance for a topic.

        Args:
            topic: Camunda topic name

        Returns:
            Worker instance

        Raises:
            KeyError: If no worker registered for topic
        """
        if topic not in self._workers:
            raise KeyError(f"No worker registered for topic: {topic}")
        return self._workers[topic]

    def get_all_workers(self) -> dict[str, Any]:
        """Get all registered workers."""
        return self._workers.copy()

    def register_service(
        self,
        name: str,
        service: Any,
    ) -> None:
        """
        Register a service instance.

        Args:
            name: Service name
            service: Service instance
        """
        self._services[name] = service
        logger.debug("Registered service", name=name)

    def get_service(self, name: str) -> Any:
        """
        Get a service by name.

        Args:
            name: Service name

        Returns:
            Service instance

        Raises:
            KeyError: If service not found
        """
        if name not in self._services:
            raise KeyError(f"Service not found: {name}")
        return self._services[name]

    @property
    def is_initialized(self) -> bool:
        """Check if container is initialized."""
        return self._initialized


# Global container instance
_container: Container | None = None


@lru_cache
def get_container() -> Container:
    """
    Get the global container instance.

    Returns:
        Container instance (cached)
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


async def initialize_container(settings: Settings | None = None) -> Container:
    """
    Initialize and return the global container.

    Args:
        settings: Optional settings override

    Returns:
        Initialized container
    """
    global _container
    if _container is None:
        _container = Container(settings)
    await _container.initialize()
    return _container
