"""CDC-to-BPM Bridge Service.

Consumes Debezium CDC events from Tasy ERP via Kafka and starts/correlates
CIB Seven process instances per ADR-004 and ADR-006.
"""

from healthcare_platform.shared.cdc_bridge.app import CDCBridgeApp
from healthcare_platform.shared.cdc_bridge.consumer import EventConsumer
from healthcare_platform.shared.cdc_bridge.process_starter import ProcessStarter

__all__ = ["CDCBridgeApp", "EventConsumer", "ProcessStarter"]
