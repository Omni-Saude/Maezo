"""Mock client classes para testes."""

from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock
from datetime import datetime


class MockCamundaClient:
    """Mock client para Camunda Engine."""

    def __init__(self):
        self.fetch_and_lock = AsyncMock()
        self.complete = AsyncMock()
        self.handle_failure = AsyncMock()
        self.handle_bpmn_error = AsyncMock()
        self.start_process = AsyncMock()
        self.get_process_instance = AsyncMock()
        self.get_variables = AsyncMock()
        self.set_variables = AsyncMock()

        # Configure default behaviors
        self._configure_defaults()

    def _configure_defaults(self):
        """Configura comportamentos padrão dos mocks."""
        self.fetch_and_lock.return_value = []
        self.complete.return_value = None
        self.start_process.return_value = {
            "id": "proc-inst-001",
            "definitionId": "process:1:def-001",
        }
        self.get_process_instance.return_value = {
            "id": "proc-inst-001",
            "ended": False,
            "suspended": False,
        }


class MockFHIRClient:
    """Mock client para FHIR Server."""

    def __init__(self):
        self.create = AsyncMock()
        self.read = AsyncMock()
        self.update = AsyncMock()
        self.delete = AsyncMock()
        self.search = AsyncMock()
        self.validate_resource = AsyncMock()
        self.get_capability_statement = AsyncMock()

        self._configure_defaults()

    def _configure_defaults(self):
        """Configura comportamentos padrão dos mocks."""
        self.validate_resource.return_value = True
        self.create.return_value = {
            "resourceType": "Patient",
            "id": "patient-001",
        }
        self.search.return_value = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": 0,
            "entry": [],
        }


class MockDatabaseClient:
    """Mock client para banco de dados."""

    def __init__(self):
        self.execute = AsyncMock()
        self.fetch_one = AsyncMock()
        self.fetch_all = AsyncMock()
        self.begin_transaction = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()

        self._configure_defaults()

    def _configure_defaults(self):
        """Configura comportamentos padrão dos mocks."""
        self.execute.return_value = None
        self.fetch_one.return_value = None
        self.fetch_all.return_value = []
        self.commit.return_value = None
        self.rollback.return_value = None


class MockERPClient:
    """Mock client para sistema ERP (TASY/MV Soul)."""

    def __init__(self):
        self.create_invoice = AsyncMock()
        self.get_contract_rules = AsyncMock()
        self.calculate_billing = AsyncMock()
        self.submit_glosa = AsyncMock()
        self.get_patient = AsyncMock()
        self.sync_patient = AsyncMock()
        self.create_appointment = AsyncMock()

        self._configure_defaults()

    def _configure_defaults(self):
        """Configura comportamentos padrão dos mocks."""
        self.create_invoice.return_value = {
            "invoice_id": "INV-001",
            "status": "created",
        }
        self.get_contract_rules.return_value = {
            "insurance_type": "AMB",
            "table": "AMB",
            "rules": {},
        }
        self.calculate_billing.return_value = {
            "total_amount": 150.00,
            "procedures": [],
        }
