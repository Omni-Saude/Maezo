"""CIB Seven External Task Worker Runner.

Bridges the 184 worker classes to CIB Seven's External Task REST API
using camunda-external-task-client-python3 (ADR-003).

Usage:
    # Run all workers for a domain:
    python -m healthcare_platform.shared.runtime.worker_runner --domain revenue_cycle

    # Run specific topics:
    python -m healthcare_platform.shared.runtime.worker_runner --topics billing-calculate-charges,identify-glosa

    # Run all workers:
    python -m healthcare_platform.shared.runtime.worker_runner --all
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from camunda.external_task.external_task import ExternalTask
from camunda.external_task.external_task_worker import ExternalTaskWorker
from tenacity import retry, stop_after_delay, wait_exponential

from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.runtime.registry import WorkerRegistry

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Health check HTTP server (K8s liveness/readiness probes)
# ---------------------------------------------------------------------------

_healthy = True
_shutdown = False


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health" and _healthy and not _shutdown:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"UP"}')
        else:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"status":"DOWN"}')

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress access logs


def _start_health_server(port: int = 8000) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health endpoint started", port=port)
    return server


# ---------------------------------------------------------------------------
# Task handler adapter
# ---------------------------------------------------------------------------


def _make_handler(worker_instance: Any, topic: str):
    """Create a handler function that delegates to the worker's process_task method."""

    def handle(task: ExternalTask):
        variables = task.get_variables() or {}

        try:
            result = asyncio.run(worker_instance.execute(task))

            if result.success:
                return task.complete(result.variables)
            elif result.error_code:
                return task.bpmn_error(
                    error_code=result.error_code,
                    error_message=result.error_message or "",
                    variables=result.variables,
                )
            else:
                retries = (task.get_retries() or 3) - 1
                return task.failure(
                    error_message=result.error_message or "Worker failure",
                    error_details="",
                    max_retries=max(retries, 0),
                    retry_timeout=result.retry_timeout or 30000,
                )

        except Exception as exc:
            logger.error("Unhandled worker exception", topic=topic, error=str(exc), exc_info=True)
            retries = (task.get_retries() or 3) - 1
            return task.failure(
                error_message=str(exc)[:666],
                error_details="",
                max_retries=max(retries, 0),
                retry_timeout=30000,
            )

    return handle


# ---------------------------------------------------------------------------
# Signal handling for graceful shutdown
# ---------------------------------------------------------------------------


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Handle SIGTERM and SIGINT for graceful shutdown."""
    global _shutdown
    signal_name = signal.Signals(signum).name
    logger.info("Received shutdown signal", signal=signal_name)
    _shutdown = True


# ---------------------------------------------------------------------------
# Connection retry wrapper
# ---------------------------------------------------------------------------


@retry(stop=stop_after_delay(120), wait=wait_exponential(multiplier=1, min=2, max=30))
def _subscribe_with_retry(
    worker_id: str,
    engine_url: str,
    config: dict[str, Any],
    topic: str,
    handler: Any,
) -> None:
    """Subscribe to a topic with connection retry logic."""
    logger.info("Attempting to subscribe to topic", topic=topic, engine_url=engine_url)
    ExternalTaskWorker(
        worker_id=worker_id,
        base_url=engine_url,
        config=config,
    ).subscribe(topic, handler)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run(
    topics: list[str] | None = None,
    domain: str | None = None,
    run_all: bool = False,
) -> None:
    """Start external task workers and begin polling CIB Seven."""

    engine_url = os.getenv("CIBSEVEN_ENGINE_URL", "http://localhost:8080/engine-rest")
    worker_id = os.getenv("WORKER_ID", f"maestro-worker-{os.getpid()}")
    health_port = int(os.getenv("HEALTH_PORT", "8000"))

    config = {
        "maxTasks": int(os.getenv("WORKER_MAX_TASKS", "10")),
        "lockDuration": int(os.getenv("WORKER_LOCK_DURATION", "300000")),
        "asyncResponseTimeout": int(os.getenv("WORKER_LONG_POLL_MS", "30000")),
        "retries": 3,
        "retryTimeout": 30000,
        "sleepSeconds": int(os.getenv("WORKER_SLEEP_SECONDS", "5")),
        "isDebug": os.getenv("WORKER_DEBUG", "false").lower() == "true",
    }

    # Keycloak auth if configured
    kc_client_id = os.getenv("KEYCLOAK_CLIENT_ID")
    kc_client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
    if kc_client_id and kc_client_secret:
        config["auth_basic"] = {
            "username": kc_client_id,
            "password": kc_client_secret,
        }

    # Discover workers
    registry = WorkerRegistry()
    registry.discover()

    if topics:
        entries = {t: registry.get(t) for t in topics if registry.get(t)}
    elif domain:
        entries = registry.get_by_domain(domain)
    elif run_all:
        entries = registry.all()
    else:
        logger.error("Specify --topics, --domain, or --all")
        sys.exit(1)

    if not entries:
        logger.error("No workers found for given filter")
        sys.exit(1)

    logger.info(
        "Starting worker runner",
        engine_url=engine_url,
        worker_id=worker_id,
        topic_count=len(entries),
        topics=list(entries.keys()),
    )

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    # Start health endpoint
    health_server = _start_health_server(health_port)

    # Subscribe to each topic with retry
    for topic, worker_cls in entries.items():
        worker_instance = worker_cls()
        handler = _make_handler(worker_instance, topic)

        logger.info("Subscribing to topic", topic=topic, worker=worker_cls.__name__)
        _subscribe_with_retry(worker_id, engine_url, config, topic, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Maestro CIB Seven Worker Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--topics", help="Comma-separated topic names")
    group.add_argument(
        "--domain",
        choices=["revenue_cycle", "patient_access", "clinical_operations", "platform_services"],
        help="Run all workers for a domain",
    )
    group.add_argument("--all", action="store_true", help="Run all discovered workers")

    args = parser.parse_args()

    topics = args.topics.split(",") if args.topics else None
    run(topics=topics, domain=args.domain, run_all=args.all)


if __name__ == "__main__":
    main()
