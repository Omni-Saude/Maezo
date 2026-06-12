"""
test_rc004_bpmn.py — Integração SP-RC-004 Produção Clínica.

Testa o fluxo SP_RC_004_Clinical_Production.
Todos os tasks são bpmn:task (auto-complete) — nenhum worker externo necessário.

Fluxo principal (happy path):
  start → assign_prices (auto) → dmn_contract_pricing (auto) → dmn_package_pricing (auto)
       → validate_compatibility (auto, compatibilityStatus=compatibilityResult)
       → gateway_compatibility (FEEL: =compatibilityStatus = true)
         Sim: → calculate_production (auto) → collect_data (auto)
              → dmn_outlier_detection (auto, outlierAnalysis.isOutlier=?)
              → gateway_outlier (FEEL: =outlierAnalysis.isOutlier = false)
                Não: → Gateway_07jleu7 → record_production → end_success (COMPLETED)
                Sim: → review_outlier (auto) → timer 24h → re-detect
         Não: → review_incompatibility (auto) → end_incompatible (COMPLETED)

Variáveis chave:
  compatibilityResult (bool) → outputParameter → compatibilityStatus
  Gateway condition FEEL: =compatibilityStatus = true

  outlierAnalysis (dict com isOutlier bool) — pode ser passado diretamente
  Gateway condition FEEL: =outlierAnalysis.isOutlier = false

  outlierRevisaoNecessaria (bool) → Gateway_1uvv8tp condition JUEL: ${outlierRevisaoNecessaria == true}

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
    trigger_timers,
    wait_for_state,
)

PROCESS_KEY = "SP_RC_004_Clinical_Production"
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
class TestRC004ClinicalProduction:
    """
    Integração SP-RC-004 — todos os tasks são bpmn:task (auto-complete).
    Sem workers externos. Variáveis controladas via parâmetros de início.
    """

    def test_happy_path_compatible_not_outlier(self, cib7, require_cib7):
        """
        Happy path: procedimentos compatíveis, não é outlier.
          compatibilityResult=true → gateway_compatibility toma flow_compatible (FEEL: =compatibilityStatus = true)
          outlierAnalysis.isOutlier=false → gateway_outlier toma flow_not_outlier
          → record_production → end_success → COMPLETED.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":          HAPPY_PATH_IDS["patient"],
            "encounterId":        HAPPY_PATH_IDS["encounter"],
            "procedureCodes":     "40101010",
            # Variáveis-fonte para output parameters das bpmn:task (auto-complete):
            "pricedProcedures":   "[]",               # task_assign_prices → proceduresWithPrices
            "compatibilityResult": True,               # task_validate_compatibility → compatibilityStatus
            "incompatibleItems":  "",                  # task_validate_compatibility → incompatibilities
            "totalValue":         1000,                # task_calculate_production → productionValue
            "breakdown":          "[]",               # task_calculate_production → valueBreakdown
            "outlierAnalysis":    {"isOutlier": False},  # dmn_outlier_detection (bpmn:task)
            "outlierRevisaoNecessaria": False,
            "productionId":       "prod-001",         # task_record_production → recordedProductionId
        })
        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)
        assert state == "COMPLETED", f"Estado inesperado: {state}"

        vars_ = get_process_variables(cib7, instance_id)
        assert vars_.get("compatibilityStatus") is True

    def test_incompatible_procedures_ends_incompatible(self, cib7, require_cib7):
        """
        Procedimentos incompatíveis: compatibilityResult=false → compatibilityStatus=false
        → gateway_compatibility default (flow_incompatible)
        → review_incompatibility → end_incompatible → COMPLETED.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":           HAPPY_PATH_IDS["patient"],
            "encounterId":         HAPPY_PATH_IDS["encounter"],
            "procedureCodes":      "40101010",
            "pricedProcedures":    "[]",
            "compatibilityResult": False,
            "incompatibleItems":   "40101010",
        })
        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)
        assert state == "COMPLETED", f"Estado inesperado: {state}"

        vars_ = get_process_variables(cib7, instance_id)
        assert vars_.get("compatibilityStatus") is False

    def test_outlier_detected_accepted_completes(self, cib7, require_cib7):
        """
        Outlier detectado mas aceito (outlierRevisaoNecessaria=false):
          compatibilityResult=true → flow_compatible
          outlierAnalysis.isOutlier=true → flow_is_outlier → review_outlier → timer 24h
          Após timer: → Gateway_010dozk → collect_data → dmn_outlier_detection
          outlierAnalysis.isOutlier=false + outlierRevisaoNecessaria=false
            → Gateway_1uvv8tp toma Flow_1cbai6y (sim/aceito)
            → record_production → end_success → COMPLETED.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":               HAPPY_PATH_IDS["patient"],
            "encounterId":             HAPPY_PATH_IDS["encounter"],
            "procedureCodes":          "40101010",
            "pricedProcedures":        "[]",
            "compatibilityResult":     True,
            "incompatibleItems":       "",
            "totalValue":              1000,
            "breakdown":               "[]",
            # 1ª passagem: outlier detectado
            "outlierAnalysis":         {"isOutlier": True},
            "outlierRevisaoNecessaria": False,  # aceito após revisão
            "productionId":            "prod-002",
        })

        import time
        time.sleep(3)
        trigger_timers(cib7, instance_id, wait_s=5)

        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=45)
        assert state == "COMPLETED", f"Estado inesperado: {state}"

    def test_no_compatibility_result_takes_incompatible_default(self, cib7, require_cib7):
        """
        compatibilityResult não definido → compatibilityStatus=null
        FEEL: =compatibilityStatus = true → false → default flow_incompatible → COMPLETED.
        """
        instance_id = start_process(cib7, PROCESS_KEY, {
            "patientId":          HAPPY_PATH_IDS["patient"],
            "encounterId":        HAPPY_PATH_IDS["encounter"],
            "pricedProcedures":   "[]",
            "compatibilityResult": False,
            "incompatibleItems":  "",
        })
        state = wait_for_state(cib7, instance_id, "COMPLETED", timeout_s=TIMEOUT)
        assert state == "COMPLETED", f"Estado inesperado: {state}"
