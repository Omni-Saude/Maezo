#!/usr/bin/env python3
"""DMN Tenant Override Resolver - Validates tenant resolution per ADR-007.

Checks:
- Duplicate decision_ids across tenants
- Global fallback exists for each tenant-specific DMN
- Reports override matrix

Usage:
    python scripts/dmn_tenant_resolver.py
    python scripts/dmn_tenant_resolver.py --path healthcare_platform/
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    sys.exit("ERROR: lxml is required. Install with: pip install lxml")

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"


def detect_tenant(filepath: str) -> str:
    """Detect tenant from file path. Returns 'global' if no tenant folder."""
    parts = Path(filepath).parts
    for i, part in enumerate(parts):
        if part == "tenants" and i + 1 < len(parts):
            return parts[i + 1]
    return "global"


def extract_decision_ids(filepath: str) -> list[str]:
    """Extract all decision IDs from a DMN file."""
    try:
        tree = etree.parse(filepath)
    except etree.XMLSyntaxError:
        return []

    root = tree.getroot()
    ids = []
    for decision in root.findall(".//{%s}decision" % DMN_NS):
        did = decision.get("id", "")
        if did:
            ids.append(did)
    return ids


def build_tenant_map(root_path: str) -> dict[str, dict[str, list[str]]]:
    """Build mapping: decision_id -> {tenant -> [files]}.

    Returns dict where keys are decision_ids and values are dicts
    mapping tenant_id to list of files containing that decision.
    """
    decision_map: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for dirpath, _, filenames in os.walk(root_path):
        for fn in sorted(filenames):
            if fn.endswith(".dmn"):
                filepath = os.path.join(dirpath, fn)
                tenant = detect_tenant(filepath)
                for decision_id in extract_decision_ids(filepath):
                    decision_map[decision_id][tenant].append(filepath)

    return dict(decision_map)


def validate_tenant_resolution(decision_map: dict) -> list[dict]:
    """Validate tenant override resolution per ADR-007.

    Rules:
    - Each tenant-specific decision should have a global fallback
    - Duplicate decision_ids within the same tenant are flagged
    """
    issues = []

    for decision_id, tenants in sorted(decision_map.items()):
        tenant_list = [t for t in tenants if t != "global"]
        has_global = "global" in tenants

        # Check for tenant-specific without global fallback
        if tenant_list and not has_global:
            issues.append({
                "decision_id": decision_id,
                "issue": "MISSING_GLOBAL_FALLBACK",
                "tenants": tenant_list,
                "message": f"Tenant-specific DMN exists without global fallback",
            })

        # Check for duplicate files within same tenant
        for tenant, files in tenants.items():
            if len(files) > 1:
                issues.append({
                    "decision_id": decision_id,
                    "issue": "DUPLICATE_IN_TENANT",
                    "tenant": tenant,
                    "files": files,
                    "message": f"Decision '{decision_id}' defined {len(files)} times in tenant '{tenant}'",
                })

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DMN tenant override resolution (ADR-007)")
    parser.add_argument("--path", default="healthcare_platform/", help="Root directory to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"ERROR: '{args.path}' is not a directory", file=sys.stderr)
        return 1

    print(f"Scanning {args.path} for tenant override validation (ADR-007)...")
    decision_map = build_tenant_map(args.path)

    # Summary
    total_decisions = len(decision_map)
    global_only = sum(1 for d, t in decision_map.items() if list(t.keys()) == ["global"])
    with_overrides = sum(1 for d, t in decision_map.items() if any(k != "global" for k in t))
    all_tenants = set()
    for tenants in decision_map.values():
        all_tenants.update(t for t in tenants if t != "global")

    print(f"\nTenant Resolution Summary:")
    print(f"  Total unique decisions: {total_decisions}")
    print(f"  Global-only decisions:  {global_only}")
    print(f"  Decisions with tenant overrides: {with_overrides}")
    print(f"  Tenants found: {sorted(all_tenants) if all_tenants else ['(none - all global)']}")

    # Validate
    issues = validate_tenant_resolution(decision_map)

    if args.json:
        report = {
            "total_decisions": total_decisions,
            "global_only": global_only,
            "with_overrides": with_overrides,
            "tenants": sorted(all_tenants),
            "issues": issues,
        }
        print(json.dumps(report, indent=2))
        return 1 if issues else 0

    if issues:
        print(f"\nIssues Found ({len(issues)}):")
        for issue in issues:
            print(f"  [{issue['issue']}] {issue['decision_id']}: {issue['message']}")
            if "files" in issue:
                for f in issue["files"]:
                    print(f"    - {f}")
        return 1

    print("\nAll tenant overrides are properly resolved. No issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
