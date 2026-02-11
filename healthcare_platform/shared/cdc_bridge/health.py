"""Liveness, readiness, and metrics HTTP endpoints."""

from __future__ import annotations

import json
import logging
from aiohttp import web

logger = logging.getLogger(__name__)

# Simple in-process counters; replace with prometheus_client if needed.
_metrics: dict[str, int] = {
    "messages_consumed_total": 0,
    "processing_errors_total": 0,
    "process_starts_total": 0,
    "message_correlations_total": 0,
    "dead_letter_total": 0,
}


def inc(name: str, amount: int = 1) -> None:
    _metrics[name] = _metrics.get(name, 0) + amount


class HealthServer:
    """Async HTTP server exposing health, readiness, and Prometheus metrics."""

    def __init__(self, port: int, kafka_ready_check) -> None:
        self._port = port
        self._kafka_ready = kafka_ready_check
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/ready", self._ready)
        app.router.add_get("/metrics", self._prom_metrics)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("Health server listening on port %d", self._port)

    async def close(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _health(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "UP"})

    async def _ready(self, _: web.Request) -> web.Response:
        ready = await self._kafka_ready()
        status = "READY" if ready else "NOT_READY"
        code = 200 if ready else 503
        return web.json_response({"status": status}, status=code)

    async def _prom_metrics(self, _: web.Request) -> web.Response:
        lines = [
            f"cdc_bridge_{k} {v}" for k, v in sorted(_metrics.items())
        ]
        return web.Response(
            text="\n".join(lines) + "\n",
            content_type="text/plain",
        )
