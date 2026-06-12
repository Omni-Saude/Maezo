#!/bin/bash
# BPMN Pre-Commit Validation Hook
# 
# Install: ln -s ../../scripts/bpmn_pre_commit_hook.sh .git/hooks/pre-commit
# Usage: Automatically runs on `git commit`

set -e

echo "🔍 Running BPMN compliance checks..."

# Get list of staged BPMN files
STAGED_BPMN=$(git diff --cached --name-only --diff-filter=ACM | grep '\.bpmn$' || true)

if [ -z "$STAGED_BPMN" ]; then
    echo "✅ No BPMN files in this commit"
    exit 0
fi

echo "📋 Checking $(echo "$STAGED_BPMN" | wc -l | tr -d ' ') BPMN file(s)..."

ERRORS=0

# R1: Check for Zeebe namespace
echo -n "  [R1] Namespace validation... "
ZEEBE_FILES=$(echo "$STAGED_BPMN" | xargs grep -l 'xmlns:camunda="http://camunda.org/schema/zeebe' 2>/dev/null || true)
if [ -n "$ZEEBE_FILES" ]; then
    echo "❌ FAILED"
    echo ""
    echo "  🔴 CRITICAL: Zeebe namespace found in:"
    echo "$ZEEBE_FILES" | sed 's/^/    - /'
    echo ""
    echo "  Fix: Replace with Camunda 7 namespace:"
    echo '    xmlns:camunda="http://camunda.org/schema/1.0/bpmn"'
    echo ""
    ERRORS=$((ERRORS + 1))
else
    echo "✅"
fi

# R3: Check for kebab-case topics (attribute form)
echo -n "  [R3] Topic format validation... "
KEBAB_FILES=""
for file in $STAGED_BPMN; do
    if grep -q 'camunda:topic="[^"]*-[^"]*"' "$file" 2>/dev/null; then
        KEBAB_FILES="$KEBAB_FILES $file"
    fi
done

if [ -n "$KEBAB_FILES" ]; then
    echo "❌ FAILED"
    echo ""
    echo "  🔴 CRITICAL: Kebab-case topics found in:"
    echo "$KEBAB_FILES" | tr ' ' '\n' | grep -v '^$' | sed 's/^/    - /'
    echo ""
    echo "  Fix: Use dot.snake_case format:"
    echo "    ❌ surgical-scheduling"
    echo "    ✅ surgical.scheduling"
    echo ""
    ERRORS=$((ERRORS + 1))
else
    echo "✅"
fi

# R2: Check filename convention SP-{DOMAIN}-{NNN}_{Description}.bpmn
echo -n "  [R2] Filename convention... "
INVALID_NAMES=""
for file in $STAGED_BPMN; do
    basename=$(basename "$file")
    # Allow templates to skip this check
    if echo "$file" | grep -q 'template'; then
        continue
    fi
    
    # Check if filename matches SP-XX-NNN pattern
    if ! echo "$basename" | grep -qE '^SP-(PA|CO|RC|PS)-[0-9]{3}_.*\.bpmn$'; then
        INVALID_NAMES="$INVALID_NAMES $file"
    fi
done

if [ -n "$INVALID_NAMES" ]; then
    echo "⚠️  WARNING"
    echo ""
    echo "  🟡 Non-standard filenames:"
    echo "$INVALID_NAMES" | tr ' ' '\n' | grep -v '^$' | sed 's/^/    - /'
    echo ""
    echo "  Expected: SP-{DOMAIN}-{NNN}_{Description}.bpmn"
    echo "  Domains: PA (patient_access), CO (clinical_operations)"
    echo "           RC (revenue_cycle), PS (platform_services)"
    echo ""
    # Warning only, don't block commit
else
    echo "✅"
fi

# R5: Check for duplicate process IDs across ALL bpmn files (not just staged)
echo -n "  [R5] Process ID uniqueness... "
TEMP_PROCESS_IDS=$(mktemp)

# Extract process IDs from all BPMN files
find healthcare_platform -name '*.bpmn' -not -path '*/.archive/*' -not -path '*/template*' 2>/dev/null | \
    xargs grep -h '<bpmn:process id=' 2>/dev/null | \
    sed -E 's/.*id="([^"]+)".*/\1/' | \
    sort > "$TEMP_PROCESS_IDS"

DUPLICATES=$(uniq -d < "$TEMP_PROCESS_IDS")
rm "$TEMP_PROCESS_IDS"

if [ -n "$DUPLICATES" ]; then
    echo "❌ FAILED"
    echo ""
    echo "  🔴 CRITICAL: Duplicate process IDs:"
    echo "$DUPLICATES" | sed 's/^/    - /'
    echo ""
    echo "  Each process ID must be unique across all BPMN files"
    echo ""
    ERRORS=$((ERRORS + 1))
else
    echo "✅"
fi

# R4: Check for BPMNDI presence (warning only)
echo -n "  [R4] BPMNDI diagram presence... "
MISSING_BPMNDI=""
for file in $STAGED_BPMN; do
    if ! grep -q 'bpmndi:BPMNDiagram' "$file" 2>/dev/null; then
        MISSING_BPMNDI="$MISSING_BPMNDI $file"
    fi
done

if [ -n "$MISSING_BPMNDI" ]; then
    echo "⚠️  WARNING"
    echo ""
    echo "  🟡 Missing BPMNDI sections (cannot edit in Camunda Modeler):"
    echo "$MISSING_BPMNDI" | tr ' ' '\n' | grep -v '^$' | sed 's/^/    - /'
    echo ""
    # Warning only, don't block
else
    echo "✅"
fi

echo ""
if [ $ERRORS -gt 0 ]; then
    echo "❌ Pre-commit validation FAILED with $ERRORS critical error(s)"
    echo ""
    echo "Fix the issues above and commit again."
    echo "Or bypass with: git commit --no-verify (NOT RECOMMENDED)"
    exit 1
else
    echo "✅ All BPMN compliance checks passed!"
    exit 0
fi
