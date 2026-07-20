"""Per-ecosystem manifest parser registry.

Each ecosystem module exposes ``ECOSYSTEM`` (the id), ``is_anchored(filenames)``
(does this directory anchor an instance of the ecosystem), and
``collect(root, dirpath, filenames)`` returning an ``EcosystemResult``. The
collector walks the tree, groups candidate manifest files by directory, and asks
each registered ecosystem whether that directory anchors it. The registry order
is the stable presentation order for the supply chain surface.
"""

from __future__ import annotations

from . import cargo, cocoapods, gem, golang, npm, nuget, pypi, swift

# Registration order is the deterministic label order in the projection.
ECOSYSTEM_MODULES = (npm, pypi, swift, golang, gem, cargo, cocoapods, nuget)

# Human labels for the supply chain surface, keyed by ecosystem id.
ECOSYSTEM_LABELS: dict[str, str] = {
    "npm": "npm (Node.js)",
    "pypi": "PyPI (Python)",
    "swift": "Swift Package Manager",
    "golang": "Go modules",
    "gem": "RubyGems (Bundler)",
    "cargo": "Cargo (Rust)",
    "cocoapods": "CocoaPods",
    "nuget": "NuGet (.NET)",
}

__all__ = ["ECOSYSTEM_MODULES", "ECOSYSTEM_LABELS"]
