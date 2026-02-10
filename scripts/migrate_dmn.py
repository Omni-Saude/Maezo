#!/usr/bin/env python3
"""Migrate legacy DMN files to new platform structure based on migration manifest."""

import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "docs", "Migration", "migration_manifest.json")

def main():
    with open(MANIFEST, "r") as f:
        manifest = json.load(f)

    entries = manifest["entries"]
    total = len(entries)
    success = 0
    failed = 0
    failures = []

    domain_map = {
        "revenue_cycle": "platform/revenue_cycle/dmn",
        "patient_access": "platform/patient_access/dmn",
        "clinical_operations": "platform/clinical_operations/dmn",
        "platform_services": "platform/platform_services/dmn",
    }

    for entry in entries:
        legacy_rel = entry["legacy_path"]
        legacy_abs = os.path.join(ROOT, legacy_rel)

        domain = entry.get("domain", "")
        category = entry.get("category", "")
        subcategory = entry.get("subcategory", "")
        rule_id = entry.get("rule_id", "")

        base = domain_map.get(domain)
        if not base:
            failures.append((legacy_rel, f"Unknown domain: {domain}"))
            failed += 1
            continue

        sub_parts = [s.strip() for s in subcategory.split("/") if s.strip()]
        last_sub = sub_parts[-1] if sub_parts else ""

        filename = rule_id.lower().replace("-", "_") + ".dmn"

        if last_sub:
            target_rel = os.path.join(base, category, last_sub, filename)
        else:
            target_rel = os.path.join(base, category, filename)

        target_abs = os.path.join(ROOT, target_rel)

        if not os.path.isfile(legacy_abs):
            failures.append((legacy_rel, "Legacy file not found"))
            failed += 1
            continue

        try:
            os.makedirs(os.path.dirname(target_abs), exist_ok=True)
            shutil.copy2(legacy_abs, target_abs)
            success += 1
        except Exception as e:
            failures.append((legacy_rel, str(e)))
            failed += 1

    print(f"\n{'='*60}")
    print(f"DMN Migration Summary")
    print(f"{'='*60}")
    print(f"Total entries:  {total}")
    print(f"Attempted:      {total}")
    print(f"Successful:     {success}")
    print(f"Failed:         {failed}")
    print(f"{'='*60}")

    if failures:
        print(f"\nFailures ({len(failures)}):")
        for path, reason in failures:
            print(f"  - {path}: {reason}")

if __name__ == "__main__":
    main()
