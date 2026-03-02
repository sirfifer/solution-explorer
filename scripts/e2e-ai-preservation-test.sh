#!/usr/bin/env bash
set -euo pipefail

# End-to-end AI enhancement preservation test.
#
# Runs a fresh analysis on a codebase, merges AI enhancements from a baseline,
# then validates that all ai_enhance data on unchanged components is preserved.
#
# Usage:
#   scripts/e2e-ai-preservation-test.sh <codebase-path> <baseline-json> [changed-components]
#
# Example:
#   scripts/e2e-ai-preservation-test.sh \
#     /Users/ramerman/dev/unamentis \
#     /Users/ramerman/dev/unamentis/.arch-baseline/architecture.json \
#     "unamentis/services/featureflags"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 2 ]; then
    echo "Usage: $0 <codebase-path> <baseline-json> [changed-components]"
    exit 2
fi

CODEBASE="$1"
BASELINE="$2"
CHANGED="${3:-}"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "============================================================"
echo "E2E AI Enhancement Preservation Test"
echo "============================================================"
echo "Codebase:   $CODEBASE"
echo "Baseline:   $BASELINE"
echo "Changed:    ${CHANGED:-none}"
echo "Temp dir:   $TMPDIR"
echo ""

# Step 1: Fresh scan
echo "--- Step 1: Running fresh analysis ---"
python3 "$REPO_DIR/analyze.py" "$CODEBASE" \
    -o "$TMPDIR/fresh-scan.json" --pretty

# Quick sanity check: fresh scan should have no ai_enhance
AI_COUNT=$(python3 -c "
import json
d = json.load(open('$TMPDIR/fresh-scan.json'))
count = 0
if 'ai_enhance' in d: count += 1
def walk(cs):
    n = 0
    for c in cs:
        if 'ai_enhance' in c: n += 1
        n += walk(c.get('children', []))
    return n
count += walk(d.get('components', []))
count += sum(1 for r in d.get('relationships', []) if 'ai_enhance' in r)
print(count)
")

if [ "$AI_COUNT" -ne 0 ]; then
    echo "WARNING: Fresh scan contains $AI_COUNT ai_enhance entries (expected 0)"
else
    echo "  Fresh scan confirmed: 0 ai_enhance entries (correct)"
fi
echo ""

# Step 2: Merge AI enhancements from baseline
echo "--- Step 2: Merging AI enhancements from baseline ---"
cp "$TMPDIR/fresh-scan.json" "$TMPDIR/merged.json"
python3 "$SCRIPT_DIR/merge-ai-enhancements.py" \
    --baseline "$BASELINE" \
    --target "$TMPDIR/merged.json"
echo ""

# Step 3: Validate preservation
echo "--- Step 3: Validating AI enhancement preservation ---"
echo ""
python3 "$SCRIPT_DIR/validate-ai-preservation.py" \
    --baseline "$BASELINE" \
    --result "$TMPDIR/merged.json" \
    --changed-components "$CHANGED"
