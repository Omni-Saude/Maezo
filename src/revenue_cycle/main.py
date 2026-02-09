"""
Main entry point for Hospital Revenue Cycle Workers.

Initializes the application, connects to Camunda 8, and starts
processing external tasks.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

import structlog

from revenue_cycle import __version__
from revenue_cycle.config import Settings, get_settings
from revenue_cycle.di.container import Container, get_container, initialize_container
from revenue_cycle.observability.logging import configure_logging

logger = structlog.get_logger(__name__)


class WorkerApplication:
    """
    Main application class for running Camunda 8 external task workers.

    Manages the lifecycle of the application including:
    - Configuration loading
    - Container initialization
    - Worker registration and startup
    - Graceful shutdown
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize the application.

        Args:
            settings: Application settings (loads from environment if not provided)
        """
        self._settings = settings or get_settings()
        self._container: Container | None = None
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """
        Start the worker application.

        Initializes all components and begins processing tasks.
        """
        logger.info(
            "Starting Hospital Revenue Cycle Workers",
            version=__version__,
            environment=self._settings.environment,
        )

        # Initialize container
        self._container = await initialize_container(self._settings)

        # Register signal handlers
        self._setup_signal_handlers()

        # Start workers
        self._running = True
        await self._run_workers()

    async def stop(self) -> None:
        """
        Stop the worker application.

        Gracefully shuts down all components.
        """
        logger.info("Stopping worker application")
        self._running = False
        self._shutdown_event.set()

        if self._container:
            await self._container.shutdown()

        logger.info("Worker application stopped")

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self._handle_signal(s)),
            )

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """
        Handle shutdown signal.

        Args:
            sig: Signal received
        """
        logger.info("Received shutdown signal", signal=sig.name)
        await self.stop()

    async def _run_workers(self) -> None:
        """
        Run all registered workers.

        This is a placeholder for the actual Camunda client integration.
        In production, this would use the camunda-external-task-client.
        """
        if not self._container:
            raise RuntimeError("Container not initialized")

        workers = self._container.get_all_workers()

        logger.info(
            "Starting workers",
            count=len(workers),
            topics=list(workers.keys()),
        )

        # TODO: Integrate with actual Camunda 8 external task client
        # This would typically look like:
        #
        # from camunda.external_task.external_task_client import ExternalTaskClient
        #
        # client = ExternalTaskClient(
        #     base_url=self._settings.camunda.gateway_address,
        #     worker_id=self._settings.camunda.worker_name,
        # )
        #
        # for topic, worker in workers.items():
        #     client.subscribe(
        #         topic=topic,
        #         handler=worker.execute,
        #         lock_duration=worker._lock_duration,
        #         max_jobs=worker._max_jobs,
        #     )
        #
        # await client.start()

        # For now, just wait for shutdown signal
        logger.info(
            "Workers registered, waiting for tasks",
            camunda_url=self._settings.camunda.gateway_address,
        )

        # Keep running until shutdown
        await self._shutdown_event.wait()


def main() -> None:
    """
    Main entry point for the application.

    Sets up logging and runs the async application.
    """
    # Configure logging early
    settings = get_settings()
    configure_logging(settings)

    logger.info(
        "Hospital Revenue Cycle Workers",
        version=__version__,
        python_version=sys.version,
    )

    # Create and run application
    app = WorkerApplication(settings)

    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.exception("Application failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
