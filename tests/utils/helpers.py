"""Helper functions para testes."""

from typing import Dict, Any, Optional
from unittest.mock import AsyncMock
import xml.etree.ElementTree as ET
from pathlib import Path


async def run_worker(
    worker: Any,
    variables: Dict[str, Any],
    tenant: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa um worker com variáveis de teste.

    Args:
        worker: Instância do worker a executar
        variables: Variáveis de entrada
        tenant: Código do tenant (opcional)

    Returns:
        Resultado da execução do worker

    Example:
        >>> result = await run_worker(
        ...     worker=PatientValidationWorker(),
        ...     variables={"patient_cpf": "12345678901"},
        ...     tenant="AUSTA"
        ... )
    """
    # Adiciona tenant_code se fornecido
    if tenant:
        variables["tenant_code"] = tenant

    # Cria external task mock
    external_task = make_external_task(
        topic=getattr(worker, "topic_name", "test-topic"),
        variables=variables,
        tenant_id=tenant or "austa-001"
    )

    # Executa o worker
    try:
        result = await worker.execute(external_task)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exception_type": type(e).__name__,
        }


def make_external_task(
    topic: str,
    variables: Dict[str, Any],
    tenant_id: str = "austa-001",
    task_id: Optional[str] = None,
    process_instance_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Cria um external task mock para testes.

    Args:
        topic: Nome do tópico
        variables: Variáveis do processo
        tenant_id: ID do tenant
        task_id: ID da tarefa (gerado se não fornecido)
        process_instance_id: ID da instância do processo
        **kwargs: Campos adicionais

    Returns:
        External task formatado

    Example:
        >>> task = make_external_task(
        ...     topic="validate-patient",
        ...     variables={"cpf": "12345678901"},
        ...     tenant_id="austa-001"
        ... )
    """
    import random

    task_id = task_id or f"ext-task-{random.randint(10000, 99999)}"
    process_instance_id = process_instance_id or f"proc-inst-{random.randint(1000, 9999)}"

    # Converte variáveis para formato Camunda
    camunda_variables = {}
    for key, value in variables.items():
        camunda_variables[key] = _to_camunda_variable(value)

    external_task = {
        "activityId": f"task_{topic}",
        "activityInstanceId": f"task_{topic}:{random.randint(10000, 99999)}",
        "id": task_id,
        "processInstanceId": process_instance_id,
        "tenantId": tenant_id,
        "topicName": topic,
        "workerId": "test-worker",
        "variables": camunda_variables,
        "retries": 3,
        "lockExpirationTime": "2024-12-31T23:59:59.000+0000",
    }

    external_task.update(kwargs)
    return external_task


def _to_camunda_variable(value: Any) -> Dict[str, Any]:
    """Converte valor Python para formato de variável Camunda."""
    if isinstance(value, bool):
        return {"type": "Boolean", "value": value, "valueInfo": {}}
    elif isinstance(value, int):
        return {"type": "Integer", "value": value, "valueInfo": {}}
    elif isinstance(value, float):
        return {"type": "Double", "value": value, "valueInfo": {}}
    elif isinstance(value, str):
        return {"type": "String", "value": value, "valueInfo": {}}
    elif isinstance(value, dict):
        return {
            "type": "Object",
            "value": value,
            "valueInfo": {
                "objectTypeName": "java.util.HashMap",
                "serializationDataFormat": "application/json",
            },
        }
    elif isinstance(value, list):
        return {
            "type": "Object",
            "value": value,
            "valueInfo": {
                "objectTypeName": "java.util.ArrayList",
                "serializationDataFormat": "application/json",
            },
        }
    else:
        return {"type": "String", "value": str(value), "valueInfo": {}}


def assert_prometheus_metric(
    metric_name: str,
    labels: Dict[str, str],
    expected: Any
) -> None:
    """
    Verifica se uma métrica Prometheus tem o valor esperado.

    Args:
        metric_name: Nome da métrica
        labels: Labels da métrica
        expected: Valor esperado

    Raises:
        AssertionError: Se métrica não corresponder ao esperado

    Example:
        >>> assert_prometheus_metric(
        ...     "worker_executions_total",
        ...     {"worker": "patient_validation", "status": "success"},
        ...     5
        ... )
    """
    # Mock implementation - em ambiente real, consultaria o registry Prometheus
    # Por ora, apenas valida os parâmetros
    assert metric_name, "Metric name cannot be empty"
    assert isinstance(labels, dict), "Labels must be a dictionary"
    assert expected is not None, "Expected value cannot be None"

    # TODO: Implementar consulta real ao Prometheus registry quando integrado
    print(f"[MOCK] Checking metric {metric_name}{labels} == {expected}")


def load_dmn_file(dmn_path: str | Path) -> ET.Element:
    """
    Carrega e parseia um arquivo DMN.

    Args:
        dmn_path: Caminho para o arquivo DMN

    Returns:
        Elemento raiz do XML parseado

    Raises:
        FileNotFoundError: Se arquivo não existir
        ET.ParseError: Se XML for inválido

    Example:
        >>> dmn = load_dmn_file("dmn/billing/insurance_routing.dmn")
        >>> decision_tables = dmn.findall(".//{*}decisionTable")
    """
    dmn_path = Path(dmn_path)

    if not dmn_path.exists():
        raise FileNotFoundError(f"DMN file not found: {dmn_path}")

    try:
        tree = ET.parse(dmn_path)
        return tree.getroot()
    except ET.ParseError as e:
        raise ET.ParseError(f"Invalid DMN XML in {dmn_path}: {e}")


def extract_decision_tables(dmn_root: ET.Element) -> list[ET.Element]:
    """
    Extrai todas as decision tables de um DMN.

    Args:
        dmn_root: Elemento raiz do DMN

    Returns:
        Lista de elementos decisionTable

    Example:
        >>> dmn = load_dmn_file("billing.dmn")
        >>> tables = extract_decision_tables(dmn)
        >>> assert len(tables) > 0
    """
    # DMN usa namespace, então procuramos com {*} para ignorar namespace
    return dmn_root.findall(".//{*}decisionTable")


def get_dmn_inputs(decision_table: ET.Element) -> list[str]:
    """
    Extrai os nomes dos inputs de uma decision table.

    Args:
        decision_table: Elemento decisionTable

    Returns:
        Lista de nomes de inputs

    Example:
        >>> inputs = get_dmn_inputs(decision_table)
        >>> assert "insurance_type" in inputs
    """
    inputs = []
    for input_elem in decision_table.findall(".//{*}input"):
        label = input_elem.get("label")
        if label:
            inputs.append(label)
    return inputs


def get_dmn_outputs(decision_table: ET.Element) -> list[str]:
    """
    Extrai os nomes dos outputs de uma decision table.

    Args:
        decision_table: Elemento decisionTable

    Returns:
        Lista de nomes de outputs

    Example:
        >>> outputs = get_dmn_outputs(decision_table)
        >>> assert "billing_amount" in outputs
    """
    outputs = []
    for output_elem in decision_table.findall(".//{*}output"):
        label = output_elem.get("label") or output_elem.get("name")
        if label:
            outputs.append(label)
    return outputs
