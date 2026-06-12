#!/usr/bin/env python3
"""Fix DMN XML/Schema issues across all .dmn files in src/.

Issues addressed:
1. namespace= → targetNamespace= (545 files)
2. DMN 1.1 namespace → DMN 1.3 (22 files)
3. JSON files with .dmn extension → renamed to .json (2 files)
4. CRLF → LF line endings (all files)
5. Single-quote XML declarations → double-quote (consistency)
"""

import os
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

# Counters
stats = {
    "total": 0,
    "namespace_fixed": 0,
    "dmn11_upgraded": 0,
    "json_renamed": 0,
    "crlf_fixed": 0,
    "quotes_fixed": 0,
    "skipped": 0,
}


def fix_dmn_file(filepath: Path) -> None:
    """Apply all fixes to a single DMN file."""
    raw = filepath.read_bytes()
    content = raw.decode("utf-8", errors="replace")

    # --- Detect JSON files masquerading as .dmn ---
    stripped = content.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        new_path = filepath.with_suffix(".json")
        filepath.rename(new_path)
        stats["json_renamed"] += 1
        print(f"  RENAMED -> {new_path.name} (was JSON, not DMN)")
        return

    changed = False

    # --- Fix 1: namespace= → targetNamespace= ---
    # Match bare `namespace=` that is NOT `xmlns:*namespace=` or `targetNamespace=`
    # In DMN <definitions> tag, the attribute appears as ` namespace="`
    pattern_ns = re.compile(
        r'(<definitions\b[^>]*?)\bnamespace=',
        re.DOTALL,
    )
    # Only replace if targetNamespace is not already present
    if "targetNamespace=" not in content and pattern_ns.search(content):
        content = pattern_ns.sub(r'\1targetNamespace=', content)
        stats["namespace_fixed"] += 1
        changed = True

    # --- Fix 2: Upgrade DMN 1.1 → DMN 1.3 namespace ---
    old_ns = "http://www.omg.org/spec/DMN/20151101/dmn.xsd"
    new_ns = "https://www.omg.org/spec/DMN/20191111/MODEL/"
    if old_ns in content:
        content = content.replace(old_ns, new_ns)
        # Also add DMNDI/DC namespaces if missing (required for DMN 1.3)
        if 'xmlns:dmndi=' not in content:
            content = content.replace(
                f'xmlns="{new_ns}"',
                f'xmlns="{new_ns}"\n             xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/"\n             xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/"',
            )
        stats["dmn11_upgraded"] += 1
        changed = True

    # --- Fix 3: Normalize XML declaration quotes ---
    # <?xml version='1.0' encoding='UTF-8'?> → <?xml version="1.0" encoding="UTF-8"?>
    old_decl_patterns = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<?xml version='1.0' encoding='utf-8'?>",
    ]
    for old_decl in old_decl_patterns:
        if old_decl in content:
            content = content.replace(old_decl, '<?xml version="1.0" encoding="UTF-8"?>')
            stats["quotes_fixed"] += 1
            changed = True
            break

    # --- Fix 4: CRLF → LF ---
    if "\r\n" in content:
        content = content.replace("\r\n", "\n")
        stats["crlf_fixed"] += 1
        changed = True

    # --- Write back if changed ---
    if changed:
        filepath.write_text(content, encoding="utf-8", newline="")
    else:
        stats["skipped"] += 1


def main() -> None:
    print(f"Scanning {SRC_DIR} for .dmn files...")
    dmn_files = sorted(SRC_DIR.rglob("*.dmn"))
    stats["total"] = len(dmn_files)
    print(f"Found {stats['total']} DMN files\n")

    for i, f in enumerate(dmn_files, 1):
        if i % 200 == 0 or i == len(dmn_files):
            print(f"  Processing {i}/{stats['total']}...")
        try:
            fix_dmn_file(f)
        except Exception as exc:
            print(f"  ERROR: {f.relative_to(SRC_DIR)} - {exc}", file=sys.stderr)

    print(f"\n{'='*60}")
    print(f"DMN Schema Fix Report")
    print(f"{'='*60}")
    print(f"Total files scanned:       {stats['total']}")
    print(f"namespace -> targetNS:     {stats['namespace_fixed']}")
    print(f"DMN 1.1 -> 1.3 upgraded:   {stats['dmn11_upgraded']}")
    print(f"JSON renamed (.dmn->.json):{stats['json_renamed']}")
    print(f"CRLF -> LF fixed:          {stats['crlf_fixed']}")
    print(f"XML quotes normalized:     {stats['quotes_fixed']}")
    print(f"Already OK (skipped):      {stats['skipped']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
