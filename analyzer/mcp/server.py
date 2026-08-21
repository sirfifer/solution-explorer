"""Minimal, correct MCP stdio server for the fact store.

The official `mcp` Python SDK is an optional dependency and is not required to
run this server (invariant I7: local-first, zero mandatory dependency). This
module speaks the MCP stdio transport directly: newline-delimited JSON-RPC 2.0
messages on stdin/stdout. It handles ``initialize``, ``notifications/initialized``,
``tools/list``, ``tools/call``, and ``ping``.

Upgrade path (recorded, TASKS.md P8-1): the twelve tools live in tools.py as pure
functions with JSON-Schema specs. Swapping to ``mcp.server.Server`` is a
transport change only; ``tools.TOOLS`` is handed over unchanged.

Everything here is a read over one open store. No writes, no LLM calls (I9).
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any, Optional

from ..contracts import PostconditionError
from . import __version__
from .context import StoreContext
from .tools import TOOLS, TOOLS_BY_NAME, ToolError, call_tool, render_result

# The latest MCP protocol revision this server targets. The server echoes the
# client's requested version when the client sends one (spec-compliant
# negotiation), falling back to this.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

# JSON-RPC error codes (subset of the spec).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class MCPServer:
    """Dispatches MCP JSON-RPC methods against a :class:`StoreContext`."""

    def __init__(self, ctx: StoreContext):
        self.ctx = ctx
        self._initialized = False

    # -- JSON-RPC plumbing -------------------------------------------------

    def _result(self, req_id: Any, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def handle(self, message: dict) -> Optional[dict]:
        """Handle one parsed JSON-RPC message; return a response, or None for a
        notification (a message with no ``id``)."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(message.get("id") if isinstance(message, dict) else None,
                               INVALID_REQUEST, "not a JSON-RPC 2.0 message")
        method = message.get("method")
        req_id = message.get("id")
        is_notification = "id" not in message
        params = message.get("params") or {}

        try:
            if method == "initialize":
                return self._result(req_id, self._initialize(params))
            if method == "notifications/initialized":
                self._initialized = True
                return None
            if method == "ping":
                return self._result(req_id, {})
            if method == "tools/list":
                return self._result(req_id, {"tools": self._tool_list()})
            if method == "tools/call":
                return self._tools_call(req_id, params)
            # Unknown notification: ignore. Unknown request: method not found.
            if is_notification:
                return None
            return self._error(req_id, METHOD_NOT_FOUND, f"unknown method: {method}")
        except Exception as exc:  # pragma: no cover - defensive
            if is_notification:
                return None
            return self._error(req_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

    def _initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) and requested else DEFAULT_PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "solution-explorer-mcp", "version": __version__},
            "instructions": (
                "Query a Solution Explorer fact store. Start with se_overview, "
                "then se_search to locate ids, then se_component / se_symbol / "
                "se_refs / se_impact for detail. Every answer cites file:line "
                "evidence and marks confidence and AI staleness."
            ),
        }

    def _tool_list(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
            for t in TOOLS
        ]

    def _tools_call(self, req_id: Any, params: dict) -> dict:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not name:
            return self._error(req_id, INVALID_PARAMS, "tools/call requires a 'name'")
        if not isinstance(arguments, dict):
            return self._error(req_id, INVALID_PARAMS, "'arguments' must be an object")
        # An unknown tool is resolved BEFORE dispatch so it maps to INVALID_PARAMS
        # here and can never be conflated with a handler that itself raises
        # KeyError over store data (adversarial review of PR #75, finding 1): that
        # is a real internal fault and must reach the INTERNAL_ERROR bulkhead
        # below with per-tool attribution, not be mislabeled "unknown tool".
        if name not in TOOLS_BY_NAME:
            return self._error(req_id, INVALID_PARAMS, f"unknown tool: {name}")
        # Per-tool bulkhead at the dispatch boundary (R1 wave 4). Each tool's
        # result is validated for shape-and-completeness inside call_tool; a
        # malformed result (PostconditionError) or an unexpected exception in the
        # handler degrades to a well-formed MCP error with per-tool attribution,
        # never a crashed server loop or a silent garbage handoff. ToolError
        # (malformed arguments) keeps its user-facing INVALID_PARAMS mapping.
        try:
            result = call_tool(self.ctx, name, arguments)
        except ToolError as exc:
            return self._error(req_id, INVALID_PARAMS, str(exc))
        except PostconditionError as exc:
            return self._error(
                req_id, INTERNAL_ERROR, f"tool '{name}' produced an incomplete result: {exc}"
            )
        except Exception as exc:  # noqa: BLE001 - tool bulkhead, never crash the loop
            return self._error(
                req_id, INTERNAL_ERROR, f"tool '{name}' failed: {type(exc).__name__}: {exc}"
            )
        try:
            as_json = bool(arguments.get("json"))
            text = render_result(result, as_json)
        except Exception as exc:  # noqa: BLE001 - rendering bulkhead, never crash the loop
            return self._error(
                req_id, INTERNAL_ERROR,
                f"rendering tool '{name}' result failed: {type(exc).__name__}: {exc}",
            )
        return self._result(
            req_id,
            {"content": [{"type": "text", "text": text}], "isError": False},
        )


def serve_stdio(server: MCPServer, instream: IO[str], outstream: IO[str]) -> None:
    """Run the newline-delimited JSON-RPC loop until stdin closes."""
    for raw in instream:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(outstream, {"jsonrpc": "2.0", "id": None,
                               "error": {"code": PARSE_ERROR, "message": "parse error"}})
            continue
        response = server.handle(message)
        if response is not None:
            _write(outstream, response)


def _write(outstream: IO[str], obj: dict) -> None:
    outstream.write(json.dumps(obj, default=str) + "\n")
    outstream.flush()


def run(store_path: str) -> int:
    """Open the store read-only and serve stdio. Returns a process exit code."""
    import os

    from ..store import FactStore

    if not os.path.exists(store_path):
        print(
            f"solution-explorer-mcp: store not found: {store_path}\n"
            "Build one first, for example: "
            "solution-explorer <repo> --engine v2 --split --store <path>",
            file=sys.stderr,
        )
        return 2
    try:
        store = FactStore(store_path)
    except Exception as exc:
        print(f"solution-explorer-mcp: cannot open store {store_path}: {exc}", file=sys.stderr)
        return 2
    try:
        ctx = StoreContext(store)
        server = MCPServer(ctx)
        serve_stdio(server, sys.stdin, sys.stdout)
    finally:
        store.close()
    return 0
