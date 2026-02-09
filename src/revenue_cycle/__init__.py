"""
Hospital Revenue Cycle Workers - Camunda 8 External Task Workers.

This package provides Python-based external task workers for processing
hospital revenue cycle management workflows in Camunda 8.

Key Features:
- Multi-tenant database support
- Federated business rules via DMN
- Idempotent task processing
- Comprehensive observability (logging, metrics, tracing)
- Integration with TASY ERP, TISS, LIS, PACS systems
"""

__version__ = "1.0.0"
__author__ = "Revenue Cycle Development Team"

from revenue_cycle.workers.base import BaseWorker, WorkerResult

__all__ = [
    "BaseWorker",
    "WorkerResult",
    "__version__",
]
