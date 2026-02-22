#!/usr/bin/env bash
set -euo pipefail

# Validate that the solution-explorer preview is serving correctly.
# Usage: scripts/validate-preview.sh [URL]
# Exits non-zero on any failure.

PREVIEW_URL="${1:-http://localhost:4173}"
SE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "Validating solution-explorer preview..."
echo "  Root: $SE_ROOT"
echo "  URL:  $PREVIEW_URL"
echo ""

# --- Static checks ---
echo "Static checks:"

# 1. architecture.json exists and is valid JSON with expected structure
ARCH_FILE="$SE_ROOT/viewer/public/architecture.json"
if [ ! -f "$ARCH_FILE" ]; then
  fail "viewer/public/architecture.json does not exist"
else
  if python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    for key in ('components', 'relationships', 'stats'):
        assert key in d, f'missing key: {key}'
    assert len(d['components']) > 0, 'components array is empty'
    print(f'       {len(d[\"components\"])} top-level components, {len(d[\"relationships\"])} relationships')
except Exception as e:
    print(f'       {e}', file=sys.stderr)
    sys.exit(1)
" "$ARCH_FILE" 2>&1; then
    pass "architecture.json is valid with expected structure"
  else
    fail "architecture.json is invalid or missing required keys"
  fi
fi

# 2. dist/index.html exists
if [ -f "$SE_ROOT/viewer/dist/index.html" ]; then
  pass "viewer/dist/index.html exists"
else
  fail "viewer/dist/index.html missing (was the viewer built?)"
fi

# 3. dist/assets/ has JS and CSS files
JS_COUNT=$(find "$SE_ROOT/viewer/dist/assets" -name "*.js" 2>/dev/null | wc -l | tr -d ' ')
CSS_COUNT=$(find "$SE_ROOT/viewer/dist/assets" -name "*.css" 2>/dev/null | wc -l | tr -d ' ')
if [ "$JS_COUNT" -gt 0 ] && [ "$CSS_COUNT" -gt 0 ]; then
  pass "dist/assets/ contains JS ($JS_COUNT) and CSS ($CSS_COUNT) files"
else
  fail "dist/assets/ missing JS ($JS_COUNT) or CSS ($CSS_COUNT) files"
fi

echo ""

# --- HTTP checks ---
echo "HTTP checks (against $PREVIEW_URL):"

fetch_info() {
  curl -sS -o /dev/null -w "%{http_code}|%{content_type}" --max-time 10 "$1" 2>/dev/null || echo "000|error"
}

# 4. Index page returns HTML
RESULT=$(fetch_info "$PREVIEW_URL/")
HTTP_CODE="${RESULT%%|*}"
CONTENT_TYPE="${RESULT##*|}"
if [ "$HTTP_CODE" = "200" ] && echo "$CONTENT_TYPE" | grep -qi "html"; then
  pass "GET / returns 200 with text/html"
else
  fail "GET / returned $HTTP_CODE with $CONTENT_TYPE (expected 200 + text/html)"
fi

# 5. architecture.json returns valid JSON
ARCH_URL="$PREVIEW_URL/architecture.json"
RESULT=$(fetch_info "$ARCH_URL")
HTTP_CODE="${RESULT%%|*}"
CONTENT_TYPE="${RESULT##*|}"
if [ "$HTTP_CODE" = "200" ] && echo "$CONTENT_TYPE" | grep -qi "json"; then
  if curl -sS --max-time 10 "$ARCH_URL" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'components' in d" 2>/dev/null; then
    pass "GET /architecture.json returns 200 with application/json and valid body"
  else
    fail "GET /architecture.json has JSON content-type but body is not valid JSON"
  fi
else
  fail "GET /architecture.json returned $HTTP_CODE with $CONTENT_TYPE (expected 200 + application/json)"
fi

# 6. Non-existent JSON path is rejected by content-type check
MANIFEST_URL="$PREVIEW_URL/architecture/manifest.json"
RESULT=$(fetch_info "$MANIFEST_URL")
HTTP_CODE="${RESULT%%|*}"
CONTENT_TYPE="${RESULT##*|}"
if [ "$HTTP_CODE" != "200" ]; then
  pass "GET /architecture/manifest.json returns $HTTP_CODE (not found, as expected)"
elif ! echo "$CONTENT_TYPE" | grep -qi "json"; then
  pass "GET /architecture/manifest.json returns 200 but content-type is '$CONTENT_TYPE' (app will correctly reject it)"
else
  # This is expected in split mode where manifest.json actually exists
  pass "GET /architecture/manifest.json returns 200 with JSON content-type (split mode detected)"
fi

echo ""

# --- Summary ---
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "VALIDATION FAILED. Fix the issues above before proceeding."
  exit 1
fi

echo "All checks passed. Preview is ready."
exit 0
