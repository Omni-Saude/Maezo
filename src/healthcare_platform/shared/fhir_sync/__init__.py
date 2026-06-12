"""FHIR Sync Service — CDC events to HAPI FHIR R4.

Consumes Debezium CDC events from Kafka, transforms via Tasy-to-FHIR
adapters, and persists to HAPI FHIR using conditional upsert.
"""

from healthcare_platform.shared.fhir_sync.app import FHIRSyncApp
from healthcare_platform.shared.fhir_sync.consumer import FHIRSyncConsumer

__all__ = ["FHIRSyncApp", "FHIRSyncConsumer"]
