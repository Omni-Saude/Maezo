"""Fixtures for BPMN integration tests.

Provides session-scoped fixtures for CIB7 engine connectivity,
BPMN file discovery, and worker TOPIC constant collection.

Author: CIB7 Platform Team
Version: 1.0.0
"""

from __future__ import annotations

import ast
import os
import re
import time
from pathlib import Path
from typing import Dict, List

import yaml
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ── CIB7 Engine Fixtures ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def cib7_url() -> str:
    """Return the CIB7 REST engine URL.

    Reads from the CIB7_URL environment variable.
    Defaults to http://localhost:8080/engine-rest.
    """
    return os.environ.get("CIB7_URL", "http://localhost:8080/engine-rest")


@pytest.fixture(scope="session")
def cib7_client(cib7_url: str) -> requests.Session:
    """Return a requests.Session configured to reach the CIB7 engine.

    Applies retry logic and waits up to 30 seconds for the engine to
    become available before returning.  If the engine is unreachable the
    fixture yields the session anyway so individual tests can skip
    themselves via the ``skip_if_unavailable`` helper.
    """
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Wait for engine to become available (up to 30 seconds)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            resp = session.get(f"{cib7_url}/version", timeout=3)
            if resp.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)

    return session


@pytest.fixture(scope="session")
def engine_available(cib7_url: str, cib7_client: requests.Session) -> bool:
    """Return True when the CIB7 engine version endpoint responds with HTTP 200."""
    try:
        resp = cib7_client.get(f"{cib7_url}/version", timeout=5)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


# ── BPMN File Discovery Fixtures ─────────────────────────────────────


@pytest.fixture(scope="session")
def bpmn_dir() -> Path:
    """Return the root directory that contains all BPMN files."""
    workspace = Path(__file__).parents[3]  # repo root
    return workspace / "healthcare_platform"


@pytest.fixture(scope="session")
def bpmn_files(bpmn_dir: Path) -> List[Path]:
    """Return a sorted list of all .bpmn files under healthcare_platform.

    Archive directories (prefixed with ``.``) are excluded so that
    superseded process definitions do not pollute the test run.
    """
    files: List[Path] = []
    for path in bpmn_dir.rglob("*.bpmn"):
        # Exclude hidden/archive directories such as .archive, .archived-duplicates
        if any(part.startswith(".") for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


# ── Worker TOPIC Discovery Fixture ───────────────────────────────────


def _extract_topics_from_file(path: Path) -> List[str]:
    """Extract TOPIC string values from a Python worker source file.

    Handles both module-level assignments (``TOPIC = "..."```) and
    class-level assignments (``TOPIC = "..."`` inside a class body).
    """
    topics: List[str] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return topics

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOPIC":
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        topics.append(node.value.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "TOPIC":
                if node.value and isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    topics.append(node.value.value)

    return topics


@pytest.fixture(scope="session")
def worker_topics(bpmn_dir: Path) -> Dict[str, List[str]]:
    """Return a mapping of TOPIC value -> list of source file paths for all active workers.

    Scans all ``*worker*.py`` files under ``healthcare_platform``, excluding
    archive and test directories.  Also includes topics defined in the
    central topic_registry.yaml so that registry-registered topics are
    recognized without requiring a dedicated worker file.
    """
    topics: Dict[str, List[str]] = {}
    for worker_file in bpmn_dir.rglob("*worker*.py"):
        # Exclude archive directories and test files
        if any(part.startswith(".") for part in worker_file.parts):
            continue
        if "test_" in worker_file.name:
            continue
        for topic in _extract_topics_from_file(worker_file):
            topics.setdefault(topic, []).append(str(worker_file))

    # Also load topics from the central topic_registry.yaml
    registry_path = bpmn_dir.parent / "config" / "topic_registry.yaml"
    if registry_path.exists():
        with registry_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        registry_topics = raw.get("topics", {})
        if isinstance(registry_topics, dict):
            for topic_name in registry_topics:
                if topic_name not in topics:
                    topics[topic_name] = [str(registry_path)]

    return topics
