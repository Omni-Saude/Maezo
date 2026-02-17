"""Shared fixtures for coding worker tests.

Provides tenant context setup for all coding v2 worker tests.
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
    """Automatically set up tenant context for all coding tests.

    The coding v2 workers use @require_tenant decorator which validates
    that tenant context is set before execution. This fixture ensures
    all tests have a valid tenant context.
    """
    # Set up tenant context before test
    tenant = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(tenant)

    yield

    # Clean up after test
    clear_tenant()


@pytest.fixture(autouse=True)
def mock_federated_dmn_service(mock_dmn_service, monkeypatch):
    """Auto-inject mock DMN service into all v2 workers.

    V2 workers create their own FederatedDMNService in __init__.
    This fixture patches the class to return our mock instead.
    """
    from healthcare_platform.shared.dmn import federation_service

    def mock_init(self, *args, **kwargs):
        # Copy the evaluate method from our mock
        self.evaluate = mock_dmn_service.evaluate

    monkeypatch.setattr(
        federation_service.FederatedDMNService,
        "__init__",
        mock_init
    )

    yield mock_dmn_service


@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService for DMN evaluation.

    Returns:
        MagicMock with evaluate() method configured to return appropriate
        responses based on the table name being evaluated.
    """
    def evaluate_side_effect(tenant_id=None, category=None, table_name=None, inputs=None, **kwargs):
        """Return appropriate responses based on table name."""
        # Default safe response
        result = {"resultado": "PROSSEGUIR", "acao": "Codificação válida", "risco": "BAIXO"}

        # CID10 suggestion tables
        if "cid10_suggestion" in str(table_name):
            if "confidence_boosting" in str(table_name):
                # Return suggested CID10 codes
                result["suggestions"] = [
                    {"code": "E11.9", "description": "Diabetes mellitus tipo 2", "confidence": 0.95},
                    {"code": "I10", "description": "Hipertensão essencial", "confidence": 0.88}
                ]
            elif "format_validation" in str(table_name):
                # Validate format and return valid suggestions
                suggestions = inputs.get("suggestions", []) if inputs else []
                result["valid_suggestions"] = suggestions

        # TUSS suggestion tables
        if "tuss_suggestion" in str(table_name):
            if "cid10_correlation" in str(table_name):
                # Return raw TUSS suggestions
                result["raw_suggestions"] = [
                    {"code": "10101012", "description": "Consulta em consultório", "confidence": 0.97},
                    {"code": "40301150", "description": "Hemograma completo", "confidence": 0.91}
                ]
            elif "format_validation" in str(table_name):
                # Validate format and return validated TUSS
                raw = inputs.get("raw_suggestions", []) if inputs else []
                result["validated_tuss"] = raw

        # Code validation tables
        if "code_validation" in str(table_name):
            if "cid10_format" in str(table_name):
                # Return validated CID10 codes
                suggested = inputs.get("suggested_cid10_codes", []) if inputs else []
                result["validated_cid10"] = suggested
                result["errors"] = []
            elif "cid10_incompatibility" in str(table_name):
                # Check incompatibility
                result["errors"] = []
            elif "tuss_format" in str(table_name):
                # Return format valid TUSS
                suggested = inputs.get("suggested_tuss_codes", []) if inputs else []
                result["format_valid_tuss"] = suggested
                result["errors"] = []
            elif "tuss_coverage" in str(table_name):
                # Return validated TUSS
                format_valid = inputs.get("format_valid_tuss", []) if inputs else []
                result["validated_tuss"] = format_valid
                result["errors"] = []
            elif "tuss_cid10_requirements" in str(table_name):
                # Check requirements
                result["errors"] = []

        # Code compatibility tables
        if "code_compatibility" in str(table_name):
            result["resultado"] = "PROSSEGUIR"
            result["Decisao"] = "Prosseguir"

        # Fraud scoring tables - return alerts based on table name
        if "fraud_scoring" in str(table_name):
            result["alerts"] = []
            result["score"] = 0

            # Specific fraud checks
            if "upcoding" in str(table_name):
                # If we're checking upcoding, add an alert
                result["alerts"] = [{"type": "upcoding", "message": "Possible upcoding detected"}]
                result["score"] = 25
            elif "unbundling" in str(table_name):
                result["alerts"] = [{"type": "unbundling", "message": "Unbundling pattern detected"}]
                result["score"] = 20
            elif "phantom" in str(table_name):
                result["alerts"] = [{"type": "phantom", "message": "Phantom billing pattern"}]
                result["score"] = 30
            elif "frequency" in str(table_name):
                # Check if frequency is suspicious
                tuss_count = inputs.get("tuss_count", 0) if inputs else 0
                if tuss_count > 5:
                    result["alerts"] = [{"type": "frequency", "message": "Frequency abuse detected"}]
                    result["score"] = 15

        # Risk thresholds
        if "risk_thresholds" in str(table_name):
            risk = inputs.get("risk_score", 0) if inputs else 0
            result["recommendation"] = "flag" if risk > 80 else "clear"

        # Audit quality checks
        if "audit_quality" in str(table_name):
            result["resultado"] = "PROSSEGUIR"  # Pass audit checks by default
            result["acao"] = "Codificação válida"
            result["risco"] = "BAIXO"

        # Audit approval - check both recommendation and score
        if "audit_approval" in str(table_name):
            rec = inputs.get("audit_recommendation", "aprovar") if inputs else "aprovar"
            score = inputs.get("audit_score", 100) if inputs else 100
            # Block if recommendation is to revise/block OR score is low
            should_block = rec in ["revisar", "bloquear", "failed"] or score < 70
            result["resultado"] = "BLOQUEAR" if should_block else "PROSSEGUIR"

        # Fraud clearance - more detailed check
        if "fraud_clearance" in str(table_name):
            rec = inputs.get("fraud_recommendation", "clear") if inputs else "clear"
            # Block on flag, critical, high, or block
            should_block = rec in ["flag", "critical", "high", "block"]
            result["resultado"] = "BLOQUEAR" if should_block else "PROSSEGUIR"

        # Complexity scoring tables
        if "complexity_scoring" in str(table_name):
            if "diagnosis_count" in str(table_name):
                diag_count = inputs.get("diagnosis_count", 0) if inputs else 0
                comorbidity_count = inputs.get("comorbidity_count", 0) if inputs else 0
                result["contribution"] = diag_count * 0.5
                result["weight"] = 0.5
            elif "age_factors" in str(table_name):
                age = inputs.get("patient_age", 0) if inputs else 0
                if age >= 70:
                    result["age_factor"] = 2.0
                    result["contribution"] = 2.0
                elif age >= 50:
                    result["age_factor"] = 1.5
                    result["contribution"] = 1.5
                else:
                    result["age_factor"] = 1.0
                    result["contribution"] = 1.0
                result["weight"] = 1.0
            elif "encounter_class_weight" in str(table_name):
                enc_class = inputs.get("encounter_class", "") if inputs else ""
                if enc_class == "internacao":
                    result["weight"] = 2.0
                    result["contribution"] = 2.0
                elif enc_class == "emergencia":
                    result["weight"] = 1.5
                    result["contribution"] = 1.5
                else:
                    result["weight"] = 1.0
                    result["contribution"] = 1.0

        return result

    mock = MagicMock()
    mock.evaluate.side_effect = evaluate_side_effect
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
    task.failure = AsyncMock()
    task.handle_failure = AsyncMock()
    task.variables = {}
    task.id = "task-123"
    task.worker_id = "worker-456"
    task.topic_name = "test-topic"
    return task


async def execute_worker_with_mock_task(worker, mock_task):
    """Helper to execute v2 workers with v1 mock_task pattern.

    V2 workers expect dict input and return dict output.
    V1 tests use mock_task with get_variable/complete/bpmn_error.

    This helper bridges the gap by:
    1. Converting mock_task.get_variable() calls to a dict
    2. Calling worker.execute(dict) or worker.process_task(dict)
    3. Calling mock_task.complete() or mock_task.bpmn_error() based on result
    """
    from healthcare_platform.shared.domain.exceptions import BpmnErrorException

    # Build variables dict from mock_task
    variables = {}
    if hasattr(mock_task, 'get_variable'):
        # Try to get all common variables
        common_vars = [
            "encounterId", "encounter_id", "tenantId", "tenant_id",
            "cid10Codes", "cid10_codes", "validatedCid10", "validated_cid10",
            "tussCodes", "tuss_codes", "validatedTuss", "validated_tuss",
            "clinicalNotes", "clinical_notes", "proceduresText", "procedures_text",
            "suggestedCid10Codes", "suggested_cid10_codes",
            "suggestedTussCodes", "suggested_tuss_codes",
            "formatValidTuss", "format_valid_tuss",
            "rulesApplied", "rules_applied", "codedBy", "coded_by",
            "auditThreshold", "audit_threshold", "auditStatus", "audit_status",
            "fraudRiskLevel", "fraud_risk_level", "patientAge", "patient_age",
            "patientId", "patient_id", "comorbidities", "encounterClass", "encounter_class",
            "codingRulesResult", "coding_rules_result",
        ]
        for var in common_vars:
            val = mock_task.get_variable(var)
            if val is not None:
                variables[var] = val

    try:
        # Try execute() method first (v2 pattern)
        if hasattr(worker, 'execute') and not hasattr(worker.execute, '__self__'):
            # Unbound method or async function
            result = await worker.execute(variables)
        elif hasattr(worker, 'process_task'):
            # V1 compatibility method
            result_obj = await worker.process_task(variables=variables)
            if hasattr(result_obj, 'success'):
                if not result_obj.success:
                    await mock_task.bpmn_error(
                        result_obj.error_code or "ERROR",
                        result_obj.error_message or "Task failed"
                    )
                    return
                result = result_obj.variables
            else:
                result = result_obj
        else:
            raise ValueError(f"Worker {worker} has no execute or process_task method")

        # Success - call complete
        await mock_task.complete(result)
    except BpmnErrorException as e:
        # BPMN error - call bpmn_error
        await mock_task.bpmn_error(e.error_code, str(e))
    except Exception as e:
        # Other error - call failure
        error_code = getattr(e, 'bpmn_error_code', getattr(e, 'error_code', 'ERROR'))
        await mock_task.bpmn_error(error_code, str(e))


@pytest.fixture
def mock_ans_client():
    """Mock ANS client for code validation tests.

    Returns:
        MagicMock with validate_cid10, validate_tuss, and search methods
    """
    mock = MagicMock()
    mock.validate_cid10 = AsyncMock(return_value=True)
    mock.validate_tuss = AsyncMock(return_value=True)
    mock.search_cid10 = AsyncMock(return_value=[])
    mock.search_tuss = AsyncMock(return_value=[])
    return mock
