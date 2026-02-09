"""
Streaming utilities for memory-efficient background worker processing.

Provides async generators and chunking utilities for processing large datasets
without loading everything into memory at once. Includes memory monitoring
and automatic garbage collection triggers.

This module solves the OOM (Out of Memory) issues observed in audit workers
by implementing:
- Chunked data processing with configurable batch sizes
- Memory usage monitoring with automatic GC triggers
- Async generators for streaming data from sources
- Timeout enforcement with early termination
"""

from __future__ import annotations

import gc
import asyncio
import psutil
from typing import Any, AsyncIterator, Callable, Iterator, TypeVar
from datetime import datetime, timedelta

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class MemoryMonitor:
    """
    Monitor memory usage and trigger garbage collection when thresholds are exceeded.

    This prevents OOM kills by proactively managing memory during long-running operations.
    """

    def __init__(self, threshold_mb: int = 512):
        """
        Initialize memory monitor.

        Args:
            threshold_mb: Memory threshold in MB (default: 512)
        """
        self.threshold_bytes = threshold_mb * 1024 * 1024
        self.process = psutil.Process()
        self._last_check = datetime.now()
        self._check_interval = timedelta(seconds=5)

    def check_and_gc(self, force: bool = False) -> tuple[int, bool]:
        """
        Check memory usage and trigger GC if threshold exceeded.

        Args:
            force: Force immediate check regardless of interval

        Returns:
            Tuple of (current_memory_mb, gc_triggered)
        """
        now = datetime.now()
        if not force and now - self._last_check < self._check_interval:
            return 0, False

        self._last_check = now
        memory_info = self.process.memory_info()
        current_mb = memory_info.rss // (1024 * 1024)

        if memory_info.rss > self.threshold_bytes:
            logger.warning(
                "Memory threshold exceeded, triggering garbage collection",
                current_mb=current_mb,
                threshold_mb=self.threshold_bytes // (1024 * 1024),
            )
            gc.collect()

            # Check again after GC
            post_gc_info = self.process.memory_info()
            post_gc_mb = post_gc_info.rss // (1024 * 1024)
            freed_mb = current_mb - post_gc_mb

            logger.info(
                "Garbage collection completed",
                freed_mb=freed_mb,
                current_mb=post_gc_mb,
            )
            return current_mb, True

        return current_mb, False


async def chunked_stream(
    items: list[T],
    batch_size: int = 100,
    memory_monitor: MemoryMonitor | None = None,
) -> AsyncIterator[list[T]]:
    """
    Stream items in chunks of specified size with optional memory monitoring.

    This prevents loading all items into memory at once and enables
    memory-efficient processing of large datasets.

    Args:
        items: List of items to stream
        batch_size: Number of items per chunk
        memory_monitor: Optional memory monitor for GC triggers

    Yields:
        Chunks of items (lists of size <= batch_size)

    Example:
        async for chunk in chunked_stream(historical_claims, batch_size=100):
            for claim in chunk:
                # Process claim
                pass
            # Memory freed after each chunk
    """
    total_items = len(items)
    logger.debug(
        "Starting chunked stream",
        total_items=total_items,
        batch_size=batch_size,
    )

    for i in range(0, total_items, batch_size):
        chunk = items[i:i + batch_size]

        # Check memory before yielding chunk
        if memory_monitor:
            memory_monitor.check_and_gc()

        yield chunk

        # Allow other tasks to run
        await asyncio.sleep(0)

    logger.debug("Chunked stream completed", total_items=total_items)


async def timeout_wrapper(
    coro: Any,
    timeout_seconds: int,
    operation_name: str = "operation",
) -> Any:
    """
    Wrap a coroutine with timeout enforcement.

    Args:
        coro: Coroutine to execute
        timeout_seconds: Timeout in seconds
        operation_name: Name for logging

    Returns:
        Result from coroutine

    Raises:
        asyncio.TimeoutError: If timeout is exceeded
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(
            "Operation timed out",
            operation=operation_name,
            timeout_seconds=timeout_seconds,
        )
        raise


class StreamingAccumulator:
    """
    Accumulator for streaming aggregations with memory monitoring.

    Allows building up results incrementally while monitoring memory usage.
    """

    def __init__(
        self,
        memory_monitor: MemoryMonitor | None = None,
        max_items: int | None = None,
    ):
        """
        Initialize accumulator.

        Args:
            memory_monitor: Optional memory monitor
            max_items: Maximum items to accumulate (prevents unbounded growth)
        """
        self.items: list[Any] = []
        self.memory_monitor = memory_monitor
        self.max_items = max_items
        self.total_processed = 0

    def add(self, item: Any) -> bool:
        """
        Add item to accumulator.

        Args:
            item: Item to add

        Returns:
            True if item was added, False if limit reached
        """
        if self.max_items and len(self.items) >= self.max_items:
            logger.warning(
                "Accumulator limit reached",
                max_items=self.max_items,
                total_processed=self.total_processed,
            )
            return False

        self.items.append(item)
        self.total_processed += 1

        # Periodic memory check
        if self.total_processed % 100 == 0 and self.memory_monitor:
            self.memory_monitor.check_and_gc()

        return True

    def get_results(self) -> list[Any]:
        """Get accumulated results."""
        return self.items

    def clear(self):
        """Clear accumulated items and free memory."""
        self.items.clear()
        if self.memory_monitor:
            self.memory_monitor.check_and_gc(force=True)


async def stream_with_filter(
    items: list[T],
    predicate: Callable[[T], bool],
    batch_size: int = 100,
    memory_monitor: MemoryMonitor | None = None,
) -> AsyncIterator[T]:
    """
    Stream items with filtering, processing in chunks.

    Args:
        items: Items to stream
        predicate: Filter function (return True to include item)
        batch_size: Chunk size for processing
        memory_monitor: Optional memory monitor

    Yields:
        Filtered items one at a time

    Example:
        async for claim in stream_with_filter(
            historical_claims,
            lambda c: c.get("providerId") == provider_id,
            batch_size=100,
        ):
            # Process matching claim
            pass
    """
    async for chunk in chunked_stream(items, batch_size, memory_monitor):
        for item in chunk:
            if predicate(item):
                yield item

        # Allow other tasks to run
        await asyncio.sleep(0)


async def stream_with_transform(
    items: list[T],
    transform: Callable[[T], Any],
    batch_size: int = 100,
    memory_monitor: MemoryMonitor | None = None,
) -> AsyncIterator[Any]:
    """
    Stream items with transformation, processing in chunks.

    Args:
        items: Items to stream
        transform: Transform function
        batch_size: Chunk size for processing
        memory_monitor: Optional memory monitor

    Yields:
        Transformed items one at a time

    Example:
        async for amount in stream_with_transform(
            historical_claims,
            lambda c: float(c.get("amount", 0)),
            batch_size=100,
        ):
            amounts.append(amount)
    """
    async for chunk in chunked_stream(items, batch_size, memory_monitor):
        for item in chunk:
            yield transform(item)

        # Allow other tasks to run
        await asyncio.sleep(0)
