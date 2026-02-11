#!/usr/bin/env python3
"""DMN XML Validator - Validates DMN 1.3 schema compliance and FEEL expressions.

Usage:
    python scripts/validate_dmn.py healthcare_platform/
    python scripts/validate_dmn.py healthcare_platform/ --dry-run
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from lxml import etree
except ImportError:
    sys.exit("ERROR: lxml is required. Install with: pip install lxml")

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"
NSMAP = {"dmn": DMN_NS}

VALID_HIT_POLICIES = {
    "UNIQUE", "FIRST", "PRIORITY", "ANY",
    "COLLECT", "RULE ORDER", "OUTPUT ORDER",
}

VALID_TYPE_REFS = {
    "string", "boolean", "number", "integer", "long", "double",
    "date", "time", "dateTime", "dayTimeDuration", "yearMonthDuration",
}

# FEEL 1.3 syntax patterns for validation
FEEL_DATE_RE = re.compile(r'date\(\s*"[^"]*"\s*\)')
FEEL_TIME_RE = re.compile(r'time\(\s*"[^"]*"\s*\)')
FEEL_DURATION_RE = re.compile(r'duration\(\s*"[^"]*"\s*\)')
FEEL_UNMATCHED_QUOTE_RE = re.compile(r"(?<![\\])\"(?:[^\"\\]|\\.)*$")
FEEL_KEYWORDS = {"and", "or", "not", "in", "between", "true", "false", "null"}


@dataclass
class ValidationError:
    file: str
    line: Optional[int]
    error_type: str
    message: str

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.error_type}] {loc}: {self.message}"


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)
    files_checked: int = 0
    files_valid: int = 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


def validate_feel_expression(text: str, file: str, line: Optional[int]) -> list[ValidationError]:
    """Validate a FEEL 1.3 expression for common syntax issues."""
    errors: list[ValidationError] = []
    if not text or not text.strip():
        return errors

    stripped = text.strip()

    # Check unmatched quotes
    quote_count = stripped.count('"') - stripped.count('\\"')
    if quote_count % 2 != 0:
        errors.append(ValidationError(file, line, "FEEL_SYNTAX", f"Unmatched double quote in: {stripped[:80]}"))

    # Check unmatched brackets
    for open_c, close_c, name in [("[", "]", "bracket"), ("(", ")", "parenthesis"), ("{", "}", "brace")]:
        if stripped.count(open_c) != stripped.count(close_c):
            errors.append(ValidationError(file, line, "FEEL_SYNTAX", f"Unmatched {name} in: {stripped[:80]}"))

    # Check single-quoted strings (FEEL uses double quotes)
    if re.search(r"(?<![a-zA-Z])'[^']*'(?!\))", stripped):
        # Allow date('...'), time('...'), duration('...')
        no_funcs = re.sub(r"(date|time|duration)\('[^']*'\)", "", stripped)
        if "'" in no_funcs:
            errors.append(ValidationError(file, line, "FEEL_SYNTAX", f"FEEL 1.3 uses double quotes for strings, not single: {stripped[:80]}"))

    # Check date literal format: date("...") not date('...')  -- already covered above
    # Check list syntax: should use [ ] not ( ) for lists
    # Check invalid operators
    if "==" in stripped:
        errors.append(ValidationError(file, line, "FEEL_SYNTAX", f"Use '=' not '==' for equality in FEEL: {stripped[:80]}"))

    if "!=" in stripped:
        errors.append(ValidationError(file, line, "FEEL_SYNTAX", f"Use 'not()' or '!= ' is allowed but prefer FEEL idioms: {stripped[:80]}"))

    return errors


def validate_dmn_file(filepath: str) -> list[ValidationError]:
    """Validate a single DMN file for schema compliance and FEEL syntax."""
    errors: list[ValidationError] = []

    # Parse XML
    try:
        tree = etree.parse(filepath)
    except etree.XMLSyntaxError as e:
        errors.append(ValidationError(filepath, getattr(e, "lineno", None), "XML_PARSE", str(e)))
        return errors

    root = tree.getroot()

    # Check root element is 'definitions'
    local_name = etree.QName(root.tag).localname
    if local_name != "definitions":
        errors.append(ValidationError(filepath, 1, "SCHEMA", f"Root element must be 'definitions', got '{local_name}'"))
        return errors

    # Check DMN namespace
    ns = etree.QName(root.tag).namespace
    if ns and "DMN" not in ns.upper():
        errors.append(ValidationError(filepath, 1, "SCHEMA", f"Unexpected namespace: {ns}"))

    # Validate decisions
    decisions = root.findall(".//dmn:decision", NSMAP)
    if not decisions:
        # Try without namespace (some files may use default ns)
        decisions = root.findall(".//{%s}decision" % DMN_NS)

    if not decisions:
        errors.append(ValidationError(filepath, None, "SCHEMA", "No <decision> elements found"))
        return errors

    for decision in decisions:
        decision_id = decision.get("id", "unknown")
        decision_name = decision.get("name", "")

        if not decision_id or decision_id == "unknown":
            errors.append(ValidationError(filepath, decision.sourceline, "SCHEMA", "Decision missing 'id' attribute"))

        # Find decisionTable
        tables = decision.findall("{%s}decisionTable" % DMN_NS)
        for table in tables:
            hit_policy = table.get("hitPolicy", "UNIQUE")
            if hit_policy not in VALID_HIT_POLICIES:
                errors.append(ValidationError(
                    filepath, table.sourceline, "SCHEMA",
                    f"Invalid hitPolicy '{hit_policy}' in {decision_id}. Valid: {VALID_HIT_POLICIES}"
                ))

            # Validate inputs
            for inp in table.findall("{%s}input" % DMN_NS):
                input_expr = inp.find("{%s}inputExpression" % DMN_NS)
                if input_expr is not None:
                    type_ref = input_expr.get("typeRef")
                    if type_ref and type_ref not in VALID_TYPE_REFS:
                        errors.append(ValidationError(
                            filepath, input_expr.sourceline, "TYPE",
                            f"Unknown typeRef '{type_ref}' in {decision_id}"
                        ))
                    text_el = input_expr.find("{%s}text" % DMN_NS)
                    if text_el is not None and text_el.text:
                        errors.extend(validate_feel_expression(text_el.text, filepath, text_el.sourceline))

            # Validate outputs
            for out in table.findall("{%s}output" % DMN_NS):
                type_ref = out.get("typeRef")
                if type_ref and type_ref not in VALID_TYPE_REFS:
                    errors.append(ValidationError(
                        filepath, out.sourceline, "TYPE",
                        f"Unknown typeRef '{type_ref}' in output of {decision_id}"
                    ))

            # Validate rules
            rules = table.findall("{%s}rule" % DMN_NS)
            if not rules:
                errors.append(ValidationError(
                    filepath, table.sourceline, "SCHEMA",
                    f"DecisionTable '{decision_id}' has no rules"
                ))

            for rule in rules:
                # Check inputEntry FEEL expressions
                for entry in rule.findall("{%s}inputEntry" % DMN_NS):
                    text_el = entry.find("{%s}text" % DMN_NS)
                    if text_el is not None and text_el.text:
                        errors.extend(validate_feel_expression(text_el.text, filepath, text_el.sourceline))

                # Check outputEntry FEEL expressions
                for entry in rule.findall("{%s}outputEntry" % DMN_NS):
                    text_el = entry.find("{%s}text" % DMN_NS)
                    if text_el is not None and text_el.text:
                        errors.extend(validate_feel_expression(text_el.text, filepath, text_el.sourceline))

    return errors


def find_dmn_files(root_path: str) -> list[str]:
    """Recursively find all .dmn files under the given path."""
    files = []
    for dirpath, _, filenames in os.walk(root_path):
        for fn in sorted(filenames):
            if fn.endswith(".dmn"):
                files.append(os.path.join(dirpath, fn))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DMN 1.3 files")
    parser.add_argument("path", help="Root directory to scan for .dmn files")
    parser.add_argument("--dry-run", action="store_true", help="List files without validating")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-file status")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"ERROR: '{args.path}' is not a directory", file=sys.stderr)
        return 1

    dmn_files = find_dmn_files(args.path)
    print(f"Found {len(dmn_files)} DMN files in {args.path}")

    if args.dry_run:
        for f in dmn_files:
            print(f"  {f}")
        return 0

    result = ValidationResult()
    result.files_checked = len(dmn_files)

    for filepath in dmn_files:
        file_errors = validate_dmn_file(filepath)
        if file_errors:
            result.errors.extend(file_errors)
        else:
            result.files_valid += 1

        if args.verbose:
            status = "FAIL" if file_errors else "OK"
            print(f"  [{status}] {filepath}")

    # Report
    print(f"\n{'='*60}")
    print(f"DMN Validation Report")
    print(f"{'='*60}")
    print(f"Files checked:  {result.files_checked}")
    print(f"Files valid:    {result.files_valid}")
    print(f"Files with errors: {result.files_checked - result.files_valid}")
    print(f"Total errors:   {len(result.errors)}")

    if result.errors:
        print(f"\nErrors:")
        for err in result.errors:
            print(f"  {err}")
        return 1

    print("\nAll DMN files are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
