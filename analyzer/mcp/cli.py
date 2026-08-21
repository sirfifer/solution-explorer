"""Console entry point: ``solution-explorer-mcp --store PATH``.

Starts the MCP stdio server over an existing v2 fact store. A missing store is a
clean, non-zero exit with a message (a guardrail, not a stack trace).
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from . import __version__
from .server import run


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution-explorer-mcp",
        description="MCP server exposing a Solution Explorer fact store to AI agents "
        "(twelve read-only tools over stdio JSON-RPC).",
    )
    parser.add_argument(
        "--store",
        required=True,
        help="Path to the v2 fact-store database (built with "
        "`solution-explorer <repo> --engine v2 --split --store <path>`).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    return run(args.store)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
