"""BPMN process instantiation integration tests.

Parametrized tests that start a process instance for the main sub-process
definitions in each domain.  Tests are skipped individually when a process
definition key is not found (404) in the target engine, allowing the suite
to run against a partially-deployed engine without hard failures.

Author: CIB7 Platform Team
Version: 1.0.0
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import pytest
import requests


# Process definition keys to verify.
# Each tuple: (process_key, human_readable_label)
# Keys must match the ``id`` attribute of <bpmn:process> in the actual BPMN files.
PROCESS_DEFINITIONS: Tuple[Tuple[str, str], ...] = (
    # Revenue Cycle
    ("SP_RC_001_Scheduling_Registration", "Revenue Cycle - Scheduling & Registration"),
    # Patient Access
    ("Process_DemandCapture", "Patient Access - Demand Capture"),
    # Clinical Operations
    ("SP_CO_001_Triage_Routing", "Clinical Operations - Triage & Clinical Routing"),
    # Platform Services
    ("Process_ComplianceAudit", "Platform Services - Compliance Audit"),
)


def _start_process(
    cib7_url: str,
    session: requests.Session,
    process_key: str,
    variables: Dict[str, Any] | None = None,
) -> requests.Response:
    """POST to /process-definition/key/{key}/start and return the response."""
    payload: Dict[str, Any] = {"variables": variables or {}}
    return session.post(
        f"{cib7_url}/process-definition/key/{process_key}/start",
        json=payload,
        timeout=15,
    )


@pytest.mark.integration
@pytest.mark.bpmn
@pytest.mark.slow
@pytest.mark.requires_engine
@pytest.mark.parametrize(
    "process_key,label",
    PROCESS_DEFINITIONS,
    ids=[key for key, _ in PROCESS_DEFINITIONS],
)
def test_process_instantiation(
    process_key: str,
    label: str,
    cib7_url: str,
    cib7_client: requests.Session,
    engine_available: bool,
) -> None:
    """Start a process instance for ``process_key`` and assert HTTP 200.

    The test is skipped when:
    - The CIB7 engine is not reachable.
    - The process definition does not exist (HTTP 404) in the deployed engine.

    A 200 response confirms the engine accepted the start request and the
    BPMN was successfully deployed and registered.
    """
    if not engine_available:
        pytest.skip("CIB7 engine is not available at %s" % cib7_url)

    try:
        resp = _start_process(cib7_url, cib7_client, process_key)
    except requests.exceptions.RequestException as exc:
        pytest.fail(
            "Network error starting process %r (%s): %s" % (process_key, label, exc)
        )

    if resp.status_code == 404:
        pytest.skip(
            "Process definition %r not deployed in engine (404) — skipping" % process_key
        )

    assert resp.status_code == 200, (
        "Expected HTTP 200 starting process %r (%s), got %d: %s"
        % (process_key, label, resp.status_code, resp.text[:300])
    )
