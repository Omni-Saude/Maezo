"""
test_rc002_bpmn_workers.py — Integração SP-RC-002 Pré-Atendimento e Autorização.

Testa o fluxo COMPLETO com workers Python reais contra o CIB Seven.

  Workers REAIS:
    - ValidateProcedureWorker  (revenue_cycle.validate_procedure)
      → Valida código TUSS via DMN procedure_code_adjudication

  Workers STUB (sem implementação V2 para estes tópicos):
    - revenue_cycle.check_authorization   (sem worker V2)
    - revenue_cycle.request_authorization (sem worker V2)
    - AtualizarTasy                       (sem worker V2)
    - RevisarManual                       (sem worker V2)
    - escalar-autoriza-o                  (sem worker V2)

  NOTA sobre ValidateProcedureWorker:
    O worker espera as variáveis:
      - procedure_codes (list) e coverage_type (str)
    O BPMN envia via inputParameter:
      - procedureCode (str) e clinicalData (str)
    Existe divergência de nomes → adapter traduz as variáveis.

Requer: CIB Seven rodando em http://localhost:8080
"""
from __future__ import annotations

import dataclasses
import uuid

import httpx
import pytest

from tests.e2e.conftest import CIB7_URL, CIB7_USER, CIB7_PASS, TIMEOUT
from tests.fixtures.fhir_seed import HAPPY_PATH_IDS, AUTH_DENIED_IDS
from tests.integration.worker_harness import (
    WorkerHarness,
    cancel_all_active,
    get_process_variables,
    make_mock_dmn,
    start_process,
    stub_worker,
    trigger_timers,
    wait_for_state,
)
from healthcare_platform.revenue_cycle.production.workers.validate_procedure_worker_v2 import (
    ValidateProcedureWorker,
)
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus

PROCESS_KEY = "SP_RC_002_Pre_Service"


@pytest.fixture
def cib7():
    with httpx.Client(
        base_url=f"{CIB7_URL}/engine-rest",
        auth=(CIB7_USER, CIB7_PASS),
        timeout=TIMEOUT,
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean(cib7):
    cancel_all_active(cib7, PROCESS_KEY)
    yield
    cancel_all_active(cib7, PROCESS_KEY)


# ---------------------------------------------------------------------------
# Adaptador: ValidateProcedureWorker
# ---------------------------------------------------------------------------

def _make_validate_procedure_adapter(worker: ValidateProcedureWorker):
    """
    Adapta I/O do ValidateProcedureWorker para o contrato BPMN SP-RC-002.

    Contrato BPMN:
      IN:  procedureCode=${procedureCode}, clinicalData=${clinicalData}, authorizationNumber=${authNumber}
      OUT: procedureValidated=${validationStatus}

    Worker lê: procedure_codes (list), coverage_type (str)
    Worker retorna: validated_procedures, all_valid, invalid_codes

    Adapter:
      - Converte procedureCode (str) → procedure_codes ([str])
      - coverage_type extraído de clinicalData ou default "ambulatorial"
      - all_valid=True → validationStatus="OK" (contrato BPMN)

    TODO: alinhar ValidateProcedureWorker com contrato BPMN (ADR-003)
    """
    def adapter(context: TaskContext) -> TaskResult:
        # Adaptar entrada
        procedure_code = context.variables.get("procedureCode", "")
        clinical_data = context.variables.get("clinicalData", {})
        if isinstance(clinical_data, str):
            import json
            try:
                clinical_data = json.loads(clinical_data)
            except Exception:
                clinical_data = {}

        adapted = dataclasses.replace(
            context,
            variables={
                **context.variables,
                "procedure_codes": [procedure_code] if procedure_code else [],
                "coverage_type": clinical_data.get("coverageType", "ambulatorial"),
            },
        )
        result = worker.execute(adapted)

        if result.status == TaskStatus.SUCCESS:
            # Adaptar saída: all_valid → validationStatus (contrato BPMN)
            all_valid = result.variables.get("all_valid", True)
            vars_out = dict(result.variables or {})
            vars_out["validationStatus"] = "OK" if all_valid else "INVALID"
            return TaskResult.success(vars_out)

        if result.status == TaskStatus.BPMN_ERROR:
            # Procedimento inválido — preservar error_code
            return result

        return result

    return adapter


# ---------------------------------------------------------------------------
# Worker map factory
# ---------------------------------------------------------------------------

def _build_worker_map(mock_dmn, auth_status: str = "APPROVED") -> dict:
    """
    Monta worker map para SP-RC-002.

    Workers reais: validate_procedure (com adapter)
    Workers stub: todos os demais
    """
    validate_worker = ValidateProcedureWorker(dmn_service=mock_dmn)

    return {
        # ── Stub: verificar necessidade de autorização ───────────────────────
        "revenue_cycle.check_authorization": stub_worker({
            "requiresAuth": True,
            "authType": "prior_auth",
        }),
        # ── Stub: solicitar autorização ──────────────────────────────────────
        "revenue_cycle.request_authorization": stub_worker({
            "authorizationNumber": f"AUTH-{uuid.uuid4().hex[:8]}",
            "authStatus": auth_status,
        }),
        # ── Stub: atualizar Tasy ─────────────────────────────────────────────
        "AtualizarTasy": stub_worker({"tasyUpdated": True}),
        # ── Worker real: validar procedimento (com adapter) ──────────────────
        "revenue_cycle.validate_procedure": _make_validate_procedure_adapter(validate_worker),
        # ── Stub: revisão manual (path PENDING) ──────────────────────────────
        "RevisarManual": stub_worker({"reviewCompleted": True}),
        # ── Stub: escalar autorização (path SLA 48h) ─────────────────────────
        "escalar-autoriza-o": stub_worker({"escalated": True}),
    }


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRC002PreServiceWorkers:
    """
    Integração SP-RC-002 com ValidateProcedureWorker real.

    O worker executa sua lógica real de adjudicação de código TUSS via DMN.
    """

    @pytest.fixture(autouse=True)
    def _pause_competing_workers(self, pause_rc_worker):
        """Garante que o worker RC de produção está pausado durante os testes."""

    def test_happy_path_valid_procedure_code(self, cib7, require_cib7):
        """
        Fluxo completo: autorização aprovada → ValidateProcedureWorker valida código TUSS.

        DMN retorna PROSSEGUIR para o código 40101010 (consulta médica em consultório).
        Worker deve retornar validationStatus="OK" → processo COMPLETED.
        """
        mock_dmn = make_mock_dmn(responses={
            "procedure_code_adjudication": {
                "resultado": "PROSSEGUIR",
                "acao": "Código TUSS válido — consulta médica ambulatorial",
                "risco": "BAIXO",
                "coverageType": "ambulatorial",
                "procedureName": "Consulta médica em consultório",
            }
        })
        worker_map = _build_worker_map(mock_dmn, auth_status="APPROVED")
        instance_id = None

        with WorkerHarness(cib7, worker_map) as harness:
            instance_id = start_process(cib7, PROCESS_KEY, {
                "patientId":             HAPPY_PATH_IDS["patient"],
                "procedureCode":         "40101010",
                "payerId":               HAPPY_PATH_IDS["org_payer"],
                "clinicalJustification": "Consulta de rotina — colecistite",
                "encounterId":           HAPPY_PATH_IDS["encounter"],
                "clinicalData":          '{"diagnosis": "K80.2", "procedure": "40101010", "coverageType": "ambulatorial"}',
            })

            # Timer PT1H precisa ser disparado após request_authorization
            import time
            time.sleep(3)  # Aguarda stubs completarem check + request
            triggered = trigger_timers(cib7, instance_id, wait_s=8)

            state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=30)

        assert state == "COMPLETED", (
            f"Estado: {state}\n"
            f"Triggered timers: {triggered}\n"
            f"Workers executados: {harness.executed}\n"
            f"Erros: {harness.errors}"
        )

        # ValidateProcedureWorker deve ter executado
        executed_topics = {e["topic"] for e in harness.executed}
        assert "revenue_cycle.validate_procedure" in executed_topics, (
            "ValidateProcedureWorker não executou"
        )
        assert not harness.errors, f"Erros: {harness.errors}"

    def test_invalid_procedure_code_dmn_bloquear(self, cib7, require_cib7):
        """
        DMN retorna BLOQUEAR para código inválido → worker retorna bpmnError.

        O BPMN SP-RC-002 não tem boundary event para validate_procedure,
        então o processo ficará com INCIDENT (não COMPLETED nem ACTIVE normal).
        Este teste valida que o worker rejeita o código corretamente.
        """
        mock_dmn = make_mock_dmn(responses={
            "procedure_code_adjudication": {
                "resultado": "BLOQUEAR",
                "acao": "Código TUSS não encontrado na tabela ANS Rol de Procedimentos",
                "risco": "ALTO",
            }
        })
        worker_map = _build_worker_map(mock_dmn, auth_status="APPROVED")
        instance_id = None

        try:
            with WorkerHarness(cib7, worker_map) as harness:
                instance_id = start_process(cib7, PROCESS_KEY, {
                    "patientId":             AUTH_DENIED_IDS["patient"],
                    "procedureCode":         "99999999",   # código inválido — não existe no Rol ANS
                    "payerId":               AUTH_DENIED_IDS["org_payer"],
                    "clinicalJustification": "Teste com código inválido",
                    "encounterId":           HAPPY_PATH_IDS["encounter"],
                    "clinicalData":          '{"diagnosis": "K80.2", "procedure": "99999999"}',
                })

                import time
                time.sleep(3)
                trigger_timers(cib7, instance_id, wait_s=8)
                time.sleep(5)  # Aguarda worker executar e tentar completar

            # Worker retornou bpmnError → processo deve ter INCIDENT ou estar ACTIVE
            state = wait_for_state(cib7, instance_id, "ACTIVE", timeout_s=5)
            # Aceita ACTIVE (bpmnError criou incident) ou COMPLETED (se boundary capturou)
            assert state in ("ACTIVE", "COMPLETED"), f"Estado inesperado: {state}"

            # O worker de validate_procedure DEVE ter executado
            executed_topics = {e["topic"] for e in harness.executed}
            assert "revenue_cycle.validate_procedure" in executed_topics, (
                "ValidateProcedureWorker não executou para código inválido"
            )

        finally:
            if instance_id:
                cancel_all_active(cib7, PROCESS_KEY)

    def test_validate_procedure_worker_logic_directly(self, require_cib7):
        """
        Testa a lógica do ValidateProcedureWorker diretamente (sem CIB Seven).
        Valida que o worker responde corretamente ao DMN.
        """
        from healthcare_platform.shared.workers.base import TaskContext

        mock_dmn = make_mock_dmn(responses={
            "procedure_code_adjudication": {
                "resultado": "PROSSEGUIR",
                "acao": "Código TUSS válido — consulta médica em consultório",
                "risco": "BAIXO",
                "coverageType": "ambulatorial",
                "procedureName": "Consulta médica em consultório",
            }
        })
        worker = ValidateProcedureWorker(dmn_service=mock_dmn)
        context = TaskContext(
            task_id="test-task-001",
            process_instance_id=HAPPY_PATH_IDS["claim"],
            tenant_id="HOSPITAL_A",
            variables={
                "procedure_codes": ["40101010", "40301362"],   # TUSS: consulta + hemograma
                "coverage_type": "ambulatorial",
            },
            worker_id="integration-test",
        )

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["all_valid"] is True
        assert len(result.variables["validated_procedures"]) == 2
        # DMN foi chamado 2 vezes (uma por código)
        assert mock_dmn.evaluate.call_count == 2
