#!/usr/bin/env python3
"""
Architecture Analyzer - Extracts architecture from any codebase.

Outputs a hierarchical architecture.json for the interactive viewer.

Usage:
    python analyze.py /path/to/repo -o architecture.json
    python analyze.py .  # analyze current directory

This is a thin wrapper around the analyzer package.
See analyzer/ for the full implementation.
"""

# Re-export key classes for backward compatibility with existing imports
# (e.g., tests, scripts that do `from analyze import ArchitectureScanner`)
from analyzer.models import (  # noqa: F401
    Architecture,
    Component,
    ComponentDoc,
    FileInfo,
    Relationship,
    Symbol,
)
from analyzer.parsers import (  # noqa: F401
    PARSERS,
    BaseParser,
    GoParser,
    PythonParser,
    RubyParser,
    RustParser,
    SwiftParser,
    TypeScriptParser,
)
from analyzer.scanner import ArchitectureScanner  # noqa: F401
from analyzer.multi_repo import MultiRepoOrchestrator  # noqa: F401
from analyzer.swiftui_flow import SwiftUIFlowDetector  # noqa: F401
from analyzer.cli import main  # noqa: F401

if __name__ == "__main__":
    main()
