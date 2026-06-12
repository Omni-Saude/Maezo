"""CIB Seven External Task Worker Runner.

Bridges worker classes to CIB Seven's External Task REST API
using camunda-external-task-client-python3 (ADR-003).

Supports 3 execution modes (Principle 5):
    # 1. Subdomain-specific (container mode):
    python -m healthcare_platform.shared.runtime.worker_runner --domain revenue_cycle --subdomain billing

    # 2. Domain-wide (swarm/debug mode):
    python -m healthcare_platform.shared.runtime.worker_runner --domain revenue_cycle

    # 3. Topic-specific (dev mode):
    python -m healthcare_platform.shared.runtime.worker_runner --topics billing-calculate-charges,identify-glosa

    # 4. All workers:
    python -m healthcare_platform.shared.runtime.worker_runner --all

Implements Graceful Drain (Principle 6):
    SIGTERM → flag shutdown → /health returns 503 → wait for in-flight tasks
    → drain timeout → exit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from camunda.external_task.external_task import ExternalTask
from camunda.external_task.external_task_worker import ExternalTaskWorker
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext
from healthcare_platform.shared.multi_tenant.context import set_current_tenant, clear_tenant, TenantContext, TENANT_ID_REVERSE
from prometheus_client import Counter, Histogram, Gauge
from tenacity import retry, stop_after_delay, wait_exponential

from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.runtime.registry import WorkerRegistry


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

TASKS_TOTAL = Counter(
    "cib7_worker_tasks_total",
    "Total external tasks processed (per topic/domain)",
    ["topic", "status", "domain", "subdomain"],
)
TASK_DURATION = Histogram(
    "cib7_worker_task_duration_seconds",
    "External task processing duration in seconds (per topic/domain)",
    ["topic", "domain", "subdomain"],
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
)
TASKS_IN_PROGRESS = Gauge(
    "cib7_worker_tasks_in_progress",
    "External tasks currently being processed (per topic/domain)",
    ["topic", "domain", "subdomain"],
)

# Resolved at startup via CLI args
_DOMAIN_LABEL = os.getenv("WORKER_DOMAIN", "unknown")
_SUBDOMAIN_LABEL = os.getenv("WORKER_SUBDOMAIN", "unknown")

# Mock mode: env MOCK_MODE=true → skip real execute, sleep random duration
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")
MOCK_MIN_DELAY = float(os.getenv("MOCK_MIN_DELAY", "0.2"))
MOCK_MAX_DELAY = float(os.getenv("MOCK_MAX_DELAY", "3.0"))
MOCK_FAILURE_RATE = float(os.getenv("MOCK_FAILURE_RATE", "0.05"))

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Graceful Drain Manager (Principle 6)
# ---------------------------------------------------------------------------


class GracefulDrainManager:
    """Manages graceful shutdown of the worker process.

    On SIGTERM:
    1. Sets _shutdown flag → /health returns 503 immediately
    2. Polling loops break on next cycle
    3. In-flight tasks complete normally
    4. Atomic counter tracks active tasks
    5. When counter = 0, process exits
    6. Safety timeout (DRAIN_TIMEOUT_SECONDS) forces exit with warning

    Timeout coordination:
        stop_grace_period (90s) > DRAIN_TIMEOUT (60s) + long_poll_margin (30s)
    """

    def __init__(self, drain_timeout: int = 60) -> None:
        self._shutdown = False
        self._active_tasks = 0
        self._lock = threading.Lock()
        self._drain_timeout = drain_timeout

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown

    @property
    def active_tasks(self) -> int:
        with self._lock:
            return self._active_tasks

    def start_shutdown(self, signal_name: str = "UNKNOWN") -> None:
        """Initiate graceful drain."""
        self._shutdown = True
        logger.info(
            "Graceful drain initiated",
            signal=signal_name,
            active_tasks=self.active_tasks,
            drain_timeout=self._drain_timeout,
        )

    def task_started(self) -> None:
        """Increment in-flight task counter."""
        with self._lock:
            self._active_tasks += 1

    def task_completed(self) -> None:
        """Decrement in-flight task counter."""
        with self._lock:
            self._active_tasks = max(0, self._active_tasks - 1)

    def wait_for_drain(self) -> bool:
        """Block until all in-flight tasks complete or timeout.

        Returns:
            True if all tasks drained cleanly, False if timeout reached.
        """
        deadline = time.monotonic() + self._drain_timeout
        while self.active_tasks > 0 and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            logger.info(
                "Draining in-flight tasks",
                active=self.active_tasks,
                remaining_seconds=round(remaining, 1),
            )
            time.sleep(min(1.0, remaining))

        if self.active_tasks > 0:
            logger.warning(
                "Drain timeout reached, forcing shutdown",
                remaining_tasks=self.active_tasks,
                timeout=self._drain_timeout,
            )
            return False

        logger.info("All tasks drained successfully")
        return True


# Module-level drain manager
drain_manager = GracefulDrainManager(
    drain_timeout=int(os.getenv("DRAIN_TIMEOUT_SECONDS", "60"))
)


# ---------------------------------------------------------------------------
# Health + Metrics HTTP server (Principle 7)
# ---------------------------------------------------------------------------


class _HealthMetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for /health and /metrics endpoints."""

    def do_GET(self) -> None:
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_health(self) -> None:
        """Liveness probe — 200 UP, 503 DRAINING/DOWN."""
        if drain_manager.is_shutting_down:
            self.send_response(503)
            body = json.dumps({
                "status": "DRAINING",
                "active_tasks": drain_manager.active_tasks,
            }).encode()
        else:
            self.send_response(200)
            body = json.dumps({"status": "UP"}).encode()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _handle_metrics(self) -> None:
        """Prometheus metrics endpoint."""
        try:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        except ImportError:
            self.send_response(501)
            self.end_headers()
            self.wfile.write(b"prometheus_client not installed")

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress access logs


def _start_health_server(port: int = 8000) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), _HealthMetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health/metrics endpoint started", port=port, paths=["/health", "/metrics"])
    return server


# ---------------------------------------------------------------------------
# Task handler adapter (with drain-aware task tracking)
# ---------------------------------------------------------------------------


def _make_handler(worker_instance: Any, topic: str):
    """Create a handler function that delegates to the worker's execute method.

    When MOCK_MODE is enabled, skips real execute() and sleeps for a random
    duration (0-10s) before completing the task. Useful for generating
    realistic metrics on dashboards without real business logic.
    """
    d = _DOMAIN_LABEL
    s = _SUBDOMAIN_LABEL

    def handle(task: ExternalTask):
        # Reject new tasks during drain
        if drain_manager.is_shutting_down:
            logger.info("Rejecting task during drain", topic=topic)
            return task.failure(
                error_message="Worker shutting down (graceful drain)",
                error_details="",
                max_retries=task._calculate_retries(3),
                retry_timeout=5000,
            )

        drain_manager.task_started()
        TASKS_IN_PROGRESS.labels(topic=topic, domain=d, subdomain=s).inc()
        start = time.monotonic()
        try:
            # --- MOCK MODE: sleep random + complete ---
            if MOCK_MODE:
                sleep_time = random.uniform(MOCK_MIN_DELAY, MOCK_MAX_DELAY)
                logger.info("Mock execute", topic=topic, sleep_seconds=round(sleep_time, 2))
                time.sleep(sleep_time)

                # Configurable chance of simulated failure for realistic dashboards
                if random.random() < MOCK_FAILURE_RATE:
                    elapsed = time.monotonic() - start
                    TASK_DURATION.labels(topic=topic, domain=d, subdomain=s).observe(elapsed)
                    TASKS_TOTAL.labels(topic=topic, status="failure", domain=d, subdomain=s).inc()
                    retries = task._calculate_retries(3)
                    return task.failure(
                        error_message="[MOCK] Simulated transient failure",
                        error_details="",
                        max_retries=max(retries, 0),
                        retry_timeout=5000,
                    )

                elapsed = time.monotonic() - start
                TASK_DURATION.labels(topic=topic, domain=d, subdomain=s).observe(elapsed)
                TASKS_TOTAL.labels(topic=topic, status="success", domain=d, subdomain=s).inc()
                return task.complete({"_mock": True, "_duration_s": round(elapsed, 2)})

            # --- REAL MODE ---
            # BaseExternalTaskWorker subclasses expect a TaskContext (not raw ExternalTask)
            # and their execute() is synchronous. Older/function-based workers may be async.
            if isinstance(worker_instance, BaseExternalTaskWorker):
                raw_tenant = task.get_tenant_id() or ""
                context = TaskContext(
                    task_id=task.get_task_id(),
                    process_instance_id=task.get_process_instance_id(),
                    tenant_id=raw_tenant,
                    variables=task.get_variables() or {},
                    worker_id=task.get_worker_id() or topic,
                    business_key=task.get_business_key(),
                )
                # Set multi-tenant context (required by @require_tenant decorators)
                _tenant_token = None
                try:
                    # Map CIB Seven tenant (e.g. Maezo_rc) to platform tenant (e.g. austa-hospital)
                    # Default to austa-hospital for dev/test environments
                    platform_tenant = raw_tenant if raw_tenant in TENANT_ID_REVERSE else "austa-hospital"
                    tenant_ctx = TenantContext.from_tenant_id(platform_tenant)
                    _tenant_token = set_current_tenant(tenant_ctx)
                except Exception:
                    logger.debug("Could not set tenant context for %s, continuing without", raw_tenant)
                try:
                    result = worker_instance.execute(context)
                finally:
                    clear_tenant()
            elif asyncio.iscoroutinefunction(worker_instance.execute):
                result = asyncio.run(worker_instance.execute(task))
            else:
                result = worker_instance.execute(task)

            # Determine success: ProcessTaskResult has .success (bool),
            # TaskResult has .status (enum with .SUCCESS value)
            is_success = getattr(result, "success", None)
            if is_success is None:
                status = getattr(result, "status", None)
                is_success = status is not None and status.value == "SUCCESS"

            elapsed = time.monotonic() - start
            TASK_DURATION.labels(topic=topic, domain=d, subdomain=s).observe(elapsed)

            if is_success:
                TASKS_TOTAL.labels(topic=topic, status="success", domain=d, subdomain=s).inc()
                return task.complete(getattr(result, "variables", {}))
            elif getattr(result, "error_code", None):
                TASKS_TOTAL.labels(topic=topic, status="bpmn_error", domain=d, subdomain=s).inc()
                return task.bpmn_error(
                    error_code=result.error_code,
                    error_message=getattr(result, "error_message", "") or "",
                    variables=getattr(result, "variables", {}),
                )
            else:
                TASKS_TOTAL.labels(topic=topic, status="failure", domain=d, subdomain=s).inc()
                retries = task._calculate_retries(3)
                return task.failure(
                    error_message=getattr(result, "error_message", "Worker failure") or "Worker failure",
                    error_details="",
                    max_retries=max(retries, 0),
                    retry_timeout=getattr(result, "retry_timeout", 30000) or 30000,
                )

        except Exception as exc:
            elapsed = time.monotonic() - start
            TASK_DURATION.labels(topic=topic, domain=d, subdomain=s).observe(elapsed)
            TASKS_TOTAL.labels(topic=topic, status="error", domain=d, subdomain=s).inc()
            logger.error("Unhandled worker exception", topic=topic, error=str(exc), exc_info=True)
            retries = task._calculate_retries(3)
            return task.failure(
                error_message=str(exc)[:666],
                error_details="",
                max_retries=max(retries, 0),
                retry_timeout=30000,
            )
        finally:
            TASKS_IN_PROGRESS.labels(topic=topic, domain=d, subdomain=s).dec()
            drain_manager.task_completed()

    return handle


# ---------------------------------------------------------------------------
# Signal handling for graceful shutdown
# ---------------------------------------------------------------------------


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Handle SIGTERM and SIGINT for graceful shutdown."""
    signal_name = signal.Signals(signum).name
    drain_manager.start_shutdown(signal_name=signal_name)


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
    logger.info("Subscribing to topic", topic=topic, engine_url=engine_url)
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
    subdomain: str | None = None,
    run_all: bool = False,
) -> None:
    """Start external task workers and begin polling CIB Seven.

    Args:
        topics: Specific topic names to subscribe to (dev mode).
        domain: Domain to run workers for (swarm mode).
        subdomain: Subdomain within domain (container mode).
        run_all: Run all discovered workers.
    """
    global _DOMAIN_LABEL, _SUBDOMAIN_LABEL
    _DOMAIN_LABEL = domain or os.getenv("WORKER_DOMAIN", "unknown")
    _SUBDOMAIN_LABEL = subdomain or os.getenv("WORKER_SUBDOMAIN", "unknown")

    engine_url = os.getenv("CIBSEVEN_ENGINE_URL", "http://localhost:8080/engine-rest")
    worker_id = os.getenv("WORKER_ID", f"maezo-worker-{os.getpid()}")
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

    # Basic Auth para CIB Seven (sem Keycloak — ADR-020)
    cib7_user = os.getenv("CIB7_USER")
    cib7_password = os.getenv("CIB7_PASSWORD")
    if cib7_user and cib7_password:
        config["auth_basic"] = {
            "username": cib7_user,
            "password": cib7_password,
        }

    # Discover workers (with domain_filter for container mode performance)
    registry = WorkerRegistry()
    registry.discover(domain_filter=domain)

    # Select workers based on execution mode
    if topics:
        entries = {t: registry.get(t) for t in topics if registry.get(t)}
        missing = [t for t in topics if not registry.get(t)]
        if missing:
            logger.warning("Topics not found in registry", missing=missing)
    elif subdomain and domain:
        entries = registry.get_by_subdomain(domain, subdomain)
    elif domain:
        entries = registry.get_by_domain(domain)
    elif run_all:
        entries = registry.all()
    else:
        logger.error("Specify --topics, --domain [--subdomain], or --all")
        sys.exit(1)

    if not entries:
        logger.error(
            "No workers found for given filter",
            domain=domain,
            subdomain=subdomain,
            topics=topics,
        )
        sys.exit(1)

    logger.info(
        "Starting worker runner",
        engine_url=engine_url,
        worker_id=worker_id,
        domain=domain,
        subdomain=subdomain,
        topic_count=len(entries),
        topics=sorted(entries.keys()),
    )

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    # Start health/metrics endpoint
    health_server = _start_health_server(health_port)

    # Instantiate workers (tolerant: log and skip failures — Principle 9)
    active_entries: dict[str, Any] = {}
    for topic, worker_cls in entries.items():
        try:
            worker_instance = worker_cls()
            active_entries[topic] = worker_instance
        except Exception as exc:
            logger.warning(
                "Failed to instantiate worker, skipping",
                topic=topic,
                worker=worker_cls.__name__,
                error=str(exc),
            )

    if not active_entries:
        logger.error("No workers could be instantiated")
        sys.exit(1)

    logger.info(
        "Worker instantiation complete",
        total=len(active_entries),
        skipped=len(entries) - len(active_entries),
    )

    # Subscribe to each topic in its own thread (subscribe() blocks)
    subscription_threads: list[threading.Thread] = []
    for topic, worker_instance in active_entries.items():
        handler = _make_handler(worker_instance, topic)
        logger.info("Subscribing to topic", topic=topic, worker=type(worker_instance).__name__)

        t = threading.Thread(
            target=_subscribe_with_retry,
            args=(worker_id, engine_url, config, topic, handler),
            name=f"worker-{topic}",
            daemon=True,
        )
        t.start()
        subscription_threads.append(t)

    logger.info(
        "All subscriptions started",
        thread_count=len(subscription_threads),
    )

    # Block main thread until shutdown signal
    try:
        while not drain_manager.is_shutting_down:
            time.sleep(1)
    except KeyboardInterrupt:
        drain_manager.start_shutdown(signal_name="KeyboardInterrupt")

    # Wait for in-flight tasks to drain
    drained = drain_manager.wait_for_drain()
    health_server.shutdown()
    sys.exit(0 if drained else 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="MAEZO CIB Seven Worker Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--topics", help="Comma-separated topic names")
    group.add_argument(
        "--domain",
        choices=[
            "revenue_cycle",
            "patient_access",
            "clinical_operations",
            "platform_services",
        ],
        help="Run all workers for a domain",
    )
    group.add_argument("--all", action="store_true", help="Run all discovered workers")

    parser.add_argument(
        "--subdomain",
        help="Run workers for a specific subdomain within a domain (container mode)",
    )

    args = parser.parse_args()

    # Validate --subdomain requires --domain
    if args.subdomain and not args.domain:
        parser.error("--subdomain requires --domain")

    topics = args.topics.split(",") if args.topics else None
    run(
        topics=topics,
        domain=args.domain,
        subdomain=args.subdomain,
        run_all=args.all,
    )


if __name__ == "__main__":
    main()
