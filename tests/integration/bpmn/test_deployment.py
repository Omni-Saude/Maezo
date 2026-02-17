"""BPMN deployment integration tests.

Verifies that every BPMN file in the repository can be deployed to
a running CIB7 (Camunda 7) engine.  Tests are skipped automatically
when the engine is unreachable.

Author: CIB7 Platform Team
Version: 1.0.0
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests


def pytest_generate_tests(metafunc):
    if "bpmn_path" in metafunc.fixturenames:
        bpmn_dir = Path(__file__).parents[3] / "healthcare_platform"
        files = sorted(
            p for p in bpmn_dir.rglob("*.bpmn")
            if not any(part.startswith(".") for part in p.parts)
        )
        metafunc.parametrize("bpmn_path", files, ids=[f.name for f in files])


@pytest.mark.integration
@pytest.mark.bpmn
@pytest.mark.slow
@pytest.mark.requires_engine
def test_deploy_bpmn_file(
    bpmn_path: Path,
    cib7_url: str,
    cib7_client: requests.Session,
    engine_available: bool,
) -> None:
    """POST a single .bpmn file to /deployment/create and assert HTTP 200.

    Skips when the CIB7 engine is not reachable.
    """
    if not engine_available:
        pytest.skip("CIB7 engine is not available at %s" % cib7_url)

    deployment_name = bpmn_path.stem
    with bpmn_path.open("rb") as fh:
        files = {
            "deployment-name": (None, deployment_name),
            "enable-duplicate-filtering": (None, "true"),
            "deploy-changed-only": (None, "true"),
            bpmn_path.name: (
                bpmn_path.name,
                fh,
                "application/octet-stream",
            ),
        }
        try:
            resp = cib7_client.post(
                f"{cib7_url}/deployment/create",
                files=files,
                timeout=15,
            )
        except requests.exceptions.RequestException as exc:
            pytest.fail("%s -> %s" % (bpmn_path.name, exc))

    assert resp.status_code == 200, (
        "%s -> HTTP %d: %s"
        % (bpmn_path.name, resp.status_code, resp.text[:200])
    )
