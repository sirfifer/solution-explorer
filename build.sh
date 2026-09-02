#!/usr/bin/env bash
set -euo pipefail

# SysCorpus build script
# Runs the analyzer and builds the static viewer.
# Output: viewer/dist/ (deploy anywhere)

# Split mode (manifest.json + per-component detail files) runs uncapped, so no
# symbols are silently truncated. The viewer auto-detects the manifest.
if [ -f "solution-explorer.json" ]; then
  echo "Multi-repo mode: using solution-explorer.json"
  python3 analyze.py --config solution-explorer.json -o viewer/public/architecture --split --compact
else
  ANALYZE_PATH="${1:-.}"
  echo "Single-repo mode: analyzing ${ANALYZE_PATH}"
  python3 analyze.py "${ANALYZE_PATH}" -o viewer/public/architecture --split --compact
fi

# A deployed viewer is a publication (docs/publication/PUBLICATION-METADATA.md).
# Validate the sidecar if it is there; warn loudly if it is not. Set
# SE_REQUIRE_PUBLICATION=1 to make its absence a hard failure, which is what
# any public demo of a codebase you do not own should do.
if [ -f "publication.json" ] && [ ! -f "viewer/public/publication.json" ]; then
  cp publication.json viewer/public/publication.json
fi
if [ "${SE_REQUIRE_PUBLICATION:-}" = "1" ]; then
  python3 scripts/validate-publication.py viewer/public --require
else
  python3 scripts/validate-publication.py viewer/public
fi

cd viewer
npm ci
npm run build

echo ""
echo "Build complete. Output: viewer/dist/"
echo "Deploy these static files to any web host."
