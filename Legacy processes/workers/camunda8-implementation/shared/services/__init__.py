"""
Business services for Hospital Revenue Cycle.

This module provides:
- Contract pricing service for insurance contract rules
- Database service for async database operations
- Accounting service for CPC 25 compliant provisions
- ERP integration client
- Kafka producer for event publishing
"""

from revenue_cycle.services.contract_service import (
    ContractPricingService,
    ContractService,
    MockContractService,
    DEFAULT_DISCOUNT_RATES,
)
from revenue_cycle.services.database import DatabaseService, get_database_service
from revenue_cycle.services.accounting import AccountingService
from revenue_cycle.services.erp_client import ERPClient, ERPIntegrationError
from revenue_cycle.services.kafka_producer import KafkaProducer, KafkaPublishError, get_kafka_producer
from revenue_cycle.services.pricing import (
    PricingService,
    DatabasePricingService,
    MockPricingService,
)
from revenue_cycle.services.dmn import (
    DMNService,
    ZeebeDMNService,
    FallbackDMNService,
    DMNEvaluationError,
    BillingCalculationDMN,
)
from revenue_cycle.services.tiss import (
    TissXmlGenerator,
    TissValidationResult,
    TissXmlGenerationError,
)

__all__ = [
    # Contract Service
    "ContractService",
    "ContractPricingService",
    "MockContractService",
    "DEFAULT_DISCOUNT_RATES",
    # Database
    "DatabaseService",
    "get_database_service",
    # Accounting
    "AccountingService",
    # ERP Integration
    "ERPClient",
    "ERPIntegrationError",
    # Kafka
    "KafkaProducer",
    "KafkaPublishError",
    "get_kafka_producer",
    # Pricing
    "PricingService",
    "DatabasePricingService",
    "MockPricingService",
    # DMN
    "DMNService",
    "ZeebeDMNService",
    "FallbackDMNService",
    "DMNEvaluationError",
    "BillingCalculationDMN",
    # TISS
    "TissXmlGenerator",
    "TissValidationResult",
    "TissXmlGenerationError",
]
