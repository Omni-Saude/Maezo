"""Unit tests for CDC event parser."""

from __future__ import annotations

import pytest

from healthcare_platform.shared.cdc_bridge.event_parser import (
    CDCEvent,
    OperationType,
    ProcessAction,
    map_to_process_action,
    parse_cdc_event,
)


class TestParseCDCEvent:
    """Test parsing raw Debezium messages into CDCEvent objects."""

    def test_parse_create_operation(self) -> None:
        raw = {
            "op": "c",
            "source": {
                "table": "ATENDIMENTO",
                "ts_ms": 1707696000000,
                "db": "AUSTA",
            },
            "after": {
                "nr_atendimento": "12345",
                "cd_paciente": "PAC001",
                "dt_entrada": "2026-02-11",
            },
            "before": None,
        }
        event = parse_cdc_event(raw)
        assert event is not None
        assert event.operation == OperationType.CREATE
        assert event.table_name == "ATENDIMENTO"
        assert event.record_data["nr_atendimento"] == "12345"
        assert event.before_data is None
        assert event.timestamp_ms == 1707696000000

    def test_parse_update_operation(self) -> None:
        raw = {
            "op": "u",
            "source": {"table": "CONTA_MEDICA", "ts_ms": 1707696001000, "db": "AUSTA"},
            "after": {"nr_conta": "C-001", "vl_total": "1500.00", "st_conta": "A"},
            "before": {"nr_conta": "C-001", "vl_total": "1000.00", "st_conta": "P"},
        }
        event = parse_cdc_event(raw)
        assert event is not None
        assert event.operation == OperationType.UPDATE
        assert event.table_name == "CONTA_MEDICA"
        assert event.record_data["vl_total"] == "1500.00"
        assert event.before_data is not None
        assert event.before_data["vl_total"] == "1000.00"

    def test_parse_delete_operation(self) -> None:
        raw = {
            "op": "d",
            "source": {"table": "ITEM_CONTA", "ts_ms": 1707696002000, "db": "AUSTA"},
            "after": None,
            "before": {"nr_sequencia": "SEQ123", "nr_conta": "C-001"},
        }
        event = parse_cdc_event(raw)
        assert event is not None
        assert event.operation == OperationType.DELETE
        assert event.record_data == {}
        assert event.before_data is not None

    def test_parse_missing_op_field(self) -> None:
        raw = {"source": {"table": "TEST"}, "after": {}}
        event = parse_cdc_event(raw)
        assert event is None

    def test_parse_unknown_operation_type(self) -> None:
        raw = {"op": "x", "source": {"table": "TEST"}, "after": {}}
        event = parse_cdc_event(raw)
        assert event is None

    def test_parse_with_null_after(self) -> None:
        raw = {"op": "c", "source": {"table": "TEST", "ts_ms": 0, "db": ""}, "after": None}
        event = parse_cdc_event(raw)
        assert event is not None
        assert event.record_data == {}


class TestMapToProcessAction:
    """Test mapping CDC events to BPM process actions."""

    def test_map_atendimento_create_to_start_process(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="ATENDIMENTO",
            record_data={
                "nr_atendimento": "ATD-12345",
                "cd_paciente": "PAC001",
                "dt_entrada": "2026-02-11",
            },
            before_data=None,
            timestamp_ms=1707696000000,
            source_db="AUSTA",
        )
        action = map_to_process_action(event, tenant_id="austa")
        assert action is not None
        assert action.action_type == "start"
        assert action.process_key == "encounter-registration"
        assert action.message_name is None
        assert action.business_key == "ATD-12345"
        assert action.tenant_id == "austa"
        assert action.variables["cdc_table"] == "ATENDIMENTO"
        assert action.variables["cdc_operation"] == "c"
        assert action.variables["cd_paciente"] == "PAC001"

    def test_map_conta_medica_create_to_start_process(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="CONTA_MEDICA",
            record_data={"nr_conta": "C-001", "vl_total": "1500.00"},
            before_data=None,
            timestamp_ms=1707696001000,
            source_db="AUSTA",
        )
        action = map_to_process_action(event)
        assert action is not None
        assert action.action_type == "start"
        assert action.process_key == "revenue-cycle-main"
        assert action.business_key == "C-001"

    def test_map_item_conta_create_to_correlate_message(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="ITEM_CONTA",
            record_data={"nr_conta": "C-001", "cd_item": "ITEM123", "vl_item": "150.00"},
            before_data=None,
            timestamp_ms=1707696002000,
            source_db="AUSTA",
        )
        action = map_to_process_action(event)
        assert action is not None
        assert action.action_type == "correlate"
        assert action.message_name == "MSG_CHARGE_CAPTURED"
        assert action.process_key is None
        assert action.business_key == "C-001"

    def test_map_prescricao_create_to_correlate_message(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="PRESCRICAO",
            record_data={"nr_atendimento": "ATD-12345", "cd_prescricao": "PRESC001"},
            before_data=None,
            timestamp_ms=1707696003000,
            source_db="AUSTA",
        )
        action = map_to_process_action(event)
        assert action is not None
        assert action.action_type == "correlate"
        assert action.message_name == "MSG_PRESCRIPTION_CREATED"
        assert action.business_key == "ATD-12345"

    def test_map_unmapped_table_returns_none(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="UNKNOWN_TABLE",
            record_data={"id": "123"},
            before_data=None,
            timestamp_ms=0,
            source_db="",
        )
        action = map_to_process_action(event)
        assert action is None

    def test_map_unmapped_operation_returns_none(self) -> None:
        event = CDCEvent(
            operation=OperationType.UPDATE,  # Only CREATE mapped for ATENDIMENTO
            table_name="ATENDIMENTO",
            record_data={"nr_atendimento": "ATD-001"},
            before_data=None,
            timestamp_ms=0,
            source_db="",
        )
        action = map_to_process_action(event)
        assert action is None

    def test_map_missing_business_key_returns_none(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="ATENDIMENTO",
            record_data={"cd_paciente": "PAC001"},  # Missing nr_atendimento
            before_data=None,
            timestamp_ms=0,
            source_db="",
        )
        action = map_to_process_action(event)
        assert action is None

    def test_variables_exclude_none_values(self) -> None:
        event = CDCEvent(
            operation=OperationType.CREATE,
            table_name="ATENDIMENTO",
            record_data={
                "nr_atendimento": "ATD-001",
                "cd_paciente": "PAC001",
                "dt_alta": None,
            },
            before_data=None,
            timestamp_ms=0,
            source_db="",
        )
        action = map_to_process_action(event)
        assert action is not None
        assert "dt_alta" not in action.variables
        assert action.variables["cd_paciente"] == "PAC001"
