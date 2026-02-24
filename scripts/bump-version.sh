#!/usr/bin/env bash
set -euo pipefail

# Usage: scripts/bump-version.sh <version>
# Updates the version across all package files from the canonical source.
#
# Examples:
#   scripts/bump-version.sh 0.3.0
#   scripts/bump-version.sh 0.4.0-beta.1

VERSION="${1:?Usage: bump-version.sh <version>}"

# Validate semver format (with optional prerelease)
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
  echo "Error: '$VERSION' is not valid semver"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 1. Update canonical source (analyzer/__init__.py)
sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" \
  "$REPO_ROOT/analyzer/__init__.py"

# 2. Update CLI package.json
cd "$REPO_ROOT/packages/cli"
npm version "$VERSION" --no-git-tag-version --allow-same-version >/dev/null

# 3. Update viewer package.json
cd "$REPO_ROOT/viewer"
npm version "$VERSION" --no-git-tag-version --allow-same-version >/dev/null

echo "Version updated to $VERSION in:"
echo "  analyzer/__init__.py"
echo "  packages/cli/package.json"
echo "  viewer/package.json"
