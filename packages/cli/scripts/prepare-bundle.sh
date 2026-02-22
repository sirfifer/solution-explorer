#!/usr/bin/env bash
set -euo pipefail

# Prepare the npm package bundle before publishing.
# Copies the pre-built viewer, Python analyzer, and support scripts
# into the CLI package directory so they ship with the npm package.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLI_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$CLI_DIR/../.." && pwd)"

echo "Preparing solution-explorer npm package bundle..."
echo "  CLI dir:   $CLI_DIR"
echo "  Repo root: $REPO_ROOT"

# 1. Build the viewer if needed
VIEWER_DIST="$REPO_ROOT/viewer/dist"
if [ ! -d "$VIEWER_DIST" ] || [ ! -f "$VIEWER_DIST/index.html" ]; then
  echo "  Building viewer..."
  cd "$REPO_ROOT/viewer"
  npm ci
  npm run build
  cd "$CLI_DIR"
fi

# 2. Copy viewer dist
echo "  Copying viewer dist..."
rm -rf "$CLI_DIR/viewer-dist"
cp -r "$VIEWER_DIST" "$CLI_DIR/viewer-dist"

# Remove architecture.json from viewer-dist if it exists (will be generated fresh)
rm -f "$CLI_DIR/viewer-dist/architecture.json"

# 3. Copy Python analyzer (stdlib-only, no deps needed)
echo "  Copying analyzer..."
rm -rf "$CLI_DIR/analyzer"
cp -r "$REPO_ROOT/analyzer" "$CLI_DIR/analyzer"
cp "$REPO_ROOT/analyze.py" "$CLI_DIR/analyze.py"

# Remove __pycache__ and .pyc files
find "$CLI_DIR/analyzer" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$CLI_DIR/analyzer" -name "*.pyc" -delete 2>/dev/null || true

# 4. Copy support scripts for live monitoring
echo "  Copying support scripts..."
rm -rf "$CLI_DIR/scripts-bundle"
mkdir -p "$CLI_DIR/scripts-bundle"
for script in collect-ci-status.py generate-admin-summary.py; do
  if [ -f "$REPO_ROOT/scripts/$script" ]; then
    cp "$REPO_ROOT/scripts/$script" "$CLI_DIR/scripts-bundle/$script"
  fi
done

echo "  Bundle ready."
echo ""
echo "  Contents:"
echo "    viewer-dist/   $(du -sh "$CLI_DIR/viewer-dist" | cut -f1) (pre-built viewer)"
echo "    analyzer/      $(du -sh "$CLI_DIR/analyzer" | cut -f1) (Python analyzer)"
echo "    analyze.py     (analyzer entry point)"
echo "    scripts-bundle/ (live monitoring scripts)"
