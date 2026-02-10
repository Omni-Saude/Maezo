"""
Health Check Endpoints - Liveness and Readiness Probes.

ADR-010: Kubernetes-compatible health checks.
Exposes /healthz (liveness) and /readyz (readiness) via a lightweight ASGI app.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from prometheus_client import Gauge

from healthcare_platform.shared.i18n import _

HEALTH_STATUS = Gauge(
    "cib7_health_status",
    "Health check status (1=healthy, 0=unhealthy)",
    labelnames=["check_name", "probe_type"],
)


class ProbeType(str, Enum):
    LIVENESS = "liveness"
    READINESS = "readiness"


@dataclass
class CheckResult:
    name: str
    healthy: bool
    message: str = ""
    latency_ms: float = 0.0


@dataclass
class HealthRegistry:
    """Registry for health check functions."""

    _liveness_checks: dict[str, Callable[[], Awaitable[CheckResult]]] = field(
        default_factory=dict
    )
    _readiness_checks: dict[str, Callable[[], Awaitable[CheckResult]]] = field(
        default_factory=dict
    )

    def register_liveness(
        self, name: str, check: Callable[[], Awaitable[CheckResult]]
    ) -> None:
        self._liveness_checks[name] = check

    def register_readiness(
        self, name: str, check: Callable[[], Awaitable[CheckResult]]
    ) -> None:
        self._readiness_checks[name] = check

    async def run_liveness(self) -> tuple[bool, list[CheckResult]]:
        return await self._run_checks(self._liveness_checks, ProbeType.LIVENESS)

    async def run_readiness(self) -> tuple[bool, list[CheckResult]]:
        return await self._run_checks(self._readiness_checks, ProbeType.READINESS)

    async def _run_checks(
        self,
        checks: dict[str, Callable[[], Awaitable[CheckResult]]],
        probe: ProbeType,
    ) -> tuple[bool, list[CheckResult]]:
        results: list[CheckResult] = []
        all_healthy = True
        for name, check_fn in checks.items():
            start = time.monotonic()
            try:
                result = await check_fn()
            except Exception as exc:
                result = CheckResult(name=name, healthy=False, message=str(exc))
            result.latency_ms = (time.monotonic() - start) * 1000
            HEALTH_STATUS.labels(check_name=name, probe_type=probe.value).set(
                1.0 if result.healthy else 0.0
            )
            results.append(result)
            if not result.healthy:
                all_healthy = False
        return all_healthy, results


# Module-level singleton
health_registry = HealthRegistry()


def build_health_response(
    healthy: bool, results: list[CheckResult]
) -> dict[str, Any]:
    """Build a JSON-serializable health response."""
    return {
        "status": "healthy" if healthy else "unhealthy",
        "checks": [
            {
                "name": r.name,
                "status": "pass" if r.healthy else "fail",
                "message": r.message,
                "latency_ms": round(r.latency_ms, 2),
            }
            for r in results
        ],
    }


# ---------------------------------------------------------------------------
# Common health checks (register at startup)
# ---------------------------------------------------------------------------


async def check_cib7_engine(base_url: str = "http://localhost:8080") -> CheckResult:
    """Check CIB7 engine REST API is reachable."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/engine-rest/engine")
            return CheckResult(
                name="cib7_engine",
                healthy=resp.status_code == 200,
                message=f"status={resp.status_code}",
            )
    except Exception as exc:
        return CheckResult(name="cib7_engine", healthy=False, message=str(exc))


async def check_database(dsn: str) -> CheckResult:
    """Check database connectivity."""
    import asyncpg

    try:
        conn = await asyncpg.connect(dsn, timeout=5.0)
        await conn.execute("SELECT 1")
        await conn.close()
        return CheckResult(name="database", healthy=True, message="connected")
    except Exception as exc:
        return CheckResult(name="database", healthy=False, message=str(exc))
