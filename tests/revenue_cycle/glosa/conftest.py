"""Shared fixtures for glosa worker tests.

Provides tenant context setup for all glosa v2 worker tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    set_current_tenant,
    clear_tenant,
)
from healthcare_platform.shared.domain.enums import TenantCode


@pytest.fixture(autouse=True)
def setup_tenant_context():
    """Automatically set up tenant context for all glosa tests.

    The glosa v2 workers use @require_tenant decorator which validates
    that tenant context is set before execution. This fixture ensures
    all tests have a valid tenant context.
    """
    # Set up tenant context before test
    tenant = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(tenant)

    yield

    # Clean up after test
    clear_tenant()


@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService for DMN evaluation.

    Returns:
        MagicMock with evaluate() method configured with smart defaults
        that infer appropriate values from inputs
    """
    def smart_evaluate(tenant_id, category, table_name, inputs):
        """Smart DMN evaluation that infers reasonable outputs from inputs."""
        from healthcare_platform.shared.domain.enums import GlosaReasonCode

        # Extract common inputs
        reason_code = inputs.get("reasonCode", "")
        description = inputs.get("description", "")
        denial_ratio = inputs.get("denialRatio", 0.0)
        # Get glosaType from inputs (for appeal eligibility checks)
        input_glosa_type = inputs.get("glosaType", "").upper()
        days_remaining = inputs.get("daysRemaining", 30)
        available_documentation = inputs.get("availableDocumentation", [])
        # For submission workers
        response_code = inputs.get("responseCode", "")
        attempt_count = inputs.get("attemptCount", 0)

        # Map enum values (GLOSA_001, etc.) back to their names for classification
        # This handles both enum.value and enum.name formats
        reason_code_name = reason_code
        try:
            # Try to find matching enum by value
            for code_enum in GlosaReasonCode:
                if code_enum.value == reason_code:
                    reason_code_name = code_enum.name
                    break
        except (ValueError, AttributeError):
            pass

        # Infer glosaType from reasonCode or description
        # Note: GlosaType enum values are lowercase, but DMN tables use UPPERCASE
        # The worker will convert UPPERCASE to lowercase via enum lookup
        glosa_type = "TECHNICAL"  # Default (uppercase for DMN)
        if reason_code_name:
            # Map reason codes to glosa types
            admin_codes = ["MISSING_AUTH", "EXPIRED_AUTH", "DUPLICATE_CHARGE",
                          "MISSING_DOCUMENTATION", "EXCEEDS_QUANTITY"]
            linear_codes = ["PRICE_DIVERGENCE", "QUANTITY_DIVERGENCE"]

            if any(code in reason_code_name for code in admin_codes):
                glosa_type = "ADMINISTRATIVE"
            elif any(code in reason_code_name for code in linear_codes):
                glosa_type = "LINEAR"
        elif description:
            # Infer from description keywords
            description_lower = description.lower()
            if any(kw in description_lower for kw in ["autorização", "documentação", "duplicad"]):
                glosa_type = "ADMINISTRATIVE"
            elif any(kw in description_lower for kw in ["preço", "quantidade", "valor"]):
                glosa_type = "LINEAR"

        # Infer glosaExtent from denial ratio
        # Note: GlosaExtent enum values are lowercase
        glosa_extent = "TOTAL" if denial_ratio >= 1.0 else "PARTIAL"

        # Check for required documentation based on reason code
        required_docs = []
        if reason_code_name:
            if "CLINICAL_JUSTIFICATION" in reason_code_name:
                required_docs = ["clinical_notes", "medical_report"]
            elif "INVALID_CODE" in reason_code_name:
                required_docs = ["procedure_documentation", "code_justification"]
            elif "SIGNATURE" in reason_code_name:
                required_docs = ["signed_forms"]

        missing_docs = [doc for doc in required_docs if doc not in available_documentation]

        # Handle submission-specific routing
        if response_code:
            # This is a submission adjudication call
            if response_code == "SUCCESS":
                resultado = "PROSSEGUIR"
                acao = "Recurso enviado com sucesso"
            elif response_code in ["CONNECTION_ERROR", "TIMEOUT"] and attempt_count < 3:
                resultado = "REVISAR"
                acao = "Tentar reenvio"
            else:
                resultado = "BLOQUEAR"
                acao = "Falha na submissão, escalar"
        # Handle appeal eligibility checks with explicit availableDocumentation check
        elif "availableDocumentation" in inputs:
            # Only check documentation when explicitly provided in inputs
            resultado = "PROSSEGUIR"
            acao = "Processar normalmente"
            if input_glosa_type == "TOTAL":
                resultado = "BLOQUEAR"
                acao = "Glosas TOTAL não são passíveis de recurso"
            elif days_remaining < 0:
                resultado = "BLOQUEAR"
                acao = "Prazo de recurso expirado"
            elif input_glosa_type and input_glosa_type not in ["ADMINISTRATIVE", "TECHNICAL", "PARTIAL", "TOTAL", ""]:
                resultado = "BLOQUEAR"
                acao = f"Tipo de glosa inválido: {input_glosa_type}"
            elif missing_docs:
                resultado = "BLOQUEAR"
                acao = f"Documentação obrigatória ausente: {', '.join(missing_docs)}"
        else:
            # Default fallback - PROSSEGUIR for documentation generation and other workers
            resultado = "PROSSEGUIR"
            acao = "Processar normalmente"

        # Build result with missing documentation if applicable
        result = {
            "resultado": resultado,
            "acao": acao,
            "risco": "BAIXO",
            "observacao": "Padrão dentro do esperado",
            "acaoRecomendada": "Continuar",
            # Smart inference - omit reasonCode so worker can use fallback
            "reasonDescription": "Análise processada",
            "glosaType": glosa_type,
            "glosaExtent": glosa_extent,
            # Legacy 5-output support (for backward compat)
            "glosa_tipo": glosa_type,
            "glosa_severidade": "ALTA"
        }

        # Add missing documentation list if any
        if missing_docs:
            result["missingDocumentation"] = missing_docs

        return result

    mock = MagicMock()
    mock.evaluate.side_effect = smart_evaluate
    return mock


@pytest.fixture
def mock_task():
    """Mock Camunda External Task for v1-style worker tests.

    V2 workers don't use this pattern (they take dict directly),
    but v1 tests may still reference it. This provides compatibility.

    Returns:
        MagicMock with common task methods (get_variable, complete, bpmn_error, etc.)
    """
    task = MagicMock()
    task.get_variable = MagicMock(return_value=None)
    task.complete = AsyncMock()
    task.bpmn_error = AsyncMock()
    task.handle_failure = AsyncMock()
    task.variables = {}
    task.id = "task-123"
    task.worker_id = "worker-456"
    task.topic_name = "test-topic"
    return task


@pytest.fixture
def mock_dmn_service_error():
    """Mock FederatedDMNService that raises an error for testing error handling.

    Returns:
        MagicMock configured to raise ValueError when evaluate() is called
    """
    mock = MagicMock()
    mock.evaluate.side_effect = ValueError("DMN evaluation failed")
    return mock


@pytest.fixture
def mock_metrics():
    """Mock metrics service for testing.

    Returns:
        MagicMock with record_metric() method
    """
    mock = MagicMock()
    mock.record_metric = MagicMock()
    return mock


@pytest.fixture
def basic_task_context():
    """Create basic TaskContext for v2 worker tests.

    Returns:
        TaskContext with common test defaults
    """
    from healthcare_platform.shared.workers.base import TaskContext

    return TaskContext(
        task_id="task_test_123",
        process_instance_id="proc_test_123",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="test_worker",
    )
