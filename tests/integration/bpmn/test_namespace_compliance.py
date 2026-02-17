"""BPMN namespace compliance tests.

Verifies that every BPMN file:
- Declares the Camunda 7 namespace
- Does NOT declare any Zeebe (Camunda 8) namespace

These checks ensure all process definitions target the correct engine
and that no Camunda 8 / Zeebe constructs have been accidentally
introduced.

Author: CIB7 Platform Team
Version: 1.0.0
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

import pytest


CAMUNDA7_NAMESPACE = "http://camunda.org/schema/1.0/bpmn"
ZEEBE_NAMESPACE_FRAGMENT = "zeebe"


@pytest.mark.integration
@pytest.mark.bpmn
class TestBpmnNamespaceCompliance:
    """Namespace compliance checks for all BPMN files."""

    def test_all_bpmn_have_camunda7_namespace(
        self, bpmn_files: List[Path]
    ) -> None:
        """Every BPMN file must declare the Camunda 7 namespace.

        The raw XML text is searched for the namespace URI to confirm that
        ``xmlns:camunda="http://camunda.org/schema/1.0/bpmn"`` (or any
        equivalent xmlns declaration binding that URI) is present.

        Note: Python's ``xml.etree.ElementTree`` strips xmlns declarations
        from ``root.attrib``; raw-text search is the correct approach to
        detect namespace declarations, consistent with the Zeebe check below.
        """
        assert bpmn_files, "No BPMN files found under healthcare_platform"

        missing: List[str] = []
        unreadable: List[str] = []

        for bpmn_path in bpmn_files:
            try:
                raw_text = bpmn_path.read_text(encoding="utf-8")
            except OSError as exc:
                unreadable.append(
                    "Could not read %s: %s" % (bpmn_path.name, exc)
                )
                continue

            try:
                ET.parse(str(bpmn_path))
            except ET.ParseError as exc:
                unreadable.append(
                    "XML parse error in %s: %s" % (bpmn_path.name, exc)
                )
                continue

            if CAMUNDA7_NAMESPACE not in raw_text:
                missing.append(str(bpmn_path))

        errors: List[str] = []
        if unreadable:
            errors.append(
                "%d BPMN file(s) could not be parsed:\n%s"
                % (len(unreadable), "\n".join(unreadable))
            )
        if missing:
            errors.append(
                "%d BPMN file(s) missing Camunda 7 namespace (%s):\n%s"
                % (len(missing), CAMUNDA7_NAMESPACE, "\n".join(missing))
            )

        assert not errors, "\n\n".join(errors)

    def test_no_zeebe_namespace_in_any_bpmn(
        self, bpmn_files: List[Path]
    ) -> None:
        """No BPMN file may contain a Zeebe (Camunda 8) namespace declaration.

        The check is a simple string search for the word 'zeebe' (case-
        insensitive) which covers all known Zeebe namespace URIs such as
        ``http://camunda.org/schema/zeebe/1.0``.
        """
        assert bpmn_files, "No BPMN files found under healthcare_platform"

        violations: List[str] = []
        unreadable: List[str] = []

        for bpmn_path in bpmn_files:
            try:
                raw_text = bpmn_path.read_text(encoding="utf-8")
            except OSError as exc:
                unreadable.append(
                    "Could not read %s: %s" % (bpmn_path.name, exc)
                )
                continue

            if ZEEBE_NAMESPACE_FRAGMENT in raw_text.lower():
                violations.append(str(bpmn_path))

        errors: List[str] = []
        if unreadable:
            errors.append(
                "%d BPMN file(s) could not be read:\n%s"
                % (len(unreadable), "\n".join(unreadable))
            )
        if violations:
            errors.append(
                "%d BPMN file(s) contain a Zeebe namespace (forbidden in CIB7):\n%s"
                % (len(violations), "\n".join(violations))
            )

        assert not errors, "\n\n".join(errors)
