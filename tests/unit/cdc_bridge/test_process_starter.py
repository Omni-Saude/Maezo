"""Unit tests for CIB7 process starter with Basic Auth (ADR-020)."""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import MagicMock, patch

import httpx
import pytest

from healthcare_platform.shared.cdc_bridge.config import CIB7Settings
from healthcare_platform.shared.cdc_bridge.process_starter import ProcessStarter


@pytest.fixture
def cib7_settings() -> CIB7Settings:
    return CIB7Settings(
        engine_url="http://test-engine:8080",
        tenant_id="test-tenant",
        user="admin",
        password="test-password",
    )


@pytest.fixture
async def process_starter(
    cib7_settings: CIB7Settings,
) -> AsyncGenerator[ProcessStarter, None]:
    starter = ProcessStarter(cib7_settings)
    await starter.start()
    yield starter
    await starter.close()


class TestBasicAuth:
    """Test Basic Auth configuration on the HTTP client."""

    @pytest.mark.asyncio
    async def test_client_created_with_basic_auth(self, cib7_settings: CIB7Settings) -> None:
        starter = ProcessStarter(cib7_settings)
        await starter.start()
        assert starter._client is not None
        assert starter._client.auth is not None
        await starter.close()

    @pytest.mark.asyncio
    async def test_client_created_without_auth_when_no_user(self) -> None:
        settings = CIB7Settings(engine_url="http://test:8080", tenant_id="t", user="", password="")
        starter = ProcessStarter(settings)
        await starter.start()
        assert starter._client is not None
        assert starter._client.auth is None
        await starter.close()


class TestStartProcess:
    """Test starting new process instances."""

    @pytest.mark.asyncio
    async def test_start_process_success(self, process_starter: ProcessStarter) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "process-instance-123", "businessKey": "BK-001"}
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b'{"id":"process-instance-123"}'

        with patch.object(
            process_starter._client, "request", return_value=mock_response
        ) as mock_request:
            result = await process_starter.start_process(
                process_key="test-process",
                variables={"key1": "value1", "key2": 123, "key3": True, "key4": 45.67},
                business_key="BK-001",
                tenant_id="test-tenant",
            )
            assert result["id"] == "process-instance-123"
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert "test-process" in call_args[0][1]
            assert "test-tenant" in call_args[0][1]
            payload = call_args[1]["json"]
            assert payload["businessKey"] == "BK-001"
            assert payload["variables"]["key1"]["value"] == "value1"
            assert payload["variables"]["key1"]["type"] == "String"
            assert payload["variables"]["key2"]["type"] == "Long"
            assert payload["variables"]["key3"]["type"] == "Boolean"
            assert payload["variables"]["key4"]["type"] == "Double"

    @pytest.mark.asyncio
    async def test_start_process_with_retry(self, process_starter: ProcessStarter) -> None:
        mock_success = MagicMock()
        mock_success.json.return_value = {"id": "instance-456"}
        mock_success.raise_for_status = MagicMock()
        mock_success.content = b'{"id":"instance-456"}'

        attempt_count = 0

        async def mock_request_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise httpx.TransportError("Connection failed")
            return mock_success

        with patch.object(
            process_starter._client, "request", side_effect=mock_request_side_effect
        ):
            result = await process_starter.start_process(
                process_key="test",
                variables={},
                business_key="BK-002",
                tenant_id="test",
            )
            assert result["id"] == "instance-456"
            assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_start_process_max_retries_exceeded(
        self, process_starter: ProcessStarter
    ) -> None:
        with patch.object(
            process_starter._client,
            "request",
            side_effect=httpx.TransportError("Connection refused"),
        ):
            with pytest.raises(RuntimeError, match="failed after 3 attempts"):
                await process_starter.start_process(
                    process_key="test",
                    variables={},
                    business_key="BK-003",
                    tenant_id="test",
                )


class TestCorrelateMessage:
    """Test message correlation to running processes."""

    @pytest.mark.asyncio
    async def test_correlate_message_success(self, process_starter: ProcessStarter) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"resultType": "ProcessDefinition"}
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b'{"resultType":"ProcessDefinition"}'

        with patch.object(
            process_starter._client, "request", return_value=mock_response
        ) as mock_request:
            result = await process_starter.correlate_message(
                message_name="MSG_TEST",
                correlation_keys={"businessKey": "BK-001", "orderId": "ORD-123"},
                variables={"status": "completed", "amount": 100},
            )
            assert result["resultType"] == "ProcessDefinition"
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert "/engine-rest/message" in call_args[0][1]
            payload = call_args[1]["json"]
            assert payload["messageName"] == "MSG_TEST"
            assert payload["correlationKeys"]["businessKey"]["value"] == "BK-001"
            assert payload["processVariables"]["status"]["value"] == "completed"

    @pytest.mark.asyncio
    async def test_correlate_message_with_http_error(
        self, process_starter: ProcessStarter
    ) -> None:
        async def mock_raise_error(*args: Any, **kwargs: Any) -> None:
            raise httpx.HTTPStatusError(
                "404 Not Found", request=MagicMock(), response=MagicMock(status_code=404)
            )

        with patch.object(process_starter._client, "request", side_effect=mock_raise_error):
            with pytest.raises(RuntimeError, match="failed after 3 attempts"):
                await process_starter.correlate_message(
                    message_name="MSG_NOTFOUND",
                    correlation_keys={"businessKey": "BK-INVALID"},
                    variables={},
                )


class TestVariableTypeMapping:
    """Test Camunda variable type mapping."""

    @pytest.mark.asyncio
    async def test_variable_types_mapped_correctly(
        self, process_starter: ProcessStarter
    ) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "instance"}
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b'{"id":"instance"}'

        with patch.object(
            process_starter._client, "request", return_value=mock_response
        ) as mock_request:
            await process_starter.start_process(
                process_key="test",
                variables={
                    "string_var": "text",
                    "int_var": 42,
                    "bool_var": False,
                    "float_var": 3.14,
                },
                business_key="BK",
                tenant_id="test",
            )
            payload = mock_request.call_args[1]["json"]
            vars_dict = payload["variables"]
            assert vars_dict["string_var"]["type"] == "String"
            assert vars_dict["int_var"]["type"] == "Long"
            assert vars_dict["bool_var"]["type"] == "Boolean"
            assert vars_dict["float_var"]["type"] == "Double"
