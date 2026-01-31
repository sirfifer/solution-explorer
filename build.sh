#!/usr/bin/env bash
set -euo pipefail

# Solution Explorer build script
# Runs the analyzer and builds the static viewer.
# Output: viewer/dist/ (deploy anywhere)

if [ -f "solution-explorer.json" ]; then
  echo "Multi-repo mode: using solution-explorer.json"
  python3 analyze.py --config solution-explorer.json -o viewer/public/architecture.json --compact
else
  ANALYZE_PATH="${1:-.}"
  echo "Single-repo mode: analyzing ${ANALYZE_PATH}"
  python3 analyze.py "${ANALYZE_PATH}" -o viewer/public/architecture.json --compact
fi

cd viewer
npm ci
npm run build

echo ""
echo "Build complete. Output: viewer/dist/"
echo "Deploy these static files to any web host."
