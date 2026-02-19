# Analyzer Package Architecture

The `analyzer/` package is the core of Solution Explorer's static analysis. It scans codebases to extract components, relationships, symbols, and metrics, producing structured JSON for the interactive viewer.

## Package Structure

```
analyzer/
├── __init__.py          # Package marker, version
├── cli.py               # CLI entry point (argparse, output handling)
├── models.py            # Data model (dataclasses)
├── constants.py         # Shared constants (skip dirs, language maps, markers)
├── utils.py             # Shared utility functions
├── config_parsers.py    # Config file parsers (package.json, Cargo.toml, etc.)
├── scanner.py           # ArchitectureScanner (core orchestration)
├── swiftui_flow.py      # SwiftUI navigation/tab flow detection
├── multi_repo.py        # Multi-repo orchestration
└── parsers/             # Per-language source parsers
    ├── __init__.py      # Parser registry (PARSERS dict)
    ├── base.py          # BaseParser interface
    ├── swift.py         # SwiftParser
    ├── python_lang.py   # PythonParser
    ├── typescript.py    # TypeScriptParser (also handles JavaScript)
    ├── go.py            # GoParser
    ├── rust.py          # RustParser
    └── ruby.py          # RubyParser
```

## Import Dependency Order

Modules are ordered to avoid circular imports:

```
constants.py       ← no internal imports
models.py          ← no internal imports
utils.py           ← imports constants
parsers/base.py    ← imports models
parsers/*.py       ← imports models, parsers.base
parsers/__init__.py ← imports all parsers, exports PARSERS dict
config_parsers.py  ← imports models
swiftui_flow.py    ← imports models, utils, constants
scanner.py         ← imports models, constants, utils, parsers, config_parsers, swiftui_flow
multi_repo.py      ← imports models, scanner
cli.py             ← imports scanner, multi_repo
```

## Key Classes

### ArchitectureScanner (`scanner.py`)

The main orchestrator. Takes a root `Path` and runs a 6-phase scan pipeline:

1. **Discover components** via marker files (package.json, Cargo.toml, Info.plist, etc.)
2. **Scan files** using per-language parsers to extract symbols and imports
3. **Promote types** (detect component type from framework, directory structure, config)
4. **Detect relationships** (imports, port-based HTTP, Docker links, URL patterns)
5. **Compute metrics** (file counts, line counts, size, language breakdown)
6. **Extract documentation** (README, CLAUDE.md, CHANGELOG, API endpoints, env vars)

```python
from pathlib import Path
from analyzer.scanner import ArchitectureScanner

scanner = ArchitectureScanner(Path("/path/to/repo"))
arch = scanner.scan()  # Returns an Architecture dataclass
```

### BaseParser (`parsers/base.py`)

All language parsers extend `BaseParser` and implement three methods:

- `extract_symbols(file_path, content, lines)` → list of `Symbol` dataclasses
- `extract_imports(content, lines)` → list of import strings
- `detect_framework(file_path, content)` → framework name or `None`

### SwiftUIFlowDetector (`swiftui_flow.py`)

Detects SwiftUI navigation flows: TabView tabs, NavigationLink targets, sheet/fullScreenCover presentations, and embedded view composition. Uses BFS with distance-based tab assignment to build the screen hierarchy.

### MultiRepoOrchestrator (`multi_repo.py`)

Coordinates analysis across multiple repositories defined in a `solution-explorer.json` config file. Clones remote repos, runs `ArchitectureScanner` on each, and merges results.

## Data Model (`models.py`)

All data is represented as Python dataclasses:

| Class | Purpose |
|-------|---------|
| `Architecture` | Root container: components, relationships, symbols, files, stats |
| `Component` | A logical unit (app, library, service) with children for hierarchy |
| `Symbol` | A code entity (class, struct, function, etc.) with file and line info |
| `Relationship` | A connection between two components (import, HTTP, Docker, etc.) |
| `FileInfo` | Metadata for a source file (path, language, lines, size, symbols) |
| `ComponentDoc` | Documentation extracted from README, config files, comments |

## Output Modes

### Single-file mode (default)

```bash
python3 analyze.py /path/to/repo -o architecture.json
```

Produces one JSON file with everything. Default symbol limit is 5,000 (use `--max-symbols 0` for unlimited).

### Split mode

```bash
python3 analyze.py /path/to/repo -o architecture/ --split
```

Produces a directory:
- `manifest.json`: Component tree, relationships, stats (small, ~20-100 KB)
- `data/detail-{component-id}.json`: Symbols and files per component (loaded on demand)

No symbol limit in split mode (symbols are naturally bounded per component).

## Adding a New Language Parser

1. Create `analyzer/parsers/your_lang.py`
2. Extend `BaseParser`:

```python
from ..parsers.base import BaseParser
from ..models import Symbol

class YourLangParser(BaseParser):
    def extract_symbols(self, file_path, content, lines):
        symbols = []
        # Parse the file, create Symbol instances
        return symbols

    def extract_imports(self, content, lines):
        imports = []
        # Extract import/require/use statements
        return imports

    def detect_framework(self, file_path, content):
        # Return framework name or None
        return None
```

3. Register in `analyzer/parsers/__init__.py`:

```python
from .your_lang import YourLangParser

PARSERS = {
    # ... existing entries ...
    "yourlang": YourLangParser,
}
```

4. Add language extension mapping in `analyzer/constants.py` under `LANGUAGE_MAP`.

5. Write tests in `tests/test_parsers_extra.py` or a new test file.

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run with coverage
python3 -m pytest tests/ --cov=analyzer --cov-report=term-missing

# Run a specific test file
python3 -m pytest tests/test_utils.py -v
```

Test files:
- `test_analyzer.py`: Core integration tests (components, symbols, relationships)
- `test_utils.py`: Unit tests for `utils.py` and `config_parsers.py`
- `test_cli.py`: CLI argument parsing and split output
- `test_parsers_extra.py`: Ruby parser and SwiftUI flow detector
- `test_scanner_deep.py`: Scanner internals (discovery, type promotion, frameworks)

## Backward Compatibility

`analyze.py` at the project root is a thin wrapper that re-exports all public symbols from the package. Existing scripts, GitHub Actions, and CLI usage continue to work:

```python
# These all still work:
from analyze import ArchitectureScanner, Symbol, Component
python3 analyze.py /path/to/repo
```
