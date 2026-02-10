#!/usr/bin/env python3
import json
import os

with open('docs/Migration/migration_manifest.json') as f:
    data = json.load(f)

pending = [e for e in data.get('entries', []) if e.get('migration_status') != 'complete']

missing = []
for entry in pending:
    new_path = entry.get('new_path', '')
    full_path = os.path.join('/Users/rodrigo/claude-projects/Ochestrator-CIB7-OP/Healthcare-Orchest-CIB7', new_path)

    if not os.path.exists(full_path):
        missing.append(entry)

print(f'Total pending in manifest: {len(pending)}')
print(f'Actually missing files: {len(missing)}')
print()

for entry in missing:
    rule_id = entry.get('rule_id', 'N/A')
    new_path = entry.get('new_path', 'NO_PATH')
    print(f'{rule_id}|{new_path}')
