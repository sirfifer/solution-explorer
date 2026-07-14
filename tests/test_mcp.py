"""Tests for the MCP server (P8-1): the nine tools, response shapes, staleness
and confidence marking, truncation notices, guardrails, and a real stdio
JSON-RPC round trip against a fixture store.

The tools read only the store (invariant I9). Every response cites evidence and
marks confidence and AI staleness where applicable (I3, I5).
"""

import json
import os
import subprocess
import sys

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.digest import DigestIndex
from analyzer.extract import extract_repo
from analyzer.mcp.context import StoreContext
from analyzer.mcp.server import MCPServer
from analyzer.mcp.tools import TOOLS, ToolError, call_tool, render_result
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


def _build_store(path=":memory:", *, enrich=True):
    """Build a v2 store from the polyglot fixture, optionally with enrichment.

    Adds a FRESH component enrichment (digest matches), a STALE one (digest does
    not), an architecture narrative, a synthetic rule with a plain-language
    enrichment, and a synthetic concern, so every tool has something to surface.
    """
    store = FactStore(path)
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    if enrich:
        index = DigestIndex.from_store(store)
        fresh_digest = index.for_target("component", "services/api")
        store.add_enrichment(
            "component", "services/api",
            {"description": "Serves the user-facing HTTP API.", "help_text": "The API server."},
            derived_from_hash=fresh_digest, commit_sha="abcdef1234567890",
        )
        store.add_enrichment(
            "component", "services/web/src",
            {"description": "Stale note about the web client."},
            derived_from_hash="0" * 64, commit_sha="beef000000000000",
        )
        store.add_enrichment(
            "architecture", "@architecture",
            {"description": "A polyglot demo: an API server, a web client, and libraries."},
            derived_from_hash=index.for_target("architecture", "@architecture"),
            commit_sha="abcdef1234567890",
        )
        # A synthetic rule plus its plain-language enrichment.
        store.add_rule(
            "rule:services/api:validate-user-id", "services/api", "validation",
            summary="user_id must be a positive integer",
            evidence=[{"file": "services/api/api/server.py", "line": 33}],
            confidence="inferred",
        )
        store.add_enrichment(
            "rule", "rule:services/api:validate-user-id",
            {"name": "User id must be positive", "statement": "Reject non-positive user ids."},
            derived_from_hash=None, commit_sha="abcdef1234567890",
        )
        # A synthetic concern with a member component.
        store.add_concern(
            "concern:logging", "logging", title="Logging",
            basis="import of a logging module",
            members=[{"component_id": "services/api", "files": ["services/api/api/server.py"]}],
        )
        store.commit()
    return store


@pytest.fixture(scope="module")
def ctx():
    store = _build_store()
    yield StoreContext(store)
    store.close()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_exactly_nine_tools_with_expected_names():
    names = {t.name for t in TOOLS}
    assert names == {
        "se_overview", "se_search", "se_component", "se_symbol",
        "se_refs", "se_impact", "se_coverage", "se_rules", "se_findings",
    }
    assert len(TOOLS) == 9


def test_every_tool_has_a_json_schema_and_json_flag():
    for t in TOOLS:
        assert t.input_schema["type"] == "object"
        assert "json" in t.input_schema["properties"]


# ---------------------------------------------------------------------------
# Per-tool response shapes
# ---------------------------------------------------------------------------


def test_overview_counts_and_narrative(ctx):
    r = call_tool(ctx, "se_overview", {})
    d = r.data
    assert d["components"]["total"] == 8
    assert d["capabilities"]["by_kind"].get("api") == 1
    assert d["findings"]["total"] == 5
    assert d["findings"]["unverified"] == 5
    assert d["coverage"]["parsed"] == 13
    # One fresh + one stale + one architecture row were stamped.
    assert d["enrichment"]["stale"] >= 1
    assert d["architecture_narrative"]
    assert "ARCHITECTURE OVERVIEW" in r.text


def test_search_ranks_and_carries_context(ctx):
    r = call_tool(ctx, "se_search", {"query": "user"})
    assert r.data["count"] >= 1
    hit = r.data["results"][0]
    assert set(hit) == {"kind", "id", "context"}
    # A kind filter restricts ref_kind.
    r2 = call_tool(ctx, "se_search", {"query": "user", "kind": "component"})
    assert all(h["kind"] == "component" for h in r2.data["results"])


def test_component_card_has_edges_capabilities_and_evidence(ctx):
    r = call_tool(ctx, "se_component", {"id": "services/api"})
    d = r.data
    assert d["role"] == "api-server"
    assert d["capabilities"][0]["confidence"] == "certain"
    assert d["capabilities"][0]["evidence"][0]["file"].endswith("server.py")
    # One inbound edge from the web client, with confidence and evidence.
    assert len(d["edges_in"]) == 1
    e = d["edges_in"][0]
    assert e["type"] == "http"
    assert e["confidence"] == "inferred"
    assert e["evidence"][0]["line"] == 8


def test_component_fresh_vs_stale_enrichment_marked(ctx):
    fresh = call_tool(ctx, "se_component", {"id": "services/api"})
    assert fresh.data["enrichment"]["stale"] is False
    assert "STALE" not in fresh.text
    stale = call_tool(ctx, "se_component", {"id": "services/web/src"})
    assert stale.data["enrichment"]["stale"] is True
    assert "STALE" in stale.text


def test_symbol_card_signature_doc_preview_parent(ctx):
    sid = ". apps/ios apps/ios/Sources/App/ContentView.swift ContentView/increment"
    r = call_tool(ctx, "se_symbol", {"id": sid})
    d = r.data
    assert d["kind"] == "method"
    assert d["docstring"] == "Increment the counter."
    assert d["component"] == "apps/ios"
    assert d["parent_chain"][0].endswith("ContentView")
    assert d["file"].endswith("ContentView.swift")


def test_refs_reports_scope_and_direction(ctx):
    r = call_tool(ctx, "se_refs", {"id": "services/api"})
    assert "component granularity" in r.data["reference_resolution"]
    assert len(r.data["importers"]) == 1
    assert r.data["importers"][0]["id"] == "services/web/src"
    # A symbol id resolves to its containing component.
    sid = ". apps/ios apps/ios/Sources/App/ContentView.swift ContentView/increment"
    r2 = call_tool(ctx, "se_refs", {"id": sid, "direction": "out"})
    assert r2.data["resolved_component"] == "apps/ios"
    assert "importers" not in r2.data


def test_impact_ranked_with_evidence_chain(ctx):
    r = call_tool(ctx, "se_impact", {"id": "services/api"})
    d = r.data
    assert d["affected_count"] == 1
    hit = d["affected"][0]
    assert hit["id"] == "services/web/src"
    assert hit["depth"] == 1
    assert hit["via"]["type"] == "http"
    assert hit["via"]["evidence"][0]["line"] == 8


def test_coverage_summary_and_filtered_rows(ctx):
    summary = call_tool(ctx, "se_coverage", {})
    assert summary.data["by_disposition"]["parsed"] == 13
    rows = call_tool(ctx, "se_coverage", {"disposition": "excluded:unsupported_extension"})
    assert rows.data["count"] == 2
    assert all("path" in row for row in rows.data["rows"])


def test_rules_surfaces_plain_language_name(ctx):
    r = call_tool(ctx, "se_rules", {"component": "services/api"})
    assert r.data["count"] == 1
    rule = r.data["rules"][0]
    assert rule["kind"] == "validation"
    assert rule["plain_language"] == "User id must be positive"
    assert "User id must be positive" in r.text


def test_findings_always_show_verification_status(ctx):
    r = call_tool(ctx, "se_findings", {})
    assert r.data["count"] == 5
    for f in r.data["findings"]:
        assert "verification_status" in f
        assert f["unverified"] is True
    assert "[UNVERIFIED]" in r.text
    # A component filter also returns concern memberships.
    r2 = call_tool(ctx, "se_findings", {"component": "services/api"})
    assert any(c["id"] == "concern:logging" for c in r2.data["concern_memberships"])


def test_json_mode_returns_parseable_payload(ctx):
    r = call_tool(ctx, "se_component", {"id": "services/api"})
    parsed = json.loads(render_result(r, True))
    assert parsed["id"] == "services/api"
    assert parsed["capabilities"][0]["kind"] == "api"


# ---------------------------------------------------------------------------
# Truncation (no silent truncation, always an "N more" notice)
# ---------------------------------------------------------------------------


def test_findings_truncation_notice(ctx):
    r = call_tool(ctx, "se_findings", {"limit": 2})
    assert len(r.data["findings"]) == 2
    assert r.data["truncation_note"] is not None
    assert "3 more" in r.data["truncation_note"]
    assert "3 more" in r.text


def test_search_truncation_notice(ctx):
    r = call_tool(ctx, "se_search", {"query": "user", "limit": 1})
    assert r.data["truncated"] is True
    assert r.data["truncation_note"] is not None
    assert r.data["truncation_note"] in r.text


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def test_unknown_tool_raises_keyerror(ctx):
    with pytest.raises(KeyError):
        call_tool(ctx, "se_nonexistent", {})


def test_missing_required_arg_raises_toolerror(ctx):
    with pytest.raises(ToolError):
        call_tool(ctx, "se_component", {})
    with pytest.raises(ToolError):
        call_tool(ctx, "se_search", {})


def test_bad_id_raises_toolerror(ctx):
    with pytest.raises(ToolError):
        call_tool(ctx, "se_component", {"id": "no/such/component"})


def test_bad_limit_and_depth_raise_toolerror(ctx):
    with pytest.raises(ToolError):
        call_tool(ctx, "se_search", {"query": "user", "limit": 0})
    with pytest.raises(ToolError):
        call_tool(ctx, "se_impact", {"id": "services/api", "depth": 0})


# ---------------------------------------------------------------------------
# JSON-RPC dispatch (in-process, no subprocess)
# ---------------------------------------------------------------------------


def test_server_dispatch_initialize_list_call(ctx):
    server = MCPServer(ctx)
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18"}})
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "solution-explorer-mcp"

    # A notification returns nothing.
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 9

    called = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "se_overview", "arguments": {}}})
    assert called["result"]["isError"] is False
    assert "ARCHITECTURE OVERVIEW" in called["result"]["content"][0]["text"]


def test_server_dispatch_errors(ctx):
    server = MCPServer(ctx)
    unknown_method = server.handle({"jsonrpc": "2.0", "id": 1, "method": "nope"})
    assert unknown_method["error"]["code"] == -32601
    unknown_tool = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                 "params": {"name": "se_bogus", "arguments": {}}})
    assert unknown_tool["error"]["code"] == -32602
    bad_args = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "se_component", "arguments": {}}})
    assert bad_args["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# Real stdio round trip (mandatory proof): spawn the process, drive it.
# ---------------------------------------------------------------------------


def _rpc(msg):
    return json.dumps(msg) + "\n"


def test_stdio_round_trip(tmp_path):
    store_path = tmp_path / "polyglot.db"
    store = _build_store(str(store_path))
    store.close()

    proc = subprocess.Popen(
        [sys.executable, "-m", "analyzer.mcp", "--store", str(store_path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    script = (
        _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})
        + _rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + _rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "se_overview", "arguments": {}}})
        + _rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "se_search", "arguments": {"query": "user"}}})
        + _rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "se_impact", "arguments": {"id": "services/api", "json": True}}})
    )
    out, err = proc.communicate(script, timeout=60)
    assert proc.returncode == 0, err

    responses = [json.loads(line) for line in out.splitlines() if line.strip()]
    by_id = {r.get("id"): r for r in responses}

    assert by_id[1]["result"]["serverInfo"]["name"] == "solution-explorer-mcp"
    assert len(by_id[2]["result"]["tools"]) == 9
    assert "ARCHITECTURE OVERVIEW" in by_id[3]["result"]["content"][0]["text"]
    assert "SEARCH" in by_id[4]["result"]["content"][0]["text"]
    # id 5 asked for json mode: the content is a parseable impact payload.
    impact = json.loads(by_id[5]["result"]["content"][0]["text"])
    assert impact["affected"][0]["id"] == "services/web/src"


def test_stdio_missing_store_exits_cleanly(tmp_path):
    missing = tmp_path / "nope.db"
    proc = subprocess.run(
        [sys.executable, "-m", "analyzer.mcp", "--store", str(missing)],
        input="", capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)), timeout=30,
    )
    assert proc.returncode == 2
    assert "store not found" in proc.stderr
