"""BPMN topic-to-worker connectivity tests.

Verifies that:
1. Every ``camunda:topic`` declared in any BPMN file has a corresponding
   Python worker that exports a matching ``TOPIC`` constant.
2. Every topic string follows the required ``dot.snake_case`` format
   (no dashes, no camelCase, no uppercase letters after a dot).

Author: CIB7 Platform Team
Version: 1.0.0
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set

import pytest


# Camunda 7 XML namespaces used in BPMN files
_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"

# Regex patterns for topic format validation
# Valid: dot.snake_case  e.g. "revenue_cycle.verify_insurance", "surgical.specimen"
# The top-level prefix may itself contain underscores.
_VALID_TOPIC_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
# Forbidden patterns
_HAS_DASH_RE = re.compile(r"-")
_HAS_CAMEL_RE = re.compile(r"[A-Z]")


def _extract_bpmn_topics(bpmn_path: Path) -> Set[str]:
    """Return the set of ``camunda:topic`` values declared in a BPMN file."""
    topics: Set[str] = set()
    raw = bpmn_path.read_text(encoding="utf-8")

    # Use regex as a fast pre-filter to avoid XML namespace registration costs
    for match in re.finditer(r'camunda:topic=["\']([^"\']+)["\']', raw):
        topics.add(match.group(1))

    return topics


@pytest.mark.integration
@pytest.mark.bpmn
class TestTopicConnectivity:
    """Ensure every BPMN topic has a backing worker implementation."""

    def test_all_bpmn_topics_have_workers(
        self,
        bpmn_files: List[Path],
        worker_topics: Dict[str, List[str]],
    ) -> None:
        """Every ``camunda:topic`` in a BPMN must map to a worker TOPIC constant.

        Topics that are declared in BPMN files but have no corresponding
        worker are reported as failures.
        """
        assert bpmn_files, "No BPMN files found under healthcare_platform"

        all_bpmn_topics: Dict[str, List[str]] = {}  # topic -> [bpmn files]

        for bpmn_path in bpmn_files:
            for topic in _extract_bpmn_topics(bpmn_path):
                all_bpmn_topics.setdefault(topic, []).append(bpmn_path.name)

        if not all_bpmn_topics:
            pytest.skip("No camunda:topic attributes found in any BPMN file")

        orphan_topics: List[str] = []
        for topic, files in sorted(all_bpmn_topics.items()):
            # Skip BPMN template topics — design-time stencils, not deployed processes
            if topic.startswith("template."):
                continue
            if topic not in worker_topics:
                orphan_topics.append(
                    "  topic=%r  found in: %s" % (topic, ", ".join(files))
                )

        assert not orphan_topics, (
            "%d BPMN topic(s) have no matching worker TOPIC constant:\n%s"
            % (len(orphan_topics), "\n".join(orphan_topics))
        )


@pytest.mark.integration
@pytest.mark.bpmn
class TestTopicFormatCompliance:
    """Validate topic string formatting rules."""

    def test_topic_format_compliance(
        self,
        bpmn_files: List[Path],
        worker_topics: Dict[str, List[str]],
    ) -> None:
        """All topics must use dot.snake_case format with no dashes or camelCase.

        Checks topics sourced from both BPMN files and worker TOPIC constants
        to surface violations wherever they originate.
        """
        # Collect topics from BPMN files
        bpmn_topics: Dict[str, str] = {}
        for bpmn_path in bpmn_files:
            for topic in _extract_bpmn_topics(bpmn_path):
                bpmn_topics[topic] = "BPMN:%s" % bpmn_path.name

        # Combine with worker-sourced topics
        all_topics: Dict[str, str] = {}
        all_topics.update(
            {
                t: "worker:%s" % ",".join(Path(src).name for src in srcs)
                for t, srcs in worker_topics.items()
            }
        )
        all_topics.update(bpmn_topics)  # BPMN entry overwrites if duplicate

        violations: List[str] = []
        for topic, source in sorted(all_topics.items()):
            reasons: List[str] = []
            if _HAS_DASH_RE.search(topic):
                reasons.append("contains dashes")
            if _HAS_CAMEL_RE.search(topic):
                reasons.append("contains uppercase letters (camelCase forbidden)")
            if not _VALID_TOPIC_RE.match(topic):
                reasons.append("does not match dot.snake_case pattern")

            if reasons:
                violations.append(
                    "  topic=%r (%s): %s" % (topic, source, "; ".join(reasons))
                )

        assert not violations, (
            "%d topic(s) violate the dot.snake_case format rule:\n%s"
            % (len(violations), "\n".join(violations))
        )
