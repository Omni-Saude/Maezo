"""
test_rc001_bpmn.py — Integração SP-RC-001 Agendamento e Registro.

Testa o fluxo completo SP_RC_001_Scheduling_Registration.
Todos os tasks são bpmn:task (auto-complete) — nenhum worker externo necessário.

Fluxo principal:
  start → verify_insurance → check_eligibility → gateway_eligibility
    Sim (eligibilityStatus=true): schedule_appointment → end_success
    Não (eligibilityStatus=false): manual_review → end_manual_review

Variáveis chave:
  isEligible (bool)        → outputParameter → eligibilityStatus
  Gateway condition: ${eligibilityStatus == true}

Requer: CIB Seven rodando em http://localhost:8080
"""
from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import CIB7_URL, CIB7_USER, CIB7_PASS
from tests.fixtures.fhir_seed import HAPPY_PATH_IDS
from tests.integration.worker_harness import (
    cancel_all_active,
    get_process_variables,
    start_process,
    wait_for_state,
)

PROCESS_KEY = "SP_RC_001_Scheduling_Registration"
TIMEOUT = 30.0


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
# Testes
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRC001SchedulingRegistration:
    """
    Integração SP-RC-001 — todos os tasks são bpmn:task (auto-complete).
    Sem workers externos. Variáveis controladas via parâmetros de início.
    """

    def test_happy_path_eligible_completes(self, cib7, require_cib7):
        """
        Happy path: isEligible=true → eligibilityStatus=true
        → gateway_eligibility toma flow_eligible_yes
        → schedule_appointment → end_success → COMPLETED.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":          HAPPY_PATH_IDS["patient"],
            "insuranceCardNumber": "BC-12345-6789",
            # Variáveis-fonte para output parameters das bpmn:task (auto-complete):
            "coverageStatus":     "active",          # task_verify_insurance → insuranceVerified
            "isEligible":         True,               # task_check_eligibility → eligibilityStatus
            "appointmentId":      HAPPY_PATH_IDS["appointment"],  # task_schedule_appointment
        })
        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)
        assert state == "COMPLETED", f"Estado inesperado: {state}"

        # Confirmar que a variável foi propagada corretamente
        vars_ = get_process_variables(cib7, instance_id)
        assert vars_.get("eligibilityStatus") is True, (
            f"eligibilityStatus esperado True, obtido: {vars_.get('eligibilityStatus')}"
        )

    def test_ineligible_goes_to_manual_review(self, cib7, require_cib7):
        """
        Paciente inelegível: isEligible=false → gateway toma default flow_eligible_no
        → manual_review → end_manual_review → COMPLETED.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":          HAPPY_PATH_IDS["patient"],
            "insuranceCardNumber": "BC-INVALIDO",
            "coverageStatus":     "inactive",
            "isEligible":         False,
        })
        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)
        assert state == "COMPLETED", f"Estado inesperado: {state}"

        vars_ = get_process_variables(cib7, instance_id)
        assert vars_.get("eligibilityStatus") is False, (
            f"eligibilityStatus esperado False, obtido: {vars_.get('eligibilityStatus')}"
        )

    def test_no_insurance_card_goes_to_manual_review(self, cib7, require_cib7):
        """
        Sem carteirinha: isEligible=false → eligibilityStatus=false
        → ${eligibilityStatus == true} = false → default path → manual review.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":           HAPPY_PATH_IDS["patient"],
            "insuranceCardNumber": "",
            "coverageStatus":      "unknown",
            "isEligible":          False,
        })
        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)
        assert state == "COMPLETED", f"Estado inesperado: {state}"

    def test_multiple_patients_concurrent(self, cib7, require_cib7):
        """
        Duas instâncias simultâneas: um elegível, um não elegível.
        Ambas devem completar independentemente.
        """
        id_eligible = start_process(cib7, PROCESS_KEY, {
            "patientId":           HAPPY_PATH_IDS["patient"],
            "insuranceCardNumber": "BC-12345-6789",
            "coverageStatus":      "active",
            "isEligible":          True,
            "appointmentId":       HAPPY_PATH_IDS["appointment"],
        })
        id_ineligible = start_process(cib7, PROCESS_KEY, {
            "patientId":           "rc-patient-other-001",
            "insuranceCardNumber": "BC-INVALIDO",
            "coverageStatus":      "inactive",
            "isEligible":          False,
        })

        state1 = wait_for_state(cib7, id_eligible,   "COMPLETED", timeout_s=TIMEOUT)
        state2 = wait_for_state(cib7, id_ineligible, "COMPLETED", timeout_s=TIMEOUT)

        assert state1 == "COMPLETED", f"Instância elegível: {state1}"
        assert state2 == "COMPLETED", f"Instância inelegível: {state2}"
