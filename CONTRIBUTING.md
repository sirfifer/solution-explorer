# Contributing to Solution Explorer

Thank you for your interest in contributing to Solution Explorer! This guide will help you get started.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/solution-explorer.git
   cd solution-explorer
   ```
3. **Set up the development environment**:
   ```bash
   # Python analyzer (no external dependencies needed)
   python3 --version  # Requires 3.10+

   # React viewer
   cd viewer
   npm install
   ```
4. **Create a branch** for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Running Locally

```bash
# Analyze a codebase (produces architecture.json)
python3 analyze.py /path/to/repo -o viewer/public/architecture.json

# Start the viewer in dev mode
cd viewer && npm run dev
```

### Running Tests

```bash
# Python tests
python3 -m pytest tests/ -v

# TypeScript tests
cd viewer && npm test

# Linting
ruff check analyze.py
cd viewer && npm run lint
```

### Code Style

**Python (analyze.py):**
- Formatted and linted with [Ruff](https://docs.astral.sh/ruff/)
- Line length limit: 120 characters
- Target: Python 3.10+
- Zero external dependencies (stdlib only)

**TypeScript (viewer):**
- Linted with ESLint
- Built with Vite + React 19
- Styled with Tailwind CSS

Run the linters before submitting:
```bash
ruff check analyze.py
cd viewer && npm run lint
```

## What to Contribute

### Good First Issues

Look for issues tagged with [`good first issue`](https://github.com/sirfifer/solution-explorer/labels/good%20first%20issue) for beginner-friendly tasks.

### Areas Where Help Is Welcome

- **Language support**: Improve parsing for existing languages or add new ones
- **Viewer features**: New visualizations, improved interactions, accessibility
- **Documentation**: Tutorials, examples, improving existing docs
- **Bug fixes**: Check the [issue tracker](https://github.com/sirfifer/solution-explorer/issues)
- **Testing**: Expanding test coverage for parsers and viewer components

### Adding Language Support

The analyzer in `analyze.py` supports multiple languages. To improve parsing for an existing language or add a new one:

1. Study the existing parser classes (e.g., `SwiftParser`, `PythonParser`, `GoParser`)
2. Add or modify the parser in `analyze.py`
3. Add test cases in `tests/test_analyzer.py`
4. Test against real-world codebases in that language

## Submitting Changes

1. **Commit your changes** with clear, descriptive messages
2. **Push to your fork**: `git push origin feature/your-feature-name`
3. **Open a Pull Request** against `main`
4. **Describe your changes** in the PR description, including:
   - What the change does
   - Why it's needed
   - How to test it
   - Screenshots (if there are UI changes)

### Pull Request Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Make sure all existing tests pass
- Update documentation if your change affects user-facing behavior
- Follow the existing code style

## Reporting Bugs

When reporting a bug, please include:

1. A clear description of the problem
2. Steps to reproduce
3. Expected vs. actual behavior
4. The language/framework of the codebase you were analyzing (if relevant)
5. Your environment (OS, Python version, Node.js version)

## Suggesting Features

Feature suggestions are welcome! Please open an issue describing:

1. The problem you're trying to solve
2. Your proposed solution
3. Any alternatives you've considered

## Architecture Overview

Understanding the project structure helps with contributing:

```
solution-explorer/
├── analyze.py          # Core analyzer (Python, zero dependencies)
├── action.yml          # GitHub Action definition
├── build.sh            # Static site build script
├── tests/              # Python test suite
└── viewer/             # React/TypeScript frontend
    ├── src/
    │   ├── components/ # React components (nodes, panels, search)
    │   ├── utils/      # Layout, search, documentation utilities
    │   ├── store.ts    # Zustand state management
    │   └── types.ts    # TypeScript type definitions
    └── public/         # Static assets + generated architecture.json
```

The **analyzer** walks a codebase, detects components via marker files, parses source files for symbols and relationships, and outputs `architecture.json`. The **viewer** reads that JSON and renders an interactive graph using React Flow and ELK layout.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## Questions?

Open an issue or start a discussion. We're happy to help!
