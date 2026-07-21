"""Shape-and-completeness postcondition on MCP tool results (card R1 wave 4).

Each tool's result is validated at the dispatch handoff (``call_tool``): a
malformed result (a non-ToolResult, a non-string ``text``, or a non-dict
``data``) raises PostconditionError, which the server maps to a well-formed MCP
error instead of shipping quiet garbage (a JSON ``"null"`` or a non-string text
field rendered as a false success). An unexpected exception in a handler
degrades to a well-formed MCP error with per-tool attribution, and the server
loop never crashes.

Fail-before: pre-wave-4, a structurally-incomplete result was handed off with
``isError: false`` (a false success); now it is an honest INTERNAL_ERROR. The
tests drive the REAL dispatch and server over a fixture store.
"""

from __future__ import annotations

import os

import pytest

from analyzer.contracts import PostconditionError
from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.mcp import tools as tools_mod
from analyzer.mcp.context import StoreContext
from analyzer.mcp.server import INTERNAL_ERROR, MCPServer
from analyzer.mcp.tools import ToolResult, call_tool
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


@pytest.fixture(scope="module")
def ctx():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    yield StoreContext(store)
    store.close()


def _tools_call(server, name, arguments=None):
    return server.handle({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })


def _patch_handler(monkeypatch, name, fn):
    """Replace a tool's handler on its shared spec, reverted after the test."""
    spec = tools_mod.TOOLS_BY_NAME[name]
    monkeypatch.setattr(spec, "handler", fn)


# ---------------------------------------------------------------------------
# the postcondition itself (unit)
# ---------------------------------------------------------------------------


def test_call_tool_rejects_a_non_dict_data(ctx, monkeypatch):
    _patch_handler(monkeypatch, "se_overview", lambda c, a: ToolResult(text="ok", data=None))
    with pytest.raises(PostconditionError, match="result.data is not a dict"):
        call_tool(ctx, "se_overview", {})


def test_call_tool_rejects_a_non_string_text(ctx, monkeypatch):
    _patch_handler(monkeypatch, "se_overview", lambda c, a: ToolResult(text=None, data={}))
    with pytest.raises(PostconditionError, match="result.text is not a string"):
        call_tool(ctx, "se_overview", {})


def test_call_tool_rejects_a_non_tool_result(ctx, monkeypatch):
    _patch_handler(monkeypatch, "se_overview", lambda c, a: {"not": "a ToolResult"})
    with pytest.raises(PostconditionError, match="did not return a ToolResult"):
        call_tool(ctx, "se_overview", {})


def test_healthy_tool_still_passes_the_postcondition(ctx):
    # Regression guard: a real, well-formed result is unaffected by the check.
    result = call_tool(ctx, "se_overview", {})
    assert isinstance(result, ToolResult)
    assert isinstance(result.text, str) and result.text
    assert isinstance(result.data, dict)


# ---------------------------------------------------------------------------
# the server maps a bad result to a well-formed MCP error (never a crash)
# ---------------------------------------------------------------------------


def test_server_maps_incomplete_result_to_well_formed_error(ctx, monkeypatch):
    server = MCPServer(ctx)
    _patch_handler(monkeypatch, "se_overview", lambda c, a: ToolResult(text="ok", data=None))
    resp = _tools_call(server, "se_overview")
    # A well-formed JSON-RPC error, NOT a false-success result.
    assert "error" in resp
    assert "result" not in resp
    assert resp["error"]["code"] == INTERNAL_ERROR
    assert "incomplete result" in resp["error"]["message"]
    assert "se_overview" in resp["error"]["message"]


def test_server_maps_unexpected_handler_exception_to_error(ctx, monkeypatch):
    server = MCPServer(ctx)

    def _boom(c, a):
        raise RuntimeError("handler blew up")

    _patch_handler(monkeypatch, "se_overview", _boom)
    resp = _tools_call(server, "se_overview")
    assert "error" in resp
    assert resp["error"]["code"] == INTERNAL_ERROR
    assert "se_overview" in resp["error"]["message"]
    assert "RuntimeError" in resp["error"]["message"]


def test_server_loop_survives_a_bad_tool_and_serves_the_next_call(ctx, monkeypatch):
    # The bulkhead must never crash the dispatch: after a failing tool call the
    # SAME server answers a subsequent valid call normally.
    server = MCPServer(ctx)

    def _boom(c, a):
        raise RuntimeError("handler blew up")

    _patch_handler(monkeypatch, "se_overview", _boom)
    bad = _tools_call(server, "se_overview")
    assert "error" in bad
    # A different, healthy tool still works on the same server instance.
    good = _tools_call(server, "se_component", {"id": "services/api"})
    assert good["result"]["isError"] is False
    assert good["result"]["content"][0]["text"]


def test_healthy_tools_call_is_unchanged(ctx):
    server = MCPServer(ctx)
    resp = _tools_call(server, "se_overview")
    assert "error" not in resp
    assert resp["result"]["isError"] is False
    assert resp["result"]["content"][0]["text"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
