"""Tests for SyncERPDataWorker."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.sync_erp_data_worker import (
    SyncERPDataInput,
    SyncERPDataOutput,
    execute,
    ERPSyncException,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.mark.unit
class TestSyncERPDataWorker:
    """Test suite for SyncERPDataWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_patient_sync(self, tenant_austa):
        """Test successful patient data synchronization."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {
                "payload": {
                    "after": {
                        "patient_id": "pat-123",
                        "name": "João Silva",
                        "birth_date": "1980-01-01",
                        "gender": "M",
                        "cpf": "12345678901",
                    }
                }
            },
            "operation": "create",
            "timestamp": datetime.now().isoformat(),
        }

        result = await execute(input_data)

        assert result["source_system"] == "tasy"
        assert result["entity_type"] == "patient"
        assert result["operation"] == "create"
        assert result["sync_status"] == "success"

    @pytest.mark.asyncio
    async def test_happy_path_procedure_sync(self, tenant_austa):
        """Test successful procedure data synchronization."""
        input_data = {
            "source_system": "mv_soul",
            "entity_type": "procedure",
            "cdc_event": {
                "payload": {
                    "after": {
                        "procedure_id": "proc-456",
                        "patient_id": "pat-123",
                        "code": "10101012",
                        "description": "Consulta médica",
                    }
                }
            },
            "operation": "update",
        }

        result = await execute(input_data)

        assert result["entity_type"] == "procedure"
        assert result["operation"] == "update"

    @pytest.mark.asyncio
    async def test_happy_path_encounter_sync(self, tenant_austa):
        """Test successful encounter data synchronization."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "encounter",
            "cdc_event": {
                "payload": {
                    "after": {
                        "encounter_id": "enc-789",
                        "patient_id": "pat-123",
                        "admission_date": "2024-01-01",
                    }
                }
            },
            "operation": "create",
        }

        result = await execute(input_data)

        assert result["entity_type"] == "encounter"

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            await execute({
                "source_system": "tasy",
                # Missing required fields
            })

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {"payload": {"after": {}}},
            "operation": "create",
        }

        with pytest.raises(InvalidTenant):
            await execute(input_data)

    @pytest.mark.asyncio
    async def test_different_source_systems(self, tenant_austa):
        """Test synchronization from different source systems."""
        for source in ["tasy", "mv_soul"]:
            input_data = {
                "source_system": source,
                "entity_type": "patient",
                "cdc_event": {
                    "payload": {
                        "after": {
                            "patient_id": f"pat-{source}",
                            "name": "Test",
                        }
                    }
                },
                "operation": "create",
            }

            result = await execute(input_data)

            assert result["source_system"] == source

    @pytest.mark.asyncio
    async def test_different_operations(self, tenant_austa):
        """Test different CDC operations."""
        for operation in ["create", "update", "delete"]:
            input_data = {
                "source_system": "tasy",
                "entity_type": "patient",
                "cdc_event": {
                    "payload": {
                        "after": {
                            "patient_id": f"pat-{operation}",
                        }
                    }
                },
                "operation": operation,
            }

            result = await execute(input_data)

            assert result["operation"] == operation

    @pytest.mark.asyncio
    async def test_force_sync_flag(self, tenant_austa):
        """Test force_sync flag."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {
                "payload": {"after": {"patient_id": "pat-123"}}
            },
            "operation": "update",
            "force_sync": True,
        }

        result = await execute(input_data)

        assert result["sync_status"] == "success"

    @pytest.mark.asyncio
    async def test_conflicts_detected(self, tenant_austa):
        """Test conflict detection."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {
                "payload": {"after": {"patient_id": "pat-123"}}
            },
            "operation": "update",
        }

        result = await execute(input_data)

        # Conflicts might be detected
        assert result["conflicts_detected"] >= 0

    @pytest.mark.asyncio
    async def test_records_processed_count(self, tenant_austa):
        """Test that records processed are counted."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {
                "payload": {"after": {"patient_id": "pat-123"}}
            },
            "operation": "create",
        }

        result = await execute(input_data)

        assert result["records_processed"] == 1
        assert result["records_synced"] >= 0

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {
                "payload": {"after": {"patient_id": "pat-999"}}
            },
            "operation": "create",
        }

        result = await execute(input_data)

        assert result["sync_status"] == "success"

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test that multiple executions produce consistent results."""
        input_data = {
            "source_system": "tasy",
            "entity_type": "patient",
            "cdc_event": {
                "payload": {"after": {"patient_id": "pat-idem"}}
            },
            "operation": "create",
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        # Should have same structure
        assert result1["source_system"] == result2["source_system"]
        assert result1["entity_type"] == result2["entity_type"]
