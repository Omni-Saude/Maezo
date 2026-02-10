"""Custom assertions para testes de workers e FHIR resources."""

from typing import Any, Dict
import pytest


def assert_worker_success(result: Dict[str, Any]) -> None:
    """
    Verifica se o resultado de um worker foi bem-sucedido.

    Args:
        result: Dicionário de resultado do worker

    Raises:
        AssertionError: Se o worker não foi bem-sucedido

    Example:
        >>> result = await worker.execute(task)
        >>> assert_worker_success(result)
    """
    assert result is not None, "Worker result is None"
    assert "success" in result or "status" in result, "Missing success/status field"

    success = result.get("success", result.get("status") == "success")
    assert success, f"Worker failed: {result.get('error', 'Unknown error')}"

    if "output_variables" in result:
        assert result["output_variables"] is not None, "Output variables is None"


def assert_bpmn_error(exc: Exception, expected_code: str) -> None:
    """
    Verifica se uma exceção BPMN Error tem o código esperado.

    Args:
        exc: Exceção capturada
        expected_code: Código de erro BPMN esperado

    Raises:
        AssertionError: Se não for um BPMN Error ou código não corresponder

    Example:
        >>> with pytest.raises(BPMNError) as exc_info:
        ...     await worker.execute(task)
        >>> assert_bpmn_error(exc_info.value, "INVALID_CPF")
    """
    from healthcare_platform.shared.exceptions import BPMNError

    assert isinstance(exc, BPMNError), f"Expected BPMNError, got {type(exc).__name__}"
    assert exc.error_code == expected_code, (
        f"Expected error code '{expected_code}', got '{exc.error_code}'"
    )


def assert_tenant_isolated(result: Dict[str, Any], tenant_id: str) -> None:
    """
    Verifica se o resultado está isolado ao tenant correto.

    Args:
        result: Resultado a verificar
        tenant_id: ID do tenant esperado

    Raises:
        AssertionError: Se tenant não corresponder ou estiver ausente

    Example:
        >>> result = await worker.execute(task)
        >>> assert_tenant_isolated(result, "austa-001")
    """
    assert "tenant_id" in result or "tenant_code" in result, (
        "Result missing tenant identification"
    )

    result_tenant = result.get("tenant_id") or result.get("tenant_code")
    assert result_tenant == tenant_id, (
        f"Expected tenant '{tenant_id}', got '{result_tenant}'"
    )


def assert_fhir_resource_valid(resource: Dict[str, Any], resource_type: str) -> None:
    """
    Verifica se um recurso FHIR é válido e do tipo esperado.

    Args:
        resource: Recurso FHIR a validar
        resource_type: Tipo de recurso esperado (Patient, Appointment, etc.)

    Raises:
        AssertionError: Se recurso for inválido

    Example:
        >>> patient = {"resourceType": "Patient", "id": "123"}
        >>> assert_fhir_resource_valid(patient, "Patient")
    """
    assert resource is not None, "FHIR resource is None"
    assert isinstance(resource, dict), f"FHIR resource must be dict, got {type(resource)}"

    assert "resourceType" in resource, "Missing resourceType field"
    assert resource["resourceType"] == resource_type, (
        f"Expected resourceType '{resource_type}', got '{resource['resourceType']}'"
    )

    # Validações básicas de estrutura FHIR
    if resource_type == "Patient":
        assert "identifier" in resource or "name" in resource, (
            "Patient must have identifier or name"
        )
    elif resource_type == "Appointment":
        assert "status" in resource, "Appointment must have status"
        assert "participant" in resource, "Appointment must have participants"
    elif resource_type == "Practitioner":
        assert "name" in resource, "Practitioner must have name"


async def assert_idempotent(worker: Any, input_data: Dict[str, Any]) -> None:
    """
    Verifica se um worker é idempotente executando-o múltiplas vezes.

    Args:
        worker: Worker a testar
        input_data: Dados de entrada para o worker

    Raises:
        AssertionError: Se resultados não forem idênticos

    Example:
        >>> await assert_idempotent(worker, {"cpf": "12345678901"})
    """
    # Primeira execução
    result1 = await worker.execute(input_data)

    # Segunda execução
    result2 = await worker.execute(input_data)

    # Resultados devem ser idênticos (ignorando timestamps)
    assert result1["success"] == result2["success"], (
        "Idempotency violated: success status differs"
    )

    # Compara campos principais (exclui timestamps e IDs gerados)
    excluded_fields = {"timestamp", "execution_time", "trace_id", "created_at"}

    for key in result1.get("output_variables", {}).keys():
        if key not in excluded_fields:
            assert result1["output_variables"].get(key) == result2["output_variables"].get(key), (
                f"Idempotency violated: field '{key}' differs between executions"
            )
